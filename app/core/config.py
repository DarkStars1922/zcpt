from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "综合测评平台"
    environment: str = "local"

    secret_key: str = "crying-1385432-shr124567755"
    algorithm: str = "HS256"
    access_token_expire_seconds: int = 7200
    refresh_token_expire_seconds: int = 604800

    database_url: str = "sqlite:///./platform.db"
    sql_echo: bool = False
    auto_create_tables: bool = True

    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_enabled: bool = True
    access_token_blacklist_prefix: str = "auth:blacklist:"
    idempotency_prefix: str = "idempotency:"
    cache_prefix: str = "cache:"
    export_status_prefix: str = "export:"

    celery_task_always_eager: bool = True
    celery_task_eager_propagates: bool = True
    celery_result_expires_seconds: int = 86400

    upload_dir: str = "./uploads"
    export_dir: str = "./exports"
    upload_max_file_size: int = 10485760
    allowed_upload_content_types: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
        ]
    )

    email_provider: str = "mock"
    email_default_from: str = "noreply@zcpt.local"
    email_mock_success: bool = True

    ai_audit_provider: str = "paddleocr"
    ai_audit_fallback_to_manual: bool = True
    file_analysis_enabled: bool = True
    paddle_model_source: str = "BOS"
    paddle_model_dir: str = "./models/paddleocr"
    paddleocr_device: str = "cpu"
    paddleocr_use_doc_orientation_classify: bool = True
    paddleocr_use_textline_orientation: bool = True
    paddleocr_text_detection_model_name: str = "PP-OCRv5_mobile_det"
    paddleocr_text_detection_model_dir: str | None = None
    paddleocr_text_recognition_model_name: str = "PP-OCRv5_mobile_rec"
    paddleocr_text_recognition_model_dir: str | None = None
    paddleocr_layout_detection_model_name: str = "PP-DocLayout-S"
    paddleocr_layout_detection_model_dir: str | None = None
    paddleocr_cpu_threads: int = 4
    paddleocr_enable_mkldnn: bool = True
    paddleocr_seal_score_threshold: float = 0.4

    default_term: str = "2025-2026-1"
    export_download_base_path: str = "/api/v1/teacher/exports"

    @property
    def upload_dir_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def export_dir_path(self) -> Path:
        return Path(self.export_dir)

    @property
    def paddle_model_dir_path(self) -> Path:
        return Path(self.paddle_model_dir)


settings = Settings()
