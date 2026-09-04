"""Read-only replay of parser adapters against archived email attachments."""

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from app.parsing import parse


def sender_context(metadata):
    metadata = json.loads(metadata or "{}")
    sender = metadata.get("from", "")
    match = re.search(r"@([A-Za-z0-9.-]+)", sender)
    return {
        "sender": sender,
        "sender_domain": match.group(1).lower() if match else "unknown",
        "subject": metadata.get("subject", ""),
        "source": "email",
    }


def main():
    options = argparse.ArgumentParser()
    options.add_argument("--database", default="runtime/development.db")
    options.add_argument("--storage", type=Path, default=Path("runtime/archive"))
    options.add_argument("--max-rows", type=int, default=10000)
    args = options.parse_args()
    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    attachments = connection.execute(
        """
        SELECT attachment.filename, attachment.storage_key, parent.metadata_json
        FROM documents attachment
        JOIN documents parent ON parent.id = attachment.parent_id
        WHERE attachment.source = 'email'
        ORDER BY attachment.received_at
        """
    ).fetchall()
    summaries = defaultdict(Counter)
    reasons = defaultdict(Counter)
    for attachment in attachments:
        context = sender_context(attachment["metadata_json"])
        domain = context["sender_domain"]
        content = (args.storage / attachment["storage_key"]).read_bytes()
        try:
            result = parse(
                attachment["filename"], content, args.max_rows, context=context
            )
        except ValueError as exc:
            summaries[domain]["exceptions"] += 1
            reasons[domain][str(exc)] += 1
            continue
        summaries[domain]["files"] += 1
        summaries[domain]["records"] += len(result["records"])
        summaries[domain]["errors"] += len(result["errors"])
        summaries[domain][result["parser_version"]] += 1
        for error in result["errors"]:
            reasons[domain][error.get("reason", "unknown")] += 1
    for domain in sorted(summaries):
        print(domain, dict(summaries[domain]))
        for reason, count in reasons[domain].most_common(5):
            print(f"  {count} × {reason}")


if __name__ == "__main__":
    main()
