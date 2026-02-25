import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class ReviewerToken(SQLModel, table=True):
    __tablename__ = "reviewer_token_record"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    token: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    token_type: str = Field(default="reviewer", sa_column=Column(String(20), nullable=False, default="reviewer"))

    creator_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    activated_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    class_ids_json: str = Field(default="[]", sa_column=Column(Text, nullable=False, default="[]"))
    is_revoked: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))

    activated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    expired_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def class_ids(self) -> list[int]:
        try:
            value = json.loads(self.class_ids_json or "[]")
            if not isinstance(value, list):
                return []
            return [int(item) for item in value if isinstance(item, int) or (isinstance(item, str) and item.isdigit())]
        except (json.JSONDecodeError, ValueError, TypeError):
            return []

    def set_class_ids(self, class_ids: list[int]) -> None:
        cleaned = [int(item) for item in class_ids]
        self.class_ids_json = json.dumps(cleaned, ensure_ascii=False)
