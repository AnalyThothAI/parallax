"""Unit tests for the three Investigator tools and ``PulseToolContext`` budget.

The tools are exercised through their private ``_impl_*`` pure functions so we
do not need to construct a SDK ``RunContextWrapper`` / ``ToolContext`` per call;
the SDK-decorated ``@function_tool`` wrappers are trivial passthroughs and are
covered by the import smoke test in ``conftest.py``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from gmgn_twitter_intel.domains.pulse_lab.services.agent_tool_runtime import AgentToolRuntime
from gmgn_twitter_intel.integrations.openai_agents.tools import (
    PulseToolContext,
    ToolBudgetExceeded,
    get_official_token_profile,
    get_target_price_action,
    get_target_recent_tweets,
)
from gmgn_twitter_intel.integrations.openai_agents.tools.official_profile import (
    _impl_get_official_token_profile,
)
from gmgn_twitter_intel.integrations.openai_agents.tools.price_action import (
    _impl_get_target_price_action,
)
from gmgn_twitter_intel.integrations.openai_agents.tools.recent_tweets import (
    _impl_get_target_recent_tweets,
)

# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Stub connection that returns canned rows per ``execute`` call.

    Each entry in ``rowsets`` is the rows returned by the *n*-th execute call.
    If fewer rowsets than calls are supplied, the last one is reused.
    """

    def __init__(self, rowsets: list[list[dict[str, Any]]]) -> None:
        self._rowsets = rowsets or [[]]
        self._idx = 0
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        self.executed.append((sql, params))
        rows = self._rowsets[min(self._idx, len(self._rowsets) - 1)]
        self._idx += 1
        return _FakeCursor(rows)


class _FakePool:
    def __init__(
        self,
        rowsets: list[list[dict[str, Any]]] | None = None,
        *,
        raise_on_connection: Exception | None = None,
    ) -> None:
        self._rowsets = rowsets if rowsets is not None else [[]]
        self._raise = raise_on_connection
        self.conn = _FakeConn(self._rowsets)

    @contextmanager
    def connection(self):
        if self._raise is not None:
            raise self._raise
        yield self.conn


def _ctx(pool: Any, *, max_calls: int = 5) -> PulseToolContext:
    return PulseToolContext(tool_runtime=AgentToolRuntime(db_pool=pool, investigator_max_tool_calls=max_calls))


# ---------------------------------------------------------------------------
# PulseToolContext budget
# ---------------------------------------------------------------------------


def test_budget_increments_and_raises_on_overflow() -> None:
    ctx = _ctx(None, max_calls=5)
    for _ in range(5):
        ctx.tool_runtime.get_target_recent_tweets(target_id="")
    assert ctx.tool_calls_count == 5
    with pytest.raises(ToolBudgetExceeded):
        ctx.tool_runtime.get_target_recent_tweets(target_id="")
    assert ctx.tool_calls_count == 6


def test_budget_three_call_route() -> None:
    """OQ-1: cex routes get budget=3."""
    ctx = _ctx(None, max_calls=3)
    ctx.tool_runtime.get_target_recent_tweets(target_id="")
    ctx.tool_runtime.get_target_recent_tweets(target_id="")
    ctx.tool_runtime.get_target_recent_tweets(target_id="")
    with pytest.raises(ToolBudgetExceeded):
        ctx.tool_runtime.get_target_recent_tweets(target_id="")


# ---------------------------------------------------------------------------
# get_target_recent_tweets
# ---------------------------------------------------------------------------


def _tweet_row(
    *,
    event_id: str,
    handle: str = "alice",
    tweet_id: str = "1111",
    status: str = "EXACT",
    confidence: float = 0.9,
    received_at_ms: int = 1700000000000,
    text: str = "buy SOL now",
    followers: int = 1234,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "author_handle": handle,
        "author_followers": followers,
        "received_at_ms": received_at_ms,
        "text_clean": text,
        "tweet_id": tweet_id,
        "resolution_status": status,
        "confidence": confidence,
    }


def test_recent_tweets_returns_rows_and_updates_contributed_ids() -> None:
    rows = [_tweet_row(event_id=f"evt-{i}", tweet_id=str(1000 + i)) for i in range(5)]
    pool = _FakePool([rows])
    ctx = _ctx(pool)

    result = _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc", limit=20)

    assert result["data"]["target_id"] == "asset:sol:abc"
    tweets = result["data"]["tweets"]
    assert len(tweets) == 5
    assert all(t["tweet_url"].startswith("https://x.com/alice/status/") for t in tweets)
    assert result["contributed_event_ids"] == [f"evt-{i}" for i in range(5)]
    assert ctx.contributed_event_ids == {f"evt-{i}" for i in range(5)}
    assert ctx.tool_calls_count == 1


def test_recent_tweets_empty_target_returns_empty_without_query() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool)

    result = _impl_get_target_recent_tweets(ctx, target_id="")

    assert result == {
        "data": {"target_id": "", "tweets": []},
        "contributed_event_ids": [],
    }
    assert pool.conn.executed == []  # no DB hit
    assert ctx.tool_calls_count == 1


def test_recent_tweets_target_not_found_returns_empty_list() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool)

    result = _impl_get_target_recent_tweets(ctx, target_id="asset:sol:missing")

    assert result["data"] == {"target_id": "asset:sol:missing", "tweets": []}
    assert result["contributed_event_ids"] == []


def test_recent_tweets_db_error_returns_error_dict_without_raising() -> None:
    pool = _FakePool(raise_on_connection=RuntimeError("connection refused"))
    ctx = _ctx(pool)

    result = _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc")

    assert "error" in result["data"]
    assert "connection refused" in result["data"]["error"]
    assert result["contributed_event_ids"] == []


def test_recent_tweets_oversize_payload_is_truncated() -> None:
    # Each tweet ~ a few hundred bytes once a long text is embedded;
    # request 25 tweets with ~500 byte text each => >4KiB.
    long_text = "x" * 500
    rows = [_tweet_row(event_id=f"evt-{i}", tweet_id=str(2000 + i), text=long_text) for i in range(25)]
    pool = _FakePool([rows])
    ctx = _ctx(pool)

    result = _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc", limit=30)

    assert result["data"].get("truncated") is True
    assert len(result["data"]["tweets"]) < 25
    # contributed_event_ids stays in sync with the truncated list
    assert len(result["contributed_event_ids"]) == len(result["data"]["tweets"])


def test_recent_tweets_respects_budget_when_called_too_many_times() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool, max_calls=2)
    _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc")
    _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc")
    with pytest.raises(ToolBudgetExceeded):
        _impl_get_target_recent_tweets(ctx, target_id="asset:sol:abc")


# ---------------------------------------------------------------------------
# get_target_price_action
# ---------------------------------------------------------------------------


def _price_agg(
    *,
    candles_count: int = 12,
    first_seen_ms: int = 1700000000000,
    latest_seen_ms: int = 1700086400000,
    price_min: float = 1.0,
    price_max: float = 2.5,
    liquidity_peak: float = 5_000_000.0,
    volume_24h_peak: float = 1_200_000.0,
    holders_peak: int = 8500,
) -> dict[str, Any]:
    return {
        "candles_count": candles_count,
        "first_seen_ms": first_seen_ms,
        "latest_seen_ms": latest_seen_ms,
        "price_min": price_min,
        "price_max": price_max,
        "liquidity_peak_usd": liquidity_peak,
        "volume_24h_peak_usd": volume_24h_peak,
        "holders_peak": holders_peak,
    }


def _price_tick(
    *,
    price_usd: float = 1.5,
    liquidity_usd: float = 4_000_000.0,
    volume_24h_usd: float = 800_000.0,
    market_cap_usd: float = 30_000_000.0,
    holders: int = 8000,
    observed_at_ms: int = 1700050000000,
) -> dict[str, Any]:
    return {
        "price_usd": price_usd,
        "liquidity_usd": liquidity_usd,
        "volume_24h_usd": volume_24h_usd,
        "market_cap_usd": market_cap_usd,
        "holders": holders,
        "observed_at_ms": observed_at_ms,
    }


def test_price_action_returns_summary() -> None:
    pool = _FakePool(
        [
            [_price_agg()],
            [_price_tick(price_usd=1.0)],  # first
            [_price_tick(price_usd=2.0)],  # latest
        ]
    )
    ctx = _ctx(pool)

    result = _impl_get_target_price_action(ctx, target_id="asset:sol:abc", hours=24)

    data = result["data"]
    assert data["target_id"] == "asset:sol:abc"
    assert data["hours"] == 24
    assert data["candles_count"] == 12
    assert data["first_price_usd"] == 1.0
    assert data["current_price_usd"] == 2.0
    assert data["price_change_window_pct"] == 100.0
    assert data["volume_24h_usd"] == 800_000.0
    assert data["holders"] == 8000
    assert result["contributed_event_ids"] == []
    assert ctx.tool_calls_count == 1
    # No event id contributed
    assert ctx.contributed_event_ids == set()


def test_price_action_no_ticks_returns_zero_count() -> None:
    pool = _FakePool([[{"candles_count": 0}], [], []])
    ctx = _ctx(pool)

    result = _impl_get_target_price_action(ctx, target_id="asset:sol:abc")

    data = result["data"]
    assert data["candles_count"] == 0
    assert data["current_price_usd"] is None
    assert data["first_price_usd"] is None
    assert data["price_change_window_pct"] is None


def test_price_action_db_error_returns_error_dict() -> None:
    pool = _FakePool(raise_on_connection=RuntimeError("pool exhausted"))
    ctx = _ctx(pool)

    result = _impl_get_target_price_action(ctx, target_id="asset:sol:abc")

    assert "error" in result["data"]
    assert "pool exhausted" in result["data"]["error"]
    assert result["contributed_event_ids"] == []


def test_price_action_empty_target_short_circuits() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool)

    result = _impl_get_target_price_action(ctx, target_id="")

    assert result["data"]["target_id"] == ""
    assert result["data"]["candles_count"] == 0
    assert pool.conn.executed == []


# ---------------------------------------------------------------------------
# get_official_token_profile
# ---------------------------------------------------------------------------


def _profile_row(
    *,
    description: str | None = None,
    symbol: str = "SOL",
    name: str = "Solana",
) -> dict[str, Any]:
    return {
        "asset_id": "asset:sol:abc",
        "provider": "gmgn_dex",
        "symbol": symbol,
        "name": name,
        "description": description,
        "website_url": "https://example.com",
        "twitter_username": "solana",
        "twitter_url": "https://x.com/solana",
        "telegram_url": "https://t.me/solana",
        "logo_url": "https://cdn/logo.png",
        "banner_url": None,
        "updated_at_ms": 1700000000000,
    }


def test_official_profile_with_description_marks_available() -> None:
    pool = _FakePool([[_profile_row(description="L1 chain.")]])
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="asset:sol:abc")

    data = result["data"]
    assert data["symbol"] == "SOL"
    assert data["website"] == "https://example.com"
    assert data["description"] == "L1 chain."
    assert data["description_source_available"] is True
    assert result["contributed_event_ids"] == []


def test_official_profile_empty_description_marks_unavailable() -> None:
    """OQ-3: GMGN description is empirically empty; flag must be False."""
    pool = _FakePool([[_profile_row(description="")]])
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="asset:sol:abc")

    assert result["data"]["description"] is None
    assert result["data"]["description_source_available"] is False


def test_official_profile_null_description_marks_unavailable() -> None:
    pool = _FakePool([[_profile_row(description=None)]])
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="asset:sol:abc")

    assert result["data"]["description"] is None
    assert result["data"]["description_source_available"] is False


def test_official_profile_missing_returns_empty_data() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="asset:sol:abc")

    assert result == {"data": {}, "contributed_event_ids": []}


def test_official_profile_db_error_returns_error_dict() -> None:
    pool = _FakePool(raise_on_connection=RuntimeError("boom"))
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="asset:sol:abc")

    assert "error" in result["data"]
    assert result["contributed_event_ids"] == []


def test_official_profile_empty_target_short_circuits() -> None:
    pool = _FakePool([[]])
    ctx = _ctx(pool)

    result = _impl_get_official_token_profile(ctx, target_id="  ")

    assert result == {"data": {}, "contributed_event_ids": []}
    assert pool.conn.executed == []


# ---------------------------------------------------------------------------
# SDK wrapper smoke
# ---------------------------------------------------------------------------


def test_function_tool_wrappers_expose_expected_names() -> None:
    assert get_target_recent_tweets.name == "get_target_recent_tweets"
    assert get_target_price_action.name == "get_target_price_action"
    assert get_official_token_profile.name == "get_official_token_profile"
    # Description pulled from the docstring; ensure non-empty.
    for tool in (
        get_target_recent_tweets,
        get_target_price_action,
        get_official_token_profile,
    ):
        assert tool.description, f"{tool.name} should expose a description"
