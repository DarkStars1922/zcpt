from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel


class AnnouncementScopeBinding(SQLModel, table=True):
    __tablename__ = "announcement_scope_binding"
    __table_args__ = (
        UniqueConstraint("announcement_id", "archive_record_id", "class_id", name="uq_announcement_scope_class"),
    )

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    announcement_id: int = Field(
        sa_column=Column(Integer, ForeignKey("announcement_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    archive_record_id: int = Field(
        sa_column=Column(Integer, ForeignKey("archive_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    grade: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    class_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
