"""Local-only launcher. No default password, real mailbox access, or database reset."""

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]


class LaunchError(Exception):
    pass


def say(message):
    print(message, flush=True)


def run(command, *, root, env, cwd=None):
    try:
        subprocess.run(
            [str(arg) for arg in command], cwd=cwd or root, env=env, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LaunchError(
            "上一步未完成，已停止启动。请检查上方错误；原有账号和业务数据不会被清空。"
        ) from exc


def local_environment(root, port):
    env = os.environ.copy()
    # A convenience command must never migrate a production DB inherited from a shell.
    if env.get("DATABASE_URL") or env.get("ARCHIVE_DIR"):
        raise LaunchError(
            "检测到 DATABASE_URL 或 ARCHIVE_DIR。一键入口只管理本机开发数据；请在未设置这两项变量的新终端运行，正式部署使用 README 中的部署流程。"
        )
    env.update(
        DATABASE_URL="sqlite:///./runtime/development.db",
        ARCHIVE_DIR="./runtime/archive",
        COOKIE_SECURE="false",
        ALLOWED_ORIGINS=f"http://127.0.0.1:{port},http://localhost:{port}",
        PYTHONPATH=str(root / "backend"),
        PYTHONUNBUFFERED="1",
    )
    return env


@contextmanager
def launch_lock(runtime, url):
    # Never unlink a flock file: doing so could allow two lock holders on different inodes.
    with (runtime / "launcher.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            address = handle.read().strip()
            raise LaunchError(
                f"另一个启动窗口正在运行或准备启动。请使用原窗口，不要重复启动。\n该窗口地址：{address or '正在准备'}"
            )
        handle.seek(0)
        handle.truncate()
        handle.write(url)
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def check_port(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # Match Uvicorn: an immediately restarted server may have TIME_WAIT connections.
            # This does not allow sharing a port with an active listener (no SO_REUSEPORT).
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EPERM}:
            raise LaunchError(
                "当前运行环境不允许监听本机端口。请在本机终端运行，或检查沙箱 / 系统权限。"
            ) from exc
        raise LaunchError(
            f"本机 {port} 端口不可用，未停止任何已有服务。可改用：./一键启动.sh --port {port + 1 if port < 65535 else 8000}"
        ) from exc


def digest_files(paths, root):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def prepare_backend(root, env):
    python = root / ".venv/bin/python"
    uv = shutil.which("uv")
    if not python.is_file():
        if (root / ".venv").exists():
            raise LaunchError(
                "已有 .venv，但未找到可用 Python；请检查环境，不会自动删除该目录。"
            )
        say("准备 Python 运行环境（首次运行可能需要联网下载）……")
        if uv:
            run([uv, "venv", "--python", "3.12", ".venv"], root=root, env=env)
        else:
            candidate = shutil.which("python3.12") or sys.executable
            result = subprocess.run(
                [candidate, "-c", "import sys; sys.exit(sys.version_info < (3, 12))"],
                check=False,
            )
            if result.returncode:
                raise LaunchError(
                    "请先安装 Python 3.12+ 或 uv，再重新运行；尚未创建业务数据。"
                )
            run([candidate, "-m", "venv", ".venv"], root=root, env=env)
    check = subprocess.run(
        [str(python), "-c", "import sys; sys.exit(sys.version_info < (3, 12))"],
        check=False,
    )
    if check.returncode:
        raise LaunchError("现有 .venv 需要 Python 3.12+；不会自动覆盖或删除环境。")
    # Check the actual installed versions, not just an installation success marker.
    probe = """import importlib.metadata as m, pathlib, sys
try:
    requirements = pathlib.Path('backend/requirements.lock').read_text().splitlines()
    ready = all(m.version(name) == version for line in requirements
                if line.strip() and not line.startswith('#')
                for name, version in [line.strip().split('==', 1)])
except (m.PackageNotFoundError, ValueError):
    ready = False
sys.exit(0 if ready else 1)
"""
    result = subprocess.run([str(python), "-c", probe], cwd=root, env=env, check=False)
    if result.returncode:
        say("安装锁定版本的后端依赖……")
        command = (
            [uv, "pip", "install", "--python", python]
            if uv
            else [python, "-m", "pip", "install"]
        )
        run([*command, "-r", "backend/requirements.lock"], root=root, env=env)
    return python


def prepare_frontend(root, env):
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise LaunchError("未找到 Node.js / npm；请安装 Node.js 22.13+ 后重试。")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    if tuple(int(part) for part in version.lstrip("v").split(".")[:3]) < (22, 13, 0):
        raise LaunchError(f"当前 Node.js {version}，需要 22.13 或更新版本。")
    frontend = root / "frontend"
    marker = root / "runtime/launcher-build.json"
    try:
        state = json.loads(marker.read_text())
        if not isinstance(state, dict):
            state = {}
    except (FileNotFoundError, ValueError):
        state = {}
    dependencies = version + digest_files(
        [frontend / "package.json", frontend / "package-lock.json"], frontend
    )
    installed = state.get("dependencies") == dependencies and all(
        (frontend / f"node_modules/.bin/{tool}").is_file() for tool in ("vite", "tsc")
    )
    if not installed:
        say("安装锁定版本的前端依赖（首次运行需要联网）……")
        run([npm, "ci", "--no-fund", "--no-audit"], root=root, env=env, cwd=frontend)
    sources = [
        path
        for path in frontend.iterdir()
        if path.is_file()
        and path.suffix in {".json", ".ts", ".js", ".mjs", ".cjs", ".html", ".css"}
    ]
    for directory in ("src", "public"):
        sources.extend(
            path for path in (frontend / directory).rglob("*") if path.is_file()
        )
    build = dependencies + digest_files(sources, frontend)
    if (
        not installed
        or state.get("build") != build
        or not (frontend / "dist/index.html").is_file()
    ):
        say("构建正式页面……")
        run([npm, "run", "build"], root=root, env=env, cwd=frontend)
        marker.write_text(json.dumps({"dependencies": dependencies, "build": build}))
    else:
        say("前端未变化，使用已有构建。")
    return hashlib.sha256(build.encode()).hexdigest()[:12]


def stop_children(children):
    # Only signal children created by this run; no pkill, port-based kills, or stale PID files.
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 12
    for child in children:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def serve(root, python, env, port, *, open_browser, build_token):
    url = f"http://127.0.0.1:{port}"
    browser_url = f"{url}/?build={build_token}"
    logs = root / "runtime/logs"
    logs.mkdir(parents=True, exist_ok=True)
    children = []
    opener = build_opener(
        ProxyHandler({})
    )  # Local readiness must not go through a proxy.
    try:
        with (
            (logs / "api.log").open("ab") as api_log,
            (logs / "worker.log").open("ab") as worker_log,
        ):
            for command, output in [
                (
                    [
                        python,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    api_log,
                ),
                # Mail sync runs only for mailboxes an administrator explicitly enabled.
                ([python, "-m", "app.worker", "--mail"], worker_log),
            ]:
                children.append(
                    subprocess.Popen(
                        [str(arg) for arg in command],
                        cwd=root,
                        env=env,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                )
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if any(child.poll() is not None for child in children):
                    raise LaunchError(f"服务启动失败，请查看 {logs} 中的日志。")
                try:
                    with opener.open(url + "/api/health", timeout=1) as response:
                        if json.load(response).get("status") == "ok":
                            break
                except (URLError, TimeoutError, OSError, ValueError):
                    pass
                time.sleep(0.25)
            else:
                raise LaunchError(f"等待服务就绪超时，请查看 {logs} 中的日志。")
            say(
                f"\n序川已启动：{url}\n使用刚设置的管理员邮箱和密码登录；管理入口在“组织与权限”。\n上传附件将自动排队解析；管理员在网页中启用的邮箱会进行后台只读同步。\n保留此窗口，按 Ctrl+C 停止；再次启动仍保留账号与数据。\n日志：{logs}\n"
            )
            if open_browser:
                try:
                    opened = webbrowser.open(browser_url, new=2)
                except (webbrowser.Error, OSError):
                    opened = False
                if not opened:
                    say("未能自动打开浏览器，请手动打开上方地址。")
            while True:
                if any(child.poll() is not None for child in children):
                    raise LaunchError(
                        f"有服务意外退出，已停止本次启动的其他服务。请查看 {logs} 中的日志后重启。"
                    )
                time.sleep(0.5)
    finally:
        stop_children(children)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="序川一键启动（Linux / macOS 本机开发试用，不用于多人生产部署）"
    )
    parser.add_argument("--port", type=int, default=8000, help="本机端口，默认 8000")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument(
        "--reset-password",
        metavar="EMAIL",
        help="重置本机账号密码，不启动服务；需先停止启动窗口",
    )
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("端口应在 1024–65535 之间")
    os.umask(0o077)
    previous = {}
    try:
        env = local_environment(ROOT, args.port)
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)

        def interrupted(*_):
            raise KeyboardInterrupt

        for sig in (signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, interrupted)
        with launch_lock(runtime, f"http://127.0.0.1:{args.port}"):
            say(
                "序川 · 本机开发启动\n数据位置：runtime/development.db 和 runtime/archive/\n这是本机试用入口；正式多人使用请部署 PostgreSQL 与内网 HTTPS。"
            )
            if args.reset_password:
                if not (runtime / "development.db").is_file():
                    raise LaunchError(
                        "本机尚未初始化。请先运行 ./一键启动.sh 创建管理员。"
                    )
                python = prepare_backend(ROOT, env)
                run(
                    [
                        python,
                        "-m",
                        "app.cli",
                        "reset-password",
                        "--email",
                        args.reset_password,
                    ],
                    root=ROOT,
                    env=env,
                )
                return 0
            check_port(args.port)
            python = prepare_backend(ROOT, env)
            build_token = prepare_frontend(ROOT, env)
            say("检查数据库结构（只执行版本迁移，不清空数据）……")
            run(
                [
                    python,
                    "-m",
                    "alembic",
                    "-c",
                    "backend/alembic.ini",
                    "upgrade",
                    "head",
                ],
                root=ROOT,
                env=env,
            )
            run([python, "-m", "app.cli", "setup"], root=ROOT, env=env)
            serve(
                ROOT,
                python,
                env,
                args.port,
                open_browser=not args.no_open,
                build_token=build_token,
            )
        return 0
    except KeyboardInterrupt:
        say("\n已停止本次启动。账号、业务数据和归档资料均保留。")
        return 0
    except (LaunchError, OSError, subprocess.SubprocessError) as exc:
        say(f"\n无法继续：{exc}")
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
