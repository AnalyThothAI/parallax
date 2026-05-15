from __future__ import annotations

import asyncio
from decimal import Decimal

import yaml

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import (
    ADVISORY_LOCK_KEY,
    TokenCaptureTierWorker,
    project_once,
)
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS
from gmgn_twitter_intel.platform.config.settings import WorkersSettings, default_workers_yaml


def test_project_once_promotes_hottest_targets_to_tier1_ws_subscribed() -> None:
    repos = FakeRepos(
        [
            {"target_type": "chain_token", "target_id": "sol:mid", "score": Decimal("7")},
            {"target_type": "cex_symbol", "target_id": "okx:ETH-USDT", "score": Decimal("12")},
            {"target_type": "chain_token", "target_id": "sol:hot", "score": Decimal("20")},
        ]
    )

    processed = project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=2, poll_limit=10)

    assert processed == 3
    assert repos.registry.calls == [
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "since_ms": 1_800_000_000_000 - WINDOW_MS["24h"],
            "limit": 10,
        }
    ]
    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:hot", 1, "ws_subscribed", "20"),
        tier("cex_symbol", "okx:ETH-USDT", 1, "ws_subscribed", "12"),
        tier("chain_token", "sol:mid", 2, "batch_poll", "7"),
    ]
    assert repos.conn.commit_count == 1


def test_project_once_assigns_tier2_and_tier3_deterministically() -> None:
    repos = FakeRepos(
        [
            {"target_type": "chain_token", "target_id": "sol:c", "score": 10},
            {"target_type": "chain_token", "target_id": "sol:b", "score": 10},
            {"target_type": "chain_token", "target_id": "sol:a", "score": 10},
            {"target_type": "cex_symbol", "target_id": "binance:BTCUSDT", "score": 9},
        ]
    )

    processed = project_once(repos, now_ms=1_800_000_000_000, batch_size=4, ws_limit=1, poll_limit=1)

    assert processed == 4
    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:a", 1, "ws_subscribed", "10"),
        tier("chain_token", "sol:b", 2, "batch_poll", "10"),
        tier("chain_token", "sol:c", 3, "inline_only", "10"),
        tier("cex_symbol", "binance:BTCUSDT", 3, "inline_only", "9"),
    ]


def test_project_once_maps_legacy_active_target_rows_to_new_market_targets() -> None:
    repos = FakeRepos(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "chain_id": "solana",
                "address": "So11111111111111111111111111111111111111112",
                "rank_score": "4.5",
            },
            {
                "target_type": "CexToken",
                "target_id": "cex-token-1",
                "provider": "Binance",
                "native_market_id": "ethusdt",
                "composite_rank_score": "9.25",
            },
        ]
    )

    processed = project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=10, poll_limit=10)

    assert processed == 2
    assert repos.token_capture_tiers.upserts == [
        tier("cex_symbol", "binance:ETHUSDT", 1, "ws_subscribed", "9.25"),
        tier(
            "chain_token",
            "solana:So11111111111111111111111111111111111111112",
            1,
            "ws_subscribed",
            "4.5",
        ),
    ]


def test_project_once_uses_recency_score_when_rank_score_is_missing() -> None:
    repos = FakeRepos(
        [
            {"target_type": "chain_token", "target_id": "sol:older", "computed_at_ms": 100},
            {"target_type": "chain_token", "target_id": "sol:newer", "source_max_received_at_ms": 200},
        ]
    )

    project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=10, poll_limit=10)

    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:newer", 1, "ws_subscribed", "200"),
        tier("chain_token", "sol:older", 1, "ws_subscribed", "100"),
    ]


def test_worker_run_once_returns_worker_result_processed_count() -> None:
    db = FakeDB(
        FakeRepos(
            [
                {"target_type": "chain_token", "target_id": "sol:hot", "score": 3},
                {"target_type": "cex_symbol", "target_id": "okx:ETH-USDT", "score": 2},
            ]
        )
    )
    worker = TokenCaptureTierWorker(db=db, telemetry=object(), batch_size=5, ws_limit=1, poll_limit=1)

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 2
    assert result.notes == {"updated_tiers": 2}
    assert db.session_names == ["token_capture_tier"]


def test_worker_exposes_single_writer_advisory_lock_key() -> None:
    worker = TokenCaptureTierWorker(db=FakeDB(FakeRepos([])), telemetry=object())

    assert ADVISORY_LOCK_KEY == 2026051503
    assert worker.SINGLE_WRITER_KEY == ADVISORY_LOCK_KEY
    assert worker._advisory_lock_key() == ADVISORY_LOCK_KEY


def test_worker_has_no_provider_dependency_slots() -> None:
    worker = TokenCaptureTierWorker(db=FakeDB(FakeRepos([])), telemetry=object())

    assert not hasattr(worker, "cex_market")
    assert not hasattr(worker, "dex_quote_market")
    assert not hasattr(worker, "stream_provider")


def test_default_workers_yaml_includes_token_capture_tier_settings() -> None:
    workers = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert workers.token_capture_tier.enabled is True
    assert workers.token_capture_tier.batch_size == 500
    assert workers.token_capture_tier.ws_limit == 100
    assert workers.token_capture_tier.poll_limit == 500
    assert workers.token_capture_tier.advisory_lock_key == ADVISORY_LOCK_KEY


def test_registry_active_live_market_targets_projects_rank_score_from_factor_snapshot() -> None:
    conn = CapturingConn()

    rows = RegistryRepository(conn).active_live_market_targets(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        since_ms=1_800_000_000_000 - WINDOW_MS["24h"],
        limit=25,
    )

    assert rows == []
    assert "factor_snapshot_json" in conn.sql
    assert "composite" in conn.sql
    assert "rank_score" in conn.sql
    assert "AS score" in conn.sql
    assert "AS rank_score" in conn.sql


def tier(target_type: str, target_id: str, tier_value: int, reason: str, score: str) -> dict[str, object]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "tier": tier_value,
        "reason": reason,
        "score": Decimal(score),
        "updated_at_ms": 1_800_000_000_000,
    }


class FakeRepos:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.registry = FakeRegistry(rows)
        self.token_capture_tiers = FakeTokenCaptureTiers()
        self.conn = FakeConn()


class FakeRegistry:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def active_live_market_targets(self, *, projection_version: str, since_ms: int, limit: int):
        self.calls.append({"projection_version": projection_version, "since_ms": since_ms, "limit": limit})
        return self.rows[:limit]


class FakeTokenCaptureTiers:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    def upsert_tier(self, **kwargs) -> None:
        self.upserts.append(kwargs)


class FakeConn:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class FakeDB:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos
        self.session_names: list[str] = []

    def worker_session(self, name: str):
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos

    def __enter__(self) -> FakeRepos:
        return self.repos

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class CapturingConn:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def execute(self, sql: str, params: tuple[object, ...]):
        self.sql = sql
        self.params = params
        return EmptyRows()


class EmptyRows:
    def fetchall(self) -> list[dict[str, object]]:
        return []
