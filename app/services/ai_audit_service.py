from difflib import SequenceMatcher
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.core.constants import MANAGE_REVIEW_ROLES, ROLE_STUDENT
from app.core.utils import json_dumps, utcnow
from app.models.ai_audit_report import AIAuditReport
from app.models.application import Application
from app.models.application_attachment import ApplicationAttachment
from app.models.award_dict import AwardDict
from app.models.file_analysis_result import FileAnalysisResult
from app.models.file_info import FileInfo
from app.models.user import User
from app.services.errors import ServiceError
from app.services.file_analysis_service import analyze_file, get_file_analysis_payload
from app.services.reviewer_scope_service import get_active_reviewer_class_ids
from app.services.serializers import serialize_ai_audit
from app.services.system_log_service import write_system_log


def get_ai_report(db: Session, user: User, application_id: int) -> dict:
    application = db.get(Application, application_id)
    if not application or application.is_deleted:
        raise ServiceError("resource not found", 1002)

    if user.role in MANAGE_REVIEW_ROLES:
        pass
    elif user.role == ROLE_STUDENT:
        if application.applicant_id != user.id:
            reviewer_class_ids = get_active_reviewer_class_ids(db, user)
            if not reviewer_class_ids:
                raise ServiceError("permission denied", 1003)
            applicant = db.get(User, application.applicant_id)
            if not applicant or applicant.class_id not in reviewer_class_ids:
                raise ServiceError("permission denied", 1003)
    else:
        raise ServiceError("permission denied", 1003)

    report = db.exec(select(AIAuditReport).where(AIAuditReport.application_id == application_id)).first()
    if not report:
        raise ServiceError("ai report not found", 1002)
    return serialize_ai_audit(report)


def get_ai_logs(db: Session, user: User, *, result: str | None, page: int, size: int) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
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
    applicant = db.get(User, application.applicant_id)
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

        attachment_rows = db.exec(
            select(ApplicationAttachment, FileInfo, FileAnalysisResult)
            .join(FileInfo, ApplicationAttachment.file_id == FileInfo.id)
            .outerjoin(FileAnalysisResult, FileAnalysisResult.file_id == FileInfo.id)
            .where(ApplicationAttachment.application_id == application_id, FileInfo.status != "deleted")
        ).all()
        attachment_count = len(attachment_rows)
        award = db.exec(select(AwardDict).where(AwardDict.award_uid == application.award_uid)).first()
        risk_points = []
        warning_points = []
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

        attachment_analysis = []
        for _, file, analysis in attachment_rows:
            if not analysis or analysis.status != "completed":
                analysis = analyze_file(db, file, uploader=applicant)
            attachment_analysis.append(
                {
                    "file_id": file.id,
                    "filename": file.original_name,
                    "analysis": analysis,
                    "payload": get_file_analysis_payload(analysis),
                }
            )

        combined_ocr_text = "\n".join(
            item["analysis"].ocr_text.strip()
            for item in attachment_analysis
            if item["analysis"] and item["analysis"].status == "completed" and item["analysis"].ocr_text
        ).strip()
        if not combined_ocr_text:
            combined_ocr_text = f"{application.title} {application.description}".strip()

        identity_check = _build_identity_check(applicant, attachment_analysis)
        consistency_check = _build_consistency_check(application, award, attachment_analysis)
        risk_points.extend(consistency_check["critical_risks"])
        warning_points.extend(consistency_check["warning_risks"])
        if identity_check["status"] == "mismatch":
            warning_points.append("附件未识别到申请人姓名")
        if consistency_check["payload"]["title_check"]["status"] == "mismatch":
            result = "abnormal"
            next_status = "ai_abnormal"
        if consistency_check["payload"]["level_check"]["status"] == "mismatch":
            result = "abnormal"
            next_status = "ai_abnormal"

        report.provider = settings.ai_audit_provider
        report.status = "completed"
        report.result = result
        report.ocr_text = combined_ocr_text
        report.identity_check_json = json_dumps(identity_check)
        report.consistency_check_json = json_dumps(consistency_check["payload"])
        report.risk_points_json = json_dumps(risk_points + warning_points)
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


def _build_identity_check(applicant: User | None, attachment_analysis: list[dict]) -> dict:
    expected_name = applicant.name if applicant else None
    file_checks = []
    matched_fields = []
    any_completed = False
    any_match = False
    for item in attachment_analysis:
        analysis = item["analysis"]
        payload = item["payload"]
        name_check = payload.get("uploader_name_match", {})
        if analysis and analysis.status == "completed":
            any_completed = True
        matched = bool(name_check.get("matched"))
        if matched:
            any_match = True
            matched_fields.append(item["file_id"])
        file_checks.append(
            {
                "file_id": item["file_id"],
                "filename": item["filename"],
                "matched": name_check.get("matched"),
                "matches": name_check.get("matches", []),
                "status": analysis.status if analysis else "missing",
            }
        )
    status = "matched" if any_match else "mismatch" if any_completed else "unknown"
    return {
        "expected_name": expected_name,
        "matched": any_match,
        "status": status,
        "matched_fields": matched_fields,
        "files": file_checks,
    }


def _build_consistency_check(application: Application, award: AwardDict | None, attachment_analysis: list[dict]) -> dict:
    document_titles = []
    recognized_levels = []
    seal_detected = False
    signature_detected = False
    file_checks = []
    any_completed = False

    for item in attachment_analysis:
        analysis = item["analysis"]
        payload = item["payload"]
        if analysis and analysis.status == "completed":
            any_completed = True
        document_title = payload.get("document_title")
        if document_title:
            document_titles.append(document_title)
        for level in payload.get("recognized_levels", []):
            if level not in recognized_levels:
                recognized_levels.append(level)
        seal_detected = seal_detected or bool(payload.get("seal", {}).get("detected"))
        signature_detected = signature_detected or bool(payload.get("signature", {}).get("detected"))
        filename_similarity = _text_similarity(Path(item["filename"]).stem, application.title)
        file_checks.append(
            {
                "file_id": item["file_id"],
                "filename": item["filename"],
                "matched": filename_similarity >= 0.62,
                "similarity": filename_similarity,
            }
        )

    title_score = max((_text_similarity(title, application.title) for title in document_titles), default=0.0)
    title_status = "matched" if title_score >= 0.72 else "mismatch" if document_titles else "unknown"

    expected_levels = _extract_levels(application.title, application.description, award.award_name if award else "")
    if expected_levels and recognized_levels:
        level_status = "matched" if set(expected_levels) & set(recognized_levels) else "mismatch"
    elif expected_levels:
        level_status = "unknown"
    else:
        level_status = "matched"

    filename_status = "matched" if any(item["matched"] for item in file_checks) else "mismatch" if file_checks else "unknown"
    seal_status = "matched" if seal_detected else "mismatch" if any_completed else "unknown"
    signature_status = "matched" if signature_detected else "mismatch" if any_completed else "unknown"

    critical_risks = []
    warning_risks = []
    if title_status == "mismatch":
        critical_risks.append("附件 OCR 内容与申报标题不一致")
    if level_status == "mismatch":
        critical_risks.append("附件识别级别与申报内容不一致")
    if filename_status == "mismatch":
        warning_risks.append("上传文件名与申报标题相似度较低")
    if seal_status == "mismatch":
        warning_risks.append("未提取到印章区域")
    if signature_status == "mismatch":
        warning_risks.append("未提取到落款或签字区域")

    payload = {
        "matched": not critical_risks,
        "diff": critical_risks + warning_risks,
        "title_check": {
            "status": title_status,
            "expected": application.title,
            "recognized_titles": document_titles,
            "best_similarity": title_score,
        },
        "level_check": {
            "status": level_status,
            "expected": expected_levels,
            "recognized": recognized_levels,
        },
        "filename_check": {
            "status": filename_status,
            "expected": application.title,
            "files": file_checks,
        },
        "seal_check": {
            "status": seal_status,
            "detected": seal_detected,
        },
        "signature_check": {
            "status": signature_status,
            "detected": signature_detected,
        },
    }
    return {
        "payload": payload,
        "critical_risks": critical_risks,
        "warning_risks": warning_risks,
    }


def _extract_levels(*texts: str) -> list[str]:
    keywords = []
    haystack = "\n".join(filter(None, texts))
    for item in ("国际级", "国家级", "省级", "市级", "校级", "院级", "一等奖", "二等奖", "三等奖", "特等奖"):
        if item in haystack and item not in keywords:
            keywords.append(item)
    return keywords


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 1.0
    return round(SequenceMatcher(None, normalized_left, normalized_right).ratio(), 4)


def _normalize_text(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
