from __future__ import annotations

import asyncio
from datetime import date

from parallax.domains.macro_intel.runtime.macro_research_worker import (
    MacroResearchWorker,
)
from parallax.domains.macro_intel.services.completed_session_macro import (
    MacroSessionView,
)
from parallax.platform.config.settings import MacroResearchWorkerSettings


def test_worker_calls_completed_session_module_without_session_arguments() -> None:
    runtime = _FakeCompletedSessionMacro(_view(publication_rows_written=1))
    worker = MacroResearchWorker(
        settings=MacroResearchWorkerSettings(enabled=True),
        db=object(),
        telemetry=None,
        completed_session_macro=runtime,  # type: ignore[arg-type]
    )

    result = asyncio.run(worker.run_once())

    assert runtime.calls == [()]
    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["publication"] == "published"


def test_worker_reports_published_replay_as_skipped() -> None:
    runtime = _FakeCompletedSessionMacro(_view(publication_rows_written=0))
    worker = MacroResearchWorker(
        settings=MacroResearchWorkerSettings(enabled=True),
        db=object(),
        telemetry=None,
        completed_session_macro=runtime,  # type: ignore[arg-type]
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["model_calls"] == 0
    assert result.notes["publication_rows_written"] == 0


class _FakeCompletedSessionMacro:
    def __init__(self, view: MacroSessionView) -> None:
        self._view = view
        self.calls: list[tuple[object, ...]] = []

    async def run(self, *args: object) -> MacroSessionView:
        self.calls.append(args)
        return self._view


def _view(*, publication_rows_written: int) -> MacroSessionView:
    return MacroSessionView(
        session_date=date(2026, 7, 23),
        status="published",
        market_cutoff_ms=100,
        sealed_at_ms=110,
        attempt_count=1,
        max_attempts=3,
        due_at_ms=110,
        artifact={"title": "宏观研究"},
        report_markdown="# 宏观研究",
        audit={"model_calls": 3},
        artifact_hash="sha256:artifact",
        published_at_ms=120,
        model_calls=3 if publication_rows_written else 0,
        run_rows_written=3 if publication_rows_written else 0,
        publication_rows_written=publication_rows_written,
    )
