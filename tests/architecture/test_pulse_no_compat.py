from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.validators import _signal_pulse_window
from gmgn_twitter_intel.platform.config.settings import (
    PULSE_CANDIDATE_STALE_JOB_TTL_SECONDS,
    PULSE_CANDIDATE_WINDOWS,
    PulseCandidateWorkerSettings,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
PULSE_PROMPTS = SRC / "domains" / "pulse_lab" / "prompts"
SETTINGS = SRC / "platform" / "config" / "settings.py"
PULSE_DESK_DECISIONS = ROOT / "docs" / "generated" / "pulse-agent-desk-decisions.md"

LEGACY_COMMITTEE_STAGE_NAMES = ("evidence_debate", "decision_maker")
REMOVED_PROMPT_FILES = ("evidence_debate.md", "decision_maker.md")
RESEARCH_COMMITTEE_PROMPT_FILES = ("signal_analyst.md", "bear_case.md", "risk_portfolio_judge.md")
RUNTIME_SOURCE_ROOTS = (
    SRC / "domains" / "pulse_lab",
    SRC / "integrations" / "openai_agents",
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


def test_removed_pulse_prompt_files_do_not_exist() -> None:
    for filename in REMOVED_PROMPT_FILES:
        assert not (PULSE_PROMPTS / filename).exists()
    for filename in RESEARCH_COMMITTEE_PROMPT_FILES:
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


def test_generated_pulse_operator_docs_do_not_advertise_removed_agent_flow() -> None:
    text = PULSE_DESK_DECISIONS.read_text(encoding="utf-8")
    forbidden = (
        "evidence_debate",
        "decision_maker",
        "DecisionMaker",
        "Investigator",
        "investigator",
        "fallback tool",
    )
    offenders = [pattern for pattern in forbidden if pattern in text]
    assert not offenders
