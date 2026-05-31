from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import DecisionRoute

_MEME_REQUIRED_FIELDS = ("price_usd", "holders", "liquidity_usd", "market_cap_usd", "volume_24h_usd")
_CEX_REQUIRED_FIELDS = ("price_usd", "venue_id")


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    route: DecisionRoute
    score: float
    hard_blocked: bool
    missing_fields: tuple[str, ...]
    stale_fields: tuple[str, ...]
    blockers: tuple[str, ...]


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


def compute_completeness(factor_snapshot: dict[str, Any], *, route: DecisionRoute) -> CompletenessResult:
    if route == "research_only":
        return CompletenessResult(
            route=route,
            score=0.0,
            hard_blocked=True,
            missing_fields=(),
            stale_fields=(),
            blockers=("research_only_no_resolved_target",),
        )

    snapshot = _mapping(factor_snapshot)
    market = _mapping(snapshot.get("market"))
    decision_latest = market.get("decision_latest")
    readiness = _mapping(market.get("readiness"))
    missing_fields = tuple(_stable_strings(readiness.get("missing_fields")))
    stale_fields = tuple(_stable_strings(readiness.get("stale_fields")))
    blockers: list[str] = []

    if not isinstance(decision_latest, dict) or not decision_latest:
        blockers.append("decision_latest_missing")
        decision_latest = {}

    required_fields = _CEX_REQUIRED_FIELDS if route == "cex" else _MEME_REQUIRED_FIELDS
    required_missing = tuple(
        field for field in required_fields if _is_missing_field(field, decision_latest, missing_fields, stale_fields)
    )
    available_count = len(required_fields) - len(required_missing)
    score = 0.0 if not required_fields else max(0.0, min(1.0, available_count / len(required_fields)))

    if route == "meme" and any(
        field in set((*missing_fields, *stale_fields)) for field in ("holders", "liquidity_usd", "market_cap_usd")
    ):
        blockers.append("dex_floor_unverified")

    cohort_blocker = _cohort_blocker(snapshot)
    if cohort_blocker:
        blockers.append(cohort_blocker)

    threshold = 0.8 if route == "cex" else 0.6
    if score < threshold and "data_completeness_below_hard_gate" not in blockers:
        blockers.append("data_completeness_below_hard_gate")

    return CompletenessResult(
        route=route,
        score=score,
        hard_blocked=bool(blockers),
        missing_fields=required_missing or missing_fields,
        stale_fields=stale_fields,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _cohort_blocker(snapshot: dict[str, Any]) -> str | None:
    normalization = _mapping(snapshot.get("normalization"))
    cohort_status = str(normalization.get("cohort_status") or "").strip()
    if cohort_status == "insufficient":
        return "cohort_insufficient"
    if cohort_status == "all_tied":
        return "cohort_all_tied"
    if str(normalization.get("status") or "").strip() == "no_signal" and cohort_status != "ready":
        return "cohort_no_signal"
    return None


def _is_missing_field(
    field: str,
    decision_latest: dict[str, Any],
    missing_fields: tuple[str, ...],
    stale_fields: tuple[str, ...],
) -> bool:
    if field in missing_fields or field in stale_fields:
        return True
    value = decision_latest.get(field)
    return value is None or value == ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stable_strings(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


__all__ = ["CompletenessResult", "compute_completeness", "route_decision_context"]
