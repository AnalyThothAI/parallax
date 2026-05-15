from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
from agents import set_tracing_export_api_key
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI

from gmgn_twitter_intel.platform.config.settings import Settings

T = TypeVar("T")

DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_RPM_LIMIT = 3000
SHARED_HEADERS = {"User-Agent": "gmgn-twitter-intel/0.1"}


class LLMGateway:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        trace_enabled: bool = True,
        trace_api_key: str | None = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        rpm_limit: int = DEFAULT_RPM_LIMIT,
    ) -> None:
        self.api_key = str(api_key or "")
        self.base_url = _api_base(base_url)
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._limiter = AsyncLimiter(max(1, int(rpm_limit)), 60)
        self._clients: list[Any] = []
        self.last_worker_name: str | None = None
        self.last_stage: str | None = None

        tracing_export_key = str(trace_api_key or "").strip()
        if not tracing_export_key and _is_openai_base_url(self.base_url):
            tracing_export_key = self.api_key
        self.trace_export_enabled = bool(trace_enabled and tracing_export_key)
        if self.trace_export_enabled:
            set_tracing_export_api_key(tracing_export_key)

    @classmethod
    def create(cls, settings: Settings) -> LLMGateway:
        return cls(
            api_key=settings.llm_api_key or "",
            base_url=settings.llm_base_url,
            trace_enabled=settings.llm_trace_enabled,
            trace_api_key=settings.llm_trace_api_key,
        )

    async def run_with_limits(
        self,
        worker_name: str,
        stage: str,
        timeout_s: float,
        coro_factory: Callable[[], Awaitable[T]],
    ) -> T:
        self.last_worker_name = str(worker_name)
        self.last_stage = str(stage)
        async with self._semaphore, self._limiter:
            return await asyncio.wait_for(coro_factory(), timeout=float(timeout_s))

    def openai_client(self, *, model: str, base_url: str, timeout_s: float) -> AsyncOpenAI:
        _ = model
        http_client = httpx.AsyncClient(trust_env=False)
        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=_api_base(base_url),
            timeout=float(timeout_s),
            max_retries=0,
            default_headers=SHARED_HEADERS,
            http_client=http_client,
        )
        self._clients.append(client)
        return client

    async def aclose(self) -> None:
        errors: list[Exception] = []
        while self._clients:
            client = self._clients.pop()
            close = getattr(client, "close", None) or getattr(client, "aclose", None)
            if close is None:
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("llm_gateway_close_failed", errors)


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


def _is_openai_base_url(base_url: str) -> bool:
    value = _api_base(base_url).lower()
    return value == "https://api.openai.com" or value.startswith("https://api.openai.com/")


__all__ = ["LLMGateway"]
