from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserInfo


class RegisterRequest(BaseModel):
    account: str = Field(min_length=4, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    role: str = Field(default="student")
    is_auth: bool = Field(default=False)
    class_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = None


class LoginRequest(BaseModel):
    account: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    user: UserInfo
    access_token: str
    refresh_token: str
    expires_in: int


class RegisterData(BaseModel):
    user: UserInfo


class RefreshData(BaseModel):
    access_token: str
    expires_in: int
