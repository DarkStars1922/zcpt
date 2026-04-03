from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ReviewerToken(SQLModel, table=True):
    __tablename__ = "reviewer_token_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    token: str = Field(sa_column=Column(String(128), unique=True, index=True, nullable=False))
    token_type: str = Field(sa_column=Column(String(20), nullable=False, default="reviewer"))
    class_ids_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="pending", index=True))
    created_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    activated_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True),
    )
    activated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
