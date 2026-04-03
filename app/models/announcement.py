from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Announcement(SQLModel, table=True):
    __tablename__ = "announcement_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    archive_record_id: int = Field(
        sa_column=Column(Integer, ForeignKey("archive_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    title: str = Field(sa_column=Column(String(255), nullable=False))
    scope_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    show_fields_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="active"))
    start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    end_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    closed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
