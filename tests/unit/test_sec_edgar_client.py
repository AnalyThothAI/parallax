from __future__ import annotations

import httpx

from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import CompositeEquityEventDocumentProvider
from gmgn_twitter_intel.integrations.equity_events.sec_edgar_client import SecEdgarClient


def test_sec_edgar_client_fetches_company_submissions_and_conditional_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"cik": "0000320193", "name": "Apple Inc."},
            headers={"etag": "next-etag", "last-modified": "Fri, 22 May 2026 00:00:00 GMT"},
        )

    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(handler),
        min_interval_seconds=0,
    )

    result = client.fetch_company_submissions("CIK320193", etag="old-etag", last_modified="old-date")

    assert result.status_code == 200
    assert result.payload["cik"] == "0000320193"
    assert result.etag == "next-etag"
    assert result.last_modified == "Fri, 22 May 2026 00:00:00 GMT"
    assert requests[0].url.path == "/submissions/CIK0000320193.json"
    assert requests[0].headers["if-none-match"] == "old-etag"
    assert requests[0].headers["if-modified-since"] == "old-date"


def test_sec_edgar_client_returns_not_modified() -> None:
    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(304, headers={"etag": "same"})),
        min_interval_seconds=0,
    )

    result = client.fetch_company_submissions("320193", etag="old-etag")

    assert result.status_code == 304
    assert result.not_modified is True
    assert result.etag == "same"
    assert result.payload == {}


def test_sec_edgar_client_retries_429_and_5xx_with_backoff_and_retry_after() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"retry-after": "0.25"}),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps: list[float] = []

    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(lambda request: next(responses)),
        min_interval_seconds=0,
        max_attempts=3,
        backoff_seconds=0.5,
        sleep=sleeps.append,
    )

    result = client.fetch_company_submissions("320193")

    assert result.status_code == 200
    assert result.payload == {"ok": True}
    assert sleeps == [0.25, 1.0]


def test_sec_edgar_client_paces_requests() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client = SecEdgarClient(
        user_agent="gmgn-test contact@example.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
        min_interval_seconds=0.11,
        clock=clock,
        sleep=sleep,
    )

    client.fetch_company_submissions("320193")
    client.fetch_company_submissions("320193")

    assert sleeps == [0.11]


def test_equity_document_provider_wraps_expected_sec_failures() -> None:
    provider = CompositeEquityEventDocumentProvider(
        sec_client=SecEdgarClient(
            user_agent="gmgn-test contact@example.com",
            transport=httpx.MockTransport(lambda request: httpx.Response(404, text="missing")),
            min_interval_seconds=0,
        )
    )

    result = provider.fetch_source({"source_id": "sec:AAPL", "provider_type": "sec_submissions", "cik": "320193"})

    assert result.status_code == 404
    assert result.documents[0]["status"] == "failed"
    assert result.documents[0]["error_code"] == "sec_http_404"


def test_equity_document_provider_wraps_rate_limit_and_5xx_failures() -> None:
    for status_code, error_code in ((429, "sec_http_429"), (503, "sec_http_503")):
        provider = CompositeEquityEventDocumentProvider(
            sec_client=SecEdgarClient(
                user_agent="gmgn-test contact@example.com",
                transport=httpx.MockTransport(lambda request, status=status_code: httpx.Response(status)),
                min_interval_seconds=0,
                max_attempts=1,
            )
        )

        result = provider.fetch_source({"source_id": "sec:AAPL", "provider_type": "sec_submissions", "cik": "320193"})

        assert result.documents[0]["error_code"] == error_code


def test_equity_document_provider_wraps_timeout_invalid_json_and_invalid_cik() -> None:
    timeout_provider = CompositeEquityEventDocumentProvider(
        sec_client=SecEdgarClient(
            user_agent="gmgn-test contact@example.com",
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(httpx.TimeoutException("slow", request=request))
            ),
            min_interval_seconds=0,
        )
    )
    invalid_json_provider = CompositeEquityEventDocumentProvider(
        sec_client=SecEdgarClient(
            user_agent="gmgn-test contact@example.com",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
            min_interval_seconds=0,
        )
    )

    assert timeout_provider.fetch_source({"source_id": "sec:AAPL", "cik": "320193"}).documents[0][
        "error_code"
    ] == "sec_timeout"
    assert invalid_json_provider.fetch_source({"source_id": "sec:AAPL", "cik": "320193"}).documents[0][
        "error_code"
    ] == "sec_invalid_json"
    assert invalid_json_provider.fetch_source({"source_id": "sec:AAPL", "cik": "CIK-not-a-number"}).documents[0][
        "error_code"
    ] == "invalid_cik"
