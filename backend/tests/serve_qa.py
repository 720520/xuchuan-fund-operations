"""Disposable browser-test server. No production DB and no live IMAP access.

Run explicitly from repository root. A fresh UUID directory is created each time.
Account qa@example.invalid / local-ui-test-only-2026 is only for this loopback server.
"""

import argparse
import re
import threading
from pathlib import Path
from uuid import uuid4

import uvicorn
from app.config import Settings
from app.db import Base
from app.immutability import install_guards
from app.main import create_app
from app.models import Group, Manager, Membership, User
from app.security import password_hash
from app.worker import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse", help="仅复用本脚本创建的 runtime/ui-qa-UUID 测试目录"
    )
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()
    directory = (
        Path(args.reuse).resolve()
        if args.reuse
        else Path("runtime") / ("ui-qa-" + uuid4().hex)
    )
    if args.reuse:
        if (
            directory.parent != Path("runtime").resolve()
            or not re.fullmatch(r"ui-qa-[a-f0-9]{32}", directory.name)
            or not (directory / "test.db").is_file()
        ):
            parser.error("只能复用已存在的独立页面测试目录")
    else:
        directory.mkdir(parents=True)
    settings = Settings(
        database_url=f"sqlite:///{directory}/test.db",
        storage=directory / "archive",
        cookie_secure=False,
        origins=(f"http://127.0.0.1:{args.port}",),
    )
    app = create_app(settings)
    if not args.reuse:
        Base.metadata.create_all(app.state.engine)
        with app.state.engine.begin() as c:
            install_guards(c)
        with app.state.factory.begin() as db:
            group = Group(name="界面联调集团（测试）")
            db.add(group)
            db.flush()
            manager = Manager(group_id=group.id, name="界面联调管理人（测试）")
            db.add(manager)
            db.flush()
            user = User(
                email="qa@example.invalid",
                name="试运行管理员",
                password_hash=password_hash("local-ui-test-only-2026"),
            )
            db.add(user)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id,
                    manager_id=manager.id,
                    roles=["admin", "operator"],
                    can_download=True,
                )
            )
    stop = threading.Event()

    def worker():
        while not stop.wait(3):
            run_once(app.state.factory, settings, mail=False)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    print(f"Disposable QA data: {directory}; no real data or mailboxes", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
