from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlmodel import Field, SQLModel


class ClassInfo(SQLModel, table=True):
    __tablename__ = "class_info"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    class_id: int = Field(sa_column=Column(Integer, unique=True, nullable=False, index=True))
    grade: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    name: str = Field(sa_column=Column(String(64), nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True, index=True))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
