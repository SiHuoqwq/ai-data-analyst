from typing import Literal

from pydantic import Field

from app.v2.schemas.api import APIModel


AllowedRecommendationIntent = Literal["group_comparison", "monthly_trend"]


class RecommendationCandidate(APIModel):
    intent_type: AllowedRecommendationIntent
    label: str = Field(min_length=1, max_length=60)
    question: str = Field(min_length=1, max_length=1000)
    referenced_fields: list[str] = Field(min_length=1, max_length=12)


class RecommendationGeneration(APIModel):
    candidates: list[RecommendationCandidate] = Field(max_length=2)
