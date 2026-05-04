from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol

from .llm_enrichment import build_enrichment_prompt, parse_enrichment_response


class EnrichmentClientProtocol(Protocol):
    provider: str
    model: str

    async def enrich_event(self, *, event: dict, entities: list[dict]): ...


class OpenAIChatEnrichmentClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def enrich_event(self, *, event: dict, entities: list[dict]):
        return await asyncio.to_thread(self._enrich_event_sync, event=event, entities=entities)

    def _enrich_event_sync(self, *, event: dict, entities: list[dict]):
        messages = build_enrichment_prompt(event=event, entities=entities)
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "gmgn-twitter-intel/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
        content = payload["choices"][0]["message"]["content"]
        return parse_enrichment_response(content, event_text=_event_text(event))


def _event_text(event: dict) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""
