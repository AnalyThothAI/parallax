from __future__ import annotations

import math
from typing import Any

SUPPORTED_WINDOW = "1h"
HOT_RANK_LIMIT = 50
MIN_RANK_SCORE = 30.0

UNSUPPORTED_WINDOW_REASON = "narrative_not_supported_for_window"
MISSING_ADMISSION_REASON = "no_current_admission"
OUT_OF_FRONTIER_REASON = "out_of_frontier"


def narrative_admission_from_current_row(
    row: dict[str, Any] | None,
    *,
    window: str,
) -> dict[str, Any]:
    """Derive the public admission contract from one Token Radar current row."""
    if window != SUPPORTED_WINDOW:
        return _missing_admission(
            reason=UNSUPPORTED_WINDOW_REASON,
            display_status="unsupported_window",
        )
    if row is None:
        return _missing_admission(
            reason=MISSING_ADMISSION_REASON,
            display_status="not_ready",
        )

    rank = _positive_int(row.get("rank"), field="rank")
    rank_score = _finite_number(row.get("rank_score"), field="rank_score")
    source_event_ids = _string_list(row.get("source_event_ids_json"), field="source_event_ids_json")
    computed_at_ms = _positive_int(row.get("computed_at_ms"), field="computed_at_ms")
    independent_authors = _independent_authors(row)

    if rank <= HOT_RANK_LIMIT:
        status = "admitted"
        reason = "hot_rank"
        display_status = "current"
        is_current = True
        data_gaps: list[dict[str, str]] = []
    elif rank_score >= MIN_RANK_SCORE:
        status = "admitted"
        reason = "rank_score"
        display_status = "current"
        is_current = True
        data_gaps = []
    else:
        status = "suppressed"
        reason = OUT_OF_FRONTIER_REASON
        display_status = "out_of_frontier"
        is_current = False
        data_gaps = [{"reason": reason}]

    return {
        "status": status,
        "reason": reason,
        "is_current": is_current,
        "computed_at_ms": computed_at_ms,
        "currentness": {"display_status": display_status, "reason": reason},
        "coverage": {
            "source_mentions": len(source_event_ids),
            "independent_authors": independent_authors,
        },
        "data_gaps": data_gaps,
    }


def _missing_admission(*, reason: str, display_status: str) -> dict[str, Any]:
    return {
        "status": "missing",
        "reason": reason,
        "is_current": False,
        "computed_at_ms": None,
        "currentness": {"display_status": display_status, "reason": reason},
        "coverage": {"source_mentions": 0, "independent_authors": 0},
        "data_gaps": [{"reason": reason}],
    }


def _independent_authors(row: dict[str, Any]) -> int:
    snapshot = _mapping(row.get("factor_snapshot_json"), field="factor_snapshot_json")
    families = _mapping(snapshot.get("families"), field="factor_snapshot_json.families")
    propagation = _mapping(
        families.get("social_propagation"),
        field="factor_snapshot_json.families.social_propagation",
    )
    facts = _mapping(
        propagation.get("facts"),
        field="factor_snapshot_json.families.social_propagation.facts",
    )
    return _nonnegative_int(
        facts.get("independent_authors"),
        field="factor_snapshot_json.families.social_propagation.facts.independent_authors",
    )


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    return value


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    return value


def _positive_int(value: Any, *, field: str) -> int:
    parsed = _nonnegative_int(value, field=field)
    if parsed <= 0:
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    return parsed


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    return value


def _finite_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"token_radar_narrative_admission_current_row_invalid:{field}")
    return parsed


__all__ = ["narrative_admission_from_current_row"]
