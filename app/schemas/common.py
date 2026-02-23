from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: dict = Field(default_factory=dict)
    request_id: str | None = None
