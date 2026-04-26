from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.core.constants import CLASS_GRADE_MAP
from app.core.utils import utcnow
from app.models.class_info import ClassInfo


def serialize_class_info(row: ClassInfo) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "grade": row.grade,
        "name": row.name,
        "label": row.name or f"{row.grade}级 {row.class_id}班",
        "value": row.class_id,
        "is_active": bool(row.is_active),
        "is_deleted": bool(row.is_deleted),
        "is_graduating": is_graduating_grade(row.grade),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def ensure_default_classes(db: Session) -> None:
    existing_count = db.exec(select(ClassInfo)).first()
    if existing_count:
        return
    now = utcnow()
    for class_id, grade in CLASS_GRADE_MAP.items():
        db.add(
            ClassInfo(
                class_id=class_id,
                grade=grade,
                name=f"{grade}级 {class_id}班",
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def list_class_records(
    db: Session,
    *,
    include_deleted: bool = False,
    active_only: bool = False,
    include_graduating: bool = True,
) -> list[ClassInfo]:
    ensure_default_classes(db)
    stmt = select(ClassInfo)
    if not include_deleted:
        stmt = stmt.where(ClassInfo.is_deleted.is_(False))
    if active_only:
        stmt = stmt.where(ClassInfo.is_active.is_(True))
    rows = db.exec(stmt.order_by(ClassInfo.grade.desc(), ClassInfo.class_id.asc())).all()
    if include_graduating:
        return rows
    return [row for row in rows if not is_graduating_grade(row.grade)]


def get_class_info(db: Session, class_id: int | None, *, active_only: bool = False) -> ClassInfo | None:
    if class_id is None:
        return None
    ensure_default_classes(db)
    stmt = select(ClassInfo).where(ClassInfo.class_id == int(class_id), ClassInfo.is_deleted.is_(False))
    if active_only:
        stmt = stmt.where(ClassInfo.is_active.is_(True))
    return db.exec(stmt).first()


def get_class_grade(db: Session, class_id: int | None) -> int | None:
    row = get_class_info(db, class_id)
    if row:
        return row.grade
    if class_id is None:
        return None
    mapped = CLASS_GRADE_MAP.get(int(class_id))
    if mapped is not None:
        return mapped
    if 100 <= int(class_id) <= 999:
        return 2020 + int(class_id) // 100
    return None


def get_class_ids_by_grade(db: Session, grade: int, *, include_graduating: bool = True) -> list[int]:
    rows = list_class_records(db, active_only=True, include_graduating=include_graduating)
    return [row.class_id for row in rows if row.grade == int(grade)]


def get_class_grade_map(db: Session, *, include_graduating: bool = True) -> dict[int, int]:
    rows = list_class_records(db, active_only=True, include_graduating=include_graduating)
    result = {row.class_id: row.grade for row in rows}
    if result:
        return result
    return dict(CLASS_GRADE_MAP)


def is_graduating_class(db: Session, class_id: int | None) -> bool:
    grade = get_class_grade(db, class_id)
    return is_graduating_grade(grade)


def is_graduating_grade(grade: int | None, *, reference_time: datetime | None = None) -> bool:
    if grade is None:
        return False
    now = reference_time or utcnow()
    return int(grade) <= now.year - 4
