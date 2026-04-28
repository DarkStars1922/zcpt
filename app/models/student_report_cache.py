from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class StudentReportCache(SQLModel, table=True):
    __tablename__ = "student_report_cache"
    __table_args__ = (UniqueConstraint("announcement_id", "student_id", name="uq_student_report_cache_scope"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    announcement_id: int = Field(
        sa_column=Column(Integer, ForeignKey("announcement_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    student_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    term: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    status: str = Field(default="completed", sa_column=Column(String(20), nullable=False, default="completed", index=True))
    report_json: str = Field(sa_column=Column(Text, nullable=False))
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
