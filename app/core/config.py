from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "综合测评平台"
    secret_key: str = "crying—1385432-shr124567755"
    algorithm: str = "HS256"
    access_token_expire_seconds: int = 7200
    refresh_token_expire_seconds: int = 604800
    database_url: str = "sqlite:///./platform.db"
    upload_dir: str = "./uploads"
    upload_max_file_size: int = 10485760
    ai_audit_enabled: bool = False


settings = Settings()
