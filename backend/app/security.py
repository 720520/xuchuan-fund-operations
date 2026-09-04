import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException
from sqlalchemy import select

from .db import now
from .models import (
    AuditEvent,
    Manager,
    Membership,
    Product,
    ProductGrant,
    Session,
    User,
)

PASSWORDS = PasswordHasher()
ROLES = {
    "admin",
    "operator",
    "operations_lead",
    "manager_head",
    "group_viewer",
    "fund_manager",
    "trader",
    "compliance",
    "finance",
}
OPERATORS = {"operator", "operations_lead"}
FULL_READ = OPERATORS | {"manager_head", "group_viewer", "compliance"}


def password_hash(password):
    if len(password) < 12 or len(password) > 128:
        raise HTTPException(422, "密码长度须为 12–128 位")
    return PASSWORDS.hash(password)


def verify_password(encoded, password):
    try:
        return PASSWORDS.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def new_session(db, user_id, hours):
    token = secrets.token_urlsafe(48)
    db.add(
        Session(
            token_hash=digest(token),
            user_id=user_id,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(hours=hours)
            ).isoformat(),
        )
    )
    return token


def session_user(db, token):
    session = db.get(Session, digest(token)) if token else None
    user = (
        db.get(User, session.user_id)
        if session and session.expires_at > now()
        else None
    )
    if not user or not user.active:
        raise HTTPException(401, "请登录，或会话已失效")
    return user


def memberships(db, user):
    return list(db.scalars(select(Membership).where(Membership.user_id == user.id)))


def rights(db, user, manager_id):
    manager = db.get(Manager, manager_id)
    if not manager:
        return {
            "member": False,
            "read": False,
            "write": False,
            "admin": False,
            "download": False,
            "all_products": False,
            "archive": False,
            "roles": [],
        }
    own = next((m for m in memberships(db, user) if m.manager_id == manager_id), None)
    roles = set(own.roles) if own else set()
    is_admin = "admin" in roles
    group_access = False
    for m in memberships(db, user):
        if set(m.roles) & (OPERATORS | {"group_viewer"}):
            other = db.get(Manager, m.manager_id)
            if other.group_id == manager.group_id:
                group_access = True
    grants = bool(
        db.scalar(
            select(ProductGrant.id)
            .join(Product, Product.id == ProductGrant.product_id)
            .where(ProductGrant.user_id == user.id, Product.manager_id == manager_id)
            .limit(1)
        )
    )
    return {
        "member": own is not None,
        "read": is_admin
        or bool(roles & FULL_READ)
        or group_access
        or bool(roles & {"fund_manager", "trader", "finance"} and grants),
        "write": is_admin or bool(roles & OPERATORS),
        "admin": is_admin,
        "download": is_admin or bool(own and own.can_download),
        "all_products": is_admin or bool(roles & FULL_READ) or group_access,
        "archive": is_admin or bool(roles & FULL_READ),
        "roles": sorted(roles),
    }


def require(db, user, manager_id, action="read", product_id=None):
    permissions = rights(db, user, manager_id)
    if not permissions.get(action):
        raise HTTPException(403, "没有该牌照的相应权限")
    if action == "read" and not permissions["all_products"]:
        if not product_id or not db.scalar(
            select(ProductGrant.id).where(
                ProductGrant.user_id == user.id, ProductGrant.product_id == product_id
            )
        ):
            raise HTTPException(403, "没有该产品的查看权限")
    return permissions


def audit(db, actor, manager_id, action, object_id, details=None):
    db.add(
        AuditEvent(
            manager_id=manager_id,
            actor_id=actor.id if actor else None,
            action=action,
            object_id=object_id,
            details=details or {},
        )
    )
