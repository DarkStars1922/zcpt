from pydantic import BaseModel, Field, model_validator

from app.core.score_rules import is_valid_score_category


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

    @model_validator(mode="after")
    def validate_score_category(self):
        if (self.category is not None or self.sub_type is not None) and not is_valid_score_category(self.category, self.sub_type):
            raise ValueError("category/sub_type must be one of the configured score categories")
        return self


class AwardDictUpdateRequest(BaseModel):
    category: str | None = Field(default=None, max_length=32)
    sub_type: str | None = Field(default=None, max_length=64)
    award_name: str | None = Field(default=None, max_length=255)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_score_category(self):
        if self.category is not None and self.sub_type is not None and not is_valid_score_category(self.category, self.sub_type):
            raise ValueError("category/sub_type must be one of the configured score categories")
        return self
