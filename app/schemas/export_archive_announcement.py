from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class TeacherExportFilters(BaseModel):
    grade: int | None = Field(default=None, ge=1900, le=3000)
    class_id: int | None = Field(default=None, ge=1)
    class_ids: list[int] | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=32)
    sub_type: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=255)
    from_date: date | None = None
    to_date: date | None = None


class TeacherExportCreateRequest(BaseModel):
    scope: str = Field(default="applications", max_length=32)
    format: str = Field(default="xlsx", max_length=16)
    filters: TeacherExportFilters = Field(default_factory=TeacherExportFilters)


class ArchiveCreateRequest(BaseModel):
    export_task_id: str = Field(min_length=1, max_length=40)
    archive_name: str | None = Field(default=None, max_length=255)
    term: str | None = Field(default=None, max_length=32)
    grade: int | None = Field(default=None, ge=1900, le=3000)
    class_ids: list[int] | None = Field(default=None, max_length=200)


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    archive_id: str = Field(min_length=1, max_length=40)
    start_at: datetime
    end_at: datetime
    content: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at 必须晚于 start_at")
        return self
