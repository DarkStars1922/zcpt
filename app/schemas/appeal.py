from pydantic import BaseModel, Field

from app.schemas.application import AttachmentPayload


class AppealCreateRequest(BaseModel):
    announcement_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=2000)
    application_id: int | None = Field(default=None, gt=0)
    attachments: list[AttachmentPayload] = Field(default_factory=list)


class AppealProcessRequest(BaseModel):
    result: str = Field(pattern="^(approved|rejected)$")
    result_comment: str | None = Field(default=None, max_length=2000)
    application_id: int | None = Field(default=None, gt=0)
    score_action: str = Field(default="none", pattern="^(none|cancel_application|adjust_score)$")
    score: float | None = Field(default=None, ge=0)
