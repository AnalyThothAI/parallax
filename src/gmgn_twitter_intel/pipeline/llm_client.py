from __future__ import annotations

from typing import Any, Protocol

from openai import APIError, AsyncOpenAI, OpenAIError

from .social_event_extraction import (
    build_social_event_prompt,
    parse_social_event_response,
    social_event_response_format,
)


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
        sdk_client: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = sdk_client or AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=timeout_seconds,
            default_headers={"User-Agent": "gmgn-twitter-intel/0.1"},
        )

    async def enrich_event(self, *, event: dict, entities: list[dict]):
        messages = build_social_event_prompt(event=event, entities=entities)
        try:
            completion = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                response_format=social_event_response_format(),
            )
        except APIError as exc:
            raise RuntimeError(f"LLM request failed: {exc.status_code} {exc.message}") from exc
        except OpenAIError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        content = completion.choices[0].message.content or ""
        return parse_social_event_response(content, event_text=_event_text(event))


def _event_text(event: dict) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""
