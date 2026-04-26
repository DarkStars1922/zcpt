from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url
from sqlmodel import Session, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.bootstrap import seed_initial_data
from app.core.config import settings
from app.core.database import configure_engine, get_engine
from app.core.security import hash_password
from app.core.utils import json_dumps, utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.student_score_summary import StudentScoreSummary
from app.models.user import User
from app.services.reviewer_scope_service import refresh_user_reviewer_state

DEFAULT_PASSWORD = "pass1234"
STANDARD_ACCOUNTS = [
    {
        "account": "admin",
        "name": "系统管理员",
        "role": "admin",
        "class_id": None,
        "email": "admin@zcpt.local",
    },
    {
        "account": "teacher",
        "name": "测试教师一号",
        "role": "teacher",
        "class_id": None,
        "email": "teacher@zcpt.local",
    },
    {
        "account": "teacher_demo",
        "name": "测试教师二号",
        "role": "teacher",
        "class_id": None,
        "email": "teacher_demo@zcpt.local",
    },
    {
        "account": "student_reviewer",
        "name": "学生审核员一号",
        "role": "student",
        "class_id": 301,
        "email": "student_reviewer@zcpt.local",
    },
    {
        "account": "student_reviewer_302",
        "name": "学生审核员二号",
        "role": "student",
        "class_id": 302,
        "email": "student_reviewer_302@zcpt.local",
    },
    {
        "account": "student_normal",
        "name": "普通学生一号",
        "role": "student",
        "class_id": 301,
        "email": "student_normal@zcpt.local",
    },
    {
        "account": "student_302",
        "name": "普通学生二号",
        "role": "student",
        "class_id": 302,
        "email": "student_302@zcpt.local",
    },
]
REVIEWER_TOKEN = "rvw_standard_301"
REVIEWER_TOKENS = {
    "student_reviewer": "rvw_standard_301",
    "student_reviewer_302": "rvw_standard_302",
}
REGISTER_REVIEWER_TOKEN = "rvw_register_301"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed standard MySQL/SQLite test accounts.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL") or settings.database_url)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--skip-upgrade", action="store_true")
    args = parser.parse_args()

    database_url = args.database_url
    os.environ["DATABASE_URL"] = database_url
    settings.database_url = database_url

    _ensure_database(database_url)
    if not args.skip_upgrade:
        _run_alembic_upgrade(database_url)

    configure_engine(database_url)
    with Session(get_engine()) as db:
        seed_initial_data(db)
        users = {
            account["account"]: _upsert_user(db, password=args.password, **account) for account in STANDARD_ACCOUNTS
        }
        for account in STANDARD_ACCOUNTS:
            if account["role"] == "student":
                _ensure_score_summary(db, users[account["account"]].id)
        for reviewer_account, token_value in REVIEWER_TOKENS.items():
            _upsert_reviewer_token(db, token_value=token_value, teacher=users["teacher"], reviewer=users[reviewer_account])
        _upsert_pending_reviewer_token(db, token_value=REGISTER_REVIEWER_TOKEN, teacher=users["teacher"], class_ids=[301])
        for account in STANDARD_ACCOUNTS:
            if account["role"] == "student":
                refresh_user_reviewer_state(db, users[account["account"]])
        db.commit()

    print("standard accounts seeded")
    print(f"database_url={database_url}")
    print("accounts:")
    print(f"  admin   | account=admin                | password={args.password}")
    print(f"  teacher | account=teacher              | password={args.password}")
    print(f"  teacher | account=teacher_demo         | password={args.password}")
    print(f"  student | account=student_reviewer     | password={args.password} | reviewer=yes | class_id=301")
    print(f"  student | account=student_reviewer_302 | password={args.password} | reviewer=yes | class_id=302")
    print(f"  student | account=student_normal       | password={args.password} | reviewer=no  | class_id=301")
    print(f"  student | account=student_302          | password={args.password} | reviewer=no  | class_id=302")
    print(f"active_reviewer_tokens={', '.join(REVIEWER_TOKENS.values())}")
    print(f"unused_register_reviewer_token={REGISTER_REVIEWER_TOKEN}")


def _ensure_database(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql"):
        return
    database_name = url.database
    if not database_name:
        return
    server_url = url.set(database="mysql")
    engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    except OperationalError as exc:
        if "Access denied" in str(exc):
            return
        raise
    finally:
        engine.dispose()


def _run_alembic_upgrade(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT_DIR,
        check=True,
        env=env,
    )


def _upsert_user(
    db: Session,
    *,
    account: str,
    name: str,
    role: str,
    class_id: int | None,
    email: str,
    password: str,
) -> User:
    user = db.exec(select(User).where(User.account == account)).first()
    if not user:
        user = User(account=account, password_hash=hash_password(password), name=name, role=role)
    else:
        user.password_hash = hash_password(password)
    user.name = name
    user.role = role
    user.class_id = class_id
    user.email = email
    user.phone = None
    user.is_deleted = False
    user.deleted_at = None
    user.updated_at = utcnow()
    if role != "student":
        user.is_reviewer = False
        user.reviewer_token_id = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ensure_score_summary(db: Session, student_id: int | None) -> None:
    if student_id is None:
        return
    existing = db.exec(select(StudentScoreSummary).where(StudentScoreSummary.student_id == student_id)).first()
    if existing:
        return
    db.add(StudentScoreSummary(student_id=student_id))
    db.commit()


def _upsert_reviewer_token(db: Session, *, token_value: str, teacher: User, reviewer: User) -> None:
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == token_value)).first()
    now = utcnow()
    if not token:
        token = ReviewerToken(token=token_value)
    token.token_type = "reviewer"
    token.class_ids_json = json_dumps([reviewer.class_id])
    token.status = "active"
    token.created_by = teacher.id
    token.activated_user_id = reviewer.id
    token.activated_at = now
    token.expires_at = None
    token.revoked_at = None
    db.add(token)
    db.commit()

    refresh_user_reviewer_state(db, reviewer)
    db.commit()


def _upsert_pending_reviewer_token(db: Session, *, token_value: str, teacher: User, class_ids: list[int]) -> None:
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == token_value)).first()
    if not token:
        token = ReviewerToken(token=token_value)
    token.token_type = "reviewer"
    token.class_ids_json = json_dumps(class_ids)
    token.status = "pending"
    token.created_by = teacher.id
    token.activated_user_id = None
    token.activated_at = None
    token.expires_at = None
    token.revoked_at = None
    db.add(token)
    db.commit()


if __name__ == "__main__":
    main()
