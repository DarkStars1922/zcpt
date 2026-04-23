from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserInfo(BaseModel):
    id: int
    account: str
    name: str
    role: str
    class_id: int | None = None
    is_reviewer: bool = False
    reviewer_token_id: int | None = None
    email: str | None = None
    phone: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("email", "phone", mode="before")
    @classmethod
    def normalize_blank_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value
