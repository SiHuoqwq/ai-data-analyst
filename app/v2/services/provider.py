import json
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from app.db.models import FileModel
from app.v2.schemas.analysis import (
    ModelPlanDraft,
    PlanStepDraft,
    model_tool_catalog,
)
from app.v2.schemas.intents import DomainIntent
from app.v2.schemas.conclusions import (
    ConclusionFinding,
    ConclusionRecommendation,
    StructuredConclusion,
)
from app.v2.services.evidence import (
    ConclusionEvidenceError,
    EvidenceAliasMap,
    EvidenceRegistry,
)
from app.v2.services.structured_response import (
    StructuredResponseError,
    StructuredResponseParser,
)
from app.v2.services.structured_diagnostics import (
    diagnose_structured_response,
)


DOMAIN_INTENT_ADAPTER = TypeAdapter(DomainIntent)
DOMAIN_INTENT_EXAMPLES = [
    {
        "workflow": "group_comparison",
        "dimensions": [
            "course_category",
            "course_difficulty",
            "purchase_channel",
            "primary_device",
        ],
        "metric_ids": [
            "enrollment_count",
            "completion_rate",
            "refund_rate",
            "rating",
        ],
        "detect_underperforming": True,
    },
    {
        "workflow": "monthly_trend",
        "series_dimension": "course_category",
        "metric_ids": [
            "enrollment_count",
            "paid_amount",
            "completion_rate",
        ],
    },
]


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        user_message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class ProviderStep:
    step_id: str
    operation: str
    display_name: str
    arguments: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderPlan:
    goal: str
    steps: tuple[ProviderStep, ...]


class AnalysisProvider(Protocol):
    name: str
    model: str

    def set_history(self, history: list[dict[str, str]]) -> None: ...

    def build_plan(self, question: str, file_record: FileModel) -> ProviderPlan: ...

    def before_step(self) -> None: ...

    def repair_step(
        self,
        question: str,
        file_record: FileModel,
        failed_step: dict[str, Any],
        error: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> ProviderStep | None: ...

    def build_answer(
        self,
        question: str,
        file_record: FileModel,
        evidence: list[dict[str, Any]],
    ) -> str: ...

    def build_conclusion(
        self,
        question: str,
        file_record: FileModel,
        registry: EvidenceRegistry,
    ) -> StructuredConclusion: ...


class FakeAnalysisProvider:
    name = "fake"
    model = "deterministic-v1"

    def __init__(self, step_delay_seconds: float = 0):
        self.step_delay_seconds = step_delay_seconds
        self.history: list[dict[str, str]] = []
        self.last_conclusion_aliases: EvidenceAliasMap | None = None
        self.last_conclusion_mode = "model"
        self.last_conclusion_diagnostics: list[dict[str, Any]] = []
        self.last_intent_mode = "model"
        self.last_intent_diagnostics: list[dict[str, Any]] = []
        self._last_finish_reason: str | None = None

    def set_history(self, history: list[dict[str, str]]) -> None:
        self.history = history

    def build_plan(self, question: str, file_record: FileModel) -> ProviderPlan:
        if question == "[fake:fail]":
            raise RuntimeError("controlled fake provider failure")
        return ProviderPlan(
            goal=f"检查 {file_record.filename} 并生成可验证的数据摘要",
            steps=(
                ProviderStep(
                    "inspect_dataset", "inspect_dataset", "检查数据概况", None
                ),
                ProviderStep(
                    "create_chart", "create_visualization", "生成概览图表", None
                ),
            ),
        )

    def before_step(self) -> None:
        if self.step_delay_seconds:
            time.sleep(self.step_delay_seconds)

    def repair_step(
        self,
        question: str,
        file_record: FileModel,
        failed_step: dict[str, Any],
        error: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> ProviderStep | None:
        return None

    def build_answer(
        self,
        question: str,
        file_record: FileModel,
        evidence: list[dict[str, Any]],
    ) -> str:
        artifact_ids = [
            item.get("artifact_id", "")
            if isinstance(item, dict)
            else str(item)
            for item in evidence
        ]
        references = "、".join(f"`{artifact_id}`" for artifact_id in artifact_ids)
        return (
            f"已完成对 **{file_record.filename}** 的确定性数据概览。"
            f"结论与展示内容来自结构化产物：{references}。"
        )

    def build_conclusion(
        self,
        question: str,
        file_record: FileModel,
        registry: EvidenceRegistry,
    ) -> StructuredConclusion:
        if not registry.items:
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "本次分析没有可用于生成结论的结构化证据",
            )
        aliases = registry.create_alias_map(
            registry.items[: min(3, len(registry.items))]
        )
        self.last_conclusion_aliases = aliases
        primary = [entry.alias for entry in aliases.entries]
        return StructuredConclusion(
            headline="数据概览结论",
            overview="本次结论由已完成的确定性分析步骤生成。",
            findings=[
                ConclusionFinding(
                    title="关键数据已完成核验",
                    statement="当前数据集的主要结构化结果已生成。",
                    evidence_refs=primary,
                )
            ],
            recommendations=[
                ConclusionRecommendation(
                    action="结合结构化结果继续检查重点分组",
                    reason="当前证据可作为后续分析的可靠起点",
                    evidence_refs=primary,
                )
            ],
            limitations=["测试分析模式不读取历史回答作为计算输入。"],
        )


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        max_tool_rounds: int,
        max_prompt_chars: int,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_tool_rounds = max_tool_rounds
        self.max_prompt_chars = max_prompt_chars
        self.history: list[dict[str, str]] = []
        self._cancel_check: Callable[[], bool] | None = None
        self._structured_parser = StructuredResponseParser()
        self._client = client
        self._owns_client = client is None
        self.last_conclusion_aliases: EvidenceAliasMap | None = None
        self.last_conclusion_mode = "model"
        self.last_conclusion_diagnostics: list[dict[str, Any]] = []

    def set_history(self, history: list[dict[str, str]]) -> None:
        self.history = self._limited_history(history)

    def set_cancel_check(
        self, cancel_check: Callable[[], bool] | None
    ) -> None:
        self._cancel_check = cancel_check

    def build_plan(
        self,
        question: str,
        file_record: FileModel,
        history: list[dict[str, str]] | None = None,
    ) -> ProviderPlan:
        if history is not None:
            self.set_history(history)
        self._require_config()
        profile = self._safe_dataset_profile(file_record)
        payload = {
            "question": question[:4000],
            "dataset": profile,
            "recent_history": self.history,
            "allowed_tools": model_tool_catalog(),
            "rules": [
                "只调用 allowed_tools 中的只读工具",
                "不得生成 Python、SQL、文件路径或 dataset id",
                "先 inspect_dataset，再执行问题所需统计和图表",
                "create_chart 的 source_step_id 必须引用前面的表格步骤",
                f"步骤总数不得超过 {self.max_tool_rounds}",
            ],
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是数据分析规划器。只返回一个 JSON 对象，字段为 "
                        "goal 和 steps；每个 step 包含 id、tool、purpose、arguments。"
                        "关键数字必须由工具计算，不能猜测。"
                    ),
                },
                {
                    "role": "user",
                    "content": self._bounded_json(payload),
                },
            ],
            temperature=0,
        )
        try:
            draft = self._validate_plan_response(content)
        except (StructuredResponseError, ValidationError) as initial_error:
            self._raise_if_cancelled()
            repaired = self._repair_plan_response(content, initial_error)
            try:
                draft = self._validate_plan_response(repaired)
            except (StructuredResponseError, ValidationError) as exc:
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "分析服务返回了无法执行的计划",
                    retryable=False,
                ) from exc
        if len(draft.steps) > self.max_tool_rounds:
            raise ProviderError(
                "TOOL_ROUND_LIMIT_EXCEEDED",
                "分析计划超过允许的工具步骤数量",
                retryable=False,
            )
        return ProviderPlan(
            goal=draft.goal,
            steps=tuple(
                ProviderStep(
                    step_id=step.id,
                    operation=step.tool,
                    display_name=step.purpose,
                    arguments=step.arguments,
                )
                for step in draft.steps
            ),
        )

    def generate_intent(
        self,
        question: str,
        file_record: FileModel,
        history: list[dict[str, str]] | None = None,
    ) -> DomainIntent:
        if history is not None:
            self.set_history(history)
        self._require_config()
        self.last_intent_mode = "model"
        self.last_intent_diagnostics = []
        payload = {
            "question": question[:4000],
            "dataset": self._safe_dataset_profile(file_record),
            "recent_history": self.history,
            "intent_schema": DOMAIN_INTENT_ADAPTER.json_schema(),
            "valid_json_examples": DOMAIN_INTENT_EXAMPLES,
            "rules": [
                "当前领域仅限在线学习运营",
                "只返回一个 JSON 对象，不要使用 Markdown 代码块",
                "不要解释原因，不要添加未定义字段",
                "只能使用 Schema 列出的工作流、维度 ID 和指标 ID",
                "只识别分析意图，不计算数字",
                "执行流程和可视化由后端决定",
            ],
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是在线学习运营分析意图识别器。"
                        "只返回符合给定 Schema 的 JSON 对象。"
                    ),
                },
                {
                    "role": "user",
                    "content": self._bounded_json(payload),
                },
            ],
            temperature=0,
            json_output=True,
            max_tokens=1000,
        )
        try:
            intent = self._validate_intent_response(content)
            self.last_intent_diagnostics.append(
                diagnose_structured_response(
                    content,
                    finish_reason=self._last_finish_reason,
                    request_stage="initial",
                    error=None,
                    intent_mode="model",
                )
            )
            return intent
        except (StructuredResponseError, ValidationError) as initial_error:
            self.last_intent_diagnostics.append(
                diagnose_structured_response(
                    content,
                    finish_reason=self._last_finish_reason,
                    request_stage="initial",
                    error=initial_error,
                )
            )
            self._raise_if_cancelled()
            repaired = self._repair_intent_response(
                content,
                initial_error,
            )
            try:
                intent = self._validate_intent_response(repaired)
                self.last_intent_mode = "repaired_model"
                self.last_intent_diagnostics.append(
                    diagnose_structured_response(
                        repaired,
                        finish_reason=self._last_finish_reason,
                        request_stage="repair",
                        error=None,
                        intent_mode="repaired_model",
                    )
                )
                return intent
            except (StructuredResponseError, ValidationError) as exc:
                self.last_intent_diagnostics.append(
                    diagnose_structured_response(
                        repaired,
                        finish_reason=self._last_finish_reason,
                        request_stage="repair",
                        error=exc,
                    )
                )
                raise ProviderError(
                    "INTENT_REPAIR_FAILED",
                    "分析服务返回了无法执行的分析意图",
                    retryable=False,
                    details={
                        "intent_diagnostics": self.last_intent_diagnostics,
                    },
                ) from exc

    def _validate_intent_response(self, content: str) -> DomainIntent:
        return DOMAIN_INTENT_ADAPTER.validate_python(
            self._structured_parser.parse_object(content)
        )

    def _repair_intent_response(
        self,
        content: str,
        error: StructuredResponseError | ValidationError,
    ) -> str:
        payload = {
            "validation_issues": self._validation_issues(error),
            "response_diagnostic": self.last_intent_diagnostics[-1],
            "intent_schema": DOMAIN_INTENT_ADAPTER.json_schema(),
            "valid_json_examples": DOMAIN_INTENT_EXAMPLES,
            "rules": [
                "仅返回一个完整 JSON 对象，不要使用 Markdown",
                "只能使用 Schema 定义的字段和逻辑 ID",
                "不要解释、计算或添加额外字段",
            ],
        }
        return self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "修复在线学习运营分析意图的结构。"
                        "仅返回符合 Schema 的 JSON 对象。"
                    ),
                },
                {
                    "role": "user",
                    "content": self._bounded_json(payload),
                },
            ],
            temperature=0,
            json_output=True,
            max_tokens=1000,
        )

    def _validate_plan_response(self, content: str) -> ModelPlanDraft:
        return ModelPlanDraft.model_validate(
            self._structured_parser.parse_object(content)
        )

    def _repair_plan_response(
        self,
        content: str,
        error: StructuredResponseError | ValidationError,
    ) -> str:
        payload = {
            "invalid_response_excerpt": self._safe_response_excerpt(content),
            "validation_issues": self._validation_issues(error),
            "allowed_tools": model_tool_catalog(),
            "plan_schema": ModelPlanDraft.model_json_schema(),
            "rules": [
                "仅返回一个完整 JSON 对象",
                "不得补写无法从现有响应确认的字段值",
                "工具名称和参数必须通过给定 Schema",
            ],
        }
        return self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "修复分析计划的结构，不执行计划。"
                        "仅返回一个符合 Schema 的 JSON 对象。"
                    ),
                },
                {"role": "user", "content": self._bounded_json(payload)},
            ],
            temperature=0,
        )

    def _raise_if_cancelled(self) -> None:
        if self._cancel_check is not None and self._cancel_check():
            raise ProviderError(
                "RUN_CANCELLED",
                "分析任务已取消",
                retryable=False,
            )

    def _safe_response_excerpt(self, content: str) -> str:
        excerpt = content[:2000]
        excerpt = re.sub(
            r"(?i)\b[A-Z]:[\\/][^\s\"']+",
            "[redacted-path]",
            excerpt,
        )
        excerpt = re.sub(
            r"(?i)\bhttps?://[^\s\"']+",
            "[redacted-url]",
            excerpt,
        )
        if self.api_key:
            excerpt = excerpt.replace(self.api_key, "[redacted]")
        return excerpt

    @staticmethod
    def _validation_issues(
        error: StructuredResponseError | ValidationError,
    ) -> list[dict[str, Any]]:
        if isinstance(error, ValidationError):
            return [
                {
                    "location": list(item["loc"]),
                    "type": item["type"],
                }
                for item in error.errors(
                    include_url=False,
                    include_input=False,
                    include_context=False,
                )
            ]
        return [{"location": [], "type": "invalid_json_object"}]

    def before_step(self) -> None:
        return None

    def repair_step(
        self,
        question: str,
        file_record: FileModel,
        failed_step: dict[str, Any],
        error: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> ProviderStep:
        self._require_config()
        payload = {
            "question": question[:4000],
            "dataset": self._safe_dataset_profile(file_record),
            "failed_step": failed_step,
            "tool_error": {
                "code": error.get("code"),
                "message": error.get("message"),
                "details": error.get("details", {}),
            },
            "prior_evidence": evidence[-10:],
            "allowed_tools": model_tool_catalog(),
            "rules": [
                "只返回一个修正后的 step JSON 对象",
                "只能使用可用字段和白名单工具",
                "不得返回 Python、SQL、文件路径或 dataset id",
            ],
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "修正失败的数据分析步骤。只返回包含 "
                        "id、tool、purpose、arguments 的 JSON 对象。"
                    ),
                },
                {"role": "user", "content": self._bounded_json(payload)},
            ],
            temperature=0,
        )
        try:
            draft = PlanStepDraft.model_validate(self._parse_json(content))
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "PROVIDER_INVALID_RESPONSE",
                "分析服务没有返回可执行的修正步骤",
                retryable=False,
            ) from exc
        return ProviderStep(
            step_id=draft.id,
            operation=draft.tool,
            display_name=draft.purpose,
            arguments=draft.arguments,
        )

    def build_answer(
        self,
        question: str,
        file_record: FileModel,
        evidence: list[dict[str, Any]],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if history is not None:
            self.set_history(history)
        self._require_config()
        limited_evidence = []
        for item in evidence[:20]:
            limited_evidence.append(
                {
                    "artifact_type": item.get("artifact_type"),
                    "title": item.get("title"),
                    "summary": item.get("summary", {}),
                    "preview": item.get("preview", [])[:20],
                    "warnings": item.get("warnings", []),
                }
            )
        payload = {
            "question": question[:4000],
            "dataset": self._safe_dataset_profile(file_record),
            "recent_history": self.history,
            "evidence": limited_evidence,
            "answer_rules": [
                "先给关键结论，再给数据依据、限制和运营建议",
                "只能引用 dataset、evidence 中直接出现的业务数字",
                "不要输出 artifact_id、内部 ID、URL 或其他技术标识符",
                "不要自行计算 evidence 未直接提供的差值、倍数或百分比",
                "每个比例数值都必须单独带 %，并保持一致格式",
                "所有数值使用阿拉伯数字，不使用中文数字或模糊数量词",
                "金额使用人民币格式，比例使用一致的百分比格式",
                "样本量不足或字段缺失时必须说明",
                "相关关系不能表述为因果关系",
            ],
        }
        answer = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的数据分析师。仅根据提供的结构化证据回答，"
                        "不得补充证据中不存在的统计数字。使用简洁中文 Markdown。"
                    ),
                },
                {"role": "user", "content": self._bounded_json(payload)},
            ],
            temperature=0.2,
        ).strip()
        if not answer:
            raise ProviderError(
                "PROVIDER_INVALID_RESPONSE",
                "分析服务没有返回最终结论",
                retryable=False,
            )
        unsupported_numbers = self._unsupported_numbers(
            answer,
            [{"dataset": payload["dataset"]}, *limited_evidence],
        )
        if unsupported_numbers:
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "分析结论包含无法由本次工具结果验证的数字",
                retryable=False,
                details={
                    "unsupported_numbers": unsupported_numbers[:10],
                },
            )
        return answer

    def build_conclusion(
        self,
        question: str,
        file_record: FileModel,
        registry: EvidenceRegistry,
    ) -> StructuredConclusion:
        self._require_config()
        self.last_conclusion_mode = "model"
        self.last_conclusion_diagnostics = []
        payload = {
            "question": question[:4000],
            "dataset": self._safe_dataset_profile(file_record),
            "conclusion_schema": StructuredConclusion.model_json_schema(),
            "rules": [
                "仅返回一个完整 JSON 对象",
                "所有业务数字只能通过 evidence_refs 引用，不得写入叙述字段",
                "每个 finding 和 recommendation 必须引用当前 evidence alias",
                "不得输出文件路径、URL、内部 ID 或服务器信息",
            ],
        }
        aliases = self._bounded_alias_map(
            payload,
            registry,
        )
        self.last_conclusion_aliases = aliases
        payload["evidence_registry"] = aliases.prompt_payload()
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的数据分析师。根据证据注册表返回结构化结论，"
                        "只返回符合 Schema 的 JSON 对象。"
                    ),
                },
                {"role": "user", "content": self._bounded_json(payload)},
            ],
            temperature=0.2,
        )
        try:
            return self._validate_conclusion_response(content, aliases)
        except (
            StructuredResponseError,
            ValidationError,
            ConclusionEvidenceError,
        ) as initial_error:
            self.last_conclusion_diagnostics.append(
                self._conclusion_diagnostic(
                    "initial",
                    content,
                    initial_error,
                )
            )
            self._raise_if_cancelled()
            repaired, repair_aliases = self._repair_conclusion_response(
                content, initial_error, registry
            )
            self.last_conclusion_aliases = repair_aliases
            try:
                conclusion = self._validate_conclusion_response(
                    repaired,
                    repair_aliases,
                )
                self.last_conclusion_mode = "repaired_model"
                return conclusion
            except (
                StructuredResponseError,
                ValidationError,
                ConclusionEvidenceError,
            ) as exc:
                repair_diagnostic = self._conclusion_diagnostic(
                    "repair",
                    repaired,
                    exc,
                )
                repair_diagnostic["error_types"] = sorted(
                    {
                        *repair_diagnostic["error_types"],
                        "RESPONSE_REPAIR_FAILED",
                    }
                )
                self.last_conclusion_diagnostics.append(repair_diagnostic)
                raise ProviderError(
                    "UNGROUNDED_ANSWER",
                    "分析服务返回的结论无法由本次结构化证据验证",
                    retryable=False,
                    details={
                        "conclusion_diagnostics": (
                            self.last_conclusion_diagnostics
                        ),
                        "answer_warnings": [
                            "STRUCTURED_CONCLUSION_REJECTED",
                            "STRUCTURED_CONCLUSION_REPAIR_FAILED",
                        ],
                    },
                ) from exc

    def _validate_conclusion_response(
        self,
        content: str,
        aliases: EvidenceAliasMap,
    ) -> StructuredConclusion:
        conclusion = StructuredConclusion.model_validate(
            self._structured_parser.parse_object(content)
        )
        return aliases.validate_conclusion(conclusion)

    def _repair_conclusion_response(
        self,
        content: str,
        error: (
            StructuredResponseError
            | ValidationError
            | ConclusionEvidenceError
        ),
        registry: EvidenceRegistry,
    ) -> tuple[str, EvidenceAliasMap]:
        issues = (
            self._validation_issues(error)
            if isinstance(error, (StructuredResponseError, ValidationError))
            else [{"location": ["evidence_refs"], "type": error.code}]
        )
        payload = {
            "invalid_response_excerpt": self._safe_response_excerpt(content),
            "validation_issues": issues,
            "conclusion_schema": StructuredConclusion.model_json_schema(),
            "rules": [
                "仅返回一个完整 JSON 对象",
                "叙述字段不得包含数字",
                "只能引用给定 evidence alias",
            ],
        }
        repair_aliases = self._bounded_alias_map(payload, registry)
        payload["evidence_registry"] = repair_aliases.prompt_payload()
        repaired = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "修复结构化分析结论，不重新执行分析。"
                        "只返回符合 Schema 的 JSON 对象。"
                    ),
                },
                {"role": "user", "content": self._bounded_json(payload)},
            ],
            temperature=0,
        )
        return repaired, repair_aliases

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _require_config(self) -> None:
        if not self.api_key:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "真实分析服务尚未配置 API Key",
                retryable=False,
            )

    def _client_instance(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_seconds,
            )
        return self._client

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_output: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if json_output:
            body["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        self._last_finish_reason = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client_instance().post(
                    "/v1/chat/completions", json=body
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self.max_retries:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise ProviderError(
                    "PROVIDER_TIMEOUT",
                    "分析服务连接超时，请稍后重试",
                    retryable=True,
                ) from exc
            if response.status_code in {401, 403}:
                raise ProviderError(
                    "PROVIDER_AUTH_FAILED",
                    "真实分析服务鉴权失败，请检查配置",
                    retryable=False,
                )
            if response.status_code == 429:
                if attempt < self.max_retries:
                    self._limited_backoff(response, attempt)
                    continue
                raise ProviderError(
                    "PROVIDER_RATE_LIMITED",
                    "真实分析服务当前请求过多，请稍后重试",
                    retryable=True,
                )
            if response.status_code >= 500:
                if attempt < self.max_retries:
                    self._limited_backoff(response, attempt)
                    continue
                raise ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "真实分析服务暂时不可用，请稍后重试",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise ProviderError(
                    "PROVIDER_REQUEST_REJECTED",
                    "真实分析服务拒绝了当前请求",
                    retryable=False,
                )
            try:
                data = response.json()
                choice = data["choices"][0]
                self._last_finish_reason = choice.get("finish_reason")
                return str(choice["message"].get("content") or "")
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "分析服务返回了无法识别的结果",
                    retryable=False,
                ) from exc
        raise AssertionError("unreachable")

    def _limited_backoff(self, response: httpx.Response, attempt: int) -> None:
        retry_after = response.headers.get("Retry-After")
        try:
            seconds = min(float(retry_after), 1.0) if retry_after else 0.1
        except ValueError:
            seconds = 0.1
        time.sleep(seconds * (attempt + 1))

    def _safe_dataset_profile(self, file_record: FileModel) -> dict[str, Any]:
        fields = []
        for item in (file_record.columns_info or []):
            fields.append(
                {
                    "name": str(item.get("name", ""))[:256],
                    "dtype": str(item.get("dtype", ""))[:100],
                    "null_count": item.get("null_count"),
                    "null_rate": item.get("null_rate"),
                    "unique_count": item.get("unique_count"),
                }
            )
        return {
            "filename": file_record.filename,
            "row_count": file_record.row_count,
            "column_count": file_record.col_count,
            "fields": fields,
        }

    def _limited_history(
        self, history: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        result = []
        remaining = min(self.max_prompt_chars // 3, 6000)
        for item in reversed(history[-10:]):
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            content = content[:remaining]
            result.append({"role": role, "content": content})
            remaining -= len(content)
            if remaining <= 0:
                break
        return list(reversed(result))

    def _bounded_json(self, payload: dict[str, Any]) -> str:
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(text) <= self.max_prompt_chars:
            return text
        reduced = dict(payload)
        reduced["recent_history"] = []
        text = json.dumps(reduced, ensure_ascii=False, allow_nan=False)
        if len(text) <= self.max_prompt_chars:
            return text
        raise ProviderError(
            "PROMPT_LIMIT_EXCEEDED",
            "分析请求超过当前上下文限制",
            retryable=False,
        )

    def _bounded_alias_map(
        self,
        base_payload: dict[str, Any],
        registry: EvidenceRegistry,
    ) -> EvidenceAliasMap:
        groups: dict[str, list[Any]] = {}
        for item in registry.items:
            groups.setdefault(item.source_artifact_id, []).append(item)

        ordered = []
        index = 0
        while True:
            added = False
            for group in groups.values():
                if index < len(group):
                    ordered.append(group[index])
                    added = True
            if not added:
                break
            index += 1

        selected = []
        for item in ordered:
            candidate_items = [*selected, item]
            candidate = registry.create_alias_map(candidate_items)
            payload = {
                **base_payload,
                "evidence_registry": candidate.prompt_payload(),
            }
            text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            if len(text) > self.max_prompt_chars:
                break
            selected = candidate_items

        if not selected:
            raise ProviderError(
                "PROMPT_LIMIT_EXCEEDED",
                "分析请求超过当前上下文限制",
                retryable=False,
            )
        return registry.create_alias_map(selected)

    @staticmethod
    def _conclusion_diagnostic(
        phase: str,
        content: str,
        error: (
            StructuredResponseError
            | ValidationError
            | ConclusionEvidenceError
        ),
    ) -> dict[str, Any]:
        error_types: set[str] = set()
        field_paths: set[str] = set()
        unknown_reference_count = 0
        narrative_number_token_count = 0

        if isinstance(error, StructuredResponseError):
            error_types.add("INVALID_JSON")
        elif isinstance(error, ConclusionEvidenceError):
            error_types.add(error.code)
            unknown_reference_count = error.unknown_count
        else:
            for item in error.errors(
                include_url=False,
                include_input=False,
                include_context=False,
            ):
                location = ".".join(str(part) for part in item["loc"])
                if location:
                    field_paths.add(location)
                issue_type = item["type"]
                if issue_type == "missing":
                    error_types.add("MISSING_REQUIRED_FIELD")
                elif issue_type == "extra_forbidden":
                    error_types.add("EXTRA_FIELD")
                elif (
                    item["loc"] == ("findings",)
                    and issue_type in {"too_short", "list_too_short"}
                ):
                    error_types.add("EMPTY_FINDINGS")
                elif (
                    "evidence_refs" in item["loc"]
                    and issue_type in {"too_short", "list_too_short"}
                ):
                    error_types.add(
                        "FINDING_WITHOUT_EVIDENCE"
                        if item["loc"][0] == "findings"
                        else "RECOMMENDATION_WITHOUT_EVIDENCE"
                    )
                elif (
                    issue_type == "value_error"
                    and item["loc"]
                    and item["loc"][-1]
                    in {
                        "headline",
                        "overview",
                        "title",
                        "statement",
                        "action",
                        "reason",
                        "limitations",
                    }
                ):
                    error_types.add("NUMBER_IN_NARRATIVE")
                else:
                    error_types.add("INVALID_FIELD_TYPE")
            if "NUMBER_IN_NARRATIVE" in error_types:
                narrative_values: list[str] = []
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    parsed = {}

                def collect_narrative(value: Any) -> None:
                    if isinstance(value, dict):
                        for key, nested in value.items():
                            if key in {
                                "headline",
                                "overview",
                                "title",
                                "statement",
                                "action",
                                "reason",
                                "limitations",
                            }:
                                collect_narrative(nested)
                    elif isinstance(value, list):
                        for nested in value:
                            collect_narrative(nested)
                    elif isinstance(value, str):
                        narrative_values.append(value)

                collect_narrative(parsed)
                narrative_number_token_count = sum(
                    len(re.findall(r"\d+", value))
                    for value in narrative_values
                )

        return {
            "phase": phase,
            "error_types": sorted(error_types),
            "field_paths": sorted(field_paths),
            "error_count": (
                len(error.errors()) if isinstance(error, ValidationError) else 1
            ),
            "unknown_reference_count": unknown_reference_count,
            "narrative_number_token_count": narrative_number_token_count,
            "response_length": len(content),
            "response_sha256": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
        }

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                stripped = "\n".join(lines[1:-1])
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError("response must be an object")
        return value

    @classmethod
    def _numbers_are_grounded(
        cls, answer: str, evidence: list[dict[str, Any]]
    ) -> bool:
        return not cls._unsupported_numbers(answer, evidence)

    @classmethod
    def _unsupported_numbers(
        cls, answer: str, evidence: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        pattern = re.compile(
            r"(?<![A-Za-z0-9_-])-?\d+(?:,\d{3})*(?:\.\d+)?"
        )
        rate_markers = (
            "率",
            "比例",
            "percent",
            "rate",
            "completion",
            "refund",
            "quantile",
            "分位",
        )
        amount_markers = (
            "金额",
            "销售额",
            "收入",
            "成本",
            "价格",
            "amount",
            "sales",
            "revenue",
            "cost",
            "price",
        )
        ignored_keys = {"artifact_id", "title"}
        allowed_artifact_ids: set[str] = set()
        allowed: list[float] = []
        allowed_rates: list[float] = []
        allowed_amounts: list[float] = []
        unsupported: list[dict[str, str]] = []

        def collect_artifact_ids(value: Any) -> None:
            if isinstance(value, dict):
                artifact_id = value.get("artifact_id")
                if isinstance(artifact_id, str) and artifact_id:
                    allowed_artifact_ids.add(artifact_id)
                for nested in value.values():
                    collect_artifact_ids(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_artifact_ids(nested)

        def add_number(number: float, semantic_key: str) -> None:
            allowed.append(number)
            normalized_key = semantic_key.lower()
            if any(marker in normalized_key for marker in rate_markers):
                allowed_rates.append(number)
                if -1 <= number <= 1:
                    allowed_rates.append(number * 100)
            if any(marker in normalized_key for marker in amount_markers):
                allowed_amounts.append(number)

        def collect(value: Any, semantic_key: str = "") -> None:
            if isinstance(value, bool) or value is None:
                return
            if isinstance(value, (int, float)):
                add_number(float(value), semantic_key)
                return
            if isinstance(value, str):
                for match in pattern.findall(value):
                    add_number(float(match.replace(",", "")), semantic_key)
                return
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key in ignored_keys:
                        continue
                    collect(nested, str(key))
                return
            if isinstance(value, list):
                for nested in value:
                    collect(nested, semantic_key)

        collect_artifact_ids(evidence)
        collect(evidence)
        scan_answer = answer
        for artifact_id in sorted(
            allowed_artifact_ids, key=len, reverse=True
        ):
            scan_answer = scan_answer.replace(
                artifact_id, " " * len(artifact_id)
            )
        for match in pattern.finditer(scan_answer):
            token = match.group(0).replace(",", "")
            number = float(token)
            decimal_places = (
                len(token.rsplit(".", 1)[1]) if "." in token else 0
            )
            display_tolerance = 0.5 * (10 ** -decimal_places) + 1e-9
            following = scan_answer[match.end() : match.end() + 2]
            line_start = scan_answer.rfind("\n", 0, match.start()) + 1
            line_prefix = scan_answer[line_start : match.start()].strip()
            if (
                line_prefix in {"", "-", "*"}
                and following[:1] in {".", "、", ")", "）"}
            ):
                continue
            raw_context = scan_answer[
                max(0, match.start() - 16) : match.start()
            ].lower()
            context = re.split(
                r"[。！？!?；;，,|/\\\r\n]", raw_context
            )[-1]
            if following.lstrip().startswith("%"):
                candidates = allowed_rates
                semantic_category = "rate"
            elif (
                "￥"
                in scan_answer[max(0, match.start() - 2) : match.start()]
                or "¥"
                in scan_answer[max(0, match.start() - 2) : match.start()]
                or following.lstrip().startswith("元")
            ):
                candidates = allowed_amounts
                semantic_category = "amount"
            elif any(marker in context for marker in rate_markers):
                candidates = allowed_rates
                semantic_category = "rate"
            elif any(marker in context for marker in amount_markers):
                candidates = allowed_amounts
                semantic_category = "amount"
            else:
                candidates = allowed
                semantic_category = "general"
            if not any(
                abs(number - candidate)
                <= max(1e-6, display_tolerance)
                for candidate in candidates
            ):
                unsupported.append(
                    {
                        "token": match.group(0),
                        "semantic_category": semantic_category,
                    }
                )
        return unsupported
