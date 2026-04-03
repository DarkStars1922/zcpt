from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ExportTask(SQLModel, table=True):
    __tablename__ = "export_task_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    task_id: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    scope: str = Field(sa_column=Column(String(50), nullable=False))
    format: str = Field(sa_column=Column(String(20), nullable=False))
    filters_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    options_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="queued", index=True))
    file_path: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    file_name: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
