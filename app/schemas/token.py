from datetime import datetime

from pydantic import BaseModel, Field


class CreateReviewerTokenRequest(BaseModel):
    class_ids: list[int] = Field(min_length=1)
    expired_at: datetime | None = None


class ActivateReviewerTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
