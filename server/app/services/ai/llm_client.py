"""The LLM client seam (CLAUDE.md §9 — the fourth and final injected dependency, after the
clock, IMAP fetcher, and ntfy publisher). Nothing in `app/services/ai/` may call an LLM
directly; tests use `FakeLlmClient`, production wires `LmStudioClient` against the suite's
local LM Studio instance (an OpenAI-compatible chat completions endpoint, CLAUDE.md's target
architecture — never a hosted/cloud model: this data never leaves the host).
"""

from typing import Protocol

import httpx


class LlmClient(Protocol):
    async def complete(self, prompt: str) -> str: ...

    async def chat(self, messages: list[dict]) -> str: ...


class FakeLlmClient:
    """Test double — returns a scripted response regardless of prompt content."""

    def __init__(self, response: str):
        self.response = response
        self.prompts_seen: list[str] = []
        self.messages_seen: list[list[dict]] = []

    async def complete(self, prompt: str) -> str:
        self.prompts_seen.append(prompt)
        return self.response

    async def chat(self, messages: list[dict]) -> str:
        self.messages_seen.append(messages)
        return self.response


class LmStudioClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 15.0):
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._timeout = timeout_seconds

    async def complete(self, prompt: str) -> str:
        return await self.chat([{"role": "user", "content": prompt}])

    async def chat(self, messages: list[dict]) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                json={"model": self._model, "messages": messages, "temperature": 0},
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
