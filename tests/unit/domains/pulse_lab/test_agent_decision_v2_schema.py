"""Schema tests for the v2 Pulse agent decision pydantic types.

Covers the BullBearView / TradePlaybook / EvidenceDebateMemo types and
the v2-extended FinalDecision hard constraints (Task 3, plan
2026-05-16-pulse-agent-desk-redesign-plan-cn.md §Task 3).

OQ-4 reject_execution_language counter-test is also included to confirm
field names / enum values introduced in v2 do not trigger the forbidden
trading-execution regex.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    EvidenceClaim,
    EvidenceDebateMemo,
    FinalDecision,
    TradePlaybook,
    contains_trading_execution_instruction,
)

_ABSTAIN_THESIS = "窗口期内未观察到稳定叙事或对立证据，缺乏足够输入支撑可执行的判断，应转入 research_only"


# ---------------------------------------------------------------------------
# BullBearView
# ---------------------------------------------------------------------------


def test_bull_bear_view_absent_with_empty_fields_ok() -> None:
    view = BullBearView(strength="absent")
    assert view.strength == "absent"
    assert view.thesis_zh == ""
    assert view.supporting_event_ids == []


def test_bull_bear_view_absent_with_thesis_rejected() -> None:
    with pytest.raises(ValidationError, match="strength=absent requires empty thesis_zh"):
        BullBearView(strength="absent", thesis_zh="不应该有 thesis")


def test_bull_bear_view_absent_with_supporting_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="strength=absent requires empty supporting_event_ids"):
        BullBearView(strength="absent", supporting_event_ids=["event-1"])


def test_bull_bear_view_non_absent_without_supporting_ids_ok() -> None:
    view = BullBearView(strength="moderate", thesis_zh="社交热度持续上升")
    assert view.supporting_event_ids == []


def test_bull_bear_view_non_absent_without_thesis_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty thesis_zh"):
        BullBearView(strength="moderate", supporting_event_ids=["event-1"])


def test_bull_bear_view_moderate_with_thesis_and_ids_ok() -> None:
    view = BullBearView(
        strength="moderate",
        thesis_zh="多位 KOL 同时提及该 ticker",
        supporting_event_ids=["event-1", "event-2"],
    )
    assert view.strength == "moderate"


def test_bull_bear_view_rejects_execution_language_in_thesis() -> None:
    with pytest.raises(ValidationError, match="trading execution"):
        BullBearView(
            strength="strong",
            thesis_zh="建议买入并设置止损",
            supporting_event_ids=["event-1"],
        )


# ---------------------------------------------------------------------------
# TradePlaybook
# ---------------------------------------------------------------------------


def test_trade_playbook_no_playbook_with_empty_lists_ok() -> None:
    playbook = TradePlaybook(has_playbook=False, monitoring_horizon="24h")
    assert playbook.has_playbook is False
    assert playbook.watch_signals == []
    assert playbook.exit_triggers == []


def test_trade_playbook_no_playbook_with_watch_signals_cleared() -> None:
    playbook = TradePlaybook(
        has_playbook=False,
        watch_signals=["流动性回撤"],
        monitoring_horizon="1h",
    )
    assert playbook.watch_signals == []


def test_trade_playbook_no_playbook_with_exit_triggers_cleared() -> None:
    playbook = TradePlaybook(
        has_playbook=False,
        exit_triggers=["提及量下降"],
        monitoring_horizon="4h",
    )
    assert playbook.exit_triggers == []


def test_trade_playbook_has_playbook_with_only_exit_triggers_ok() -> None:
    # Spec allows has_playbook=true even if watch_signals empty (so long as
    # exit_triggers carries content). Only the False case forces both empty.
    playbook = TradePlaybook(
        has_playbook=True,
        watch_signals=[],
        exit_triggers=["关键作者抛售"],
        monitoring_horizon="4h",
    )
    assert playbook.has_playbook is True


def test_trade_playbook_rejects_execution_language() -> None:
    with pytest.raises(ValidationError, match="trading execution"):
        TradePlaybook(
            has_playbook=True,
            watch_signals=["关注 buy signal"],
            exit_triggers=["提及量停止增长"],
            monitoring_horizon="1h",
        )


# ---------------------------------------------------------------------------
# EvidenceDebateMemo
# ---------------------------------------------------------------------------


def _absent() -> BullBearView:
    return BullBearView(strength="absent")


def test_evidence_debate_memo_with_allowed_refs_ok() -> None:
    memo = EvidenceDebateMemo(
        bull_claims=(
            EvidenceClaim(claim="社交事件显示讨论正在扩散", evidence_refs=("event:event-1",), stance="bull"),
        ),
        bear_claims=(
            EvidenceClaim(claim="市场流动性仍然偏薄", evidence_refs=("market:pf-1",), stance="risk"),
        ),
        summary_zh="证据包内社交扩散较强，但市场流动性仍偏薄，需要等待更多确认。",
        allowed_evidence_ref_ids=("event:event-1", "market:pf-1"),
    )
    assert memo.allowed_evidence_ref_ids == ("event:event-1", "market:pf-1")


def test_evidence_debate_claim_requires_evidence_refs() -> None:
    claim = EvidenceClaim(claim="社交事件显示讨论正在扩散", evidence_refs=(), stance="bull")
    assert claim.evidence_refs == ()


def test_evidence_claim_allows_factual_buy_language() -> None:
    claim = EvidenceClaim(claim="链上记录显示地址买入并推高热度。", evidence_refs=("event:1",), stance="bull")

    assert claim.claim == "链上记录显示地址买入并推高热度。"


@pytest.mark.parametrize(
    "claim_text",
    [
        "链上可以看到鲸鱼买入。",
        "可以看到地址买入并推高热度。",
        "社群记录显示卖压出现但资金仍然流入。",
    ],
)
def test_evidence_claim_allows_factual_market_flow_language(claim_text: str) -> None:
    claim = EvidenceClaim(claim=claim_text, evidence_refs=("event:1",), stance="bull")

    assert claim.claim == claim_text


@pytest.mark.parametrize(
    "claim_text",
    [
        "建议买入并设置止损。",
        "推荐买入。",
        "应当买入。",
        "必须买入。",
        "不要买入。",
        "建议建仓。",
        "应该加仓。",
        "适合减仓。",
    ],
)
def test_evidence_claim_rejects_prescriptive_execution_advice(claim_text: str) -> None:
    with pytest.raises(ValidationError, match="trading execution"):
        EvidenceClaim(claim=claim_text, evidence_refs=("event:1",), stance="bull")


# ---------------------------------------------------------------------------
# FinalDecision (v2)
# ---------------------------------------------------------------------------


def _playbook(has: bool = True) -> TradePlaybook:
    if has:
        return TradePlaybook(
            has_playbook=True,
            watch_signals=["cohort 持续扩散"],
            exit_triggers=["提及量停止增长"],
            monitoring_horizon="4h",
        )
    return TradePlaybook(has_playbook=False, monitoring_horizon="24h")


def _hc_kwargs(
    *,
    archetype: str = "memetic",
    bear_strength: str = "moderate",
    evidence_count: int = 3,
) -> dict[str, object]:
    bear: BullBearView
    if bear_strength == "absent":
        bear = _absent()
    else:
        bear = BullBearView(
            strength=bear_strength,  # type: ignore[arg-type]
            thesis_zh="流动性深度仍然偏薄，存在拉砸风险",
            supporting_event_ids=["bear-1", "bear-2"],
        )
    return {
        "route": "meme",
        "recommendation": "high_conviction",
        "confidence": 0.82,
        "abstain_reason": None,
        "summary_zh": "社交与市场事实共振，cohort 扩散充分",
        "narrative_archetype": archetype,
        "narrative_thesis_zh": "叙事由多位 KOL 同时提及并触发现货放量，cohort 显著扩散且未见显著反驳",
        "bull_view": BullBearView(
            strength="strong",
            thesis_zh="cohort 扩散 + 现货放量双向确认",
            supporting_event_ids=[f"event-{i}" for i in range(1, evidence_count + 1)],
        ),
        "bear_view": bear,
        "playbook": _playbook(True),
        "evidence_event_ids": [f"event-{i}" for i in range(1, evidence_count + 1)],
        "supporting_evidence_refs": tuple(f"event:event-{i}" for i in range(1, evidence_count + 1)),
    }


def test_final_decision_high_conviction_with_bear_absent_rejected() -> None:
    kwargs = _hc_kwargs(bear_strength="absent")
    with pytest.raises(ValidationError, match=r"bear_view\.strength >= moderate"):
        FinalDecision(**kwargs)


def test_final_decision_high_conviction_with_insufficient_evidence_rejected() -> None:
    kwargs = _hc_kwargs(evidence_count=2)
    with pytest.raises(ValidationError, match="evidence_event_ids >= 3"):
        FinalDecision(**kwargs)


def test_final_decision_high_conviction_with_empty_archetype_rejected() -> None:
    kwargs = _hc_kwargs(archetype="")
    with pytest.raises(ValidationError, match="non-empty narrative_archetype"):
        FinalDecision(**kwargs)


def test_final_decision_high_conviction_with_unclear_archetype_rejected() -> None:
    kwargs = _hc_kwargs(archetype="unclear")
    with pytest.raises(ValidationError, match="non-empty narrative_archetype"):
        FinalDecision(**kwargs)


def test_final_decision_high_conviction_with_all_constraints_ok() -> None:
    decision = FinalDecision(**_hc_kwargs())
    assert decision.recommendation == "high_conviction"
    assert decision.bull_view.strength == "strong"
    assert decision.bear_view.strength == "moderate"
    assert len(decision.evidence_event_ids) == 3
    assert decision.narrative_archetype == "memetic"


def test_final_decision_abstain_with_active_playbook_rejected() -> None:
    with pytest.raises(ValidationError, match=r"playbook\.has_playbook=false"):
        FinalDecision(
            route="research_only",
            recommendation="abstain",
            confidence=0.0,
            abstain_reason="证据不足以形成判断",
            summary_zh="证据缺失，转 research_only。",
            narrative_archetype="",
            narrative_thesis_zh=_ABSTAIN_THESIS,
            bull_view=_absent(),
            bear_view=_absent(),
            playbook=_playbook(True),
            evidence_event_ids=[],
        )


def test_final_decision_abstain_requires_abstain_reason() -> None:
    with pytest.raises(ValidationError, match="abstain_reason is required"):
        FinalDecision(
            route="research_only",
            recommendation="abstain",
            confidence=0.0,
            abstain_reason=None,
            summary_zh="证据不足。",
            narrative_archetype="",
            narrative_thesis_zh=_ABSTAIN_THESIS,
            bull_view=_absent(),
            bear_view=_absent(),
            playbook=_playbook(False),
            evidence_event_ids=[],
        )


def test_final_decision_abstain_with_no_playbook_ok() -> None:
    decision = FinalDecision(
        route="research_only",
        recommendation="abstain",
        confidence=0.0,
        abstain_reason="resolver 未确定 target；不能形成资产判断",
        summary_zh="目标资产未解析，转 research_only。",
        narrative_archetype="",
        narrative_thesis_zh=_ABSTAIN_THESIS,
        bull_view=_absent(),
        bear_view=_absent(),
        playbook=_playbook(False),
        evidence_event_ids=[],
        residual_risks=["无 target 无法形成资产判断"],
    )
    assert decision.recommendation == "abstain"
    assert decision.playbook.has_playbook is False


def test_final_decision_round_trip_model_validate_dump_consistent() -> None:
    decision = FinalDecision(**_hc_kwargs())
    dumped = decision.model_dump(mode="json")
    re_validated = FinalDecision.model_validate(dumped)
    assert re_validated.model_dump(mode="json") == dumped


def test_final_decision_rejects_execution_language_in_summary() -> None:
    kwargs = _hc_kwargs()
    kwargs["summary_zh"] = "可以买入并设置止损止盈"
    with pytest.raises(ValidationError, match="trading execution"):
        FinalDecision(**kwargs)


def test_final_decision_rejects_prescriptive_execution_advice_in_summary() -> None:
    kwargs = _hc_kwargs()
    kwargs["summary_zh"] = "建议买入。"
    with pytest.raises(ValidationError, match="trading execution"):
        FinalDecision(**kwargs)


def test_final_decision_non_abstain_without_packet_refs_rejected() -> None:
    with pytest.raises(ValidationError, match="supporting_evidence_refs"):
        FinalDecision(
            route="meme",
            recommendation="watchlist",
            confidence=0.4,
            abstain_reason=None,
            summary_zh="放观察列表。",
            narrative_archetype="memetic",
            narrative_thesis_zh="叙事正在成型但 cohort 尚未扩散，需要更多窗口期观察才能确认方向",
            bull_view=BullBearView(
                strength="weak",
                thesis_zh="单一 KOL 提及",
                supporting_event_ids=["event-1"],
            ),
            bear_view=_absent(),
            playbook=_playbook(True),
            evidence_event_ids=[],
            residual_risks=[],
        )


# ---------------------------------------------------------------------------
# OQ-4: reject_execution_language counter-test for v2 field/enum vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "1h",
        "4h",
        "24h",
        "has_playbook",
        "watch_signals",
        "exit_triggers",
        "monitoring_horizon",
        "关注 watched_author 接力",
        "流动性回撤 >20% 触发退出",
        "提及量停止增长",
        "关键作者抛售",
        "narrative_archetype",
        "narrative_thesis_zh",
        "bull_view",
        "bear_view",
        "evidence_event_urls",
        "evidence_debate",
        "decision_maker",
    ],
)
def test_oq4_reject_execution_language_no_false_positives(case: str) -> None:
    assert contains_trading_execution_instruction(case) is False, (
        f"OQ-4 regression: {case!r} falsely classified as trading execution language"
    )


@pytest.mark.parametrize(
    "case",
    ["买入并止损", "go long", "open short", "set stop loss", "leverage 5x"],
)
def test_oq4_reject_execution_language_still_catches_real_cases(case: str) -> None:
    assert contains_trading_execution_instruction(case) is True
