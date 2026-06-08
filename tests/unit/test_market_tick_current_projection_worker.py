from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.runtime.market_tick_current_projection_worker import (
    MarketTickCurrentProjectionWorker,
)


def test_worker_claims_dirty_target_writes_current_enqueues_radar_and_wakes_after_success() -> None:
    claim = _claim("chain_token", "solana:abc")
    tick = _tick_row("chain_token", "solana:abc", "tick-1")
    db = _FakeDB(claims=[claim], latest_by_target={("chain_token", "solana:abc"): tick})
    wake = _FakeWakeEmitter()
    worker = _worker(db=db, wake_emitter=wake)

    result = asyncio.run(worker.run_once(now_ms=1_700_000_010_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert result.failed == 0
    assert result.notes == {
        "claimed": 1,
        "changed": 1,
        "missing": 0,
        "failed": 0,
        "token_radar_dirty_enqueued": 1,
    }
    assert db.claim_calls == [
        {
            "limit": 100,
            "now_ms": 1_700_000_010_000,
            "lease_ms": 120_000,
            "lease_owner": "market_tick_current_projection",
            "commit": True,
        }
    ]
    tx = db.transactions[0].repos
    assert tx.market_tick_current.upserts == [(tick, 1_700_000_010_000)]
    assert tx.token_radar_dirty_targets.market_enqueues == [
        {
            "rows": [("chain_token", "solana:abc")],
            "reason": "market_tick_current_changed",
            "now_ms": 1_700_000_010_000,
            "commit": False,
        }
    ]
    assert tx.market_tick_current_dirty_targets.done == [(claim, 1_700_000_010_000, False)]
    assert wake.market_tick_current_notifications == [{"target_type": "batch", "target_id": "market_tick_current"}]


def test_worker_does_not_wake_token_radar_when_dirty_enqueue_returns_zero() -> None:
    claim = _claim("chain_token", "solana:abc")
    tick = _tick_row("chain_token", "solana:abc", "tick-1")
    db = _FakeDB(
        claims=[claim],
        latest_by_target={("chain_token", "solana:abc"): tick},
        token_radar_enqueue_counts=[0],
    )
    wake = _FakeWakeEmitter()

    result = asyncio.run(_worker(db=db, wake_emitter=wake).run_once(now_ms=1_700_000_010_000))

    assert result.processed == 1
    assert result.failed == 0
    assert result.notes == {
        "claimed": 1,
        "changed": 1,
        "missing": 0,
        "failed": 0,
        "token_radar_dirty_enqueued": 0,
    }
    tx = db.transactions[0].repos
    assert tx.token_radar_dirty_targets.market_enqueues == [
        {
            "rows": [("chain_token", "solana:abc")],
            "reason": "market_tick_current_changed",
            "now_ms": 1_700_000_010_000,
            "commit": False,
        }
    ]
    assert wake.market_tick_current_notifications == []


def test_worker_coalesces_token_radar_wake_for_multiple_changed_claims() -> None:
    claims = [_claim("chain_token", "solana:abc"), _claim("cex_symbol", "binance:BTCUSDT")]
    ticks = {
        ("chain_token", "solana:abc"): _tick_row("chain_token", "solana:abc", "tick-1"),
        ("cex_symbol", "binance:BTCUSDT"): _tick_row("cex_symbol", "binance:BTCUSDT", "tick-2"),
    }
    db = _FakeDB(claims=claims, latest_by_target=ticks, token_radar_enqueue_counts=[1, 1])
    wake = _FakeWakeEmitter()

    result = asyncio.run(_worker(db=db, wake_emitter=wake).run_once(now_ms=1_700_000_010_000))

    assert result.processed == 2
    assert result.failed == 0
    assert result.notes == {
        "claimed": 2,
        "changed": 2,
        "missing": 0,
        "failed": 0,
        "token_radar_dirty_enqueued": 2,
    }
    assert wake.market_tick_current_notifications == [{"target_type": "batch", "target_id": "market_tick_current"}]


def test_worker_marks_done_without_radar_enqueue_when_latest_tick_missing() -> None:
    claim = _claim("cex_symbol", "binance:BTCUSDT")
    db = _FakeDB(claims=[claim], latest_by_target={})
    wake = _FakeWakeEmitter()

    result = asyncio.run(_worker(db=db, wake_emitter=wake).run_once(now_ms=1_700_000_010_000))

    tx = db.transactions[0].repos
    assert result.notes == {
        "claimed": 1,
        "changed": 0,
        "missing": 1,
        "failed": 0,
        "token_radar_dirty_enqueued": 0,
    }
    assert tx.market_tick_current.upserts == []
    assert tx.token_radar_dirty_targets.market_enqueues == []
    assert tx.market_tick_current_dirty_targets.done == [(claim, 1_700_000_010_000, False)]
    assert wake.market_tick_current_notifications == []


def test_worker_marks_done_without_radar_enqueue_when_current_row_is_unchanged() -> None:
    claim = _claim("chain_token", "solana:abc")
    tick = _tick_row("chain_token", "solana:abc", "tick-1")
    db = _FakeDB(claims=[claim], latest_by_target={("chain_token", "solana:abc"): tick}, upsert_changed=False)

    result = asyncio.run(_worker(db=db).run_once(now_ms=1_700_000_010_000))

    tx = db.transactions[0].repos
    assert result.notes == {
        "claimed": 1,
        "changed": 0,
        "missing": 0,
        "failed": 0,
        "token_radar_dirty_enqueued": 0,
    }
    assert tx.token_radar_dirty_targets.market_enqueues == []
    assert tx.market_tick_current_dirty_targets.done == [(claim, 1_700_000_010_000, False)]


def test_worker_marks_error_on_processing_failure() -> None:
    claim = _claim("chain_token", "solana:abc")
    db = _FakeDB(claims=[claim], latest_by_target={}, latest_error=RuntimeError("boom"))

    result = asyncio.run(_worker(db=db).run_once(now_ms=1_700_000_010_000))

    assert result.processed == 0
    assert result.failed == 1
    assert result.notes == {
        "claimed": 1,
        "changed": 0,
        "missing": 0,
        "failed": 1,
        "token_radar_dirty_enqueued": 0,
    }
    assert db.transactions[0].rolled_back is True
    assert db.transactions[1].repos.market_tick_current_dirty_targets.errors == [
        {
            "claims": [claim],
            "error": "RuntimeError: boom",
            "retry_ms": 30_000,
            "now_ms": 1_700_000_010_000,
            "commit": False,
        }
    ]


def test_worker_passes_wake_waiter_and_statement_timeout_from_settings() -> None:
    db = _FakeDB(claims=[])
    wake_waiter = object()
    worker = _worker(db=db, wake_waiter=wake_waiter)

    assert worker.wake_waiter is wake_waiter
    result = asyncio.run(worker.run_once(now_ms=1_700_000_010_000))

    assert result.skipped == 1
    assert result.notes == {
        "claimed": 0,
        "changed": 0,
        "missing": 0,
        "failed": 0,
        "token_radar_dirty_enqueued": 0,
    }
    assert db.worker_sessions == [{"name": "market_tick_current_projection", "statement_timeout_seconds": 30.0}]


def _worker(
    *,
    db: _FakeDB,
    wake_emitter: _FakeWakeEmitter | None = None,
    wake_waiter: object | None = None,
) -> MarketTickCurrentProjectionWorker:
    return MarketTickCurrentProjectionWorker(
        name="market_tick_current_projection",
        settings=SimpleNamespace(
            enabled=True,
            batch_size=100,
            lease_ms=120_000,
            retry_ms=30_000,
            statement_timeout_seconds=30.0,
            soft_timeout_seconds=120.0,
            hard_timeout_seconds=180.0,
        ),
        db=db,
        telemetry=object(),
        wake_emitter=wake_emitter or _FakeWakeEmitter(),
        wake_waiter=wake_waiter,
    )


def _claim(target_type: str, target_id: str) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "payload_hash": "claim-hash",
        "lease_owner": "market_tick_current_projection",
        "attempt_count": 1,
    }


def _tick_row(target_type: str, target_id: str, tick_id: str) -> dict[str, Any]:
    return {"target_type": target_type, "target_id": target_id, "tick_id": tick_id}


class _FakeDB:
    def __init__(
        self,
        *,
        claims: list[dict[str, Any]],
        latest_by_target: dict[tuple[str, str], dict[str, Any]] | None = None,
        upsert_changed: bool = True,
        latest_error: Exception | None = None,
        token_radar_enqueue_counts: list[int] | None = None,
    ) -> None:
        self.claims = claims
        self.latest_by_target = latest_by_target or {}
        self.upsert_changed = upsert_changed
        self.latest_error = latest_error
        self.token_radar_enqueue_counts = list(token_radar_enqueue_counts or [])
        self.worker_sessions: list[dict[str, Any]] = []
        self.claim_calls: list[dict[str, Any]] = []
        self.transactions: list[_FakeTransaction] = []

    def next_token_radar_enqueue_count(self, default: int) -> int:
        if self.token_radar_enqueue_counts:
            return self.token_radar_enqueue_counts.pop(0)
        return default

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        self.worker_sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        repos = _FakeRepos(self)
        yield repos

    @contextmanager
    def worker_transaction(self, name: str, statement_timeout_seconds: float | None = None):
        transaction = _FakeTransaction(_FakeRepos(self))
        self.transactions.append(transaction)
        try:
            yield transaction.repos
        except BaseException:
            transaction.rolled_back = True
            raise
        else:
            transaction.committed = True


class _FakeTransaction:
    def __init__(self, repos: _FakeRepos) -> None:
        self.repos = repos
        self.committed = False
        self.rolled_back = False


class _FakeRepos:
    def __init__(self, db: _FakeDB) -> None:
        self.market_tick_current_dirty_targets = _FakeDirtyTargets(db)
        self.market_tick_current = _FakeCurrentRepo(db)
        self.token_radar_dirty_targets = _FakeRadarDirtyTargets(db)


class _FakeDirtyTargets:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self.done: list[tuple[dict[str, Any], int, bool]] = []
        self.errors: list[dict[str, Any]] = []

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.db.claim_calls.append(kwargs)
        return list(self.db.claims)

    def mark_done(self, claims: list[dict[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        self.done.extend((claim, now_ms, commit) for claim in claims)
        return len(claims)

    def mark_error(
        self,
        claims: list[dict[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        self.errors.append(
            {
                "claims": claims,
                "error": error,
                "retry_ms": retry_ms,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(claims)


class _FakeCurrentRepo:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self.upserts: list[tuple[dict[str, Any], int]] = []

    def latest_tick_for_target(self, *, target_type: str, target_id: str) -> dict[str, Any] | None:
        if self.db.latest_error is not None:
            raise self.db.latest_error
        return self.db.latest_by_target.get((target_type, target_id))

    def upsert_current_from_tick(self, tick_row: dict[str, Any], *, now_ms: int) -> bool:
        self.upserts.append((tick_row, now_ms))
        return self.db.upsert_changed


class _FakeRadarDirtyTargets:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self.market_enqueues: list[dict[str, Any]] = []

    def enqueue_market_targets(self, rows, *, reason: str, now_ms: int, commit: bool = True):
        materialized = list(rows)
        self.market_enqueues.append({"rows": materialized, "reason": reason, "now_ms": now_ms, "commit": commit})
        return self.db.next_token_radar_enqueue_count(default=len(materialized))


class _FakeWakeEmitter:
    def __init__(self) -> None:
        self.market_tick_current_notifications: list[dict[str, str]] = []

    def notify_market_tick_current_updated(self, *, target_type: str, target_id: str) -> None:
        self.market_tick_current_notifications.append({"target_type": target_type, "target_id": target_id})
