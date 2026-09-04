"""Read-only IMAP size check for specific message UIDs."""

import argparse

from app.config import Settings
from app.db import connect
from app.mailbox_security import open_imap, stored_config
from app.models import Mailbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mailbox_id")
    parser.add_argument("uids", nargs="+", type=int)
    args = parser.parse_args()
    settings = Settings()
    engine, factory = connect(settings.database_url)
    with factory() as db:
        mailbox = db.get(Mailbox, args.mailbox_id)
        config = stored_config(settings, mailbox)
        with open_imap(config) as client:
            client.select_folder(config.get("folder") or "INBOX", readonly=True)
            for uid in args.uids:
                details = client.fetch([uid], ["RFC822.SIZE"])[uid]
                print(f"{uid}: {details[b'RFC822.SIZE']} bytes")
    engine.dispose()


if __name__ == "__main__":
    main()
