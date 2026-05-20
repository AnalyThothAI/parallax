from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

EPOCH_POLICY_VERSION = "token-narrative-epoch-v1"
DIGEST_WINDOWS = frozenset({"1h", "4h", "24h"})

EpochDecisionReason = Literal[
    "unsupported_window",
    "no_ready_digest",
    "no_material_delta",
    "material_delta_due",
    "ttl_refresh_due",
    "semantic_pending",
    "insufficient",
]


@dataclass(frozen=True, slots=True)
class NarrativeEpochDecision:
    reason: EpochDecisionReason
    should_refresh: bool
    should_write_status_digest: bool
    next_due_at_ms: int
    epoch_policy_version: str = EPOCH_POLICY_VERSION
    refresh_reason: str | None = None


@dataclass(frozen=True, slots=True)
class NarrativeEpochThreshold:
    min_new_sources: int
    min_new_authors: int
    max_epoch_age_ms: int


DEFAULT_THRESHOLDS = {
    "1h": NarrativeEpochThreshold(min_new_sources=3, min_new_authors=2, max_epoch_age_ms=15 * 60 * 1000),
    "4h": NarrativeEpochThreshold(min_new_sources=5, min_new_authors=2, max_epoch_age_ms=30 * 60 * 1000),
    "24h": NarrativeEpochThreshold(min_new_sources=8, min_new_authors=3, max_epoch_age_ms=2 * 60 * 60 * 1000),
}


class NarrativeEpochPolicy:
    def __init__(
        self,
        *,
        thresholds: Mapping[str, NarrativeEpochThreshold] | None = None,
        stance_mix_change_threshold: float = 0.20,
        attention_mix_change_threshold: float = 0.20,
        price_move_refresh_pct: float = 12.0,
    ) -> None:
        self.thresholds = dict(thresholds or DEFAULT_THRESHOLDS)
        self.stance_mix_change_threshold = float(stance_mix_change_threshold)
        self.attention_mix_change_threshold = float(attention_mix_change_threshold)
        self.price_move_refresh_pct = float(price_move_refresh_pct)

    def evaluate(
        self,
        *,
        admission: Mapping[str, Any],
        last_ready_digest: Mapping[str, Any] | None,
        semantic_coverage: Mapping[str, Any],
        market_context: Mapping[str, Any] | None,
        now_ms: int,
    ) -> NarrativeEpochDecision:
        window = str(admission.get("window") or "")
        if window not in DIGEST_WINDOWS:
            return NarrativeEpochDecision(
                reason="unsupported_window",
                should_refresh=False,
                should_write_status_digest=False,
                next_due_at_ms=int(now_ms) + 24 * 60 * 60 * 1000,
            )

        threshold = self.thresholds[window]
        next_due = int(now_ms) + threshold.max_epoch_age_ms
        source_count = _int_value(semantic_coverage.get("source_event_count"), admission.get("source_event_count"))
        authors = _author_count(admission)
        pending = (
            _int_value(semantic_coverage.get("missing_semantic_count"))
            + _int_value(semantic_coverage.get("pending_semantic_count"))
            + _int_value(semantic_coverage.get("retryable_semantic_count"))
        )

        if last_ready_digest is None:
            if source_count <= 0 or authors <= 0:
                return NarrativeEpochDecision(
                    reason="insufficient",
                    should_refresh=False,
                    should_write_status_digest=True,
                    next_due_at_ms=next_due,
                )
            if pending > 0:
                return NarrativeEpochDecision(
                    reason="semantic_pending",
                    should_refresh=False,
                    should_write_status_digest=True,
                    next_due_at_ms=min(next_due, int(now_ms) + 60_000),
                )
            return NarrativeEpochDecision(
                reason="no_ready_digest",
                should_refresh=True,
                should_write_status_digest=False,
                next_due_at_ms=next_due,
                refresh_reason="initial_ready",
            )

        if _ttl_expired(last_ready_digest, now_ms=int(now_ms)):
            return NarrativeEpochDecision(
                reason="ttl_refresh_due",
                should_refresh=True,
                should_write_status_digest=False,
                next_due_at_ms=next_due,
                refresh_reason="ttl_refresh_due",
            )

        delta_sources = _source_delta_count(admission, last_ready_digest)
        delta_authors = _author_delta_count(admission, last_ready_digest)
        price_move_pct = abs(_float_value((market_context or {}).get("price_move_pct")))
        if (
            delta_sources >= threshold.min_new_sources
            or delta_authors >= threshold.min_new_authors
            or price_move_pct >= self.price_move_refresh_pct
        ):
            return NarrativeEpochDecision(
                reason="material_delta_due",
                should_refresh=True,
                should_write_status_digest=False,
                next_due_at_ms=next_due,
                refresh_reason="material_delta_due",
            )

        return NarrativeEpochDecision(
            reason="no_material_delta",
            should_refresh=False,
            should_write_status_digest=False,
            next_due_at_ms=next_due,
        )


def _ttl_expired(digest: Mapping[str, Any], *, now_ms: int) -> bool:
    display_current_until_ms = digest.get("display_current_until_ms")
    return display_current_until_ms is not None and _int_value(display_current_until_ms) < now_ms


def _source_delta_count(admission: Mapping[str, Any], digest: Mapping[str, Any]) -> int:
    admission_ids = _string_set(admission.get("source_event_ids"), admission.get("source_event_ids_json"))
    digest_ids = _string_set(digest.get("source_event_ids"), digest.get("source_event_ids_json"))
    if admission_ids:
        return len(admission_ids - digest_ids)
    return max(_int_value(admission.get("source_event_count")) - _int_value(digest.get("source_event_count")), 0)


def _author_delta_count(admission: Mapping[str, Any], digest: Mapping[str, Any]) -> int:
    admission_authors = _string_set(
        admission.get("author_ids"),
        admission.get("independent_author_ids"),
        admission.get("source_author_ids"),
    )
    digest_authors = _string_set(
        digest.get("author_ids"),
        digest.get("independent_author_ids"),
        digest.get("source_author_ids"),
    )
    if admission_authors:
        return len(admission_authors - digest_authors)
    return max(_author_count(admission) - _author_count(digest), 0)


def _author_count(payload: Mapping[str, Any]) -> int:
    authors = _string_set(
        payload.get("author_ids"),
        payload.get("independent_author_ids"),
        payload.get("source_author_ids"),
    )
    if authors:
        return len(authors)
    return _int_value(
        payload.get("independent_author_count"),
        payload.get("author_count"),
        payload.get("source_author_count"),
    )


def _string_set(*values: Any) -> set[str]:
    result: set[str] = set()
    for value in values:
        if isinstance(value, str):
            parsed_value = _parse_json_sequence(value)
            if parsed_value is None:
                result.add(value)
            else:
                result.update(str(item) for item in parsed_value if item is not None)
        elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
            result.update(str(item) for item in value if item is not None)
    return result


def _parse_json_sequence(value: str) -> list[Any] | tuple[Any, ...] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (list, tuple)):
        return parsed
    return None


def _int_value(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
