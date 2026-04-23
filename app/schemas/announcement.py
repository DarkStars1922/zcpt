from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AnnouncementScope(BaseModel):
    grade: int | None = None
    class_ids: list[int] = Field(default_factory=list)


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    archive_id: str = Field(min_length=1, max_length=64)
    scope: AnnouncementScope
    start_at: datetime
    end_at: datetime
    show_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at 必须晚于 start_at")
        return self


class AnnouncementUpdateRequest(AnnouncementCreateRequest):
    pass
