import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.db.models import FileModel
from app.v2.schemas.analysis import (
    ModelPlanDraft,
    PlanStepDraft,
    model_tool_catalog,
)


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        user_message: str,
        retryable: bool = False,
    ):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable


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


class FakeAnalysisProvider:
    name = "fake"
    model = "deterministic-v1"

    def __init__(self, step_delay_seconds: float = 0):
        self.step_delay_seconds = step_delay_seconds
        self.history: list[dict[str, str]] = []

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
        self._client = client
        self._owns_client = client is None

    def set_history(self, history: list[dict[str, str]]) -> None:
        self.history = self._limited_history(history)

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
            draft = ModelPlanDraft.model_validate(self._parse_json(content))
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
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
                    "artifact_id": item.get("artifact_id"),
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
                "只能引用 evidence 中出现的数字和 artifact_id",
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
        if not self._numbers_are_grounded(answer, limited_evidence):
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "分析结论包含无法由本次工具结果验证的数字",
                retryable=False,
            )
        return answer

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
        self, messages: list[dict[str, str]], *, temperature: float
    ) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
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
                return str(data["choices"][0]["message"].get("content") or "")
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
        pattern = re.compile(r"(?<![\w-])-?\d+(?:,\d{3})*(?:\.\d+)?")
        rate_markers = (
            "率",
            "比例",
            "percent",
            "rate",
            "completion",
            "refund",
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
        allowed: list[float] = []
        allowed_rates: list[float] = []
        allowed_amounts: list[float] = []

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

        collect(evidence)
        for match in pattern.finditer(answer):
            number = float(match.group(0).replace(",", ""))
            following = answer[match.end() : match.end() + 2]
            context = answer[max(0, match.start() - 16) : match.start()].lower()
            if following.lstrip().startswith("%"):
                candidates = allowed_rates
            elif (
                "￥" in answer[max(0, match.start() - 2) : match.start()]
                or "¥" in answer[max(0, match.start() - 2) : match.start()]
                or following.lstrip().startswith("元")
            ):
                candidates = allowed_amounts
            elif any(marker in context for marker in rate_markers):
                candidates = allowed_rates
            elif any(marker in context for marker in amount_markers):
                candidates = allowed_amounts
            else:
                candidates = allowed
            if not any(
                abs(number - candidate)
                <= max(1e-6, abs(candidate) * 1e-6)
                for candidate in candidates
            ):
                return False
        return True
