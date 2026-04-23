from __future__ import annotations

from sqlmodel import Session, select

from app.core.utils import utcnow
from app.models.student_score_summary import StudentScoreSummary


def get_student_actual_score_map(db: Session, student_ids: list[int]) -> dict[int, float]:
    if not student_ids:
        return {}
    rows = db.exec(
        select(StudentScoreSummary).where(StudentScoreSummary.student_id.in_(student_ids))
    ).all()
    return {row.student_id: float(row.actual_score or 0.0) for row in rows}


def add_student_actual_score(db: Session, student_id: int, score_delta: float) -> StudentScoreSummary:
    summary = db.exec(select(StudentScoreSummary).where(StudentScoreSummary.student_id == student_id)).first()
    if not summary:
        summary = StudentScoreSummary(student_id=student_id, actual_score=0.0)
    summary.actual_score = round(float(summary.actual_score or 0.0) + float(score_delta or 0.0), 4)
    summary.updated_at = utcnow()
    db.add(summary)
    return summary
