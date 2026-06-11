from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from parallax.app.runtime.current_read_model_publisher import stable_current_payload_hash

_MACRO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NON_FACT_RAW_PAYLOAD_KEYS = {
    "fetch_ts",
    "fetched_at",
    "fetched_at_ms",
    "provider_fetch_ts",
    "provider_fetched_at",
    "provider_fetched_at_ms",
    "received_at",
    "received_at_ms",
    "run_id",
    "sync_run_id",
    "import_run_id",
}


def normalize_macro_date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError("macro observed_at must be a date or YYYY-MM-DD string")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _MACRO_DATE_RE.fullmatch(value):
        return date.fromisoformat(value)
    raise ValueError("macro observed_at must be a date or YYYY-MM-DD string")


def macro_observation_id(observation: Mapping[str, Any]) -> str:
    identity = "|".join(
        [
            str(observation.get("source_name") or ""),
            str(observation.get("concept_key") or ""),
            str(observation.get("series_key") or ""),
            str(normalize_macro_date(observation.get("observed_at"))),
        ]
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"macro-observation:{digest}"


def macro_observation_fact_payload_hash(observation: Mapping[str, Any]) -> str:
    payload = {
        "source_name": observation.get("source_name"),
        "series_key": observation.get("series_key"),
        "concept_key": observation.get("concept_key"),
        "observed_at": normalize_macro_date(observation.get("observed_at")),
        "value_numeric": observation.get("value_numeric"),
        "unit": observation.get("unit"),
        "frequency": observation.get("frequency"),
        "data_quality": observation.get("data_quality"),
        "source_ts": observation.get("source_ts"),
        "raw_payload_json": _fact_raw_payload(
            observation.get("raw_payload_json") or observation.get("raw_payload") or {}
        ),
    }
    return _stable_payload_hash(payload)


def macro_series_current_row_payload_hash(row: Mapping[str, Any]) -> str:
    payload = {
        "projection_version": row.get("projection_version"),
        "concept_key": row.get("concept_key"),
        "observed_at": normalize_macro_date(row.get("observed_at")),
        "series_rank": int(row.get("series_rank") or 0),
        "value_numeric": row.get("value_numeric"),
        "source_name": row.get("source_name"),
        "series_key": row.get("series_key"),
        "source_priority": int(row.get("source_priority") or 0),
        "unit": row.get("unit"),
        "frequency": row.get("frequency"),
        "data_quality": row.get("data_quality"),
        "source_ts": row.get("source_ts"),
        "raw_payload_json": row.get("raw_payload_json") or row.get("raw_payload") or {},
    }
    return stable_current_payload_hash(payload)


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_json_ready(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}"


def _fact_raw_payload(raw_payload: object) -> dict[str, Any]:
    if not isinstance(raw_payload, Mapping):
        return {}
    return {str(key): value for key, value in raw_payload.items() if str(key) not in _NON_FACT_RAW_PAYLOAD_KEYS}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, set | frozenset):
        return sorted(_json_ready(inner) for inner in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


__all__ = [
    "macro_observation_fact_payload_hash",
    "macro_observation_id",
    "macro_series_current_row_payload_hash",
    "normalize_macro_date",
]
