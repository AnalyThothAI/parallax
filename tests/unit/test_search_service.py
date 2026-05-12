import pytest

from gmgn_twitter_intel.domains.token_intel.read_models.search_service import SearchCursorError, SearchService


def test_search_merges_target_and_lexical_hits_by_event_id():
    query = FakeSearchQuery(
        route_hits=[
            hit("event-1", route="target", route_rank=1, route_score=1.0, received_at_ms=2000),
            hit("event-1", route="lexical", route_rank=1, route_score=0.5, received_at_ms=2000),
        ]
    )

    result = SearchService(search_query=query).search("btc", limit=20)

    assert result.ok is True
    assert len(result.items) == 1
    assert result.items[0]["match_type"] == "target"
    assert result.items[0]["route_scores"] == {"target": 1.0, "lexical": 0.5}
    assert set(result.items[0]["match_reasons"]) == {"target:CexToken", "fts"}


def test_search_paginates_with_next_cursor():
    query = FakeSearchQuery(
        route_hits=[
            hit("event-1", route="target", route_rank=1, received_at_ms=3000),
            hit("event-2", route="target", route_rank=2, received_at_ms=2000),
        ]
    )

    first = SearchService(search_query=query).search("btc", limit=1)
    second = SearchService(search_query=query).search("btc", limit=1, cursor=first.page["next_cursor"])

    assert first.page["has_more"] is True
    assert first.items[0]["event"]["event_id"] == "event-1"
    assert second.items[0]["event"]["event_id"] == "event-2"


def test_search_rejects_invalid_cursor():
    query = FakeSearchQuery(route_hits=[])

    with pytest.raises(SearchCursorError):
        SearchService(search_query=query).search("btc", cursor="not-a-cursor")


def test_search_routes_symbol_and_cashtag_to_same_target_candidates():
    bare_query = FakeSearchQuery(route_hits=[])
    cashtag_query = FakeSearchQuery(route_hits=[])

    SearchService(search_query=bare_query).search("btc", limit=20)
    SearchService(search_query=cashtag_query).search("$btc", limit=20)

    assert bare_query.resolved_symbols == ["BTC"]
    assert cashtag_query.resolved_symbols == ["BTC"]


def test_search_expands_known_symbol_aliases_for_lexical_route():
    query = FakeSearchQuery(route_hits=[])

    SearchService(search_query=query).search("bitcoin", limit=20)

    assert query.route_intents[-1].lexical_query == "btc OR bitcoin OR bitcoins OR 比特币 OR xbt"
    assert query.resolved_symbols == ["BTC"]


class FakeSearchQuery:
    def __init__(self, *, route_hits):
        self._route_hits = route_hits
        self.resolved_symbols: list[str | None] = []
        self.route_intents = []

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

    def route_hits(self, *, intent, target_candidates, watched_only, route_limit):
        self.route_intents.append(intent)
        return self._route_hits[:route_limit]


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
        "received_at_ms": received_at_ms,
    }
