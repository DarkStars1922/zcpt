from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel


class StudentScoreSummary(SQLModel, table=True):
    __tablename__ = "student_score_summary"
    __table_args__ = (UniqueConstraint("student_id", name="uq_student_score_summary_student_id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    student_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    actual_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
