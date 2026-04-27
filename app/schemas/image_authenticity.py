from pydantic import BaseModel, Field


class ImageAuthenticityRequest(BaseModel):
    file_id: str = Field(min_length=1, max_length=128)
    run_c2pa: bool = True
    run_external: bool = True
