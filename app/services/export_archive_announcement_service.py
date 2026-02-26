import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from openpyxl import Workbook
from sqlalchemy import and_, or_, select
from sqlmodel import Session

from app.core.config import settings
from app.models.announcement import Announcement
from app.models.application import Application
from app.models.export_archive import ExportArchive
from app.models.export_task import ExportTask
from app.models.user import User


class ExportArchiveAnnouncementError(Exception):
    def __init__(self, message: str, code: int = 1000):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass
class ExportPayload:
    score_rows: list[dict]
    application_rows: list[dict]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_teacher_or_admin(user: User) -> None:
    if user.role not in {"teacher", "admin"}:
        raise ExportArchiveAnnouncementError("无权限", 1003)


def _build_task_id() -> str:
    return f"exp_{uuid.uuid4().hex[:12]}"


def _build_archive_id() -> str:
    return f"arc_{uuid.uuid4().hex[:12]}"


def _ensure_export_dir() -> str:
    export_dir = os.path.abspath(getattr(settings, "export_dir", "./exports"))
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _build_application_query_filters(filters: dict) -> list:
    conditions = [Application.is_deleted.is_(False)]

    class_ids = filters.get("class_ids")
    class_id = filters.get("class_id")
    status = filters.get("status")
    category = filters.get("category")
    sub_type = filters.get("sub_type")
    keyword = filters.get("keyword")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if class_ids:
        conditions.append(User.class_id.in_(class_ids))
    elif class_id is not None:
        conditions.append(User.class_id == class_id)
    if status:
        conditions.append(Application.status == status)
    if category:
        conditions.append(Application.category == category)
    if sub_type:
        conditions.append(Application.sub_type == sub_type)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            or_(
                User.name.ilike(like),
                User.account.ilike(like),
                Application.title.ilike(like),
            )
        )
    if from_date:
        conditions.append(Application.occurred_at >= from_date)
    if to_date:
        conditions.append(Application.occurred_at <= to_date)

    return conditions


def _resolve_students(db: Session, filters: dict) -> list[User]:
    conditions = [User.role == "student"]
    class_ids = filters.get("class_ids")
    class_id = filters.get("class_id")
    keyword = filters.get("keyword")

    if class_ids:
        conditions.append(User.class_id.in_(class_ids))
    elif class_id is not None:
        conditions.append(User.class_id == class_id)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(User.name.ilike(like), User.account.ilike(like)))

    stmt = select(User).where(and_(*conditions)).order_by(User.class_id.asc(), User.account.asc())
    return db.scalars(stmt).all()


def _build_export_payload(rows: list[tuple[Application, User]], students: list[User]) -> ExportPayload:
    application_rows: list[dict] = []
    summary_by_student: dict[int, dict] = {}

    for student in students:
        summary_by_student[student.id] = {
            "student_id": student.id,
            "account": student.account,
            "name": student.name,
            "class_id": student.class_id,
            "application_count": 0,
            "approved_count": 0,
            "pending_count": 0,
            "rejected_count": 0,
            "approved_score": 0.0,
            "total_score": 0.0,
        }

    for application, student in rows:
        if student.id not in summary_by_student:
            summary_by_student[student.id] = {
                "student_id": student.id,
                "account": student.account,
                "name": student.name,
                "class_id": student.class_id,
                "application_count": 0,
                "approved_count": 0,
                "pending_count": 0,
                "rejected_count": 0,
                "approved_score": 0.0,
                "total_score": 0.0,
            }

        item = summary_by_student[student.id]
        item["application_count"] += 1
        if application.status == "approved":
            item["approved_count"] += 1
            if application.score is not None:
                item["approved_score"] += float(application.score)
                item["total_score"] += float(application.score)
        elif application.status == "rejected":
            item["rejected_count"] += 1
        else:
            item["pending_count"] += 1

        application_rows.append(
            {
                "application_id": application.id,
                "student_id": student.id,
                "student_account": student.account,
                "student_name": student.name,
                "class_id": student.class_id,
                "title": application.title,
                "category": application.category,
                "sub_type": application.sub_type,
                "award_uid": application.award_uid,
                "status": application.status,
                "score": application.score,
                "occurred_at": application.occurred_at.isoformat(),
                "created_at": application.created_at.isoformat(),
                "updated_at": application.updated_at.isoformat(),
            }
        )

    score_rows = []
    for _, item in sorted(summary_by_student.items(), key=lambda pair: (pair[1]["class_id"] or 0, pair[1]["account"] or "")):
        item["approved_score"] = round(item["approved_score"], 2)
        item["total_score"] = round(item["total_score"], 2)
        score_rows.append(item)

    return ExportPayload(score_rows=score_rows, application_rows=application_rows)


def _write_export_excel(task_id: str, payload: ExportPayload) -> tuple[str, str]:
    workbook = Workbook()

    score_sheet = workbook.active
    score_sheet.title = "scores"
    score_sheet.append(
        [
            "student_id",
            "account",
            "name",
            "class_id",
            "application_count",
            "approved_count",
            "pending_count",
            "rejected_count",
            "approved_score",
            "total_score",
        ]
    )
    for row in payload.score_rows:
        score_sheet.append(
            [
                row["student_id"],
                row["account"],
                row["name"],
                row["class_id"],
                row["application_count"],
                row["approved_count"],
                row["pending_count"],
                row["rejected_count"],
                row["approved_score"],
                row["total_score"],
            ]
        )

    application_sheet = workbook.create_sheet("applications")
    application_sheet.append(
        [
            "application_id",
            "student_id",
            "student_account",
            "student_name",
            "class_id",
            "title",
            "category",
            "sub_type",
            "award_uid",
            "status",
            "score",
            "occurred_at",
            "created_at",
            "updated_at",
        ]
    )
    for row in payload.application_rows:
        application_sheet.append(
            [
                row["application_id"],
                row["student_id"],
                row["student_account"],
                row["student_name"],
                row["class_id"],
                row["title"],
                row["category"],
                row["sub_type"],
                row["award_uid"],
                row["status"],
                row["score"],
                row["occurred_at"],
                row["created_at"],
                row["updated_at"],
            ]
        )

    export_dir = _ensure_export_dir()
    file_name = f"{task_id}.xlsx"
    file_path = os.path.join(export_dir, file_name)
    workbook.save(file_path)
    workbook.close()
    return file_path, file_name


def create_export_task(db: Session, user: User, *, scope: str, output_format: str, filters: dict) -> ExportTask:
    _ensure_teacher_or_admin(user)
    normalized_scope = (scope or "applications").strip().lower()
    normalized_format = (output_format or "xlsx").strip().lower()
    if normalized_scope != "applications":
        raise ExportArchiveAnnouncementError("scope 仅支持 applications", 1001)
    if normalized_format != "xlsx":
        raise ExportArchiveAnnouncementError("format 仅支持 xlsx", 1001)

    task_id = _build_task_id()
    query_conditions = _build_application_query_filters(filters)
    rows = db.exec(
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*query_conditions))
        .order_by(Application.created_at.desc())
    ).all()
    students = _resolve_students(db, filters)
    payload = _build_export_payload(rows, students)
    file_path, file_name = _write_export_excel(task_id, payload)

    task = ExportTask(
        task_id=task_id,
        creator_user_id=user.id,
        scope=normalized_scope,
        format=normalized_format,
        status="success",
        file_path=file_path,
        file_name=file_name,
        total_students=len(payload.score_rows),
        total_applications=len(payload.application_rows),
        completed_at=_utc_now(),
    )
    task.set_filters(filters)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_export_task(db: Session, user: User, *, task_id: str) -> ExportTask:
    _ensure_teacher_or_admin(user)
    stmt = select(ExportTask).where(ExportTask.task_id == task_id)
    task = db.exec(stmt).first()
    if task is None:
        raise ExportArchiveAnnouncementError("资源不存在", 1002)
    return task


def create_archive(db: Session, user: User, *, export_task_id: str, archive_name: str | None, term: str | None, grade: int | None, class_ids: list[int] | None) -> ExportArchive:
    _ensure_teacher_or_admin(user)
    task = db.exec(select(ExportTask).where(ExportTask.task_id == export_task_id)).first()
    if task is None:
        raise ExportArchiveAnnouncementError("导出任务不存在", 1002)
    if task.status != "success":
        raise ExportArchiveAnnouncementError("导出任务尚未成功，不能归档", 1000)
    if not task.file_path or not os.path.exists(task.file_path):
        raise ExportArchiveAnnouncementError("导出文件不存在，不能归档", 1002)

    existed_archive = db.exec(select(ExportArchive).where(ExportArchive.export_task_id == export_task_id)).first()
    if existed_archive is not None:
        raise ExportArchiveAnnouncementError("该导出任务已归档", 1007)

    task_filters = task.filters
    resolved_class_ids = class_ids
    if resolved_class_ids is None:
        if isinstance(task_filters.get("class_ids"), list):
            resolved_class_ids = task_filters.get("class_ids")
        elif task_filters.get("class_id") is not None:
            resolved_class_ids = [int(task_filters.get("class_id"))]
        else:
            resolved_class_ids = []

    resolved_archive_name = archive_name or f"{export_task_id}_archive"

    archive = ExportArchive(
        archive_id=_build_archive_id(),
        export_task_id=export_task_id,
        creator_user_id=user.id,
        archive_name=resolved_archive_name,
        term=term,
        grade=grade,
        is_announced=False,
    )
    archive.set_class_ids(resolved_class_ids)

    db.add(archive)
    db.commit()
    db.refresh(archive)
    return archive


def list_archives(db: Session, user: User, *, term: str | None, grade: int | None, class_id: int | None, page: int, size: int) -> dict:
    _ensure_teacher_or_admin(user)
    archives = db.exec(select(ExportArchive).order_by(ExportArchive.created_at.desc())).all()

    filtered: list[ExportArchive] = []
    for item in archives:
        if term and item.term != term:
            continue
        if grade is not None and item.grade != grade:
            continue
        if class_id is not None and class_id not in item.class_ids:
            continue
        filtered.append(item)

    total = len(filtered)
    start = (page - 1) * size
    end = start + size
    paged = filtered[start:end]

    data = []
    for item in paged:
        data.append(
            {
                "archive_id": item.archive_id,
                "archive_name": item.archive_name,
                "export_task_id": item.export_task_id,
                "term": item.term,
                "grade": item.grade,
                "class_ids": item.class_ids,
                "is_announced": item.is_announced,
                "created_at": item.created_at.isoformat(),
            }
        )

    return {
        "page": page,
        "size": size,
        "total": total,
        "list": data,
    }


def get_archive_download_file(db: Session, user: User, *, archive_id: str) -> tuple[str, str]:
    _ensure_teacher_or_admin(user)
    archive = db.exec(select(ExportArchive).where(ExportArchive.archive_id == archive_id)).first()
    if archive is None:
        raise ExportArchiveAnnouncementError("资源不存在", 1002)

    task = db.exec(select(ExportTask).where(ExportTask.task_id == archive.export_task_id)).first()
    if task is None or not task.file_path:
        raise ExportArchiveAnnouncementError("归档对应导出文件不存在", 1002)
    if not os.path.exists(task.file_path):
        raise ExportArchiveAnnouncementError("归档文件不存在", 1002)

    return task.file_path, (task.file_name or f"{task.task_id}.xlsx")


def get_archive_detail(db: Session, user: User, *, archive_id: str) -> dict:
    _ensure_teacher_or_admin(user)
    archive = db.exec(select(ExportArchive).where(ExportArchive.archive_id == archive_id)).first()
    if archive is None:
        raise ExportArchiveAnnouncementError("资源不存在", 1002)

    task = db.exec(select(ExportTask).where(ExportTask.task_id == archive.export_task_id)).first()
    if task is None:
        raise ExportArchiveAnnouncementError("归档对应导出任务不存在", 1002)

    return {
        "archive_id": archive.archive_id,
        "archive_name": archive.archive_name,
        "export_task_id": archive.export_task_id,
        "term": archive.term,
        "grade": archive.grade,
        "class_ids": archive.class_ids,
        "is_announced": archive.is_announced,
        "created_at": archive.created_at.isoformat(),
        "export": {
            "task_id": task.task_id,
            "status": task.status,
            "total_students": task.total_students,
            "total_applications": task.total_applications,
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
    }


def create_announcement(
    db: Session,
    user: User,
    *,
    title: str,
    archive_id: str,
    start_at: datetime,
    end_at: datetime,
    content: str | None,
) -> Announcement:
    _ensure_teacher_or_admin(user)

    archive = db.exec(select(ExportArchive).where(ExportArchive.archive_id == archive_id)).first()
    if archive is None:
        raise ExportArchiveAnnouncementError("归档不存在", 1002)

    announcement = Announcement(
        archive_id=archive_id,
        publisher_user_id=user.id,
        title=title,
        content=content,
        start_at=start_at,
        end_at=end_at,
    )

    archive.is_announced = True
    db.add(archive)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


def list_announcements(db: Session, user: User) -> list[dict]:
    if user.id is None:
        raise ExportArchiveAnnouncementError("无权限", 1003)

    rows = db.exec(
        select(Announcement, ExportArchive)
        .join(ExportArchive, ExportArchive.archive_id == Announcement.archive_id)
        .order_by(Announcement.created_at.desc())
    ).all()
    now = _utc_now()

    data = []
    for announcement, archive in rows:
        data.append(
            {
                "id": announcement.id,
                "title": announcement.title,
                "archive_id": announcement.archive_id,
                "archive_name": archive.archive_name,
                "term": archive.term,
                "grade": archive.grade,
                "class_ids": archive.class_ids,
                "start_at": announcement.start_at.isoformat(),
                "end_at": announcement.end_at.isoformat(),
                "content": announcement.content,
                "is_active": announcement.start_at <= now <= announcement.end_at,
                "created_at": announcement.created_at.isoformat(),
            }
        )
    return data
