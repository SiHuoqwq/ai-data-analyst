from typing import Literal

from pydantic import Field

from app.v2.schemas.api import APIModel


AllowedRecommendationIntent = Literal["group_comparison", "monthly_trend"]


class RecommendationCandidate(APIModel):
    """A bounded model selection; free text is legacy input and never public."""

    intent_type: AllowedRecommendationIntent
    referenced_fields: list[str] = Field(min_length=1, max_length=12)
    label: str | None = Field(default=None, min_length=1, max_length=60)
    question: str | None = Field(default=None, min_length=1, max_length=1000)
    detect_underperforming: bool = False


class RecommendationGeneration(APIModel):
    candidates: list[RecommendationCandidate] = Field(max_length=6)


class RecommendationEnvelope(APIModel):
    """Strict outer Provider envelope with independently parsed items."""

    candidates: list[object] = Field(max_length=6)
