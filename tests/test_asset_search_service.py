from __future__ import annotations

from gmgn_twitter_intel.retrieval.asset_search_service import AssetSearchService


def test_symbol_search_returns_unresolved_mentions():
    service = AssetSearchService(
        evidence=FakeEvidence(),
        assets=FakeAssets(
            candidates=[],
            mention_events=[
                {
                    "event_id": "event-1",
                    "received_at_ms": 1000,
                    "normalized_symbol": "MIRROR",
                    "attribution_status": "unresolved",
                }
            ],
        ),
    )

    result = service.search("$MIRROR", limit=20)

    assert result.ok is True
    assert result.error is None
    assert result.resolution["status"] == "unresolved"
    assert result.items[0]["match_type"] == "asset_mention"
    assert result.items[0]["event"]["event_id"] == "event-1"


def test_symbol_search_returns_ambiguous_candidates_and_events():
    service = AssetSearchService(
        evidence=FakeEvidence(),
        assets=FakeAssets(
            candidates=[
                {"asset_id": "asset:dex:solana:dog", "identity_status": "resolved"},
                {"asset_id": "asset:dex:base:dog", "identity_status": "resolved"},
            ],
            mention_events=[{"event_id": "event-1", "received_at_ms": 1000, "normalized_symbol": "DOG"}],
        ),
    )

    result = service.search("$DOG", limit=20)

    assert result.ok is True
    assert result.resolution["status"] == "ambiguous"
    assert len(result.candidates) == 2
    assert result.items


def test_symbol_search_reports_resolved_when_single_resolved_candidate_exists():
    service = AssetSearchService(
        evidence=FakeEvidence(),
        assets=FakeAssets(
            candidates=[
                {
                    "asset_id": "asset:cex:BTC",
                    "identity_status": "resolved",
                    "venue_id": "venue:cex:okx:SPOT:BTC-USDT",
                }
            ],
            mention_events=[{"event_id": "event-1", "received_at_ms": 1000, "normalized_symbol": "BTC"}],
        ),
    )

    result = service.search("$BTC", limit=20)

    assert result.ok is True
    assert result.resolution["status"] == "resolved"
    assert result.candidates[0]["asset_id"] == "asset:cex:BTC"


def test_text_search_still_uses_fts():
    evidence = FakeEvidence(fts_events=[{"event_id": "event-text", "score": 0.42}])
    service = AssetSearchService(evidence=evidence, assets=FakeAssets(candidates=[], mention_events=[]))

    result = service.search("mirror", limit=20)

    assert result.ok is True
    assert result.items[0]["match_type"] == "fts"
    assert result.items[0]["event"]["event_id"] == "event-text"
    assert evidence.fts_queries == ["mirror"]


class FakeAssets:
    def __init__(self, *, candidates, mention_events):
        self._candidates = candidates
        self._mention_events = mention_events

    def candidates_for_symbol(self, symbol):
        return self._candidates

    def events_for_symbol_mentions(self, symbol, *, limit, watched_only=False):
        return self._mention_events[:limit]


class FakeEvidence:
    def __init__(self, *, fts_events=None):
        self.fts_events = fts_events or []
        self.fts_queries: list[str] = []

    def search_fts(self, text, *, limit, watched_only=False):
        self.fts_queries.append(text)
        return self.fts_events[:limit]

    def count_fts(self, text, *, watched_only=False):
        return len(self.fts_events)

    def recent_events(self, *, limit, handles, watched_only=False):
        return []
