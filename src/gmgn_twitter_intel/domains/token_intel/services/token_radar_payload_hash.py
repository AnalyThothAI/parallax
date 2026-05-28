from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

EPHEMERAL_FACTOR_SNAPSHOT_PATH = "factor_snapshot_json.provenance.computed_at_ms"


def canonical_token_radar_payload(payload: Any) -> Any:
    """Return JSON-ready Token Radar payload data for stable hashing."""
    raw = getattr(payload, "obj", payload)
    return _canonical_value(raw, factor_snapshot_root=_looks_like_factor_snapshot(raw))


def stable_token_radar_payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        canonical_token_radar_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_value(value: Any, *, factor_snapshot_root: bool = False) -> Any:
    raw = getattr(value, "obj", value)
    if isinstance(raw, Decimal):
        return float(raw)
    if isinstance(raw, Mapping):
        is_snapshot_root = factor_snapshot_root or _looks_like_factor_snapshot(raw)
        out: dict[str, Any] = {}
        for key, item in raw.items():
            key_str = str(key)
            if is_snapshot_root and key_str == "provenance":
                out[key_str] = _canonical_factor_snapshot_provenance(item)
            elif key_str == "factor_snapshot_json":
                out[key_str] = _canonical_value(item, factor_snapshot_root=True)
            else:
                out[key_str] = _canonical_value(item)
        return out
    if isinstance(raw, list | tuple):
        return [_canonical_value(item) for item in raw]
    if isinstance(raw, set):
        return [_canonical_value(item) for item in sorted(raw, key=repr)]
    return raw


def _canonical_factor_snapshot_provenance(value: Any) -> Any:
    raw = getattr(value, "obj", value)
    if not isinstance(raw, Mapping):
        return _canonical_value(raw)
    return {str(key): _canonical_value(item) for key, item in raw.items() if str(key) != "computed_at_ms"}


def _looks_like_factor_snapshot(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    schema_version = value.get("schema_version")
    if isinstance(schema_version, str) and schema_version.startswith("token_factor_snapshot"):
        return True
    return "provenance" in value and any(key in value for key in ("families", "composite", "subject"))


__all__ = ["canonical_token_radar_payload", "stable_token_radar_payload_hash"]
