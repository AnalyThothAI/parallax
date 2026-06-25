import pytest

from parallax.domains.token_intel.read_models.search_service import (
    SearchCursorError,
    SearchScopeError,
    SearchService,
    SearchWindowError,
)


def test_search_requires_explicit_query_boundaries_before_repository_call():
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(TypeError):
        SearchService(search_query=query).search("btc")

    assert query.resolved_symbols == []
    assert query.route_limits == []
    assert query.target_limits == []


def test_search_allows_zero_limit_with_empty_page_and_target_lookahead() -> None:
    query = FakeSearchQuery(target_hits=[hit("event-1", route="target", route_rank=1, received_at_ms=3000)])

    result = SearchService(search_query=query).search("btc", limit=0, scope="all", window="24h")

    assert result.ok is True
    assert result.items == []
    assert result.page["returned_count"] == 0
    assert result.page["has_more"] is True
    assert query.target_limits == [1]


@pytest.mark.parametrize("limit", [-1, True, "20"])
def test_search_rejects_malformed_limit_before_repository_call(limit: object) -> None:
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(ValueError, match="search_limit_required"):
        SearchService(search_query=query).search(
            "btc",
            limit=limit,  # type: ignore[arg-type]
            scope="all",
            window="24h",
        )

    assert query.resolved_symbols == []
    assert query.route_limits == []
    assert query.target_limits == []


def test_search_merges_target_and_lexical_hits_by_event_id():
    query = FakeSearchQuery(
        route_hits=[
            hit("event-1", route="target", route_rank=1, route_score=1.0, received_at_ms=2000),
            hit("event-1", route="lexical", route_rank=1, route_score=0.5, received_at_ms=2000),
        ]
    )

    result = SearchService(search_query=query).search("macro market", limit=20, scope="all", window="24h")

    assert result.ok is True
    assert len(result.items) == 1
    assert result.items[0]["match_type"] == "target"
    assert result.items[0]["route_scores"] == {"target": 1.0, "lexical": 0.5}
    assert set(result.items[0]["match_reasons"]) == {"target:CexToken", "fts"}


def test_search_paginates_with_next_cursor():
    query = FakeSearchQuery(
        target_hits=[
            hit("event-1", route="target", route_rank=1, received_at_ms=3000),
            hit("event-2", route="target", route_rank=2, received_at_ms=2000),
        ]
    )

    first = SearchService(search_query=query).search("btc", limit=1, scope="all", window="24h")
    second = SearchService(search_query=query).search(
        "btc",
        limit=1,
        scope="all",
        window="24h",
        cursor=first.page["next_cursor"],
    )

    assert first.page["has_more"] is True
    assert first.items[0]["event"]["event_id"] == "event-1"
    assert second.items[0]["event"]["event_id"] == "event-2"
    assert query.target_after_values == [None, {"status_rank": 0, "received_at_ms": 3000, "event_id": "event-1"}]


def test_search_target_cursor_does_not_expand_route_window_from_the_top():
    query = FakeSearchQuery(
        target_hits=[
            hit(f"event-{index}", route="target", route_rank=index, received_at_ms=10_000 - index)
            for index in range(1, 500)
        ]
    )

    first = SearchService(search_query=query).search("btc", limit=50, scope="all", window="24h")
    SearchService(search_query=query).search(
        "btc",
        limit=50,
        scope="all",
        window="24h",
        cursor=first.page["next_cursor"],
    )

    assert query.target_limits == [51, 51]
    assert query.target_after_values[1] == {
        "status_rank": 0,
        "received_at_ms": 9950,
        "event_id": "event-50",
    }


def test_search_rejects_invalid_cursor():
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(SearchCursorError):
        SearchService(search_query=query).search(
            "btc",
            limit=20,
            scope="all",
            window="24h",
            cursor="not-a-cursor",
        )


def test_search_rejects_invalid_scope_before_repository_call():
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(SearchScopeError):
        SearchService(search_query=query).search("btc", limit=20, scope="everything", window="24h")

    assert query.resolved_symbols == []
    assert query.route_limits == []
    assert query.target_limits == []


def test_search_rejects_invalid_window_before_repository_call():
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(SearchWindowError):
        SearchService(search_query=query).search("btc", limit=20, scope="all", window="7d")

    assert query.resolved_symbols == []
    assert query.route_limits == []
    assert query.target_limits == []


def test_search_routes_symbol_and_cashtag_to_same_target_candidates():
    bare_query = FakeSearchQuery(route_hits=[])
    cashtag_query = FakeSearchQuery(route_hits=[])

    SearchService(search_query=bare_query).search("btc", limit=20, scope="all", window="24h")
    SearchService(search_query=cashtag_query).search("$btc", limit=20, scope="all", window="24h")

    assert bare_query.resolved_symbols == ["BTC"]
    assert cashtag_query.resolved_symbols == ["BTC"]


def test_search_routes_symbol_or_query_to_targets():
    query = FakeSearchQuery(target_hits=[hit("event-1", route="target", route_rank=1, received_at_ms=3000)])

    result = SearchService(search_query=query).search("btc OR eth", limit=20, scope="all", window="24h")

    assert result.items[0]["event"]["event_id"] == "event-1"
    assert query.resolved_symbol_batches == [("BTC", "ETH")]
    assert query.resolved_symbols == []


def test_search_expands_known_symbol_aliases_for_lexical_route():
    query = FakeSearchQuery(route_hits=[])

    result = SearchService(search_query=query).search("bitcoin", limit=20, scope="all", window="24h")

    assert result.query["lexical_query"] == "btc OR bitcoin OR bitcoins OR 比特币 OR xbt"
    assert query.resolved_symbols == ["BTC"]


def test_search_fuzzy_alias_typo_routes_to_target():
    query = FakeSearchQuery(target_hits=[hit("event-1", route="target", route_rank=1, received_at_ms=3000)])

    result = SearchService(search_query=query).search("bitcon", limit=20, scope="all", window="24h")

    assert result.items[0]["event"]["event_id"] == "event-1"
    assert query.resolved_symbols == ["BITCON", "BTC"]


def test_search_applies_requested_window_to_target_route():
    query = FakeSearchQuery(target_hits=[hit("event-1", route="target", route_rank=1, received_at_ms=3000)])

    SearchService(search_query=query).search(
        "btc",
        limit=20,
        scope="all",
        window="24h",
        now_ms=1_700_086_400_000,
    )

    assert query.target_since_values == [1_700_000_000_000]


def test_search_applies_requested_window_to_keyword_route():
    query = FakeSearchQuery(route_hits=[hit("event-1", route="lexical", route_rank=1, received_at_ms=3000)])

    SearchService(search_query=query).search(
        "挖矿",
        limit=20,
        scope="all",
        window="4h",
        now_ms=1_700_014_400_000,
    )

    assert query.route_since_values == [1_700_000_000_000]


class FakeSearchQuery:
    def __init__(self, *, route_hits=None, target_hits=None):
        self._route_hits = route_hits or []
        self._target_hits = target_hits if target_hits is not None else self._route_hits
        self.resolved_symbols: list[str | None] = []
        self.resolved_symbol_batches: list[tuple[str, ...]] = []
        self.route_intents = []
        self.route_limits: list[int] = []
        self.target_limits: list[int] = []
        self.target_after_values: list[dict | None] = []
        self.route_since_values: list[int] = []
        self.target_since_values: list[int] = []

    def resolve_targets(self, intent):
        self.resolved_symbols.append(intent.symbol)
        if intent.symbol == "BTC":
            return [
                {
                    "target_type": "CexToken",
                    "target_id": "cex_token:BTC",
                    "symbol": "BTC",
                    "status": "resolved",
                    "source": "cex_token",
                    "reason": "CONFIRMED_CEX_TOKEN",
                }
            ]
        return []

    def resolve_symbols(self, symbols):
        self.resolved_symbol_batches.append(tuple(symbols))
        candidates = []
        for symbol in symbols:
            candidates.extend(self.resolve_targets(type("Intent", (), {"symbol": symbol})()))
        self.resolved_symbols.clear()
        return candidates

    def route_hits(self, *, intent, target_candidates, watched_only, route_limit, since_ms):
        self.route_intents.append(intent)
        self.route_limits.append(route_limit)
        self.route_since_values.append(since_ms)
        return self._route_hits[:route_limit]

    def target_hits_page(self, target_candidates, *, watched_only, limit, after, since_ms):
        self.target_limits.append(limit)
        self.target_after_values.append(after)
        self.target_since_values.append(since_ms)
        hits = self._target_hits
        if after:
            event_ids = [str(item["event_id"]) for item in hits]
            start = event_ids.index(str(after["event_id"])) + 1
            hits = hits[start:]
        return hits[:limit]


def hit(
    event_id: str,
    *,
    route: str,
    route_rank: int,
    route_score: float = 1.0,
    received_at_ms: int,
):
    target = None
    reasons = ["fts"]
    if route == "target":
        target = {
            "target_type": "CexToken",
            "target_id": "cex_token:BTC",
            "symbol": "BTC",
            "status": "resolved",
            "source": "token_intent_resolutions",
            "reason": "TARGET_ROUTE",
        }
        reasons = ["target:CexToken"]
    return {
        "event_id": event_id,
        "event": {"event_id": event_id, "received_at_ms": received_at_ms},
        "route": route,
        "route_rank": route_rank,
        "route_score": route_score,
        "match_reasons": reasons,
        "target": target,
        "target_status_rank": 0,
        "received_at_ms": received_at_ms,
    }
