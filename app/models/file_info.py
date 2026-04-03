from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class FileInfo(SQLModel, table=True):
    __tablename__ = "file_info"

    id: str = Field(sa_column=Column(String(128), primary_key=True, index=True))
    uploader_id: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("user_info.id"), nullable=True))
    original_name: str = Field(sa_column=Column(String(255), nullable=False))
    storage_path: str = Field(sa_column=Column(String(512), nullable=False))
    content_type: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    size: int = Field(sa_column=Column(Integer, nullable=False))
    md5: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    status: str = Field(sa_column=Column(String(20), nullable=False, default="active"))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
