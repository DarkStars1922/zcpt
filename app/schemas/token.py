from datetime import datetime

from pydantic import BaseModel, Field


class ReviewerTokenCreateRequest(BaseModel):
    class_ids: list[int] = Field(min_length=1)
    expired_at: datetime


class ReviewerTokenActivateRequest(BaseModel):
    token: str = Field(min_length=6, max_length=64)
