from pydantic import BaseModel, Field


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = Field(default=None, max_length=2000)


class BatchReviewDecisionRequest(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=200)
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = Field(default=None, max_length=2000)


class TeacherRecheckRequest(ReviewDecisionRequest):
    score: float | None = Field(default=None, ge=0)
