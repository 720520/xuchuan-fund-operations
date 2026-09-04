"""Print bounded sample rows for one archived workbook per custodian domain."""

import io
import json
import re
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path

from app.parsing import extract_tables


def sender_domain(metadata):
    sender = json.loads(metadata or "{}").get("from", "")
    match = re.search(r"@([A-Za-z0-9.-]+)", sender)
    return match.group(1).lower() if match else "unknown"


def workbook_members(filename, content):
    if not filename.lower().endswith(".zip"):
        yield filename, content
        return
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for member in archive.infolist():
            if not member.is_dir() and Path(member.filename).suffix.lower() in {".xls", ".xlsx"}:
                yield Path(member.filename).name, archive.read(member)


def main():
    connection = sqlite3.connect("runtime/development.db")
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT attachment.filename, attachment.storage_key, parent.metadata_json
        FROM documents attachment
        JOIN documents parent ON parent.id = attachment.parent_id
        WHERE attachment.source = 'email' AND attachment.parent_id IS NOT NULL
        ORDER BY attachment.received_at
        """
    ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[sender_domain(row["metadata_json"])].append(row)
    for domain in ["citics.com", "htsc.com", "ebscn.com", "cmschina.com.cn", "swhysc.com"]:
        print(f"\n### {domain}")
        shown = 0
        for row in grouped[domain]:
            if domain == "citics.com" and "产品成立日" in row["filename"]:
                continue
            content = (Path("runtime/archive") / row["storage_key"]).read_bytes()
            for filename, member_content in workbook_members(row["filename"], content):
                print(f"FILE {filename}")
                for sheet, sheet_rows in extract_tables(filename, member_content):
                    print(f"SHEET {sheet}")
                    for index, values in enumerate(sheet_rows[:25], 1):
                        compact = [value for value in values[:16]]
                        if any(value not in (None, "") for value in compact):
                            print(index, compact)
                shown += 1
                if shown >= 2:
                    break
            if shown >= 2:
                break


if __name__ == "__main__":
    main()
