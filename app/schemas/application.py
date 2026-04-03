from datetime import date

from pydantic import BaseModel, Field, model_validator


class AttachmentPayload(BaseModel):
    file_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_attachment(self):
        if not self.file_id:
            raise ValueError("attachments[].file_id 必填")
        return self


class ApplicationCreateRequest(BaseModel):
    award_uid: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    occurred_at: date
    attachments: list[AttachmentPayload] = Field(default_factory=list)
    category: str = Field(min_length=1, max_length=32)
    sub_type: str = Field(min_length=1, max_length=64)
    score: float | None = Field(default=None, ge=0)


class ApplicationUpdateRequest(ApplicationCreateRequest):
    version: int | None = Field(default=None, ge=1)
