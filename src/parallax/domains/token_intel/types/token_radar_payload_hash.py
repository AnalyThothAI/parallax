from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash


def canonical_token_radar_payload(payload: Any) -> Any:
    """Return Token Radar payload data with product-ephemeral fields removed."""
    raw = _unwrap_jsonb(payload)
    return _canonical_value(raw, path=(), root_token_factor_snapshot=_is_token_factor_snapshot(raw))


def stable_token_radar_payload_hash(payload: Any) -> str:
    return stable_current_payload_hash(canonical_token_radar_payload(payload))


def _canonical_value(
    value: Any,
    *,
    path: tuple[str, ...],
    root_token_factor_snapshot: bool = False,
) -> Any:
    raw = _unwrap_jsonb(value)
    if isinstance(raw, Decimal):
        return float(raw)
    if isinstance(raw, Mapping):
        out: dict[str, Any] = {}
        for key, item in raw.items():
            if type(key) is not str:
                raise ValueError(f"current payload hash payload has non-string keys: {(key,)}")
            item_path = (*path, key)
            if _is_ephemeral_factor_snapshot_computed_at_path(
                item_path,
                root_token_factor_snapshot=root_token_factor_snapshot,
            ):
                continue
            out[key] = _canonical_value(
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
    if isinstance(raw, set | frozenset):
        raise ValueError(f"current payload hash payload has unsupported containers: {raw}")
    return raw


def _unwrap_jsonb(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return value.obj
    return value


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
