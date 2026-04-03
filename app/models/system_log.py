from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class SystemLog(SQLModel, table=True):
    __tablename__ = "system_log"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    actor_id: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    action: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    target_type: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    target_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    detail_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
