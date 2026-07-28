import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictConclusionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _narrative_without_numbers(value: str) -> str:
    if re.search(r"\d", value):
        raise ValueError(
            "business numbers must be injected through evidence references"
        )
    return value


class ConclusionFinding(StrictConclusionModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    _title_without_numbers = field_validator("title")(
        _narrative_without_numbers
    )
    _statement_without_numbers = field_validator("statement")(
        _narrative_without_numbers
    )


class ConclusionRecommendation(StrictConclusionModel):
    action: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    _action_without_numbers = field_validator("action")(
        _narrative_without_numbers
    )
    _reason_without_numbers = field_validator("reason")(
        _narrative_without_numbers
    )


class StructuredConclusion(StrictConclusionModel):
    headline: str = Field(min_length=1, max_length=200)
    overview: str = Field(min_length=1, max_length=1000)
    findings: list[ConclusionFinding] = Field(min_length=1, max_length=10)
    recommendations: list[ConclusionRecommendation] = Field(
        default_factory=list, max_length=10
    )
    limitations: list[str] = Field(default_factory=list, max_length=20)

    _headline_without_numbers = field_validator("headline")(
        _narrative_without_numbers
    )
    _overview_without_numbers = field_validator("overview")(
        _narrative_without_numbers
    )
    _limitations_without_numbers = field_validator("limitations")(
        lambda values: [_narrative_without_numbers(item) for item in values]
    )
