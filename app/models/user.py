from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    __tablename__ = "user_info"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    account: str = Field(sa_column=Column(String(32), unique=True, index=True, nullable=False))
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(sa_column=Column(String(64), nullable=False))
    role: str = Field(default="student", sa_column=Column(String(20), nullable=False, default="student"))
    is_reviewer: bool | None = Field(default=False, sa_column=Column(Integer, nullable=False, default=0))
    reviewer_token_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("reviewer_token_record.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    class_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    email: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    phone: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
