from __future__ import annotations

import io
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from parallax.app.surfaces.cli.parser import build_parser
from parallax.cli import main
from parallax.domains.macro_intel.repositories.macro_research_repository import (
    MacroResearchRepository,
)

SESSION_DATE = date(2026, 7, 23)
NOW_MS = 1_784_847_600_000


def test_retry_failed_run_is_one_atomic_conditional_update() -> None:
    row = {
        "applied": True,
        "reason": "retry_granted",
        "session_date": SESSION_DATE,
        "previous_status": "failed",
        "status": "retryable",
        "attempt_count": 3,
        "previous_max_attempts": 3,
        "max_attempts": 4,
        "due_at_ms": NOW_MS,
        "leased_until_ms": None,
        "lease_owner": None,
        "last_error_code": None,
        "last_error_message": None,
    }
    conn = _FakeConnection(row)

    result = MacroResearchRepository(conn).retry_failed_run(
        session_date=SESSION_DATE,
        now_ms=NOW_MS,
    )

    assert result == row
    assert len(conn.calls) == 1
    sql = " ".join(conn.calls[0]["sql"].split())
    assert "WITH target AS MATERIALIZED" in sql
    assert "FOR UPDATE" in sql
    assert "target.status = 'failed'" in sql
    assert "NOT target.publication_exists" in sql
    assert "GREATEST(runs.max_attempts, runs.attempt_count + 1)" in sql
    assert "leased_until_ms = NULL" in sql
    assert "last_error_code = NULL" in sql
    assert conn.calls[0]["params"] == (SESSION_DATE, NOW_MS, NOW_MS)


def test_retry_failed_run_missing_session_is_an_auditable_noop() -> None:
    result = MacroResearchRepository(_FakeConnection(None)).retry_failed_run(
        session_date=SESSION_DATE,
        now_ms=NOW_MS,
    )

    assert result == {
        "applied": False,
        "reason": "run_not_found",
        "session_date": SESSION_DATE,
        "previous_status": None,
        "status": None,
        "attempt_count": None,
        "previous_max_attempts": None,
        "max_attempts": None,
        "due_at_ms": None,
        "leased_until_ms": None,
        "lease_owner": None,
        "last_error_code": None,
        "last_error_message": None,
    }


def test_retry_failed_macro_research_owns_transaction(monkeypatch) -> None:
    from parallax.app.operations import macro as operation

    events: list[str] = []
    repository = SimpleNamespace(
        retry_failed_run=lambda **_kwargs: {
            "applied": True,
            "reason": "retry_granted",
            "session_date": SESSION_DATE,
        }
    )

    @contextmanager
    def transaction():
        events.append("transaction_enter")
        yield
        events.append("transaction_exit")

    @contextmanager
    def fake_repositories(_settings):
        yield SimpleNamespace(macro_research=repository, transaction=transaction)

    monkeypatch.setattr(operation, "repositories", fake_repositories)

    result = operation.retry_failed_macro_research(
        SimpleNamespace(),
        session_date=SESSION_DATE,
        now_ms=NOW_MS,
    )

    assert events == ["transaction_enter", "transaction_exit"]
    assert result == {
        "action": "retry_research",
        "requested_at_ms": NOW_MS,
        "outcome": "applied",
        "applied": True,
        "reason": "retry_granted",
        "session_date": SESSION_DATE,
    }


def test_macro_retry_research_cli_returns_auditable_json(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as command

    monkeypatch.setattr(command, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(command, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(
        command,
        "retry_failed_macro_research",
        lambda _settings, *, session_date, now_ms: {
            "action": "retry_research",
            "requested_at_ms": now_ms,
            "outcome": "applied",
            "applied": True,
            "reason": "retry_granted",
            "session_date": session_date,
            "previous_status": "failed",
            "status": "retryable",
            "attempt_count": 3,
            "previous_max_attempts": 3,
            "max_attempts": 4,
            "due_at_ms": now_ms,
            "leased_until_ms": None,
            "lease_owner": None,
            "last_error_code": None,
            "last_error_message": None,
        },
    )
    stdout = io.StringIO()

    code = main(
        ["macro", "retry-research", "--session-date", "2026-07-23"],
        stdout=stdout,
    )

    assert code == 0
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {
            "action": "retry_research",
            "requested_at_ms": NOW_MS,
            "outcome": "applied",
            "applied": True,
            "reason": "retry_granted",
            "session_date": "2026-07-23",
            "previous_status": "failed",
            "status": "retryable",
            "attempt_count": 3,
            "previous_max_attempts": 3,
            "max_attempts": 4,
            "due_at_ms": NOW_MS,
            "leased_until_ms": None,
            "lease_owner": None,
            "last_error_code": None,
            "last_error_message": None,
        },
    }


def test_macro_retry_research_parser_and_invalid_date() -> None:
    args = build_parser().parse_args(["macro", "retry-research", "--session-date", "2026-07-23"])
    assert args.macro_command == "retry-research"
    assert args.session_date == "2026-07-23"

    stdout = io.StringIO()
    code = main(
        ["macro", "retry-research", "--session-date", "not-a-date"],
        stdout=stdout,
    )
    assert code == 2
    assert json.loads(stdout.getvalue()) == {
        "ok": False,
        "error": "macro_retry_research_invalid_date",
        "field": "session_date",
    }


def test_0195_lifecycle_only_allows_the_exact_operator_retry_shape() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "src/parallax/platform/db/alembic/versions"
        / "20260724_0195_macro_research_failed_retry.py"
    ).read_text(encoding="utf-8")

    assert "OLD.status = 'failed' AND NEW.status = 'retryable'" in migration
    assert "GREATEST(OLD.max_attempts, OLD.attempt_count + 1)" in migration
    assert "NEW.due_at_ms <> NEW.updated_at_ms" in migration
    assert "macro_research_run_operator_retry_shape_invalid" in migration
    assert "OLD.status IN ('failed', 'published')" in migration
    assert "forward-only Macro research recovery contract" in migration


class _FakeConnection:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.calls: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        self.calls.append({"sql": sql, "params": params})
        return _FakeCursor(self.row)


class _FakeCursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row
