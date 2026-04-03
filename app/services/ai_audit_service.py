from sqlmodel import Session, select

from app.core.config import settings
from app.core.constants import ROLE_STUDENT
from app.core.utils import json_dumps, utcnow
from app.models.ai_audit_report import AIAuditReport
from app.models.application import Application
from app.models.application_attachment import ApplicationAttachment
from app.models.award_dict import AwardDict
from app.models.user import User
from app.services.errors import ServiceError
from app.services.serializers import serialize_ai_audit
from app.services.system_log_service import write_system_log


def get_ai_report(db: Session, user: User, application_id: int) -> dict:
    application = db.get(Application, application_id)
    if not application or application.is_deleted:
        raise ServiceError("资源不存在", 1002)
    if user.role == ROLE_STUDENT and application.applicant_id != user.id:
        raise ServiceError("无权限", 1003)
    report = db.exec(select(AIAuditReport).where(AIAuditReport.application_id == application_id)).first()
    if not report:
        raise ServiceError("暂无 AI 审核报告", 1002)
    return serialize_ai_audit(report)


def get_ai_logs(db: Session, user: User, *, result: str | None, page: int, size: int) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("无权限", 1003)
    stmt = select(AIAuditReport)
    if result:
        stmt = stmt.where(AIAuditReport.result == result)
    rows = db.exec(stmt.order_by(AIAuditReport.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    total = len(db.exec(stmt).all())
    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [serialize_ai_audit(row) for row in rows],
    }


def run_ai_audit(db: Session, application_id: int) -> None:
    application = db.get(Application, application_id)
    if not application or application.is_deleted:
        return
    report = db.exec(select(AIAuditReport).where(AIAuditReport.application_id == application_id)).first()
    if not report:
        report = AIAuditReport(application_id=application_id, provider=settings.ai_audit_provider, status="queued")
        db.add(report)
        db.commit()
        db.refresh(report)

    try:
        report.status = "running"
        report.updated_at = utcnow()
        db.add(report)
        db.commit()

        attachment_count = len(
            db.exec(select(ApplicationAttachment).where(ApplicationAttachment.application_id == application_id)).all()
        )
        award = db.exec(select(AwardDict).where(AwardDict.award_uid == application.award_uid)).first()
        risk_points = []
        result = "pass"
        next_status = "pending_review"
        if attachment_count == 0:
            risk_points.append("缺少证明附件")
            result = "abnormal"
            next_status = "ai_abnormal"
        elif "异常" in application.title or "异常" in application.description:
            risk_points.append("标题或描述触发人工复核规则")
            result = "abnormal"
            next_status = "ai_abnormal"

        report.provider = settings.ai_audit_provider
        report.status = "completed"
        report.result = result
        report.ocr_text = f"{application.title} {application.description}"
        report.identity_check_json = json_dumps({"matched": True, "matched_fields": ["title"]})
        report.consistency_check_json = json_dumps({"matched": result == "pass", "diff": risk_points})
        report.risk_points_json = json_dumps(risk_points)
        report.score_breakdown_json = json_dumps(
            [
                {
                    "rule_code": "R_AWARD_UID",
                    "rule_name": f"奖项 {application.award_uid}",
                    "score": application.item_score,
                    "max_score": award.max_score if award else application.item_score,
                }
            ]
        )
        report.item_score = application.item_score
        report.total_score = application.total_score
        report.error_message = None
        report.updated_at = utcnow()
        report.audited_at = utcnow()

        application.status = next_status
        application.updated_at = utcnow()
        db.add(report)
        db.add(application)
        db.commit()
        write_system_log(
            db,
            action="ai_audit.complete",
            target_type="application",
            target_id=str(application_id),
            detail={"result": result, "status": next_status},
        )
    except Exception as exc:
        report.status = "failed"
        report.result = "error"
        report.error_message = str(exc)
        report.updated_at = utcnow()
        db.add(report)
        if settings.ai_audit_fallback_to_manual:
            application.status = "pending_review"
            application.updated_at = utcnow()
            db.add(application)
        db.commit()
        write_system_log(
            db,
            action="ai_audit.failed",
            target_type="application",
            target_id=str(application_id),
            detail={"error": str(exc)},
        )
