from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class AIAuditReport(SQLModel, table=True):
    __tablename__ = "ai_audit_report"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    application_id: int = Field(
        sa_column=Column(Integer, ForeignKey("comprehensive_apply.id", ondelete="CASCADE"), unique=True, nullable=False)
    )
    provider: str = Field(sa_column=Column(String(50), nullable=False, default="mock"))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="queued", index=True))
    result: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    ocr_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    identity_check_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    consistency_check_json: str = Field(sa_column=Column(Text, nullable=False, default="{}"))
    risk_points_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    score_breakdown_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    item_score: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    total_score: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    audited_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
