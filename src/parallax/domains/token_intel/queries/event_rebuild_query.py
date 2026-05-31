from __future__ import annotations

from typing import Any


class EventRebuildQuery:
    """Fetches events to be used as input for token intent rebuilding."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def recent_events(self, *, since_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT event_id, received_at_ms, text, reference_json, event_json
            FROM events
            WHERE received_at_ms >= %s
            ORDER BY received_at_ms DESC, event_id
            LIMIT %s
            """,
            (since_ms, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]
