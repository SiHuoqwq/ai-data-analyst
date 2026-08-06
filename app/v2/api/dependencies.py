from fastapi import Depends

from app.config import settings
from app.v2.api.errors import V2APIError
from app.v2.services.provider import DeepSeekProvider, FakeAnalysisProvider


def get_provider():
    if settings.v2_provider == "fake":
        provider = FakeAnalysisProvider(
            step_delay_seconds=settings.v2_fake_step_delay_seconds
        )
    elif settings.v2_provider == "deepseek":
        if not settings.deepseek_api_key.strip():
            raise V2APIError(
                503,
                "PROVIDER_NOT_CONFIGURED",
                "真实分析服务尚未配置 API Key",
                retryable=False,
            )
        provider = DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.v2_llm_timeout_seconds,
            max_retries=settings.v2_llm_max_retries,
            max_tool_rounds=settings.v2_max_tool_rounds,
            max_prompt_chars=settings.v2_max_prompt_chars,
        )
    else:
        raise V2APIError(
            503,
            "PROVIDER_NOT_AVAILABLE",
            "当前 V2 Provider 不可用",
            {"configured_provider": settings.v2_provider},
            retryable=False,
        )
    setattr(provider, "_owned_by_provider_dependency", True)
    return provider


def get_recommendation_provider(provider=Depends(get_provider)):
    """Close only providers created by get_provider for this request.

    Dependency overrides return unmarked shared providers and retain ownership.
    """
    try:
        yield provider
    finally:
        if getattr(provider, "_owned_by_provider_dependency", False):
            close = getattr(provider, "close", None)
            if callable(close):
                close()
