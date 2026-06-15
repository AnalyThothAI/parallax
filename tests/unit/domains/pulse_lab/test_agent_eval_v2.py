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
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket


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


def test_evidence_first_eval_requires_formal_packet_contract() -> None:
    case = _case()
    case["input_json"]["context"]["evidence_packet"] = {
        "evidence_packet_hash": "sha256:packet",
        "allowed_evidence_refs": [{"ref_id": "event:event-1", "ref_type": "event"}],
    }

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


def test_cost_guard_skip_decision_does_not_require_decision_stage() -> None:
    case = _case(
        final=_abstain_decision(),
        stages=("evidence_pack", "evidence_completeness_gate"),
    )
    case["input_json"]["context"]["cost_guard"] = {
        "decision": {"action": "skip_decision", "decision_allowed": False},
    }

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"
    assert result["details_json"]["checked_stage_names"] == [
        "evidence_pack",
        "evidence_completeness_gate",
    ]


def test_cost_guard_reuse_terminal_run_is_not_a_stage_skip_escape_hatch() -> None:
    case = _case(stages=("evidence_pack", "evidence_completeness_gate"))
    case["input_json"]["context"]["cost_guard"] = {
        "decision": {"action": "reuse_terminal_run"},
    }

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "fail"
    assert "stage_contract" in result["details_json"]["violations"]


def test_failed_eval_case_records_failure_reason() -> None:
    case = build_pulse_failed_eval_case(
        run_id="run-1",
        runtime_hash="sha256:runtime",
        context={"evidence_packet": _packet()},
        route="meme",
        completeness={"hard_blocked": False},
        stage_audits=(_stage("pulse_decision", status="failed"),),
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
        "pulse_decision",
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
    refs = ("event:event-1", "market:pf-1", "metric:market:price_usd", "gate:pulse:market_missing")
    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        run_id="run-1",
        evidence_packet_hash="sha256:packet",
        schema_version="pulse-evidence-packet-v1",
        candidate_id="candidate-1",
        target_type="chain_token",
        target_id="asset:test",
        symbol="TEST",
        window="1h",
        scope="default",
        snapshot_at_ms=1,
        source_event_ids=("event-1",),
        allowed_evidence_refs=[
            {
                "ref_id": ref,
                "ref_type": ref.split(":", 1)[0],
                "source_table": "events",
                "source_id": ref.rsplit(":", 1)[-1],
                "observed_at_ms": 1,
                "summary_zh": "证据摘要",
                "quality": "high",
            }
            for ref in refs
        ],
        social_evidence={"status": "complete", "event_refs": ("event:event-1",)},
        market_evidence={
            "status": "complete",
            "route": "meme",
            "target_market_type": "dex",
            "price_usd": 1.0,
            "liquidity_usd": 1000.0,
            "freshness_status": "fresh",
            "market_refs": ("market:pf-1", "metric:market:price_usd"),
        },
        identity_evidence={"status": "complete", "identity_refs": ("identity:token",)},
        quality_metrics={"ref_count": len(refs), "high_quality_ref_count": len(refs), "fresh_ref_count": len(refs)},
    ).model_dump(mode="json")


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
