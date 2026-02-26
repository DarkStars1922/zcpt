from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Announcement(SQLModel, table=True):
    __tablename__ = "announcement_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    archive_id: str = Field(
        sa_column=Column(String(40), ForeignKey("export_archive_record.archive_id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    publisher_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    title: str = Field(sa_column=Column(String(255), nullable=False))
    content: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    end_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
