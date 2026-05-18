from __future__ import annotations

from typing import Any


class NarrativeSourceQuery:
    def __init__(self, conn: Any):
        self.conn = conn

    def admitted_radar_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT row_id, target_type, target_id, rank, rank_score, computed_at_ms,
                   factor_snapshot_json->'provenance'->'source_event_ids' AS source_event_ids_json
            FROM token_radar_rows
            WHERE "window" = %s
              AND scope = %s
              AND projection_version = %s
              AND target_type IS NOT NULL
              AND target_id IS NOT NULL
            ORDER BY computed_at_ms DESC, rank ASC
            LIMIT %s
            """,
            (window, scope, projection_version, int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def source_mentions_for_admission(
        self,
        *,
        target_type: str,
        target_id: str,
        since_ms: int,
        watched_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              resolution.target_type,
              resolution.target_id,
              events.text_clean AS text_clean,
              events.author_handle,
              events.received_at_ms AS source_received_at_ms,
              events.tweet_id,
              events.raw_json AS reference_json
            FROM token_intent_resolutions AS resolution
            JOIN events ON events.event_id = resolution.event_id
            WHERE resolution.target_type = %s
              AND resolution.target_id = %s
              AND COALESCE(resolution.is_current, true) = true
              AND events.received_at_ms >= %s
              {watched_clause}
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, int(since_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def digest_context(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        since_ms: int,
        max_mentions: int,
    ) -> dict[str, Any]:
        mentions = self.source_mentions_for_admission(
            target_type=target_type,
            target_id=target_id,
            since_ms=since_ms,
            watched_only=scope == "matched",
            limit=max_mentions,
        )
        return {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "mentions": mentions,
            "source_event_count": len(mentions),
            "independent_author_count": len({row.get("author_handle") for row in mentions if row.get("author_handle")}),
        }


def _row(row: Any) -> dict[str, Any]:
    return dict(row)
