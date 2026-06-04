from __future__ import annotations

import json
from typing import Any

NEWS_WORKER_ADVISORY_LOCK_KEYS = {
    "news_fetch": 2026051905,
    "news_item_process": 2026051902,
    "news_item_brief": 2026052001,
    "news_page_projection": 2026051904,
    "news_source_quality_projection": 2026052201,
}

NEWS_CLEAR_TABLES = (
    "news_projection_dirty_targets",
    "news_page_rows",
    "news_source_quality_rows",
    "news_item_agent_briefs",
    "news_item_agent_runs",
    "news_fact_candidates",
    "news_token_mentions",
    "news_item_entities",
)
OPTIONAL_LEGACY_CLEAR_TABLES = (
    "_".join(("news", "context", "items")),
    "news_story_members",
    "news_story_groups",
)
NEWS_CLEAR_TAIL_TABLES = (
    "news_item_observation_edges",
    "news_items",
    "news_provider_items",
    "news_fetch_runs",
)


class NewsIntelHardCutCleanupAbort(RuntimeError):
    """Raised when execute mode detects active News runtime state."""


def cleanup_news_intel_hard_cut(repos: Any, *, execute: bool, now_ms: int) -> dict[str, Any]:
    conn = repos.conn
    now = int(now_ms)
    existing_optional_tables = _existing_tables(conn, OPTIONAL_LEGACY_CLEAR_TABLES)
    ordered_tables = (*NEWS_CLEAR_TABLES, *existing_optional_tables, *NEWS_CLEAR_TAIL_TABLES)
    dry_run = not bool(execute)
    result: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "dry_run": dry_run,
        "execute": bool(execute),
        "now_ms": now,
        "process_worker_persistent_lease_supported": False,
        "optional_legacy_tables": list(existing_optional_tables),
        "table_counts": _table_counts(conn, ordered_tables),
        "notification_counts": _news_notification_counts(conn),
        "active_state": _active_news_state(conn, now_ms=now),
        "deleted_tables": {},
        "deleted_notifications": {},
        "reset_sources": 0,
    }
    if dry_run:
        return result

    with conn.transaction():
        guard_state = news_intel_hard_cut_runtime_guard(conn, now_ms=now)
        result["active_state"] = guard_state["active_state"]
        result["advisory_locks"] = guard_state["advisory_locks"]
        blockers = guard_state["blockers"]
        if blockers:
            raise NewsIntelHardCutCleanupAbort(json.dumps({"blockers": blockers}, sort_keys=True))
        result["deleted_notifications"] = _delete_news_notifications(conn)
        result["deleted_tables"] = _delete_tables(conn, ordered_tables)
        result["reset_sources"] = int(
            conn.execute(
                """
                UPDATE news_sources
                   SET etag = NULL,
                       last_modified = NULL,
                       last_fetch_at_ms = NULL,
                       last_success_at_ms = NULL,
                       consecutive_failures = 0,
                       last_error = NULL,
                       source_quality_status = 'unknown',
                       next_fetch_after_ms = 0,
                       sync_cursor_json = '{}'::jsonb,
                       sync_high_watermark_ms = 0,
                       sync_diagnostics_json = '{}'::jsonb,
                       updated_at_ms = %s
                """,
                (now,),
            ).rowcount
            or 0
        )
    result["table_counts_after"] = _table_counts(conn, ordered_tables)
    result["notification_counts_after"] = _news_notification_counts(conn)
    return result


def _existing_tables(conn: Any, table_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        table_name
        for table_name in table_names
        if conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table_name,)).fetchone()["exists"]
    )


def _table_counts(conn: Any, table_names: tuple[str, ...]) -> dict[str, int]:
    return {
        table_name: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
        for table_name in table_names
    }


def _news_notification_counts(conn: Any) -> dict[str, int]:
    notification_filter = """
        rule_id = 'news_high_signal'
        AND (source_table = 'news_page_rows' OR entity_type = 'news_item')
    """
    notifications = int(
        conn.execute(f"SELECT COUNT(*) AS count FROM notifications WHERE {notification_filter}").fetchone()["count"]
    )
    reads = int(
        conn.execute(
            f"""
            SELECT COUNT(*) AS count
              FROM notification_reads AS reads
              JOIN notifications AS notifications ON notifications.notification_id = reads.notification_id
             WHERE {notification_filter}
            """
        ).fetchone()["count"]
    )
    deliveries = int(
        conn.execute(
            f"""
            SELECT COUNT(*) AS count
              FROM notification_deliveries AS deliveries
              JOIN notifications AS notifications ON notifications.notification_id = deliveries.notification_id
             WHERE {notification_filter}
            """
        ).fetchone()["count"]
    )
    return {
        "notifications": notifications,
        "notification_reads": reads,
        "notification_deliveries": deliveries,
    }


def _delete_news_notifications(conn: Any) -> dict[str, int]:
    counts = _news_notification_counts(conn)
    deleted = int(
        conn.execute(
            """
            DELETE FROM notifications
             WHERE rule_id = 'news_high_signal'
               AND (source_table = 'news_page_rows' OR entity_type = 'news_item')
            """
        ).rowcount
        or 0
    )
    return {**counts, "deleted_notifications": deleted}


def _delete_tables(conn: Any, table_names: tuple[str, ...]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for table_name in table_names:
        deleted[table_name] = int(conn.execute(f"DELETE FROM {table_name}").rowcount or 0)
    return deleted


def _active_news_state(conn: Any, *, now_ms: int) -> dict[str, Any]:
    running_fetch_runs = int(
        conn.execute(
            "SELECT COUNT(*) AS count FROM news_fetch_runs WHERE status = 'running'",
        ).fetchone()["count"]
    )
    dirty_leases = [
        dict(row)
        for row in conn.execute(
            """
            SELECT projection_name,
                   COUNT(*)::int AS count,
                   MIN(updated_at_ms)::bigint AS min_updated_at_ms,
                   MAX(leased_until_ms)::bigint AS max_leased_until_ms
              FROM news_projection_dirty_targets
             WHERE leased_until_ms IS NOT NULL
               AND leased_until_ms > %s
             GROUP BY projection_name
             ORDER BY projection_name
            """,
            (int(now_ms),),
        ).fetchall()
    ]
    return {
        "running_fetch_runs": running_fetch_runs,
        "active_dirty_leases": dirty_leases,
    }


def _try_news_advisory_locks(conn: Any) -> dict[str, bool]:
    lock_state: dict[str, bool] = {}
    for worker_name, lock_key in NEWS_WORKER_ADVISORY_LOCK_KEYS.items():
        row = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", (int(lock_key),)).fetchone()
        lock_state[worker_name] = bool(row["acquired"])
    return lock_state


def _active_blockers(*, active_state: dict[str, Any], advisory_locks: dict[str, bool]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    running_fetch_runs = int(active_state.get("running_fetch_runs") or 0)
    if running_fetch_runs:
        blockers.append({"type": "running_fetch_runs", "count": running_fetch_runs})
    dirty_leases = list(active_state.get("active_dirty_leases") or [])
    if dirty_leases:
        blockers.append({"type": "active_dirty_leases", "leases": dirty_leases})
    unavailable_locks = [worker_name for worker_name, acquired in advisory_locks.items() if not acquired]
    if unavailable_locks:
        blockers.append({"type": "advisory_lock_unavailable", "workers": unavailable_locks})
    return blockers


def news_intel_hard_cut_runtime_guard(conn: Any, *, now_ms: int) -> dict[str, Any]:
    active_state = _active_news_state(conn, now_ms=int(now_ms))
    advisory_locks = _try_news_advisory_locks(conn)
    blockers = _active_blockers(active_state=active_state, advisory_locks=advisory_locks)
    return {
        "active_state": active_state,
        "advisory_locks": advisory_locks,
        "blockers": blockers,
    }


__all__ = [
    "NEWS_WORKER_ADVISORY_LOCK_KEYS",
    "NewsIntelHardCutCleanupAbort",
    "cleanup_news_intel_hard_cut",
    "news_intel_hard_cut_runtime_guard",
]
