from __future__ import annotations

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
PULSE_CANDIDATES_REPOSITORY = SRC / "domains" / "pulse_lab" / "repositories" / "pulse_candidates_repository.py"
PULSE_CANDIDATE_WORKER = SRC / "domains" / "pulse_lab" / "runtime" / "pulse_candidate_worker.py"
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
    SRC
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260608_0156_pulse_candidate_product_identity_hard_cut.py"
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
