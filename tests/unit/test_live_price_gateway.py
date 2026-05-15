from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_persists_only_material_decision_latest_frames():
    db = FakeDB()
    stream_provider = FakeStreamProvider(
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_000_000,
                price_usd=1.0,
                raw={"price": "1.0"},
            ),
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_001_000,
                price_usd=1.0001,
                raw={"price": "1.0001"},
            ),
        ]
    )
    published: list[dict] = []
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        stream_provider=stream_provider,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=published.append,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result.notes["result"]["updates_received"] == 2
    assert result.processed == 1
    assert len(db.repos.price_observations.calls) == 1
    assert db.repos.price_observations.calls[0]["observation_kind"] == "decision_latest"
    assert result.notes["live_observation_reasons"]["first_seen"] == 1
    assert result.notes["live_observation_reasons"]["debounced"] == 1
    assert published[0]["market"]["decision_latest"]["price_usd"] == 1.0


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = updates

    async def stream_price_info(self, targets):
        for update in self.updates:
            yield update


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 30.0,
        "timeout_seconds": 120.0,
        "subscription_limit": 10,
        "hot_target_ttl_seconds": 60.0,
        "reconnect_delay_seconds": 0.1,
        "cex_poll_interval_seconds": 30.0,
        "live_observation_heartbeat_seconds": 60.0,
        "live_observation_min_price_change_pct": 0.005,
        "live_observation_min_write_interval_seconds": 5.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.repos = FakeRepos()

    def worker_session(self, name: str):
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepos:
    def __init__(self) -> None:
        self.registry = FakeRegistry()
        self.price_observations = FakePriceObservations()


class FakeRegistry:
    def active_live_market_targets(self, *, projection_version, since_ms, limit):
        return [
            {
                "target_type": "Asset",
                "target_id": "asset:solana:token:abc",
                "chain_id": "solana",
                "address": "abc",
                "native_market_id": None,
                "quote_symbol": None,
                "provider": "okx",
            }
        ]


class FakePriceObservations:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.latest = {}

    def latest_for_target(self, *, target_type, target_id, now_ms, max_age_ms):
        return self.latest.get((target_type, target_id))

    def insert_market_observation(
        self,
        observation,
        *,
        observation_kind,
        source_event_id,
        source_intent_id,
        source_resolution_id,
        event_received_at_ms,
        commit,
    ):
        self.calls.append({"observation": observation, "observation_kind": observation_kind, "commit": commit})
        self.latest[(observation.target.target_type, observation.target.target_id)] = observation
        return "observation-id"
