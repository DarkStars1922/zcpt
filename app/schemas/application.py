from datetime import date

from pydantic import BaseModel, Field, model_validator


class AttachmentPayload(BaseModel):
    file_id: str | None = Field(default=None, min_length=1, max_length=128)
    file_url: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_attachment_ref(self):
        if not self.file_id and not self.file_url:
            raise ValueError("attachments[].file_id 或 attachments[].file_url 至少提供一个")
        return self


class ApplicationCreateRequest(BaseModel):
    award_uid: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    occurred_at: date
    attachments: list[AttachmentPayload] = Field(default_factory=list)
    category: str = Field(min_length=1, max_length=32)
    sub_type: str = Field(min_length=1, max_length=64)
    score: float | None = Field(default=None, ge=0)


class ApplicationUpdateRequest(BaseModel):
    award_uid: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    occurred_at: date
    attachments: list[AttachmentPayload] = Field(default_factory=list)
    category: str = Field(min_length=1, max_length=32)
    sub_type: str = Field(min_length=1, max_length=64)
    score: float | None = Field(default=None, ge=0)
