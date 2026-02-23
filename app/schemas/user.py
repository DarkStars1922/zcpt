from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    id: int
    name: str
    role: str
    class_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
