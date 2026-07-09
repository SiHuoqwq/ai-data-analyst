from app.services.llm.base import BaseLLM


class OpenAILLM(BaseLLM):
    def __init__(self):
        self._model = "gpt-4o"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        raise NotImplementedError("OpenAI provider not yet implemented")

    async def chat_stream(self, messages: list[dict]):
        raise NotImplementedError("OpenAI provider not yet implemented")
        yield
