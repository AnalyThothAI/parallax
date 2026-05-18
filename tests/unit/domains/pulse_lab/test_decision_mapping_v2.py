"""Unit coverage for ``candidate_fields_from_decision`` v2 surface.

`decision_mapping` deliberately keeps v2 narrative / bull-bear / playbook /
evidence-url fields inside ``decision_json`` instead of promoting them into
dedicated columns (KISS — single source of truth for downstream readers).
These tests freeze that contract: a model_dump round-trip must include every
v2 field so ``SignalPulseService._decision`` can project them later.
"""

from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.services.decision_mapping import (
    candidate_fields_from_decision,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    TradePlaybook,
)


def _full_v2_decision() -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="high_conviction",
        confidence=0.82,
        abstain_reason=None,
        summary_zh="cohort 持续扩散，链上质量同步确认。",
        narrative_archetype="memetic",
        narrative_thesis_zh=(
            "多位独立 KOL 同时提及该 ticker 并触发现货放量，cohort 显著扩散，对立证据仍存但未占据主导。"
        ),
        bull_view=BullBearView(
            strength="strong",
            thesis_zh="cohort 扩散叠加现货放量双向确认",
            supporting_event_ids=["event-1", "event-2"],
        ),
        bear_view=BullBearView(
            strength="moderate",
            thesis_zh="流动性深度尚浅，存在闪崩风险",
            supporting_event_ids=["event-3"],
        ),
        playbook=TradePlaybook(
            has_playbook=True,
            watch_signals=["watched_mentions_growth", "independent_author_count"],
            exit_triggers=["mention_decay", "watched_silence"],
            monitoring_horizon="4h",
        ),
        evidence_event_urls={
            "event-1": "https://twitter.com/example/status/1",
            "event-2": "https://twitter.com/example/status/2",
        },
        invalidation_conditions=["主要 KOL 删帖。"],
        residual_risks=["市场宏观波动。"],
        evidence_event_ids=["event-1", "event-2", "event-3"],
    )


def test_candidate_fields_decision_json_contains_all_v2_fields() -> None:
    fields = candidate_fields_from_decision(_full_v2_decision(), stage_count=2)
    decision_json = fields["decision_json"]

    assert decision_json["narrative_archetype"] == "memetic"
    assert decision_json["narrative_thesis_zh"].startswith("多位独立 KOL")
    assert decision_json["bull_view"] == {
        "strength": "strong",
        "thesis_zh": "cohort 扩散叠加现货放量双向确认",
        "supporting_event_ids": ["event-1", "event-2"],
    }
    assert decision_json["bear_view"] == {
        "strength": "moderate",
        "thesis_zh": "流动性深度尚浅，存在闪崩风险",
        "supporting_event_ids": ["event-3"],
    }
    assert decision_json["playbook"] == {
        "has_playbook": True,
        "watch_signals": ["watched_mentions_growth", "independent_author_count"],
        "exit_triggers": ["mention_decay", "watched_silence"],
        "monitoring_horizon": "4h",
    }
    assert decision_json["evidence_event_urls"] == {
        "event-1": "https://twitter.com/example/status/1",
        "event-2": "https://twitter.com/example/status/2",
    }
    # v1 fields still present
    assert decision_json["summary_zh"].startswith("cohort")
    assert decision_json["evidence_event_ids"] == ["event-1", "event-2", "event-3"]


def test_candidate_fields_does_not_promote_v2_to_main_columns() -> None:
    """v2 narrative / bull-bear / playbook are intentionally NOT mapped to
    pulse_candidates main-table columns. They live only inside decision_json.
    This freezes the KISS decision so future contributors don't add redundant
    columns + dual-write risk.
    """
    fields = candidate_fields_from_decision(_full_v2_decision(), stage_count=2)
    forbidden = {
        "decision_narrative_archetype",
        "decision_narrative_thesis_zh",
        "decision_bull_view",
        "decision_bear_view",
        "decision_playbook",
        "decision_evidence_event_urls",
    }
    assert forbidden.isdisjoint(fields.keys())


def test_candidate_fields_v1_columns_still_present() -> None:
    fields = candidate_fields_from_decision(_full_v2_decision(), stage_count=2)
    assert fields["decision_route"] == "meme"
    assert fields["decision_recommendation"] == "high_conviction"
    assert fields["decision_confidence"] == 0.82
    assert fields["decision_abstain_reason"] is None
    assert fields["decision_stage_count"] == 2
    assert fields["score_band"] == "high_conviction"
