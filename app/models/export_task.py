import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ExportTask(SQLModel, table=True):
    __tablename__ = "teacher_export_task"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    task_id: str = Field(sa_column=Column(String(40), unique=True, nullable=False, index=True))
    creator_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    scope: str = Field(default="applications", sa_column=Column(String(32), nullable=False, default="applications"))
    format: str = Field(default="xlsx", sa_column=Column(String(16), nullable=False, default="xlsx"))
    filters_json: str = Field(default="{}", sa_column=Column(Text, nullable=False, default="{}"))
    status: str = Field(default="success", sa_column=Column(String(20), nullable=False, default="success", index=True))
    file_path: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    file_name: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    total_students: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    total_applications: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    @property
    def filters(self) -> dict:
        try:
            value = json.loads(self.filters_json or "{}")
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    def set_filters(self, value: dict) -> None:
        self.filters_json = json.dumps(value, ensure_ascii=False)
