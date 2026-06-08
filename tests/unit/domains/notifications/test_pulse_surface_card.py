from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.notifications.services.pulse_surface_card import render_pulse_surface_card


def _decision(
    *,
    route: str = "meme",
    recommendation: str = "trade_candidate",
    confidence: float = 0.78,
    narrative_archetype: str = "vc_endorsed_launch",
    narrative_thesis_zh: str = "知名 VC 在窗口内表态推动短期注意力。",
    bull_strength: str | None = "strong",
    bull_thesis: str = "10 名独立作者在 30 分钟内同步讨论，事件聚类。",
    bull_event_ids: list[str] | None = None,
    bear_strength: str | None = "moderate",
    bear_thesis: str = "出现两条关于流动性回撤的提示。",
    bear_event_ids: list[str] | None = None,
    playbook_present: bool = True,
    horizon: str = "4h",
    watch_signals: list[str] | None = None,
    exit_triggers: list[str] | None = None,
    evidence_event_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    bull: dict[str, Any] | None
    if bull_strength is None:
        bull = None
    else:
        bull = {
            "strength": bull_strength,
            "thesis_zh": bull_thesis,
            "supporting_event_ids": bull_event_ids or ["evt-bull-1", "evt-bull-2"],
        }
    bear: dict[str, Any] | None
    if bear_strength is None:
        bear = None
    else:
        bear = {
            "strength": bear_strength,
            "thesis_zh": bear_thesis,
            "supporting_event_ids": bear_event_ids or ["evt-bear-1"],
        }
    playbook = {
        "has_playbook": playbook_present,
        "monitoring_horizon": horizon,
        "watch_signals": watch_signals if watch_signals is not None else ["独立作者持续 ≥ 12", "watched_mentions ≥ 3"],
        "exit_triggers": exit_triggers if exit_triggers is not None else ["短时回撤超过 25%", "watched_mentions 停滞"],
    }
    return {
        "route": route,
        "recommendation": recommendation,
        "confidence": confidence,
        "abstain_reason": None,
        "summary_zh": "",
        "invalidation_conditions": [],
        "residual_risks": [],
        "evidence_event_ids": [],
        "narrative_archetype": narrative_archetype,
        "narrative_thesis_zh": narrative_thesis_zh,
        "bull_view": bull,
        "bear_view": bear,
        "playbook": playbook,
        "evidence_event_urls": evidence_event_urls
        or {
            "evt-bull-1": "https://x.com/alice/status/111",
            "evt-bull-2": "https://x.com/bob/status/222",
            "evt-bear-1": "https://x.com/charlie/status/333",
        },
    }


def _row(**overrides: Any) -> dict[str, Any]:
    base = {
        "candidate_id": "pulse-pepe-1",
        "subject_key": "asset:eip155:1:erc20:0xpepe",
        "symbol": "PEPE",
        "chain": "eip155:1",
        "address": "0xpepe",
    }
    base.update(overrides)
    return base


def test_happy_path_renders_all_six_sections():
    body = render_pulse_surface_card(row=_row(), decision=_decision())

    assert "## $PEPE · Meme · 交易候选 · conf 78% Signal Pulse" in body
    assert "### 📖 叙事" in body
    assert "`vc_endorsed_launch`" in body
    assert "知名 VC 在窗口内表态推动短期注意力。" in body
    assert "### 🟢 看多（强）" in body
    assert "10 名独立作者在 30 分钟内同步讨论" in body
    assert "[原推](https://x.com/alice/status/111)" in body
    assert "### 🔴 看空（中）" in body
    assert "出现两条关于流动性回撤的提示。" in body
    assert "### 🎯 Playbook" in body
    assert "监控窗口 4h" in body
    assert "独立作者持续 ≥ 12" in body
    assert "短时回撤超过 25%" in body
    assert "### 🔗 链接" in body
    assert "[GMGN](https://gmgn.ai/eip155%3A1/token/0xpepe)" in body
    assert "[X 搜索](https://x.com/search?q=%24PEPE&f=live)" in body
    assert "Pulse: `pulse-pepe-1`" in body


def test_bull_absent_drops_bull_section_keeps_bear():
    decision = _decision(bull_strength="absent")
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert "### 🟢 看多" not in body
    assert "### 🔴 看空" in body


def test_both_views_absent_and_no_narrative_drops_narrative_section():
    decision = _decision(
        bull_strength="absent",
        bear_strength="absent",
        narrative_archetype="",
        narrative_thesis_zh="",
    )
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert "### 📖 叙事" not in body
    assert "### 🟢 看多" not in body
    assert "### 🔴 看空" not in body
    # Always-keep tier
    assert "## $PEPE" in body
    assert "### 🎯 Playbook" in body
    assert "### 🔗 链接" in body


def test_no_playbook_drops_playbook_section():
    decision = _decision(playbook_present=False)
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert "### 🎯 Playbook" not in body
    # Other sections still present
    assert "## $PEPE" in body
    assert "### 📖 叙事" in body
    assert "### 🔗 链接" in body


def test_length_cap_triggers_degradation_in_order():
    huge = "拉" * 4000  # well past the 2500 cap on its own
    decision = _decision(narrative_thesis_zh=huge, bull_thesis=huge, bear_thesis=huge)

    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert len(body) <= 2500
    # Header / Playbook / Links must always survive
    assert "## $PEPE" in body
    assert "### 🎯 Playbook" in body
    assert "### 🔗 链接" in body
    # Bear should be the first to drop
    assert "### 🔴 看空" not in body


def test_length_cap_drops_bull_after_bear_when_still_over():
    # Make bull thesis also huge so dropping bear alone isn't enough
    huge = "拉" * 4000
    decision = _decision(narrative_thesis_zh="短叙事。", bull_thesis=huge, bear_thesis=huge)

    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert len(body) <= 2500
    assert "### 🔴 看空" not in body
    assert "### 🟢 看多" not in body
    # Narrative still present
    assert "短叙事。" in body
    assert "### 🎯 Playbook" in body


def test_length_cap_drops_narrative_last():
    huge = "拉" * 4000
    decision = _decision(
        narrative_thesis_zh=huge,
        bull_thesis=huge,
        bear_thesis=huge,
    )

    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert len(body) <= 2500
    # All three optional sections gone
    assert "### 📖 叙事" not in body
    assert "### 🟢 看多" not in body
    assert "### 🔴 看空" not in body
    # Always-keep tier present
    assert "## $PEPE" in body
    assert "### 🎯 Playbook" in body
    assert "### 🔗 链接" in body


def test_evidence_without_url_renders_truncated_id_fallback():
    decision = _decision(
        bear_event_ids=["evt-no-url-1"],
        evidence_event_urls={
            "evt-bull-1": "https://x.com/alice/status/111",
            "evt-bull-2": "https://x.com/bob/status/222",
            # evt-no-url-1 deliberately missing
        },
    )
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert "`evt-no-url-1…`" in body
    assert "[原推]" in body  # bull side still has urls


def test_evidence_with_url_renders_link():
    decision = _decision()
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert "[原推](https://x.com/alice/status/111)" in body
    assert "[原推](https://x.com/bob/status/222)" in body
    assert "[原推](https://x.com/charlie/status/333)" in body


def test_header_handles_unknown_route_and_recommendation_gracefully():
    decision = _decision(route="unknown_route", recommendation="unknown_rec", confidence=0.5)
    body = render_pulse_surface_card(row=_row(), decision=decision)

    # Unknown route/recommendation passed through verbatim
    assert "unknown_route" in body
    assert "unknown_rec" in body
    assert "conf 50%" in body


def test_header_omits_route_recommendation_when_blank():
    decision = _decision(route="", recommendation="", confidence=None)
    body = render_pulse_surface_card(row=_row(), decision=decision)

    # Should still have $PEPE header
    assert "## $PEPE Signal Pulse" in body


def test_missing_symbol_uses_subject_key():
    decision = _decision()
    body = render_pulse_surface_card(
        row={"candidate_id": "pulse-x", "subject_key": "source:event:abc", "symbol": None},
        decision=decision,
    )

    assert "source:event:abc" in body
    assert "$" not in body.split("Signal Pulse")[0]  # no $-prefixed symbol in header


def test_missing_chain_address_drops_gmgn_link_only():
    decision = _decision()
    body = render_pulse_surface_card(
        row={"candidate_id": "pulse-x", "subject_key": "asset:foo", "symbol": "PEPE"},
        decision=decision,
    )

    assert "GMGN" not in body
    assert "[X 搜索]" in body
    assert "Pulse: `pulse-x`" in body


def test_gmgn_link_uses_factor_snapshot_subject_when_row_chain_address_missing():
    body = render_pulse_surface_card(
        row={"candidate_id": "pulse-x", "subject_key": "asset:foo", "symbol": "PEPE"},
        decision=_decision(),
        factor_snapshot={"subject": {"chain": "solana", "address": "So11111111111111111111111111111111111111112"}},
    )

    assert "[GMGN](https://gmgn.ai/solana/token/So11111111111111111111111111111111111111112)" in body


def test_gmgn_link_uses_asset_profile_identity_when_row_and_snapshot_missing_chain_address():
    body = render_pulse_surface_card(
        row={"candidate_id": "pulse-x", "subject_key": "asset:foo", "symbol": "PEPE"},
        decision=_decision(),
        asset_profile={"identity": {"chain": "base", "address": "0xbase"}},
    )

    assert "[GMGN](https://gmgn.ai/base/token/0xbase)" in body


def test_evidence_id_list_capped_at_five():
    many_ids = [f"evt-bull-{i}" for i in range(10)]
    url_map = {f"evt-bull-{i}": f"https://x.com/u/status/{i}" for i in range(10)}
    decision = _decision(bull_event_ids=many_ids, evidence_event_urls=url_map)

    body = render_pulse_surface_card(row=_row(), decision=decision)

    # First 5 links present, 6th and later absent
    assert "[原推](https://x.com/u/status/0)" in body
    assert "[原推](https://x.com/u/status/4)" in body
    assert "[原推](https://x.com/u/status/5)" not in body


@pytest.mark.parametrize(
    "strength,zh",
    [
        ("weak", "弱"),
        ("moderate", "中"),
        ("strong", "强"),
    ],
)
def test_strength_label_mapping(strength: str, zh: str):
    decision = _decision(bull_strength=strength, bear_strength=None)
    body = render_pulse_surface_card(row=_row(), decision=decision)

    assert f"### 🟢 看多（{zh}）" in body


def test_narrative_thesis_with_execution_language_is_not_rendered():
    body = render_pulse_surface_card(
        row=_row(),
        decision=_decision(narrative_thesis_zh="建议买入并设置止损"),
    )

    assert "### 📖 叙事" in body
    assert "建议买入" not in body
    assert "止损" not in body


def test_bull_and_bear_theses_with_execution_language_are_not_rendered():
    body = render_pulse_surface_card(
        row=_row(),
        decision=_decision(
            bull_thesis="go long with leverage",
            bear_thesis="open short if momentum fades",
        ),
    )

    assert "### 🟢 看多" not in body
    assert "### 🔴 看空" not in body
    assert "go long" not in body
    assert "open short" not in body


def test_playbook_filters_execution_language_entries():
    body = render_pulse_surface_card(
        row=_row(),
        decision=_decision(
            watch_signals=["新增独立作者", "建议买入"],
            exit_triggers=["讨论降温", "设置止损"],
        ),
    )

    assert "新增独立作者" in body
    assert "讨论降温" in body
    assert "建议买入" not in body
    assert "设置止损" not in body


def test_body_has_final_hard_cap_after_degradation():
    huge_safe_entry = "安全观察信号" * 1000
    body = render_pulse_surface_card(
        row=_row(),
        decision=_decision(
            narrative_thesis_zh="叙事",
            bull_thesis="看多理由",
            bear_thesis="看空理由",
            watch_signals=[huge_safe_entry],
            exit_triggers=[huge_safe_entry],
        ),
    )

    assert len(body) <= 2500
    assert body.endswith("...")
