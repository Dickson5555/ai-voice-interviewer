
from pydantic import BaseModel, Field, field_validator


class InterviewResponse(BaseModel):
    """Shape of every response the interviewer agent returns."""

    reaction: str = Field(
        ..., min_length=1, max_length=300,
        description="Short natural reaction to the candidate's last answer."
    )
    feedback: str = Field(
        ..., min_length=1, max_length=500,
        description="Short, constructive feedback on the answer."
    )
    score: int = Field(
        ..., ge=0, le=10,
        description="Score for the answer, 0-10."
    )
    next_question: str = Field(
        ..., min_length=1, max_length=500,
        description="The next interview question to ask."
    )

    @field_validator("score", mode="before")
    @classmethod
    def coerce_score(cls, v):
        # LLMs sometimes return "8/10" or "8.0" - be forgiving.
        if isinstance(v, str):
            v = v.split("/")[0].strip()
            try:
                v = float(v)
            except ValueError:
                return 0
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return 0