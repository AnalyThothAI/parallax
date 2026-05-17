from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

_WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}


class SocialEventExtractionRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_extraction(
        self,
        *,
        event_id: str,
        run_id: str | None,
        author_handle: str | None,
        received_at_ms: int,
        schema_version: str,
        model_version: str,
        event_type: str,
        source_action: str,
        subject: str,
        direction_hint: str,
        attention_mechanism: str,
        impact_hint: float,
        semantic_novelty_hint: float,
        confidence: float,
        is_signal_event: bool,
        anchor_terms: list[dict[str, Any]],
        token_candidates: list[dict[str, Any]],
        semantic_risks: list[str],
        summary_zh: str,
        raw_response: dict[str, Any],
        extraction_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_event_id = str(event_id)
        extraction_id = extraction_id or _extraction_id(normalized_event_id)
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO social_event_extractions(
              extraction_id, event_id, run_id, author_handle, received_at_ms, schema_version, model_version,
              event_type, source_action, subject, direction_hint, attention_mechanism, impact_hint,
              semantic_novelty_hint, confidence, is_signal_event, anchor_terms_json, token_candidates_json,
              semantic_risks_json, summary_zh, raw_response_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(event_id) DO UPDATE SET
              run_id = excluded.run_id,
              author_handle = excluded.author_handle,
              received_at_ms = excluded.received_at_ms,
              schema_version = excluded.schema_version,
              model_version = excluded.model_version,
              event_type = excluded.event_type,
              source_action = excluded.source_action,
              subject = excluded.subject,
              direction_hint = excluded.direction_hint,
              attention_mechanism = excluded.attention_mechanism,
              impact_hint = excluded.impact_hint,
              semantic_novelty_hint = excluded.semantic_novelty_hint,
              confidence = excluded.confidence,
              is_signal_event = excluded.is_signal_event,
              anchor_terms_json = excluded.anchor_terms_json,
              token_candidates_json = excluded.token_candidates_json,
              semantic_risks_json = excluded.semantic_risks_json,
              summary_zh = excluded.summary_zh,
              raw_response_json = excluded.raw_response_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                extraction_id,
                normalized_event_id,
                run_id,
                author_handle,
                int(received_at_ms),
                schema_version,
                model_version,
                event_type,
                source_action,
                subject,
                direction_hint,
                attention_mechanism,
                float(impact_hint),
                float(semantic_novelty_hint),
                float(confidence),
                bool(is_signal_event),
                _json(anchor_terms),
                _json(token_candidates),
                _json(semantic_risks),
                summary_zh,
                _json(raw_response),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.by_event_id(normalized_event_id) or {}

    def by_event_id(self, event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM social_event_extractions WHERE event_id = %s",
            (str(event_id),),
        ).fetchone()
        return _decode(dict(row)) if row else None

    def by_event_ids(self, event_ids: Sequence[str]) -> dict[str, dict[str, Any] | None]:
        ids = _event_ids(event_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM social_event_extractions
            WHERE event_id = ANY(%s)
            ORDER BY event_id, extraction_id
            """,
            (ids,),
        ).fetchall()
        items: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = _decode(dict(row))
            items.setdefault(str(item["event_id"]), item)
        return {event_id: items.get(event_id) for event_id in ids}

    def recent(
        self,
        *,
        window: str,
        limit: int,
        handles: set[str] | None = None,
        event_types: set[str] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        now = int(now_ms if now_ms is not None else _now_ms())
        clauses = ["se.received_at_ms >= %s"]
        params: list[Any] = [now - _WINDOW_MS.get(window, _WINDOW_MS["1h"])]
        if handles:
            normalized = sorted(handle.lower().lstrip("@") for handle in handles)
            clauses.append(f"lower(se.author_handle) IN ({','.join('%s' for _ in normalized)})")
            params.extend(normalized)
        if event_types:
            normalized_types = sorted(event_types)
            clauses.append(f"se.event_type IN ({','.join('%s' for _ in normalized_types)})")
            params.extend(normalized_types)
        rows = self.conn.execute(
            f"""
            SELECT se.*, e.event_json
            FROM social_event_extractions se
            LEFT JOIN events e ON e.event_id = se.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY se.received_at_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return {"items": [_decode(dict(row)) for row in rows], "window": window, "limit": max(0, int(limit))}


def _extraction_id(event_id: str) -> str:
    payload = f"social_event_extraction|{event_id}"
    return "social_event_extraction:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    row["is_signal_event"] = bool(row["is_signal_event"])
    row["anchor_terms"] = _json_loads(row.pop("anchor_terms_json", None), [])
    row["token_candidates"] = _json_loads(row.pop("token_candidates_json", None), [])
    row["semantic_risks"] = _json_loads(row.pop("semantic_risks_json", None), [])
    row["raw_response"] = _json_loads(row.pop("raw_response_json", None), {})
    event_json = row.pop("event_json", None)
    row["event"] = _json_loads(event_json, None) if event_json is not None else None
    return row


def _event_ids(event_ids: Sequence[str]) -> list[str]:
    return [event_id for event_id in dict.fromkeys(str(item).strip() for item in event_ids) if event_id]


def _now_ms() -> int:
    return int(time.time() * 1000)
