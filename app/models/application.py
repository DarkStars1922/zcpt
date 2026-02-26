import json
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Application(SQLModel, table=True):
    __tablename__ = "comprehensive_apply"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    applicant_id: int = Field(
        sa_column=Column(Integer, ForeignKey("user_info.id", ondelete="CASCADE"), index=True)
    )

    category: str = Field(
        default="physical_mental",
        sa_column=Column(String(32), nullable=False, default="physical_mental"),
    )
    sub_type: str = Field(
        default="basic",
        sa_column=Column(String(64), nullable=False, default="basic"),
    )
    award_type: str = Field(
        default="",
        sa_column=Column(String(64), nullable=False, default=""),
    )
    award_level: str = Field(
        default="",
        sa_column=Column(String(64), nullable=False, default=""),
    )
    award_uid: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    description: str = Field(sa_column=Column(Text, nullable=False))
    occurred_at: date = Field(sa_column=Column(Date, nullable=False))

    attachments_json: str = Field(default="[]", sa_column=Column(Text, nullable=False, default="[]"))

    status: str = Field(default="pending_review", sa_column=Column(String(32), nullable=False, default="pending_review", index=True))
    score: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    score_rule_version: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))

    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, default=1))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    deleted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    @property
    def attachments(self) -> list[dict]:
        try:
            value = json.loads(self.attachments_json or "[]")
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    def set_attachments(self, value: list[dict]) -> None:
        self.attachments_json = json.dumps(value, ensure_ascii=False)
