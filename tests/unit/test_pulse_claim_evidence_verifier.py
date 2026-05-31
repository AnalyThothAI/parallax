from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerifier


def test_unknown_ref_blocks_publish() -> None:
    packet = _packet()
    memo = _memo(bull_refs=("event:event-1", "metric:market:unknown"))
    decision = _decision("trade_candidate", supporting_refs=("event:event-1",))

    result = _verify(packet, memo, decision)

    assert result.valid is False
    assert result.unknown_ref_ids == ("metric:market:unknown",)
    assert result.display_status_if_failed == "hidden_invalid_output"


def test_event_id_only_final_decision_blocks_non_abstain_publish() -> None:
    packet = _packet()
    memo = _memo(bull_refs=("event:event-1",))
    decision = _decision("trade_candidate", supporting_refs=(), evidence_event_ids=("event-1",))

    result = _verify(packet, memo, decision)

    assert result.valid is False
    assert "final_decision.supporting_evidence_refs" in result.missing_required_ref_claims
    assert "event_id_only_final_decision" in result.unsupported_claims


def test_event_id_string_is_not_accepted_as_complete_evidence_ref() -> None:
    packet = _packet()
    memo = _memo(bull_refs=("event:event-1",))
    decision = _decision("trade_candidate", supporting_refs=("event-1",))

    result = _verify(packet, memo, decision)

    assert result.valid is False
    assert result.unknown_ref_ids == ("event-1",)


def test_complete_refs_allow_public_display() -> None:
    packet = _packet()
    memo = _memo(bull_refs=("event:event-1", "metric:market:price_usd"))
    decision = _decision("trade_candidate", supporting_refs=("event:event-1", "metric:market:price_usd"))

    result = _verify(packet, memo, decision)

    assert result.valid is True
    assert result.unknown_ref_ids == ()
    assert result.decision_status == "trade_candidate"
    assert result.display_status_if_failed is None


def test_abstain_can_use_gate_gap_ref_without_supporting_refs() -> None:
    packet = _packet()
    memo = SimpleNamespace(
        bull_claims=(),
        bear_claims=(),
        rebuttal_claims=(),
        data_gap_claims=(_claim(("gate:pulse:blocked_market_contract", "missing:market.price_usd")),),
    )
    decision = _decision("abstain", supporting_refs=(), data_gap_refs=("gate:pulse:blocked_market_contract",))

    result = _verify(packet, memo, decision, bear_memo=memo)

    assert result.valid is True
    assert result.decision_status == "abstain"


def _packet() -> SimpleNamespace:
    return SimpleNamespace(
        allowed_evidence_refs=[
            {"ref_id": "event:event-1", "ref_type": "event"},
            {"ref_id": "metric:market:price_usd", "ref_type": "metric"},
            {"ref_id": "identity:token", "ref_type": "identity"},
            {"ref_id": "gate:pulse:blocked_market_contract", "ref_type": "gate"},
        ]
    )


def _verify(
    packet: SimpleNamespace,
    signal_memo: SimpleNamespace,
    decision: SimpleNamespace,
    *,
    bear_memo: SimpleNamespace | None = None,
):
    return ClaimEvidenceVerifier().verify(packet, signal_memo, bear_memo or _bear_memo(), decision)


def _memo(*, bull_refs: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        bull_claims=(_claim(bull_refs),),
        bear_claims=(),
        rebuttal_claims=(),
        data_gap_claims=(),
    )


def _bear_memo() -> SimpleNamespace:
    return SimpleNamespace(risk_claims=(), missing_fact_impacts=())


def _claim(refs: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(claim="claim", evidence_refs=refs, stance="bull")


def _decision(
    recommendation: str,
    *,
    supporting_refs: tuple[str, ...],
    risk_refs: tuple[str, ...] = (),
    data_gap_refs: tuple[str, ...] = (),
    evidence_event_ids: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        recommendation=recommendation,
        supporting_evidence_refs=supporting_refs,
        risk_evidence_refs=risk_refs,
        data_gap_refs=data_gap_refs,
        evidence_event_ids=list(evidence_event_ids),
    )
