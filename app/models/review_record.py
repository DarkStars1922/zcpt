from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ReviewRecord(SQLModel, table=True):
    __tablename__ = "review_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    application_id: int = Field(
        sa_column=Column(Integer, ForeignKey("comprehensive_apply.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    reviewer_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    decision: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    reason_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    reason_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
