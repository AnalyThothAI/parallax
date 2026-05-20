from __future__ import annotations

from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.token_intel.read_models.token_case_service import (
    TokenCaseInvalidScope,
    TokenCaseService,
    TokenCaseTargetNotFound,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_target_repository import TokenTargetRepository

TARGET_ID = "asset:solana:token:hansa"
NOW_MS = 1_700_000_060_000


def test_token_case_dossier_builds_all_sections_for_resolved_asset():
    service = TokenCaseService(
        targets=FakeTargets(rows=[target_row("event-2"), target_row("event-1")]),
        profiles=FakeProfiles(profile={"status": "ready", "provider": "test_profile"}),
        live_price_gateway=FakeLivePriceGateway(),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=2,
        now_ms=NOW_MS,
    )

    assert list(dossier) == ["target", "profile", "timeline", "posts", "market_live"]
    assert dossier["target"]["target_id"] == TARGET_ID
    assert dossier["profile"]["status"] == "ready"
    assert dossier["timeline"]["summary"]["posts"] == 2
    assert dossier["posts"]["returned_count"] == 2
    assert dossier["market_live"]["status"] in {"ready", "missing"}


def test_token_case_dossier_raises_not_found_for_unknown_target():
    service = TokenCaseService(
        targets=FakeTargets(rows=[], identity=None),
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(),
    )

    with pytest.raises(TokenCaseTargetNotFound):
        service.dossier(
            target_type="Asset",
            target_id="asset:solana:token:unknown",
            window="1h",
            scope="all",
            posts_limit=2,
            now_ms=NOW_MS,
        )


def test_token_case_accepts_watched_scope_alias():
    targets = FakeTargets(rows=[target_row("event-1", is_watched=True)])
    service = TokenCaseService(
        targets=targets,
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="watched",
        posts_limit=1,
        now_ms=NOW_MS,
    )

    assert dossier["posts"]["query"]["scope"] == "watched"
    assert {call["watched_only"] for call in targets.timeline_calls} == {True}


def test_token_case_rejects_invalid_scope():
    service = TokenCaseService(
        targets=FakeTargets(rows=[]),
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(),
    )

    with pytest.raises(TokenCaseInvalidScope):
        service.dossier(
            target_type="Asset",
            target_id=TARGET_ID,
            window="1h",
            scope="private",
            posts_limit=2,
            now_ms=NOW_MS,
        )


def test_token_case_uses_missing_live_market_when_gateway_returns_none():
    service = TokenCaseService(
        targets=FakeTargets(rows=[target_row("event-1")]),
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(snapshot=None),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=2,
        now_ms=NOW_MS,
    )

    assert dossier["market_live"]["status"] == "missing"
    assert dossier["market_live"]["target_type"] == "Asset"
    assert dossier["market_live"]["target_id"] == TARGET_ID


def test_token_case_uses_latest_market_tick_when_live_gateway_is_missing():
    service = TokenCaseService(
        targets=FakeTargets(
            rows=[target_row("event-1")],
            market_tick={
                "source_provider": "gmgn_dex_quote",
                "price_usd": Decimal("0.000028486255"),
                "market_cap_usd": Decimal("28486.254971513744"),
                "liquidity_usd": Decimal("18230.629102955"),
                "volume_24h_usd": Decimal("26133.3652616"),
                "open_interest_usd": Decimal("1200000.5"),
                "holders": 551,
                "observed_at_ms": NOW_MS - 2_000,
                "received_at_ms": NOW_MS - 1_000,
            },
        ),
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(snapshot=None),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=2,
        now_ms=NOW_MS,
    )

    assert dossier["market_live"]["status"] == "ready"
    assert dossier["market_live"]["provider"] == "gmgn_dex_quote"
    assert dossier["market_live"]["price_usd"] == 0.000028486255
    assert dossier["market_live"]["market_cap_usd"] == 28486.254971513744
    assert dossier["market_live"]["liquidity_usd"] == 18230.629102955
    assert dossier["market_live"]["volume_24h_usd"] == 26133.3652616
    assert dossier["market_live"]["open_interest_usd"] == 1200000.5
    assert dossier["market_live"]["holders"] == 551
    assert dossier["market_live"]["age_ms"] == 1_000
    assert "agent_brief" not in dossier


def test_token_case_keeps_profile_and_market_context_without_agent_brief():
    service = TokenCaseService(
        targets=FakeTargets(
            rows=[target_row("event-1")],
            market_tick={
                "source_provider": "gmgn_dex_quote",
                "price_usd": Decimal("0.000028486255"),
                "market_cap_usd": Decimal("28486.254971513744"),
                "liquidity_usd": Decimal("18230.629102955"),
                "volume_24h_usd": Decimal("26133.3652616"),
                "holders": 551,
                "observed_at_ms": NOW_MS - 2_000,
                "received_at_ms": NOW_MS - 1_000,
            },
        ),
        profiles=FakeProfiles(
            profile={
                "status": "ready",
                "provider": "gmgn_dex_profile",
                "identity": {"name": "Hansa"},
                "links": {"website_url": "https://hansa.example"},
                "source": {"raw_available": True},
            }
        ),
        live_price_gateway=FakeLivePriceGateway(snapshot=None),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=2,
        now_ms=NOW_MS,
    )

    assert dossier["profile"]["status"] == "ready"
    assert dossier["market_live"]["status"] == "ready"
    assert "agent_brief" not in dossier


def test_token_case_uses_unsupported_live_market_without_gateway():
    service = TokenCaseService(
        targets=FakeTargets(rows=[target_row("event-1")]),
        profiles=FakeProfiles(),
        live_price_gateway=None,
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=2,
        now_ms=NOW_MS,
    )

    assert dossier["market_live"]["status"] == "unsupported"


def test_token_case_limits_first_posts_page_to_posts_limit():
    service = TokenCaseService(
        targets=FakeTargets(rows=[target_row("event-2"), target_row("event-1")]),
        profiles=FakeProfiles(),
        live_price_gateway=FakeLivePriceGateway(),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id=TARGET_ID,
        window="1h",
        scope="all",
        posts_limit=1,
        now_ms=NOW_MS,
    )

    assert dossier["posts"]["returned_count"] == 1


def test_token_target_repository_target_identity_maps_asset_row():
    conn = FakeConn(
        row={
            "target_type": "Asset",
            "target_id": TARGET_ID,
            "symbol": "HANSA",
            "name": "Hansa",
            "chain_id": "solana",
            "address": "hansa",
            "status": "canonical",
            "pricefeed_id": "pricefeed:gmgn:hansa",
            "provider": "gmgn",
            "native_market_id": "solana:hansa",
            "quote_symbol": "USD",
            "feed_type": "dex_spot",
        }
    )
    repo = TokenTargetRepository(conn)

    result = repo.target_identity(target_type="Asset", target_id=TARGET_ID)

    assert result == {
        "target_type": "Asset",
        "target_id": TARGET_ID,
        "symbol": "HANSA",
        "name": "Hansa",
        "chain_id": "solana",
        "address": "hansa",
        "status": "canonical",
        "source": "registry_assets",
        "reason": "TARGET_ID",
        "pricefeed_id": "pricefeed:gmgn:hansa",
        "provider": "gmgn",
        "native_market_id": "solana:hansa",
        "quote_symbol": "USD",
        "feed_type": "dex_spot",
    }
    assert "FROM registry_assets" in conn.sql
    assert conn.params == [TARGET_ID]


def test_token_target_repository_target_identity_escapes_cex_feed_like_pattern():
    conn = FakeConn(
        row={
            "target_type": "CexToken",
            "target_id": "cex_token:BTC",
            "symbol": "BTC",
            "name": None,
            "chain_id": None,
            "address": None,
            "status": "canonical",
            "pricefeed_id": "pricefeed:okx:BTC-USDT",
            "provider": "okx",
            "native_market_id": "BTC-USDT",
            "quote_symbol": "USDT",
            "feed_type": "cex_spot",
        }
    )
    repo = TokenTargetRepository(conn)

    result = repo.target_identity(target_type="CexToken", target_id="cex_token:BTC")

    assert result["source"] == "cex_tokens"
    assert "price_feeds.feed_type LIKE 'cex_%%'" in conn.sql
    assert conn.params == ["cex_token:BTC"]


class FakeTargets:
    def __init__(self, *, rows, identity=None, market_tick=None):
        self.rows = rows
        self.identity = identity if identity is not None else target_identity()
        self.market_tick = market_tick
        self.timeline_calls = []

    def target_identity(self, *, target_type, target_id):
        if self.identity is None:
            return None
        if self.identity["target_type"] != target_type or self.identity["target_id"] != target_id:
            return None
        return self.identity

    def timeline_rows(self, *, target_type, target_id, since_ms, watched_only, limit, cursor=None):
        self.timeline_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "since_ms": since_ms,
                "watched_only": watched_only,
                "limit": limit,
                "cursor": cursor,
            }
        )
        rows = [
            row
            for row in self.rows
            if row["target_type"] == target_type
            and row["target_id"] == target_id
            and row["received_at_ms"] >= since_ms
            and (not watched_only or row["is_watched"])
        ]
        return rows[:limit]

    def latest_market_tick(self, *, target_type, target_id):
        if self.identity is None:
            return None
        if self.identity["target_type"] != target_type or self.identity["target_id"] != target_id:
            return None
        return self.market_tick


class FakeProfiles:
    def __init__(self, *, profile=None):
        self.profile = profile or {"status": "missing"}

    def profile_for_target(self, *, target_type, target_id):
        return self.profile


class FakeLivePriceGateway:
    def __init__(self, *, snapshot="ready"):
        self.snapshot_payload = snapshot

    def snapshot(self, *, target_type, target_id, now_ms=None):
        if self.snapshot_payload is None:
            return None
        return {
            "target_type": target_type,
            "target_id": target_id,
            "status": "ready",
            "price_usd": 0.42,
            "market_cap_usd": 4_200_000,
            "liquidity_usd": 500_000,
            "holders": None,
            "observed_at_ms": now_ms,
            "provider": "test",
        }


class FakeConn:
    def __init__(self, *, row):
        self.row = row
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = list(params or [])
        return self

    def fetchone(self):
        return self.row


def target_identity() -> dict:
    return {
        "target_type": "Asset",
        "target_id": TARGET_ID,
        "symbol": "HANSA",
        "name": "Hansa",
        "chain_id": "solana",
        "address": "hansa",
        "status": "canonical",
        "source": "registry_assets",
        "reason": "TARGET_ID",
        "pricefeed_id": "pricefeed:gmgn:hansa",
        "provider": "gmgn",
        "native_market_id": "solana:hansa",
        "quote_symbol": "USD",
        "feed_type": "dex_spot",
    }


def target_row(event_id: str, *, is_watched: bool = True) -> dict:
    return {
        "event_id": event_id,
        "tweet_id": event_id,
        "target_type": "Asset",
        "target_id": TARGET_ID,
        "symbol": "HANSA",
        "chain_id": "solana",
        "address": "hansa",
        "author_handle": "alice",
        "text": "$HANSA first social wave",
        "text_clean": "$HANSA first social wave",
        "canonical_url": None,
        "is_watched": is_watched,
        "received_at_ms": 1_700_000_000_000,
        "attribution_status": "EXACT",
        "confidence": Decimal("0.95"),
        "reference_json": None,
        "market_tick_id": f"tick:{event_id}",
        "market_tick_provider": "gmgn",
        "pricefeed_id": "pricefeed:gmgn:hansa",
        "price_usd": Decimal("0.42"),
        "price_quote": Decimal("0.42"),
        "price_quote_symbol": "USD",
        "market_tick_observed_at_ms": 1_700_000_000_000,
        "market_tick_lag_ms": 0,
        "market_capture_method": "tier1_ws",
    }
