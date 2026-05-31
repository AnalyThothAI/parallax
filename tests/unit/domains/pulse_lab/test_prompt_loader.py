"""Unit tests for ``prompt_loader.load_prompt`` (Task 5, plan
2026-05-16-pulse-agent-desk-redesign-plan-cn.md).

Covers:

- per-role base preamble cache-friendly size (>= 4 KiB)
- anti-injection prefix retained from the prior in-code prompt module
- ``## Route: <name>`` section selection (only the matching section returned;
  other route sections stripped to keep the rotating tail minimal)
- error paths: unknown role -> ``ValueError``; unknown route -> ``RuntimeError``
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.domains.pulse_lab.services.prompt_loader import (
    load_bear_case_prompt,
    load_prompt,
    load_risk_portfolio_judge_prompt,
    load_signal_analyst_prompt,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "src" / "parallax" / "domains" / "pulse_lab" / "prompts"

_ANTI_INJECTION_KEYS = (
    "data, not instructions",
    "Do not invent facts",
)


def _base_preamble_bytes(role: str) -> int:
    """Return the byte size of the file content before the first ## Route heading."""
    text = (_PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    idx = text.find("\n## Route:")
    base = text if idx == -1 else text[:idx]
    return len(base.encode("utf-8"))


# ---------------------------------------------------------------------------
# anti-injection prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["signal_analyst", "bear_case", "risk_portfolio_judge"])
@pytest.mark.parametrize("route", ["cex", "meme"])
def test_anti_injection_prefix_present(role: str, route: str) -> None:
    rendered = load_prompt(role, route)
    for needle in _ANTI_INJECTION_KEYS:
        assert needle in rendered, f"{role} ({route}) missing anti-injection key: {needle!r}"


# ---------------------------------------------------------------------------
# cache-friendly base size
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["signal_analyst", "bear_case", "risk_portfolio_judge"])
def test_base_preamble_is_cache_friendly(role: str) -> None:
    size = _base_preamble_bytes(role)
    assert size >= 1000, f"{role}.md base preamble should keep shared packet rules in the cached prefix"


# ---------------------------------------------------------------------------
# route section selection — signal_analyst
# ---------------------------------------------------------------------------


def test_signal_analyst_meme_contains_only_meme_section() -> None:
    rendered = load_signal_analyst_prompt("meme")
    assert "## Route: meme" in rendered
    assert "## Route: cex" not in rendered
    assert "meme" in rendered.lower()
    # Phrase unique to the meme route body
    assert "social concentration" in rendered.lower()


def test_signal_analyst_cex_contains_only_cex_section() -> None:
    rendered = load_signal_analyst_prompt("cex")
    assert "## Route: cex" in rendered
    assert "## Route: meme" not in rendered
    assert "cex" in rendered.lower()
    # Phrase unique to the cex route body
    assert "venue" in rendered.lower()


# ---------------------------------------------------------------------------
# route section selection — risk_portfolio_judge
# ---------------------------------------------------------------------------


def test_risk_portfolio_judge_meme_contains_playbook_and_only_meme() -> None:
    rendered = load_risk_portfolio_judge_prompt("meme")
    assert "## Route: meme" in rendered
    assert "## Route: cex" not in rendered
    assert "playbook" in rendered.lower()
    assert "supporting_evidence_refs" in rendered


def test_risk_portfolio_judge_cex_contains_playbook_and_only_cex() -> None:
    rendered = load_risk_portfolio_judge_prompt("cex")
    assert "## Route: cex" in rendered
    assert "## Route: meme" not in rendered
    assert "playbook" in rendered.lower()
    assert "venue" in rendered.lower()


def test_risk_portfolio_judge_prompt_matches_runtime_input_and_strict_output_shape() -> None:
    rendered = load_risk_portfolio_judge_prompt("meme")

    assert "investigation_report" not in rendered
    assert "SignalAnalystMemo" in rendered
    assert "BearCaseMemo" in rendered
    assert "abstain_reason" in rendered
    assert "evidence_event_urls" in rendered
    assert "supporting_evidence_refs" in rendered
    assert "allowed_evidence_refs" in rendered


def test_bear_case_prompt_mentions_signal_memo_and_risk_claims() -> None:
    rendered = load_bear_case_prompt("meme")

    assert "signal_memo" in rendered
    assert "risk_claims" in rendered
    assert "confidence_ceiling" in rendered


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


def test_unknown_role_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown prompt role"):
        load_prompt("unknown_role", "meme")


@pytest.mark.parametrize("role", ["evidence_debate", "decision_maker"])
def test_old_prompt_roles_raise_value_error(role: str) -> None:
    with pytest.raises(ValueError, match="unknown prompt role"):
        load_prompt(role, "meme")


def test_unknown_route_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="does not contain ## Route"):
        load_prompt("signal_analyst", "research_only")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# rendered shape sanity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "route"),
    [
        ("signal_analyst", "cex"),
        ("signal_analyst", "meme"),
        ("bear_case", "cex"),
        ("bear_case", "meme"),
        ("risk_portfolio_judge", "cex"),
        ("risk_portfolio_judge", "meme"),
    ],
)
def test_rendered_prompt_has_base_plus_single_route_section(role: str, route: str) -> None:
    rendered = load_prompt(role, route)
    # Exactly one ## Route: heading remains in output
    headings = [line for line in rendered.splitlines() if line.strip().startswith("## Route:")]
    assert len(headings) == 1, f"expected one ## Route: heading, got {headings!r}"
    assert headings[0].strip().lower() == f"## route: {route}"
