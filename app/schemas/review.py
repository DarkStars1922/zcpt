from pydantic import BaseModel, Field


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    comment: str | None = Field(default=None, max_length=1000)
    reason_code: str | None = Field(default=None, max_length=64)
    reason_text: str | None = Field(default=None, max_length=2000)


class ReviewBatchDecisionRequest(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=200)
    decision: str = Field(min_length=1, max_length=20)
    comment: str | None = Field(default=None, max_length=1000)
    reason_code: str | None = Field(default=None, max_length=64)
    reason_text: str | None = Field(default=None, max_length=2000)
