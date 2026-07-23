from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    DailyMacroJudgment,
    EvidenceAvailability,
    EvidencePackHealth,
    JudgmentGateError,
    MacroEvidenceItem,
    MacroEvidencePack,
    ReviewerResult,
    render_daily_macro_judgment_zh,
    require_renderer_consistency,
    validate_daily_macro_judgment,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    is_us_market_session,
    market_session_advance,
    market_session_close_ms,
)

SESSION = date(2026, 7, 2)
CUTOFF_MS = market_session_close_ms(SESSION)


def test_contract_rejects_scores_probabilities_and_non_spy_calls() -> None:
    raw = _judgment_payload(_pack())
    raw["score"] = 72
    with pytest.raises(JudgmentGateError, match="forbidden_fields:score"):
        validate_daily_macro_judgment(raw, evidence_pack=_pack(), reviewer=ReviewerResult(disposition="pass"))

    raw = _judgment_payload(_pack())
    raw["tlt_5d"] = {"direction": "up"}
    with pytest.raises(JudgmentGateError, match="schema_invalid"):
        validate_daily_macro_judgment(raw, evidence_pack=_pack(), reviewer=ReviewerResult(disposition="pass"))

    with pytest.raises(ValidationError):
        DailyMacroJudgment.model_validate({**_judgment_payload(_pack()), "probability": 0.7})


def test_range_and_no_call_are_distinct_machine_states() -> None:
    pack = _pack()
    raw = _judgment_payload(pack)
    raw["spy_5d"]["direction"] = "range"
    raw["spy_20d"]["direction"] = "no_call"

    judgment = validate_daily_macro_judgment(
        raw,
        evidence_pack=pack,
        reviewer=ReviewerResult(disposition="pass"),
    )

    assert judgment.spy_5d.direction.value == "range"
    assert judgment.spy_20d.direction.value == "no_call"


def test_degraded_pack_forces_affected_horizon_to_no_call() -> None:
    pack = _pack(
        health=EvidencePackHealth(
            status="degraded",
            local_reasons=("credit_stale",),
            no_call_horizons=(20,),
        )
    )
    raw = _judgment_payload(pack)
    raw["data_health"] = "degraded"
    raw["spy_20d"]["direction"] = "down"
    with pytest.raises(JudgmentGateError, match="requires_no_call:20"):
        validate_daily_macro_judgment(raw, evidence_pack=pack, reviewer=ReviewerResult(disposition="pass"))

    raw["spy_20d"]["direction"] = "no_call"
    judgment = validate_daily_macro_judgment(
        raw,
        evidence_pack=pack,
        reviewer=ReviewerResult(disposition="pass"),
    )
    assert judgment.data_health == "degraded"
    assert judgment.spy_20d.direction.value == "no_call"


def test_reference_closure_reviewer_and_renderer_are_hard_gates() -> None:
    pack = _pack()
    raw = _judgment_payload(pack)
    raw["counterevidence"][0]["evidence_refs"] = ["missing:ref"]
    with pytest.raises(JudgmentGateError, match="unknown_evidence_refs"):
        validate_daily_macro_judgment(raw, evidence_pack=pack, reviewer=ReviewerResult(disposition="pass"))

    raw = _judgment_payload(pack)
    with pytest.raises(JudgmentGateError, match="reviewer_block"):
        validate_daily_macro_judgment(
            raw,
            evidence_pack=pack,
            reviewer=ReviewerResult(
                disposition="block",
                issues=({"code": "causal_jump", "message": "因果链未闭合"},),
            ),
        )

    judgment = validate_daily_macro_judgment(
        raw,
        evidence_pack=pack,
        reviewer=ReviewerResult(disposition="pass"),
    )
    memo = render_daily_macro_judgment_zh(judgment)
    assert "## SPY 5D / 20D" in memo
    assert "5D：range" in memo
    assert "20D：up" in memo
    assert "experimental / shadow research" in memo
    require_renderer_consistency(judgment, memo)
    with pytest.raises(JudgmentGateError, match="renderer_mismatch"):
        require_renderer_consistency(judgment, memo + "事后改写")


def test_session_calendar_covers_holiday_and_early_close() -> None:
    assert is_us_market_session(date(2026, 7, 2))
    assert not is_us_market_session(date(2026, 7, 3))
    assert market_session_advance(date(2026, 7, 2), sessions=1) == date(2026, 7, 6)
    assert market_session_advance(date(2026, 11, 25), sessions=1) == date(2026, 11, 27)
    assert market_session_close_ms(date(2026, 11, 27)) < market_session_close_ms(date(2026, 11, 30))
    with pytest.raises(ValueError, match="market_session_required"):
        market_session_close_ms(date(2026, 7, 4))


def _pack(*, health: EvidencePackHealth | None = None) -> MacroEvidencePack:
    evidence = MacroEvidenceItem(
        evidence_ref="macro:asset:spy:2026-07-02:test",
        page_id="cross_asset",
        source_name="test",
        concept_key="asset:spy",
        series_key="test:SPY",
        observed_at=SESSION,
        available_at_ms=CUTOFF_MS,
        availability=EvidenceAvailability.SESSION_CLOSE,
        source_timestamp=SESSION.isoformat(),
        ingested_at_ms=CUTOFF_MS + 1,
        data_quality="ok",
        selection_rule="session_close_market_fact",
        content_hash="a" * 64,
        content={"value_numeric": "620.25", "unit": "price"},
    )
    return MacroEvidencePack(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        sealed_at_ms=CUTOFF_MS + 10,
        projection_version="macro_decision_v2",
        pages={
            "overview": {"page_id": "overview"},
            "cross_asset": {"page_id": "cross_asset"},
            "rates_inflation": {"page_id": "rates_inflation"},
            "growth_labor": {"page_id": "growth_labor"},
            "liquidity_funding": {"page_id": "liquidity_funding"},
            "credit": {"page_id": "credit"},
        },
        evidence=(evidence,),
        health=health or EvidencePackHealth(status="ready"),
    )


def _judgment_payload(pack: MacroEvidencePack) -> dict[str, object]:
    ref = next(iter(pack.evidence_refs))
    return {
        "experimental_marker": "experimental_shadow_research",
        "session_date": SESSION.isoformat(),
        "market_cutoff_ms": CUTOFF_MS,
        "data_health": "ready",
        "macro_state": "增长放缓但信用与流动性尚未形成系统性压力。",
        "pressures": [
            {
                "axis": "growth",
                "state": "easing",
                "mechanism": "增长动能边际回落，盈利预期面临温和压力。",
                "evidence_refs": [ref],
            }
        ],
        "spy_5d": {
            "horizon_sessions": 5,
            "direction": "range",
            "thesis": "短期交叉资产信号相互抵消。",
            "evidence_refs": [ref],
        },
        "spy_20d": {
            "horizon_sessions": 20,
            "direction": "up",
            "thesis": "信用稳定仍支持中期风险偏好。",
            "evidence_refs": [ref],
        },
        "counterevidence": [{"statement": "增长动能仍可能进一步走弱。", "evidence_refs": [ref]}],
        "audit_versions": {
            "evidence_pack_hash": pack.pack_hash,
            "schema_version": "daily_macro_judgment_v1",
            "prompt_version": "macro_analyst_v1",
            "workflow_version": "deepagents_analyst_reviewer_v1",
        },
    }
