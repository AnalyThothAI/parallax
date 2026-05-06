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


def test_symbol_search_falls_back_to_fts_when_asset_index_has_no_events():
    evidence = FakeEvidence(fts_events=[{"event_id": "event-text", "score": 0.42}])
    service = AssetSearchService(
        evidence=evidence,
        assets=FakeAssets(candidates=[], mention_events=[]),
    )

    result = service.search("$MIRROR", limit=20)

    assert result.ok is True
    assert result.resolution["status"] == "unresolved"
    assert result.total_count == 1
    assert result.items[0]["match_type"] == "fts_symbol_fallback"
    assert result.items[0]["event"]["event_id"] == "event-text"
    assert evidence.fts_queries == ["MIRROR"]


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


def test_symbol_search_ignores_unresolved_placeholder_when_real_candidate_exists():
    service = AssetSearchService(
        evidence=FakeEvidence(),
        assets=FakeAssets(
            candidates=[
                {
                    "asset_id": "asset:unresolved:MIRROR",
                    "asset_type": "unresolved_symbol",
                    "identity_status": "unresolved",
                },
                {"asset_id": "asset:dex:solana:mirror", "asset_type": "dex_asset", "identity_status": "resolved"},
            ],
            mention_events=[{"event_id": "event-1", "received_at_ms": 1000, "normalized_symbol": "MIRROR"}],
        ),
    )

    result = service.search("$MIRROR", limit=20)

    assert result.resolution["status"] == "resolved"
    assert [candidate["asset_id"] for candidate in result.candidates] == ["asset:dex:solana:mirror"]


def test_symbol_search_prefers_unique_cex_candidate_for_symbol_only_query():
    service = AssetSearchService(
        evidence=FakeEvidence(),
        assets=FakeAssets(
            candidates=[
                {
                    "asset_id": "asset:dex:bsc:0xtao",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "venue_type": "dex",
                },
                {
                    "asset_id": "asset:cex:TAO",
                    "asset_type": "cex_asset",
                    "identity_status": "resolved",
                    "venue_type": "cex",
                },
            ],
            mention_events=[{"event_id": "event-1", "received_at_ms": 1000, "normalized_symbol": "TAO"}],
        ),
    )

    result = service.search("$TAO", limit=20)

    assert result.resolution["status"] == "resolved"
    assert [candidate["asset_id"] for candidate in result.candidates] == ["asset:cex:TAO"]


def test_ca_search_uses_asset_index_instead_of_fts():
    evidence = FakeEvidence(fts_events=[{"event_id": "event-text", "score": 0.42}])
    service = AssetSearchService(
        evidence=evidence,
        assets=FakeAssets(
            candidates=[],
            ca_candidates=[
                {
                    "asset_id": "asset:dex:ethereum:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "identity_status": "resolved",
                    "venue_id": "venue:dex:ethereum:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                }
            ],
            ca_events=[
                {
                    "event_id": "event-ca",
                    "received_at_ms": 1000,
                    "address_hint": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "attribution_status": "direct",
                }
            ],
            mention_events=[],
        ),
    )

    result = service.search("eth:0x6982508145454ce325ddbe47a25d4ec3d2311933", limit=20)

    assert result.ok is True
    assert result.resolution["status"] == "resolved"
    assert result.items[0]["match_type"] == "asset_mention"
    assert result.items[0]["event"]["event_id"] == "event-ca"
    assert evidence.fts_queries == []


def test_ca_search_falls_back_to_fts_when_asset_index_has_no_events():
    evidence = FakeEvidence(fts_events=[{"event_id": "event-ca-text", "score": 0.9}])
    service = AssetSearchService(
        evidence=evidence,
        assets=FakeAssets(candidates=[], mention_events=[], ca_candidates=[], ca_events=[]),
    )

    result = service.search("eth:0x6982508145454ce325ddbe47a25d4ec3d2311933", limit=20)

    assert result.ok is True
    assert result.resolution["status"] == "unresolved"
    assert result.items[0]["match_type"] == "fts_ca_fallback"
    assert result.items[0]["event"]["event_id"] == "event-ca-text"
    assert evidence.fts_queries == ["0x6982508145454Ce325dDbE47a25d4ec3d2311933"]


def test_text_search_still_uses_fts():
    evidence = FakeEvidence(fts_events=[{"event_id": "event-text", "score": 0.42}])
    service = AssetSearchService(evidence=evidence, assets=FakeAssets(candidates=[], mention_events=[]))

    result = service.search("mirror", limit=20)

    assert result.ok is True
    assert result.items[0]["match_type"] == "fts"
    assert result.items[0]["event"]["event_id"] == "event-text"
    assert evidence.fts_queries == ["mirror"]


class FakeAssets:
    def __init__(self, *, candidates, mention_events, ca_candidates=None, ca_events=None):
        self._candidates = candidates
        self._mention_events = mention_events
        self._ca_candidates = ca_candidates or []
        self._ca_events = ca_events or []

    def candidates_for_symbol(self, symbol):
        return self._candidates

    def events_for_symbol_mentions(self, symbol, *, limit, watched_only=False):
        return self._mention_events[:limit]

    def candidates_for_ca(self, *, chain, address):
        return self._ca_candidates

    def events_for_ca_mentions(self, *, chain, address, limit, watched_only=False):
        return self._ca_events[:limit]


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
