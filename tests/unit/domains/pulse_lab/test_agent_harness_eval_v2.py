"""Unit tests for the Pulse Agent Desk v2 deterministic grader
(plan 2026-05-16 Task 10).

Covers each of the 5 rules (R1..R5) with a happy + fail variant, the
legacy_skipped defensive dispatch (reviewer G.1), and a complete v2
PulseDecisionPayload that passes every rule.

These tests intentionally build the case dict by hand (rather than going
through ``build_pulse_deterministic_eval_case``) so individual rules can
be exercised in isolation without dragging in Pydantic validators that
would short-circuit several violations at the type layer.
"""

from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness_eval import (
    grade_pulse_deterministic_eval_case,
)

# ---------------------------------------------------------------------------
# fixtures (builders return plain dicts so tests can mutate freely)
# ---------------------------------------------------------------------------


def _v2_bull_view(strength: str = "moderate") -> dict[str, Any]:
    if strength == "absent":
        return {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []}
    return {
        "strength": strength,
        "thesis_zh": "Independent author breadth keeps expanding.",
        "supporting_event_ids": ["event-1", "event-2"],
    }


def _v2_bear_view(strength: str = "moderate") -> dict[str, Any]:
    if strength == "absent":
        return {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []}
    return {
        "strength": strength,
        "thesis_zh": "DEX floor liquidity is still thin.",
        "supporting_event_ids": ["event-3"],
    }


def _v2_playbook(*, has_playbook: bool = True) -> dict[str, Any]:
    if not has_playbook:
        return {
            "has_playbook": False,
            "watch_signals": [],
            "exit_triggers": [],
            "monitoring_horizon": "4h",
        }
    return {
        "has_playbook": True,
        "watch_signals": ["Independent author count keeps rising"],
        "exit_triggers": ["DEX liquidity drops below entry level"],
        "monitoring_horizon": "4h",
    }


def _v2_final(
    *,
    recommendation: str = "trade_candidate",
    evidence_event_ids: list[str] | None = None,
    bull_strength: str = "moderate",
    bear_strength: str = "moderate",
    playbook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "route": "meme",
        "recommendation": recommendation,
        "confidence": 0.62,
        "abstain_reason": None,
        "summary_zh": "Healthy social ignition with monitoring guardrails.",
        "narrative_archetype": "kol-ignition",
        "narrative_thesis_zh": (
            "Watched and independent author breadth keeps growing on a meme "
            "asset that still needs DEX liquidity confirmation."
        ),
        "bull_view": _v2_bull_view(bull_strength),
        "bear_view": _v2_bear_view(bear_strength),
        "playbook": playbook if playbook is not None else _v2_playbook(),
        "evidence_event_urls": {"event-1": "https://x.com/foo/status/1"},
        "invalidation_conditions": ["Independent author count rolls over"],
        "residual_risks": ["Single-KOL driven"],
        "evidence_event_ids": evidence_event_ids
        if evidence_event_ids is not None
        else ["event-1", "event-2"],
    }


def _v2_stage_audits(
    *,
    investigator_status: str = "ok",
    decision_maker_status: str = "ok",
    investigator_tool_calls: list[dict[str, Any]] | None = None,
    investigator_response: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    tool_calls = (
        investigator_tool_calls
        if investigator_tool_calls is not None
        else [{"name": "lookup_recent_mentions", "args": {}}]
    )
    response = investigator_response if investigator_response is not None else {
        "narrative_archetype_candidate": "kol-ignition",
        "narrative_observation_zh": "Stub investigator observation for tests.",
        "bull_observation": {
            "strength": "moderate",
            "thesis_zh": "Stub bull thesis",
            "supporting_event_ids": ["event-1", "event-2"],
        },
        "bear_observation": {
            "strength": "weak",
            "thesis_zh": "Stub bear thesis",
            "supporting_event_ids": ["event-3"],
        },
        "data_gaps": [],
    }
    return [
        {
            "stage": "investigator",
            "status": investigator_status,
            "input_json": {"tool_calls": tool_calls},
            "response_json": response,
        },
        {
            "stage": "decision_maker",
            "status": decision_maker_status,
            "input_json": {},
            "response_json": {},
        },
    ]


def _make_case(
    *,
    final: dict[str, Any] | None = None,
    stage_audits: list[dict[str, Any]] | None = None,
    hard_blocked: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "eval_case_id": "case-test",
        "harness_hash": "sha256:test",
        "route": "meme",
        "recommendation": (final or _v2_final())["recommendation"],
        "input_json": {
            "context": context or {"candidate_id": "candidate-1"},
            "completeness": {"hard_blocked": hard_blocked},
            "stage_audits": stage_audits if stage_audits is not None else _v2_stage_audits(),
        },
        "expected_json": {
            "final_decision": final if final is not None else _v2_final(),
            "stage_count": 2,
        },
    }


# ---------------------------------------------------------------------------
# Complete v2 happy path — all 5 rules pass
# ---------------------------------------------------------------------------


def test_complete_v2_case_passes_all_rules() -> None:
    result = grade_pulse_deterministic_eval_case(_make_case())

    assert result["status"] == "pass"
    assert result["score"] == 1.0
    assert result["details_json"]["violations"] == []
    assert result["grader_version"] == "pulse-deterministic-harness-v2"


# ---------------------------------------------------------------------------
# R1 stages_present
# ---------------------------------------------------------------------------


def test_r1_stages_present_happy() -> None:
    result = grade_pulse_deterministic_eval_case(_make_case())
    assert "stages_present" not in result["details_json"]["violations"]


def test_r1_stages_present_flags_missing_decision_maker() -> None:
    audits = _v2_stage_audits()
    audits[1]["status"] = "failed"
    result = grade_pulse_deterministic_eval_case(_make_case(stage_audits=audits))
    assert result["status"] == "fail"
    assert "stages_present" in result["details_json"]["violations"]


def test_r1_stages_present_skipped_when_hard_blocked() -> None:
    audits = [{"stage": "research_only_gate", "status": "skipped", "input_json": {}, "response_json": {}}]
    final = _v2_final(
        recommendation="abstain",
        evidence_event_ids=[],
        playbook=_v2_playbook(has_playbook=False),
    )
    final["abstain_reason"] = "hard_blocked"
    case = _make_case(final=final, stage_audits=audits, hard_blocked=True)
    result = grade_pulse_deterministic_eval_case(case)
    assert "stages_present" not in result["details_json"]["violations"]


# ---------------------------------------------------------------------------
# R2 tool_calls_present
# ---------------------------------------------------------------------------


def test_r2_tool_calls_present_happy() -> None:
    result = grade_pulse_deterministic_eval_case(_make_case())
    assert "tool_calls_present" not in result["details_json"]["violations"]


def test_r2_tool_calls_present_fails_when_empty() -> None:
    audits = _v2_stage_audits(investigator_tool_calls=[])
    result = grade_pulse_deterministic_eval_case(_make_case(stage_audits=audits))
    assert result["status"] == "fail"
    assert "tool_calls_present" in result["details_json"]["violations"]


def test_r2_tool_calls_skipped_when_hard_blocked() -> None:
    audits = [{"stage": "research_only_gate", "status": "skipped", "input_json": {}, "response_json": {}}]
    final = _v2_final(
        recommendation="abstain",
        evidence_event_ids=[],
        playbook=_v2_playbook(has_playbook=False),
    )
    final["abstain_reason"] = "hard_blocked"
    case = _make_case(final=final, stage_audits=audits, hard_blocked=True)
    result = grade_pulse_deterministic_eval_case(case)
    assert "tool_calls_present" not in result["details_json"]["violations"]


# ---------------------------------------------------------------------------
# R3 evidence_subset
# ---------------------------------------------------------------------------


def test_r3_evidence_subset_happy() -> None:
    result = grade_pulse_deterministic_eval_case(_make_case())
    assert "evidence_subset" not in result["details_json"]["violations"]


def test_r3_evidence_subset_fails_when_final_cites_unknown_event() -> None:
    final = _v2_final(evidence_event_ids=["event-1", "event-999"])
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert result["status"] == "fail"
    assert "evidence_subset" in result["details_json"]["violations"]


def test_r3_evidence_subset_accepts_context_supplied_ids() -> None:
    # investigator response has no event ids; context.evidence_event_ids supplies them.
    audits = _v2_stage_audits(
        investigator_response={
            "narrative_archetype_candidate": "kol-ignition",
            "narrative_observation_zh": "Stub investigator observation for tests.",
            "bull_observation": {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []},
            "bear_observation": {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []},
            "data_gaps": [],
        },
    )
    final = _v2_final(evidence_event_ids=["ctx-1"])
    case = _make_case(
        final=final,
        stage_audits=audits,
        context={"evidence_event_ids": ["ctx-1"], "source_event_ids": ["ctx-2"]},
    )
    result = grade_pulse_deterministic_eval_case(case)
    assert "evidence_subset" not in result["details_json"]["violations"]


# ---------------------------------------------------------------------------
# R4 high_conviction_constraint
# ---------------------------------------------------------------------------


def test_r4_high_conviction_happy() -> None:
    final = _v2_final(
        recommendation="high_conviction",
        evidence_event_ids=["event-1", "event-2", "event-3"],
        bull_strength="strong",
        bear_strength="moderate",
    )
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert "high_conviction_constraint" not in result["details_json"]["violations"]
    assert result["status"] == "pass"


def test_r4_high_conviction_fails_when_evidence_below_three() -> None:
    final = _v2_final(
        recommendation="high_conviction",
        evidence_event_ids=["event-1", "event-2"],
        bull_strength="strong",
        bear_strength="moderate",
    )
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert result["status"] == "fail"
    assert "high_conviction_constraint" in result["details_json"]["violations"]


def test_r4_high_conviction_fails_when_bull_strength_weak() -> None:
    final = _v2_final(
        recommendation="high_conviction",
        evidence_event_ids=["event-1", "event-2", "event-3"],
        bull_strength="weak",
        bear_strength="moderate",
    )
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert result["status"] == "fail"
    assert "high_conviction_constraint" in result["details_json"]["violations"]


# ---------------------------------------------------------------------------
# R5 playbook_consistent
# ---------------------------------------------------------------------------


def test_r5_playbook_consistent_abstain_happy() -> None:
    final = _v2_final(
        recommendation="abstain",
        evidence_event_ids=[],
        playbook=_v2_playbook(has_playbook=False),
    )
    final["abstain_reason"] = "Insufficient evidence"
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert "playbook_consistent" not in result["details_json"]["violations"]


def test_r5_playbook_consistent_fails_when_abstain_has_playbook_true() -> None:
    final = _v2_final(
        recommendation="abstain",
        evidence_event_ids=[],
        playbook=_v2_playbook(has_playbook=True),
    )
    final["abstain_reason"] = "Insufficient evidence"
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert result["status"] == "fail"
    assert "playbook_consistent" in result["details_json"]["violations"]


def test_r5_playbook_consistent_fails_when_abstain_has_watch_signals() -> None:
    playbook = {
        "has_playbook": False,
        "watch_signals": ["watch this"],
        "exit_triggers": [],
        "monitoring_horizon": "4h",
    }
    final = _v2_final(
        recommendation="abstain",
        evidence_event_ids=[],
        playbook=playbook,
    )
    final["abstain_reason"] = "Insufficient evidence"
    result = grade_pulse_deterministic_eval_case(_make_case(final=final))
    assert result["status"] == "fail"
    assert "playbook_consistent" in result["details_json"]["violations"]


# ---------------------------------------------------------------------------
# Legacy dispatch (G.1)
# ---------------------------------------------------------------------------


def test_legacy_case_detected_by_v1_stage_names_returns_legacy_skipped() -> None:
    case = {
        "eval_case_id": "case-v1",
        "harness_hash": "sha256:v1",
        "route": "meme",
        "recommendation": "trade_candidate",
        "input_json": {
            "context": {},
            "completeness": {"hard_blocked": False},
            "stage_audits": [
                {"stage": "analyst", "status": "ok", "input_json": {}, "response_json": {}},
                {"stage": "critic", "status": "ok", "input_json": {}, "response_json": {}},
                {"stage": "judge", "status": "ok", "input_json": {}, "response_json": {}},
            ],
        },
        "expected_json": {
            "final_decision": {
                # v1 schema lacked narrative/bull/bear/playbook.
                "route": "meme",
                "recommendation": "trade_candidate",
                "confidence": 0.4,
                "summary_zh": "v1 summary",
                "evidence_event_ids": ["event-1"],
            },
            "stage_count": 3,
        },
    }
    result = grade_pulse_deterministic_eval_case(case)
    assert result["status"] == "legacy_skipped"
    assert result["details_json"]["violations"] == []
    assert "notes" in result["details_json"]


def test_legacy_case_detected_by_missing_v2_keys_returns_legacy_skipped() -> None:
    """No v1 stage names, but final_decision lacks every v2 key."""

    case = {
        "eval_case_id": "case-v1-shape",
        "harness_hash": "sha256:v1-shape",
        "route": "meme",
        "recommendation": "trade_candidate",
        "input_json": {
            "context": {},
            "completeness": {"hard_blocked": False},
            # No stage names at all → can't detect from stages → fall back to final keys.
            "stage_audits": [],
        },
        "expected_json": {
            "final_decision": {
                "route": "meme",
                "recommendation": "trade_candidate",
                "confidence": 0.4,
                "summary_zh": "v1 summary",
            },
            "stage_count": 0,
        },
    }
    result = grade_pulse_deterministic_eval_case(case)
    assert result["status"] == "legacy_skipped"
    assert result["details_json"]["violations"] == []


def test_legacy_dispatch_is_defensive_against_missing_keys() -> None:
    """A near-empty case shape must not raise KeyError."""

    result = grade_pulse_deterministic_eval_case({})
    # Empty case has no v2 keys → treated as legacy.
    assert result["status"] == "legacy_skipped"
    assert result["details_json"]["violations"] == []
