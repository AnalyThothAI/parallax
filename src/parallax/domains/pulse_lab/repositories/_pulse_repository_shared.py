from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from psycopg.types.json import Jsonb

DISPLAY_PULSE_STATUSES = ("trade_candidate", "token_watch", "risk_rejected_high_info")
SUMMARY_PULSE_STATUSES = (*DISPLAY_PULSE_STATUSES, "blocked_low_information")
DISPLAY_PULSE_STATUS_SQL = "('trade_candidate', 'token_watch', 'risk_rejected_high_info')"


@dataclass(frozen=True, slots=True)
class PulseAdmissionClaim:
    accepted: bool
    reason: str
    job: dict[str, Any] | None = None


def _row(row: Any) -> dict[str, Any]:
    return {str(key): _decode_json_value(value) for key, value in dict(row).items()}


def _optional_row(row: Any) -> dict[str, Any] | None:
    return _row(row) if row else None


def _json(value: Any) -> Jsonb:
    return Jsonb(_json_ready(value), dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _decode_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _encode_cursor(updated_at_ms: int, candidate_id: str) -> str:
    payload = json.dumps(
        {"updated_at_ms": int(updated_at_ms), "candidate_id": str(candidate_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "updated_at_ms" not in payload or "candidate_id" not in payload:
        return None
    candidate_id = payload["candidate_id"]
    if not isinstance(candidate_id, str):
        return None
    try:
        updated_at_ms = int(payload["updated_at_ms"])
    except (TypeError, ValueError):
        return None
    return {"updated_at_ms": updated_at_ms, "candidate_id": candidate_id}


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values if isinstance(values, list | tuple | set) else []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    if hasattr(conn, "transaction"):
        return cast("AbstractContextManager[Any]", conn.transaction())
    return nullcontext()


def _normalize_subject(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("@").lower()
    return normalized or None


def _normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("$").upper()
    return normalized or None


def _now_ms() -> int:
    return int(time.time() * 1000)
