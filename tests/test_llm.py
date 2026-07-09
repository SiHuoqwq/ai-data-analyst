import pytest
from app.services.llm.factory import get_llm
from app.services.llm.base import BaseLLM
from app.services.llm.deepseek import DeepSeekLLM


def test_get_llm_returns_deepseek_by_default():
    llm = get_llm()
    assert isinstance(llm, BaseLLM)
    assert llm.model_name == "deepseek-chat"


def test_get_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm("unknown")


def test_deepseek_llm_attributes():
    llm = get_llm("deepseek")
    assert isinstance(llm, DeepSeekLLM)
    assert llm.model_name == "deepseek-chat"
    assert llm.api_key is not None
