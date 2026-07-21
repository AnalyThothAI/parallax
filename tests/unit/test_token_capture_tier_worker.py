from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from decimal import Decimal
from types import SimpleNamespace, TracebackType
from typing import Any

import pytest
import yaml

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from parallax.domains.asset_market.runtime.token_capture_tier_worker import (
    ADVISORY_LOCK_KEY,
    TokenCaptureTierWorker,
    project_once,
)
from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS
from parallax.platform.config.settings import WorkersSettings, default_workers_yaml


def _worker_settings(
    *,
    batch_size: int = 100,
    ws_limit: int = 50,
    poll_limit: int = 200,
    lease_ms: int = 60_000,
    interval_seconds: float = 30.0,
    retry_ms: int = 30_000,
    max_attempts: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        interval_seconds=interval_seconds,
        soft_timeout_seconds=120.0,
        hard_timeout_seconds=180.0,
        backoff=SimpleNamespace(base_ms=1_000, max_ms=60_000),
        batch_size=batch_size,
        ws_limit=ws_limit,
        poll_limit=poll_limit,
        lease_ms=lease_ms,
        retry_ms=retry_ms,
        max_attempts=max_attempts,
        advisory_lock_key=ADVISORY_LOCK_KEY,
    )


def test_project_once_promotes_hottest_targets_to_tier1_ws_subscribed() -> None:
    repos = FakeRepos(
        [
            asset_target("asset-mid", chain_id="sol", address="mid", score=Decimal("7")),
            cex_target("cex-eth", provider="binance", native_market_id="ETHUSDT", score=Decimal("12")),
            asset_target("asset-hot", chain_id="sol", address="hot", score=Decimal("20")),
        ]
    )

    with repos.transaction():
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
    assert repos.transaction_events == ["commit"]
    assert repos.conn.commit_count == 0


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

    with repos.transaction():
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

    with repos.transaction():
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

    with repos.transaction():
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

    with repos.transaction():
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

    with repos.transaction():
        project_once(repos, now_ms=1_800_000_000_000, batch_size=10, ws_limit=10, poll_limit=10)

    assert repos.token_capture_tiers.upserts == [
        tier("chain_token", "sol:newer", 1, "ws_subscribed", "0"),
        tier("chain_token", "sol:older", 1, "ws_subscribed", "0"),
    ]


def test_worker_requires_formal_settings_and_db_contracts() -> None:
    db = FakeDB(FakeRepos([]))

    with pytest.raises(RuntimeError, match="token_capture_tier_settings_required"):
        TokenCaptureTierWorker(pool_bundle=db, settings=None)
    with pytest.raises(RuntimeError, match="token_capture_tier_db_required"):
        TokenCaptureTierWorker(pool_bundle=None, settings=_worker_settings())


def test_worker_reads_formal_settings_fields_directly() -> None:
    db = FakeDB(FakeRepos([]))

    with pytest.raises(AttributeError, match="batch_size"):
        TokenCaptureTierWorker(
            pool_bundle=db,
            settings=SimpleNamespace(enabled=True, interval_seconds=30.0, ws_limit=1, poll_limit=1),
        )
    with pytest.raises(AttributeError, match="ws_limit"):
        TokenCaptureTierWorker(
            pool_bundle=db,
            settings=SimpleNamespace(enabled=True, interval_seconds=30.0, batch_size=5, poll_limit=1),
        )
    with pytest.raises(AttributeError, match="poll_limit"):
        TokenCaptureTierWorker(
            pool_bundle=db,
            settings=SimpleNamespace(enabled=True, interval_seconds=30.0, batch_size=5, ws_limit=1),
        )

    lease_repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    lease_worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(lease_repos),
        settings=SimpleNamespace(enabled=True, interval_seconds=30.0, batch_size=5, ws_limit=1, poll_limit=1),
    )

    with pytest.raises(AttributeError, match="lease_ms"):
        asyncio.run(lease_worker.run_once(now_ms=1_800_000_000_000))

    assert lease_repos.token_capture_tier_dirty_targets.claim_calls == []
    assert lease_repos.token_capture_tiers.upserts == []
    assert lease_repos.token_capture_tier_dirty_targets.done_count == 0


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        pytest.param("batch_size", 0, "token_capture_tier_batch_size_required", id="batch-zero"),
        pytest.param("batch_size", True, "token_capture_tier_batch_size_required", id="batch-bool"),
        pytest.param("batch_size", "5", "token_capture_tier_batch_size_required", id="batch-string"),
        pytest.param("ws_limit", -1, "token_capture_tier_ws_limit_required", id="ws-negative"),
        pytest.param("ws_limit", True, "token_capture_tier_ws_limit_required", id="ws-bool"),
        pytest.param("ws_limit", "1", "token_capture_tier_ws_limit_required", id="ws-string"),
        pytest.param("poll_limit", -1, "token_capture_tier_poll_limit_required", id="poll-negative"),
        pytest.param("poll_limit", True, "token_capture_tier_poll_limit_required", id="poll-bool"),
        pytest.param("poll_limit", "1", "token_capture_tier_poll_limit_required", id="poll-string"),
    ],
)
def test_worker_rejects_malformed_runtime_settings(
    field: str,
    value: Any,
    error_code: str,
) -> None:
    settings = _worker_settings()
    setattr(settings, field, value)

    with pytest.raises(ValueError, match=error_code):
        TokenCaptureTierWorker(pool_bundle=FakeDB(FakeRepos([])), settings=settings)


@pytest.mark.parametrize("lease_ms", [0, True, "60000"])
def test_worker_rejects_malformed_lease_before_claiming_dirty_target(lease_ms: Any) -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(repos),
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1, lease_ms=lease_ms),
    )

    with pytest.raises(ValueError, match="token_capture_tier_lease_ms_required"):
        asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert repos.token_capture_tier_dirty_targets.claim_calls == []
    assert repos.token_capture_tiers.upserts == []
    assert repos.token_capture_tier_dirty_targets.done_count == 0


def test_worker_run_once_returns_worker_result_processed_count() -> None:
    db = FakeDB(
        FakeRepos(
            [
                asset_target("asset-hot", chain_id="sol", address="hot", score=3),
                cex_target("cex-eth", provider="binance", native_market_id="ETHUSDT", score=2),
            ]
        )
    )
    worker = TokenCaptureTierWorker(
        pool_bundle=db,
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1),
    )

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 2
    assert result.notes["claimed"] == 1
    assert result.notes["rows_written"] == 2
    assert db.session_names == ["token_capture_tier"]


def test_worker_run_once_reports_zero_rows_written_when_projection_unchanged() -> None:
    db = FakeDB(
        FakeRepos(
            [
                asset_target("asset-hot", chain_id="sol", address="hot", score=3),
                cex_target("cex-eth", provider="binance", native_market_id="ETHUSDT", score=2),
            ],
            unchanged_upserts=True,
        )
    )
    worker = TokenCaptureTierWorker(
        pool_bundle=db,
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1),
    )

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["claimed"] == 1
    assert result.notes["rows_written"] == 0
    assert db.repos.token_capture_tier_dirty_targets.done_count == 1


def test_worker_retries_claim_when_projection_fails_instead_of_rolling_back_attempt() -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    repos.token_capture_tiers = InvalidChangedCountTokenCaptureTiers()
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(repos),
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1, retry_ms=7_000, max_attempts=3),
    )

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["rows_written"] == 0
    assert repos.transaction_events == ["rollback", "commit"]
    assert repos.token_capture_tier_dirty_targets.done_count == 0
    assert repos.token_capture_tier_dirty_targets.errors[0]["retry_ms"] == 7_000
    assert repos.token_capture_tier_dirty_targets.errors[0]["max_attempts"] == 3
    assert repos.token_capture_tier_dirty_targets.errors[0]["worker_name"] == "token_capture_tier"


def test_worker_does_not_report_rolled_back_rows_when_claim_completion_is_stale() -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    repos.token_capture_tier_dirty_targets.mark_done = lambda claims, **kwargs: 0
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(repos),
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1),
    )

    result = asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert result.processed == 0
    assert result.failed == 1
    assert result.notes["rows_written"] == 0
    assert "token_capture_tier_dirty_target_stale_completion" in result.notes["result"]["last_error"]


def test_project_once_rejects_invalid_changed_count_without_zero_fallback() -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    repos.token_capture_tiers = InvalidChangedCountTokenCaptureTiers()

    with pytest.raises(TypeError, match="token_capture_tier_changed_count_invalid"), repos.transaction():
        project_once(repos, now_ms=1_800_000_000_000, batch_size=5, ws_limit=1, poll_limit=1)

    assert repos.transaction_events == ["rollback"]
    assert repos.token_capture_tier_dirty_targets.done_count == 0


@pytest.mark.parametrize(
    ("override", "error_code"),
    [
        pytest.param({"batch_size": 0}, "token_capture_tier_project_batch_size_required", id="batch-zero"),
        pytest.param({"batch_size": True}, "token_capture_tier_project_batch_size_required", id="batch-bool"),
        pytest.param({"batch_size": "5"}, "token_capture_tier_project_batch_size_required", id="batch-string"),
        pytest.param({"ws_limit": -1}, "token_capture_tier_project_ws_limit_required", id="ws-negative"),
        pytest.param({"ws_limit": True}, "token_capture_tier_project_ws_limit_required", id="ws-bool"),
        pytest.param({"ws_limit": "1"}, "token_capture_tier_project_ws_limit_required", id="ws-string"),
        pytest.param({"poll_limit": -1}, "token_capture_tier_project_poll_limit_required", id="poll-negative"),
        pytest.param({"poll_limit": True}, "token_capture_tier_project_poll_limit_required", id="poll-bool"),
        pytest.param({"poll_limit": "1"}, "token_capture_tier_project_poll_limit_required", id="poll-string"),
    ],
)
def test_project_once_rejects_malformed_projection_limits_without_runtime_repair(
    override: dict[str, Any],
    error_code: str,
) -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    kwargs: dict[str, Any] = {"batch_size": 5, "ws_limit": 1, "poll_limit": 1}
    kwargs.update(override)

    with pytest.raises(ValueError, match=error_code), repos.transaction():
        project_once(repos, now_ms=1_800_000_000_000, **kwargs)

    assert repos.registry.calls == []
    assert repos.token_capture_tiers.upserts == []
    assert repos.token_capture_tiers.demotion_calls == []


def test_project_once_requires_external_session_transaction() -> None:
    repos = FakeRepos([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])

    with pytest.raises(RuntimeError, match="token_capture_tier_projection:transaction_required"):
        project_once(repos, now_ms=1_800_000_000_000, batch_size=5, ws_limit=1, poll_limit=1)

    assert repos.registry.calls == []
    assert repos.token_capture_tiers.upserts == []
    assert repos.token_capture_tiers.demotion_calls == []
    assert repos.conn.commit_count == 0


def test_worker_requires_session_transaction_before_projecting_claimed_dirty_target() -> None:
    repos = FakeReposWithoutTransaction([asset_target("asset-hot", chain_id="sol", address="hot", score=3)])
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(repos),
        telemetry=object(),
        settings=_worker_settings(batch_size=5, ws_limit=1, poll_limit=1),
    )

    with pytest.raises(AttributeError, match="transaction"):
        asyncio.run(worker.run_once(now_ms=1_800_000_000_000))

    assert len(repos.token_capture_tier_dirty_targets.claim_calls) == 1
    assert repos.token_capture_tier_dirty_targets.claim_calls[0]["commit"] is True
    assert repos.token_capture_tiers.upserts == []
    assert repos.token_capture_tier_dirty_targets.done_count == 0


def test_worker_exposes_single_writer_advisory_lock_key() -> None:
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(FakeRepos([])),
        telemetry=object(),
        settings=_worker_settings(),
    )

    assert ADVISORY_LOCK_KEY == 2026051503
    assert worker.SINGLE_WRITER_KEY == ADVISORY_LOCK_KEY
    assert worker._advisory_lock_key() == ADVISORY_LOCK_KEY


def test_worker_has_no_provider_dependency_slots() -> None:
    worker = TokenCaptureTierWorker(
        pool_bundle=FakeDB(FakeRepos([])),
        telemetry=object(),
        settings=_worker_settings(),
    )

    assert not hasattr(worker, "cex_market")
    assert not hasattr(worker, "dex_quote_market")
    assert not hasattr(worker, "stream_provider")


def test_default_workers_yaml_includes_token_capture_tier_settings() -> None:
    workers = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert workers.token_capture_tier.enabled is True
    assert workers.token_capture_tier.batch_size == 500
    assert workers.token_capture_tier.ws_limit == 100
    assert workers.token_capture_tier.poll_limit == 500
    assert workers.token_capture_tier.retry_ms == 30_000
    assert workers.token_capture_tier.max_attempts == 3
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
    assert "token_radar_publication_state" in conn.sql
    assert "token_radar_projection_coverage" not in conn.sql
    assert "SELECT computed_at_ms\n                FROM token_radar_current_rows" not in conn.sql
    assert "latest_sets.current_published_at_ms AS computed_at_ms" in conn.sql
    assert "current_generation_id" not in conn.sql
    assert "rows.generation_id = latest_sets.current_generation_id" not in conn.sql
    assert "token_radar_current_rows.computed_at_ms >= %s" not in conn.sql
    assert "token_radar_rows" not in conn.sql
    assert conn.params == (
        TOKEN_RADAR_PROJECTION_VERSION,
        1_800_000_000_000 - WINDOW_MS["24h"],
        TOKEN_RADAR_PROJECTION_VERSION,
        25,
    )


@pytest.mark.parametrize("limit", [-1, True, "25"])
def test_registry_ranked_live_market_targets_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = CapturingConn()

    with pytest.raises(ValueError, match="registry_ranked_live_market_targets_limit_required"):
        RegistryRepository(conn).ranked_live_market_targets(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            since_ms=1_800_000_000_000 - WINDOW_MS["24h"],
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.sql == ""
    assert conn.params == ()


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
        unchanged_upserts: bool = False,
    ) -> None:
        self.registry = FakeRegistry(rows)
        self.token_capture_tiers = FakeTokenCaptureTiers(
            existing_tiers=existing_tiers or [],
            unchanged_upserts=unchanged_upserts,
        )
        self.token_capture_tier_dirty_targets = FakeCaptureDirtyTargets()
        self.conn = FakeConn()
        self.transaction_depth = 0
        self.transaction_events: list[str] = []

    def transaction(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation: str) -> None:
        if self.transaction_depth <= 0:
            raise RuntimeError(f"{operation}:transaction_required")


class FakeReposWithoutTransaction:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.registry = FakeRegistry(rows)
        self.token_capture_tiers = FakeTokenCaptureTiers()
        self.token_capture_tier_dirty_targets = FakeCaptureDirtyTargets()
        self.conn = FakeConn()


class FakeTransaction(AbstractContextManager[FakeRepos]):
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos

    def __enter__(self) -> FakeRepos:
        self.repos.transaction_depth += 1
        return self.repos

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self.repos.transaction_events.append("rollback" if exc_type is not None else "commit")
        self.repos.transaction_depth -= 1
        return False


class FakeRegistry:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def ranked_live_market_targets(self, *, projection_version: str, since_ms: int, limit: int):
        self.calls.append({"projection_version": projection_version, "since_ms": since_ms, "limit": limit})
        return self.rows[:limit]


class FakeTokenCaptureTiers:
    def __init__(
        self,
        *,
        existing_tiers: list[dict[str, object]] | None = None,
        unchanged_upserts: bool = False,
    ) -> None:
        self.upserts: list[dict[str, object]] = []
        self.demotion_calls: list[dict[str, object]] = []
        self.demoted: list[tuple[str, str]] = []
        self._existing: list[dict[str, object]] = list(existing_tiers or [])
        self.unchanged_upserts = bool(unchanged_upserts)

    def upsert_tier(self, **kwargs) -> bool:
        self.upserts.append(kwargs)
        return not self.unchanged_upserts

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


class InvalidChangedCountTokenCaptureTiers(FakeTokenCaptureTiers):
    def upsert_tier(self, **kwargs):
        self.upserts.append(kwargs)


class FakeCaptureDirtyTargets:
    def __init__(self) -> None:
        self.done_count = 0
        self.claim_calls: list[dict[str, object]] = []
        self.errors: list[dict[str, Any]] = []

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
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
        self.done_count += len(claims)
        return len(claims)

    def mark_error(self, claims, **kwargs):
        self.errors.extend({**dict(claim), **kwargs} for claim in claims)
        return len(claims)


class FakeConn:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class FakeDB:
    def __init__(self, repos: Any) -> None:
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
