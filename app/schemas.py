from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class EventIn(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=36, max_length=36)
    event_type: Literal[
        "product_view",
        "product_click",
        "search",
        "category_view",
        "time_spent",
        "recommendation_impression",
        "recommendation_click",
    ]
    product_id: int | None = None
    search_query: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime | None = None


class EventBatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=100)


class RecommendationPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    narrative: str = Field(min_length=1, max_length=2000)
    items: list[dict[str, Any]] = Field(min_length=1, max_length=5)


class CareerStagePayload(BaseModel):
    phase: str = Field(min_length=1, max_length=100)
    duration: str = Field(min_length=1, max_length=60)
    goal: str = Field(min_length=1, max_length=500)
    skills: list[str] = Field(default_factory=list, max_length=10)
    course_ids: list[int] = Field(default_factory=list, max_length=5)
    project: str = Field(default="", max_length=500)
    certifications: list[str] = Field(default_factory=list, max_length=5)
    interview_prep: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("skills", "certifications", "interview_prep", mode="before")
    @classmethod
    def normalize_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value


class CareerPathPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1500)
    target_role: str = Field(min_length=1, max_length=150)
    estimated_months: int = Field(ge=1, le=60)
    hero_message: str = Field(min_length=1, max_length=300)
    stages: list[CareerStagePayload] = Field(min_length=3, max_length=8)
