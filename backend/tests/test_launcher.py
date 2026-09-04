"""First-run setup and the local launcher must never replace existing accounts."""

import importlib.util
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from app import cli
from app.db import Base, connect
from app.models import AuditEvent, Membership, Product, Session, User
from app.security import new_session, password_hash, verify_password
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_launcher", ROOT / "scripts/launch.py"
)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
PASSWORD = "launcher-test-only-2026"


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", url)
    engine, factory = connect(url)
    Base.metadata.create_all(engine)
    yield factory
    engine.dispose()


def wizard_input(monkeypatch, answers, passwords=None):
    answers = iter(answers)
    passwords = iter(passwords or [PASSWORD, PASSWORD])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)


def seed_admin(factory, roles=None):
    with factory.begin() as db:
        return cli.create_initial_admin(
            db,
            group="隔离测试集团",
            manager="隔离测试牌照",
            email="admin@test.invalid",
            name="测试管理员",
            roles=roles or ["admin", "operator"],
            download=True,
            encoded=password_hash(PASSWORD),
        )


@pytest.mark.parametrize(
    "operator,download,roles,can_download",
    [
        ("", "", ["admin"], False),
        ("y", "n", ["admin", "operator"], False),
        ("是", "yes", ["admin", "operator"], True),
    ],
)
def test_first_setup_explicit_permissions_no_demo_data(
    local_db, monkeypatch, operator, download, roles, can_download
):
    wizard_input(
        monkeypatch, ["测试公司", "", "", "Admin@Test.Invalid", operator, download]
    )
    with local_db.begin() as db:
        cli.setup(db)
    with local_db() as db:
        user = db.scalar(select(User))
        member = db.scalar(select(Membership))
        assert user.email == "admin@test.invalid"
        assert user.name == "管理员"
        assert user.password_hash != PASSWORD
        assert verify_password(user.password_hash, PASSWORD)
        assert member.roles == roles and member.can_download == can_download
        assert db.scalar(select(func.count()).select_from(Product)) == 0
        assert db.scalar(select(AuditEvent)).action == "system.bootstrapped"


def test_existing_setup_never_prompts_or_changes_password(
    local_db, monkeypatch, capsys
):
    seed_admin(local_db)
    with local_db() as db:
        encoded = db.scalar(select(User.password_hash))
    monkeypatch.setattr(
        "builtins.input", lambda _: pytest.fail("must not prompt again")
    )
    monkeypatch.setattr(
        cli.getpass, "getpass", lambda _: pytest.fail("must not reset password")
    )
    for _ in range(2):
        with local_db.begin() as db:
            cli.setup(db)
    with local_db() as db:
        assert db.scalar(select(User.password_hash)) == encoded
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
    assert "admin@test.invalid" in capsys.readouterr().out


def test_first_setup_refuses_noninteractive_password(local_db, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(ValueError, match="首次运行需要在终端"), local_db.begin() as db:
        cli.setup(db)
    with local_db() as db:
        assert db.scalar(select(User)) is None


def test_cancelled_setup_leaves_no_partial_account(local_db, monkeypatch):
    wizard_input(monkeypatch, ["公司", "", "", "admin@test.invalid", "y", "y"])

    def cancel(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.getpass, "getpass", cancel)
    with pytest.raises(KeyboardInterrupt), local_db.begin() as db:
        cli.setup(db)
    with local_db() as db:
        assert db.scalar(select(User)) is None
        assert db.scalar(select(Membership)) is None
        assert db.scalar(select(AuditEvent)) is None


def test_setup_without_active_admin_does_not_reinitialize(local_db):
    seed_admin(local_db, ["operator"])
    with pytest.raises(ValueError, match="没有可用管理员"), local_db.begin() as db:
        cli.setup(db)
    with local_db() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_password_validation_retries_and_never_prints_password(monkeypatch, capsys):
    passwords = iter(["short", PASSWORD, "mismatched-2026", PASSWORD, PASSWORD])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))
    assert verify_password(cli.ask_password(), PASSWORD)
    output = capsys.readouterr().out
    assert "密码长度" in output and "不一致" in output
    assert PASSWORD not in output


def test_cli_password_reset_revokes_sessions_without_changing_roles(
    local_db, monkeypatch
):
    seed_admin(local_db)
    with local_db.begin() as db:
        user = db.scalar(select(User))
        new_session(db, user.id, 8)
        new_session(db, user.id, 8)
    monkeypatch.setattr(
        sys, "argv", ["cli", "reset-password", "--email", "ADMIN@test.invalid"]
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "replacement-test-only-2026")
    cli.main()
    with local_db() as db:
        user = db.scalar(select(User))
        assert verify_password(user.password_hash, "replacement-test-only-2026")
        assert not verify_password(user.password_hash, PASSWORD)
        assert db.scalar(select(func.count()).select_from(Session)) == 0
        assert db.scalar(select(Membership.roles)) == ["admin", "operator"]
        assert "user.password_reset" in list(db.scalars(select(AuditEvent.action)))


def test_local_config_uses_exact_origin_and_rejects_external_database(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ARCHIVE_DIR", raising=False)
    env = launcher.local_environment(tmp_path, 18001)
    assert env["DATABASE_URL"] == "sqlite:///./runtime/development.db"
    assert env["COOKIE_SECURE"] == "false"
    assert env["ALLOWED_ORIGINS"] == "http://127.0.0.1:18001,http://localhost:18001"
    assert env["PYTHONPATH"] == str(tmp_path / "backend")
    monkeypatch.setenv("DATABASE_URL", "postgresql://do-not-connect")
    with pytest.raises(launcher.LaunchError, match="检测到 DATABASE_URL"):
        launcher.local_environment(tmp_path, 8000)


def test_launch_lock_prevents_duplicate_workers_and_releases(tmp_path):
    with (
        launcher.launch_lock(tmp_path, "http://127.0.0.1:18001"),
        pytest.raises(launcher.LaunchError, match="18001"),
        launcher.launch_lock(tmp_path, "http://127.0.0.1:18002"),
    ):
        pytest.fail("second process must not start")
    with launcher.launch_lock(tmp_path, "http://127.0.0.1:18002"):
        assert (tmp_path / "launcher.lock").read_text() == "http://127.0.0.1:18002"


def test_port_conflict_never_terminates_existing_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(launcher.LaunchError, match="未停止任何已有服务"):
            launcher.check_port(port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_build_fingerprint_covers_content_and_name(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("first")
    first = launcher.digest_files([source], tmp_path)
    source.write_text("second")
    assert launcher.digest_files([source], tmp_path) != first
    before = launcher.digest_files([source], tmp_path)
    renamed = source.rename(tmp_path / "other.ts")
    assert launcher.digest_files([renamed], tmp_path) != before


def wait_for(
    client, path, *, process, predicate=lambda r: r.status_code == 200, seconds=35
):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("launcher exited before becoming ready")
        try:
            result = client.get(path)
            if predicate(result):
                return result
        except httpx.TransportError:
            pass
        time.sleep(0.15)
    raise AssertionError(f"timed out waiting for {path}")


@pytest.mark.skipif(
    not (ROOT / "runtime/launcher-build.json").is_file(),
    reason="run the launcher once to prepare dependencies/build for this local smoke test",
)
def test_real_launcher_login_upload_restart_and_cleanup(tmp_path, monkeypatch):
    # Reuse only code/dependencies/build. DB, originals, logs and locks are isolated in tmp_path.
    sandbox = tmp_path / "含空格 project"
    sandbox.mkdir()
    (sandbox / "runtime").mkdir()
    for name in ("backend", "frontend", ".venv"):
        (sandbox / name).symlink_to(ROOT / name, target_is_directory=True)
    shutil.copyfile(
        ROOT / "runtime/launcher-build.json", sandbox / "runtime/launcher-build.json"
    )
    url = f"sqlite:///{sandbox}/runtime/development.db"
    with monkeypatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    engine, factory = connect(url)
    manager = seed_admin(factory)
    engine.dispose()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    runner = f"import sys; sys.path.insert(0, {str(ROOT)!r}); from scripts import launch; from pathlib import Path; launch.ROOT = Path({str(sandbox)!r}); sys.exit(launch.main())"
    env = os.environ.copy()
    for key in ("DATABASE_URL", "ARCHIVE_DIR"):
        env.pop(key, None)
    process = None
    with (
        (tmp_path / "launcher-output.log").open("w+") as output,
        httpx.Client(
            base_url=origin, headers={"Origin": origin}, timeout=2, trust_env=False
        ) as client,
    ):
        try:
            for iteration in range(2):
                process = subprocess.Popen(
                    [
                        str(ROOT / ".venv/bin/python"),
                        "-c",
                        runner,
                        "--port",
                        str(port),
                        "--no-open",
                    ],
                    cwd=tmp_path,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                wait_for(client, "/api/health", process=process)
                assert client.get("/").status_code == 200
                login = client.post(
                    "/api/auth/login",
                    json={"email": "admin@test.invalid", "password": PASSWORD},
                )
                assert login.status_code == 200, login.text
                assert "httponly" in login.headers["set-cookie"].lower()
                assert "; secure" not in login.headers["set-cookie"].lower()
                permissions = client.get("/api/auth/me").json()["managers"][0][
                    "permissions"
                ]
                assert permissions["admin"] and permissions["write"]
                if iteration == 0:
                    created = client.post(
                        f"/api/managers/{manager}/products",
                        json={
                            "code": "LAUNCH-QA",
                            "name": "启动测试产品",
                            "shares": ["A"],
                        },
                    )
                    assert created.status_code == 201, created.text
                    content = "产品代码,份额类别,估值日期,单位净值\nLAUNCH-QA,A,2026-08-28,1.1234\n".encode()
                    uploaded = client.post(
                        f"/api/managers/{manager}/documents",
                        files={"file": ("test.csv", content, "text/csv")},
                    )
                    assert uploaded.status_code == 201, uploaded.text
                    doc = uploaded.json()
                    wait_for(
                        client,
                        f"/api/managers/{manager}/documents",
                        process=process,
                        predicate=lambda r: (
                            r.status_code == 200
                            and r.json()[0]["job"]["status"] == "completed"
                        ),
                    )
                else:
                    assert (
                        len(client.get(f"/api/managers/{manager}/products").json()) == 1
                    )
                    assert (
                        client.get(f"/api/documents/{doc['id']}/download").content
                        == content
                    )
                # Includes one normal Ctrl+C and one terminal-closed SIGHUP path.
                process.send_signal(signal.SIGINT if iteration == 0 else signal.SIGHUP)
                assert process.wait(timeout=20) == 0
                with socket.socket() as probe:
                    assert probe.connect_ex(("127.0.0.1", port)) != 0
            output.seek(0)
            text = output.read()
            assert "前端未变化" in text and "已初始化" in text
            assert PASSWORD not in text
        finally:
            if process and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=20)
