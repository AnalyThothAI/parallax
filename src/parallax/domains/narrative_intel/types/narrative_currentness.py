from __future__ import annotations

from typing import Any


def unsupported_admission_sentinel(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
) -> dict[str, Any]:
    """Return the non-persisted admission coverage state for an unsupported window."""
    reason = "narrative_not_supported_for_window"
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "schema_version": schema_version,
        "status": "missing",
        "reason": reason,
        "is_current": False,
        "source_event_count": 0,
        "independent_author_count": 0,
        "computed_at_ms": None,
        "data_gaps_json": [{"reason": reason}],
        "currentness": {"display_status": "unsupported_window", "reason": reason},
    }


__all__ = ["unsupported_admission_sentinel"]
