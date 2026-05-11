from __future__ import annotations

from typing import Any


class AssetSearchEventsQuery:
    """Fetches events matching token evidence criteria for the asset search service."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def events_for_evidence(
        self,
        *,
        where_sql: str,
        params: list[Any],
        limit: int,
        watched_only: bool,
    ) -> list[dict[str, Any]]:
        clauses = [where_sql]
        query_params = list(params)
        if watched_only:
            clauses.append("events.is_watched = true")
        query_params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            WITH matched AS (
              SELECT DISTINCT ON (events.event_id)
                events.*,
                token_evidence.evidence_id,
                token_evidence.evidence_type,
                token_evidence.raw_value AS mention_raw_value,
                token_evidence.normalized_symbol,
                token_evidence.chain_hint,
                token_evidence.address_hint,
                token_intent_resolutions.target_type,
                token_intent_resolutions.target_id,
                token_intent_resolutions.pricefeed_id,
                token_intent_resolutions.resolution_status,
                CASE
                  WHEN token_intent_resolutions.resolution_status = 'EXACT' THEN 1.0
                  WHEN token_intent_resolutions.resolution_status = 'UNIQUE_BY_CONTEXT' THEN 0.9
                  WHEN token_intent_resolutions.resolution_status = 'AMBIGUOUS' THEN 0.45
                  ELSE 0.0
                END AS resolution_confidence
              FROM token_evidence
              JOIN events ON events.event_id = token_evidence.event_id
              LEFT JOIN token_intent_evidence
                ON token_intent_evidence.evidence_id = token_evidence.evidence_id
              LEFT JOIN token_intent_resolutions
                ON token_intent_resolutions.intent_id = token_intent_evidence.intent_id
               AND token_intent_resolutions.is_current = true
              WHERE {" AND ".join(clauses)}
              ORDER BY events.event_id, token_intent_resolutions.decision_time_ms DESC NULLS LAST
            )
            SELECT *
            FROM matched
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT %s
            """,
            query_params,
        ).fetchall()
        return [dict(row) for row in rows]
