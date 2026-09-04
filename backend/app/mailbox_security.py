"""Encrypted mailbox credentials and verified IMAP connections."""

import json
import os
import ssl
import stat
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from imapclient import IMAPClient


def _fernet(settings, *, create=False):
    configured = os.getenv("MAIL_ENCRYPTION_KEY")
    if configured:
        try:
            return Fernet(configured.encode())
        except ValueError as exc:
            raise ValueError("MAIL_ENCRYPTION_KEY 不是有效的 Fernet 密钥") from exc
    path: Path = settings.mail_key_file
    if path.exists():
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
        ):
            raise ValueError(
                "邮箱加密密钥必须由当前用户持有、权限为 600，且不能是符号链接"
            )
        return Fernet(path.read_bytes().strip())
    if not create:
        raise ValueError("邮箱加密密钥不存在，无法读取已保存授权码")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_info = path.parent.stat()
    if parent_info.st_uid != os.getuid() or parent_info.st_mode & 0o077:
        raise ValueError("邮箱密钥目录必须由当前用户持有且权限为 700")
    key = Fernet.generate_key()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _fernet(settings)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key)
        stream.flush()
        os.fsync(stream.fileno())
    return Fernet(key)


def encrypt_password(settings, mailbox_id, password):
    payload = json.dumps(
        {"mailbox_id": mailbox_id, "password": password}, separators=(",", ":")
    ).encode()
    return _fernet(settings, create=True).encrypt(payload).decode()


def decrypt_password(settings, mailbox):
    if not mailbox.credential_ciphertext:
        return None
    try:
        payload = json.loads(
            _fernet(settings).decrypt(mailbox.credential_ciphertext.encode()).decode()
        )
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("邮箱授权码无法解密，请由管理员重新填写") from exc
    if payload.get("mailbox_id") != mailbox.id or not payload.get("password"):
        raise ValueError("邮箱授权码与配置不匹配，请由管理员重新填写")
    return payload["password"]


def stored_config(settings, mailbox, password=None):
    if mailbox.host and mailbox.username:
        secret = (
            password if password is not None else decrypt_password(settings, mailbox)
        )
        return {
            "host": mailbox.host,
            "port": mailbox.port,
            "tls": mailbox.tls,
            "username": mailbox.username,
            "password": secret,
            "send_id": mailbox.send_id,
        }
    prefix = mailbox.env_prefix
    secret = os.getenv(prefix + "_PASSWORD")
    return {
        "host": os.getenv(prefix + "_HOST"),
        "port": int(os.getenv(prefix + "_PORT", "993")),
        "tls": os.getenv(prefix + "_TLS", "ssl"),
        "username": os.getenv(prefix + "_USER"),
        "password": secret,
        "oauth_token": os.getenv(prefix + "_OAUTH_TOKEN"),
        "send_id": os.getenv(prefix + "_SEND_ID", "false").lower() == "true",
        "folder": os.getenv(prefix + "_FOLDER", "INBOX"),
    }


@contextmanager
def open_imap(config, client_type=IMAPClient):
    if (
        not config.get("host")
        or not config.get("username")
        or not (config.get("password") or config.get("oauth_token"))
    ):
        raise ValueError("邮箱服务器、账号或授权码未配置")
    mode = config.get("tls", "ssl")
    if mode not in {"ssl", "starttls"}:
        raise ValueError("只允许 SSL 或 STARTTLS 加密连接")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with client_type(
        config["host"],
        port=int(config["port"]),
        ssl=mode == "ssl",
        ssl_context=context,
        timeout=45,
    ) as client:
        if mode == "starttls":
            client.starttls(context)
        if config.get("oauth_token"):
            client.oauth2_login(config["username"], config["oauth_token"])
        else:
            client.login(config["username"], config["password"])
        if config.get("send_id"):
            client.id_(
                {"name": "Xuchuan", "version": "0.1", "vendor": "Internal Operations"}
            )
        yield client


def selectable_folders(client):
    folders = []
    for flags, _, folder in client.list_folders():
        normalized = [
            flag.decode(errors="replace") if isinstance(flag, bytes) else flag
            for flag in flags
        ]
        if "\\noselect" not in {flag.lower() for flag in normalized}:
            folders.append(folder)
    return folders


def test_connection(config, client_type=IMAPClient):
    with open_imap(config, client_type) as client:
        folders = selectable_folders(client)
        if not folders:
            raise ValueError("服务器没有返回可读取的邮件文件夹")
        client.select_folder(
            "INBOX" if "INBOX" in folders else folders[0], readonly=True
        )
        return folders
