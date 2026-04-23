from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlmodel import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.bootstrap import seed_initial_data
from app.core.config import settings
from app.core.database import configure_engine, get_engine
from app.core.security import hash_password
from app.core.utils import json_dumps, utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.services.reviewer_scope_service import refresh_user_reviewer_state

DEFAULT_PASSWORD = "pass1234"


def main() -> None:
    db_path = _resolve_sqlite_db_path(settings.database_url)
    if db_path.exists():
        db_path.unlink()

    _run_alembic_upgrade()
    configure_engine(settings.database_url)

    reviewer_token_value = ""
    with Session(get_engine()) as db:
        seed_initial_data(db)

        admin = _create_user(
            db,
            account="admin",
            name="Admin",
            role="admin",
            class_id=None,
            password=DEFAULT_PASSWORD,
            email="admin@zcpt.example.com",
        )
        teacher = _create_user(
            db,
            account="teacher",
            name="Teacher",
            role="teacher",
            class_id=None,
            password=DEFAULT_PASSWORD,
            email="teacher@zcpt.example.com",
        )
        reviewer_student = _create_user(
            db,
            account="student301_reviewer",
            name="Student 301 Reviewer",
            role="student",
            class_id=301,
            password=DEFAULT_PASSWORD,
            email="student301_reviewer@zcpt.example.com",
        )
        student_301 = _create_user(
            db,
            account="student301",
            name="Student 301",
            role="student",
            class_id=301,
            password=DEFAULT_PASSWORD,
            email="student301@zcpt.example.com",
        )
        student_302 = _create_user(
            db,
            account="student302",
            name="Student 302",
            role="student",
            class_id=302,
            password=DEFAULT_PASSWORD,
            email="student302@zcpt.example.com",
        )

        reviewer_token = ReviewerToken(
            token="rvw_seed_301_reviewer",
            token_type="reviewer",
            class_ids_json=json_dumps([301]),
            status="active",
            created_by=teacher.id,
            activated_user_id=reviewer_student.id,
            activated_at=utcnow(),
        )
        db.add(reviewer_token)
        db.commit()
        db.refresh(reviewer_token)

        refresh_user_reviewer_state(db, reviewer_student)
        db.commit()
        reviewer_token_value = reviewer_token.token

    print("reset + seed completed")
    print(f"database: {db_path}")
    print("accounts:")
    print(f"  admin    | account=admin               | password={DEFAULT_PASSWORD}")
    print(f"  teacher  | account=teacher             | password={DEFAULT_PASSWORD}")
    print(f"  student  | account=student301_reviewer | password={DEFAULT_PASSWORD} | class_id=301 | reviewer=yes")
    print(f"  student  | account=student301          | password={DEFAULT_PASSWORD} | class_id=301")
    print(f"  student  | account=student302          | password={DEFAULT_PASSWORD} | class_id=302")
    print(f"reviewer token (student301_reviewer): {reviewer_token_value}")


def _create_user(
    db: Session,
    *,
    account: str,
    name: str,
    role: str,
    class_id: int | None,
    password: str,
    email: str,
) -> User:
    user = User(
        account=account,
        password_hash=hash_password(password),
        name=name,
        role=role,
        class_id=class_id,
        email=email,
        is_reviewer=False,
        updated_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resolve_sqlite_db_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite"):
        raise RuntimeError("reset_seed_accounts.py only supports sqlite DATABASE_URL")

    prefix = "sqlite:///"
    raw_path = database_url[len(prefix) :] if database_url.startswith(prefix) else database_url.replace("sqlite://", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def _run_alembic_upgrade() -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = settings.database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT_DIR,
        check=True,
        env=env,
    )


if __name__ == "__main__":
    main()
