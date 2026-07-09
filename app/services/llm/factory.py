from app.config import settings
from app.services.llm.base import BaseLLM


def get_llm(provider: str | None = None) -> BaseLLM:
    provider = provider or settings.llm_provider

    if provider == "deepseek":
        from app.services.llm.deepseek import DeepSeekLLM
        return DeepSeekLLM()
    elif provider == "openai":
        from app.services.llm.openai import OpenAILLM
        return OpenAILLM()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
