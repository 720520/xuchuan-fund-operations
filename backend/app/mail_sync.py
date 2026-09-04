"""Read-only IMAP ingestion. Never STORE, EXPUNGE, MOVE, DELETE or change flags."""

import hashlib
from datetime import date, datetime, timezone
from email import policy
from email.parser import BytesParser

from sqlalchemy import select

from .db import now
from .mailbox_security import open_imap, selectable_folders, stored_config
from .models import Document, ExceptionTask, Mailbox, MailReceipt, ParseJob
from .security import audit
from .services import archive, task


def ingest_message(
    db, settings, mailbox, validity, message_uid, raw, received_at=None, folder="INBOX"
):
    existing = db.scalar(
        select(MailReceipt).where(
            MailReceipt.mailbox_id == mailbox.id,
            MailReceipt.folder == folder,
            MailReceipt.uid_validity == str(validity),
            MailReceipt.message_uid == str(message_uid),
        )
    )
    if existing:
        return existing.document_id
    sha = hashlib.sha256(raw).hexdigest()
    # UIDVALIDITY can change. Identical originals are not reimported as NAV candidates.
    original = db.scalar(
        select(Document).where(
            Document.manager_id == mailbox.manager_id,
            Document.source == "email",
            Document.sha256 == sha,
            Document.media_type == "message/rfc822",
        )
    )
    if not original:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        original = archive(
            db,
            settings,
            mailbox.manager_id,
            f"{message_uid}.eml",
            raw,
            "email",
            received_at=received_at,
            metadata={
                "subject": str(msg.get("Subject", ""))[:500],
                "from": str(msg.get("From", ""))[:500],
                "message_id": str(msg.get("Message-ID", ""))[:500],
                "mailbox_id": mailbox.id,
                "folder": folder,
            },
        )
        for index, part in enumerate(msg.walk()):
            if part.is_multipart():
                continue
            filename = part.get_filename()
            if not filename and part.get_content_disposition() != "attachment":
                continue
            body = part.get_payload(decode=True)
            if not body:
                continue
            child = archive(
                db,
                settings,
                mailbox.manager_id,
                filename or f"attachment-{index}.bin",
                body,
                "email",
                parent_id=original.id,
                received_at=received_at,
                metadata={
                    "mime_index": index,
                    "mailbox_id": mailbox.id,
                    "folder": folder,
                },
            )
            if child.filename.lower().endswith(
                (".xlsx", ".xls", ".csv", ".pdf", ".xlsm")
            ):
                db.add(ParseJob(manager_id=mailbox.manager_id, document_id=child.id))
    db.add(
        MailReceipt(
            mailbox_id=mailbox.id,
            folder=folder,
            uid_validity=str(validity),
            message_uid=str(message_uid),
            document_id=original.id,
        )
    )
    db.flush()
    return original.id


def sync_mailbox(factory, settings, mailbox_id, client_type=None):
    # One mailbox lock prevents concurrent workers from importing the same UID.
    with factory.begin() as db:
        box = db.scalar(
            select(Mailbox)
            .where(Mailbox.id == mailbox_id, Mailbox.enabled.is_(True))
            .with_for_update(skip_locked=True)
        )
        if not box:
            return 0
        config = stored_config(settings, box)
        count = 0
        arguments = (config,) if client_type is None else (config, client_type)
        with open_imap(*arguments) as client:
            folders = (
                selectable_folders(client)
                if box.all_folders
                else [config.get("folder") or "INBOX"]
            )
            folders = sorted(folders, key=lambda name: (name.upper() != "INBOX", name))
            for folder in folders:
                if count >= 100:
                    break
                selected = client.select_folder(folder, readonly=True)
                validity = str(selected[b"UIDVALIDITY"])
                found = client.search(["SINCE", date.fromisoformat(box.since)])
                done = set(
                    db.scalars(
                        select(MailReceipt.message_uid).where(
                            MailReceipt.mailbox_id == box.id,
                            MailReceipt.folder == folder,
                            MailReceipt.uid_validity == validity,
                        )
                    )
                )
                pending = [uid for uid in found if str(uid) not in done][: 100 - count]
                for message_uid in pending:
                    folder_key = hashlib.sha256(folder.encode()).hexdigest()[:12]
                    issue_key = (
                        f"mail-message:{box.id}:{folder_key}:{validity}:{message_uid}"
                    )
                    try:
                        # A bad attachment must not roll back other successfully archived mail.
                        with db.begin_nested():
                            details = client.fetch(
                                [message_uid], ["RFC822.SIZE", "INTERNALDATE"]
                            )[message_uid]
                            if details[b"RFC822.SIZE"] > settings.max_upload:
                                raise ValueError("Message exceeds archive limit")
                            body = client.fetch([message_uid], ["BODY.PEEK[]"])[
                                message_uid
                            ][b"BODY[]"]
                            stamp = (
                                details.get(b"INTERNALDATE", datetime.now(timezone.utc))
                                .astimezone(timezone.utc)
                                .isoformat()
                            )
                            ingest_message(
                                db,
                                settings,
                                box,
                                validity,
                                message_uid,
                                body,
                                stamp,
                                folder,
                            )
                        count += 1
                        prior = db.scalar(
                            select(ExceptionTask).where(
                                ExceptionTask.manager_id == box.manager_id,
                                ExceptionTask.dedup_key == issue_key,
                            )
                        )
                        if prior and prior.status != "resolved":
                            prior.status, prior.updated_at, prior.revision = (
                                "resolved",
                                now(),
                                prior.revision + 1,
                            )
                            prior.resolution = {"via": "message_import_recovered"}
                            audit(
                                db,
                                None,
                                box.manager_id,
                                "exception.mail_message_recovered",
                                prior.id,
                            )
                    except Exception as exc:
                        task(
                            db,
                            box.manager_id,
                            "mailbox",
                            issue_key,
                            {
                                "mailbox_id": box.id,
                                "folder": folder,
                                "message_uid": str(message_uid),
                                "error": f"单封邮件归档失败（{type(exc).__name__}），请核查大小或格式；该 UID 未标记完成，下一轮重试，其他邮件继续。",
                            },
                        )
        box.last_sync, box.error = now(), None
        return count
