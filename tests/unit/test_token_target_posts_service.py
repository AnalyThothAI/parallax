from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.domains.token_intel.read_models.token_target_posts_service import TokenTargetPostsService
from gmgn_twitter_intel.domains.token_intel.repositories.token_target_repository import TokenTargetRepository


def test_target_posts_cursor_keeps_same_millisecond_rows_reachable():
    targets = FakeTargets(
        pages={
            None: [
                post_row("event-3", received_at_ms=1_000),
                post_row("event-2", received_at_ms=1_000),
                post_row("event-1", received_at_ms=1_000),
            ],
            (1_000, "event-2"): [post_row("event-1", received_at_ms=1_000)],
        }
    )
    service = TokenTargetPostsService(targets=targets)

    first = service.target_posts(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        post_range="current_window",
        sort="recent",
        limit=2,
        cursor=None,
        now_ms=2_000_000,
    )
    second = service.target_posts(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        post_range="current_window",
        sort="recent",
        limit=2,
        cursor=first["next_cursor"],
        now_ms=2_000_000,
    )

    assert first["query"]["target_type"] == "CexToken"
    assert first["query"]["target_id"] == "cex_token:BTC"
    assert [item["event_id"] for item in first["items"]] == ["event-3", "event-2"]
    assert isinstance(first["items"][0]["attribution_confidence"], float)
    assert first["items"][0]["stage_id"]
    assert first["items"][0]["stage_phase"] in {"seed", "ignition", "concentration"}
    assert first["items"][0]["author_role"] in {"seed", "early_amplifier", "repeater"}
    assert isinstance(first["items"][0]["is_stage_representative"], bool)
    assert "confidence" not in first["items"][0]
    assert first["items"][0]["price"]["status"] == "ready"
    assert first["items"][0]["price"]["price_usd"] == 70_000
    assert first["items"][0]["post_quality"]["score_version"] == "post_quality_v1"
    assert first["next_cursor"] == "1000:event-2"
    assert targets.seen_cursors[-1] == (1_000, "event-2")
    assert [item["event_id"] for item in second["items"]] == ["event-1"]


def test_target_repository_reads_post_prices_from_enriched_events_and_market_ticks():
    conn = FakeConn(rows=[])

    TokenTargetRepository(conn).timeline_rows(
        target_type="Asset",
        target_id="asset:pepe",
        since_ms=1_700_000_000_000,
        watched_only=False,
        limit=25,
    )

    assert "enriched_events" in conn.sql
    assert "market_ticks" in conn.sql
    assert "price_observations" not in conn.sql
    assert "message_anchor" not in conn.sql
    assert "price_observation" not in conn.sql
    assert "market_tick_id" in conn.sql
    assert "market_tick_lag_ms" in conn.sql


class FakeTargets:
    def __init__(self, *, pages):
        self.pages = pages
        self.seen_cursors = []

    def timeline_rows(self, *, target_type, target_id, since_ms, watched_only, limit, cursor=None):
        self.seen_cursors.append(cursor)
        return self.pages.get(cursor, [])[:limit]


def post_row(event_id: str, *, received_at_ms: int) -> dict:
    return {
        "event_id": event_id,
        "tweet_id": event_id,
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "symbol": "BTC",
        "author_handle": "alice",
        "text": "$BTC",
        "text_clean": "$BTC",
        "canonical_url": f"https://x.com/alice/status/{event_id}",
        "is_watched": False,
        "received_at_ms": received_at_ms,
        "attribution_status": "EXACT",
        "confidence": Decimal("0.95"),
        "reference_json": None,
        "market_tick_id": f"tick:{event_id}",
        "market_tick_provider": "okx_cex",
        "pricefeed_id": "pricefeed:okx:BTC-USDT",
        "price_usd": Decimal("70000"),
        "price_quote": Decimal("70000"),
        "price_quote_symbol": "USDT",
        "market_tick_observed_at_ms": received_at_ms + 1_000,
        "market_tick_lag_ms": 1_000,
        "market_capture_method": "tier1_ws",
    }


class FakeConn:
    def __init__(self, *, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or ()
        return self

    def fetchall(self):
        return self.rows
