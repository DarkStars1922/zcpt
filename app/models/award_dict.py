from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlmodel import Field, SQLModel


class AwardDict(SQLModel, table=True):
    __tablename__ = "award_dict"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    award_uid: int = Field(sa_column=Column(Integer, unique=True, index=True, nullable=False))
    category: str | None = Field(default=None, sa_column=Column(String(32), nullable=True, index=True))
    sub_type: str | None = Field(default=None, sa_column=Column(String(64), nullable=True, index=True))
    award_name: str = Field(sa_column=Column(String(255), nullable=False))
    score: float = Field(sa_column=Column(Float, nullable=False, default=0.0))
    max_score: float = Field(sa_column=Column(Float, nullable=False, default=0.0))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
