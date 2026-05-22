import httpx
import pytest

from gmgn_twitter_intel.app.runtime import provider_wiring
from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import CompositeEquityEventDocumentProvider
from gmgn_twitter_intel.platform.config.settings import Settings


def test_equity_event_provider_wiring_is_disabled_by_default() -> None:
    providers = provider_wiring.wire_providers(Settings(ws_token="secret"), start_collector=False)

    assert providers.equity_event_intel.document_provider is None
    assert providers.equity_event_intel.brief_provider is None


def test_equity_event_brief_provider_requires_agent_gateway() -> None:
    settings = Settings(
        ws_token="secret",
        llm={"api_key": "test-key"},
        equity_event_intel={"enabled": True, "agent": {"enabled": True}},
        workers={"agent_runtime": {"defaults": {"model": "gpt-equity"}}, "equity_event_brief": {"enabled": True}},
    )

    with pytest.raises(RuntimeError, match="AgentExecutionGateway is required"):
        provider_wiring.wire_providers(settings, start_collector=False)


def test_equity_event_document_provider_preserves_sec_http_failure_status() -> None:
    sec_client = _FailingSecClient(status_code=429)
    provider = CompositeEquityEventDocumentProvider(sec_client=sec_client)

    result = provider.fetch_source(
        {
            "source_id": "sec:MSFT",
            "provider_type": "sec_submissions",
            "cik": "0000789019",
        }
    )

    assert result.status_code == 429
    assert result.documents == [
        {
            "status": "failed",
            "error_code": "sec_http_429",
            "provider_type": "sec_submissions",
            "source_id": "sec:MSFT",
        }
    ]


class _FailingSecClient:
    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code

    def fetch_company_submissions(self, cik: str, *, etag: str | None, last_modified: str | None) -> object:
        del cik, etag, last_modified
        request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000789019.json")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("SEC failed", request=request, response=response)
