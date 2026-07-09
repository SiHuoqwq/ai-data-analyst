import json as json_module
import httpx
from app.config import settings
from app.services.llm.base import BaseLLM


class DeepSeekLLM(BaseLLM):
    def __init__(self):
        self.base_url = settings.deepseek_base_url
        self.api_key = settings.deepseek_api_key
        self._model = "deepseek-chat"
        self._client: httpx.AsyncClient | None = None

    @property
    def model_name(self) -> str:
        return self._model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._client

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        client = await self._get_client()
        body = {"model": self._model, "messages": messages, "temperature": 0.7}
        if tools:
            body["tools"] = tools

        resp = await client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        result = {"content": msg.get("content", "") or "", "tool_calls": None}
        if msg.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "args": json_module.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                }
                for tc in msg["tool_calls"]
            ]
        return result

    async def chat_stream(self, messages: list[dict]):
        client = await self._get_client()
        body = {"model": self._model, "messages": messages, "temperature": 0.7, "stream": True}

        async with client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json_module.loads(chunk)
                        delta = data["choices"][0].get("delta", {})
                        if delta.get("content"):
                            yield delta["content"]
                    except (json_module.JSONDecodeError, KeyError, IndexError):
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
