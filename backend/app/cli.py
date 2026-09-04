"""Local deployment administrator operations; never an unauthenticated setup API."""

import argparse
import getpass
import re
import sys
import warnings

from sqlalchemy import delete, select

from .config import Settings
from .db import connect
from .models import Group, Mailbox, Manager, Membership, Session, User
from .security import ROLES, audit, password_hash


def ask_text(label, *, default="", email=False, max_length=120):
    while True:
        value = (
            input(f"{label}{f' [{default}]' if default else ''}：").strip() or default
        )
        limit = 254 if email else max_length
        if not value or len(value) > limit or not value.isprintable():
            print(f"请填写有效内容，不超过 {limit} 字。")
            continue
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            print("请填写完整的登录邮箱，例如 admin@example.com。")
            continue
        return value.lower() if email else value


def ask_yes(label):
    while True:
        answer = input(f"{label} [y/N]：").strip().lower()
        if answer in {"", "n", "no", "否"}:
            return False
        if answer in {"y", "yes", "是"}:
            return True
        print("请输入 y（是）或 n（否）；直接回车表示否。")


def ask_password():
    # Never fall back to echoing a password when no controlling terminal is available.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        while True:
            password = getpass.getpass("设置密码（12–128 位，输入时不显示）：")
            if not 12 <= len(password) <= 128:
                print("密码长度须为 12–128 位，请重新设置。")
                continue
            if password != getpass.getpass("再次输入密码："):
                print("两次密码不一致，请重新设置。")
                continue
            return password_hash(password)


def create_initial_admin(db, *, group, manager, email, name, roles, download, encoded):
    if db.scalar(select(User.id).limit(1)):
        raise ValueError("系统已初始化，不能覆盖已有账号。")
    organization = Group(name=group)
    db.add(organization)
    db.flush()
    license = Manager(group_id=organization.id, name=manager)
    db.add(license)
    db.flush()
    user = User(email=email.strip().lower(), name=name, password_hash=encoded)
    db.add(user)
    db.flush()
    db.add(
        Membership(
            user_id=user.id, manager_id=license.id, roles=roles, can_download=download
        )
    )
    audit(db, user, license.id, "system.bootstrapped", user.id, {"roles": roles})
    return license.id


def setup(db):
    if db.scalar(select(User.id).limit(1)):
        admins = sorted(
            {
                user.email
                for user, member in db.execute(
                    select(User, Membership)
                    .join(Membership, Membership.user_id == User.id)
                    .where(User.active.is_(True))
                )
                if "admin" in member.roles
            }
        )
        if not admins:
            raise ValueError(
                "已有账号，但没有可用管理员；请由部署人员检查账号及牌照授权，不能重新初始化。"
            )
        print("已初始化，保留全部账号、密码及业务数据。")
        print("管理员登录邮箱：" + "、".join(admins))
        return
    if not sys.stdin.isatty():
        raise ValueError(
            "首次运行需要在终端设置管理员。请在终端运行 ./一键启动.sh；不要将密码发送到聊天。"
        )
    print("\n首次使用：创建你的机构和管理员，不生成演示产品。")
    group = ask_text("集团名称（无集团可填公司名称）")
    manager = ask_text("管理人主体 / 牌照名称", default=group)
    name = ask_text("管理员姓名", default="管理员", max_length=80)
    email = ask_text("管理员登录邮箱", email=True)
    print(
        "管理员负责组织与权限；运营操作、资料下载是另外两项权限，可以日后在界面调整。"
    )
    operator = ask_yes("该管理员是否也负责创建产品、上传材料、补录及确认净值？")
    download = ask_yes("是否允许该管理员下载归档资料？")
    roles = ["admin", "operator"] if operator else ["admin"]
    encoded = ask_password()
    create_initial_admin(
        db,
        group=group,
        manager=manager,
        email=email,
        name=name,
        roles=roles,
        download=download,
        encoded=encoded,
    )
    print(f"管理员已创建：{email}。请使用刚设置的密码登录；密码不会保存为明文。")


def main():
    parser = argparse.ArgumentParser(description="序川部署管理员工具")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="首次交互设置管理员；已有账号时只显示登录提示")
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--group", required=True)
    bootstrap.add_argument("--manager", required=True)
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument(
        "--roles", default="admin", help="逗号分隔；需要运营权限时显式包含 operator"
    )
    bootstrap.add_argument("--download", action="store_true")
    commands.add_parser("list-managers")
    add_manager = commands.add_parser("add-manager")
    add_manager.add_argument("--group-id", required=True)
    add_manager.add_argument("--name", required=True)
    reset = commands.add_parser("reset-password")
    reset.add_argument("--email", required=True)
    link = commands.add_parser("link-member")
    link.add_argument("--email", required=True)
    link.add_argument("--manager-id", required=True)
    link.add_argument("--roles", required=True)
    link.add_argument("--download", action="store_true")
    enable = commands.add_parser("enable-mailbox")
    enable.add_argument("--id", required=True)
    enable.add_argument("--confirm-scope", action="store_true", required=True)
    disable = commands.add_parser("disable-mailbox")
    disable.add_argument("--id", required=True)
    args = parser.parse_args()
    _, factory = connect(Settings().database_url)
    with factory.begin() as db:
        if args.command == "setup":
            try:
                setup(db)
            except (ValueError, getpass.GetPassWarning) as exc:
                parser.error(str(exc))
            except (EOFError, KeyboardInterrupt):
                raise SystemExit("\n设置已取消，未创建管理员。")
            return
        if args.command == "list-managers":
            for m in db.scalars(select(Manager)):
                print(f"{m.id}  {m.name}  group={m.group_id}")
            return
        if args.command == "add-manager":
            if not db.get(Group, args.group_id):
                parser.error("集团不存在")
            manager = Manager(group_id=args.group_id, name=args.name)
            db.add(manager)
            db.flush()
            audit(
                db,
                None,
                manager.id,
                "manager.created",
                manager.id,
                {"via": "deployment_cli"},
            )
            print(f"牌照已创建：{manager.id}。请用 link-member 关联管理员及运营账号。")
            return
        if args.command in {"enable-mailbox", "disable-mailbox"}:
            box = db.get(Mailbox, args.id)
            if not box:
                parser.error("邮箱不存在")
            box.enabled = args.command == "enable-mailbox"
            audit(
                db,
                None,
                box.manager_id,
                "mailbox.enabled" if box.enabled else "mailbox.disabled",
                box.id,
                {"via": "deployment_cli", "since": box.since},
            )
            print("邮箱状态已更新；下一次显式启用 --mail 的 worker 将按此范围同步。")
            return
        if args.command in {"bootstrap", "link-member"}:
            roles = args.roles.split(",")
            if not set(roles) <= ROLES:
                parser.error("未知角色")
        target = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if args.command == "bootstrap":
            if db.scalar(select(User.id).limit(1)):
                parser.error("已初始化，禁止重复 bootstrap；请通过管理员界面建立用户")
            if "admin" not in roles:
                parser.error("初始账号必须包含 admin")
            manager_id = create_initial_admin(
                db,
                group=args.group,
                manager=args.manager,
                email=args.email,
                name=args.name,
                roles=roles,
                download=args.download,
                encoded=ask_password(),
            )
            print(f"初始化完成。管理人 ID：{manager_id}。未创建任何示例业务数据。")
        elif args.command == "reset-password":
            if not target:
                parser.error("用户不存在")
            target.password_hash = ask_password()
            db.execute(delete(Session).where(Session.user_id == target.id))
            for m in db.scalars(
                select(Membership).where(Membership.user_id == target.id)
            ):
                audit(
                    db,
                    None,
                    m.manager_id,
                    "user.password_reset",
                    target.id,
                    {"via": "deployment_cli"},
                )
            print("密码已重置，所有会话已失效。")
        elif args.command == "link-member":
            if not target or not db.get(Manager, args.manager_id):
                parser.error("用户或牌照不存在")
            if db.scalar(
                select(Membership.id).where(
                    Membership.user_id == target.id,
                    Membership.manager_id == args.manager_id,
                )
            ):
                parser.error("已关联；请由该牌照管理员在界面调整权限")
            db.add(
                Membership(
                    user_id=target.id,
                    manager_id=args.manager_id,
                    roles=roles,
                    can_download=args.download,
                )
            )
            audit(
                db,
                None,
                args.manager_id,
                "membership.linked",
                target.id,
                {"via": "deployment_cli", "roles": roles},
            )
            print("账号已关联该牌照，原密码与其他牌照权限均未修改。")


if __name__ == "__main__":
    main()
