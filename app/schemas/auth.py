from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    account: str = Field(min_length=4, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    role: str = Field(default="student")
    class_id: int | None = None
    is_reviewer: bool | None = False
    reviewer_token: str | None = Field(default=None, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)
