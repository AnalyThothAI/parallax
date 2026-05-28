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
    return _canonical_value(raw, path=(), root_token_factor_snapshot=_is_token_factor_snapshot(raw))


def stable_token_radar_payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        canonical_token_radar_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_value(
    value: Any,
    *,
    path: tuple[str, ...],
    root_token_factor_snapshot: bool = False,
) -> Any:
    raw = getattr(value, "obj", value)
    if isinstance(raw, Decimal):
        return float(raw)
    if isinstance(raw, Mapping):
        out: dict[str, Any] = {}
        for key, item in raw.items():
            key_str = str(key)
            item_path = (*path, key_str)
            if _is_ephemeral_factor_snapshot_computed_at_path(
                item_path,
                root_token_factor_snapshot=root_token_factor_snapshot,
            ):
                continue
            out[key_str] = _canonical_value(
                item,
                path=item_path,
                root_token_factor_snapshot=root_token_factor_snapshot,
            )
        return out
    if isinstance(raw, list | tuple):
        return [
            _canonical_value(item, path=(*path, str(index)), root_token_factor_snapshot=root_token_factor_snapshot)
            for index, item in enumerate(raw)
        ]
    if isinstance(raw, set):
        return [
            _canonical_value(item, path=(*path, str(index)), root_token_factor_snapshot=root_token_factor_snapshot)
            for index, item in enumerate(sorted(raw, key=repr))
        ]
    return raw


def _is_ephemeral_factor_snapshot_computed_at_path(
    path: tuple[str, ...],
    *,
    root_token_factor_snapshot: bool,
) -> bool:
    if path == ("factor_snapshot_json", "provenance", "computed_at_ms"):
        return True
    return root_token_factor_snapshot and path == ("provenance", "computed_at_ms")


def _is_token_factor_snapshot(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    schema_version = value.get("schema_version")
    return isinstance(schema_version, str) and schema_version.startswith("token_factor_snapshot")


__all__ = ["canonical_token_radar_payload", "stable_token_radar_payload_hash"]
