from __future__ import annotations

import asyncio

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.dex_market_stream_worker import DexMarketStreamWorker


def test_stream_worker_writes_okx_dex_ws_price_info_observation():
    repos = FakeRepos()
    provider = FakeStreamProvider(
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                observed_at_ms=1_700_086_420_000,
                price_usd=0.111,
                market_cap_usd=110_900_000,
                liquidity_usd=4_820_000,
                volume_24h_usd=27_400_000,
                holders=57_141,
                raw={"marketCap": "110900000"},
            )
        ]
    )
    market_updates: list[dict] = []
    worker = DexMarketStreamWorker(
        stream_provider=provider,
        repository_session=lambda: FakeSession(repos),
        projection_version="token-radar-v10-current-market",
        subscription_limit=10,
        hot_target_ttl_seconds=300,
        on_market_update=market_updates.append,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_086_430_000))

    assert provider.targets == [
        {
            "chain_id": "solana",
            "address": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            "subject_type": "Asset",
            "subject_id": "asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            "pricefeed_id": None,
        }
    ]
    assert repos.registry.target_query == {
        "projection_version": "token-radar-v10-current-market",
        "since_ms": 1_700_086_130_000,
        "limit": 10,
    }
    assert repos.price_observations.inserted == [
        {
            "provider": "okx_dex_ws_price_info",
            "pricefeed_id": (
                "pricefeed:dex-token:okx_dex_ws_price_info:"
                "solana:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
            ),
            "observed_at_ms": 1_700_086_420_000,
            "subject_type": "Asset",
            "subject_id": "asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            "price_usd": 0.111,
            "price_basis": "usd",
            "market_cap_usd": 110_900_000,
            "liquidity_usd": 4_820_000,
            "volume_24h_usd": 27_400_000,
            "open_interest_usd": None,
            "holders": 57_141,
            "raw_payload": {"marketCap": "110900000"},
            "commit": False,
        }
    ]
    assert repos.committed is True
    assert market_updates[0]["type"] == "market_update"
    assert market_updates[0]["provider"] == "okx_dex_ws_price_info"
    assert market_updates[0]["target_id"] == "asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
    assert result["observations_written"] == 1


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = updates
        self.targets: list[dict] = []

    async def stream_price_info(self, targets):
        self.targets = [
            {
                "chain_id": target.chain_id,
                "address": target.address,
                "subject_type": target.subject_type,
                "subject_id": target.subject_id,
                "pricefeed_id": target.pricefeed_id,
            }
            for target in targets
        ]
        for update in self.updates:
            yield update


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepos:
    def __init__(self) -> None:
        self.registry = FakeRegistry(self)
        self.price_observations = FakePriceObservations()
        self.current_market = FakeCurrentMarket()
        self.committed = False
        self.conn = self

    def commit(self) -> None:
        self.committed = True


class FakeRegistry:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos
        self.target_query: dict | None = None

    def active_dex_market_stream_targets(self, *, projection_version, since_ms, limit):
        self.target_query = {"projection_version": projection_version, "since_ms": since_ms, "limit": limit}
        return [
            {
                "asset_id": "asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                "chain_id": "solana",
                "address": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                "symbol": "TROLL",
            }
        ]

    def upsert_pricefeed(self, **kwargs):
        return {
            "pricefeed_id": (
                "pricefeed:dex-token:okx_dex_ws_price_info:"
                f"{kwargs['chain_id']}:{kwargs['address']}"
            )
        }


class FakePriceObservations:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    def insert_observation(self, **kwargs):
        self.inserted.append(kwargs)
        return {"observation_id": "observation-1"}


class FakeCurrentMarket:
    def current_for_subjects(self, subjects, *, now_ms):
        subject = subjects[0]
        return {
            (subject["target_type"], subject["target_id"]): {
                "target_type": subject["target_type"],
                "target_id": subject["target_id"],
                "market_status": "fresh",
                "fields": {"market_cap_usd": {"value": 110_900_000, "status": "fresh"}},
            }
        }
