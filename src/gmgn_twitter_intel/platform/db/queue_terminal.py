from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json

TERMINAL_ACTIONS = frozenset(("retry", "archive", "quarantine"))
TERMINAL_STATUSES = frozenset(("terminal", "active"))

RetryTransition = Callable[[dict[str, Any]], dict[str, Any]]
RetryTransitionMap = Mapping[tuple[str, str], Callable[..., dict[str, Any]]]


def terminalize_source_row(
    conn: Any,
    *,
    worker_name: str,
    source_table: str,
    target_key: str,
    source_row: Mapping[str, Any],
    final_status: str,
    final_reason: str,
    final_reason_bucket: str | None = None,
    now_ms: int,
    attempt_count: int | None = None,
    payload_hash: str | None = None,
    first_seen_at_ms: int | None = None,
    last_attempted_at_ms: int | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    normalized_row = _normalized_source_row(source_row, payload_hash=payload_hash)
    normalized_payload_hash = _payload_hash(normalized_row.get("payload_hash"))
    source_row_hash = _stable_json_hash(normalized_row)
    terminal_generation = _next_terminal_generation(
        conn,
        worker_name=worker_name,
        source_table=source_table,
        target_key=target_key,
        source_row_hash=source_row_hash,
    )
    terminal_id = _terminal_id(
        worker_name=worker_name,
        source_table=source_table,
        target_key=target_key,
        source_row_hash=source_row_hash,
        terminal_generation=terminal_generation,
    )
    row_attempt_count = int(
        attempt_count if attempt_count is not None else _optional_int(normalized_row.get("attempt_count")) or 0
    )
    row_first_seen_at_ms = (
        first_seen_at_ms
        if first_seen_at_ms is not None
        else _optional_int(normalized_row.get("first_dirty_at_ms") or normalized_row.get("created_at_ms"))
    )
    row_last_attempted_at_ms = (
        last_attempted_at_ms
        if last_attempted_at_ms is not None
        else _optional_int(normalized_row.get("updated_at_ms") or normalized_row.get("last_attempted_at_ms"))
    )
    params = {
        "terminal_id": terminal_id,
        "worker_name": _required_text(worker_name, "worker_name"),
        "source_table": _required_text(source_table, "source_table"),
        "target_key": _required_text(target_key, "target_key"),
        "source_row_json": _jsonb(normalized_row),
        "source_row_hash": source_row_hash,
        "final_status": _required_text(final_status, "final_status"),
        "final_reason": _required_text(final_reason, "final_reason"),
        "final_reason_bucket": _reason_bucket(
            final_reason_bucket,
            final_reason=final_reason,
            final_status=final_status,
        ),
        "attempt_count": row_attempt_count,
        "payload_hash": normalized_payload_hash,
        "first_seen_at_ms": row_first_seen_at_ms,
        "last_attempted_at_ms": row_last_attempted_at_ms,
        "terminalized_at_ms": int(now_ms),
        "terminal_generation": terminal_generation,
    }
    row = conn.execute(
        """
        INSERT INTO worker_queue_terminal_events(
          terminal_id,
          worker_name,
          source_table,
          target_key,
          source_row_json,
          source_row_hash,
          final_status,
          final_reason,
          final_reason_bucket,
          attempt_count,
          payload_hash,
          first_seen_at_ms,
          last_attempted_at_ms,
          terminalized_at_ms,
          terminal_generation
        )
        VALUES (
          %(terminal_id)s,
          %(worker_name)s,
          %(source_table)s,
          %(target_key)s,
          %(source_row_json)s,
          %(source_row_hash)s,
          %(final_status)s,
          %(final_reason)s,
          %(final_reason_bucket)s,
          %(attempt_count)s,
          %(payload_hash)s,
          %(first_seen_at_ms)s,
          %(last_attempted_at_ms)s,
          %(terminalized_at_ms)s,
          %(terminal_generation)s
        )
        ON CONFLICT(worker_name, source_table, target_key)
          WHERE operator_action IS NULL
        DO UPDATE SET
          terminal_id = EXCLUDED.terminal_id,
          source_row_json = EXCLUDED.source_row_json,
          source_row_hash = EXCLUDED.source_row_hash,
          final_status = EXCLUDED.final_status,
          final_reason = EXCLUDED.final_reason,
          final_reason_bucket = CASE
            WHEN worker_queue_terminal_events.final_reason IS DISTINCT FROM EXCLUDED.final_reason
            THEN EXCLUDED.final_reason_bucket
            ELSE worker_queue_terminal_events.final_reason_bucket
          END,
          attempt_count = GREATEST(worker_queue_terminal_events.attempt_count, EXCLUDED.attempt_count),
          payload_hash = EXCLUDED.payload_hash,
          terminalized_at_ms = EXCLUDED.terminalized_at_ms,
          last_attempted_at_ms = COALESCE(
            EXCLUDED.last_attempted_at_ms,
            worker_queue_terminal_events.last_attempted_at_ms
          )
        RETURNING *
        """,
        params,
    ).fetchone()
    if commit:
        conn.commit()
    return _row_dict(row)


def inspect_terminal_events(
    conn: Any,
    *,
    worker_name: str | None = None,
    source_table: str | None = None,
    status: str = "terminal",
    reason_bucket: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    normalized_status = _status(status)
    parsed_limit = max(1, min(500, int(limit)))
    where = ["TRUE"]
    params: dict[str, Any] = {"limit": parsed_limit}
    if worker_name:
        where.append("worker_name = %(worker_name)s")
        params["worker_name"] = str(worker_name)
    if source_table:
        where.append("source_table = %(source_table)s")
        params["source_table"] = str(source_table)
    if reason_bucket:
        where.append("final_reason_bucket = %(reason_bucket)s")
        params["reason_bucket"] = _required_text(reason_bucket, "reason_bucket")
    if normalized_status == "terminal":
        where.append("operator_action IS NULL")
    rows = conn.execute(
        f"""
        SELECT *
        FROM worker_queue_terminal_events
        WHERE {" AND ".join(where)}
        ORDER BY terminalized_at_ms DESC, terminal_id ASC
        LIMIT %(limit)s
        """,
        params,
    ).fetchall()
    items = [_row_dict(row) for row in rows]
    return {
        "status": normalized_status,
        "worker": worker_name or None,
        "source_table": source_table or None,
        "reason_bucket": reason_bucket or None,
        "limit": parsed_limit,
        "count": len(items),
        "items": items,
    }


def terminal_reason_bucket(final_reason: str | None, final_status: str | None) -> str:
    reason = str(final_reason or "").lower()
    if "522" in reason:
        return "llm_provider_522"
    if "retry_budget_exhausted" in reason or "failed_exhausted" in reason or "max_attempt" in reason:
        return "retry_budget_exhausted"
    if "provider_no_quote" in reason:
        return "provider_no_quote"
    if "provider_unavailable" in reason or "transport" in reason or "connection" in reason:
        return "provider_unavailable"
    if "provider_error" in reason:
        return "provider_error"
    if "no_market_data" in reason:
        return "no_market_data"
    if "stale" in reason:
        return "stale_window_ttl"
    if "timeout" in reason:
        return "timeout"
    if "not_found" in reason:
        return "not_found"
    if "semantic" in reason:
        return "semantic_unavailable"
    return "other"


def resolve_terminal_event(
    conn: Any,
    *,
    terminal_id: str,
    action: str,
    reason: str,
    now_ms: int,
    retry_transitions: RetryTransitionMap | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    normalized_action = _action(action)
    normalized_reason = _required_text(reason, "reason")
    terminal_id = _required_text(terminal_id, "terminal_id")
    with _transaction(conn):
        current = _fetch_terminal_event(conn, terminal_id=terminal_id, for_update=True)
        if current is None:
            raise ValueError("terminal_event_not_found")
        transition = None
        if normalized_action == "retry":
            transition = _retry_transition_for(current, retry_transitions)
        row = conn.execute(
            """
            UPDATE worker_queue_terminal_events
            SET operator_action = %(operator_action)s,
                operator_reason = %(operator_reason)s,
                operator_action_at_ms = %(operator_action_at_ms)s
            WHERE terminal_id = %(terminal_id)s
            RETURNING *
            """,
            {
                "terminal_id": terminal_id,
                "operator_action": normalized_action,
                "operator_reason": normalized_reason,
                "operator_action_at_ms": int(now_ms),
            },
        ).fetchone()
        resolved = _row_dict(row)
        if transition is not None:
            resolved["transition"] = transition(dict(resolved), now_ms=int(now_ms), reason=normalized_reason)
    if commit and not hasattr(conn, "transaction"):
        conn.commit()
    return resolved


def _fetch_terminal_event(conn: Any, *, terminal_id: str, for_update: bool = False) -> dict[str, Any] | None:
    suffix = "FOR UPDATE" if for_update else ""
    row = conn.execute(
        f"""
        SELECT *
        FROM worker_queue_terminal_events
        WHERE terminal_id = %(terminal_id)s
        {suffix}
        """,
        {"terminal_id": terminal_id},
    ).fetchone()
    return _row_dict(row) if row is not None else None


def _retry_transition_for(
    event: Mapping[str, Any],
    retry_transitions: RetryTransitionMap | None,
) -> Callable[..., dict[str, Any]]:
    key = (str(event.get("worker_name") or ""), str(event.get("source_table") or ""))
    transition = (retry_transitions or {}).get(key)
    if transition is None:
        raise ValueError(f"retry_transition_unregistered:{key[0]}:{key[1]}")
    return transition


def _normalized_source_row(source_row: Mapping[str, Any], *, payload_hash: str | None) -> dict[str, Any]:
    row = dict(postgres_safe_json(dict(source_row)))
    row["payload_hash"] = _payload_hash(payload_hash if payload_hash is not None else row.get("payload_hash"))
    return row


def _stable_json_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        postgres_safe_json(dict(value)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _terminal_id(
    *,
    worker_name: str,
    source_table: str,
    target_key: str,
    source_row_hash: str,
    terminal_generation: int,
) -> str:
    encoded = "|".join(
        (
            _required_text(worker_name, "worker_name"),
            _required_text(source_table, "source_table"),
            _required_text(target_key, "target_key"),
            source_row_hash,
            str(max(1, int(terminal_generation))),
        )
    )
    return "wqte_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _next_terminal_generation(
    conn: Any,
    *,
    worker_name: str,
    source_table: str,
    target_key: str,
    source_row_hash: str,
) -> int:
    unresolved = conn.execute(
        """
        SELECT terminal_generation
        FROM worker_queue_terminal_events
        WHERE worker_name = %(worker_name)s
          AND source_table = %(source_table)s
          AND target_key = %(target_key)s
          AND operator_action IS NULL
        LIMIT 1
        """,
        {
            "worker_name": _required_text(worker_name, "worker_name"),
            "source_table": _required_text(source_table, "source_table"),
            "target_key": _required_text(target_key, "target_key"),
        },
    ).fetchone()
    if unresolved is not None:
        return max(1, int(unresolved.get("terminal_generation") or 1))
    row = conn.execute(
        """
        SELECT COALESCE(MAX(terminal_generation), 0) + 1 AS terminal_generation
        FROM worker_queue_terminal_events
        WHERE worker_name = %(worker_name)s
          AND source_table = %(source_table)s
          AND target_key = %(target_key)s
          AND source_row_hash = %(source_row_hash)s
        """,
        {
            "worker_name": _required_text(worker_name, "worker_name"),
            "source_table": _required_text(source_table, "source_table"),
            "target_key": _required_text(target_key, "target_key"),
            "source_row_hash": source_row_hash,
        },
    ).fetchone()
    return max(1, int((row or {}).get("terminal_generation") or 1))


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        return cast(AbstractContextManager[Any], transaction())
    return nullcontext()


def _jsonb(value: Mapping[str, Any]) -> Jsonb:
    return Jsonb(
        dict(value),
        dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    out = dict(row)
    source_row = out.get("source_row_json")
    if isinstance(source_row, Jsonb):
        out["source_row_json"] = source_row.obj
    return out


def _payload_hash(value: Any) -> str:
    return str(value or "").strip()


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_required")
    return text


def _reason_bucket(value: str | None, *, final_reason: str | None, final_status: str | None) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return terminal_reason_bucket(final_reason, final_status)


def _action(value: str) -> str:
    action = str(value or "").strip()
    if action not in TERMINAL_ACTIONS:
        raise ValueError(f"unsupported_terminal_action:{action}")
    return action


def _status(value: str) -> str:
    status = str(value or "").strip() or "terminal"
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"unsupported_terminal_status:{status}")
    return status
