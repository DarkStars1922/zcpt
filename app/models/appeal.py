from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Appeal(SQLModel, table=True):
    __tablename__ = "appeal_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    announcement_id: int = Field(
        sa_column=Column(Integer, ForeignKey("announcement_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    student_id: int = Field(sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=False, index=True))
    application_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("comprehensive_apply.id"), nullable=True, index=True),
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="pending", index=True))
    result: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    result_comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    score_action: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    adjusted_score: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    processed_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
