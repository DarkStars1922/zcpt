from pathlib import Path

from openpyxl import Workbook
from sqlmodel import Session, select

from app.core.cache import set_json
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.constants import CLASS_GRADE_MAP
from app.core.database import get_engine
from app.core.utils import json_loads, utcnow
from app.models.email_record import EmailRecord
from app.models.export_task import ExportTask
from app.models.application import Application
from app.models.user import User


def enqueue_ai_audit(application_id: int) -> None:
    run_ai_audit_task.delay(application_id)


def enqueue_email_job(email_id: int) -> None:
    send_email_task.delay(email_id)


def enqueue_export_job(task_id: str) -> None:
    generate_export_task.delay(task_id)


@celery_app.task(name="app.tasks.jobs.run_ai_audit_task")
def run_ai_audit_task(application_id: int) -> None:
    from app.services.ai_audit_service import run_ai_audit

    with Session(get_engine()) as db:
        run_ai_audit(db, application_id)


@celery_app.task(name="app.tasks.jobs.send_email_task")
def send_email_task(email_id: int) -> None:
    with Session(get_engine()) as db:
        record = db.get(EmailRecord, email_id)
        if not record:
            return
        if settings.email_mock_success:
            record.status = "mock_sent"
            record.error_message = None
        else:
            record.status = "failed"
            record.error_message = "mock provider configured to fail"
        record.sent_at = utcnow()
        db.add(record)
        db.commit()


@celery_app.task(name="app.tasks.jobs.generate_export_task")
def generate_export_task(task_id: str) -> None:
    with Session(get_engine()) as db:
        task = db.exec(select(ExportTask).where(ExportTask.task_id == task_id)).first()
        if not task:
            return
        task.status = "running"
        db.add(task)
        db.commit()
        _write_export_cache(task)

        filters = json_loads(task.filters_json, {})
        stmt = select(Application, User).join(User, Application.applicant_id == User.id).where(Application.is_deleted.is_(False))
        if filters.get("class_id"):
            stmt = stmt.where(User.class_id == int(filters["class_id"]))
        if filters.get("grade"):
            class_ids = [cid for cid, grade in CLASS_GRADE_MAP.items() if grade == int(filters["grade"])]
            if class_ids:
                stmt = stmt.where(User.class_id.in_(class_ids))
        if filters.get("status"):
            stmt = stmt.where(Application.status == filters["status"])

        rows = db.exec(stmt.order_by(Application.created_at.desc())).all()
        settings.export_dir_path.mkdir(parents=True, exist_ok=True)
        file_name = f"{task.task_id}.xlsx"
        file_path = settings.export_dir_path / file_name
        _build_workbook(rows, file_path)

        task.file_name = file_name
        task.file_path = str(file_path)
        task.status = "completed"
        task.completed_at = utcnow()
        db.add(task)
        db.commit()
        _write_export_cache(task)

        options = json_loads(task.options_json, {})
        if options.get("store_to_archive"):
            from app.services.archive_service import create_archive_record_from_task

            create_archive_record_from_task(db, task)


def _build_workbook(rows: list[tuple[Application, User]], file_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "applications"
    ws.append(["application_id", "student_name", "student_account", "class_id", "category", "sub_type", "title", "status", "score"])
    for application, user in rows:
        ws.append(
            [
                application.id,
                user.name,
                user.account,
                user.class_id,
                application.category,
                application.sub_type,
                application.title,
                application.status,
                application.item_score,
            ]
        )
    wb.save(file_path)


def _write_export_cache(task: ExportTask) -> None:
    set_json(
        f"{settings.export_status_prefix}{task.task_id}",
        {
            "task_id": task.task_id,
            "status": task.status,
            "file_name": task.file_name,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
        ttl_seconds=settings.celery_result_expires_seconds,
    )
