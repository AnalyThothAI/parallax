from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket


@dataclass(frozen=True, slots=True)
class EvidenceCompletenessGateResult:
    evidence_status: str
    hard_blocked: bool
    blocked_reason: str | None
    max_decision_status: str
    required_ref_ids: tuple[str, ...]
    missing_ref_types: tuple[str, ...]
    data_gaps: tuple[dict[str, Any], ...]
    public_allowed: bool
    display_status: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceCompletenessGate:
    def evaluate(self, packet: PulseEvidencePacket | Any) -> EvidenceCompletenessGateResult:
        refs = _refs(packet)
        ref_types = {str(ref.get("ref_type") or "") for ref in refs}
        social_evidence = _model_mapping(getattr(packet, "social_evidence", None))
        market = _model_items(getattr(packet, "market_evidence", ()))
        identity_evidence = _model_mapping(getattr(packet, "identity_evidence", None))
        route = _route(packet, market)

        if not social_evidence.get("event_refs") and "event" not in ref_types:
            return _blocked(
                evidence_status="insufficient",
                reason="blocked_social_contract",
                missing=("event",),
                data_gaps=_packet_gaps(packet, {"code": "social_missing"}),
            )
        if not (identity_evidence.get("identity_refs") or identity_evidence.get("profile_refs")) and (
            "identity" not in ref_types and "profile" not in ref_types
        ):
            return _blocked(
                evidence_status="insufficient",
                reason="blocked_identity_contract",
                missing=("identity",),
                data_gaps=_packet_gaps(packet, {"code": "identity_missing"}),
            )
        if route == "cex":
            market_status, reason, missing = _cex_market_status(market, ref_types)
        elif route in {"dex", "meme"}:
            market_status, reason, missing = _meme_market_status(market, ref_types)
        else:
            return _blocked(
                evidence_status="insufficient",
                reason="blocked_unknown_route",
                missing=("market",),
                data_gaps=_packet_gaps(packet, {"code": "unknown_route"}),
            )

        if reason:
            return _blocked(
                evidence_status=market_status,
                reason=reason,
                missing=missing,
                data_gaps=_packet_gaps(packet, {"code": reason}),
            )
        status = "complete" if market_status == "complete" else "partial"
        return EvidenceCompletenessGateResult(
            evidence_status=status,
            hard_blocked=False,
            blocked_reason=None,
            max_decision_status="trade_candidate" if status == "complete" else "token_watch",
            required_ref_ids=tuple(sorted(_required_ref_ids(refs))),
            missing_ref_types=tuple(),
            data_gaps=tuple(_packet_gaps(packet)),
            public_allowed=True,
            display_status="display_trade_candidate" if status == "complete" else "display_token_watch",
        )


def _cex_market_status(market: list[dict[str, Any]], ref_types: set[str]) -> tuple[str, str | None, tuple[str, ...]]:
    partial_seen = False
    for row in market:
        has_price = row.get("price_usd") is not None and str(row.get("freshness_status") or "fresh") == "fresh"
        has_source = bool(row.get("source_provider"))
        has_instrument = bool(row.get("instrument_ref") or row.get("pricefeed_id"))
        if has_price and has_source and has_instrument and ("metric" in ref_types or "market" in ref_types):
            derivatives = _mapping(row.get("derivatives"))
            levels = _items(row.get("levels"))
            snapshot = _mapping(row.get("cex_snapshot"))
            coinglass_ready = str(snapshot.get("coinglass_status") or row.get("coinglass_status") or "") == "ready"
            if coinglass_ready and (derivatives or levels or "level" in ref_types):
                return "complete", None, tuple()
            partial_seen = True
    if partial_seen:
        return "partial", None, tuple()
    stale_seen = any(str(row.get("freshness_status") or "") == "stale" for row in market)
    return ("stale" if stale_seen else "insufficient"), "blocked_market_contract", ("metric",)


def _meme_market_status(market: list[dict[str, Any]], ref_types: set[str]) -> tuple[str, str | None, tuple[str, ...]]:
    for row in market:
        has_price = row.get("price_usd") is not None and str(row.get("freshness_status") or "fresh") == "fresh"
        has_liquidity = row.get("liquidity_usd") is not None
        has_pair = bool(row.get("pair_ref") or row.get("instrument_ref") or row.get("pricefeed_id"))
        if has_price and has_liquidity and has_pair and "metric" in ref_types:
            return "complete", None, tuple()
        if has_price and has_pair and "metric" in ref_types:
            return "partial", None, tuple()
    stale_seen = any(str(row.get("freshness_status") or "") == "stale" for row in market)
    return ("stale" if stale_seen else "insufficient"), "blocked_market_contract", ("metric",)


def _blocked(
    *,
    evidence_status: str,
    reason: str,
    missing: tuple[str, ...],
    data_gaps: list[dict[str, Any]],
) -> EvidenceCompletenessGateResult:
    return EvidenceCompletenessGateResult(
        evidence_status=evidence_status,
        hard_blocked=True,
        blocked_reason=reason,
        max_decision_status="abstain",
        required_ref_ids=tuple(),
        missing_ref_types=missing,
        data_gaps=tuple(data_gaps),
        public_allowed=False,
        display_status="hidden_abstain" if evidence_status in {"insufficient", "stale"} else "hidden_invalid_output",
    )


def _route(packet: Any, market: list[dict[str, Any]]) -> str:
    for row in market:
        route = str(row.get("route") or "").lower()
        market_type = str(row.get("target_market_type") or "").lower()
        if route in {"cex", "dex", "meme", "research_only", "unknown"}:
            return route
        if market_type in {"cex", "spot", "perp", "perpetual"}:
            return "cex"
        if market_type in {"dex", "meme"}:
            return "meme"
    target_type = str(getattr(packet, "target_type", "") or "").lower()
    if "cex" in target_type:
        return "cex"
    if market:
        return "meme"
    return "research_only"


def _required_ref_ids(refs: list[dict[str, Any]]) -> list[str]:
    return [str(ref.get("ref_id")) for ref in refs if str(ref.get("ref_id") or "").strip()]


def _refs(packet: Any) -> list[dict[str, Any]]:
    return [_model_mapping(ref) for ref in _items(getattr(packet, "allowed_evidence_refs", ()))]


def _packet_gaps(packet: Any, fallback: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    gaps = [_model_mapping(gap) for gap in _items(getattr(packet, "data_gaps", ()))]
    gaps = [gap for gap in gaps if gap]
    if gaps:
        return gaps
    return [fallback] if fallback is not None else []


def _items(value: Any) -> list[Any]:
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _model_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list | tuple | set):
        return [_model_mapping(item) for item in value]
    mapped = _model_mapping(value)
    return [mapped] if mapped else []


def _model_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return cast(dict[str, Any], model_dump(mode="json"))
    if value is not None and hasattr(value, "__dict__"):
        return {str(key): item for key, item in vars(value).items()}
    return {}


__all__ = ["EvidenceCompletenessGate", "EvidenceCompletenessGateResult"]
