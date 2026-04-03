from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class SystemConfig(SQLModel, table=True):
    __tablename__ = "system_config"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    config_key: str = Field(sa_column=Column(String(100), unique=True, index=True, nullable=False))
    config_value_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    updated_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
