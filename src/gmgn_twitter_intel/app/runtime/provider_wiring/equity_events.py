from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gmgn_twitter_intel.app.runtime.provider_wiring.types import EquityEventIntelProviders
from gmgn_twitter_intel.integrations.equity_events.sec_edgar_client import SecEdgarClient
from gmgn_twitter_intel.platform.config.settings import Settings


@dataclass(frozen=True, slots=True)
class EquityDocumentProviderFetchResult:
    status_code: int
    documents: list[dict[str, Any]] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class CompositeEquityEventDocumentProvider:
    def __init__(self, *, sec_client: SecEdgarClient | None) -> None:
        self._sec_client = sec_client

    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentProviderFetchResult:
        provider_type = str(source.get("provider_type") or "sec_submissions")
        if provider_type != "sec_submissions":
            return _failed_fetch(source=source, reason="unsupported_provider_type")
        if self._sec_client is None:
            return _failed_fetch(source=source, reason="missing_sec_user_agent")

        cik = source.get("cik") or source.get("company_cik")
        if not cik:
            return _failed_fetch(source=source, reason="missing_cik")

        result = self._sec_client.fetch_company_submissions(
            str(cik),
            etag=_optional_string(source.get("etag")),
            last_modified=_optional_string(source.get("last_modified")),
        )
        if result.not_modified:
            return EquityDocumentProviderFetchResult(
                status_code=result.status_code,
                etag=result.etag,
                last_modified=result.last_modified,
                not_modified=True,
            )
        return EquityDocumentProviderFetchResult(
            status_code=result.status_code,
            documents=[
                {
                    "provider_type": "sec_submissions",
                    "source_id": source.get("source_id"),
                    "cik": str(cik),
                    "payload": result.payload,
                }
            ],
            etag=result.etag,
            last_modified=result.last_modified,
            not_modified=False,
        )

    def close(self) -> None:
        if self._sec_client is not None:
            self._sec_client.close()


def wire_equity_event_intel(
    settings: Settings,
    *,
    brief_provider: object | None = None,
) -> EquityEventIntelProviders:
    if not settings.equity_event_intel.enabled:
        return EquityEventIntelProviders()
    return EquityEventIntelProviders(
        document_provider=CompositeEquityEventDocumentProvider(
            sec_client=_sec_client(settings),
        ),
        brief_provider=brief_provider,
    )


def _sec_client(settings: Settings) -> SecEdgarClient | None:
    user_agent = _optional_string(settings.equity_event_intel.sec_user_agent)
    if user_agent is None:
        return None
    return SecEdgarClient(user_agent=user_agent)


def _failed_fetch(*, source: dict[str, Any], reason: str) -> EquityDocumentProviderFetchResult:
    return EquityDocumentProviderFetchResult(
        status_code=0,
        documents=[
            {
                "status": "failed",
                "error_code": reason,
                "provider_type": source.get("provider_type") or "sec_submissions",
                "source_id": source.get("source_id"),
            }
        ],
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "CompositeEquityEventDocumentProvider",
    "EquityDocumentProviderFetchResult",
    "wire_equity_event_intel",
]
