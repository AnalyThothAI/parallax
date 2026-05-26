import httpx
import pytest

from gmgn_twitter_intel.app.runtime import provider_wiring
from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import CompositeEquityEventDocumentProvider
from gmgn_twitter_intel.domains.equity_event_intel.types import NormalizedEquityDocument
from gmgn_twitter_intel.integrations.equity_events.sec_edgar_client import SecEdgarClient
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


def test_sec_edgar_client_fetches_filing_document_and_companyfacts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "www.sec.gov":
            return httpx.Response(
                200,
                text="<html>Revenue rose</html>",
                headers={"etag": "filing-etag", "last-modified": "Tue, 26 May 2026 00:00:00 GMT"},
            )
        return httpx.Response(
            200,
            json={"cik": 320193, "facts": {"dei": {}}},
            headers={"etag": "facts-etag", "last-modified": "Tue, 26 May 2026 01:00:00 GMT"},
        )

    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(handler),
        min_interval_seconds=0,
    )

    document = client.fetch_filing_document(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl.htm"
    )
    companyfacts = client.fetch_companyfacts("320193")

    assert document.status_code == 200
    assert document.text == "<html>Revenue rose</html>"
    assert document.etag == "filing-etag"
    assert companyfacts.payload == {"cik": 320193, "facts": {"dei": {}}}
    assert companyfacts.etag == "facts-etag"
    assert requests[0].url.path == "/Archives/edgar/data/320193/000032019326000001/aapl.htm"
    assert requests[1].url.path == "/api/xbrl/companyfacts/CIK0000320193.json"


def test_sec_edgar_client_rejects_non_archive_document_url() -> None:
    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="unexpected")),
        min_interval_seconds=0,
    )

    with pytest.raises(ValueError, match=r"SEC filing document URL must be under sec\.gov Archives"):
        client.fetch_filing_document("https://example.com/filing.htm")


def test_sec_edgar_client_rejects_redirect_outside_archive_document_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.sec.gov":
            return httpx.Response(302, headers={"location": "https://example.com/filing.htm"})
        return httpx.Response(200, text="<html>unexpected</html>")

    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(handler),
        min_interval_seconds=0,
    )

    with pytest.raises(ValueError, match=r"SEC filing document URL must be under sec\.gov Archives"):
        client.fetch_filing_document("https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl.htm")


def test_hydrate_document_evidence_ready_sec_html_produces_html_text_artifact() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=_sec_client_for_hydration(html="<html>Revenue rose</html>")
    )

    result = provider.hydrate_document_evidence(source=_source(), document=_document())

    assert result.status_code == 200
    assert result.error_code is None
    html_artifact = result.artifacts[0]
    assert html_artifact.artifact_kind == "html_text"
    assert html_artifact.extraction_status == "ready"
    assert html_artifact.content_text == "Revenue rose"
    assert html_artifact.failure_reason is None
    assert result.artifacts[1].artifact_kind == "companyfacts"
    assert result.artifacts[1].extraction_status == "ready"


def test_hydrate_document_evidence_uses_distinct_persistence_document_ids() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=_sec_client_for_hydration(html="<html>Revenue rose</html>")
    )

    result = provider.hydrate_document_evidence(
        source=_source(),
        document=_document(
            event_document_id="event-doc-123",
            provider_document_id="provider-doc-456",
            provider_document_key="provider-key-789",
        ),
    )

    assert result.artifacts[0].event_document_id == "event-doc-123"
    assert result.artifacts[0].provider_document_id == "provider-doc-456"
    assert result.artifacts[1].event_document_id == "event-doc-123"
    assert result.artifacts[1].provider_document_id == "provider-doc-456"


def test_hydrate_document_evidence_empty_sec_html_is_unavailable() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=_sec_client_for_hydration(html="<script>hidden()</script>")
    )

    result = provider.hydrate_document_evidence(source=_source(), document=_document())

    assert result.status_code == 200
    assert result.artifacts[0].extraction_status == "unavailable"
    assert result.artifacts[0].failure_reason == "empty_sec_document_text"


def test_hydrate_document_evidence_invalid_sec_url_is_failed() -> None:
    provider = CompositeEquityEventDocumentProvider(sec_client=_sec_client_for_hydration(html="unexpected"))

    result = provider.hydrate_document_evidence(
        source=_source(), document=_document(document_url="https://example.com/aapl.htm")
    )

    assert result.status_code == 0
    assert result.error_code == "sec_invalid_url"
    assert result.artifacts[0].extraction_status == "failed"
    assert result.artifacts[0].failure_reason == "sec_invalid_url"


def test_hydrate_document_evidence_companyfacts_404_is_unavailable_while_html_ready() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=_sec_client_for_hydration(html="<html>Revenue rose</html>", companyfacts_status=404)
    )

    result = provider.hydrate_document_evidence(source=_source(), document=_document())

    assert result.status_code == 200
    assert result.artifacts[0].extraction_status == "ready"
    assert result.artifacts[1].artifact_kind == "companyfacts"
    assert result.artifacts[1].extraction_status == "unavailable"
    assert result.artifacts[1].failure_reason == "companyfacts_unavailable"


def test_hydrate_document_evidence_invalid_cik_fails_companyfacts_without_raising() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=_sec_client_for_hydration(html="<html>Revenue rose</html>")
    )

    result = provider.hydrate_document_evidence(source=_source(), document=_document(cik="CIK-not-a-number"))

    assert result.artifacts[0].artifact_kind == "html_text"
    assert result.artifacts[0].extraction_status == "ready"
    assert result.artifacts[1].artifact_kind == "companyfacts"
    assert result.artifacts[1].extraction_status == "failed"
    assert result.artifacts[1].failure_reason == "sec_invalid_cik"


def test_hydrate_document_evidence_http_failure_preserves_sec_http_reason() -> None:
    provider = CompositeEquityEventDocumentProvider(sec_client=_sec_client_for_hydration(html_status=503))

    result = provider.hydrate_document_evidence(source=_source(), document=_document())

    assert result.status_code == 503
    assert result.error_code == "sec_http_503"
    assert result.artifacts[0].extraction_status == "failed"
    assert result.artifacts[0].failure_reason == "sec_http_503"


class _FailingSecClient:
    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code

    def fetch_company_submissions(self, cik: str, *, etag: str | None, last_modified: str | None) -> object:
        del cik, etag, last_modified
        request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000789019.json")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("SEC failed", request=request, response=response)


def _sec_client_for_hydration(
    *,
    html: str = "<html>Revenue rose</html>",
    html_status: int = 200,
    companyfacts_status: int = 200,
) -> SecEdgarClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.sec.gov":
            return httpx.Response(html_status, text=html)
        if companyfacts_status == 200:
            return httpx.Response(200, json={"cik": 320193, "facts": {"dei": {}}})
        return httpx.Response(companyfacts_status, text="missing")

    return SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(handler),
        min_interval_seconds=0,
        max_attempts=1,
    )


def _source() -> dict[str, object]:
    return {"source_id": "sec:AAPL", "provider_type": "sec_submissions", "cik": "320193"}


def _document(
    *,
    cik: str = "320193",
    event_document_id: str | None = None,
    provider_document_id: str | None = None,
    provider_document_key: str = "0000320193-26-000001:10-Q",
    document_url: str = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl.htm",
) -> NormalizedEquityDocument:
    return NormalizedEquityDocument(
        provider_document_key=provider_document_key,
        company_id="aapl",
        ticker="AAPL",
        cik=cik,
        event_document_id=event_document_id,
        provider_document_id=provider_document_id,
        document_url=document_url,
        payload_hash="sha256:payload",
        raw_payload_json={"title": "must not become evidence", "body_text": "must not become evidence"},
        fetched_at_ms=100,
        document_type="sec_filing",
        form_type="10-Q",
        accession_number="0000320193-26-000001",
        event_time_ms=100,
    )
