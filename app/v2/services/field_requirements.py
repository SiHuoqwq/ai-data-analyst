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
    _teacher_question_terms = ("授课教师", "教师", "老师", "讲师")
    _teacher_field_terms = (
        "教师姓名",
        "教师id",
        "授课教师",
        "讲师",
        "教师评分",
    )

    def validate(
        self,
        question: str,
        columns_info: list[dict[str, Any]] | None,
    ) -> None:
        normalized_question = self._normalize(question)
        if not any(
            term in normalized_question
            for term in self._teacher_question_terms
        ):
            return

        normalized_columns = {
            self._normalize(str(item.get("name", "")))
            for item in (columns_info or [])
        }
        if any(
            any(term in column for term in self._teacher_field_terms)
            for column in normalized_columns
        ):
            return

        message = (
            "当前数据无法回答教师维度问题：缺少教师姓名、教师ID或授课教师字段。"
            "如需衡量授课质量，请同时补充教师评分或其他可验证的质量指标。"
        )
        raise MissingRequiredFieldsError(
            "MISSING_REQUIRED_FIELDS",
            message,
            retryable=False,
            details={
                "concept": "teacher",
                "required_fields": ["教师姓名", "教师ID", "授课教师"],
                "recommended_fields": ["教师评分"],
            },
        )

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[\s_\-]+", "", normalized)
