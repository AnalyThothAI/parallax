from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from parallax.domains.pulse_lab.services.evidence_completeness_gate import EvidenceCompletenessGate
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidenceDataGap, PulseEvidencePacket


def test_cex_with_baseline_only_is_partial_token_watch() -> None:
    packet = _packet(
        market=[
            {
                "route": "cex",
                "price_usd": 1.25,
                "pricefeed_id": "pricefeed:cex:binance:spot:TESTUSDT",
                "instrument_ref": "pricefeed:cex:binance:spot:TESTUSDT",
                "source_provider": "binance_cex_rest",
                "freshness_status": "fresh",
            }
        ],
    )

    result = EvidenceCompletenessGate().evaluate(packet)

    assert result.evidence_status == "partial"
    assert result.hard_blocked is False
    assert result.public_allowed is True
    assert result.max_decision_status == "token_watch"
    assert result.blocked_reason is None


def test_cex_with_ready_snapshot_derivatives_and_levels_passes_market_contract() -> None:
    packet = _packet(
        market=[
            {
                "route": "cex",
                "price_usd": 1.25,
                "pricefeed_id": "pricefeed:cex:binance:spot:TESTUSDT",
                "instrument_ref": "pricefeed:cex:binance:spot:TESTUSDT",
                "source_provider": "binance_cex_rest",
                "freshness_status": "fresh",
                "cex_snapshot": {"coinglass_status": "ready"},
                "derivatives": {"oi_change_pct_24h": 2.5, "cvd_delta_4h": -1000},
                "levels": [{"kind": "support", "price": 1.1}],
            }
        ],
        refs=[
            _ref("event:event-1", "event"),
            _ref("metric:cex:oi_change_pct_24h:TESTUSDT", "metric"),
            _ref("level:cex:TESTUSDT:support:1.1", "level"),
            _ref("identity:token", "identity"),
        ],
    )

    result = EvidenceCompletenessGate().evaluate(packet)

    assert result.evidence_status == "complete"
    assert result.hard_blocked is False
    assert result.max_decision_status == "trade_candidate"


def test_cex_with_no_fresh_price_is_blocked_market_contract() -> None:
    packet = _packet(
        market=[
            {
                "route": "cex",
                "pricefeed_id": "pricefeed:cex:binance:spot:TESTUSDT",
                "instrument_ref": "pricefeed:cex:binance:spot:TESTUSDT",
                "source_provider": "binance_cex_rest",
                "freshness_status": "stale",
            }
        ],
    )

    result = EvidenceCompletenessGate().evaluate(packet)

    assert result.evidence_status == "stale"
    assert result.hard_blocked is True
    assert result.blocked_reason == "blocked_market_contract"
    assert result.public_allowed is False


def test_packet_with_no_social_refs_is_blocked_social_contract() -> None:
    packet = _packet(social=[], refs=[_ref("metric:market:price_usd", "metric"), _ref("identity:token", "identity")])

    result = EvidenceCompletenessGate().evaluate(packet)

    assert result.evidence_status == "insufficient"
    assert result.hard_blocked is True
    assert result.blocked_reason == "blocked_social_contract"
    assert "event" in result.missing_ref_types


def test_unknown_route_social_only_is_hidden_abstain() -> None:
    packet = _packet(route="research_only", market=[], identity=[])

    result = EvidenceCompletenessGate().evaluate(packet)

    assert result.evidence_status == "insufficient"
    assert result.max_decision_status == "abstain"
    assert result.public_allowed is False
    assert result.display_status == "hidden_abstain"


def test_gate_json_serializes_packet_model_data_gaps() -> None:
    packet = _packet(
        market=[],
        data_gaps=(
            PulseEvidenceDataGap(
                gap_id="market_missing",
                ref_type="market",
                severity="high",
                summary_zh="缺少可引用市场证据",
            ),
        ),
    )

    result = EvidenceCompletenessGate().evaluate(packet)
    payload = result.to_json()

    json.dumps(payload, ensure_ascii=False)
    assert payload["data_gaps"][0]["gap_id"] == "market_missing"


def test_evidence_gate_requires_formal_pulse_evidence_packet_without_reflection() -> None:
    packet = SimpleNamespace(
        target_type="chain_token",
        allowed_evidence_refs=[
            _ref("event:event-1", "event"),
            _ref("metric:market:price_usd", "metric"),
            _ref("identity:token", "identity"),
        ],
        social_evidence={"event_refs": ("event:event-1",)},
        market_evidence={
            "route": "meme",
            "target_market_type": "dex",
            "price_usd": 1.0,
            "liquidity_usd": 1000.0,
            "pair_ref": "pair:solana:abc",
            "freshness_status": "fresh",
        },
        identity_evidence={"identity_refs": ("identity:token",)},
        data_gaps=(),
    )

    with pytest.raises(TypeError, match="pulse_evidence_packet_contract_required"):
        EvidenceCompletenessGate().evaluate(packet)


def _packet(
    *,
    route: str = "cex",
    social: list[dict[str, object]] | None = None,
    market: list[dict[str, object]] | None = None,
    identity: list[dict[str, object]] | None = None,
    refs: list[dict[str, object]] | None = None,
    data_gaps: tuple[PulseEvidenceDataGap, ...] = (),
) -> PulseEvidencePacket:
    social = [{"event_id": "event-1", "ref_id": "event:event-1"}] if social is None else social
    market = (
        [
            {
                "route": route,
                "price_usd": 1.25,
                "pricefeed_id": "pricefeed:cex:binance:spot:TESTUSDT",
                "instrument_ref": "pricefeed:cex:binance:spot:TESTUSDT",
                "source_provider": "binance_cex_rest",
                "freshness_status": "fresh",
            }
        ]
        if market is None
        else market
    )
    identity = [{"source_id": "identity:token", "ref_id": "identity:token"}] if identity is None else identity
    refs = refs or [
        _ref("event:event-1", "event"),
        _ref("metric:market:price_usd", "metric"),
        _ref("identity:token", "identity"),
    ]
    market_row = dict(market[0]) if market else {"route": "unknown", "target_market_type": "unknown"}
    market_route = str(market_row.get("route") or route)
    if market_route not in {"cex", "dex", "meme", "unknown"}:
        market_route = "unknown"
    target_market_type = str(market_row.get("target_market_type") or ("cex" if market_route == "cex" else "dex"))
    event_refs = tuple(str(row.get("ref_id") or row.get("event_id") or "") for row in social)
    identity_refs = tuple(str(row.get("ref_id") or row.get("source_id") or "") for row in identity)

    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        run_id="run-1",
        evidence_packet_hash="sha256:packet",
        schema_version="pulse_evidence_packet_v1",
        candidate_id="candidate-1",
        target_type="cex_token" if route == "cex" else "chain_token",
        target_id="TEST",
        symbol="TEST",
        window="1h",
        scope="default",
        snapshot_at_ms=1,
        source_event_ids=("event-1",),
        allowed_evidence_refs=refs,
        social_evidence={
            "status": "complete" if event_refs else "insufficient",
            "event_refs": tuple(ref for ref in event_refs if ref),
        },
        market_evidence={
            **market_row,
            "status": "complete" if market_row.get("price_usd") is not None else "insufficient",
            "route": market_route,
            "target_market_type": target_market_type,
        },
        identity_evidence={
            "status": "complete" if identity_refs else "insufficient",
            "identity_refs": tuple(ref for ref in identity_refs if ref),
        },
        quality_metrics={
            "ref_count": len(refs),
            "high_quality_ref_count": len(refs),
            "fresh_ref_count": len(refs),
        },
        data_gaps=data_gaps,
    )


def _ref(ref_id: str, ref_type: str) -> dict[str, object]:
    return {
        "ref_id": ref_id,
        "ref_type": ref_type,
        "source_table": "test",
        "source_id": ref_id,
        "observed_at_ms": 1,
        "summary_zh": ref_id,
        "quality": "high",
    }
