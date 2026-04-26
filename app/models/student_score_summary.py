from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.core.score_rules import SCORE_RULE_VERSION

from .user import User


class StudentScoreSummary(SQLModel, table=True):
    __tablename__ = "student_score_summary"
    __table_args__ = (UniqueConstraint("student_id", name="uq_student_score_summary_student_id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    student_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    student: User = Relationship(back_populates="score_summary")
    physical_mental_basic: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    physical_mental_achievement: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    physical_mental_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    art_basic: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    art_achievement: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    art_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    labor_basic: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    labor_achievement: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    labor_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    innovation_basic: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    innovation_achievement: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    innovation_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    raw_total_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    overflow_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    physical_mental_achievement_overflow: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    art_achievement_overflow: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    labor_achievement_overflow: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    innovation_achievement_overflow: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    actual_score: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    score_rule_version: str = Field(
        default=SCORE_RULE_VERSION,
        sa_column=Column(String(32), nullable=False, default=SCORE_RULE_VERSION),
    )
    score_breakdown_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
