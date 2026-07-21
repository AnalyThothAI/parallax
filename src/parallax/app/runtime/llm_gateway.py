from __future__ import annotations

from parallax.platform.config.settings import Settings


class LLMGateway:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        trace_enabled: bool = True,
        trace_api_key: str | None = None,
    ) -> None:
        self.api_key = str(api_key or "")
        self.base_url = _model_base(base_url)
        self.trace_enabled = bool(trace_enabled)
        self.trace_api_key_configured = bool(str(trace_api_key or "").strip())
        self.trace_export_enabled = False

    @classmethod
    def create(cls, settings: Settings) -> LLMGateway:
        return cls(
            api_key=settings.llm_api_key or "",
            base_url=settings.llm_base_url,
            trace_enabled=settings.llm_trace_enabled,
            trace_api_key=settings.llm_trace_api_key,
        )

    async def aclose(self) -> None:
        return None


def _model_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    return value


__all__ = ["LLMGateway"]
