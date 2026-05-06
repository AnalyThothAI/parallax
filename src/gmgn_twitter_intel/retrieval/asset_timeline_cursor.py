from __future__ import annotations


class AssetTimelineCursorError(ValueError):
    pass


def encode_timeline_cursor(row: dict) -> str:
    return f"{int(row['received_at_ms'])}:{row['event_id']}"


def decode_timeline_cursor(cursor: str | None) -> tuple[int, str] | None:
    if not cursor:
        return None
    timestamp, separator, event_id = cursor.partition(":")
    if not separator or not event_id:
        raise AssetTimelineCursorError(cursor)
    try:
        received_at_ms = int(timestamp)
    except ValueError as exc:
        raise AssetTimelineCursorError(cursor) from exc
    if received_at_ms <= 0:
        raise AssetTimelineCursorError(cursor)
    return received_at_ms, event_id
