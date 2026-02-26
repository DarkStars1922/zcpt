import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ExportArchive(SQLModel, table=True):
    __tablename__ = "export_archive_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    archive_id: str = Field(sa_column=Column(String(40), unique=True, nullable=False, index=True))
    export_task_id: str = Field(
        sa_column=Column(String(40), ForeignKey("teacher_export_task.task_id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    creator_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    archive_name: str = Field(sa_column=Column(String(255), nullable=False))
    term: str | None = Field(default=None, sa_column=Column(String(32), nullable=True, index=True))
    grade: int | None = Field(default=None, sa_column=Column(Integer, nullable=True, index=True))
    class_ids_json: str = Field(default="[]", sa_column=Column(Text, nullable=False, default="[]"))
    is_announced: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def class_ids(self) -> list[int]:
        try:
            value = json.loads(self.class_ids_json or "[]")
            if not isinstance(value, list):
                return []
            return [int(item) for item in value if isinstance(item, int)]
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def set_class_ids(self, value: list[int]) -> None:
        self.class_ids_json = json.dumps(value, ensure_ascii=False)
