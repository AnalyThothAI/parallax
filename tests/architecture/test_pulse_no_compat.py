from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.validators import _signal_pulse_window
from parallax.app.surfaces.cli.parser import build_parser
from parallax.platform.config.settings import (
    PULSE_CANDIDATE_STALE_JOB_TTL_SECONDS,
    PULSE_CANDIDATE_WINDOWS,
    PulseCandidateWorkerSettings,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
PULSE_PROMPTS = SRC / "domains" / "pulse_lab" / "prompts"
SETTINGS = SRC / "platform" / "config" / "settings.py"
REPOSITORY_SESSION = SRC / "app" / "runtime" / "repository_session.py"
DB_POOL_BUNDLE = SRC / "app" / "runtime" / "db_pool_bundle.py"
PULSE_CANDIDATES_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_candidates_repository.py"
PULSE_REPOSITORY_SHARED = SRC / "domains" / "pulse_lab" / "repositories" / "_pulse_repository_shared.py"
PULSE_ADMISSION_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_admission_repository.py"
PULSE_RUNS_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_runs_repository.py"
PULSE_AGENT_EVAL_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_agent_eval_repository.py"
PULSE_EVIDENCE_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_evidence_repository.py"
PULSE_PLAYBOOKS_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_playbooks_repository.py"
PULSE_JOBS_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_jobs_repository.py"
PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY = (
    SRC / "domains" / "pulse_lab" / "repositories" / "pulse_trigger_dirty_target_repository.py"
)
PULSE_READ_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_read_repository.py"
PULSE_CANDIDATE_WORKER = SRC / "domains" / "pulse_lab" / "runtime" / "pulse_candidate_worker.py"
PULSE_CANDIDATE_JOB_SERVICE = SRC / "domains" / "pulse_lab" / "services" / "pulse_candidate_job_service.py"
PULSE_EVIDENCE_PACKET_BUILDER = SRC / "domains" / "pulse_lab" / "services" / "evidence_packet_builder.py"
PULSE_EVIDENCE_COMPLETENESS_GATE = SRC / "domains" / "pulse_lab" / "services" / "evidence_completeness_gate.py"
PULSE_TIMELINE_CONTEXT = SRC / "domains" / "pulse_lab" / "services" / "pulse_timeline_context.py"
PULSE_CLAIM_EVIDENCE_VERIFIER = SRC / "domains" / "pulse_lab" / "services" / "claim_evidence_verifier.py"
PULSE_RECOMMENDATION_CLIPPER = SRC / "domains" / "pulse_lab" / "services" / "recommendation_clipper.py"
PULSE_WRITE_GATE = SRC / "domains" / "pulse_lab" / "services" / "write_gate.py"
PULSE_AGENT_COST_GUARD = SRC / "domains" / "pulse_lab" / "services" / "pulse_agent_cost_guard.py"
PULSE_AGENT_OUTPUT_NORMALIZATION = SRC / "domains" / "pulse_lab" / "services" / "agent_output_normalization.py"
PULSE_EVIDENCE_SOURCE_REPOSITORY = (
    SRC / "domains" / "pulse_lab" / "repositories" / "pulse_evidence_source_repository.py"
)
SIGNAL_PULSE_SERVICE = SRC / "domains" / "pulse_lab" / "read_models" / "signal_pulse_service.py"
API_SCHEMAS = SRC / "app" / "surfaces" / "api" / "schemas.py"
PULSE_CANDIDATE_AUDIT_IDENTITY_MIGRATION = (
    SRC
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260608_0155_pulse_candidate_serving_row_audit_identity_hard_cut.py"
)
PULSE_CANDIDATE_PRODUCT_IDENTITY_MIGRATION = (
    SRC / "platform" / "db" / "alembic" / "versions" / "20260608_0156_pulse_candidate_product_identity_hard_cut.py"
)
PULSE_DESK_DECISIONS = ROOT / "docs" / "generated" / "pulse-agent-desk-decisions.md"
PULSE_OPERATOR_DOCS = (
    PULSE_DESK_DECISIONS,
    ROOT / "docs" / "generated" / "signal-pulse-agent-cost-guard-2026-05-21.md",
    ROOT / "docs" / "generated" / "pulse-1h-4h-agent-runtime-evaluation-2026-05-20.md",
)

LEGACY_COMMITTEE_STAGE_NAMES = ("evidence_debate", "decision_maker")
REMOVED_PROMPT_FILES = ("evidence_debate.md", "decision_maker.md")
REMOVED_PROMPT_FILES += ("signal_analyst.md", "bear_case.md", "risk_portfolio_judge.md")
AGENT_STAGE_PROMPT_FILES = ("pulse_decision.md",)
RUNTIME_SOURCE_ROOTS = (
    SRC / "domains" / "pulse_lab",
    SRC / "integrations" / "model_execution",
    SRC / "app" / "runtime" / "provider_wiring",
)


def _runtime_sources() -> Iterator[Path]:
    for root in RUNTIME_SOURCE_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.suffix in {".py", ".md"} and "__pycache__" not in path.parts:
                yield path


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{path} has no function {function_name}")


def test_no_runtime_source_references_removed_committee_stage_names() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT).as_posix()
        offenders.extend(
            f"{relative_path} contains {legacy_stage}"
            for legacy_stage in LEGACY_COMMITTEE_STAGE_NAMES
            if legacy_stage in text
        )

    assert not offenders, "Removed Pulse committee stage names remain in runtime sources:\n" + "\n".join(offenders)


def test_pulse_runtime_text_does_not_use_committee_language() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT).as_posix()
        if "研究委员会" in text:
            offenders.append(f"{relative_path} contains 研究委员会")

    assert not offenders, "Pulse runtime still uses committee language:\n" + "\n".join(offenders)


def test_pulse_cost_guard_actions_are_distinct_from_decision_routes() -> None:
    text = (SRC / "domains/pulse_lab/services/pulse_agent_cost_guard.py").read_text(encoding="utf-8")
    action_literal_block = text.split("PulseCostGuardAction = Literal[", maxsplit=1)[1].split("]", maxsplit=1)[0]
    action_assignments = "\n".join(line.strip() for line in text.splitlines() if "action=" in line)

    forbidden_action_literals = (
        '"research_only"',
        '"research_with_public_judge"',
    )
    offenders = [
        literal
        for literal in forbidden_action_literals
        if literal in action_literal_block or literal in action_assignments
    ]
    if "research_allowed" in text:
        offenders.append("research_allowed")

    assert not offenders, "Pulse cost guard actions should not reuse route/research labels: " + ", ".join(offenders)


def test_pulse_candidate_serving_rows_do_not_store_agent_run_identity() -> None:
    repository_text = PULSE_CANDIDATES_REPOSITORY.read_text(encoding="utf-8")
    migration_text = PULSE_CANDIDATE_AUDIT_IDENTITY_MIGRATION.read_text(encoding="utf-8")

    assert "agent_run_id" not in repository_text
    assert "DROP COLUMN IF EXISTS agent_run_id" in migration_text


def test_pulse_candidate_serving_identity_excludes_pulse_version() -> None:
    worker_text = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")
    function_text = worker_text.split("def _asset_candidate_id", 1)[1].split("def _asset_trigger_signature", 1)[0]
    migration_text = PULSE_CANDIDATE_PRODUCT_IDENTITY_MIGRATION.read_text(encoding="utf-8")

    assert "PULSE_VERSION" not in function_text
    assert "ux_pulse_candidates_product_window_key" in migration_text
    assert "candidate_type || '|' || \"window\" || '|' || scope || '|' || target_type || '|' || target_id" in (
        migration_text
    )


def test_signal_pulse_public_mapper_does_not_expose_run_step_audit_fields() -> None:
    service_text = SIGNAL_PULSE_SERVICE.read_text(encoding="utf-8")
    item_mapper = service_text.split("def pulse_item_from_row", 1)[1].split("def _dict", 1)[0]
    decision_mapper = service_text.split("def _decision", 1)[1].split("def _bull_bear_view", 1)[0]
    schema_text = API_SCHEMAS.read_text(encoding="utf-8")
    item_schema = schema_text.split("class SignalPulseItem", 1)[1].split("class SignalPulseData", 1)[0]

    assert "claim_verification" not in item_mapper
    assert "evidence_gate" not in item_mapper
    assert "stage_count" not in decision_mapper
    assert "claim_verification" not in item_schema
    assert "evidence_gate" not in item_schema


def test_signal_pulse_public_mapper_requires_formal_candidate_json_fields_without_empty_defaults() -> None:
    service_text = SIGNAL_PULSE_SERVICE.read_text(encoding="utf-8")
    item_mapper = service_text.split("def pulse_item_from_row", 1)[1].split("def _dict", 1)[0]
    decision_mapper = service_text.split("def _decision", 1)[1].split("def _bull_bear_view", 1)[0]
    forbidden = (
        '_dict(row.get("decision_json"))',
        '_list(row.get("gate_reasons_json"))',
        '_list(row.get("risk_reasons_json"))',
        '_list(row.get("evidence_event_ids_json"))',
        '_list(row.get("source_event_ids_json"))',
    )

    assert "signal_pulse_public_candidate_required" in service_text
    assert "signal_pulse_public_candidate_invalid" in service_text
    assert [token for token in forbidden if token in item_mapper or token in decision_mapper] == []


def test_pulse_read_handle_filter_does_not_expand_event_id_jsonb() -> None:
    text = PULSE_READ_REPOSITORY.read_text(encoding="utf-8")
    handle_source = text.split("def _candidate_handle_filter_clause", maxsplit=1)[1]

    banned = (
        "jsonb_array_elements_text",
        "source_event_ids_json",
        "evidence_event_ids_json",
        "JOIN events",
        "event.author_handle",
    )

    assert [token for token in banned if token in text] == []
    assert "lower({candidate_alias}.subject_key) = %s" in handle_source


def test_signal_pulse_health_uses_formal_repository_contract_without_conn_probe() -> None:
    text = SIGNAL_PULSE_SERVICE.read_text(encoding="utf-8")
    freshness_source = _function_source(SIGNAL_PULSE_SERVICE, "_freshness_health")
    banned_in_function = ('getattr(repository, "conn", None)', "return {}")

    assert "repository.freshness_health" in freshness_source
    assert "PulseFreshnessHealthService" not in text
    assert [token for token in banned_in_function if token in freshness_source] == []


def test_pulse_low_information_hide_requires_repository_contract_without_optional_fallback() -> None:
    text = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")

    banned = (
        'getattr(repos.pulse_candidates, "hide_public_candidate_for_low_information", None)',
        "if hide_func is None:",
    )

    assert "repos.pulse_candidates.hide_public_candidate_for_low_information" in text
    assert [token for token in banned if token in text] == []


def test_pulse_dirty_trigger_state_contracts_are_not_optional_fallbacks() -> None:
    text = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")

    banned = (
        "_call_optional(",
        "def _call_optional",
        'getattr(repos.pulse_admission, "recent_target_failure_count", None)',
        'getattr(repos.pulse_jobs, "pending_agent_job_count", None)',
        'getattr(repos.pulse_jobs, "pending_agent_job_count_for_window_scope", None)',
        'getattr(repos.pulse_trigger_dirty_targets, "queue_depth", None)',
    )
    required = (
        "repos.pulse_jobs.job_for_candidate",
        "repos.pulse_admission.edge_state_by_candidate",
        "repos.pulse_admission.recent_target_failure_count",
        "repos.pulse_jobs.pending_agent_job_count()",
        "repos.pulse_jobs.pending_agent_job_count_for_window_scope",
        "repos.pulse_trigger_dirty_targets.queue_depth",
    )

    assert [token for token in banned if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_candidate_job_service_requires_session_transaction_without_nullcontext_fallback() -> None:
    text = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")

    banned = (
        "def _transaction(",
        "nullcontext",
        'hasattr(conn, "transaction")',
        "conn.transaction()",
        "_transaction(repos.conn)",
    )

    assert "repos.transaction()" in text
    assert [token for token in banned if token in text] == []


def test_pulse_candidate_job_service_requires_agent_run_audit_contract_without_defaults() -> None:
    text = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")
    forbidden = (
        'audit.get("backend") or BACKEND',
        'audit.get("workflow_name") or WORKFLOW_NAME',
        'audit.get("agent_name") or AGENT_NAME',
        'audit.get("artifact_version_hash") or _artifact_hash',
        'audit.get("prompt_version") or PULSE_DECISION_PROMPT_VERSION',
        'audit.get("schema_version") or PULSE_DECISION_SCHEMA_VERSION',
        'audit.get("input_hash") or _stable_hash',
        'audit.get("trace_metadata") or {}',
        'audit.get("usage") or {}',
        'result_audit.get("usage") or _aggregate_stage_usage',
        'result_audit.get("output_hash") or _stable_hash',
        'audit.get("prompt_version") if audit else PULSE_DECISION_PROMPT_VERSION',
        'audit.get("schema_version") if audit else PULSE_DECISION_SCHEMA_VERSION',
    )
    required = (
        "def _agent_run_request_audit(",
        "def _agent_run_result_output_hash(",
        "pulse_agent_run_audit_workflow_name_required",
        "pulse_agent_run_audit_output_hash_required",
        "run_usage_json = _aggregate_stage_usage(stage_audits)",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_candidate_job_service_backpressure_requires_formal_agent_execution_error() -> None:
    backpressure_source = _function_source(PULSE_CANDIDATE_JOB_SERVICE, "_agent_no_start_backpressure_reason")
    service_text = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")
    forbidden_reflection = (
        'getattr(exc, "agent_error_class"',
        'getattr(exc, "agent_execution_started"',
        'getattr(exc, "audit"',
        'getattr(exc, "agent_audit"',
        'audit.get("error_class")',
        'audit.get("execution_started")',
        'getattr(audit, "error_class"',
        'getattr(audit, "execution_started"',
    )
    required = (
        "isinstance(exc, AgentExecutionError)",
        "error_class = exc.error_class",
        "exc.execution_started is not False",
    )

    assert "def _agent_error_class" not in service_text
    assert [token for token in forbidden_reflection if token in backpressure_source] == []
    assert [token for token in required if token not in backpressure_source] == []


def test_pulse_candidate_worker_backpressure_requires_formal_reservation_without_reflection() -> None:
    backpressure_source = _function_source(PULSE_CANDIDATE_WORKER, "_record_agent_backpressure")
    forbidden_reflection = (
        'getattr(reservation, "reason"',
        'getattr(reason, "value"',
        "reservation: Any",
    )
    required = (
        "isinstance(reservation, AgentCapacityReservation)",
        "isinstance(reason, AgentExecutionErrorClass)",
        "reason.value",
    )

    assert [token for token in forbidden_reflection if token in backpressure_source] == []
    assert [token for token in required if token not in backpressure_source] == []


def test_pulse_candidate_job_service_timeout_cleanup_uses_formal_agent_cancellation_without_audit_reflection() -> None:
    source = _function_source(PULSE_CANDIDATE_JOB_SERVICE, "_cancelled_execution_started")
    forbidden = (
        'getattr(exc, "execution_started"',
        'getattr(exc, "audit"',
        'getattr(exc, "agent_audit"',
        'audit.get("execution_started")',
        'getattr(audit, "execution_started"',
    )
    required = (
        "isinstance(exc, AgentExecutionCancelled)",
        "return exc.execution_started",
        "return bool(run_started)",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_pulse_candidate_worker_requires_session_transaction_without_conn_fallback() -> None:
    text = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")

    banned = (
        "def _transaction(",
        'hasattr(conn, "transaction")',
        "conn.transaction()",
        "_transaction(repos.conn)",
    )

    assert "repos.transaction()" in text
    assert [token for token in banned if token in text] == []


def test_pulse_jobs_repository_terminal_paths_require_connection_transaction_without_nullcontext() -> None:
    text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    transaction_source = _function_source(PULSE_JOBS_REPOSITORY, "_transaction")
    terminal_sources = {
        name: _function_source(PULSE_JOBS_REPOSITORY, name)
        for name in (
            "terminalize_exhausted_stale_running_jobs",
            "mark_job_failed",
            "mark_job_cancelled_by_worker_timeout",
            "terminalize_stale_jobs_by_window",
        )
    }
    forbidden = (
        "nullcontext",
        "return nullcontext()",
        "if callable(transaction):",
    )

    assert "raise RuntimeError" in transaction_source
    assert "pulse_jobs_repository_transaction_required" in transaction_source
    assert [token for token in forbidden if token in text] == []
    assert all("with _transaction(self.conn):" in source for source in terminal_sources.values())
    assert all("self.conn.commit()" not in source for source in terminal_sources.values())
    assert "limit: int =" not in terminal_sources["terminalize_exhausted_stale_running_jobs"]


def test_pulse_stale_running_terminalization_batch_size_is_formal_worker_policy() -> None:
    worker_source = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")
    repository_source = _function_source(PULSE_JOBS_REPOSITORY, "terminalize_exhausted_stale_running_jobs")

    forbidden_worker_tokens = (
        "limit=100",
        "limit = 100",
        'getattr(settings, "stale_running_terminalization_batch_size"',
    )

    assert "_positive_worker_setting_int(" in worker_source
    assert '"stale_running_terminalization_batch_size"' in worker_source
    assert "limit=self.stale_running_terminalization_batch_size" in worker_source
    assert "pulse_candidate_stale_running_terminalization_limit_required" in worker_source
    assert "limit: int," in repository_source
    assert "limit: int =" not in repository_source
    assert "pulse_jobs_stale_after_ms_required" in repository_source
    assert "pulse_jobs_terminalize_limit_required" in repository_source
    assert "stale_before_ms = now - max(0, int(stale_after_ms))" not in repository_source
    assert "bounded_limit = max(1, min(500, int(limit)))" not in repository_source
    assert [token for token in forbidden_worker_tokens if token in worker_source] == []


def test_pulse_job_completion_paths_are_claim_scoped() -> None:
    repository_text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    claim_predicates = (
        "AND status = 'running'",
        "AND attempt_count = %s",
        "AND updated_at_ms = %s",
    )
    scoped_sources = {
        name: _function_source(PULSE_JOBS_REPOSITORY, name)
        for name in (
            "mark_job_succeeded",
            "mark_job_failed",
            "mark_job_cancelled_by_worker_timeout",
            "release_running_job_for_backpressure",
            "release_running_job_for_provider_cooldown",
        )
    }

    assert "_pulse_job_claim_identity(job)" in repository_text
    assert "_pulse_job_claim_updated_at_ms(job)" in repository_text
    for source in scoped_sources.values():
        for token in claim_predicates:
            assert token in source
    assert "job: dict[str, Any]" in scoped_sources["mark_job_succeeded"]
    assert "job_id: str" not in scoped_sources["mark_job_succeeded"]
    job_service_source = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")
    assert "mark_job_succeeded(job," in job_service_source
    assert "mark_job_succeeded(job_identity.job_id" not in job_service_source


def test_pulse_jobs_repository_mutations_use_connection_transaction_without_manual_commit_fallback() -> None:
    text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    mutation_sources = {
        name: _function_source(PULSE_JOBS_REPOSITORY, name)
        for name in (
            "enqueue_job",
            "mark_job_succeeded",
            "release_running_job_for_backpressure",
            "release_running_job_for_provider_cooldown",
            "mark_stale_agent_runs_failed",
        )
    }
    forbidden = (
        'getattr(self.conn, "transaction", None)',
        "self.conn.commit()",
    )

    assert [token for token in forbidden if token in text] == []
    assert "def _run_job_write" in text
    assert all("_run_job_write(self.conn, commit," in source for source in mutation_sources.values())


def test_pulse_jobs_repository_stale_agent_run_counts_require_real_cursor_rowcount() -> None:
    repository_text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    source = _function_source(PULSE_JOBS_REPOSITORY, "mark_stale_agent_runs_failed")
    forbidden = (
        "cursor.rowcount or 0",
        "int(cursor.rowcount or 0)",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "pulse_jobs_repository_rowcount_required",
        "pulse_jobs_repository_rowcount_invalid",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in required if token not in repository_text] == []
    assert "return _cursor_rowcount(cursor)" in source


def test_pulse_job_terminal_returning_counts_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    exhausted_source = _function_source(PULSE_JOBS_REPOSITORY, "terminalize_exhausted_stale_running_jobs")
    stale_window_source = _function_source(PULSE_JOBS_REPOSITORY, "terminalize_stale_jobs_by_window")
    terminal_sources = exhausted_source + stale_window_source
    forbidden = (
        "return len(rows)",
        "terminalized += len(rows)",
    )
    required = (
        "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:",
        "count = _cursor_rowcount(cursor)",
        "if count != len(rows):",
        "pulse_jobs_repository_rowcount_invalid",
        "terminalized = _returned_rowcount(cursor, rows)",
        "row_count = _returned_rowcount(cursor, rows)",
        "terminalized += row_count",
    )

    assert [token for token in forbidden if token in terminal_sources] == []
    assert [token for token in required if token not in repository_text] == []


def test_pulse_jobs_repository_single_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_JOBS_REPOSITORY.read_text(encoding="utf-8")
    required_source = _function_source(PULSE_JOBS_REPOSITORY, "enqueue_job")
    optional_sources = {
        name: _function_source(PULSE_JOBS_REPOSITORY, name)
        for name in (
            "claim_due_job",
            "mark_job_succeeded",
            "mark_job_failed",
            "retry_terminal_job_from_snapshot",
            "mark_job_cancelled_by_worker_timeout",
            "release_running_job_for_backpressure",
            "release_running_job_for_provider_cooldown",
        )
    }
    forbidden = (
        ").fetchone()",
        "return _row(row)",
        "return _optional_row(row)",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )
    required = (
        "def _single_returning_rowcount(cursor: Any, row: Any) -> int:",
        "def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:",
        "def _optional_returning_row(cursor: Any, row: Any) -> dict[str, Any] | None:",
        "pulse_jobs_repository_rowcount_required",
        "pulse_jobs_repository_rowcount_invalid",
        "if count not in (0, 1):",
    )

    assert [token for token in forbidden if token in required_source] == []
    assert "_required_returning_row(cursor, row)" in required_source
    for source in optional_sources.values():
        assert [token for token in forbidden if token in source] == []
        assert "_optional_returning_row(cursor, row)" in source
    assert [token for token in required if token not in repository_text] == []


def test_pulse_jobs_repository_enqueue_requires_explicit_max_attempts_without_default() -> None:
    source = _function_source(PULSE_JOBS_REPOSITORY, "enqueue_job")
    forbidden = (
        "max_attempts: int = 3",
        "max_attempts: int =",
        '"max_attempts", 3',
        "max_attempts=3",
    )

    assert [token for token in forbidden if token in source] == []
    assert "max_attempts: int," in source


def test_pulse_job_running_timeout_is_formal_setting_without_repository_defaults() -> None:
    settings_text = SETTINGS.read_text(encoding="utf-8")
    settings_class = settings_text.split("class PulseCandidateWorkerSettings", 1)[1].split(
        "\n\nclass NarrativeAdmissionWorkerSettings",
        1,
    )[0]
    repository_session_text = REPOSITORY_SESSION.read_text(encoding="utf-8")
    db_pool_bundle_text = DB_POOL_BUNDLE.read_text(encoding="utf-8")
    pulse_repository_texts = {
        path: path.read_text(encoding="utf-8")
        for path in (
            PULSE_JOBS_REPOSITORY,
            PULSE_ADMISSION_REPOSITORY,
            PULSE_CANDIDATES_REPOSITORY,
            PULSE_RUNS_REPOSITORY,
            PULSE_AGENT_EVAL_REPOSITORY,
            PULSE_READ_REPOSITORY,
            PULSE_PLAYBOOKS_REPOSITORY,
        )
    }

    assert "job_running_timeout_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "stale_running_terminalization_batch_size: int = Field(default=100, ge=1)" in settings_class
    assert "pulse_job_running_timeout_ms: int" in repository_session_text
    assert "PulseJobsRepository(conn, running_timeout_ms=pulse_job_running_timeout_ms)" in repository_session_text
    assert (
        "pulse_job_running_timeout_ms=int(settings.workers.pulse_candidate.job_running_timeout_ms)"
        in db_pool_bundle_text
    )
    assert "pulse_job_running_timeout_ms=self.pulse_job_running_timeout_ms" in db_pool_bundle_text

    forbidden_constructor_defaults = [
        f"{path.relative_to(ROOT)} keeps running_timeout_ms default"
        for path, text in pulse_repository_texts.items()
        if "running_timeout_ms: int =" in text
    ]
    forbidden_unused_timeout_state = [
        f"{path.relative_to(ROOT)} keeps unused running_timeout_ms state"
        for path, text in pulse_repository_texts.items()
        if path != PULSE_JOBS_REPOSITORY and "running_timeout_ms" in text
    ]
    assert forbidden_constructor_defaults == []
    assert forbidden_unused_timeout_state == []


def test_pulse_agent_write_repositories_use_shared_transaction_helper_without_manual_commit_fallback() -> None:
    repositories = {
        PULSE_RUNS_REPOSITORY: (
            "insert_agent_run",
            "finish_agent_run",
            "insert_agent_run_step",
        ),
        PULSE_AGENT_EVAL_REPOSITORY: (
            "upsert_agent_runtime_version",
            "insert_agent_eval_case",
            "upsert_agent_eval_result",
        ),
        PULSE_EVIDENCE_REPOSITORY: ("upsert_packet",),
        PULSE_CANDIDATES_REPOSITORY: (
            "upsert_candidate",
            "hide_public_candidate_for_low_information",
        ),
        PULSE_PLAYBOOKS_REPOSITORY: ("upsert_playbook_snapshot",),
        PULSE_ADMISSION_REPOSITORY: (
            "record_edge_observation",
            "claim_edge_budget",
            "mark_edge_job_enqueued",
            "mark_edge_budget_rejected",
            "mark_edge_run_finished",
        ),
    }
    forbidden = (
        'getattr(self.conn, "transaction", None)',
        "self.conn.commit()",
    )
    shared_text = PULSE_REPOSITORY_SHARED.read_text(encoding="utf-8")

    assert "def _run_repository_write" in shared_text
    for path, method_names in repositories.items():
        text = path.read_text(encoding="utf-8")
        assert [token for token in forbidden if token in text] == []
        for method_name in method_names:
            source = _function_source(path, method_name)
            assert "_run_repository_write(self.conn, commit," in source


def test_pulse_admission_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_ADMISSION_REPOSITORY.read_text(encoding="utf-8")
    claim_source = _function_source(PULSE_ADMISSION_REPOSITORY, "claim_edge_budget")
    required_returning_sources = (
        _function_source(PULSE_ADMISSION_REPOSITORY, "record_edge_observation"),
        _function_source(PULSE_ADMISSION_REPOSITORY, "mark_edge_job_enqueued"),
    )
    optional_returning_sources = (
        _function_source(PULSE_ADMISSION_REPOSITORY, "mark_edge_budget_rejected"),
        _function_source(PULSE_ADMISSION_REPOSITORY, "mark_edge_run_finished"),
    )
    private_returning_sources = (_function_source(PULSE_ADMISSION_REPOSITORY, "_mark_edge_suppressed"),)
    forbidden = (
        "return row is not None",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_admission_repository_rowcount_required" in repository_text
    assert "pulse_admission_repository_rowcount_invalid" in repository_text
    assert "def _single_returning_rowcount(" in repository_text
    assert [token for token in forbidden if token in claim_source] == []
    assert "pulse_edge_budget_max_enqueues_required" in claim_source
    assert "max(1, int(max_enqueues))" not in claim_source
    assert "_single_returning_rowcount(cursor, row) == 1" in claim_source
    for source in required_returning_sources:
        assert "_required_returning_row(cursor, row)" in source
    for source in (*optional_returning_sources, *private_returning_sources):
        assert "_optional_returning_row(cursor, row)" in source


def test_pulse_playbooks_repository_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_PLAYBOOKS_REPOSITORY.read_text(encoding="utf-8")
    snapshot_source = _function_source(PULSE_PLAYBOOKS_REPOSITORY, "upsert_playbook_snapshot")
    forbidden = (
        "return _row(row)",
        "row = self.conn.execute(",
        "SELECT *",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_playbooks_repository_rowcount_required" in repository_text
    assert "pulse_playbooks_repository_rowcount_invalid" in repository_text
    assert "def _optional_returning_row(" in repository_text
    assert [token for token in forbidden if token in snapshot_source] == []
    assert "_optional_returning_row(cursor, row)" in snapshot_source


def test_pulse_candidates_repository_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_CANDIDATES_REPOSITORY.read_text(encoding="utf-8")
    returning_sources = (
        _function_source(PULSE_CANDIDATES_REPOSITORY, "upsert_candidate"),
        _function_source(PULSE_CANDIDATES_REPOSITORY, "hide_public_candidate_for_low_information"),
    )
    forbidden = (
        "return _row(row)",
        "return _optional_row(row)",
        "row = self.conn.execute(",
        "SELECT *",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_candidates_repository_rowcount_required" in repository_text
    assert "pulse_candidates_repository_rowcount_invalid" in repository_text
    assert "pulse_candidate_decision_stage_count_required" in repository_text
    assert "max(0, int(decision_stage_count))" not in repository_text
    assert "def _optional_returning_row(" in repository_text
    for source in returning_sources:
        assert [token for token in forbidden if token in source] == []
        assert "_optional_returning_row(cursor, row)" in source


def test_pulse_runs_repository_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_RUNS_REPOSITORY.read_text(encoding="utf-8")
    required_sources = (
        _function_source(PULSE_RUNS_REPOSITORY, "insert_agent_run"),
        _function_source(PULSE_RUNS_REPOSITORY, "insert_agent_run_step"),
    )
    finish_source = _function_source(PULSE_RUNS_REPOSITORY, "finish_agent_run")
    forbidden = (
        "return _row(row)",
        "return _optional_row(row)",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
        "max(0, int(latency_ms))",
        "max(0, int(decision_stage_count))",
        "max(0, int(attempt_index))",
        "max(0, int(safety_net_retries))",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_runs_repository_rowcount_required" in repository_text
    assert "pulse_runs_repository_rowcount_invalid" in repository_text
    assert "pulse_run_latency_ms_required" in repository_text
    assert "pulse_run_decision_stage_count_required" in repository_text
    assert "pulse_run_step_attempt_index_required" in repository_text
    assert "pulse_run_step_latency_ms_required" in repository_text
    assert "pulse_run_step_safety_net_retries_required" in repository_text
    assert "def _required_returning_row(" in repository_text
    assert "def _optional_returning_row(" in repository_text
    for source in required_sources:
        assert [token for token in forbidden if token in source] == []
        assert "_required_returning_row(cursor, row)" in source
    assert [token for token in forbidden if token in finish_source] == []
    assert "_optional_returning_row(cursor, row)" in finish_source


def test_pulse_decision_mapping_rejects_malformed_stage_count_without_repair() -> None:
    source = (SRC / "domains/pulse_lab/services/decision_mapping.py").read_text(encoding="utf-8")

    assert "pulse_decision_stage_count_required" in source
    assert "max(0, int(stage_count))" not in source


def test_pulse_agent_eval_repository_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = PULSE_AGENT_EVAL_REPOSITORY.read_text(encoding="utf-8")
    returning_sources = (
        _function_source(PULSE_AGENT_EVAL_REPOSITORY, "upsert_agent_runtime_version"),
        _function_source(PULSE_AGENT_EVAL_REPOSITORY, "insert_agent_eval_case"),
        _function_source(PULSE_AGENT_EVAL_REPOSITORY, "upsert_agent_eval_result"),
    )
    forbidden = (
        "return _row(row)",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_agent_eval_repository_rowcount_required" in repository_text
    assert "pulse_agent_eval_repository_rowcount_invalid" in repository_text
    assert "def _required_returning_row(" in repository_text
    for source in returning_sources:
        assert [token for token in forbidden if token in source] == []
        assert "_required_returning_row(cursor, row)" in source


def test_pulse_evidence_repository_packet_returning_write_requires_cursor_rowcount_match() -> None:
    repository_text = PULSE_EVIDENCE_REPOSITORY.read_text(encoding="utf-8")
    source = _function_source(PULSE_EVIDENCE_REPOSITORY, "upsert_packet")
    forbidden = (
        "row = self.conn.execute(",
        "if row is None:",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "pulse_evidence_repository_rowcount_required" in repository_text
    assert "pulse_evidence_repository_rowcount_invalid" in repository_text
    assert "def _required_returning_row(" in repository_text
    assert "def _required_single_rowcount(" in repository_text
    assert [token for token in forbidden if token in source] == []
    assert "_required_returning_row(cursor, row)" in source
    assert "run_link_cursor = self.conn.execute" in source
    assert "_required_single_rowcount(run_link_cursor)" in source


def test_pulse_trigger_dirty_target_repository_uses_shared_transaction_helper_without_manual_commit_fallback() -> None:
    mutation_sources = {
        name: _function_source(PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY, name)
        for name in (
            "enqueue_targets",
            "claim_due",
            "mark_done",
            "mark_error",
            "reschedule",
        )
    }
    text = PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'getattr(self.conn, "transaction", None)',
        "self.conn.commit()",
    )

    assert [token for token in forbidden if token in text] == []
    for source in mutation_sources.values():
        assert "_run_repository_write(self.conn, commit," in source


def test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract() -> None:
    repository_text = PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
        'int(claim["attempt_count"])',
    )

    assert all(token not in repository_text for token in forbidden)
    assert 'claim["attempt_count"]' in repository_text


def test_pulse_trigger_dirty_claim_and_retry_contracts_reject_runtime_repairs() -> None:
    repository_text = PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY.read_text(encoding="utf-8")
    claim_source = _function_source(PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY, "claim_due")
    error_source = _function_source(PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY, "mark_error")
    forbidden = (
        "max(1, int(lease_ms))",
        "max(0, int(limit))",
        "max(1, int(retry_ms))",
        "int(value)",
    )
    required = (
        "_required_positive_int(\n            limit,",
        "_required_positive_int(\n            lease_ms,",
        "_required_positive_int(\n            retry_ms,",
        "_required_positive_int(\n        value,",
        "pulse_trigger_dirty_target_claim_limit_required",
        "pulse_trigger_dirty_target_claim_lease_ms_required",
        "pulse_trigger_dirty_target_retry_ms_required",
        "pulse_trigger_dirty_target_max_attempts_required",
        "isinstance(value, bool) or not isinstance(value, int)",
    )

    assert [token for token in forbidden if token in claim_source or token in error_source] == []
    assert [token for token in required if token not in repository_text] == []


def test_pulse_trigger_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "pulse_trigger_dirty_target_rowcount_required",
        "pulse_trigger_dirty_target_rowcount_invalid",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in required if token not in repository_text] == []


def test_pulse_trigger_dirty_error_completion_uses_formal_retry_budget_and_terminal_ledger() -> None:
    repository_source = _function_source(PULSE_TRIGGER_DIRTY_TARGET_REPOSITORY, "mark_error")
    worker_source = _function_source(PULSE_CANDIDATE_WORKER, "scan_triggers_once")
    forbidden = (
        "max_attempts: int =",
        "worker_name: str =",
        "\n".join(
            (
                "mark_error(",
                "                            [claim],",
                "                            error=str(exc),",
                "                            now_ms=resolved_now_ms,",
                "                            retry_ms=self.trigger_error_retry_ms,",
                "                            commit=False",
            )
        ),
    )

    assert "max_attempts: int," in repository_source
    assert "worker_name: str," in repository_source
    assert "terminalize_source_row(" in repository_source
    assert 'source_table="pulse_trigger_dirty_targets"' in repository_source
    assert "max_attempts=self.max_attempts" in worker_source
    assert "worker_name=self.name" in worker_source
    assert [token for token in forbidden if token in repository_source or token in worker_source] == []


def test_pulse_candidate_job_service_run_identity_requires_formal_claimed_job_fields_without_empty_segments() -> None:
    text = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")
    forbidden = (
        'str(job.get("job_id") or "")',
        'str(job.get("trigger_signature") or "")',
        'str(job.get("timeline_signature") or "")',
    )
    required = (
        "def _pulse_job_run_identity(",
        "pulse_agent_job_claim_job_id_required",
        "pulse_agent_job_claim_trigger_signature_required",
        "pulse_agent_job_claim_timeline_signature_required",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_timeline_context_requires_valid_window_and_scope_without_fallbacks() -> None:
    text = PULSE_TIMELINE_CONTEXT.read_text(encoding="utf-8")
    forbidden = (
        'window: str = "1h"',
        'scope: str = "all"',
        "WINDOW_MS.get(window",
        "windows.get(window",
    )
    required = (
        "class PulseTimelineContextWindowError",
        "class PulseTimelineContextScopeError",
        "def _window_ms(window: str) -> int:",
        "return WINDOW_MS[window]",
        "raise PulseTimelineContextWindowError(window)",
        "raise PulseTimelineContextScopeError(scope)",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_evidence_builder_requires_source_repository_contracts_without_optional_probes() -> None:
    text = PULSE_EVIDENCE_PACKET_BUILDER.read_text(encoding="utf-8")
    forbidden = (
        "def _list_repo(",
        'getattr(self._sources, "list_market_facts", None)',
        'getattr(self._sources, "get_current_discussion_digest", None)',
        "if method is None:",
        "return list(default)",
    )
    required = (
        "self._sources.list_source_events",
        "self._sources.list_enriched_events",
        "self._sources.list_market_facts",
        "self._sources.list_identity_facts",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_evidence_builder_requires_formal_candidate_context_without_shape_fallback() -> None:
    builder_text = PULSE_EVIDENCE_PACKET_BUILDER.read_text(encoding="utf-8")
    source_repository_text = PULSE_EVIDENCE_SOURCE_REPOSITORY.read_text(encoding="utf-8")
    forbidden_builder = (
        "getattr(context,",
        "context: Any",
        "PulseCandidateContext | Any",
    )
    forbidden_source_repository = (
        "context.get(",
        "getattr(context,",
        "def _context_value(",
        "def _context_raw(",
        "context: Any",
    )
    required_builder = (
        "context.factor_snapshot",
        "context.source_event_ids",
        "context.evidence_event_ids",
        "context.candidate_id",
        "context.target_type",
        "context.target_id",
        "context.window",
        "context.scope",
    )
    required_source_repository = (
        "context.target_type",
        "context.target_id",
        "context.factor_snapshot",
    )

    assert [token for token in forbidden_builder if token in builder_text] == []
    assert [token for token in forbidden_source_repository if token in source_repository_text] == []
    assert [token for token in required_builder if token not in builder_text] == []
    assert [token for token in required_source_repository if token not in source_repository_text] == []


def test_pulse_candidate_worker_job_context_lists_are_not_repaired_to_empty() -> None:
    text = PULSE_CANDIDATE_WORKER.read_text(encoding="utf-8")
    forbidden = (
        '_clean(context.get("candidate_id"))',
        '_clean(context.get("candidate_type"))',
        '_clean(context.get("subject_key"))',
        '_clean(context.get("target_type"))',
        '_clean(context.get("target_id"))',
        '_clean(context.get("window"))',
        '_clean(context.get("scope"))',
        '_clean(context.get("trigger_signature"))',
        '_clean(context.get("timeline_signature"))',
        '_mapping(context.get("gate_result")) or None',
        '_mapping(context.get("edge_state")) or None',
        "selected_posts = []",
        "post_clusters = []",
        '_stable_strings(context.get("edge_events"))',
        '_stable_strings(context.get("source_event_ids"))',
        '_stable_strings(context.get("evidence_event_ids"))',
    )
    required = (
        "pulse_candidate_context_candidate_id_required",
        "pulse_candidate_context_candidate_type_required",
        "pulse_candidate_context_subject_key_required",
        "pulse_candidate_context_target_type_required",
        "pulse_candidate_context_target_id_required",
        "pulse_candidate_context_window_required",
        "pulse_candidate_context_scope_required",
        "pulse_candidate_context_trigger_signature_required",
        "pulse_candidate_context_timeline_signature_required",
        "pulse_candidate_context_gate_result_required",
        "pulse_candidate_context_edge_state_required",
        "pulse_candidate_context_selected_posts_required",
        "pulse_candidate_context_post_clusters_required",
        "pulse_candidate_context_edge_events_required",
        "pulse_candidate_context_source_event_ids_required",
        "pulse_candidate_context_evidence_event_ids_required",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_evidence_completeness_gate_requires_formal_packet_without_reflection() -> None:
    text = PULSE_EVIDENCE_COMPLETENESS_GATE.read_text(encoding="utf-8")
    forbidden = (
        "PulseEvidencePacket | Any",
        "getattr(packet,",
        'getattr(value, "model_dump"',
        'hasattr(value, "__dict__")',
        "vars(value)",
        "def _model_items",
        "def _model_mapping",
    )

    assert "isinstance(packet, PulseEvidencePacket)" in text
    assert "pulse_evidence_packet_contract_required" in text
    assert [token for token in forbidden if token in text] == []


def test_pulse_claim_evidence_verifier_requires_formal_models_without_reflection() -> None:
    text = PULSE_CLAIM_EVIDENCE_VERIFIER.read_text(encoding="utf-8")
    forbidden = (
        "PulseEvidencePacket | Any",
        "FinalDecision | Any",
        "getattr(packet,",
        "getattr(final_decision,",
        'ref.get("ref_id") if isinstance(ref, dict)',
        "def _sequence",
    )

    assert "isinstance(packet, PulseEvidencePacket)" in text
    assert "isinstance(final_decision, FinalDecision)" in text
    assert "pulse_claim_verifier_packet_contract_required" in text
    assert "pulse_claim_verifier_final_decision_contract_required" in text
    assert [token for token in forbidden if token in text] == []


def test_pulse_write_and_clip_gates_require_formal_models_without_reflection() -> None:
    write_gate = PULSE_WRITE_GATE.read_text(encoding="utf-8")
    clipper = PULSE_RECOMMENDATION_CLIPPER.read_text(encoding="utf-8")
    cost_guard = PULSE_AGENT_COST_GUARD.read_text(encoding="utf-8")
    combined = "\n".join((write_gate, clipper, cost_guard))
    forbidden = (
        "gate: Any",
        "evidence_gate: Any",
        "evidence_gate: Any | None",
        "claim_verification: Any",
        "source_quality: Any",
        "getattr(evidence_gate,",
        "getattr(claim_verification,",
        "getattr(gate,",
    )

    required = (
        "isinstance(gate, PulseGateResult)",
        "isinstance(evidence_gate, EvidenceCompletenessGateResult)",
        "isinstance(claim_verification, ClaimEvidenceVerificationResult)",
        "isinstance(source_quality, PulseSourceQualityDecision)",
        "pulse_write_gate_gate_contract_required",
        "pulse_recommendation_clipper_gate_contract_required",
        "evidence_gate.hard_blocked",
    )

    assert [token for token in forbidden if token in combined] == []
    assert [token for token in required if token not in combined] == []


def test_pulse_run_outcome_requires_formal_claim_verification_without_reflection() -> None:
    service = PULSE_CANDIDATE_JOB_SERVICE.read_text(encoding="utf-8")
    run_outcome = _function_source(PULSE_CANDIDATE_JOB_SERVICE, "_run_outcome")
    forbidden = (
        "claim_verification_valid",
        "claim_verification: Any",
        "getattr(claim_verification,",
    )
    required = (
        "ClaimEvidenceVerificationResult",
        "isinstance(claim_verification, ClaimEvidenceVerificationResult)",
        "pulse_run_outcome_claim_verification_contract_required",
        "claim_verification.unknown_ref_ids",
    )

    assert [token for token in forbidden if token in run_outcome] == []
    assert [token for token in required if token not in service] == []


def test_pulse_stage_output_normalization_requires_formal_packet_without_reflection() -> None:
    text = PULSE_AGENT_OUTPUT_NORMALIZATION.read_text(encoding="utf-8")
    forbidden = (
        "evidence_packet: Any",
        "def _allowed_event_ids(evidence_packet: Any)",
        "def _allowed_refs(evidence_packet: Any)",
        "def _ref_value",
        'getattr(evidence_packet, "allowed_evidence_refs"',
        "ref.get(key) if isinstance(ref, dict)",
        'evidence_packet.get("allowed_evidence_refs")',
    )
    required = (
        "isinstance(evidence_packet, PulseEvidencePacket)",
        "pulse_stage_output_normalization_packet_contract_required",
        "evidence_packet.source_event_ids",
        "evidence_packet.allowed_evidence_refs",
        "ref.ref_id",
        "ref.source_id",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_pulse_admission_repository_requires_connection_transaction_without_nullcontext() -> None:
    shared_text = PULSE_REPOSITORY_SHARED.read_text(encoding="utf-8")
    transaction_source = _function_source(PULSE_REPOSITORY_SHARED, "_transaction")
    claim_source = _function_source(PULSE_ADMISSION_REPOSITORY, "claim_pulse_admission")
    forbidden = (
        "nullcontext",
        "return nullcontext()",
        'hasattr(conn, "transaction")',
        "conn.transaction()",
    )

    assert "raise RuntimeError" in transaction_source
    assert "pulse_repository_transaction_required" in transaction_source
    assert [token for token in forbidden if token in shared_text] == []
    assert "with _transaction(self.conn):" in claim_source


def test_removed_pulse_prompt_files_do_not_exist() -> None:
    for filename in REMOVED_PROMPT_FILES:
        assert not (PULSE_PROMPTS / filename).exists()
    for filename in AGENT_STAGE_PROMPT_FILES:
        assert (PULSE_PROMPTS / filename).is_file()


def test_pulse_candidate_default_windows_are_1h_4h_only() -> None:
    settings = PulseCandidateWorkerSettings()
    assert settings.windows == ("1h", "4h")
    assert PULSE_CANDIDATE_WINDOWS == ("1h", "4h")
    assert settings.stale_job_ttl_by_window_seconds == {"1h": 3600, "4h": 14400}
    assert PULSE_CANDIDATE_STALE_JOB_TTL_SECONDS == {"1h": 3600, "4h": 14400}

    settings_text = SETTINGS.read_text(encoding="utf-8")
    pulse_candidate_template = settings_text.split("\npulse_candidate:\n", maxsplit=1)[1].split(
        "\nenrichment:\n", maxsplit=1
    )[0]
    assert 'windows: ["1h", "4h"]' in pulse_candidate_template
    assert "5m" not in pulse_candidate_template
    assert "24h" not in pulse_candidate_template


def test_signal_pulse_api_validator_rejects_removed_5m_window() -> None:
    with pytest.raises(ApiBadRequest) as exc_info:
        _signal_pulse_window("5m")

    assert exc_info.value.error == "invalid_window"
    assert exc_info.value.field == "window"


def test_pulse_cli_rejects_removed_windows() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["pulse", "health", "--window", "5m"])
    with pytest.raises(SystemExit):
        parser.parse_args(["pulse", "replay-eval", "--window", "24h"])

    assert parser.parse_args(["pulse", "health", "--window", "1h"]).window == "1h"
    assert parser.parse_args(["pulse", "replay-eval", "--window", "4h"]).window == "4h"


def test_generated_pulse_operator_docs_do_not_advertise_removed_agent_flow() -> None:
    forbidden = (
        "evidence_debate",
        "decision_maker",
        "DecisionMaker",
        "Investigator",
        "investigator",
        "fallback tool",
    )
    offenders: list[str] = []
    for path in PULSE_OPERATOR_DOCS:
        text = path.read_text(encoding="utf-8")
        offenders.extend(f"{path.relative_to(ROOT)} contains {pattern}" for pattern in forbidden if pattern in text)
    assert not offenders


def test_pulse_freshness_health_requires_explicit_since_hours_without_defaults() -> None:
    service_source = (SRC / "domains/pulse_lab/services/pulse_freshness_health.py").read_text(encoding="utf-8")
    repository_source = PULSE_READ_REPOSITORY.read_text(encoding="utf-8")
    signal_service_source = SIGNAL_PULSE_SERVICE.read_text(encoding="utf-8")
    cli_source = (SRC / "app/surfaces/cli/commands/pulse_replay.py").read_text(encoding="utf-8")

    for source in (service_source, repository_source):
        assert "since_hours: int =" not in source
        assert "since_hours: int" in source
        assert '"since_hours": max(1, int(since_hours))' not in source

    types_source = (SRC / "domains/pulse_lab/types/pulse_freshness_health.py").read_text(encoding="utf-8")
    assert "pulse_freshness_since_hours" in service_source
    assert "pulse_freshness_since_hours" in repository_source
    assert "pulse_freshness_since_hours_required" in types_source
    assert "max(1, int(since_hours))" not in types_source
    assert "since_hours=4" in signal_service_source
    assert "since_hours=int(args.since_hours)" in cli_source


def test_pulse_operator_lookback_queries_reject_instead_of_repairing() -> None:
    cost_report_source = (SRC / "domains/pulse_lab/queries/pulse_agent_cost_report.py").read_text(encoding="utf-8")
    policy_evaluator_source = (SRC / "domains/pulse_lab/queries/pulse_policy_evaluator.py").read_text(encoding="utf-8")

    assert "pulse_agent_cost_report_lookback_hours_required" in cost_report_source
    assert "pulse_policy_lookback_hours_required" in policy_evaluator_source
    assert "max(1, int(lookback_hours))" not in cost_report_source
    assert "max(1, int(lookback_hours))" not in policy_evaluator_source


def test_pulse_public_list_candidates_requires_explicit_limit_without_repository_default() -> None:
    repository_source = _function_source(PULSE_READ_REPOSITORY, "list_candidates")
    signal_service_source = _function_source(SIGNAL_PULSE_SERVICE, "pulse")

    assert "limit: int =" not in repository_source
    assert "limit: int" in repository_source
    assert "limit=limit" in signal_service_source


def test_pulse_recommendation_clipper_requires_existing_playbook_horizon_without_1h_fallback() -> None:
    source = PULSE_RECOMMENDATION_CLIPPER.read_text(encoding="utf-8")

    assert 'or "1h"' not in source
    assert "def _playbook_monitoring_horizon(" in source
    assert "pulse_recommendation_clipper_playbook_horizon_required" in source
