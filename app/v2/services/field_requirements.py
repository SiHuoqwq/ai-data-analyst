import re
import unicodedata
from typing import Any


class MissingRequiredFieldsError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class RequiredFieldGuard:
    _dimension_guards = (
        {
            "concept": "sales_consultant",
            "label": "置业顾问",
            "question_terms": ("置业顾问", "销售顾问", "顾问"),
            "field_terms": ("置业顾问", "销售顾问", "顾问"),
        },
        {
            "concept": "project_name",
            "label": "项目",
            "question_terms": ("项目", "楼盘"),
            "field_terms": ("项目", "楼盘"),
        },
        {
            "concept": "lead_channel",
            "label": "获客渠道",
            "question_terms": ("获客渠道", "渠道", "客户来源", "线索来源"),
            "field_terms": ("获客渠道", "渠道", "客户来源", "线索来源"),
        },
        {
            "concept": "property_type",
            "label": "户型",
            "question_terms": ("户型", "房型"),
            "field_terms": ("户型", "房型"),
        },
    )

    def validate(
        self,
        question: str,
        columns_info: list[dict[str, Any]] | None,
    ) -> None:
        normalized_question = self._normalize(question)
        normalized_columns = {
            self._normalize(str(item.get("name", "")))
            for item in (columns_info or [])
        }
        for guard in self._dimension_guards:
            if not any(
                term in normalized_question
                for term in guard["question_terms"]
            ):
                continue
            if any(
                any(term in column for term in guard["field_terms"])
                for column in normalized_columns
            ):
                continue
            label = guard["label"]
            raise MissingRequiredFieldsError(
                "MISSING_REQUIRED_FIELDS",
                (
                    f"当前数据中缺少「{label}」字段，"
                    f"因此暂时无法进行{label}维度分析。"
                ),
                retryable=False,
                details={
                    "concept": guard["concept"],
                    "required_fields": [guard["field_terms"][0]],
                },
            )

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[\s_\-]+", "", normalized)
