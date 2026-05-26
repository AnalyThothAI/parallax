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
            asset_target("asset-mid", chain_id="sol", address="mid", score=Decimal("7")),
            cex_target("cex-eth", provider="binance", native_market_id="ETHUSDT", score=Decimal("12")),
            asset_target("asset-hot", chain_id="sol", address="hot", score=Decimal("20")),
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
    # Tier 1 is DEX WS only (chain_token). With ws_limit=2 both chain_tokens fill Tier 1
    # even though the CEX symbol has a higher score; the CEX symbol drops to Tier 2.
    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:hot", 1, "ws_subscribed", "20"),
        tier("chain_token", "sol:mid", 1, "ws_subscribed", "7"),
        tier("cex_symbol", "binance:ETHUSDT", 2, "batch_poll", "12"),
    ]
    assert repos.conn.commit_count == 1


def test_project_once_never_assigns_cex_symbol_to_tier1_ws_even_when_hottest() -> None:
    repos = FakeRepos(
        [
            cex_target("cex-btc", provider="binance", native_market_id="BTCUSDT", score=Decimal("999")),
            asset_target(
                "asset-sol",
                chain_id="solana",
                address="So11111111111111111111111111111111111111112",
                score=Decimal("500"),
            ),
        ]
    )

    processed = project_once(repos, now_ms=1_777_800_000_000, batch_size=10, ws_limit=1, poll_limit=10)

    assert processed == 2
    assert repos.token_capture_tiers.upserts == [
        tier(
            "chain_token",
            "solana:So11111111111111111111111111111111111111112",
            1,
            "ws_subscribed",
            "500",
            updated_at_ms=1_777_800_000_000,
        ),
        tier(
            "cex_symbol",
            "binance:BTCUSDT",
            2,
            "batch_poll",
            "999",
            updated_at_ms=1_777_800_000_000,
        ),
    ]


def test_project_once_demotes_old_hot_rows_absent_from_current_projection() -> None:
    repos = FakeRepos(
        [asset_target("asset-new", chain_id="solana", address="newhot", score=Decimal("100"))],
        existing_tiers=[
            {
                "target_type": "chain_token",
                "target_id": "solana:oldhot",
                "tier": 1,
                "reason": "ws_subscribed",
            },
            {
                "target_type": "cex_symbol",
                "target_id": "binance:OLDUSDT",
                "tier": 2,
                "reason": "batch_poll",
            },
        ],
    )

    project_once(repos, now_ms=1_777_800_000_000, batch_size=10, ws_limit=1, poll_limit=10)

    assert repos.token_capture_tiers.demotion_calls == [
        {
            "active_keys": [
                {"target_type": "chain_token", "target_id": "solana:newhot"},
            ],
            "updated_at_ms": 1_777_800_000_000,
        }
    ]
    assert repos.token_capture_tiers.demoted == [
        ("chain_token", "solana:oldhot"),
        ("cex_symbol", "binance:OLDUSDT"),
    ]


def test_project_once_assigns_tier2_and_tier3_deterministically() -> None:
    repos = FakeRepos(
        [
            asset_target("asset-c", chain_id="sol", address="c", score=10),
            asset_target("asset-b", chain_id="sol", address="b", score=10),
            asset_target("asset-a", chain_id="sol", address="a", score=10),
            cex_target("cex-btc", provider="binance", native_market_id="BTCUSDT", score=9),
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


def test_project_once_maps_active_target_rows_to_market_targets() -> None:
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
                "rank_score": "9.25",
            },
        ]
    )

    processed = project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=10, poll_limit=10)

    assert processed == 2
    # Tier 1 is DEX WS only: the chain_token row goes to Tier 1 even though the CEX symbol
    # outranks it on score. The CEX symbol drops to Tier 2 batch_poll.
    assert repos.token_capture_tiers.upserts == [
        tier(
            "chain_token",
            "solana:So11111111111111111111111111111111111111112",
            1,
            "ws_subscribed",
            "4.5",
        ),
        tier("cex_symbol", "binance:ETHUSDT", 2, "batch_poll", "9.25"),
    ]


def test_project_once_uses_zero_score_when_rank_score_is_missing() -> None:
    repos = FakeRepos(
        [
            asset_target("asset-older", chain_id="sol", address="older"),
            asset_target("asset-newer", chain_id="sol", address="newer"),
        ]
    )

    project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=10, poll_limit=10)

    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:newer", 1, "ws_subscribed", "0"),
        tier("chain_token", "sol:older", 1, "ws_subscribed", "0"),
    ]


def test_worker_run_once_returns_worker_result_processed_count() -> None:
    db = FakeDB(
        FakeRepos(
            [
                asset_target("asset-hot", chain_id="sol", address="hot", score=3),
                cex_target("cex-eth", provider="binance", native_market_id="ETHUSDT", score=2),
            ]
        )
    )
    worker = TokenCaptureTierWorker(db=db, telemetry=object(), batch_size=5, ws_limit=1, poll_limit=1)

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 2
    assert result.notes["claimed"] == 1
    assert result.notes["rows_written"] == 2
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


def test_registry_ranked_live_market_targets_projects_rank_score_from_factor_snapshot() -> None:
    conn = CapturingConn()

    rows = RegistryRepository(conn).ranked_live_market_targets(
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
    assert "token_radar_projection_coverage" in conn.sql
    assert "SELECT computed_at_ms\n                FROM token_radar_current_rows" not in conn.sql
    assert "latest_sets.computed_at_ms" in conn.sql
    assert "token_radar_current_rows.computed_at_ms >= %s" not in conn.sql
    assert "token_radar_rows" not in conn.sql
    assert conn.params == (
        TOKEN_RADAR_PROJECTION_VERSION,
        1_800_000_000_000 - WINDOW_MS["24h"],
        TOKEN_RADAR_PROJECTION_VERSION,
        25,
    )


def tier(
    target_type: str,
    target_id: str,
    tier_value: int,
    reason: str,
    score: str,
    *,
    updated_at_ms: int = 1_800_000_000_000,
) -> dict[str, object]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "tier": tier_value,
        "reason": reason,
        "score": Decimal(score),
        "updated_at_ms": updated_at_ms,
    }


def asset_target(
    target_id: str,
    *,
    chain_id: str,
    address: str,
    score: object | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "target_type": "Asset",
        "target_id": target_id,
        "chain_id": chain_id,
        "address": address,
    }
    if score is not None:
        row["score"] = score
    return row


def cex_target(
    target_id: str,
    *,
    provider: str,
    native_market_id: str,
    score: object | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "target_type": "CexToken",
        "target_id": target_id,
        "provider": provider,
        "native_market_id": native_market_id,
    }
    if score is not None:
        row["score"] = score
    return row


class FakeRepos:
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        existing_tiers: list[dict[str, object]] | None = None,
    ) -> None:
        self.registry = FakeRegistry(rows)
        self.token_capture_tiers = FakeTokenCaptureTiers(existing_tiers=existing_tiers or [])
        self.token_capture_tier_dirty_targets = FakeCaptureDirtyTargets()
        self.conn = FakeConn()

    def transaction(self):
        from contextlib import nullcontext

        return nullcontext()


class FakeRegistry:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def ranked_live_market_targets(self, *, projection_version: str, since_ms: int, limit: int):
        self.calls.append({"projection_version": projection_version, "since_ms": since_ms, "limit": limit})
        return self.rows[:limit]


class FakeTokenCaptureTiers:
    def __init__(self, *, existing_tiers: list[dict[str, object]] | None = None) -> None:
        self.upserts: list[dict[str, object]] = []
        self.demotion_calls: list[dict[str, object]] = []
        self.demoted: list[tuple[str, str]] = []
        self._existing: list[dict[str, object]] = list(existing_tiers or [])

    def upsert_tier(self, **kwargs) -> None:
        self.upserts.append(kwargs)

    def demote_hot_rows_outside_rank_set(
        self,
        *,
        active_keys: list[dict[str, str]],
        updated_at_ms: int,
    ) -> int:
        active = {(item["target_type"], item["target_id"]) for item in active_keys}
        self.demotion_calls.append(
            {
                "active_keys": list(active_keys),
                "updated_at_ms": int(updated_at_ms),
            }
        )
        demoted_now: list[tuple[str, str]] = []
        for row in self._existing:
            key = (str(row["target_type"]), str(row["target_id"]))
            if int(row.get("tier", 3)) in (1, 2) and key not in active:
                demoted_now.append(key)
        self.demoted.extend(demoted_now)
        return len(demoted_now)


class FakeCaptureDirtyTargets:
    def claim_due(self, **kwargs):
        return [
            {
                "work_name": "active_live_market_rank_set",
                "partition_key": "global",
                "payload_hash": "hash",
                "lease_owner": "token_capture_tier",
                "attempt_count": 1,
            }
        ]

    def queue_depth(self, **kwargs):
        return 0

    def mark_done(self, claims, **kwargs):
        return len(claims)


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
