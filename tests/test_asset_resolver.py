from __future__ import annotations

from gmgn_twitter_intel.pipeline.asset_resolver import AssetResolver


def test_unresolved_symbol_creates_attention_asset():
    repo = FakeAssetRepository()
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "MIRROR",
            "raw_value": "$MIRROR",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "unresolved"
    assert decision.identity_status == "unresolved"
    assert decision.asset_id == "asset:unresolved:MIRROR"
    assert decision.venue_id is None
    assert decision.reasons == ["symbol_has_no_candidates"]
    assert repo.queued_jobs == [{"job_type": "symbol_resolution", "normalized_symbol": "MIRROR"}]


def test_unresolved_placeholder_is_ignored_when_real_candidate_exists():
    repo = FakeAssetRepository(
        symbol_candidates={
            "MIRROR": [
                {
                    "asset_id": "asset:unresolved:MIRROR",
                    "asset_type": "unresolved_symbol",
                    "identity_status": "unresolved",
                    "asset_confidence": 0.2,
                    "venue_id": None,
                },
                {
                    "asset_id": "asset:dex:solana:mirror111",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.9,
                    "venue_id": "venue:dex:solana:mirror111",
                    "venue_type": "dex",
                },
            ]
        }
    )
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "MIRROR",
            "raw_value": "$MIRROR",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "selected"
    assert decision.identity_status == "resolved"
    assert decision.asset_id == "asset:dex:solana:mirror111"
    assert decision.venue_id == "venue:dex:solana:mirror111"


def test_btc_prefers_single_cex_asset_candidate():
    repo = FakeAssetRepository(
        symbol_candidates={
            "BTC": [
                {
                    "asset_id": "asset:cex:BTC",
                    "asset_type": "cex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.95,
                    "venue_id": "venue:cex:okx:SPOT:BTC-USDT",
                    "venue_type": "cex",
                }
            ]
        }
    )
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "BTC",
            "raw_value": "$BTC",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "selected"
    assert decision.identity_status == "resolved"
    assert decision.asset_id == "asset:cex:BTC"
    assert decision.venue_id == "venue:cex:okx:SPOT:BTC-USDT"
    assert decision.reasons == ["single_local_cex_asset_candidate"]


def test_symbol_only_prefers_unique_cex_asset_over_dex_candidates():
    repo = FakeAssetRepository(
        symbol_candidates={
            "TAO": [
                {
                    "asset_id": "asset:dex:bsc:0xtao",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.8,
                    "venue_id": "venue:dex:bsc:0xtao",
                    "venue_type": "dex",
                },
                {
                    "asset_id": "asset:cex:TAO",
                    "asset_type": "cex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.95,
                    "venue_id": "venue:cex:okx:SPOT:TAO-USDT",
                    "venue_type": "cex",
                },
            ]
        }
    )
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "TAO",
            "raw_value": "$TAO",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "selected"
    assert decision.asset_id == "asset:cex:TAO"
    assert decision.venue_id == "venue:cex:okx:SPOT:TAO-USDT"
    assert decision.reasons == ["single_local_cex_asset_candidate"]


def test_multiple_symbol_candidates_remain_ambiguous():
    repo = FakeAssetRepository(
        symbol_candidates={
            "MIRROR": [
                {
                    "asset_id": "asset:dex:solana:mirror111",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.74,
                    "venue_id": "venue:dex:solana:mirror111",
                    "venue_type": "dex",
                },
                {
                    "asset_id": "asset:dex:base:0xmirror",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.68,
                    "venue_id": "venue:dex:base:0xmirror",
                    "venue_type": "dex",
                },
            ]
        }
    )
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "MIRROR",
            "raw_value": "$MIRROR",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "ambiguous"
    assert decision.identity_status == "ambiguous"
    assert decision.asset_id == "asset:ambiguous:MIRROR"
    assert decision.venue_id is None
    assert decision.reasons == ["multiple_local_asset_candidates"]
    assert repo.queued_jobs == [{"job_type": "symbol_resolution", "normalized_symbol": "MIRROR"}]


def test_stale_known_dex_symbol_queues_market_refresh():
    repo = FakeAssetRepository(
        symbol_candidates={
            "MIRROR": [
                {
                    "asset_id": "asset:dex:solana:mirror111",
                    "asset_type": "dex_asset",
                    "identity_status": "resolved",
                    "asset_confidence": 0.9,
                    "venue_id": "venue:dex:solana:mirror111",
                    "venue_type": "dex",
                    "chain": "solana",
                    "address": "Mirror111",
                }
            ]
        }
    )
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "cashtag",
            "normalized_symbol": "MIRROR",
            "raw_value": "$MIRROR",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "selected"
    assert repo.queued_jobs == [
        {"job_type": "ca_resolution", "chain_hint": "solana", "address_hint": "Mirror111"}
    ]


def test_gmgn_payload_with_chain_address_is_direct_dex_asset():
    repo = FakeAssetRepository()
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "gmgn_payload",
            "normalized_symbol": "SOL",
            "raw_value": "SOL",
            "chain_hint": "solana",
            "address_hint": "So11111111111111111111111111111111111111112",
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "direct"
    assert decision.identity_status == "resolved"
    assert decision.asset_id == "asset:dex:solana:so11111111111111111111111111111111111111112"
    assert decision.venue_id == "venue:dex:solana:so11111111111111111111111111111111111111112"


def test_ca_without_chain_hint_is_retained_as_unresolved_ca():
    repo = FakeAssetRepository()
    resolver = AssetResolver(repo)

    decision = resolver.resolve(
        {
            "mention_id": "mention-1",
            "event_id": "event-1",
            "mention_type": "ca",
            "raw_value": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            "address_hint": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            "chain_hint": None,
            "created_at_ms": 1_700_000_000_000,
        }
    )

    assert decision.attribution_status == "unresolved"
    assert decision.asset_id == "asset:unresolved_ca:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"
    assert decision.reasons == ["ca_missing_chain_hint"]


class FakeAssetRepository:
    def __init__(self, *, symbol_candidates=None):
        self.symbol_candidates = symbol_candidates or {}
        self.queued_jobs: list[dict[str, str]] = []

    def candidates_for_symbol(self, symbol):
        return list(self.symbol_candidates.get(symbol.upper(), []))

    def queue_resolution_job(
        self,
        *,
        job_type,
        normalized_symbol=None,
        chain_hint=None,
        address_hint=None,
        next_run_at_ms=None,
        commit=False,
    ):
        row = {"job_type": job_type}
        if normalized_symbol is not None:
            row["normalized_symbol"] = normalized_symbol
        if chain_hint is not None:
            row["chain_hint"] = chain_hint
        if address_hint is not None:
            row["address_hint"] = address_hint
        self.queued_jobs.append(row)
        return {"job_id": f"job:{job_type}:{normalized_symbol}", "status": "queued"}

    def market_snapshot_at_or_before(self, asset_id, observed_at_ms):
        return None

    def upsert_unresolved_symbol(self, symbol, *, event_id, observed_at_ms, commit=False):
        normalized = symbol.upper()
        return {
            "asset_id": f"asset:unresolved:{normalized}",
            "asset_type": "unresolved_symbol",
            "canonical_symbol": normalized,
            "identity_status": "unresolved",
        }

    def upsert_ambiguous_symbol(self, symbol, *, event_id, observed_at_ms, commit=False):
        normalized = symbol.upper()
        return {
            "asset_id": f"asset:ambiguous:{normalized}",
            "asset_type": "ambiguous_symbol",
            "canonical_symbol": normalized,
            "identity_status": "ambiguous",
        }

    def upsert_unresolved_ca(self, address, *, event_id, observed_at_ms, chain_hint=None, commit=False):
        normalized = address.lower()
        return {
            "asset_id": f"asset:unresolved_ca:{normalized}",
            "asset_type": "unresolved_ca",
            "canonical_symbol": normalized,
            "identity_status": "unresolved",
        }

    def upsert_dex_asset(
        self,
        *,
        chain,
        address,
        symbol,
        observed_at_ms,
        event_id=None,
        provider="deterministic",
        commit=False,
    ):
        normalized_chain = chain.lower()
        normalized_address = address.lower()
        return FakeAssetResolutionResult(
            asset={"asset_id": f"asset:dex:{normalized_chain}:{normalized_address}", "identity_status": "resolved"},
            venue={
                "venue_id": f"venue:dex:{normalized_chain}:{normalized_address}",
                "venue_type": "dex",
                "chain": normalized_chain,
                "address": address,
            },
        )


class FakeAssetResolutionResult:
    def __init__(self, *, asset, venue):
        self.asset = asset
        self.venue = venue
