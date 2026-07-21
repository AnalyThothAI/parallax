from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from parallax.domains.watchlist_intel.repositories.watchlist_intel_repository import (
    WatchlistIntelRepository,
)


def test_token_resolutions_for_events_projects_symbol_and_event_price() -> None:
    conn = _FakeConn(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:TokenA",
                "pricefeed_id": None,
                "resolution_status": "EXACT",
                "reason_codes_json": ["ca_match"],
                "candidate_ids_json": [],
                "lookup_keys_json": [],
                "symbol": "VOICE",
                "market_tick_id": "tick-1",
                "market_tick_provider": "gmgn_dex_quote",
                "market_tick_observed_at_ms": 1_700_000_000_000,
                "price_usd": Decimal("0.00042"),
                "price_quote": None,
                "price_quote_symbol": None,
                "quote_symbol": None,
                "market_capture_method": "tier3_inline",
                "market_tick_lag_ms": 500,
            }
        ]
    )

    grouped = WatchlistIntelRepository(conn).token_resolutions_for_events(("event-1",))

    resolution = grouped["event-1"][0]
    assert "tir.target_type IN ('Asset', 'CexToken')" in conn.sql
    assert "tir.target_id IS NOT NULL" in conn.sql
    assert resolution["symbol"] == "VOICE"
    assert resolution["price"] == {
        "status": "ready",
        "provider": "gmgn_dex_quote",
        "pricefeed_id": None,
        "price_usd": 0.00042,
        "price_quote": None,
        "quote_symbol": None,
        "observed_at_ms": 1_700_000_000_000,
        "observation_lag_ms": 500,
        "observation_id": "tick-1",
        "observation_kind": "tier3_inline",
    }


def test_handle_overview_bounds_source_sample_before_resolution_fanout() -> None:
    conn = _RecordingConn(
        [
            _FakeResult(
                one={
                    "source_event_count": 3,
                    "last_source_event_at_ms": 3_000,
                }
            ),
            _FakeResult(
                many=[
                    _event_row("event-3", received_at_ms=3_000, cashtags=["THREE"]),
                    _event_row("event-2", received_at_ms=2_000, cashtags=["TWO"]),
                ]
            ),
            _FakeResult(many=[]),
        ]
    )

    overview = WatchlistIntelRepository(conn).handle_overview(
        handle="MarionAwfal",
        scope="signal",
        since_ms=0,
        source_limit=1,
        cluster_limit=1,
    )

    assert "COUNT(*) AS source_event_count" in conn.calls[0]["sql"]
    assert "LIMIT %s" in conn.calls[1]["sql"]
    assert conn.calls[1]["params"] == ("marionawfal", 0, 2)
    assert overview["metrics"]["source_event_count"] == 3
    assert overview["metrics"]["last_source_event_at_ms"] == 3_000
    assert overview["metrics"]["candidate_mention_count"] == 1
    assert [cluster["label"] for cluster in overview["candidate_mention_clusters"]] == ["$THREE"]
    assert overview["clusters_truncated"] is True
    assert "source_events_sampled" in overview["risk_notes"]


def test_handle_overview_requires_explicit_source_and_cluster_limits_before_sql() -> None:
    conn = _RecordingConn([])

    try:
        WatchlistIntelRepository(conn).handle_overview(handle="marionawfal", scope="signal", since_ms=0)
    except TypeError as exc:
        assert "source_limit" in str(exc)
    else:
        raise AssertionError("missing overview limits should fail before SQL")

    assert conn.calls == []


@pytest.mark.parametrize("limit", [0, -1, True, "30"])
def test_timeline_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = _RecordingConn([])

    with pytest.raises(ValueError, match="watchlist_timeline_limit_required"):
        WatchlistIntelRepository(conn).timeline(handle="marionawfal", scope="signal", cursor=None, limit=limit)

    assert conn.calls == []


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        pytest.param("event_id", "", "watchlist_event_id_required", id="blank-event-id"),
        pytest.param("received_at_ms", 0, "watchlist_event_received_at_ms_required", id="zero-timestamp"),
        pytest.param("cashtags_json", "not-json", "watchlist_event_cashtags_json_required", id="invalid-json"),
        pytest.param("hashtags_json", {}, "watchlist_event_hashtags_json_required", id="wrong-json-shape"),
    ],
)
def test_timeline_rejects_malformed_persisted_event_rows(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = _event_row("event-1", received_at_ms=1_000)
    row[field_name] = value
    conn = _RecordingConn([_FakeResult(many=[row])])

    with pytest.raises(ValueError, match=error):
        WatchlistIntelRepository(conn).timeline(handle="marionawfal", scope="signal", cursor=None, limit=1)

    assert len(conn.calls) == 1


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("source_limit", 0, "watchlist_source_limit_required"),
        ("source_limit", -1, "watchlist_source_limit_required"),
        ("source_limit", True, "watchlist_source_limit_required"),
        ("source_limit", "1", "watchlist_source_limit_required"),
        ("cluster_limit", 0, "watchlist_cluster_limit_required"),
        ("cluster_limit", -1, "watchlist_cluster_limit_required"),
        ("cluster_limit", True, "watchlist_cluster_limit_required"),
        ("cluster_limit", "1", "watchlist_cluster_limit_required"),
    ],
)
def test_handle_overview_rejects_malformed_limits_before_sql(field: str, value: object, error: str) -> None:
    conn = _RecordingConn([])
    kwargs = {"source_limit": 1, "cluster_limit": 1}
    kwargs[field] = value

    with pytest.raises(ValueError, match=error):
        WatchlistIntelRepository(conn).handle_overview(handle="marionawfal", scope="signal", since_ms=0, **kwargs)

    assert conn.calls == []


def test_handles_overview_batches_configured_handles_in_one_keyset_query() -> None:
    conn = _RecordingConn(
        [
            _FakeResult(
                many=[
                    {
                        "handle": "marionawfal",
                        "last_source_event_at_ms": 3_000,
                        "recent_source_event_count": 2,
                        "recent_signal_event_count": 0,
                        "total_signal_event_count": 0,
                    },
                    {
                        "handle": "toly",
                        "last_source_event_at_ms": None,
                        "recent_source_event_count": 0,
                        "recent_signal_event_count": 0,
                        "total_signal_event_count": 0,
                    },
                ]
            )
        ]
    )

    rows = WatchlistIntelRepository(conn).handles_overview(handles=("@MarionAwfal", "toly"), since_ms=1_000)

    assert [row["handle"] for row in rows] == ["marionawfal", "toly"]
    assert len(conn.calls) == 1
    sql = conn.calls[0]["sql"]
    assert "WITH input_handles AS" in sql
    assert "WITH ORDINALITY" in sql
    assert conn.calls[0]["params"] == (["marionawfal", "toly"], 1_000)


def test_handles_overview_uses_indexable_latest_probe_and_windowed_count() -> None:
    conn = _RecordingConn([_FakeResult(many=[])])

    WatchlistIntelRepository(conn).handles_overview(handles=("marionawfal", "toly"), since_ms=1_000)

    sql = conn.calls[0]["sql"]
    assert "latest_by_handle AS" in sql
    assert "LEFT JOIN LATERAL" in sql
    assert "ORDER BY events.received_at_ms DESC, events.event_id DESC" in sql
    assert "LIMIT 1" in sql
    assert "recent_counts AS" in sql
    assert "events.received_at_ms >= %s" in sql
    assert "MAX(events.received_at_ms)" not in sql


def _event_row(
    event_id: str,
    *,
    received_at_ms: int,
    cashtags: list[str] | None = None,
    hashtags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "logical_dedup_key": event_id,
        "canonical_url": None,
        "received_at_ms": received_at_ms,
        "author_handle": "marionawfal",
        "action": "tweet",
        "text_clean": "$THREE #macro",
        "search_text": "$THREE #macro",
        "event_json": {},
        "urls_json": [],
        "cashtags_json": cashtags or [],
        "hashtags_json": hashtags or [],
        "mentions_json": [],
        "is_watched": True,
        "matched_at_ms": received_at_ms,
    }


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""

    def execute(self, sql: str, *_: Any) -> _FakeConn:
        self.sql = sql
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class _FakeResult:
    def __init__(self, *, one: dict[str, Any] | None = None, many: list[dict[str, Any]] | None = None) -> None:
        self.one = one
        self.many = many or []

    def fetchone(self) -> dict[str, Any] | None:
        return self.one

    def fetchall(self) -> list[dict[str, Any]]:
        return self.many


class _RecordingConn:
    def __init__(self, results: list[_FakeResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = ()) -> _FakeResult:
        self.calls.append({"sql": sql, "params": params})
        if not self.results:
            raise AssertionError(f"unexpected SQL call: {sql}")
        return self.results.pop(0)
