from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router


def test_equity_events_api_lists_read_model_rows_with_filters_without_postgres() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events",
            params={
                "limit": 1,
                "cursor": "3000:event-old",
                "window": "24h",
                "universe": "mega_cap",
                "ticker": "aapl",
                "event_type": "earnings_release",
                "priority": "P0",
                "source_role": "official_issuer",
                "lifecycle_status": "brief_ready",
                "brief_status": "ready",
                "q": "iphone",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert equity_events.event_page_calls == [
        {
            "brief_status": "ready",
            "cursor": "3000:event-old",
            "event_type": "earnings_release",
            "lifecycle_status": "brief_ready",
            "limit": 1,
            "priority": "P0",
            "q": "iphone",
            "source_role": "official_issuer",
            "ticker": "AAPL",
            "universe": "mega_cap",
            "window": "24h",
        }
    ]
    assert response.json() == {
        "ok": True,
        "data": {
            "items": [
                {
                    "row_id": "row-1",
                    "company_event_id": "event-1",
                    "story_id": "story-1",
                    "company_id": "company:aapl",
                    "ticker": "AAPL",
                    "company_name": "Apple Inc.",
                    "event_type": "earnings_release",
                    "priority": "P0",
                    "source_role": "official_issuer",
                    "latest_event_at_ms": 4_000,
                    "lifecycle_status": "brief_ready",
                    "headline": "Apple reports earnings",
                    "summary": "Revenue beat.",
                    "facts_json": [],
                    "documents_json": [],
                    "brief_json": {"status": "ready"},
                    "computed_at_ms": 4_100,
                    "projection_version": "equity_event_page_rows_v1",
                }
            ],
            "next_cursor": "4000:event-1",
        },
    }


def test_equity_events_rejects_malformed_feed_cursor() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events",
            params={"cursor": "bad:event-1"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cursor", "field": "cursor"}
    assert equity_events.event_page_calls == []


def test_equity_events_rejects_invalid_window() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events",
            params={"window": "abc"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_window", "field": "window"}
    assert equity_events.event_page_calls == []


def test_equity_event_detail_returns_404_for_missing_event() -> None:
    equity_events = FakeEquityEventRepository()
    equity_events.event_detail = None
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get("/api/equity-events/event-missing", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "equity_event_not_found"}


def test_equity_events_calendar_forwards_alias_filters() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events/calendar",
            params={
                "from": 1_000,
                "to": 9_000,
                "universe": "watchlist",
                "ticker": "msft",
                "status": "expected",
                "session": "pre",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert equity_events.calendar_calls == [
        {
            "from_ms": 1_000,
            "session": "pre",
            "status": "expected",
            "ticker": "MSFT",
            "to_ms": 9_000,
            "universe": "watchlist",
        }
    ]
    assert response.json() == {
        "ok": True,
        "data": {
            "items": [
                {
                    "row_id": "calendar-1",
                    "expected_event_id": "expected-1",
                    "ticker": "MSFT",
                    "expected_at_ms": 8_000,
                    "status": "expected",
                }
            ]
        },
    }


def test_equity_events_sources_status_returns_source_rows() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get("/api/equity-events/sources/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert equity_events.source_status_calls == 1
    assert response.json() == {
        "ok": True,
        "data": {"sources": [{"source_id": "sec:AAPL", "ticker": "AAPL", "enabled": True}]},
    }


def test_equity_events_summary_returns_counts() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get("/api/equity-events/summary", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert equity_events.summary_calls == 1
    assert response.json() == {
        "ok": True,
        "data": {
            "p0_open_count": 1,
            "today_count": 2,
            "brief_pending_count": 3,
            "latest_event_at_ms": 4_000,
        },
    }


def test_equity_events_story_detail_and_missing_story() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        found = client.get("/api/equity-events/stories/story-1", headers={"Authorization": "Bearer secret"})
        missing = client.get("/api/equity-events/stories/story-missing", headers={"Authorization": "Bearer secret"})

    assert found.status_code == 200
    assert found.json() == {"ok": True, "data": {"story_id": "story-1", "event_count": 1}}
    assert missing.status_code == 404
    assert missing.json() == {"ok": False, "error": "equity_event_story_not_found"}


def test_equity_events_company_timeline_returns_cursor_page() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events/companies/nvda/timeline",
            params={"limit": 1, "cursor": "5000:timeline-old"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert equity_events.timeline_calls == [{"cursor": "5000:timeline-old", "limit": 1, "ticker": "NVDA"}]
    assert response.json() == {
        "ok": True,
        "data": {
            "items": [
                {
                    "row_id": "timeline-1",
                    "ticker": "NVDA",
                    "company_event_id": "event-1",
                    "event_time_ms": 6_000,
                    "headline": "NVIDIA files 8-K",
                }
            ],
            "next_cursor": "6000:timeline-1",
        },
    }


def test_equity_events_company_timeline_rejects_malformed_cursor() -> None:
    equity_events = FakeEquityEventRepository()
    app = _app(equity_events)

    with TestClient(app) as client:
        response = client.get(
            "/api/equity-events/companies/AAPL/timeline",
            params={"cursor": "bad:row-1"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cursor", "field": "cursor"}
    assert equity_events.timeline_calls == []


class FakeEquityEventRepository:
    def __init__(self) -> None:
        self.event_page_calls: list[dict[str, Any]] = []
        self.calendar_calls: list[dict[str, Any]] = []
        self.timeline_calls: list[dict[str, Any]] = []
        self.source_status_calls = 0
        self.summary_calls = 0
        self.event_detail: dict[str, Any] | None = {"company_event_id": "event-1"}

    def list_event_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        window: str | None = None,
        universe: str | None = None,
        ticker: str | None = None,
        event_type: str | None = None,
        priority: str | None = None,
        source_role: str | None = None,
        lifecycle_status: str | None = None,
        brief_status: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        self.event_page_calls.append(
            {
                "brief_status": brief_status,
                "cursor": cursor,
                "event_type": event_type,
                "lifecycle_status": lifecycle_status,
                "limit": limit,
                "priority": priority,
                "q": q,
                "source_role": source_role,
                "ticker": ticker,
                "universe": universe,
                "window": window,
            }
        )
        return [
            {
                "row_id": "row-1",
                "company_event_id": "event-1",
                "story_id": "story-1",
                "company_id": "company:aapl",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "event_type": "earnings_release",
                "priority": "P0",
                "source_role": "official_issuer",
                "latest_event_at_ms": 4_000,
                "lifecycle_status": "brief_ready",
                "headline": "Apple reports earnings",
                "summary": "Revenue beat.",
                "facts_json": [],
                "documents_json": [],
                "brief_json": {"status": "ready"},
                "computed_at_ms": 4_100,
                "projection_version": "equity_event_page_rows_v1",
            }
        ]

    def get_event_detail(self, *, company_event_id: str) -> dict[str, Any] | None:
        if self.event_detail is None:
            return None
        return {"company_event_id": company_event_id}

    def get_story_detail(self, *, story_id: str) -> dict[str, Any] | None:
        if story_id == "story-missing":
            return None
        return {"story_id": story_id, "event_count": 1}

    def list_calendar_rows(
        self,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        universe: str | None = None,
        ticker: str | None = None,
        status: str | None = None,
        session: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calendar_calls.append(
            {
                "from_ms": from_ms,
                "session": session,
                "status": status,
                "ticker": ticker,
                "to_ms": to_ms,
                "universe": universe,
            }
        )
        return [
            {
                "row_id": "calendar-1",
                "expected_event_id": "expected-1",
                "ticker": "MSFT",
                "expected_at_ms": 8_000,
                "status": "expected",
            }
        ]

    def list_company_timeline_rows(
        self,
        *,
        ticker: str,
        limit: int,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        self.timeline_calls.append({"cursor": cursor, "limit": limit, "ticker": ticker})
        return [
            {
                "row_id": "timeline-1",
                "ticker": "NVDA",
                "company_event_id": "event-1",
                "event_time_ms": 6_000,
                "headline": "NVIDIA files 8-K",
            }
        ]

    def list_source_status(self) -> list[dict[str, Any]]:
        self.source_status_calls += 1
        return [{"source_id": "sec:AAPL", "ticker": "AAPL", "enabled": True}]

    def summary(self) -> dict[str, Any]:
        self.summary_calls += 1
        return {
            "p0_open_count": 1,
            "today_count": 2,
            "brief_pending_count": 3,
            "latest_event_at_ms": 4_000,
        }


class FakeRepositoryContext:
    def __init__(self, equity_events: FakeEquityEventRepository) -> None:
        self.equity_events = equity_events

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, equity_events: FakeEquityEventRepository) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.equity_events = equity_events

    def repositories(self):
        return FakeRepositoryContext(self.equity_events)


def _app(equity_events: FakeEquityEventRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(equity_events)
    return app
