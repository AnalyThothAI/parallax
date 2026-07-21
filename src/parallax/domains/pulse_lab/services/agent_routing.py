from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import DecisionRoute


def route_decision_context(context: dict[str, Any]) -> DecisionRoute:
    snapshot = _mapping(context.get("factor_snapshot"))
    subject = _mapping(snapshot.get("subject"))
    target_id = str(subject.get("target_id") or "").strip()
    if not target_id:
        return "research_only"
    target_market_type = str(subject.get("target_market_type") or "").strip().lower()
    if target_market_type in {"cex", "perp", "perpetual", "spot"}:
        return "cex"
    if target_market_type in {"dex", "meme", "new_pair", "pumpfun"}:
        return "meme"
    decision_latest = _mapping(_mapping(snapshot.get("market")).get("decision_latest"))
    if any(str(decision_latest.get(key) or "").strip() for key in ("venue_id", "pair_symbol")):
        return "cex"
    if decision_latest.get("open_interest_usd") is not None or decision_latest.get("funding_rate") is not None:
        return "cex"
    return "meme"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = ["route_decision_context"]
