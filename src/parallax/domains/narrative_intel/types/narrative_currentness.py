from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.narrative_intel.types.narrative_epoch_policy import (
    DIGEST_WINDOWS,
    EPOCH_POLICY_VERSION,
)

CURRENTNESS_STATUSES = ("current", "updating", "stale", "not_ready", "out_of_frontier", "unsupported_window")


def public_currentness(
    *,
    digest: dict[str, Any] | None,
    admission: dict[str, Any] | None,
    window: str,
    now_ms: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return the public currentness object required by API contracts."""
    if window and window not in DIGEST_WINDOWS:
        return _currentness_payload(
            display_status="unsupported_window",
            reason="unsupported_window",
            digest=digest,
            admission=admission,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )

    current_admission = admission if _is_current_admission(admission) else None
    if digest is None:
        return _currentness_payload(
            display_status="not_ready",
            reason=reason or "no_ready_digest",
            digest=None,
            admission=current_admission,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )

    if str(digest.get("status") or "") != "ready":
        return _currentness_payload(
            display_status="not_ready",
            reason=reason or _first_gap_reason(digest) or "no_ready_digest",
            digest=digest,
            admission=current_admission,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )

    if current_admission is None:
        return _currentness_payload(
            display_status="out_of_frontier",
            reason=reason or "not_in_current_frontier",
            digest=digest,
            admission=None,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )

    delta_sources = _source_delta_count(current_admission, digest)
    delta_authors = _author_delta_count(current_admission, digest)
    if _display_until_expired(digest, now_ms=now_ms):
        return _currentness_payload(
            display_status="stale",
            reason=reason or "ttl_refresh_due",
            digest=digest,
            admission=current_admission,
            delta_source_event_count=delta_sources,
            delta_independent_author_count=delta_authors,
        )

    ready_fingerprint = _clean(digest.get("source_fingerprint"))
    current_fingerprint = _clean(current_admission.get("source_fingerprint"))
    if ready_fingerprint and current_fingerprint and ready_fingerprint == current_fingerprint:
        return _currentness_payload(
            display_status="current",
            reason=reason or "fingerprint_match",
            digest=digest,
            admission=current_admission,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )
    if _source_ids(digest) and _source_ids(digest) == _source_ids(current_admission):
        return _currentness_payload(
            display_status="current",
            reason=reason or "fingerprint_match",
            digest=digest,
            admission=current_admission,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        )

    return _currentness_payload(
        display_status="updating",
        reason=reason or "digest_updating",
        digest=digest,
        admission=current_admission,
        delta_source_event_count=delta_sources,
        delta_independent_author_count=delta_authors,
    )


def narrative_delta_from_currentness(currentness: dict[str, Any]) -> dict[str, Any]:
    """Return Token Case top-level delta metadata derived from currentness."""
    delta_source_event_count = _int(currentness.get("delta_source_event_count"))
    delta_independent_author_count = _int(currentness.get("delta_independent_author_count"))
    return {
        "display_status": currentness.get("display_status") or "not_ready",
        "reason": currentness.get("reason"),
        "has_delta": delta_source_event_count > 0 or delta_independent_author_count > 0,
        "delta_source_event_count": delta_source_event_count,
        "delta_independent_author_count": delta_independent_author_count,
        "ready_source_event_count": _int(currentness.get("ready_source_event_count")),
        "current_source_event_count": _int(currentness.get("current_source_event_count")),
        "delta_since_ms": currentness.get("delta_since_ms"),
        "last_ready_computed_at_ms": currentness.get("last_ready_computed_at_ms"),
        "next_refresh_due_at_ms": currentness.get("next_refresh_due_at_ms"),
    }


def unsupported_digest_sentinel(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
) -> dict[str, Any]:
    """Return non-persisted 5m unsupported digest payload."""
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "schema_version": schema_version,
        "status": "pending",
        "is_current": False,
        "data_gaps_json": [{"reason": "narrative_not_supported_for_window"}],
        "semantic_coverage": 0.0,
        "source_event_count": 0,
        "labeled_event_count": 0,
        "independent_author_count": 0,
        "evidence_refs_json": [],
        "currentness": _currentness_payload(
            display_status="unsupported_window",
            reason="unsupported_window",
            digest=None,
            admission=None,
            delta_source_event_count=0,
            delta_independent_author_count=0,
        ),
    }


def _currentness_payload(
    *,
    display_status: str,
    reason: str,
    digest: Mapping[str, Any] | None,
    admission: Mapping[str, Any] | None,
    delta_source_event_count: int,
    delta_independent_author_count: int,
) -> dict[str, Any]:
    return {
        "display_status": display_status,
        "epoch_id": None if digest is None else digest.get("epoch_id"),
        "epoch_policy_version": (
            (digest or {}).get("epoch_policy_version")
            or (admission or {}).get("epoch_policy_version")
            or EPOCH_POLICY_VERSION
        ),
        "ready_source_fingerprint": None if digest is None else digest.get("source_fingerprint"),
        "current_source_fingerprint": None if admission is None else admission.get("source_fingerprint"),
        "ready_source_event_count": _source_count(digest),
        "current_source_event_count": _source_count(admission),
        "delta_source_event_count": max(0, int(delta_source_event_count)),
        "delta_independent_author_count": max(0, int(delta_independent_author_count)),
        "delta_since_ms": _delta_since_ms(digest, delta_source_event_count=delta_source_event_count),
        "last_ready_computed_at_ms": None if digest is None else _int_or_none(digest.get("computed_at_ms")),
        "next_refresh_due_at_ms": _next_refresh_due_at_ms(digest, admission),
        "reason": reason,
    }


def _is_current_admission(admission: Mapping[str, Any] | None) -> bool:
    return admission is not None and str(admission.get("status") or "admitted") == "admitted"


def _display_until_expired(digest: Mapping[str, Any], *, now_ms: int) -> bool:
    display_until = _int_or_none(digest.get("display_current_until_ms"))
    return display_until is not None and display_until < int(now_ms)


def _source_delta_count(admission: Mapping[str, Any], digest: Mapping[str, Any]) -> int:
    current_ids = _source_ids(admission)
    ready_ids = _source_ids(digest)
    if current_ids:
        return len(current_ids - ready_ids)
    return max(_source_count(admission) - _source_count(digest), 0)


def _author_delta_count(admission: Mapping[str, Any], digest: Mapping[str, Any]) -> int:
    current_authors = _string_set(
        admission.get("author_ids"),
        admission.get("independent_author_ids"),
        admission.get("source_author_ids"),
    )
    ready_authors = _string_set(
        digest.get("author_ids"),
        digest.get("independent_author_ids"),
        digest.get("source_author_ids"),
    )
    if current_authors:
        return len(current_authors - ready_authors)
    return max(_author_count(admission) - _author_count(digest), 0)


def _source_ids(payload: Mapping[str, Any] | None) -> set[str]:
    if payload is None:
        return set()
    return _string_set(payload.get("source_event_ids"), payload.get("source_event_ids_json"))


def _source_count(payload: Mapping[str, Any] | None) -> int:
    ids = _source_ids(payload)
    if ids:
        return len(ids)
    return _int((payload or {}).get("source_event_count"))


def _author_count(payload: Mapping[str, Any] | None) -> int:
    authors = _string_set(
        (payload or {}).get("author_ids"),
        (payload or {}).get("independent_author_ids"),
        (payload or {}).get("source_author_ids"),
    )
    if authors:
        return len(authors)
    return _int(
        (payload or {}).get("independent_author_count")
        or (payload or {}).get("author_count")
        or (payload or {}).get("source_author_count")
    )


def _string_set(*values: Any) -> set[str]:
    result: set[str] = set()
    for value in values:
        if value is None:
            continue
        decoded = _decode_sequence(value)
        if decoded is None:
            continue
        result.update(str(item) for item in decoded if str(item))
    return result


def _decode_sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return decoded if isinstance(decoded, Sequence) and not isinstance(decoded, (str, bytes, bytearray)) else None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def _delta_since_ms(
    digest: Mapping[str, Any] | None,
    *,
    delta_source_event_count: int,
) -> int | None:
    if digest is None or int(delta_source_event_count) <= 0:
        return None
    return _int_or_none(digest.get("source_window_end_ms")) or _int_or_none(digest.get("computed_at_ms"))


def _next_refresh_due_at_ms(digest: Mapping[str, Any] | None, admission: Mapping[str, Any] | None) -> int | None:
    return (
        _int_or_none((admission or {}).get("next_digest_due_at_ms"))
        or _int_or_none((digest or {}).get("display_current_until_ms"))
        or _int_or_none((digest or {}).get("expires_at_ms"))
    )


def _first_gap_reason(digest: Mapping[str, Any]) -> str | None:
    gaps = _decode_sequence(digest.get("data_gaps_json")) or []
    for gap in gaps:
        if isinstance(gap, Mapping) and gap.get("reason"):
            return str(gap["reason"])
    return None


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
