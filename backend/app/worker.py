import argparse
import logging
import signal
import threading
import time

from sqlalchemy import select

from .config import Settings
from .db import connect, now
from .mail_sync import sync_mailbox
from .models import Document, Mailbox, ParseJob
from .services import process_document, task

log = logging.getLogger("xuchuan.worker")


def parse_one(factory, settings):
    job_id = None
    try:
        with factory.begin() as db:
            job = db.scalar(
                select(ParseJob)
                .where(ParseJob.status == "queued")
                .order_by(ParseJob.updated_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return False
            job_id = job.id
            document = db.get(Document, job.document_id)
            process_document(db, settings, document)
        return True
    except Exception as exc:
        # The raw archive was committed before this transaction; processing can be retried.
        log.error("Parse failed: job=%s exception=%s", job_id, type(exc).__name__)
        if job_id:
            with factory.begin() as db:
                job = db.scalar(
                    select(ParseJob).where(ParseJob.id == job_id).with_for_update()
                )
                if job.status == "queued":
                    job.status, job.updated_at = "review", now()
                    job.result = {
                        "errors": [
                            {"reason": "解析事务失败，原件仍保留；请联系管理员或重试"}
                        ]
                    }
                    task(
                        db,
                        job.manager_id,
                        "parse",
                        f"parse:{job.document_id}",
                        {
                            "document_id": job.document_id,
                            "job_id": job.id,
                            **job.result,
                        },
                    )
        return bool(job_id)


def run_once(factory, settings, mail=False):
    parsed = 0
    if mail:
        with factory() as db:
            boxes = list(
                db.scalars(select(Mailbox.id).where(Mailbox.enabled.is_(True)))
            )
        for box_id in boxes:
            try:
                sync_mailbox(factory, settings, box_id)
            except Exception as exc:
                log.error(
                    "Mail sync failed: mailbox=%s exception=%s",
                    box_id,
                    type(exc).__name__,
                )
                with factory.begin() as db:
                    box = db.get(Mailbox, box_id)
                    box.error = f"同步失败（{type(exc).__name__}），请检查配置、网络及文件大小；原邮箱未修改"
                    task(
                        db,
                        box.manager_id,
                        "mailbox",
                        f"mailbox:{box.id}",
                        {"mailbox_id": box.id, "error": box.error},
                    )
            else:
                from .models import ExceptionTask
                from .security import audit

                with factory.begin() as db:
                    issue = db.scalar(
                        select(ExceptionTask).where(
                            ExceptionTask.dedup_key == f"mailbox:{box_id}"
                        )
                    )
                    if issue and issue.status != "resolved":
                        issue.status, issue.resolution, issue.updated_at = (
                            "resolved",
                            {"via": "mail_sync_recovered"},
                            now(),
                        )
                        issue.revision += 1
                        audit(
                            db,
                            None,
                            issue.manager_id,
                            "exception.mail_recovered",
                            issue.id,
                        )
    for _ in range(100):
        if not parse_one(factory, settings):
            break
        parsed += 1
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--mail",
        action="store_true",
        help="Only explicitly enabled mailboxes will connect",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    _, factory = connect(settings.database_url)
    stop = threading.Event()
    next_mail = 0.0
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        sync_due = args.mail and time.monotonic() >= next_mail
        run_once(factory, settings, sync_due)
        if sync_due:
            next_mail = time.monotonic() + 60
        if args.once:
            break
        # Upload parsing stays responsive even when mailbox polling is less frequent.
        stop.wait(10)


if __name__ == "__main__":
    main()
