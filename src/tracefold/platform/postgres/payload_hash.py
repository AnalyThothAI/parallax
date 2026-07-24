from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from math import isfinite
from typing import Any

PAYLOAD_HASH_PREFIX = "sha256:"
PAYLOAD_HASH_HEX_LENGTH = 64
DIRTY_TARGET_PAYLOAD_LIFECYCLE_FIELDS = frozenset(
    {
        "dirty_at_ms",
        "due_at_ms",
        "leased_until_ms",
        "lease_owner",
        "attempt_count",
        "updated_at_ms",
        "first_dirty_at_ms",
        "last_error",
        "priority",
    }
)


def stable_current_payload_hash(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError(f"current payload hash payload must be mapping: {payload}")
    _validate_payload_hash_keys(payload)
    _validate_payload_hash_values(payload)
    encoded = json.dumps(
        _json_ready(dict(payload)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return PAYLOAD_HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def stable_dirty_target_payload_hash(
    payload: Mapping[str, Any],
    *,
    lifecycle_fields: Iterable[str] = DIRTY_TARGET_PAYLOAD_LIFECYCLE_FIELDS,
) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError(f"current payload hash payload must be mapping: {payload}")
    lifecycle_field_set = frozenset(lifecycle_fields)
    stable_payload: dict[str, Any] = {}
    for key, value in payload.items():
        if type(key) is not str:
            raise ValueError(f"current payload hash payload has non-string keys: {(key,)}")
        if key in lifecycle_field_set:
            continue
        stable_payload[key] = value
    return stable_current_payload_hash(stable_payload)


def _validate_payload_hash_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        non_string_keys = tuple(key for key in value if type(key) is not str)
        if non_string_keys:
            raise ValueError(f"current payload hash payload has non-string keys: {non_string_keys}")
        for inner in value.values():
            _validate_payload_hash_keys(inner)
        return
    if isinstance(value, tuple | list):
        for inner in value:
            _validate_payload_hash_keys(inner)


def _validate_payload_hash_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for inner in value.values():
            _validate_payload_hash_values(inner)
        return
    if isinstance(value, tuple | list):
        for inner in value:
            _validate_payload_hash_values(inner)
        return
    if isinstance(value, set | frozenset):
        raise ValueError(f"current payload hash payload has unsupported containers: {value}")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"current payload hash payload has non-finite numbers: {value}")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(f"current payload hash payload has non-finite numbers: {value}")
    if value is None or isinstance(value, str | int | float | Decimal | date | datetime | time):
        return
    raise ValueError(f"current payload hash payload has unsupported values: {value}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return value
