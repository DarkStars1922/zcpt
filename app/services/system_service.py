from sqlalchemy import func
from sqlmodel import Session, select

from app.core.award_catalog import load_award_tree
from app.core.utils import json_dumps, utcnow
from app.models.award_dict import AwardDict
from app.models.system_config import SystemConfig
from app.models.system_log import SystemLog
from app.models.user import User
from app.schemas.system import AwardDictCreateRequest, AwardDictUpdateRequest, SystemConfigUpdateRequest
from app.services.errors import ServiceError
from app.services.serializers import serialize_system_config, serialize_system_log
from app.services.system_log_service import write_system_log


def get_system_configs(db: Session, user: User) -> dict:
    _require_admin(user)
    rows = db.exec(select(SystemConfig).order_by(SystemConfig.config_key.asc())).all()
    return {item.config_key: serialize_system_config(item)["config_value"] for item in rows}


def update_system_config(db: Session, user: User, payload: SystemConfigUpdateRequest) -> dict:
    _require_admin(user)
    config = db.exec(select(SystemConfig).where(SystemConfig.config_key == payload.config_key)).first()
    if not config:
        config = SystemConfig(config_key=payload.config_key, config_value_json=json_dumps(payload.config_value))
    config.config_value_json = json_dumps(payload.config_value)
    config.description = payload.description
    config.updated_by = user.id
    config.updated_at = utcnow()
    db.add(config)
    db.commit()
    db.refresh(config)
    write_system_log(
        db,
        action="system.config.update",
        actor_id=user.id,
        target_type="system_config",
        target_id=payload.config_key,
    )
    return serialize_system_config(config)


def get_system_logs(db: Session, user: User, *, page: int, size: int, action: str | None = None) -> dict:
    _require_admin(user)
    stmt = select(SystemLog)
    if action:
        stmt = stmt.where(SystemLog.action == action)
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(SystemLog.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"page": page, "size": size, "total": total, "list": [serialize_system_log(item) for item in rows]}


def list_award_dicts(db: Session, user: User) -> list[dict]:
    _require_admin(user)
    rows = db.exec(select(AwardDict).order_by(AwardDict.award_uid.asc())).all()
    return [
        {
            "id": row.id,
            "award_uid": row.award_uid,
            "category": row.category,
            "sub_type": row.sub_type,
            "award_name": row.award_name,
            "score": row.score,
            "max_score": row.max_score,
            "is_active": row.is_active,
        }
        for row in rows
    ]


def create_award_dict(db: Session, user: User, payload: AwardDictCreateRequest) -> dict:
    _require_admin(user)
    existing = db.exec(select(AwardDict).where(AwardDict.award_uid == payload.award_uid)).first()
    if existing:
        raise ServiceError("award_uid 已存在", 1007)
    award = AwardDict(**payload.model_dump())
    db.add(award)
    db.commit()
    db.refresh(award)
    write_system_log(db, action="system.award_dict.create", actor_id=user.id, target_type="award_dict", target_id=str(award.id))
    return {
        "id": award.id,
        "award_uid": award.award_uid,
        "category": award.category,
        "sub_type": award.sub_type,
        "award_name": award.award_name,
        "score": award.score,
        "max_score": award.max_score,
        "is_active": award.is_active,
    }


def update_award_dict(db: Session, user: User, award_id: int, payload: AwardDictUpdateRequest) -> dict:
    _require_admin(user)
    award = db.get(AwardDict, award_id)
    if not award:
        raise ServiceError("奖项不存在", 1002)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(award, field, value)
    db.add(award)
    db.commit()
    db.refresh(award)
    write_system_log(db, action="system.award_dict.update", actor_id=user.id, target_type="award_dict", target_id=str(award.id))
    return {
        "id": award.id,
        "award_uid": award.award_uid,
        "category": award.category,
        "sub_type": award.sub_type,
        "award_name": award.award_name,
        "score": award.score,
        "max_score": award.max_score,
        "is_active": award.is_active,
    }


def delete_award_dict(db: Session, user: User, award_id: int) -> None:
    _require_admin(user)
    award = db.get(AwardDict, award_id)
    if not award:
        raise ServiceError("奖项不存在", 1002)
    db.delete(award)
    db.commit()
    write_system_log(db, action="system.award_dict.delete", actor_id=user.id, target_type="award_dict", target_id=str(award_id))


def get_award_types(_: Session, __: User) -> list[dict]:
    return load_award_tree()


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise ServiceError("无权限", 1003)
