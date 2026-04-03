from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class AppealAttachment(SQLModel, table=True):
    __tablename__ = "appeal_attachment"

    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True, index=True))
    appeal_id: int = Field(
        sa_column=Column(Integer, ForeignKey("appeal_record.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    file_id: str = Field(
        sa_column=Column(String(128), ForeignKey("file_info.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
