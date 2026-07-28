import pytest

from app.config import settings
from app.v2.api.dependencies import get_provider
from app.v2.api.errors import V2APIError
from app.v2.services.provider import DeepSeekProvider, FakeAnalysisProvider
from app.v2.services.runs import AnalysisRunService
from app.db import database
from app.v2.db.models import AnalysisRunModel


def test_provider_dependency_keeps_fake_as_safe_default(monkeypatch):
    monkeypatch.setattr(settings, "v2_provider", "fake")
    assert isinstance(get_provider(), FakeAnalysisProvider)


def test_provider_dependency_builds_deepseek_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "v2_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "configured")
    provider = get_provider()
    assert isinstance(provider, DeepSeekProvider)
    assert provider.model == settings.deepseek_model


def test_provider_dependency_rejects_deepseek_without_key(monkeypatch):
    monkeypatch.setattr(settings, "v2_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    with pytest.raises(V2APIError) as raised:
        get_provider()

    assert raised.value.status_code == 503
    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"
    assert raised.value.retryable is False


def test_provider_dependency_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "v2_provider", "unknown")

    with pytest.raises(V2APIError) as raised:
        get_provider()

    assert raised.value.code == "PROVIDER_NOT_AVAILABLE"


def test_run_persists_selected_provider_metadata(v2_runtime):
    run = AnalysisRunService().create_run(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message="真实分析元数据",
        idempotency_key="provider-metadata",
        provider_name="deepseek",
        provider_model="deepseek-chat",
    )

    session = database.SessionLocal()
    persisted = session.get(AnalysisRunModel, run.id)
    assert persisted.model_config_json == {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "schema_version": "1.0",
    }
    session.close()
