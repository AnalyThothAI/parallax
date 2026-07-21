from __future__ import annotations

from typing import Any

from parallax.domains.token_intel._constants import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DECISIONS,
    TOKEN_RADAR_FACTOR_FAMILIES,
)

TOKEN_FACTOR_SNAPSHOT_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "subject",
        "market",
        "gates",
        "data_health",
        "families",
        "normalization",
        "composite",
        "provenance",
    }
)
TOKEN_FACTOR_SNAPSHOT_PROVENANCE_KEYS = frozenset({"source_event_ids", "computed_at_ms"})
TOKEN_FACTOR_SNAPSHOT_SUBJECT_KEYS = frozenset(
    {
        "target_type",
        "target_id",
        "symbol",
        "target_market_type",
        "chain",
        "address",
        "pricefeed_id",
    }
)
TOKEN_FACTOR_SNAPSHOT_MARKET_REQUIRED_KEYS = frozenset({"event_anchor", "decision_latest", "readiness"})
TOKEN_FACTOR_SNAPSHOT_MARKET_OPTIONAL_KEYS = frozenset({"capture_method", "capture_reason", "tick_lag_ms"})
TOKEN_FACTOR_SNAPSHOT_MARKET_KEYS = (
    TOKEN_FACTOR_SNAPSHOT_MARKET_REQUIRED_KEYS | TOKEN_FACTOR_SNAPSHOT_MARKET_OPTIONAL_KEYS
)
TOKEN_FACTOR_SNAPSHOT_MARKET_READINESS_KEYS = frozenset(
    {"anchor_status", "latest_status", "dex_floor_status", "missing_fields", "stale_fields"}
)
TOKEN_FACTOR_SNAPSHOT_FAMILY_KEYS = frozenset(
    {
        "raw_score",
        "score",
        "weight",
        "data_health",
        "facts",
        "factors",
    }
)
TOKEN_FACTOR_SNAPSHOT_GATES_KEYS = frozenset(
    {"eligible_for_high_alert", "max_decision", "blocked_reasons", "risk_reasons"}
)
TOKEN_FACTOR_SNAPSHOT_NORMALIZATION_KEYS = frozenset(
    {"status", "cohort_status", "cohort", "factor_ranks", "alpha_rank"}
)
TOKEN_FACTOR_SNAPSHOT_COMPOSITE_KEYS = frozenset(
    {"raw_alpha_score", "rank_score", "family_scores", "recommended_decision"}
)


def require_token_factor_snapshot(value: Any, *, field_name: str = "factor_snapshot") -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field_name} must be a non-empty factor snapshot")
    if value.get("schema_version") != TOKEN_FACTOR_SNAPSHOT_VERSION:
        raise ValueError(f"{field_name}.schema_version must be {TOKEN_FACTOR_SNAPSHOT_VERSION}")
    keys = set(value)
    missing = sorted(TOKEN_FACTOR_SNAPSHOT_TOP_LEVEL_KEYS - keys)
    if missing:
        raise ValueError(f"{field_name}.{missing[0]} is required")
    extra = sorted(keys - TOKEN_FACTOR_SNAPSHOT_TOP_LEVEL_KEYS)
    if extra:
        raise ValueError(f"{field_name}.{extra[0]} is not allowed")

    for key in ("subject", "market", "gates", "data_health", "normalization", "composite", "provenance"):
        _required_dict(value.get(key), field_name=f"{field_name}.{key}")

    subject = _required_dict(value.get("subject"), field_name=f"{field_name}.subject")
    _require_exact_keys(
        subject,
        allowed=TOKEN_FACTOR_SNAPSHOT_SUBJECT_KEYS,
        field_name=f"{field_name}.subject",
    )

    gates = _required_dict(value.get("gates"), field_name=f"{field_name}.gates")
    _require_exact_keys(
        gates,
        allowed=TOKEN_FACTOR_SNAPSHOT_GATES_KEYS,
        field_name=f"{field_name}.gates",
    )
    if not isinstance(gates.get("eligible_for_high_alert"), bool):
        raise ValueError(f"{field_name}.gates.eligible_for_high_alert is required")
    _require_decision(gates.get("max_decision"), field_name=f"{field_name}.gates.max_decision")
    for key in ("blocked_reasons", "risk_reasons"):
        _require_string_list(gates.get(key), field_name=f"{field_name}.gates.{key}")

    composite = _required_dict(value.get("composite"), field_name=f"{field_name}.composite")
    _require_exact_keys(
        composite,
        allowed=TOKEN_FACTOR_SNAPSHOT_COMPOSITE_KEYS,
        field_name=f"{field_name}.composite",
    )
    for key in ("raw_alpha_score", "rank_score"):
        if not _is_json_number(composite.get(key)):
            raise ValueError(f"{field_name}.composite.{key} is required")
    family_scores = _required_dict(
        composite.get("family_scores"),
        field_name=f"{field_name}.composite.family_scores",
    )
    _require_exact_keys(
        family_scores,
        allowed=frozenset(TOKEN_RADAR_FACTOR_FAMILIES),
        field_name=f"{field_name}.composite.family_scores",
    )
    for family, score in family_scores.items():
        if not _is_json_number(score):
            raise ValueError(f"{field_name}.composite.family_scores.{family} is required")
    _require_decision(
        composite.get("recommended_decision"),
        field_name=f"{field_name}.composite.recommended_decision",
    )

    normalization = _required_dict(value.get("normalization"), field_name=f"{field_name}.normalization")
    _require_exact_keys(
        normalization,
        allowed=TOKEN_FACTOR_SNAPSHOT_NORMALIZATION_KEYS,
        field_name=f"{field_name}.normalization",
    )
    for key in ("status", "cohort_status"):
        if not isinstance(normalization.get(key), str) or not normalization.get(key):
            raise ValueError(f"{field_name}.normalization.{key} is required")
    _required_dict(normalization.get("cohort"), field_name=f"{field_name}.normalization.cohort")
    factor_ranks = _required_dict(
        normalization.get("factor_ranks"),
        field_name=f"{field_name}.normalization.factor_ranks",
    )
    _require_exact_keys(
        factor_ranks,
        allowed=frozenset(TOKEN_RADAR_FACTOR_FAMILIES),
        field_name=f"{field_name}.normalization.factor_ranks",
    )
    for family, rank in factor_ranks.items():
        if rank is not None and not _is_json_number(rank):
            raise ValueError(f"{field_name}.normalization.factor_ranks.{family} must be a number or null")
    alpha_rank = normalization.get("alpha_rank")
    if alpha_rank is not None and not _is_json_number(alpha_rank):
        raise ValueError(f"{field_name}.normalization.alpha_rank must be a number or null")

    market = _required_dict(value.get("market"), field_name=f"{field_name}.market")
    _require_allowed_keys(
        market,
        required=TOKEN_FACTOR_SNAPSHOT_MARKET_REQUIRED_KEYS,
        allowed=TOKEN_FACTOR_SNAPSHOT_MARKET_KEYS,
        field_name=f"{field_name}.market",
    )
    for key in ("event_anchor", "decision_latest"):
        if market.get(key) is not None and not isinstance(market.get(key), dict):
            raise ValueError(f"{field_name}.market.{key} must be an object or null")
    readiness = _required_dict(market.get("readiness"), field_name=f"{field_name}.market.readiness")
    _require_exact_keys(
        readiness,
        allowed=TOKEN_FACTOR_SNAPSHOT_MARKET_READINESS_KEYS,
        field_name=f"{field_name}.market.readiness",
    )
    for key in ("missing_fields", "stale_fields"):
        if not isinstance(readiness.get(key), list):
            raise ValueError(f"{field_name}.market.readiness.{key} must be a list")

    provenance = _required_dict(value.get("provenance"), field_name=f"{field_name}.provenance")
    _require_exact_keys(
        provenance,
        allowed=TOKEN_FACTOR_SNAPSHOT_PROVENANCE_KEYS,
        field_name=f"{field_name}.provenance",
    )
    source_event_ids = provenance.get("source_event_ids")
    if (
        not isinstance(source_event_ids, list)
        or not source_event_ids
        or any(not isinstance(item, str) or not item for item in source_event_ids)
    ):
        raise ValueError(f"{field_name}.provenance.source_event_ids is required")
    if not _is_json_number(provenance.get("computed_at_ms")):
        raise ValueError(f"{field_name}.provenance.computed_at_ms is required")

    families = value.get("families")
    if not isinstance(families, dict):
        raise ValueError(f"{field_name}.families is required")
    family_keys = set(str(key) for key in families)
    allowed_families = set(TOKEN_RADAR_FACTOR_FAMILIES)
    extra_families = sorted(family_keys - allowed_families)
    if extra_families:
        raise ValueError(f"{field_name}.families.{extra_families[0]} is not allowed")
    missing_families = sorted(allowed_families - family_keys)
    if missing_families:
        raise ValueError(f"{field_name}.families.{missing_families[0]} is required")
    for family in TOKEN_RADAR_FACTOR_FAMILIES:
        family_block = _required_dict(families.get(family), field_name=f"{field_name}.families.{family}")
        _require_exact_keys(
            family_block,
            allowed=TOKEN_FACTOR_SNAPSHOT_FAMILY_KEYS,
            field_name=f"{field_name}.families.{family}",
        )
        for score_key in ("raw_score", "score", "weight"):
            if not _is_json_number(family_block.get(score_key)):
                raise ValueError(f"{field_name}.families.{family}.{score_key} is required")
        if not isinstance(family_block.get("data_health"), str) or not family_block.get("data_health"):
            raise ValueError(f"{field_name}.families.{family}.data_health is required")
        _required_dict(family_block.get("facts"), field_name=f"{field_name}.families.{family}.facts")
        _required_dict(family_block.get("factors"), field_name=f"{field_name}.families.{family}.factors")

    return value


def is_token_factor_snapshot(value: Any) -> bool:
    try:
        require_token_factor_snapshot(value)
    except ValueError:
        return False
    return True


def _required_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} is required")
    return value


def _require_exact_keys(value: dict[str, Any], *, allowed: frozenset[str], field_name: str) -> None:
    keys = set(value)
    missing = sorted(allowed - keys)
    if missing:
        raise ValueError(f"{field_name}.{missing[0]} is required")
    extra = sorted(keys - allowed)
    if extra:
        raise ValueError(f"{field_name}.{extra[0]} is not allowed")


def _require_allowed_keys(
    value: dict[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    field_name: str,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    if missing:
        raise ValueError(f"{field_name}.{missing[0]} is required")
    extra = sorted(keys - allowed)
    if extra:
        raise ValueError(f"{field_name}.{extra[0]} is not allowed")


def _require_decision(value: Any, *, field_name: str) -> None:
    if not isinstance(value, str) or value not in TOKEN_RADAR_DECISIONS:
        raise ValueError(f"{field_name} is required")


def _is_json_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_string_list(value: Any, *, field_name: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must be a string list")
