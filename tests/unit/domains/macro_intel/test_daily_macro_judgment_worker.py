from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.macro_intel.runtime.daily_macro_judgment_worker import (
    DailyMacroJudgmentWorker,
    _eligible_session,
    _next_session_to_freeze,
)
from parallax.domains.macro_intel.services.daily_macro_judgment import (
    EvidencePackHealth,
    JudgmentGateError,
    MacroEvidencePack,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    market_session_close_ms,
    market_session_offset,
)
from parallax.platform.config.settings import DailyMacroJudgmentWorkerSettings

SESSION = date(2026, 7, 22)
CUTOFF_MS = market_session_close_ms(SESSION)
NOW_MS = CUTOFF_MS + 31 * 60 * 1_000


@pytest.mark.parametrize(
    ("agent_error", "expected_status", "expected_disposition"),
    (
        (JudgmentGateError("daily_macro_judgment_schema_invalid"), "blocked", None),
        (RuntimeError("provider unavailable"), "retryable", None),
    ),
)
def test_worker_model_io_is_transaction_free_and_failure_state_is_deterministic(
    agent_error: Exception,
    expected_status: str,
    expected_disposition: str | None,
) -> None:
    pack = _pack(health=EvidencePackHealth(status="ready"))
    repo = _FakeRepository(pack)
    db = _FakeDB(repo)
    agent = _FailingAgent(db, error=agent_error)
    worker = _worker(db, agent=agent)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["publication"] == expected_status
    assert result.notes["model_calls"] == 1
    assert agent.calls == 1
    assert db.transaction_depth == 0
    if expected_status == "blocked":
        assert repo.blocked == [
            {
                "session_date": SESSION,
                "lease_owner": "daily_macro_judgment",
                "error": "daily_macro_judgment_schema_invalid",
                "reviewer_disposition": expected_disposition,
                "now_ms": NOW_MS,
            }
        ]
        assert repo.errors == []
    else:
        assert repo.errors == [
            {
                "session_date": SESSION,
                "lease_owner": "daily_macro_judgment",
                "error": "provider unavailable",
                "retry_ms": 900_000,
                "now_ms": NOW_MS,
            }
        ]
        assert repo.blocked == []


def test_globally_blocked_pack_makes_zero_model_calls_and_publishes_nothing() -> None:
    pack = _pack(
        health=EvidencePackHealth(
            status="blocked",
            global_reasons=("cutoff_lineage_untrustworthy",),
        )
    )
    repo = _FakeRepository(pack)
    db = _FakeDB(repo)
    agent = _FailingAgent(db, error=AssertionError("agent must not run"))
    worker = _worker(db, agent=agent)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.notes["publication"] == "blocked"
    assert result.notes["model_calls"] == 0
    assert agent.calls == 0
    assert repo.published == []
    assert repo.blocked[0]["error"] == "macro_evidence_pack_blocked:cutoff_lineage_untrustworthy"


def test_settle_delay_uses_previous_completed_market_session() -> None:
    before_settle = CUTOFF_MS + 29 * 60 * 1_000

    assert _eligible_session(now_ms=before_settle, settle_delay_seconds=30 * 60) == market_session_offset(
        SESSION,
        sessions=1,
    )
    assert _eligible_session(now_ms=NOW_MS, settle_delay_seconds=30 * 60) == SESSION


def test_catch_up_freezes_at_most_one_missing_market_session_per_iteration() -> None:
    previous_session = market_session_offset(SESSION, sessions=1)

    assert (
        _next_session_to_freeze(
            current_session=SESSION,
            latest_job_session=None,
        )
        == SESSION
    )
    assert (
        _next_session_to_freeze(
            current_session=SESSION,
            latest_job_session=previous_session,
        )
        == SESSION
    )
    assert (
        _next_session_to_freeze(
            current_session=SESSION,
            latest_job_session=SESSION,
        )
        is None
    )


class _FailingAgent:
    def __init__(self, db: _FakeDB, *, error: Exception) -> None:
        self.db = db
        self.error = error
        self.calls = 0

    async def analyze(self, evidence_pack: MacroEvidencePack) -> Any:
        assert evidence_pack.session_date == SESSION
        assert self.db.transaction_depth == 0
        self.calls += 1
        raise self.error


class _FakeRepository:
    def __init__(self, pack: MacroEvidencePack) -> None:
        self.pack = pack
        self.claimed = False
        self.blocked: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []

    def publications_missing_outcomes(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit == 32
        return []

    def publication_exists(self, session_date: date) -> bool:
        assert session_date == SESSION
        return False

    def latest_job_session(self) -> date:
        return SESSION

    def claim_due_job(self, **kwargs: Any) -> dict[str, Any] | None:
        assert kwargs == {
            "lease_owner": "daily_macro_judgment",
            "lease_ms": 600_000,
            "now_ms": NOW_MS,
        }
        if self.claimed:
            return None
        self.claimed = True
        return {"evidence_pack_json": self.pack.model_dump(mode="json")}

    def mark_job_blocked(self, **kwargs: Any) -> None:
        self.blocked.append(kwargs)

    def mark_job_error(self, **kwargs: Any) -> str:
        self.errors.append(kwargs)
        return "retryable"

    def publish(self, **kwargs: Any) -> bool:
        self.published.append(kwargs)
        return True


class _FakeDB:
    def __init__(self, repository: _FakeRepository) -> None:
        self.repository = repository
        self.transaction_depth = 0

    @contextmanager
    def worker_session(self, name: str, *, statement_timeout_seconds: float):
        assert name == "daily_macro_judgment"
        assert statement_timeout_seconds == 120

        @contextmanager
        def transaction():
            self.transaction_depth += 1
            try:
                yield
            finally:
                self.transaction_depth -= 1

        yield SimpleNamespace(
            daily_macro_judgments=self.repository,
            transaction=transaction,
            require_transaction=lambda **_: _require_transaction(self),
        )


def _require_transaction(db: _FakeDB) -> None:
    assert db.transaction_depth > 0


def _pack(*, health: EvidencePackHealth) -> MacroEvidencePack:
    return MacroEvidencePack(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        sealed_at_ms=NOW_MS,
        projection_version="macro_decision_v2",
        pages={
            "overview": {"page_id": "overview"},
            "cross_asset": {"page_id": "cross_asset"},
            "rates_inflation": {"page_id": "rates_inflation"},
            "growth_labor": {"page_id": "growth_labor"},
            "liquidity_funding": {"page_id": "liquidity_funding"},
            "credit": {"page_id": "credit"},
        },
        evidence=(),
        health=health,
    )


def _worker(db: _FakeDB, *, agent: _FailingAgent) -> DailyMacroJudgmentWorker:
    return DailyMacroJudgmentWorker(
        settings=DailyMacroJudgmentWorkerSettings(enabled=True),
        db=db,
        telemetry=SimpleNamespace(),
        agent=agent,
    )
