from pydantic import BaseModel, Field


class SystemConfigUpdateRequest(BaseModel):
    config_key: str = Field(min_length=1, max_length=100)
    config_value: dict = Field(default_factory=dict)
    description: str | None = None


class AwardDictCreateRequest(BaseModel):
    award_uid: int = Field(gt=0)
    category: str | None = Field(default=None, max_length=32)
    sub_type: str | None = Field(default=None, max_length=64)
    award_name: str = Field(min_length=1, max_length=255)
    score: float = Field(ge=0)
    max_score: float = Field(ge=0)


class AwardDictUpdateRequest(BaseModel):
    category: str | None = Field(default=None, max_length=32)
    sub_type: str | None = Field(default=None, max_length=64)
    award_name: str | None = Field(default=None, max_length=255)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
