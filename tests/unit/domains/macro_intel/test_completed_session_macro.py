from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from parallax.domains.macro_intel.services.completed_session_macro import (
    CompletedSessionMacro,
    completed_session_close_ms,
    resolve_completed_session,
)
from parallax.domains.macro_intel.services.macro_research import (
    FrozenMacroEvidenceScope,
    MacroResearchAgentResult,
    MacroResearchArtifact,
    MacroResearchAudit,
    MacroResearchSection,
)

SESSION = date(2026, 7, 23)
_NEW_YORK = ZoneInfo("America/New_York")


def test_completed_session_publication_replays_without_model_or_database_writes() -> None:
    cutoff_ms = completed_session_close_ms(SESSION)
    now_ms = cutoff_ms + 1_800_000
    db = _FakeDB()
    agent = _SuccessfulAgent(db)
    runtime = CompletedSessionMacro(
        db=db,
        settings=_settings(),
        agent=agent,
        lease_owner="test-lease",
        clock_ms=lambda: now_ms,
    )

    first = asyncio.run(runtime.run(SESSION))
    writes_after_first = db.repository.writes
    persisted = asyncio.run(runtime.read(SESSION))
    replay = asyncio.run(runtime.run(SESSION))

    assert first.status == "published"
    assert first.model_calls == 4
    assert first.run_rows_written == 3
    assert first.publication_rows_written == 1
    assert first.artifact_hash
    assert persisted is not None
    assert persisted.status == "published"
    assert persisted.model_calls == 0
    assert replay.status == "published"
    assert replay.model_calls == 0
    assert replay.run_rows_written == 0
    assert replay.publication_rows_written == 0
    assert agent.calls == 1
    assert db.repository.writes == writes_after_first
    assert agent.transaction_depths == [0]


def test_completed_session_failure_releases_lease_for_retry() -> None:
    cutoff_ms = completed_session_close_ms(SESSION)
    now_ms = cutoff_ms + 1_800_000
    db = _FakeDB()
    runtime = CompletedSessionMacro(
        db=db,
        settings=_settings(),
        agent=_FailingAgent(db),
        lease_owner="test-lease",
        clock_ms=lambda: now_ms,
    )

    result = asyncio.run(runtime.run(SESSION))

    assert result.status == "retryable"
    assert result.model_calls == 1
    assert result.publication_rows_written == 0
    assert result.last_error_code == "macro_research_runtimeerror"
    assert db.repository.runs[SESSION]["status"] == "retryable"
    assert db.transaction_depth == 0


def test_completed_session_renews_lease_during_long_agent_run() -> None:
    cutoff_ms = completed_session_close_ms(SESSION)
    now_ms = cutoff_ms + 1_800_000
    db = _FakeDB()
    agent = _WaitForLeaseRenewalAgent(db)
    runtime = CompletedSessionMacro(
        db=db,
        settings=_settings(lease_ms=30),
        agent=agent,
        lease_owner="test-lease",
        clock_ms=lambda: now_ms + db.repository.renew_calls,
    )

    result = asyncio.run(asyncio.wait_for(runtime.run(SESSION), timeout=1))

    assert result.status == "published"
    assert db.repository.renew_calls >= 1
    assert db.repository.publish_calls == 1
    assert db.repository.mark_error_calls == 0


def test_completed_session_cancels_analysis_without_stale_owner_writes_when_lease_is_lost() -> None:
    cutoff_ms = completed_session_close_ms(SESSION)
    now_ms = cutoff_ms + 1_800_000
    db = _FakeDB()
    db.repository.renew_result = False
    agent = _CancellationAwareAgent(db)
    runtime = CompletedSessionMacro(
        db=db,
        settings=_settings(lease_ms=3),
        agent=agent,
        lease_owner="test-lease",
        clock_ms=lambda: now_ms,
    )

    result = asyncio.run(asyncio.wait_for(runtime.run(SESSION), timeout=1))

    assert result.status == "running"
    assert agent.cancelled is True
    assert db.repository.renew_calls == 1
    assert db.repository.publish_calls == 0
    assert db.repository.mark_error_calls == 0
    assert db.repository.runs[SESSION]["lease_owner"] == "replacement-owner"


def test_resolve_completed_session_obeys_close_settle_and_market_calendar() -> None:
    before_settle = _epoch_ms(datetime(2026, 7, 23, 16, 15, tzinfo=_NEW_YORK))
    after_settle = _epoch_ms(datetime(2026, 7, 23, 16, 30, tzinfo=_NEW_YORK))
    independence_day = _epoch_ms(datetime(2026, 7, 4, 18, 0, tzinfo=_NEW_YORK))

    assert resolve_completed_session(
        now_ms=before_settle,
        settle_delay_seconds=1_800,
    ) == date(2026, 7, 22)
    assert (
        resolve_completed_session(
            now_ms=after_settle,
            settle_delay_seconds=1_800,
        )
        == SESSION
    )
    assert resolve_completed_session(
        now_ms=independence_day,
        settle_delay_seconds=0,
    ) == date(2026, 7, 2)


class _SuccessfulAgent:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.calls = 0
        self.transaction_depths: list[int] = []

    async def analyze(
        self,
        scope: FrozenMacroEvidenceScope,
    ) -> MacroResearchAgentResult:
        self.calls += 1
        self.transaction_depths.append(self._db.transaction_depth)
        artifact = MacroResearchArtifact(
            session_date=scope.session_date,
            market_cutoff_ms=scope.market_cutoff_ms,
            title="宏观研究",
            executive_summary="证据显示当前环境仍有分歧。",
            sections=(
                MacroResearchSection(
                    section_id="overview",
                    title="总览",
                    body_markdown="证据显示当前环境仍有分歧。",
                ),
            ),
        )
        return MacroResearchAgentResult(
            artifact=artifact,
            audit=MacroResearchAudit(
                scope_id=scope.scope_id,
                deepagents_version="test",
                model_name="fake-model",
                prompt_version="prompt-v1",
                workflow_version="workflow-v1",
                model_calls=4,
            ),
        )


class _FailingAgent:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    async def analyze(
        self,
        scope: FrozenMacroEvidenceScope,
    ) -> MacroResearchAgentResult:
        del scope
        assert self._db.transaction_depth == 0
        raise RuntimeError("provider unavailable")


class _WaitForLeaseRenewalAgent(_SuccessfulAgent):
    async def analyze(
        self,
        scope: FrozenMacroEvidenceScope,
    ) -> MacroResearchAgentResult:
        while self._db.repository.renew_calls == 0:
            await asyncio.sleep(0.001)
        return await super().analyze(scope)


class _CancellationAwareAgent:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.cancelled = False

    async def analyze(
        self,
        scope: FrozenMacroEvidenceScope,
    ) -> MacroResearchAgentResult:
        del scope
        assert self._db.transaction_depth == 0
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _FakeDB:
    def __init__(self) -> None:
        self.transaction_depth = 0
        self.repository = _FakeMacroResearchRepository()

    @contextmanager
    def worker_session(
        self,
        _name: str,
        statement_timeout_seconds: float,
    ):
        del statement_timeout_seconds
        yield _FakeRepositorySession(self)


class _FakeRepositorySession:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.macro_research = db.repository

    @contextmanager
    def transaction(self):
        self._db.transaction_depth += 1
        try:
            yield
        finally:
            self._db.transaction_depth -= 1

    def require_transaction(self, *, operation: str) -> None:
        if self._db.transaction_depth != 1:
            raise RuntimeError(f"{operation}:transaction_required")


class _FakeMacroResearchRepository:
    def __init__(self) -> None:
        self.runs: dict[date, dict[str, Any]] = {}
        self.publications: dict[date, dict[str, Any]] = {}
        self.writes = 0
        self.renew_calls = 0
        self.renew_result = True
        self.publish_calls = 0
        self.mark_error_calls = 0

    def publication_exists(self, session_date: date) -> bool:
        return session_date in self.publications

    def scheduling_state(self, *, through_date: date) -> dict[str, date | None]:
        del through_date
        open_sessions = [
            session_date
            for session_date, row in self.runs.items()
            if row["status"] in {"pending", "running", "retryable"}
        ]
        return {
            "open_session": min(open_sessions) if open_sessions else None,
            "latest_session": max(self.runs) if self.runs else None,
        }

    def ensure_run(self, **kwargs: Any) -> bool:
        session_date = kwargs["session_date"]
        if session_date in self.runs:
            return False
        self.runs[session_date] = {
            **kwargs,
            "status": "pending",
            "attempt_count": 0,
        }
        self.writes += 1
        return True

    def run_record(self, session_date: date) -> dict[str, Any] | None:
        row = self.runs.get(session_date)
        return dict(row) if row is not None else None

    def claim_run(self, **kwargs: Any) -> dict[str, Any] | None:
        row = self.runs[kwargs["session_date"]]
        if row["status"] not in {"pending", "retryable"}:
            return None
        row.update(
            {
                "status": "running",
                "attempt_count": int(row["attempt_count"]) + 1,
                "lease_owner": kwargs["lease_owner"],
                "leased_until_ms": int(kwargs["now_ms"]) + int(kwargs["lease_ms"]),
            }
        )
        self.writes += 1
        return dict(row)

    def renew_run_lease(self, **kwargs: Any) -> bool:
        self.renew_calls += 1
        row = self.runs[kwargs["session_date"]]
        if not self.renew_result:
            row["lease_owner"] = "replacement-owner"
            row["attempt_count"] = int(row["attempt_count"]) + 1
            self.writes += 1
            return False
        if row["status"] != "running" or row["lease_owner"] != kwargs["lease_owner"]:
            return False
        row["leased_until_ms"] = int(kwargs["now_ms"]) + int(kwargs["lease_ms"])
        self.writes += 1
        return True

    def publish(self, **kwargs: Any) -> bool:
        self.publish_calls += 1
        session_date = kwargs["session_date"]
        if session_date in self.publications:
            return False
        self.publications[session_date] = {
            "artifact_json": kwargs["artifact"],
            "report_markdown": kwargs["report_markdown"],
            "audit_json": kwargs["audit"],
            "model_name": kwargs["model_name"],
            "prompt_version": kwargs["prompt_version"],
            "workflow_version": kwargs["workflow_version"],
            "artifact_hash": kwargs["artifact_hash"],
            "published_at_ms": kwargs["now_ms"],
        }
        self.runs[session_date]["status"] = "published"
        self.writes += 2
        return True

    def mark_run_error(self, **kwargs: Any) -> str:
        self.mark_error_calls += 1
        row = self.runs[kwargs["session_date"]]
        row["status"] = "retryable"
        row["last_error_code"] = kwargs["error_code"]
        row["last_error_message"] = kwargs["error_message"]
        self.writes += 1
        return "retryable"

    def research_state(self, session_date: date) -> dict[str, Any] | None:
        row = self.runs.get(session_date)
        if row is None:
            return None
        publication = self.publications.get(session_date, {})
        return {
            **row,
            "run_status": row["status"],
            "last_error_code": row.get("last_error_code"),
            "last_error_message": row.get("last_error_message"),
            **publication,
        }


def _settings(*, lease_ms: int = 900_000) -> SimpleNamespace:
    return SimpleNamespace(
        settle_delay_seconds=1_800,
        statement_timeout_seconds=120,
        lease_ms=lease_ms,
        retry_ms=900_000,
        max_attempts=3,
    )


def _epoch_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1_000)
