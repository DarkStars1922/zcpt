from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserInfo(BaseModel):
    id: int
    account: str
    name: str
    role: str
    class_id: int | None = None
    is_reviewer: bool = False
    reviewer_token_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
