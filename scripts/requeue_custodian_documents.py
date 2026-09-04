"""Bulk requeue archived attachments for the verified custodian adapters."""

import argparse
import re

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.config import Settings
from app.custodian_parsers import KNOWN_DOMAINS
from app.db import connect, now
from app.models import Document, ParseJob


def sender_domain(metadata):
    match = re.search(r"@([A-Za-z0-9.-]+)", (metadata or {}).get("from", ""))
    return match.group(1).lower() if match else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually set matching review jobs to queued; omission is a dry run.",
    )
    args = parser.parse_args()
    settings = Settings()
    engine, factory = connect(settings.database_url)
    parent = aliased(Document)
    with factory.begin() as db:
        rows = db.execute(
            select(ParseJob, parent.metadata_json)
            .join(Document, Document.id == ParseJob.document_id)
            .join(parent, parent.id == Document.parent_id)
            .where(ParseJob.status == "review")
        ).all()
        jobs = [job for job, metadata in rows if sender_domain(metadata) in KNOWN_DOMAINS]
        missing_rows = db.execute(
            select(Document, parent.metadata_json)
            .join(parent, parent.id == Document.parent_id)
            .outerjoin(ParseJob, ParseJob.document_id == Document.id)
            .where(ParseJob.id.is_(None), Document.parent_id.is_not(None))
        ).all()
        missing = [
            document
            for document, metadata in missing_rows
            if sender_domain(metadata) in KNOWN_DOMAINS
        ]
        if args.apply:
            for job in jobs:
                job.status = "queued"
                job.updated_at = now()
            for document in missing:
                db.add(
                    ParseJob(
                        manager_id=document.manager_id,
                        document_id=document.id,
                        status="queued",
                        updated_at=now(),
                    )
                )
    engine.dispose()
    action = "已批量排队" if args.apply else "预览可批量排队"
    print(
        f"{action}：{len(jobs)} 个旧任务；"
        f"新增遗漏附件任务：{len(missing) if args.apply else 0} 个"
    )


if __name__ == "__main__":
    main()
