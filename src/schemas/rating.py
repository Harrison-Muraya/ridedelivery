from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator, ConfigDict


class CreateRatingRequest(BaseModel):
    request_id: UUID
    ratee_id: UUID
    score: int
    comment: Optional[str] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if not (1 <= v <= 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    rater_id: UUID
    ratee_id: UUID
    score: int
    comment: Optional[str]
    created_at: datetime
