"""The ntfy publisher seam (CLAUDE.md §9 — one of the four injected dependencies alongside
the clock, the IMAP fetcher, and the LLM client). Nothing that raises an alert may POST to
ntfy directly; tests use `FakeNtfyPublisher` and assert on what got published, production
wires `HttpNtfyPublisher`.
"""

from typing import Protocol

import httpx


class NtfyPublisher(Protocol):
    async def publish(
        self, message: str, *, title: str | None = None, click: str | None = None
    ) -> None: ...


class FakeNtfyPublisher:
    def __init__(self) -> None:
        # (message, title, click) — tests assert deep links land on the right alert (#34).
        self.published: list[tuple[str, str | None, str | None]] = []

    async def publish(
        self, message: str, *, title: str | None = None, click: str | None = None
    ) -> None:
        self.published.append((message, title, click))


class HttpNtfyPublisher:
    def __init__(self, base_url: str, topic: str):
        self._url = f"{base_url.rstrip('/')}/{topic}"

    async def publish(
        self, message: str, *, title: str | None = None, click: str | None = None
    ) -> None:
        # `Click` is the URL ntfy's Android app opens when the notification is tapped (#34): a
        # `magpie://…` deep link the app resolves to the relevant screen via its intent-filter.
        headers: dict[str, str] = {}
        if title:
            headers["Title"] = title
        if click:
            headers["Click"] = click
        async with httpx.AsyncClient() as client:
            await client.post(self._url, data=message.encode("utf-8"), headers=headers, timeout=8.0)
