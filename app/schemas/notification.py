from pydantic import BaseModel, EmailStr, Field


class RejectEmailRequest(BaseModel):
    application_id: int | None = None
    appeal_id: int | None = None
    to: EmailStr
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=4000)
