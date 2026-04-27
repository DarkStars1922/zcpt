from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

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


class AdminUserCreateRequest(BaseModel):
    account: str = Field(min_length=4, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    role: Literal["student", "teacher"]
    class_id: int | None = None
    is_reviewer: bool = False
    reviewer_token: str | None = Field(default=None, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_user_role_fields(self):
        if self.role == "student" and self.class_id is None:
            raise ValueError("student class_id is required")
        if self.role != "student":
            self.class_id = None
            self.is_reviewer = False
            self.reviewer_token = None
        if self.is_reviewer and not (self.reviewer_token or "").strip():
            raise ValueError("reviewer_token is required when is_reviewer is true")
        return self


class AdminUserUpdateRequest(BaseModel):
    account: str | None = Field(default=None, min_length=4, max_length=32)
    password: str | None = Field(default=None, min_length=6, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    role: Literal["student", "teacher"] | None = None
    class_id: int | None = None
    is_reviewer: bool | None = None
    reviewer_token: str | None = Field(default=None, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)


class ClassCreateRequest(BaseModel):
    class_id: int | None = Field(default=None, gt=0)
    grade: int = Field(ge=2000, le=2100)
    name: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class ClassUpdateRequest(BaseModel):
    grade: int | None = Field(default=None, ge=2000, le=2100)
    name: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
