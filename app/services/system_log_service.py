from sqlmodel import Session

from app.core.utils import json_dumps
from app.models.system_log import SystemLog


def write_system_log(
    db: Session,
    *,
    action: str,
    actor_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
) -> None:
    log = SystemLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=json_dumps(detail or {}),
    )
    db.add(log)
    db.commit()
