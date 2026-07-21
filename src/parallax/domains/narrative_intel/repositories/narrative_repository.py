from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.domains.narrative_intel.types.fingerprints import (
    source_fingerprint as build_source_fingerprint,
)
from parallax.domains.narrative_intel.types.narrative_currentness import unsupported_admission_sentinel
from parallax.domains.narrative_intel.types.narrative_epoch_policy import DIGEST_WINDOWS
from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash


class NarrativeRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_admissions(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        now_ms: int,
        limit: int | None = None,
        commit: bool = True,
    ) -> dict[str, int]:
        selected_limit = (
            _required_positive_int(limit, "narrative_admission_upsert_limit_required") if limit is not None else None
        )
        selected = list(rows)[:selected_limit] if selected_limit is not None else list(rows)
        if not selected:
            return {"upserted": 0, "seen": 0}
        if commit:
            with _transaction(self.conn):
                return self.upsert_admissions(selected, now_ms=now_ms, commit=False)
        upserted = 0
        for row in selected:
            target_type = _required_admission_text(row, "target_type")
            target_id = _required_admission_text(row, "target_id")
            window = _required_admission_text(row, "window")
            scope = _required_admission_text(row, "scope")
            schema_version = _required_admission_text(row, "schema_version")
            source_event_ids = _required_admission_string_list(row, "source_event_ids")
            source_max_received_at_ms = _required_admission_positive_int(row, "source_max_received_at_ms")
            payload = {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "schema_version": schema_version,
                "status": _required_admission_text(row, "status"),
                "reason": _required_admission_text(row, "reason"),
                "priority": _required_admission_nonnegative_int(row, "priority"),
                "last_radar_rank": _optional_admission_positive_int(row, "last_radar_rank"),
                "last_rank_score": _optional_admission_number(row, "last_rank_score"),
                "source_event_ids_json": _json(source_event_ids),
                "source_fingerprint": build_source_fingerprint(source_event_ids, source_max_received_at_ms),
                "source_max_received_at_ms": source_max_received_at_ms,
                "projection_computed_at_ms": _required_admission_positive_int(row, "projection_computed_at_ms"),
                "source_window_start_ms": _required_admission_nonnegative_int(row, "source_window_start_ms"),
                "source_window_end_ms": _required_admission_positive_int(row, "source_window_end_ms"),
                "source_event_count": _required_admission_nonnegative_int(row, "source_event_count"),
                "independent_author_count": _required_admission_nonnegative_int(row, "independent_author_count"),
                "admission_generation": _required_admission_text(row, "admission_generation"),
                "admitted_at_ms": now_ms,
                "last_seen_at_ms": now_ms,
                "updated_at_ms": now_ms,
            }
            payload["payload_hash"] = admission_payload_hash(payload)
            cursor = self.conn.execute(
                """
                INSERT INTO narrative_admissions (
                  target_type, target_id, "window", scope, schema_version, status, reason,
                  priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
                  source_max_received_at_ms, projection_computed_at_ms, source_window_start_ms,
                  source_window_end_ms, source_event_count, independent_author_count, admission_generation,
                  admitted_at_ms, last_seen_at_ms, updated_at_ms, payload_hash
                )
                VALUES (
                  %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
                  %(status)s, %(reason)s, %(priority)s, %(last_radar_rank)s, %(last_rank_score)s,
                  %(source_event_ids_json)s, %(source_fingerprint)s, %(source_max_received_at_ms)s,
                  %(projection_computed_at_ms)s, %(source_window_start_ms)s, %(source_window_end_ms)s,
                  %(source_event_count)s, %(independent_author_count)s, %(admission_generation)s,
                  %(admitted_at_ms)s, %(last_seen_at_ms)s, %(updated_at_ms)s, %(payload_hash)s
                )
                ON CONFLICT (target_type, target_id, "window", scope)
                DO UPDATE SET
                  schema_version = EXCLUDED.schema_version,
                  status = EXCLUDED.status,
                  reason = EXCLUDED.reason,
                  priority = EXCLUDED.priority,
                  last_radar_rank = EXCLUDED.last_radar_rank,
                  last_rank_score = EXCLUDED.last_rank_score,
                  source_event_ids_json = EXCLUDED.source_event_ids_json,
                  source_fingerprint = EXCLUDED.source_fingerprint,
                  source_max_received_at_ms = EXCLUDED.source_max_received_at_ms,
                  projection_computed_at_ms = EXCLUDED.projection_computed_at_ms,
                  source_window_start_ms = EXCLUDED.source_window_start_ms,
                  source_window_end_ms = EXCLUDED.source_window_end_ms,
                  source_event_count = EXCLUDED.source_event_count,
                  independent_author_count = EXCLUDED.independent_author_count,
                  admission_generation = EXCLUDED.admission_generation,
                  last_seen_at_ms = EXCLUDED.last_seen_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms,
                  payload_hash = EXCLUDED.payload_hash
                WHERE narrative_admissions.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                """,
                payload,
            )
            upserted += _cursor_rowcount(cursor)
        return {"upserted": upserted, "seen": len(selected)}

    def source_set_for_admission(
        self,
        *,
        target_type: str,
        target_id: str,
        since_ms: int,
        until_ms: int,
        watched_only: bool,
        limit: int,
    ) -> dict[str, Any]:
        watched_clause = "AND events.is_watched = true" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              events.text_clean AS text_clean,
              events.received_at_ms AS source_received_at_ms,
              events.author_handle,
              events.tweet_id,
              events.raw_json AS reference_json
            FROM token_intent_resolutions AS resolution
            JOIN events ON events.event_id = resolution.event_id
            WHERE resolution.target_type = %s
              AND resolution.target_id = %s
              AND resolution.is_current = true
              AND events.received_at_ms >= %s
              AND events.received_at_ms <= %s
              {watched_clause}
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, int(since_ms), int(until_ms), int(limit)),
        ).fetchall()
        source_rows = [_row(row) for row in rows]
        event_ids = [str(row["event_id"]) for row in source_rows if row.get("event_id")]
        max_received_at_ms = max((_int(row.get("source_received_at_ms")) or 0 for row in source_rows), default=None)
        return {
            "source_event_ids": event_ids,
            "source_rows": [
                {
                    **row,
                    "target_type": target_type,
                    "target_id": target_id,
                }
                for row in source_rows
            ],
            "source_event_count": len(event_ids),
            "independent_author_count": _author_count(source_rows),
            "source_max_received_at_ms": max_received_at_ms,
        }

    def load_radar_admission_target(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        projection_version: str,
        schema_version: str,
    ) -> dict[str, Any]:
        radar_row = self.conn.execute(
            """
            WITH latest AS (
              SELECT
                projection_version,
                "window",
                scope,
                venue,
                current_published_at_ms,
                current_row_count
              FROM token_radar_publication_state
              WHERE projection_version = %s
                AND "window" = %s
                AND scope = %s
                AND venue = 'all'
                AND latest_attempt_status = 'ready'
                AND current_published_at_ms IS NOT NULL
              LIMIT 1
            )
            SELECT token_radar_current_rows.row_id,
                   token_radar_current_rows.target_type,
                   token_radar_current_rows.target_id,
                   token_radar_current_rows.rank,
                   latest.current_published_at_ms AS computed_at_ms,
                   token_radar_current_rows.computed_at_ms AS row_computed_at_ms,
                   NULLIF(
                     token_radar_current_rows.factor_snapshot_json->'composite'->>'rank_score', ''
                   )::double precision AS rank_score,
                   token_radar_current_rows.source_event_ids_json,
                   token_radar_current_rows.source_max_received_at_ms
            FROM latest
            JOIN token_radar_current_rows
              ON token_radar_current_rows.projection_version = latest.projection_version
             AND token_radar_current_rows."window" = latest."window"
             AND token_radar_current_rows.scope = latest.scope
             AND token_radar_current_rows.venue = latest.venue
             AND token_radar_current_rows.target_type = %s
             AND token_radar_current_rows.target_id = %s
            WHERE latest.current_row_count > 0
            LIMIT 1
            """,
            (
                projection_version,
                window,
                scope,
                target_type,
                target_id,
            ),
        ).fetchone()
        return {
            "radar_row": _row(radar_row) if radar_row else None,
            "existing_admission": self.current_admission_for_target(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
            ),
        }

    def stale_admission_target(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        commit: bool = True,
    ) -> dict[str, int]:
        if commit:
            with _transaction(self.conn):
                return self.stale_admission_target(
                    target_type=target_type,
                    target_id=target_id,
                    window=window,
                    scope=scope,
                    commit=False,
                )
        admissions = self.conn.execute(
            """
            DELETE FROM narrative_admissions AS admissions
            WHERE admissions.target_type = %s
              AND admissions.target_id = %s
              AND admissions."window" = %s
              AND admissions.scope = %s
            """,
            (target_type, target_id, window, scope),
        )
        return {
            "staled_admissions": _cursor_rowcount(admissions),
        }

    def current_admission_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE target_type = %s
              AND target_id = %s
              AND "window" = %s
              AND scope = %s
              AND schema_version = %s
            ORDER BY CASE
                       WHEN status = 'admitted' THEN 0
                       WHEN status = 'suppressed' THEN 1
                       ELSE 2
                     END,
                     last_seen_at_ms DESC
            LIMIT 1
            """,
            (target_type, target_id, window, scope, schema_version),
        ).fetchone()
        return _row(row) if row else None

    def current_narrative_admissions_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        query_targets: list[dict[str, str]] = []
        for target in targets:
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "")
            key = (target_type, target_id)
            if window not in DIGEST_WINDOWS:
                result[key] = unsupported_admission_sentinel(
                    target_type=target_type,
                    target_id=target_id,
                    window=window,
                    scope=scope,
                    schema_version=schema_version,
                )
                continue
            if key not in result:
                query_targets.append({"target_type": target_type, "target_id": target_id})
            result[key] = {}

        if not query_targets:
            return result

        admissions = self._current_admissions_for_targets(
            query_targets,
            window=window,
            scope=scope,
            schema_version=schema_version,
        )
        for target in query_targets:
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "")
            key = (target_type, target_id)
            admission = admissions.get(key)
            result[key] = _admission_state(
                admission,
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
            )
        return result

    def _current_admissions_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH input_targets AS (
              SELECT DISTINCT target_type, target_id
              FROM jsonb_to_recordset(%s::jsonb) AS target(target_type text, target_id text)
            )
            SELECT DISTINCT ON (admission.target_type, admission.target_id) admission.*
            FROM narrative_admissions AS admission
            JOIN input_targets AS target
              ON target.target_type = admission.target_type
             AND target.target_id = admission.target_id
            WHERE admission."window" = %s
              AND admission.scope = %s
              AND admission.schema_version = %s
            ORDER BY admission.target_type,
                     admission.target_id,
                     CASE
                       WHEN admission.status = 'admitted' THEN 0
                       WHEN admission.status = 'suppressed' THEN 1
                       ELSE 2
                     END,
                     admission.last_seen_at_ms DESC
            """,
            (_json([dict(target) for target in targets]), window, scope, schema_version),
        ).fetchall()
        return {(str(row["target_type"]), str(row["target_id"])): _row(row) for row in rows}


def _admission_state(
    admission: dict[str, Any] | None,
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
) -> dict[str, Any]:
    admission_status = str((admission or {}).get("status") or "missing")
    admitted = admission_status == "admitted"
    reason = str((admission or {}).get("reason") or ("no_current_admission" if admission is None else admission_status))
    display_status = "current" if admitted else ("not_ready" if admission is None else "out_of_frontier")
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "schema_version": schema_version,
        "status": admission_status,
        "reason": reason,
        "is_current": admitted,
        "source_event_count": int((admission or {}).get("source_event_count") or 0),
        "independent_author_count": int((admission or {}).get("independent_author_count") or 0),
        "computed_at_ms": (admission or {}).get("projection_computed_at_ms"),
        "data_gaps_json": [] if admitted else [{"reason": reason}],
        "currentness": {"display_status": display_status, "reason": reason},
    }


def admission_payload_hash(payload: dict[str, Any]) -> str:
    return stable_current_payload_hash(
        {
            key: _current_hash_payload_value(value)
            for key, value in payload.items()
            if key
            not in {
                "projection_computed_at_ms",
                "admission_generation",
                "admitted_at_ms",
                "last_seen_at_ms",
                "updated_at_ms",
                "payload_hash",
            }
        }
    )


def _author_count(rows: Sequence[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "").strip() for row in rows if str(row.get("author_handle") or "")})


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))


def _current_hash_payload_value(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return _current_hash_payload_value(value.obj)
    if isinstance(value, dict):
        return {key: _current_hash_payload_value(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_current_hash_payload_value(inner) for inner in value]
    return value


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = [value]
    if not isinstance(decoded, Sequence) or isinstance(decoded, (bytes, bytearray, str)):
        return []
    return [str(item) for item in decoded if str(item)]


def _row(row: Any) -> dict[str, Any]:
    decoded = dict(row)
    if "source_event_ids_json" in decoded and "source_event_ids" not in decoded:
        decoded["source_event_ids"] = _json_list(decoded.get("source_event_ids_json"))
    return decoded


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_admission_text(row: dict[str, Any], field: str) -> str:
    if field not in row or row[field] is None:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return value.strip()


def _required_admission_string_list(row: dict[str, Any], field: str) -> list[str]:
    if field not in row or row[field] is None:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if not isinstance(value, list):
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return [item.strip() for item in value]


def _required_admission_positive_int(row: dict[str, Any], field: str) -> int:
    if field not in row or row[field] is None:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return int(value)


def _required_admission_nonnegative_int(row: dict[str, Any], field: str) -> int:
    if field not in row or row[field] is None:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return int(value)


def _optional_admission_positive_int(row: dict[str, Any], field: str) -> int | None:
    if field not in row:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return int(value)


def _optional_admission_number(row: dict[str, Any], field: str) -> float | None:
    if field not in row:
        raise ValueError(f"narrative_admission_repository_required:{field}")
    value = row[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"narrative_admission_repository_invalid:{field}")
    return float(value)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("narrative_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("narrative_repository_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("narrative_repository_rowcount_invalid")
    return rowcount


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("narrative_admission_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("narrative_admission_transaction_required")
    return cast(AbstractContextManager[Any], transaction())
