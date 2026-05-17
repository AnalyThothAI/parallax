"""Integration coverage for ``SignalPulseService._decision`` v2 surface.

Phase-2 surface contract: the read-model must project the full v2 FinalDecision
shape (narrative + bull/bear/playbook + evidence_event_urls) out of
``decision_json`` so the SurfaceCard UI can render without re-reading the agent
run. Each case targets a single defensive rule so a regression points at one
helper instead of a wall of diffed dicts.
"""

from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import _decision


def _row(decision_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_route": "meme",
        "decision_recommendation": decision_json.get("recommendation", "watchlist"),
        "decision_confidence": decision_json.get("confidence", 0.42),
        "decision_abstain_reason": decision_json.get("abstain_reason"),
        "decision_stage_count": 2,
        "decision_json": decision_json,
    }


def _full_v2_decision() -> dict[str, Any]:
    return {
        "route": "meme",
        "recommendation": "high_conviction",
        "confidence": 0.82,
        "abstain_reason": None,
        "summary_zh": "链上热度+独立作者扩散同步推升。",
        "narrative_archetype": "memetic",
        "narrative_thesis_zh": "新一波独立账号扩散把讨论从核心圈外推到二级账号，链上质量保持稳定。",
        "bull_view": {
            "strength": "strong",
            "thesis_zh": "独立作者数翻倍且链上深度无下滑。",
            "supporting_event_ids": ["event-1", "event-2"],
        },
        "bear_view": {
            "strength": "moderate",
            "thesis_zh": "讨论集中在 30 分钟窗口，存在情绪降温风险。",
            "supporting_event_ids": ["event-3"],
        },
        "playbook": {
            "has_playbook": True,
            "watch_signals": ["watched_mentions_growth", "independent_author_count"],
            "exit_triggers": ["mention_decay", "watched_silence"],
            "monitoring_horizon": "4h",
        },
        "evidence_event_urls": {
            "event-1": "https://twitter.com/example/status/1",
            "event-2": "https://twitter.com/example/status/2",
        },
        "invalidation_conditions": ["主要 KOL 删帖。"],
        "residual_risks": ["市场宏观波动。"],
        "evidence_event_ids": ["event-1", "event-2", "event-3"],
    }


def test_decision_projects_full_v2_surface() -> None:
    decision = _decision(_row(_full_v2_decision()))

    assert decision["narrative_archetype"] == "memetic"
    assert decision["narrative_thesis_zh"].startswith("新一波独立账号扩散")
    assert decision["bull_view"] == {
        "strength": "strong",
        "thesis_zh": "独立作者数翻倍且链上深度无下滑。",
        "supporting_event_ids": ["event-1", "event-2"],
    }
    assert decision["bear_view"] == {
        "strength": "moderate",
        "thesis_zh": "讨论集中在 30 分钟窗口，存在情绪降温风险。",
        "supporting_event_ids": ["event-3"],
    }
    assert decision["playbook"] == {
        "has_playbook": True,
        "watch_signals": ["watched_mentions_growth", "independent_author_count"],
        "exit_triggers": ["mention_decay", "watched_silence"],
        "monitoring_horizon": "4h",
    }
    assert decision["evidence_event_urls"] == {
        "event-1": "https://twitter.com/example/status/1",
        "event-2": "https://twitter.com/example/status/2",
    }
    # v1 fields still surface alongside v2
    assert decision["summary_zh"] == "链上热度+独立作者扩散同步推升。"
    assert decision["evidence_event_ids"] == ["event-1", "event-2", "event-3"]


def test_decision_returns_none_when_bull_view_missing() -> None:
    payload = _full_v2_decision()
    payload.pop("bull_view")
    decision = _decision(_row(payload))
    assert decision["bull_view"] is None
    # bear_view unaffected
    assert decision["bear_view"] is not None


def test_decision_returns_none_when_bull_view_strength_invalid() -> None:
    payload = _full_v2_decision()
    payload["bull_view"]["strength"] = "ferocious"
    decision = _decision(_row(payload))
    assert decision["bull_view"] is None


def test_decision_returns_none_when_playbook_horizon_invalid() -> None:
    payload = _full_v2_decision()
    payload["playbook"]["monitoring_horizon"] = "30m"
    decision = _decision(_row(payload))
    assert decision["playbook"] is None


def test_decision_returns_none_when_playbook_missing() -> None:
    payload = _full_v2_decision()
    payload.pop("playbook")
    decision = _decision(_row(payload))
    assert decision["playbook"] is None


def test_decision_evidence_event_urls_filters_non_string_values() -> None:
    payload = _full_v2_decision()
    payload["evidence_event_urls"] = {
        "event-1": "https://twitter.com/example/status/1",
        "event-2": 12345,  # numeric url is rejected
        17: "https://twitter.com/example/status/3",  # non-string key rejected
    }
    decision = _decision(_row(payload))
    assert decision["evidence_event_urls"] == {
        "event-1": "https://twitter.com/example/status/1",
    }


def test_decision_evidence_event_urls_empty_when_not_dict() -> None:
    payload = _full_v2_decision()
    payload["evidence_event_urls"] = ["not", "a", "map"]
    decision = _decision(_row(payload))
    assert decision["evidence_event_urls"] == {}


def test_decision_defaults_for_missing_v2_fields_are_safe() -> None:
    payload = {
        "route": "meme",
        "recommendation": "abstain",
        "confidence": 0.0,
        "abstain_reason": "missing_data",
        "summary_zh": "信息不足。",
    }
    decision = _decision(_row(payload))
    assert decision["narrative_archetype"] == ""
    assert decision["narrative_thesis_zh"] == ""
    assert decision["bull_view"] is None
    assert decision["bear_view"] is None
    assert decision["playbook"] is None
    assert decision["evidence_event_urls"] == {}
