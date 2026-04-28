from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class TeacherInsightCache(SQLModel, table=True):
    __tablename__ = "teacher_insight_cache"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    cache_key: str = Field(sa_column=Column(String(64), unique=True, nullable=False, index=True))
    term: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    grade: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    class_ids_key: str = Field(sa_column=Column(String(512), nullable=False, index=True))
    max_risk_students: int = Field(sa_column=Column(Integer, nullable=False, default=12))
    result_json: str = Field(sa_column=Column(Text, nullable=False))
    source: str | None = Field(default=None, sa_column=Column(String(32), nullable=True, index=True))
    status: str = Field(default="completed", sa_column=Column(String(20), nullable=False, default="completed", index=True))
    generated_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
