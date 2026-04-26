from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.award_catalog import load_award_tree
from app.core.constants import MANAGE_REVIEW_ROLES, REVIEWER_TOKEN_STATUS_ACTIVE, ROLE_STUDENT, ROLE_TEACHER
from app.core.security import hash_password
from app.core.utils import json_dumps, utcnow
from app.models.award_dict import AwardDict
from app.models.class_info import ClassInfo
from app.models.refresh_token import RefreshToken
from app.models.reviewer_token import ReviewerToken
from app.models.system_config import SystemConfig
from app.models.system_log import SystemLog
from app.models.user import User
from app.schemas.system import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AwardDictCreateRequest,
    AwardDictUpdateRequest,
    ClassCreateRequest,
    ClassUpdateRequest,
    SystemConfigUpdateRequest,
)
from app.services.class_service import get_class_info, list_class_records, serialize_class_info
from app.services.errors import ServiceError
from app.services.reviewer_scope_service import (
    is_datetime_expired,
    refresh_user_reviewer_state,
    sync_reviewer_token_expirations,
)
from app.services.serializers import serialize_system_config, serialize_system_log, serialize_user
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


def list_users(
    db: Session,
    user: User,
    *,
    role: str | None,
    keyword: str | None,
    page: int,
    size: int,
) -> dict:
    _require_admin(user)
    stmt = select(User).where(User.is_deleted.is_(False))
    if role:
        stmt = stmt.where(User.role == role)
    if keyword:
        like_value = f"%{keyword}%"
        stmt = stmt.where(or_(User.account.ilike(like_value), User.name.ilike(like_value), User.email.ilike(like_value)))
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"page": page, "size": size, "total": total, "list": [serialize_user(row) for row in rows]}


def create_user_by_admin(db: Session, user: User, payload: AdminUserCreateRequest) -> dict:
    _require_admin(user)
    if payload.role not in {ROLE_STUDENT, ROLE_TEACHER}:
        raise ServiceError("管理员面板仅支持创建学生或教师账号", 1001)
    existing = db.exec(select(User).where(User.account == payload.account)).first()
    if existing:
        raise ServiceError("账号已存在", 1007)

    if payload.role == ROLE_STUDENT:
        _validate_selectable_class(db, payload.class_id)

    token_record = _validate_reviewer_token(db, payload.reviewer_token) if payload.is_reviewer else None
    created = User(
        account=payload.account,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
        class_id=payload.class_id if payload.role == ROLE_STUDENT else None,
        is_reviewer=False,
        email=payload.email,
        phone=payload.phone,
        updated_at=utcnow(),
    )
    db.add(created)
    db.flush()

    if token_record:
        token_record.status = REVIEWER_TOKEN_STATUS_ACTIVE
        token_record.activated_user_id = created.id
        token_record.activated_at = utcnow()
        token_record.revoked_at = None
        db.add(token_record)
        refresh_user_reviewer_state(db, created)

    db.commit()
    db.refresh(created)
    write_system_log(
        db,
        action="system.user.create",
        actor_id=user.id,
        target_type="user",
        target_id=str(created.id),
        detail={"role": created.role, "is_reviewer": bool(created.is_reviewer)},
    )
    return serialize_user(created)


def update_user_by_admin(db: Session, user: User, target_user_id: int, payload: AdminUserUpdateRequest) -> dict:
    _require_admin(user)
    target = db.get(User, target_user_id)
    if not target or target.is_deleted:
        raise ServiceError("账号不存在", 1002)
    if target.role == "admin":
        raise ServiceError("管理员账号不能在此处修改", 1003)

    data = payload.model_dump(exclude_unset=True)
    next_role = data.get("role", target.role)
    if next_role not in {ROLE_STUDENT, ROLE_TEACHER}:
        raise ServiceError("管理员面板仅支持修改学生或教师账号", 1001)

    next_account = data.get("account")
    if next_account and next_account != target.account:
        existing = db.exec(
            select(User).where(User.account == next_account, User.id != target.id, User.is_deleted.is_(False))
        ).first()
        if existing:
            raise ServiceError("账号已存在", 1007)
        target.account = next_account

    if "name" in data and data["name"] is not None:
        target.name = data["name"]
    if "password" in data and data["password"]:
        target.password_hash = hash_password(data["password"])
        _revoke_refresh_tokens_for_user(db, target.id)
    if "email" in data:
        target.email = data["email"]
    if "phone" in data:
        target.phone = data["phone"]

    if next_role == ROLE_TEACHER:
        if target.role == ROLE_STUDENT:
            _release_reviewer_tokens(db, target)
        target.role = ROLE_TEACHER
        target.class_id = None
        target.is_reviewer = False
        target.reviewer_token_id = None
    else:
        next_class_id = data.get("class_id", target.class_id)
        if next_class_id is None:
            raise ServiceError("学生账号必须选择班级", 1001)
        _validate_selectable_class(db, next_class_id)
        target.role = ROLE_STUDENT
        target.class_id = next_class_id

        if data.get("is_reviewer") is False:
            _release_reviewer_tokens(db, target)
        elif data.get("is_reviewer") is True:
            token_value = (data.get("reviewer_token") or "").strip()
            active_tokens = db.exec(
                select(ReviewerToken).where(
                    ReviewerToken.activated_user_id == target.id,
                    ReviewerToken.status == REVIEWER_TOKEN_STATUS_ACTIVE,
                )
            ).all()
            if token_value:
                _release_reviewer_tokens(db, target)
                token_record = _validate_reviewer_token(db, token_value)
                _bind_reviewer_token(db, target, token_record)
            elif not active_tokens:
                raise ServiceError("设置审核员身份必须填写激活码", 1001)
            refresh_user_reviewer_state(db, target)

    target.updated_at = utcnow()
    db.add(target)
    db.commit()
    db.refresh(target)
    write_system_log(
        db,
        action="system.user.update",
        actor_id=user.id,
        target_type="user",
        target_id=str(target.id),
        detail={"role": target.role, "is_reviewer": bool(target.is_reviewer)},
    )
    return serialize_user(target)


def delete_user_by_admin(db: Session, user: User, target_user_id: int) -> None:
    _require_admin(user)
    if user.id == target_user_id:
        raise ServiceError("不能删除当前登录的管理员账号", 1003)
    target = db.get(User, target_user_id)
    if not target or target.is_deleted:
        raise ServiceError("账号不存在", 1002)
    if target.role == "admin":
        raise ServiceError("管理员账号不能在此处删除", 1003)

    _release_reviewer_tokens(db, target)
    _revoke_refresh_tokens_for_user(db, target.id)
    target.is_deleted = True
    target.deleted_at = utcnow()
    target.updated_at = utcnow()
    target.is_reviewer = False
    target.reviewer_token_id = None
    db.add(target)
    db.commit()
    write_system_log(
        db,
        action="system.user.delete",
        actor_id=user.id,
        target_type="user",
        target_id=str(target.id),
        detail={"account": target.account, "role": target.role},
    )


def list_classes(
    db: Session,
    user: User | None,
    *,
    public_only: bool = False,
    include_deleted: bool = False,
) -> list[dict]:
    if public_only or user is None or user.role == ROLE_STUDENT:
        rows = list_class_records(db, active_only=True, include_graduating=False)
    else:
        if user.role not in MANAGE_REVIEW_ROLES:
            raise ServiceError("无权限", 1003)
        rows = list_class_records(db, include_deleted=include_deleted, active_only=False, include_graduating=True)
    return [serialize_class_info(row) for row in rows]


def create_class(db: Session, user: User, payload: ClassCreateRequest) -> dict:
    _require_class_manage(user)
    existing = db.exec(select(ClassInfo).where(ClassInfo.class_id == payload.class_id)).first()
    if existing and not existing.is_deleted:
        raise ServiceError("班级编号已存在", 1007)
    if existing and existing.is_deleted:
        existing.grade = payload.grade
        existing.name = payload.name or f"{payload.grade}级 {payload.class_id}班"
        existing.is_active = payload.is_active
        existing.is_deleted = False
        existing.deleted_at = None
        existing.updated_at = utcnow()
        row = existing
    else:
        row = ClassInfo(
            class_id=payload.class_id,
            grade=payload.grade,
            name=payload.name or f"{payload.grade}级 {payload.class_id}班",
            is_active=payload.is_active,
            updated_at=utcnow(),
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    write_system_log(
        db,
        action="system.class.create",
        actor_id=user.id,
        target_type="class",
        target_id=str(row.class_id),
        detail={"grade": row.grade},
    )
    return serialize_class_info(row)


def update_class(db: Session, user: User, class_id: int, payload: ClassUpdateRequest) -> dict:
    _require_class_manage(user)
    row = get_class_info(db, class_id)
    if not row:
        raise ServiceError("班级不存在", 1002)
    data = payload.model_dump(exclude_unset=True)
    if "grade" in data and data["grade"] is not None:
        row.grade = data["grade"]
    if "name" in data:
        row.name = data["name"] or f"{row.grade}级 {row.class_id}班"
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = bool(data["is_active"])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    write_system_log(
        db,
        action="system.class.update",
        actor_id=user.id,
        target_type="class",
        target_id=str(row.class_id),
        detail={"grade": row.grade, "is_active": row.is_active},
    )
    return serialize_class_info(row)


def delete_class(db: Session, user: User, class_id: int) -> None:
    _require_class_manage(user)
    row = get_class_info(db, class_id)
    if not row:
        raise ServiceError("班级不存在", 1002)
    active_users = db.exec(
        select(func.count()).select_from(User).where(
            User.class_id == class_id,
            User.is_deleted.is_(False),
        )
    ).one()
    if active_users:
        raise ServiceError("班级下仍有账号，不能删除；可先停用该班级", 1000)
    row.is_deleted = True
    row.is_active = False
    row.deleted_at = utcnow()
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    write_system_log(
        db,
        action="system.class.delete",
        actor_id=user.id,
        target_type="class",
        target_id=str(class_id),
    )


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


def _validate_reviewer_token(db: Session, token_value: str | None) -> ReviewerToken:
    token_text = (token_value or "").strip()
    sync_reviewer_token_expirations(db, auto_commit=False)
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == token_text)).first()
    if not token:
        raise ServiceError("审核员激活码不存在", 1002)
    if token.status == "revoked":
        raise ServiceError("审核员激活码已撤销", 1000)
    if is_datetime_expired(token.expires_at):
        token.status = "expired"
        db.add(token)
        raise ServiceError("审核员激活码已过期", 1000)
    if token.status == REVIEWER_TOKEN_STATUS_ACTIVE and token.activated_user_id:
        raise ServiceError("审核员激活码已被使用", 1007)
    return token


def _bind_reviewer_token(db: Session, user: User, token: ReviewerToken) -> None:
    token.status = REVIEWER_TOKEN_STATUS_ACTIVE
    token.activated_user_id = user.id
    token.activated_at = utcnow()
    token.revoked_at = None
    db.add(token)
    refresh_user_reviewer_state(db, user)


def _release_reviewer_tokens(db: Session, user: User) -> None:
    tokens = db.exec(
        select(ReviewerToken).where(
            ReviewerToken.activated_user_id == user.id,
            ReviewerToken.status == REVIEWER_TOKEN_STATUS_ACTIVE,
        )
    ).all()
    for token in tokens:
        token.status = "pending"
        token.activated_user_id = None
        token.activated_at = None
        token.revoked_at = None
        db.add(token)
    user.is_reviewer = False
    user.reviewer_token_id = None
    db.add(user)


def _revoke_refresh_tokens_for_user(db: Session, user_id: int | None) -> None:
    if user_id is None:
        return
    rows = db.exec(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))).all()
    now = utcnow()
    for row in rows:
        row.is_revoked = True
        row.updated_at = now
        db.add(row)


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise ServiceError("无权限", 1003)


def _require_class_manage(user: User) -> None:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("无权限", 1003)


def _validate_selectable_class(db: Session, class_id: int | None) -> None:
    row = get_class_info(db, class_id, active_only=True)
    if not row:
        raise ServiceError("请选择有效班级", 1001)
