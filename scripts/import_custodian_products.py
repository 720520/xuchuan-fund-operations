"""Build a verified product/share inventory from custodian attachments."""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.config import Settings
from app.custodian_parsers import KNOWN_DOMAINS
from app.db import connect
from app.models import Document, Membership, Product, ShareClass, User
from app.parsing import parse
from app.security import audit


def mail_context(metadata):
    sender = (metadata or {}).get("from", "")
    match = re.search(r"@([A-Za-z0-9.-]+)", sender)
    return {
        "sender": sender,
        "sender_domain": match.group(1).lower() if match else "",
        "subject": (metadata or {}).get("subject", ""),
        "source": "email",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine, factory = connect(settings.database_url)
    parent = aliased(Document)
    inventory = defaultdict(lambda: {"names": Counter(), "shares": set(), "dates": set()})
    with factory() as db:
        rows = db.execute(
            select(Document, parent.metadata_json)
            .join(parent, parent.id == Document.parent_id)
            .where(Document.parent_id.is_not(None))
            .order_by(Document.received_at)
        ).all()
        for document, metadata in rows:
            context = mail_context(metadata)
            if context["sender_domain"] not in KNOWN_DOMAINS:
                continue
            result = parse(
                document.filename,
                (settings.storage / document.storage_key).read_bytes(),
                settings.max_rows,
                context=context,
            )
            for item in result["records"]:
                code = item.get("product_code")
                if not code:
                    continue
                entry = inventory[(document.manager_id, code)]
                entry["names"][item.get("product_name") or code] += 1
                entry["shares"].add(item.get("share_class") or "总")
                entry["dates"].add(item["valuation_date"])
    # Some custodians use an internal tier code in daily files but publish the
    # association filing code in another verified template. Merge only when the
    # exact product name has one unambiguous S-prefixed master code.
    by_name = defaultdict(list)
    for (manager_id, code), entry in inventory.items():
        if len(entry["names"]) == 1:
            by_name[(manager_id, next(iter(entry["names"])))].append(code)
    for (manager_id, _), codes in by_name.items():
        master_codes = [code for code in codes if code.startswith("S")]
        if len(codes) <= 1 or len(master_codes) != 1:
            continue
        master_key = (manager_id, master_codes[0])
        for code in list(codes):
            alias_key = (manager_id, code)
            if alias_key == master_key:
                continue
            inventory[master_key]["names"].update(inventory[alias_key]["names"])
            inventory[master_key]["shares"].update(inventory[alias_key]["shares"])
            inventory[master_key]["dates"].update(inventory[alias_key]["dates"])
            del inventory[alias_key]
    ambiguous = {
        key: value
        for key, value in inventory.items()
        if len(value["names"]) > 1
    }
    print(f"识别产品：{len(inventory)} 个；名称冲突：{len(ambiguous)} 个")
    for (_, code), entry in sorted(ambiguous.items()):
        print(f"  {code}: {dict(entry['names'])}")
    if ambiguous:
        print("存在名称冲突，未写入产品；请先核验以上代码。")
        engine.dispose()
        raise SystemExit(2)
    if not args.apply:
        for (_, code), entry in sorted(inventory.items()):
            print(
                f"  {code} | {entry['names'].most_common(1)[0][0]} | "
                f"{','.join(sorted(entry['shares']))} | 最新 {max(entry['dates'])}"
            )
        print("当前为预览；加 --apply 后写入产品及份额台账。")
        engine.dispose()
        return
    created = shares_created = 0
    active_after = (date.today() - timedelta(days=14)).isoformat()
    with factory.begin() as db:
        actors = {}
        for manager_id, _ in inventory:
            actor = next(
                (
                    user
                    for user, membership in db.execute(
                        select(User, Membership)
                        .join(Membership, Membership.user_id == User.id)
                        .where(Membership.manager_id == manager_id)
                    )
                    if "admin" in (membership.roles or [])
                ),
                None,
            )
            actors[manager_id] = actor
        for (manager_id, code), entry in sorted(inventory.items()):
            name = entry["names"].most_common(1)[0][0]
            product = db.scalar(
                select(Product).where(
                    Product.manager_id == manager_id, Product.code == code
                )
            )
            if not product:
                product = Product(
                    manager_id=manager_id,
                    code=code,
                    name=name,
                    currency="CNY",
                    strategy="",
                    expected=max(entry["dates"]) >= active_after,
                )
                db.add(product)
                db.flush()
                created += 1
                audit(
                    db,
                    actors[manager_id],
                    manager_id,
                    "product.confirmed_from_custodian_inventory",
                    product.id,
                    {
                        "code": code,
                        "name": name,
                        "shares": sorted(entry["shares"]),
                        "latest_valuation_date": max(entry["dates"]),
                    },
                )
            existing = set(
                db.scalars(
                    select(ShareClass.name).where(ShareClass.product_id == product.id)
                )
            )
            for share_name in sorted(entry["shares"] - existing):
                share = ShareClass(
                    manager_id=manager_id, product_id=product.id, name=share_name
                )
                db.add(share)
                db.flush()
                shares_created += 1
                audit(
                    db,
                    actors[manager_id],
                    manager_id,
                    "share.confirmed_from_custodian_inventory",
                    share.id,
                    {"product_id": product.id, "name": share_name},
                )
    engine.dispose()
    print(f"已写入产品：{created} 个；新增份额：{shares_created} 个")


if __name__ == "__main__":
    main()
