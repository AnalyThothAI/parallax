from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import safe_float, safe_int


@dataclass(frozen=True, slots=True)
class PulseSourceQualityDecision:
    public_allowed: bool
    reasons: tuple[str, ...]
    metrics: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "public_allowed": bool(self.public_allowed),
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


class PulseSourceQuality:
    def evaluate(
        self,
        *,
        factor_snapshot: dict[str, Any],
        window: str,
        scope: str,
    ) -> PulseSourceQualityDecision:
        metrics = _source_metrics(factor_snapshot=factor_snapshot, window=window, scope=scope)
        reasons = _quality_reasons(metrics)
        return PulseSourceQualityDecision(
            public_allowed=not reasons,
            reasons=tuple(reasons),
            metrics=metrics,
        )


def _source_metrics(*, factor_snapshot: dict[str, Any], window: str, scope: str) -> dict[str, Any]:
    social_heat = _mapping(_nested(factor_snapshot, "families", "social_heat", "facts"))
    propagation = _mapping(_nested(factor_snapshot, "families", "social_propagation", "facts"))
    unique_authors = safe_int(social_heat.get("unique_authors"))
    independent_authors = safe_int(propagation.get("independent_authors"))
    source_weighted_effective_authors = safe_float(propagation.get("source_weighted_effective_authors"))
    effective_authors = safe_float(propagation.get("effective_authors"))
    effective_author_count = max(float(independent_authors), source_weighted_effective_authors, effective_authors)
    independent_author_count = max(unique_authors, independent_authors, int(effective_author_count))
    watched_mentions = safe_int(social_heat.get("watched_mentions"))
    top_author_share = safe_float(propagation.get("top_author_share"))
    duplicate_text_share = safe_float(propagation.get("duplicate_text_share"))
    return {
        "window": str(window or ""),
        "scope": str(scope or ""),
        "unique_authors": unique_authors,
        "independent_authors": independent_authors,
        "effective_author_count": round(effective_author_count, 3),
        "independent_author_count": independent_author_count,
        "watched_mentions": watched_mentions,
        "top_author_share": round(top_author_share, 6),
        "duplicate_text_share": round(duplicate_text_share, 6),
        "watched_only": watched_mentions > 0 and independent_author_count <= 1,
    }


def _quality_reasons(metrics: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if bool(metrics.get("watched_only")):
        reasons.append("watched_only_source")
    if safe_int(metrics.get("independent_author_count")) <= 1:
        reasons.append("single_author_source")
    if safe_float(metrics.get("effective_author_count")) < 2.0:
        reasons.append("low_effective_author_count")
    if safe_float(metrics.get("top_author_share")) >= 0.70:
        reasons.append("top_author_share_high")
    if safe_float(metrics.get("duplicate_text_share")) >= 0.50:
        reasons.append("duplicate_text_share_high")
    return list(dict.fromkeys(reasons))


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = ["PulseSourceQuality", "PulseSourceQualityDecision"]
