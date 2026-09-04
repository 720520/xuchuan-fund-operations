"""Associate a reviewed non-NAV attachment with a product, preserving audit."""

import argparse

from sqlalchemy import select

from app.config import Settings
from app.db import connect, now
from app.models import Document, ExceptionTask, Membership, ParseJob, Product, User
from app.security import audit
from app.services import archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document_id")
    parser.add_argument("product_code")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine, factory = connect(settings.database_url)
    with factory.begin() as db:
        document = db.get(Document, args.document_id)
        if not document:
            raise SystemExit("原件不存在")
        product = db.scalar(
            select(Product).where(
                Product.manager_id == document.manager_id,
                Product.code == args.product_code,
            )
        )
        if not product:
            raise SystemExit("产品不存在或不属于原件牌照")
        job = db.scalar(select(ParseJob).where(ParseJob.document_id == document.id))
        issue = db.scalar(
            select(ExceptionTask).where(
                ExceptionTask.manager_id == document.manager_id,
                ExceptionTask.dedup_key == f"parse:{document.id}",
            )
        )
        print(f"{document.filename} -> {product.code} {product.name}")
        if not args.apply:
            print("当前为预览；加 --apply 后关联并关闭解析异常。")
            return
        actor = next(
            (
                user
                for user, membership in db.execute(
                    select(User, Membership)
                    .join(Membership, Membership.user_id == User.id)
                    .where(Membership.manager_id == document.manager_id)
                )
                if "admin" in (membership.roles or [])
            ),
            None,
        )
        linked = db.scalar(
            select(Document).where(
                Document.parent_id == document.id,
                Document.product_id == product.id,
                Document.source == "business_material",
            )
        )
        if not linked:
            linked = archive(
                db,
                settings,
                document.manager_id,
                document.filename,
                (settings.storage / document.storage_key).read_bytes(),
                "business_material",
                actor=actor,
                product_id=product.id,
                parent_id=document.id,
                received_at=document.received_at,
                metadata={
                    "linked_from_document_id": document.id,
                    "reason": args.reason,
                },
            )
        if job:
            job.status = "completed"
            job.updated_at = now()
            job.result = {
                "records": [],
                "errors": [],
                "record_ids": [],
                "parser_version": "business-material-v1",
                "archived_as_material": True,
                "linked_document_id": linked.id,
                "reason": args.reason,
            }
        if issue and issue.status != "resolved":
            issue.status = "resolved"
            issue.updated_at = now()
            issue.revision += 1
            issue.resolution = {
                "via": "archived_as_business_material",
                "product_id": product.id,
                "linked_document_id": linked.id,
                "reason": args.reason,
            }
        audit(
            db,
            actor,
            document.manager_id,
            "document.associated_as_business_material",
            document.id,
            {"product_id": product.id, "product_code": product.code, "reason": args.reason},
        )
    engine.dispose()
    print("已关联产品并完成材料归档")


if __name__ == "__main__":
    main()
