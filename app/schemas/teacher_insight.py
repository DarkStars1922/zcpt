from pydantic import BaseModel, Field


class TeacherInsightAnalyzeRequest(BaseModel):
    grade: int | None = Field(default=None)
    class_id: int | None = Field(default=None)
    class_ids: list[int] = Field(default_factory=list)
    max_risk_students: int = Field(default=12, ge=3, le=30)
