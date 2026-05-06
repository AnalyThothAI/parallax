from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxDexTokenCandidate
from gmgn_twitter_intel.pipeline.asset_resolution_worker import AssetResolutionWorker


def test_symbol_resolution_job_writes_dex_candidate_market_snapshot_and_backfills():
    assets = FakeAssets(
        job={"job_id": "job-1", "job_type": "symbol_resolution", "normalized_symbol": "MIRROR"}
    )
    client = FakeDexClient(
        [
            OkxDexTokenCandidate(
                chain_index="501",
                chain="solana",
                address="Mirror111111111111111111111111111111111111",
                symbol="MIRROR",
                name="Mirror",
                price_usd=0.12,
                market_cap_usd=123456.0,
                liquidity_usd=45678.0,
                holders=321,
                community_recognized=True,
                raw={"tokenSymbol": "MIRROR"},
            )
        ]
    )
    worker = AssetResolutionWorker(client=client, assets=assets, chain_indexes=("501",), poll_interval=0)

    result = worker.process_one(now_ms=1_700_000_000_000)

    assert result == {"processed": True, "job_id": "job-1", "status": "succeeded", "candidate_count": 1}
    assert client.searches == [{"query": "MIRROR", "chain_indexes": ("501",)}]
    assert assets.dex_upserts[0]["provider"] == "okx_dex"
    assert assets.market_snapshots[0]["price_usd"] == 0.12
    assert assets.reassignments == [
        {
            "symbol": "MIRROR",
            "asset_id": "asset:dex:solana:mirror111111111111111111111111111111111111",
            "venue_id": "venue:dex:solana:mirror111111111111111111111111111111111111",
        }
    ]
    assert assets.finished_jobs == [{"job_id": "job-1", "status": "succeeded", "error": None}]


def test_symbol_resolution_job_backfills_dominant_okx_dex_candidate():
    assets = FakeAssets(
        job={"job_id": "job-1", "job_type": "symbol_resolution", "normalized_symbol": "USDUC"}
    )
    client = FakeDexClient(
        [
            OkxDexTokenCandidate(
                chain_index="501",
                chain="solana",
                address="CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump",
                symbol="USDUC",
                name="unstable coin",
                price_usd=0.021,
                market_cap_usd=21_900_000.0,
                liquidity_usd=1_570_000.0,
                holders=15_331,
                community_recognized=True,
                raw={"tokenSymbol": "USDUC"},
            ),
            OkxDexTokenCandidate(
                chain_index="8453",
                chain="base",
                address="0xecedb6f8108b9f7bbf499da843dced6c2bb6e270",
                symbol="USDUC",
                name="unstable coin",
                price_usd=0.021,
                market_cap_usd=44_000.0,
                liquidity_usd=13_000.0,
                holders=6_000,
                community_recognized=True,
                raw={"tokenSymbol": "USDUC"},
            ),
            OkxDexTokenCandidate(
                chain_index="501",
                chain="solana",
                address="3TfR4oL2Q9RKpTuQztpBhmNRU31U3imwGKAu3Qx24uf1",
                symbol="USDUC",
                name="unstable coin",
                price_usd=0.38,
                market_cap_usd=386_000_000.0,
                liquidity_usd=0.001,
                holders=624,
                community_recognized=False,
                raw={"tokenSymbol": "USDUC"},
            ),
        ]
    )
    worker = AssetResolutionWorker(client=client, assets=assets, chain_indexes=("501", "8453"), poll_interval=0)

    result = worker.process_one(now_ms=1_700_000_000_000)

    assert result["candidate_count"] == 3
    assert assets.reassignments == [
        {
            "symbol": "USDUC",
            "asset_id": "asset:dex:solana:cb9dduft3zuqxqqsfa1c5ky935tereybw9xjxxhkpump",
            "venue_id": "venue:dex:solana:cb9dduft3zuqxqqsfa1c5ky935tereybw9xjxxhkpump",
        }
    ]


def test_ca_resolution_job_backfills_unresolved_ca_attributions():
    assets = FakeAssets(
        job={
            "job_id": "job-1",
            "job_type": "ca_resolution",
            "chain_hint": None,
            "address_hint": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        }
    )
    client = FakeDexClient(
        [
            OkxDexTokenCandidate(
                chain_index="1",
                chain="ethereum",
                address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
                symbol="PEPE",
                name="Pepe",
                price_usd=0.00001,
                market_cap_usd=1_000_000.0,
                liquidity_usd=500_000.0,
                holders=1000,
                community_recognized=True,
                raw={"tokenSymbol": "PEPE"},
            )
        ]
    )
    worker = AssetResolutionWorker(client=client, assets=assets, chain_indexes=("1",), poll_interval=0)

    result = worker.process_one(now_ms=1_700_000_000_000)

    assert result == {"processed": True, "job_id": "job-1", "status": "succeeded", "candidate_count": 1}
    assert assets.ca_reassignments == [
        {
            "address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "asset_id": "asset:dex:ethereum:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "venue_id": "venue:dex:ethereum:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        }
    ]


def test_resolution_worker_does_not_write_empty_market_snapshots():
    assets = FakeAssets(
        job={"job_id": "job-1", "job_type": "symbol_resolution", "normalized_symbol": "TEST"}
    )
    client = FakeDexClient(
        [
            OkxDexTokenCandidate(
                chain_index="8453",
                chain="base",
                address="0x1111111111111111111111111111111111111111",
                symbol="TEST",
                name="Test",
                price_usd=None,
                market_cap_usd=None,
                liquidity_usd=None,
                holders=None,
                community_recognized=False,
                raw={"tokenSymbol": "TEST"},
            )
        ]
    )
    worker = AssetResolutionWorker(client=client, assets=assets, chain_indexes=("8453",), poll_interval=0)

    result = worker.process_one(now_ms=1_700_000_000_000)

    assert result["candidate_count"] == 1
    assert assets.market_snapshots == []


class FakeDexClient:
    def __init__(self, candidates):
        self.candidates = candidates
        self.searches = []

    def search_tokens(self, *, query, chain_indexes):
        self.searches.append({"query": query, "chain_indexes": tuple(chain_indexes)})
        return self.candidates


class FakeAssets:
    def __init__(self, *, job):
        self.job = job
        self.dex_upserts = []
        self.market_snapshots = []
        self.reassignments = []
        self.ca_reassignments = []
        self.finished_jobs = []

    def claim_resolution_job(self, *, now_ms):
        return self.job

    def mentions_needing_symbol_resolution(self, symbol, *, limit):
        return [{"mention_id": "mention-1"}]

    def upsert_dex_asset(
        self,
        *,
        chain,
        address,
        symbol,
        observed_at_ms,
        event_id=None,
        provider,
        source_payload_hash=None,
        commit=False,
    ):
        payload = {
            "chain": chain,
            "address": address,
            "symbol": symbol,
            "provider": provider,
            "source_payload_hash": source_payload_hash,
        }
        self.dex_upserts.append(payload)
        asset_id = f"asset:dex:{chain}:{address.lower()}"
        venue_id = f"venue:dex:{chain}:{address.lower()}"
        return FakeAssetResolutionResult(asset={"asset_id": asset_id}, venue={"venue_id": venue_id})

    def insert_resolution_candidate(self, **kwargs):
        return kwargs

    def insert_market_snapshot(self, **kwargs):
        self.market_snapshots.append(kwargs)
        return kwargs

    def reassign_symbol_attributions(self, *, symbol, asset_id, venue_id, decision_time_ms, commit=False):
        self.reassignments.append({"symbol": symbol, "asset_id": asset_id, "venue_id": venue_id})
        return 3

    def reassign_ca_attributions(self, *, address, chain, asset_id, venue_id, decision_time_ms, commit=False):
        self.ca_reassignments.append({"address": address, "asset_id": asset_id, "venue_id": venue_id})
        return 2

    def finish_resolution_job(self, *, job_id, status, error=None, next_run_at_ms=None, commit=True):
        self.finished_jobs.append({"job_id": job_id, "status": status, "error": error})
        return {"job_id": job_id, "status": status}


class FakeAssetResolutionResult:
    def __init__(self, *, asset, venue):
        self.asset = asset
        self.venue = venue
