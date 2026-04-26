from pathlib import Path

from openpyxl import Workbook
from sqlmodel import Session, select

from app.core.award_catalog import serialize_award_rule
from app.core.constants import ANNOUNCEMENT_STATUS_ACTIVE, ANNOUNCEMENT_STATUS_CLOSED
from app.core.score_rules import SCORE_CATEGORY_KEYS, SCORE_CATEGORY_RULES, SCORE_SUB_TYPE_KEYS
from app.core.config import settings
from app.core.term_utils import datetime_in_term
from app.core.utils import ensure_utc_datetime, json_dumps, json_loads, utcnow
from app.models.announcement import Announcement
from app.models.announcement_scope import AnnouncementScopeBinding
from app.models.application import Application
from app.models.archive_record import ArchiveRecord
from app.models.user import User
from app.schemas.announcement import AnnouncementCreateRequest, AnnouncementUpdateRequest
from app.services.class_service import get_class_grade, get_class_ids_by_grade, is_graduating_class
from app.services.evaluation_service import build_report_evaluation
from app.services.errors import ServiceError
from app.services.score_summary_service import get_student_score_summary, get_student_score_summary_map, serialize_score_summary
from app.services.serializers import serialize_announcement, serialize_user
from app.services.system_log_service import write_system_log

CATEGORY_COLORS = {
    "physical_mental": "#c0392b",
    "art": "#7c3aed",
    "labor": "#0f9f7a",
    "innovation": "#2563eb",
}


def create_announcement(db: Session, user: User, payload: AnnouncementCreateRequest) -> dict:
    _require_manage(user)
    archive = _get_archive(db, payload.archive_id)
    scope_rows = _normalize_scope_payload(db, payload)
    announcement = Announcement(
        archive_record_id=archive.id,
        title=payload.title,
        scope_json=json_dumps(_scope_summary(scope_rows)),
        show_fields_json=json_dumps(payload.show_fields or []),
        start_at=payload.start_at,
        end_at=payload.end_at,
        created_by=user.id,
        updated_at=utcnow(),
    )
    db.add(announcement)
    db.flush()
    _replace_scope_bindings(db, announcement, scope_rows)
    db.commit()
    db.refresh(announcement)
    write_system_log(
        db,
        action="announcement.create",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement.id),
    )
    return _serialize_announcement_with_scopes(db, announcement)


def list_announcements(db: Session, user: User) -> list[dict]:
    rows = db.exec(
        select(Announcement, ArchiveRecord)
        .join(ArchiveRecord, Announcement.archive_record_id == ArchiveRecord.id)
        .order_by(Announcement.created_at.desc())
    ).all()
    if user.role == "student":
        rows = [
            (announcement, archive)
            for announcement, archive in rows
            if can_student_view_announcement(announcement, user, db=db)
        ]
    return [_serialize_announcement_with_scopes(db, announcement, fallback_archive=archive) for announcement, archive in rows]


def get_my_announcement_report(db: Session, user: User, announcement_id: int) -> dict:
    if user.role != "student":
        raise ServiceError("permission denied", 1003)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    if not can_student_view_announcement(announcement, user, db=db):
        raise ServiceError("permission denied", 1003)

    archive = db.get(ArchiveRecord, announcement.archive_record_id)
    score_summary = serialize_score_summary(get_student_score_summary(db, user.id), student_id=user.id)
    radar = _build_radar_payload(score_summary)
    return {
        "student": serialize_user(user),
        "announcement": _serialize_announcement_with_scopes(db, announcement, fallback_archive=archive),
        "score_summary": score_summary,
        "radar": radar,
        "award_history": _build_award_history(db, user, announcement=announcement),
        "evaluation": build_report_evaluation(radar=radar),
        "generated_at": utcnow().isoformat(),
    }


def update_announcement(db: Session, user: User, announcement_id: int, payload: AnnouncementUpdateRequest) -> dict:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    archive = _get_archive(db, payload.archive_id)
    scope_rows = _normalize_scope_payload(db, payload)
    announcement.archive_record_id = archive.id
    announcement.title = payload.title
    announcement.scope_json = json_dumps(_scope_summary(scope_rows))
    announcement.show_fields_json = json_dumps(payload.show_fields or [])
    announcement.start_at = payload.start_at
    announcement.end_at = payload.end_at
    announcement.updated_at = utcnow()
    db.add(announcement)
    _replace_scope_bindings(db, announcement, scope_rows)
    db.commit()
    db.refresh(announcement)
    write_system_log(
        db,
        action="announcement.update",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement.id),
    )
    return _serialize_announcement_with_scopes(db, announcement, fallback_archive=archive)


def close_announcement(db: Session, user: User, announcement_id: int) -> dict:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    announcement.status = ANNOUNCEMENT_STATUS_CLOSED
    announcement.closed_at = utcnow()
    announcement.updated_at = utcnow()
    db.add(announcement)
    db.commit()
    archive = db.get(ArchiveRecord, announcement.archive_record_id)
    return _serialize_announcement_with_scopes(db, announcement, fallback_archive=archive)


def reopen_announcement(db: Session, user: User, announcement_id: int) -> dict:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    announcement.status = ANNOUNCEMENT_STATUS_ACTIVE
    announcement.closed_at = None
    announcement.updated_at = utcnow()
    db.add(announcement)
    db.commit()
    archive = db.get(ArchiveRecord, announcement.archive_record_id)
    write_system_log(
        db,
        action="announcement.reopen",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement.id),
    )
    return _serialize_announcement_with_scopes(db, announcement, fallback_archive=archive)


def delete_announcement(db: Session, user: User, announcement_id: int) -> None:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    db.delete(announcement)
    db.commit()
    write_system_log(
        db,
        action="announcement.delete",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement_id),
    )


def get_announcement_download_path(db: Session, user: User, announcement_id: int) -> Path:
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    if user.role == "student":
        if not can_student_view_announcement(announcement, user, db=db):
            raise ServiceError("permission denied", 1003)
    elif user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)

    settings.export_dir_path.mkdir(parents=True, exist_ok=True)
    file_path = settings.export_dir_path / f"announcement_{announcement.id}_public.xlsx"
    _build_public_announcement_workbook(db, announcement, file_path)
    return file_path


def _serialize_announcement_with_scopes(
    db: Session,
    announcement: Announcement,
    *,
    fallback_archive: ArchiveRecord | None = None,
) -> dict:
    archive = fallback_archive or db.get(ArchiveRecord, announcement.archive_record_id)
    return serialize_announcement(
        announcement,
        archive.archive_id if archive else "",
        scopes=_serialize_scope_bindings(db, announcement),
    )


def _serialize_scope_bindings(db: Session, announcement: Announcement) -> list[dict]:
    rows = _get_scope_bindings(db, announcement)
    data = []
    for row in rows:
        archive = db.get(ArchiveRecord, row.archive_record_id)
        data.append(
            {
                "id": row.id,
                "archive_id": archive.archive_id if archive else None,
                "grade": row.grade,
                "class_id": row.class_id,
            }
        )
    return data


def _normalize_scope_payload(db: Session, payload: AnnouncementCreateRequest) -> list[dict]:
    raw_scopes = payload.scopes or []
    if not raw_scopes:
        raw_scopes = [
            {
                "archive_id": payload.archive_id,
                "grade": payload.scope.grade,
                "class_ids": payload.scope.class_ids,
            }
        ]

    rows = []
    seen = set()
    for raw in raw_scopes:
        archive_id = raw.archive_id if hasattr(raw, "archive_id") else raw.get("archive_id")
        grade = raw.grade if hasattr(raw, "grade") else raw.get("grade")
        class_ids = raw.class_ids if hasattr(raw, "class_ids") else raw.get("class_ids", [])
        archive = _get_archive(db, archive_id)
        resolved_grade = _resolve_scope_grade(db, grade, class_ids, archive)
        normalized_class_ids = _safe_int_list(class_ids or [])
        if not normalized_class_ids:
            key = (archive.id, resolved_grade, None)
            if key not in seen:
                rows.append({"archive": archive, "grade": resolved_grade, "class_id": None})
                seen.add(key)
            continue
        for class_id in normalized_class_ids:
            class_grade = _resolve_user_grade(db, class_id)
            if class_grade is not None and class_grade != resolved_grade:
                raise ServiceError("class_id does not belong to announcement grade", 1001)
            key = (archive.id, resolved_grade, class_id)
            if key not in seen:
                rows.append({"archive": archive, "grade": resolved_grade, "class_id": class_id})
                seen.add(key)

    grades = {row["grade"] for row in rows}
    if len(grades) != 1:
        raise ServiceError("不同年级公示必须拆分创建", 1001)
    if not rows:
        raise ServiceError("announcement scope is required", 1001)
    return rows


def _replace_scope_bindings(db: Session, announcement: Announcement, scope_rows: list[dict]) -> None:
    existing = db.exec(
        select(AnnouncementScopeBinding).where(AnnouncementScopeBinding.announcement_id == announcement.id)
    ).all()
    for row in existing:
        db.delete(row)

    touched_archives = {announcement.archive_record_id}
    for row in scope_rows:
        archive = row["archive"]
        touched_archives.add(archive.id)
        archive.is_announced = True
        db.add(archive)
        db.add(
            AnnouncementScopeBinding(
                announcement_id=announcement.id,
                archive_record_id=archive.id,
                grade=row["grade"],
                class_id=row["class_id"],
            )
        )

    for archive_id in touched_archives:
        archive = db.get(ArchiveRecord, archive_id)
        if archive:
            archive.is_announced = True
            db.add(archive)


def _scope_summary(scope_rows: list[dict]) -> dict:
    grade = scope_rows[0]["grade"] if scope_rows else None
    class_ids = sorted(row["class_id"] for row in scope_rows if row["class_id"] is not None)
    return {"grade": grade, "class_ids": class_ids}


def _get_scope_bindings(db: Session, announcement: Announcement) -> list[AnnouncementScopeBinding]:
    rows = db.exec(
        select(AnnouncementScopeBinding)
        .where(AnnouncementScopeBinding.announcement_id == announcement.id)
        .order_by(AnnouncementScopeBinding.grade.asc(), AnnouncementScopeBinding.class_id.asc())
    ).all()
    if rows:
        return rows

    archive = db.get(ArchiveRecord, announcement.archive_record_id)
    scope = json_loads(announcement.scope_json, {})
    grade = _resolve_scope_grade(db, scope.get("grade"), scope.get("class_ids") or [], archive)
    class_ids = _safe_int_list(scope.get("class_ids") or [])
    if not class_ids:
        return [
            AnnouncementScopeBinding(
                announcement_id=announcement.id,
                archive_record_id=announcement.archive_record_id,
                grade=grade,
                class_id=None,
            )
        ]
    return [
        AnnouncementScopeBinding(
            announcement_id=announcement.id,
            archive_record_id=announcement.archive_record_id,
            grade=grade,
            class_id=class_id,
        )
        for class_id in class_ids
    ]


def _build_public_announcement_workbook(db: Session, announcement: Announcement, file_path: Path) -> None:
    students = _query_public_students(db, announcement)
    student_ids = [student.id for student in students if student.id is not None]
    score_map = get_student_score_summary_map(db, student_ids)

    wb = Workbook()
    total_ws = wb.active
    total_ws.title = "公示总分"
    total_ws.append(["年级", "班级", "学号", "姓名", "官方总分"])
    for student in students:
        score_summary = serialize_score_summary(score_map.get(student.id), student_id=student.id)
        total_ws.append(
            [
                _resolve_user_grade(db, student.class_id),
                student.class_id,
                student.account,
                student.name,
                score_summary["actual_score"],
            ]
        )

    application_ws = wb.create_sheet("范围内申报")
    application_ws.append(["年级", "班级", "学号", "姓名", "申报名称", "分类", "小类", "分数", "状态", "发生日期"])
    for application, student in _query_public_applications(db, announcement):
        category_rule = SCORE_CATEGORY_RULES.get(application.category, {})
        sub_rule = (category_rule.get("sub_types") or {}).get(application.sub_type, {})
        application_ws.append(
            [
                _resolve_user_grade(db, student.class_id),
                student.class_id,
                student.account,
                student.name,
                application.title,
                category_rule.get("name") or application.category,
                sub_rule.get("name") or application.sub_type,
                application.item_score,
                application.status,
                application.occurred_at.isoformat() if application.occurred_at else "",
            ]
        )
    wb.save(file_path)


def _query_public_students(db: Session, announcement: Announcement) -> list[User]:
    bindings = _get_scope_bindings(db, announcement)
    class_ids = _expand_scope_class_ids(db, bindings)
    stmt = select(User).where(User.role == "student", User.is_deleted.is_(False))
    if class_ids:
        stmt = stmt.where(User.class_id.in_(class_ids))
    rows = db.exec(stmt.order_by(User.class_id.asc(), User.account.asc())).all()
    grades = {row.grade for row in bindings}
    if class_ids:
        return [row for row in rows if not is_graduating_class(db, row.class_id)]
    return [
        row
        for row in rows
        if _resolve_user_grade(db, row.class_id) in grades and not is_graduating_class(db, row.class_id)
    ]


def _query_public_applications(db: Session, announcement: Announcement) -> list[tuple[Application, User]]:
    students = _query_public_students(db, announcement)
    student_ids = [student.id for student in students if student.id is not None]
    if not student_ids:
        return []
    bindings = _get_scope_bindings(db, announcement)
    archive_by_id = {row.archive_record_id: db.get(ArchiveRecord, row.archive_record_id) for row in bindings}
    rows = db.exec(
        select(Application, User)
        .join(User, Application.applicant_id == User.id)
        .where(
            Application.applicant_id.in_(student_ids),
            Application.is_deleted.is_(False),
            Application.status.in_(("approved", "archived")),
        )
        .order_by(User.class_id.asc(), User.account.asc(), Application.occurred_at.asc(), Application.id.asc())
    ).all()
    return [
        (application, student)
        for application, student in rows
        if _application_matches_announcement_scope(db, application, student, bindings, archive_by_id)
    ]


def _expand_scope_class_ids(db: Session, bindings: list[AnnouncementScopeBinding]) -> list[int]:
    result = []
    grades_with_all_classes = {row.grade for row in bindings if row.class_id is None}
    for grade in grades_with_all_classes:
        for class_id in get_class_ids_by_grade(db, grade, include_graduating=False):
            if class_id not in result:
                result.append(class_id)
    for row in bindings:
        if row.class_id is not None and row.class_id not in result:
            result.append(row.class_id)
    return sorted(result)


def _resolve_scope_grade(db: Session, value, class_ids, archive: ArchiveRecord | None) -> int:
    grade = _safe_int(value)
    if grade is not None:
        return grade
    class_id_list = _safe_int_list(class_ids or [])
    class_grades = {_resolve_user_grade(db, class_id) for class_id in class_id_list}
    class_grades.discard(None)
    if len(class_grades) == 1:
        return class_grades.pop()
    if len(class_grades) > 1:
        raise ServiceError("不同年级公示必须拆分创建", 1001)
    if archive and archive.grade:
        return int(archive.grade)
    raise ServiceError("announcement grade is required", 1001)


def _build_radar_payload(score_summary: dict) -> dict:
    sub_scores = score_summary.get("sub_scores") or {}
    category_scores = score_summary.get("category_scores") or {}
    achievement_overflow_scores = score_summary.get("achievement_overflow_scores") or {}
    categories = []
    indicators = []
    for category in SCORE_CATEGORY_KEYS:
        rule = SCORE_CATEGORY_RULES[category]
        color = CATEGORY_COLORS.get(category, "#9c0c13")
        submodules = []
        for sub_type in SCORE_SUB_TYPE_KEYS:
            sub_rule = rule["sub_types"][sub_type]
            field = f"{category}_{sub_type}"
            score = _round_score(sub_scores.get(field, 0.0))
            overflow = _round_score(achievement_overflow_scores.get(f"{category}_achievement_overflow", 0.0)) if sub_type == "achievement" else 0.0
            item = {
                "key": field,
                "category": category,
                "sub_type": sub_type,
                "name": sub_rule["name"],
                "score": score,
                "max_score": _round_score(sub_rule["max_score"]),
                "overflow_score": overflow,
                "score_with_overflow": _round_score(score + overflow),
                "color": color,
            }
            submodules.append(item)
            indicators.append(
                {
                    "key": field,
                    "name": f"{rule['name']}-{sub_rule['name']}",
                    "max": _round_score(sub_rule["max_score"]),
                    "category": category,
                    "color": color,
                }
            )
        categories.append(
            {
                "key": category,
                "name": rule["name"],
                "score": _round_score(category_scores.get(f"{category}_score", 0.0)),
                "max_score": _round_score(rule["max_score"]),
                "color": color,
                "submodules": submodules,
            }
        )
    return {
        "categories": categories,
        "indicators": indicators,
    }


def _build_award_history(db: Session, user: User, *, announcement: Announcement | None = None) -> list[dict]:
    rows = db.exec(
        select(Application).where(
            Application.applicant_id == user.id,
            Application.status.in_(("approved", "archived")),
            Application.is_deleted.is_(False),
        ).order_by(Application.occurred_at.asc(), Application.created_at.asc(), Application.id.asc())
    ).all()
    history = []
    public_application_ids = None
    if announcement is not None:
        public_application_ids = {
            application.id
            for application, _ in _query_public_applications(db, announcement)
            if application.applicant_id == user.id
        }
    for application in rows:
        if public_application_ids is not None and application.id not in public_application_ids:
            continue
        award_rule = serialize_award_rule(application.award_uid)
        if _is_participation_award(application, award_rule):
            continue
        category_rule = SCORE_CATEGORY_RULES.get(application.category, {})
        sub_rule = (category_rule.get("sub_types") or {}).get(application.sub_type, {})
        history.append(
            {
                "application_id": application.id,
                "title": application.title,
                "occurred_at": application.occurred_at.isoformat() if application.occurred_at else None,
                "status": application.status,
                "score": _round_score(application.item_score or 0.0),
                "category": application.category,
                "category_name": category_rule.get("name") or application.category,
                "sub_type": application.sub_type,
                "sub_type_name": sub_rule.get("name") or application.sub_type,
                "award_uid": application.award_uid,
                "award_rule": award_rule,
                "award_rule_name": (award_rule or {}).get("rule_name"),
            }
        )
    return history


def _is_participation_award(application: Application, award_rule: dict | None) -> bool:
    haystacks = [
        application.title,
        str(application.award_uid),
        (award_rule or {}).get("rule_name"),
        (award_rule or {}).get("rule_path"),
    ]
    return any("参与未获奖" in str(item) for item in haystacks if item)


def _round_score(value) -> float:
    return round(float(value or 0.0), 4)


def can_student_view_announcement(announcement: Announcement, user: User, db: Session | None = None) -> bool:
    if user.role != "student":
        return False
    if announcement.status != ANNOUNCEMENT_STATUS_ACTIVE:
        return False
    now = utcnow()
    start_at = ensure_utc_datetime(announcement.start_at)
    end_at = ensure_utc_datetime(announcement.end_at)
    if start_at and now < start_at:
        return False
    if end_at and now > end_at:
        return False

    if db is None:
        from app.core.database import get_engine

        with Session(get_engine()) as session:
            bindings = _get_scope_bindings(session, announcement)
            if not bindings:
                return False
            if is_graduating_class(session, user.class_id):
                return False
            user_grade = _resolve_user_grade(session, user.class_id)
            for row in bindings:
                if row.class_id is not None and row.class_id == user.class_id:
                    return True
                if row.class_id is None and user_grade == row.grade:
                    return True
            return False
    else:
        bindings = _get_scope_bindings(db, announcement)
    if not bindings:
        return False
    if is_graduating_class(db, user.class_id):
        return False
    user_grade = _resolve_user_grade(db, user.class_id)
    for row in bindings:
        if row.class_id is not None and row.class_id == user.class_id:
            return True
        if row.class_id is None and user_grade == row.grade:
            return True
    return False


def _require_manage(user: User) -> None:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)


def _get_archive(db: Session, archive_id: str) -> ArchiveRecord:
    archive = db.exec(select(ArchiveRecord).where(ArchiveRecord.archive_id == archive_id)).first()
    if not archive:
        raise ServiceError("archive not found", 1002)
    return archive


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int_list(values: list) -> list[int]:
    result = []
    for item in values:
        number = _safe_int(item)
        if number is None:
            continue
        if number not in result:
            result.append(number)
    return result


def _application_matches_announcement_scope(
    db: Session,
    application: Application,
    student: User,
    bindings: list[AnnouncementScopeBinding],
    archive_by_id: dict[int, ArchiveRecord | None],
) -> bool:
    student_grade = _resolve_user_grade(db, student.class_id)
    for row in bindings:
        class_matches = row.class_id == student.class_id if row.class_id is not None else row.grade == student_grade
        if not class_matches:
            continue
        archive = archive_by_id.get(row.archive_record_id)
        if archive and not datetime_in_term(application.created_at, archive.term):
            continue
        return True
    return False


def _resolve_user_grade(db: Session, class_id: int | None) -> int | None:
    return get_class_grade(db, class_id)
