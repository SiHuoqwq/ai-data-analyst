from app.config import settings
from app.v2.api.errors import V2APIError
from app.v2.services.provider import FakeAnalysisProvider


def get_provider() -> FakeAnalysisProvider:
    if settings.v2_provider != "fake":
        raise V2APIError(
            503,
            "PROVIDER_NOT_AVAILABLE",
            "当前 V2 Provider 不可用",
            {"configured_provider": settings.v2_provider},
            retryable=False,
        )
    return FakeAnalysisProvider(
        step_delay_seconds=settings.v2_fake_step_delay_seconds
    )
