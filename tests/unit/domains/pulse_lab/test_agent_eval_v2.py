from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.services.agent_eval import (
    build_pulse_deterministic_eval_case,
    build_pulse_failed_eval_case,
    grade_pulse_deterministic_eval_case,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    StageRunAudit,
    TradePlaybook,
)


def test_evidence_first_eval_passes_complete_packet_run() -> None:
    result = grade_pulse_deterministic_eval_case(_case())

    assert result["status"] == "pass"
    assert result["details_json"]["violations"] == []


def test_evidence_first_eval_requires_packet_and_refs() -> None:
    case = _case()
    case["input_json"]["context"]["evidence_packet"] = {}

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "fail"
    assert "evidence_packet_exists" in result["details_json"]["violations"]


def test_evidence_first_eval_rejects_unknown_final_refs() -> None:
    final = _final_decision(supporting_evidence_refs=("event:ghost",))

    result = grade_pulse_deterministic_eval_case(_case(final=final))

    assert result["status"] == "fail"
    assert "decision_refs_subset_packet_refs" in result["details_json"]["violations"]
    assert result["details_json"]["unknown_refs"] == ["event:ghost"]


def test_evidence_first_eval_allows_missing_data_gap_refs() -> None:
    final = _final_decision(data_gap_refs=("missing:social_breadth",))

    result = grade_pulse_deterministic_eval_case(_case(final=final))

    assert result["status"] == "pass"
    assert result["details_json"]["unknown_refs"] == []


def test_hard_blocked_packet_does_not_require_llm_stages() -> None:
    final = _abstain_decision()
    case = _case(
        final=final,
        completeness={
            "hard_blocked": True,
            "blocked_reason": "blocked_market_contract",
            "max_decision_status": "abstain",
        },
        stages=("evidence_pack", "evidence_completeness_gate"),
    )

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"


def test_cost_guard_research_only_does_not_require_public_judge_stage() -> None:
    case = _case(
        final=_abstain_decision(),
        stages=("evidence_pack", "evidence_completeness_gate", "signal_analyst", "bear_case"),
    )
    case["input_json"]["context"]["cost_guard"] = {
        "decision": {"action": "research_only"},
        "stage_plan": {
            "run_signal_analyst": True,
            "run_bear_case": True,
            "run_risk_portfolio_judge": False,
        },
    }

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"
    assert result["details_json"]["checked_stage_names"] == [
        "evidence_pack",
        "evidence_completeness_gate",
        "signal_analyst",
        "bear_case",
    ]


def test_cost_guard_reused_terminal_run_does_not_require_model_stages() -> None:
    case = _case(stages=("evidence_pack", "evidence_completeness_gate"))
    case["input_json"]["context"]["cost_guard"] = {
        "decision": {"action": "reuse_terminal_run"},
        "stage_plan": {
            "run_signal_analyst": True,
            "run_bear_case": True,
            "run_risk_portfolio_judge": True,
        },
    }

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"


def test_failed_eval_case_records_failure_reason() -> None:
    case = build_pulse_failed_eval_case(
        run_id="run-1",
        runtime_hash="sha256:runtime",
        context={"evidence_packet": _packet()},
        route="meme",
        completeness={"hard_blocked": False},
        stage_audits=(_stage("signal_analyst", status="failed"),),
        failure_reason="invalid_schema",
    )

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"


def _case(
    *,
    final: FinalDecision | None = None,
    completeness: dict[str, Any] | None = None,
    stages: tuple[str, ...] = (
        "evidence_pack",
        "evidence_completeness_gate",
        "signal_analyst",
        "bear_case",
        "risk_portfolio_judge",
    ),
) -> dict[str, Any]:
    return build_pulse_deterministic_eval_case(
        run_id="run-1",
        runtime_hash="sha256:runtime",
        context={"evidence_packet": _packet()},
        route="meme",
        completeness=completeness
        or {
            "hard_blocked": False,
            "max_decision_status": "trade_candidate",
        },
        final_decision=final or _final_decision(),
        stage_audits=tuple(_stage(stage) for stage in stages),
    )


def _packet() -> dict[str, Any]:
    return {
        "evidence_packet_hash": "sha256:packet",
        "allowed_evidence_refs": [
            {"ref_id": "event:event-1", "ref_type": "event"},
            {"ref_id": "market:pf-1", "ref_type": "market"},
            {"ref_id": "metric:market:price_usd", "ref_type": "metric"},
            {"ref_id": "gate:pulse:market_missing", "ref_type": "gate"},
        ],
    }


def _stage(stage: str, *, status: str = "ok") -> StageRunAudit:
    return StageRunAudit(
        stage=stage,  # type: ignore[arg-type]
        route="meme",
        attempt_index=0,
        input_json={},
        prompt_text=f"{stage} prompt",
        response_json={},
        trace_metadata_json={},
        usage_json={},
        latency_ms=1,
        status=status,  # type: ignore[arg-type]
        error=None if status == "ok" else "failed",
    )


def _final_decision(
    *,
    supporting_evidence_refs: tuple[str, ...] = ("event:event-1",),
    data_gap_refs: tuple[str, ...] = (),
) -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="watchlist",
        confidence=0.62,
        summary_zh="社交证据支持继续观察，市场风险仍需跟踪。",
        narrative_archetype="social_spread",
        narrative_thesis_zh="社交扩散正在形成，但市场确认仍有限，需要继续观察后续窗口的独立作者、流动性和价格反馈。",
        bull_view=BullBearView(
            strength="moderate",
            thesis_zh="社交事件显示讨论正在扩散。",
            supporting_event_ids=["event-1"],
        ),
        bear_view=BullBearView(
            strength="weak",
            thesis_zh="市场流动性和后续确认仍不足。",
            supporting_event_ids=["event-1"],
        ),
        playbook=TradePlaybook(
            has_playbook=True,
            watch_signals=["后续社交扩散继续增加"],
            exit_triggers=["讨论热度快速回落"],
            monitoring_horizon="4h",
        ),
        evidence_event_ids=["event-1"],
        supporting_evidence_refs=supporting_evidence_refs,
        risk_evidence_refs=("market:pf-1",),
        data_gap_refs=data_gap_refs,
        residual_risks=["市场确认仍不足。"],
        invalidation_conditions=["讨论热度快速回落。"],
    )


def _abstain_decision() -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="abstain",
        confidence=0.0,
        abstain_reason="blocked_market_contract",
        summary_zh="证据包缺少市场事实，无法形成可靠判断。",
        narrative_archetype="",
        narrative_thesis_zh="证据包缺少市场事实，无法形成可靠叙事判断，应等待补齐后再评估。",
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        evidence_event_ids=[],
        data_gap_refs=("gate:pulse:market_missing",),
        residual_risks=["blocked_market_contract"],
        invalidation_conditions=[],
    )
