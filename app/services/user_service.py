from sqlmodel import Session

from app.core.utils import utcnow
from app.models.user import User
from app.schemas.user import UserUpdateRequest
from app.services.serializers import serialize_user
from app.services.system_log_service import write_system_log


def get_me(user: User) -> dict:
    return serialize_user(user)


def update_me(db: Session, user: User, payload: UserUpdateRequest) -> dict:
    if payload.email is not None:
        user.email = payload.email
    if payload.phone is not None:
        user.phone = payload.phone
    user.updated_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    write_system_log(db, action="user.update_me", actor_id=user.id, target_type="user", target_id=str(user.id))
    return serialize_user(user)
