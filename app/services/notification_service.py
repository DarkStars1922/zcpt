from sqlmodel import Session, select

from app.core.config import settings
from app.models.application import Application
from app.models.email_record import EmailRecord
from app.models.user import User
from app.schemas.notification import RejectEmailRequest
from app.services.errors import ServiceError
from app.services.serializers import serialize_email
from app.services.system_log_service import write_system_log
from app.tasks.jobs import enqueue_email_job


def queue_reject_email(db: Session, user: User, payload: RejectEmailRequest) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("无权限", 1003)
    subject = payload.subject or "综测平台通知"
    body = payload.body or "您的综测申请或申诉状态发生变化，请登录平台查看。"
    record = EmailRecord(
        application_id=payload.application_id,
        appeal_id=payload.appeal_id,
        to_email=payload.to,
        subject=subject,
        body=body,
        provider=settings.email_provider,
        status="queued",
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    response_payload = serialize_email(record)
    enqueue_email_job(record.id)
    write_system_log(
        db,
        action="notification.queue_email",
        actor_id=user.id,
        target_type="email",
        target_id=str(record.id),
    )
    return response_payload


def enqueue_reject_email_for_application(db: Session, *, actor: User, application: Application, to_email: str) -> None:
    queue_reject_email(
        db,
        actor,
        RejectEmailRequest(
            application_id=application.id,
            to=to_email,
            subject="综测申报驳回通知",
            body=f"您的申报《{application.title}》已被驳回，请登录平台查看详情。",
        ),
    )


def get_email_logs(db: Session, user: User, *, status: str | None, page: int, size: int) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("无权限", 1003)
    stmt = select(EmailRecord)
    if status:
        stmt = stmt.where(EmailRecord.status == status)
    rows = db.exec(stmt.order_by(EmailRecord.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    total = len(db.exec(stmt).all())
    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [serialize_email(row) for row in rows],
    }
