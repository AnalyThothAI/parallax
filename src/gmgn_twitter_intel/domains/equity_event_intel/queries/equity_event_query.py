from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    equity_event_page_cursor,
    equity_event_timeline_cursor,
)


class EquityEventQuery:
    def __init__(self, *, repository: Any):
        self.repository = repository

    def list_events(
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
    ) -> dict[str, Any]:
        rows = self.repository.list_event_page_rows(
            limit=max(1, int(limit)),
            cursor=cursor,
            window=window,
            universe=universe,
            ticker=_ticker(ticker),
            event_type=event_type,
            priority=priority,
            source_role=source_role,
            lifecycle_status=lifecycle_status,
            brief_status=brief_status,
            q=q,
        )
        next_cursor = equity_event_page_cursor(rows[-1]) if rows else None
        return {"items": rows, "next_cursor": next_cursor}

    def get_event(self, company_event_id: str) -> dict[str, Any] | None:
        return self.repository.get_event_detail(company_event_id=company_event_id)

    def get_story(self, story_id: str) -> dict[str, Any] | None:
        return self.repository.get_story_detail(story_id=story_id)

    def list_calendar(
        self,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        universe: str | None = None,
        ticker: str | None = None,
        status: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        rows = self.repository.list_calendar_rows(
            from_ms=from_ms,
            to_ms=to_ms,
            universe=universe,
            ticker=_ticker(ticker),
            status=status,
            session=session,
        )
        return {"items": rows}

    def company_timeline(
        self,
        *,
        ticker: str,
        limit: int,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        rows = self.repository.list_company_timeline_rows(
            ticker=_ticker(ticker) or str(ticker).strip().upper(),
            limit=max(1, int(limit)),
            cursor=cursor,
        )
        next_cursor = equity_event_timeline_cursor(rows[-1]) if rows else None
        return {"items": rows, "next_cursor": next_cursor}

    def source_status(self) -> list[dict[str, Any]]:
        return self.repository.list_source_status()

    def summary(self) -> dict[str, Any]:
        data = dict(self.repository.summary() or {})
        return {
            "p0_open_count": int(data.get("p0_open_count") or 0),
            "today_count": int(data.get("today_count") or 0),
            "brief_pending_count": int(data.get("brief_pending_count") or 0),
            "latest_event_at_ms": data.get("latest_event_at_ms"),
        }


def _ticker(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None
