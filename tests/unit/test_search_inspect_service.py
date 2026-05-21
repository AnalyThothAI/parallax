from gmgn_twitter_intel.domains.token_intel.read_models.search_inspect_service import SearchInspectService

LEGACY_MARKET_FIELD = "market_overlay"


def test_search_inspect_returns_canonical_token_result_without_agent_brief():
    service = SearchInspectService(
        search_query=FakeSearchQuery(
            candidates=[
                {
                    "target_type": "CexToken",
                    "target_id": "cex_token:BTC",
                    "symbol": "BTC",
                    "status": "resolved",
                    "source": "cex_token",
                    "reason": "CONFIRMED_CEX_TOKEN",
                }
            ],
            target_hits=[hit("ev_1", route="target", target_id="cex_token:BTC")],
        ),
        token_radar=FakeTokenRadar(),
        targets=FakeTargets(rows=[target_row("ev_1", phase_text="$BTC first social wave")]),
        profiles=FakeProfiles(profile={"status": "ready", "provider": "test_profile"}),
        live_price_gateway=FakeLivePriceGateway(),
    )

    result = service.inspect("$BTC", window="24h", scope="all", limit=50, now_ms=1_700_086_400_000)

    assert result["query"]["result_kind"] == "token_result"
    assert result["resolver"]["selected_target"]["target_id"] == "cex_token:BTC"
    assert list(result["token_result"]) == ["target", "profile", "timeline", "posts", "market_live"]
    assert result["token_result"]["timeline"]["summary"]["posts"] == 1
    assert result["token_result"]["timeline"]["market_candles"]["target_type"] == "CexToken"
    assert result["token_result"]["posts"]["items"][0]["event_id"] == "ev_1"
    assert result["token_result"]["profile"] == {"status": "ready", "provider": "test_profile"}
    assert "agent_brief" not in result["token_result"]
    assert result["token_result"]["market_live"]["status"] == "ready"
    assert "radar_item" not in result["token_result"]
    assert LEGACY_MARKET_FIELD not in result["token_result"]


def test_search_inspect_returns_topic_result_for_keyword_query():
    service = SearchInspectService(
        search_query=FakeSearchQuery(
            route_hits=[
                hit("ev_701", route="lexical", author_handle="minerwatch", text="DePIN 挖矿"),
                hit("ev_744", route="lexical", author_handle="aiinfra", text="AI compute mining"),
            ]
        ),
        token_radar=FakeTokenRadar(),
        targets=FakeTargets(rows=[]),
        profiles=FakeProfiles(),
    )

    result = service.inspect("挖矿", window="24h", scope="all", limit=50, now_ms=1_700_086_400_000)

    assert result["query"]["result_kind"] == "topic_result"
    assert result["topic_result"]["summary"] == {"posts": 2, "authors": 2}
    assert result["topic_result"]["agent_brief"]["bull_bear"]["stance"] == "research"


def test_search_inspect_returns_ambiguous_result_without_selecting_target():
    service = SearchInspectService(
        search_query=FakeSearchQuery(
            candidates=[
                {
                    "target_type": "Asset",
                    "target_id": "asset:solana:dog",
                    "symbol": "DOG",
                    "status": "ambiguous",
                    "source": "asset_identity_current",
                    "reason": "CANONICAL_SYMBOL_MATCH",
                },
                {
                    "target_type": "Asset",
                    "target_id": "asset:base:dog",
                    "symbol": "DOG",
                    "status": "ambiguous",
                    "source": "asset_identity_current",
                    "reason": "CANONICAL_SYMBOL_MATCH",
                },
            ],
            route_hits=[hit("ev_dog", route="lexical", text="$DOG discussion")],
        ),
        token_radar=FakeTokenRadar(),
        targets=FakeTargets(rows=[]),
        profiles=FakeProfiles(),
    )

    result = service.inspect("$DOG", window="24h", scope="all", limit=50, now_ms=1_700_086_400_000)

    assert result["query"]["result_kind"] == "ambiguous_result"
    assert result["resolver"]["selected_target"] is None
    assert len(result["ambiguous_result"]["candidates"]) == 2
    assert result["ambiguous_result"]["agent_brief"]["schema_version"] == "search_agent_brief_v1"


def test_search_inspect_returns_empty_result_for_empty_query():
    service = SearchInspectService(
        search_query=FakeSearchQuery(),
        token_radar=FakeTokenRadar(),
        targets=FakeTargets(rows=[]),
        profiles=FakeProfiles(),
    )

    result = service.inspect("   ", window="24h", scope="all", limit=50, now_ms=1_700_086_400_000)

    assert result["query"]["result_kind"] == "empty_result"
    assert result["token_result"] is None
    assert result["topic_result"] is None
    assert result["ambiguous_result"] is None


class FakeSearchQuery:
    def __init__(self, *, candidates=None, route_hits=None, target_hits=None):
        self.candidates = candidates or []
        self._route_hits = route_hits or []
        self._target_hits = target_hits if target_hits is not None else self._route_hits

    def resolve_targets(self, intent):
        return self.candidates

    def route_hits(self, *, intent, target_candidates, watched_only, route_limit, since_ms):
        return self._route_hits[:route_limit]

    def target_hits_page(self, target_candidates, *, watched_only, limit, after, since_ms):
        return self._target_hits[:limit]


class FakeTargets:
    def __init__(self, *, rows):
        self.rows = rows

    def target_identity(self, *, target_type, target_id):
        for row in self.rows:
            if row["target_type"] == target_type and row["target_id"] == target_id:
                return {
                    "target_type": target_type,
                    "target_id": target_id,
                    "symbol": row["symbol"],
                    "name": None,
                    "chain_id": row.get("chain_id"),
                    "address": row.get("address"),
                    "status": "resolved",
                    "source": "test",
                    "reason": "TARGET_ID",
                    "pricefeed_id": row.get("pricefeed_id"),
                    "provider": row.get("provider"),
                    "native_market_id": row.get("native_market_id"),
                    "quote_symbol": row.get("quote_symbol"),
                    "feed_type": row.get("feed_type"),
                }
        return None

    def timeline_rows(self, *, target_type, target_id, since_ms, watched_only, limit, cursor=None):
        return [
            row
            for row in self.rows
            if row["target_type"] == target_type and row["target_id"] == target_id and row["received_at_ms"] >= since_ms
        ][:limit]


class FakeTokenRadar:
    def latest_coverage(self, *, projection_version, windows, scopes):
        return {
            (window, scope): {
                "status": "ready",
                "reason": None,
                "row_count": 0,
                "source_rows": 0,
                "computed_at_ms": 1_700_086_400_000,
            }
            for window in windows
            for scope in scopes
        }

    def latest_rows(self, *, window, scope, limit, projection_version):
        return []


class FakeProfiles:
    def __init__(self, *, profile=None):
        self.profile = profile

    def profile_for_target(self, *, target_type, target_id):
        return self.profile

    def profiles_for_targets(self, targets):
        return {}


class FakeLivePriceGateway:
    def snapshot(self, *, target_type, target_id, now_ms=None):
        return {
            "target_type": target_type,
            "target_id": target_id,
            "status": "ready",
            "price_usd": 70_000,
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
            "observed_at_ms": now_ms,
            "provider": "test",
        }


def hit(
    event_id: str,
    *,
    route: str,
    target_id: str | None = None,
    author_handle: str = "alice",
    text: str = "$BTC looks strong",
) -> dict:
    target = None
    if target_id:
        target = {
            "target_type": "CexToken",
            "target_id": target_id,
            "symbol": "BTC",
            "status": "resolved",
            "source": "token_intent_resolutions",
            "reason": "TARGET_ROUTE",
        }
    return {
        "event_id": event_id,
        "event": {
            "event_id": event_id,
            "received_at_ms": 1_700_086_000_000,
            "author_handle": author_handle,
            "text_clean": text,
            "canonical_url": None,
        },
        "route": route,
        "route_rank": 1,
        "route_score": 1.0,
        "match_reasons": [route],
        "target": target,
        "target_status_rank": 0,
        "received_at_ms": 1_700_086_000_000,
    }


def target_row(event_id: str, *, phase_text: str) -> dict:
    return {
        "event_id": event_id,
        "tweet_id": event_id,
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "symbol": "BTC",
        "chain_id": None,
        "address": None,
        "author_handle": "alice",
        "text": phase_text,
        "text_clean": phase_text,
        "canonical_url": None,
        "is_watched": True,
        "received_at_ms": 1_700_086_000_000,
        "attribution_status": "EXACT",
        "confidence": 0.95,
        "reference_json": None,
        "market_tick_id": "tick:ev_1",
        "market_tick_provider": "binance_cex",
        "provider": "binance",
        "native_market_id": "BTCUSDT",
        "pricefeed_id": "pricefeed:binance:BTCUSDT",
        "quote_symbol": "USDT",
        "feed_type": "cex_spot",
        "price_usd": 70_000,
        "price_quote": 70_000,
        "price_quote_symbol": "USDT",
        "market_tick_observed_at_ms": 1_700_086_000_000,
        "market_tick_lag_ms": 0,
        "market_capture_method": "tier1_ws",
    }
