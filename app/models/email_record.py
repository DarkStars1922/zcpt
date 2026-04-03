from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class EmailRecord(SQLModel, table=True):
    __tablename__ = "email_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    application_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("comprehensive_apply.id"), nullable=True, index=True),
    )
    appeal_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("appeal_record.id"), nullable=True, index=True),
    )
    to_email: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    subject: str = Field(sa_column=Column(String(255), nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))
    provider: str = Field(sa_column=Column(String(50), nullable=False, default="mock"))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="queued", index=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    sent_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
