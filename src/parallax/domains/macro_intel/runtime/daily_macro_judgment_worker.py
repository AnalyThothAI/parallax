from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import date
from typing import Any, cast

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    DAILY_MACRO_JUDGMENT_RENDERER_VERSION,
    DAILY_MACRO_JUDGMENT_SCHEMA_VERSION,
    DailyMacroOutcome,
    EvidencePackHealthStatus,
    JudgmentGateError,
    MacroEvidencePack,
    MacroJudgmentAgent,
    render_daily_macro_judgment_zh,
    require_renderer_consistency,
    validate_daily_macro_judgment,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    market_session_advance,
    market_session_close_ms,
    market_session_offset,
    resolve_market_cutoff,
)
from parallax.domains.macro_intel.services.macro_evidence_pack import (
    MACRO_EVIDENCE_COMPILER_VERSION,
    compile_macro_evidence_pack,
)
from parallax.platform.config.settings import DailyMacroJudgmentWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class DailyMacroJudgmentWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: DailyMacroJudgmentWorkerSettings,
        db: Any,
        telemetry: Any,
        agent: MacroJudgmentAgent,
        clock_ms: Callable[[], int] | None = None,
        name: str = "daily_macro_judgment",
    ) -> None:
        if db is None:
            raise RuntimeError("daily_macro_judgment_db_required")
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self._agent = agent
        self._clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self._clock_ms())
        outcome_writes = self._mature_outcomes(now_ms=now)
        current_session = _eligible_session(
            now_ms=now,
            settle_delay_seconds=self._settle_delay_seconds(),
        )
        with self._repository_session() as repos, repos.transaction():
            current_published = repos.daily_macro_judgments.publication_exists(current_session)
            latest_job_session = repos.daily_macro_judgments.latest_job_session()
        freeze_session = _next_session_to_freeze(
            current_session=current_session,
            latest_job_session=latest_job_session,
        )
        if freeze_session is not None:
            self._freeze_job(session_date=freeze_session, now_ms=now)
        claimed = self._claim_job(now_ms=now)
        if claimed is None:
            return WorkerResult(
                processed=outcome_writes,
                notes={
                    "session_date": current_session.isoformat(),
                    "publication": "unchanged" if current_published else "not_due",
                    "model_calls": 0,
                    "publication_rows_written": 0,
                    "outcome_rows_written": outcome_writes,
                },
            )
        evidence_pack = MacroEvidencePack.model_validate(claimed["evidence_pack_json"])
        claimed_session = evidence_pack.session_date
        if evidence_pack.health.status is EvidencePackHealthStatus.BLOCKED:
            self._block_job(
                session_date=claimed_session,
                error="macro_evidence_pack_blocked:" + ",".join(evidence_pack.health.global_reasons),
                reviewer_disposition=None,
                now_ms=now,
            )
            return WorkerResult(
                processed=outcome_writes,
                failed=1,
                notes={
                    "session_date": claimed_session.isoformat(),
                    "publication": "blocked",
                    "model_calls": 0,
                    "publication_rows_written": 0,
                    "outcome_rows_written": outcome_writes,
                    "error": "macro_evidence_pack_blocked",
                },
            )
        try:
            analysis = asyncio.run(self._agent.analyze(evidence_pack))
            judgment = validate_daily_macro_judgment(
                analysis.judgment,
                evidence_pack=evidence_pack,
                reviewer=analysis.reviewer,
            )
            memo = render_daily_macro_judgment_zh(judgment)
            require_renderer_consistency(judgment, memo)
        except JudgmentGateError as exc:
            disposition = getattr(locals().get("analysis"), "reviewer", None)
            self._block_job(
                session_date=claimed_session,
                error=str(exc),
                reviewer_disposition=getattr(disposition, "disposition", None),
                now_ms=now,
            )
            return WorkerResult(
                processed=outcome_writes,
                failed=1,
                notes={
                    "session_date": claimed_session.isoformat(),
                    "publication": "blocked",
                    "model_calls": 1,
                    "publication_rows_written": 0,
                    "outcome_rows_written": outcome_writes,
                    "error": _safe_error(exc),
                },
            )
        except Exception as exc:
            status = self._retry_job(session_date=claimed_session, error=str(exc), now_ms=now)
            return WorkerResult(
                processed=outcome_writes,
                failed=1,
                notes={
                    "session_date": claimed_session.isoformat(),
                    "publication": status,
                    "model_calls": 1,
                    "publication_rows_written": 0,
                    "outcome_rows_written": outcome_writes,
                    "error": _safe_error(exc),
                },
            )
        with self._repository_session() as repos, repos.transaction():
            repos.require_transaction(operation="daily_macro_judgment_publish")
            published = repos.daily_macro_judgments.publish(
                session_date=claimed_session,
                lease_owner=self.name,
                judgment=judgment,
                memo_text=memo,
                evidence_pack_hash=evidence_pack.pack_hash,
                review=analysis.reviewer,
                agent_audit=analysis.audit,
                model_name=analysis.model_name,
                prompt_version=analysis.prompt_version,
                schema_version=DAILY_MACRO_JUDGMENT_SCHEMA_VERSION,
                workflow_version=analysis.workflow_version,
                renderer_version=DAILY_MACRO_JUDGMENT_RENDERER_VERSION,
                now_ms=now,
            )
            if not published:
                raise RuntimeError("daily_macro_judgment_publish_conflict")
        return WorkerResult(
            processed=1 + outcome_writes,
            notes={
                "session_date": claimed_session.isoformat(),
                "publication": "published",
                "model_calls": 1,
                "publication_rows_written": 1,
                "outcome_rows_written": outcome_writes,
                "evidence_pack_hash": evidence_pack.pack_hash,
                "reviewer_disposition": analysis.reviewer.disposition,
            },
        )

    def _freeze_job(self, *, session_date: date, now_ms: int) -> None:
        market_cutoff_ms = market_session_close_ms(session_date)
        with self._repository_session() as repos, repos.transaction():
            observations = repos.daily_macro_judgments.material_observations_for_evidence(
                session_date=session_date,
                lookback_days=self._lookback_days(),
                limit_per_series=self._limit_per_series(),
            )
            news = repos.daily_macro_judgments.eligible_news_text_rows(
                market_cutoff_ms=market_cutoff_ms,
                sealed_at_ms=now_ms,
                limit=self._news_limit(),
            )
        evidence_pack = compile_macro_evidence_pack(
            session_date=session_date,
            market_cutoff_ms=market_cutoff_ms,
            sealed_at_ms=now_ms,
            observation_rows=observations,
            news_rows=news,
        )
        with self._repository_session() as repos, repos.transaction():
            repos.require_transaction(operation="daily_macro_judgment_freeze")
            repos.daily_macro_judgments.insert_job(
                evidence_pack=evidence_pack,
                compiler_version=MACRO_EVIDENCE_COMPILER_VERSION,
                max_attempts=self._max_attempts(),
                due_at_ms=now_ms,
                now_ms=now_ms,
            )

    def _claim_job(self, *, now_ms: int) -> dict[str, Any] | None:
        with self._repository_session() as repos, repos.transaction():
            repos.require_transaction(operation="daily_macro_judgment_claim")
            claimed = repos.daily_macro_judgments.claim_due_job(
                lease_owner=self.name,
                lease_ms=self._lease_ms(),
                now_ms=now_ms,
            )
            return cast("dict[str, Any] | None", claimed)

    def _retry_job(self, *, session_date: date, error: str, now_ms: int) -> str:
        with self._repository_session() as repos, repos.transaction():
            repos.require_transaction(operation="daily_macro_judgment_retry")
            status = repos.daily_macro_judgments.mark_job_error(
                session_date=session_date,
                lease_owner=self.name,
                error=error,
                retry_ms=self._retry_ms(),
                now_ms=now_ms,
            )
            return str(status)

    def _block_job(
        self,
        *,
        session_date: date,
        error: str,
        reviewer_disposition: str | None,
        now_ms: int,
    ) -> None:
        with self._repository_session() as repos, repos.transaction():
            repos.require_transaction(operation="daily_macro_judgment_block")
            repos.daily_macro_judgments.mark_job_blocked(
                session_date=session_date,
                lease_owner=self.name,
                error=error,
                reviewer_disposition=reviewer_disposition,
                now_ms=now_ms,
            )

    def _mature_outcomes(self, *, now_ms: int) -> int:
        latest_session = resolve_market_cutoff(computed_at_ms=now_ms)
        writes = 0
        with self._repository_session() as repos, repos.transaction():
            publications = repos.daily_macro_judgments.publications_missing_outcomes(limit=self._outcome_batch_size())
        for publication in publications:
            session_date = publication["session_date"]
            for horizon in (5, 20):
                target_session = market_session_advance(session_date, sessions=horizon)
                if target_session > latest_session:
                    continue
                with self._repository_session() as repos, repos.transaction():
                    start = repos.daily_macro_judgments.spy_close(session_date)
                    target = repos.daily_macro_judgments.spy_close(target_session)
                if start is None or target is None:
                    continue
                start_close = float(start["value_numeric"])
                target_close = float(target["value_numeric"])
                outcome = DailyMacroOutcome(
                    session_date=session_date,
                    horizon_sessions=horizon,
                    target_session_date=target_session,
                    start_close=start_close,
                    target_close=target_close,
                    realized_return_pct=round((target_close / start_close - 1.0) * 100.0, 10),
                    source_evidence_refs=(
                        _close_ref(start),
                        _close_ref(target),
                    ),
                    computed_at_ms=now_ms,
                )
                with self._repository_session() as repos, repos.transaction():
                    repos.require_transaction(operation="daily_macro_judgment_outcome")
                    writes += int(repos.daily_macro_judgments.insert_outcome(outcome))
        return writes

    def _settle_delay_seconds(self) -> int:
        return int(self.settings.settle_delay_seconds)

    def _repository_session(self) -> Any:
        return cast(
            "Any",
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=self.settings.statement_timeout_seconds,
            ),
        )

    def _lookback_days(self) -> int:
        return int(self.settings.lookback_days)

    def _limit_per_series(self) -> int:
        return int(self.settings.limit_per_series)

    def _news_limit(self) -> int:
        return int(self.settings.news_limit)

    def _max_attempts(self) -> int:
        return int(self.settings.max_attempts)

    def _lease_ms(self) -> int:
        return int(self.settings.lease_ms)

    def _retry_ms(self) -> int:
        return int(self.settings.retry_ms)

    def _outcome_batch_size(self) -> int:
        return int(self.settings.outcome_batch_size)


def _eligible_session(*, now_ms: int, settle_delay_seconds: int) -> date:
    candidate = resolve_market_cutoff(computed_at_ms=now_ms)
    cutoff_ms = market_session_close_ms(candidate)
    if now_ms < cutoff_ms + int(settle_delay_seconds) * 1_000:
        return market_session_offset(candidate, sessions=1)
    return candidate


def _next_session_to_freeze(
    *,
    current_session: date,
    latest_job_session: date | None,
) -> date | None:
    if latest_job_session is None:
        return current_session
    next_session = market_session_advance(latest_job_session, sessions=1)
    if next_session <= current_session:
        return next_session
    return None


def _close_ref(row: dict[str, Any]) -> str:
    return (
        f"macro:asset:spy:{row['observed_at'].isoformat()}:"
        f"{row['source_name']}:{str(row.get('fact_payload_hash') or '')[:12]}"
    )


def _safe_error(value: object) -> str:
    return str(value or "daily_macro_judgment_unknown_error").replace("\n", " ")[:500]


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["DailyMacroJudgmentWorker"]
