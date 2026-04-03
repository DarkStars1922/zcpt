from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlmodel import Field, SQLModel


class ArchiveRecord(SQLModel, table=True):
    __tablename__ = "archive_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    archive_id: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    archive_name: str = Field(sa_column=Column(String(255), nullable=False))
    term: str = Field(sa_column=Column(String(32), nullable=False))
    grade: int | None = Field(default=None, sa_column=Column(Integer, nullable=True, index=True))
    class_ids_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    export_task_id: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    is_announced: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
