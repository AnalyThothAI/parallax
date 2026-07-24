from __future__ import annotations

from typing import Any


class TokenTargetCursorError(Exception):
    pass


def encode_target_cursor(row: dict[str, Any]) -> str:
    return f"{int(row.get('received_at_ms') or 0)}:{row.get('event_id')}"


def decode_target_cursor(value: str | None) -> tuple[int, str] | None:
    if not value:
        return None
    try:
        timestamp, event_id = value.split(":", 1)
        return int(timestamp), event_id
    except (TypeError, ValueError) as exc:
        raise TokenTargetCursorError(value) from exc
