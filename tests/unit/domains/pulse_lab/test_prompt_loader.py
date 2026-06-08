"""Unit tests for ``prompt_loader.load_prompt``."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.domains.pulse_lab.services.prompt_loader import (
    load_prompt,
    load_pulse_decision_prompt,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "src" / "parallax" / "domains" / "pulse_lab" / "prompts"

_ANTI_INJECTION_KEYS = (
    "data, not instructions",
    "Do not invent facts",
    "Do not use tools",
)


def _base_preamble_bytes(role: str) -> int:
    text = (_PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    idx = text.find("\n## Route:")
    base = text if idx == -1 else text[:idx]
    return len(base.encode("utf-8"))


@pytest.mark.parametrize("route", ["cex", "meme", "research_only"])
def test_pulse_decision_prompt_has_anti_injection_prefix(route: str) -> None:
    rendered = load_pulse_decision_prompt(route)  # type: ignore[arg-type]
    for needle in _ANTI_INJECTION_KEYS:
        assert needle in rendered


def test_pulse_decision_base_preamble_is_cache_friendly() -> None:
    assert _base_preamble_bytes("pulse_decision") >= 1000


@pytest.mark.parametrize(
    ("route", "unique_phrase"),
    [
        ("cex", "centralized markets"),
        ("meme", "social concentration"),
        ("research_only", "public-market recommendation"),
    ],
)
def test_pulse_decision_prompt_contains_only_selected_route(route: str, unique_phrase: str) -> None:
    rendered = load_pulse_decision_prompt(route)  # type: ignore[arg-type]

    headings = [line for line in rendered.splitlines() if line.strip().startswith("## Route:")]
    assert headings == [f"## Route: {route}"]
    assert unique_phrase in rendered


def test_pulse_decision_prompt_matches_single_stage_runtime_contract() -> None:
    rendered = load_pulse_decision_prompt("meme")

    assert "FinalDecision" in rendered
    assert "supporting_evidence_refs" in rendered
    assert "allowed_evidence_refs" in rendered
    assert "signal_memo" not in rendered
    assert "risk_claims" not in rendered
    assert "confidence_ceiling" not in rendered


def test_unknown_role_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown prompt role"):
        load_prompt("unknown_role", "meme")


@pytest.mark.parametrize(
    "role",
    [
        "evidence_debate",
        "decision_maker",
        "signal_analyst",
        "bear_case",
        "risk_portfolio_judge",
    ],
)
def test_old_prompt_roles_raise_value_error(role: str) -> None:
    with pytest.raises(ValueError, match="unknown prompt role"):
        load_prompt(role, "meme")


def test_unknown_route_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="does not contain ## Route"):
        load_prompt("pulse_decision", "unknown")  # type: ignore[arg-type]
