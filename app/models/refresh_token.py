from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_token_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    user_id: int = Field(sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), index=True))
    token_jti: str = Field(sa_column=Column(String(64), unique=True, index=True))
    is_revoked: bool = Field(default=False, sa_column=Column(Boolean, default=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
