from gmgn_twitter_intel.domains.token_intel.read_models.search_inspect_service import SearchInspectService


def test_search_inspect_returns_token_result_with_agent_brief_and_posts():
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
    )

    result = service.inspect("$BTC", window="24h", scope="all", limit=50, now_ms=1_700_086_400_000)

    assert result["query"]["result_kind"] == "token_result"
    assert result["resolver"]["selected_target"]["target_id"] == "cex_token:BTC"
    assert result["token_result"]["timeline"]["summary"]["posts"] == 1
    assert result["token_result"]["posts"]["items"][0]["event_id"] == "ev_1"
    assert result["token_result"]["market_overlay"]["price_series_type"] == "anchor_line"
    assert result["token_result"]["agent_brief"]["schema_version"] == "search_agent_brief_v1"


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
        "author_handle": "alice",
        "text": phase_text,
        "text_clean": phase_text,
        "canonical_url": None,
        "is_watched": True,
        "received_at_ms": 1_700_086_000_000,
        "attribution_status": "EXACT",
        "confidence": 0.95,
        "reference_json": None,
        "price_observation_id": "price:ev_1",
        "price_provider": "okx_cex",
        "pricefeed_id": "pricefeed:okx:BTC-USDT",
        "price_usd": 70_000,
        "price_quote": 70_000,
        "price_quote_symbol": "USDT",
        "price_observed_at_ms": 1_700_086_000_000,
        "price_observation_lag_ms": 0,
        "price_observation_kind": "message_anchor",
    }
