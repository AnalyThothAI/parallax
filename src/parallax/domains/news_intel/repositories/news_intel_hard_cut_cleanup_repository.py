from __future__ import annotations

import json
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.types.news_item_brief_contract import CURRENT_NEWS_ITEM_BRIEF_CONTRACT

NEWS_WORKER_ADVISORY_LOCK_KEYS = {
    "news_fetch": 2026051905,
    "news_item_process": 2026051902,
    "news_item_brief": 2026052001,
    "news_page_projection": 2026051904,
    "news_source_quality_projection": 2026052201,
}

MATERIAL_FACT_TABLES = (
    "news_sources",
    "news_fetch_runs",
    "news_provider_items",
    "news_item_observation_edges",
    "news_items",
    "news_item_entities",
    "news_token_mentions",
    "news_fact_candidates",
)
CURRENT_READ_MODEL_TABLES = ("news_source_quality_rows",)
RETIRED_BRIEF_FIELDS = (
    "retrieval_notes_zh",
    "source_consensus_zh",
    "confirmation_state",
    "novelty_status",
    "used_tool_call_ids",
    "impact_zh",
    "watch_items_zh",
    "confidence",
)
RETIRED_RESEARCH_PAYLOAD_KEYS = (
    "research_packet",
    "tool_results",
)
RETIRED_RESEARCH_TOOL_NAMES = (
    "get_target_news_context",
    "search_news_archive",
    "get_observation_history",
)
RETIRED_RESEARCH_TOOL_NAME_FIELDS = (
    "function",
    "function_name",
    "name",
    "tool",
    "tool_name",
    "value",
)


class NewsIntelHardCutCleanupAbort(RuntimeError):
    """Raised when execute mode detects active News runtime state."""


def cleanup_news_intel_hard_cut(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    current_artifact_version_hash: str | None = None,
) -> dict[str, Any]:
    conn = repos.conn
    now = int(now_ms)
    dry_run = not bool(execute)
    current_contract = _current_contract(current_artifact_version_hash)
    cleanup_state = _cleanup_state(conn, current_artifact_version_hash=current_artifact_version_hash)
    result: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "dry_run": dry_run,
        "execute": bool(execute),
        "now_ms": now,
        "current_contract": current_contract,
        "legacy_briefs_by_contract": _legacy_counts_by_contract(
            conn,
            table_name="news_item_agent_briefs",
            current_artifact_version_hash=current_artifact_version_hash,
        ),
        "legacy_runs_by_contract": _legacy_counts_by_contract(
            conn,
            table_name="news_item_agent_runs",
            current_artifact_version_hash=current_artifact_version_hash,
        ),
        "retired_page_rows": len(cleanup_state["page_row_ids"]),
        "retired_notifications": _notification_counts_for_ids(conn, cleanup_state["notification_ids"]),
        "deleted": {},
        "preserved_material_facts": _table_counts(conn, MATERIAL_FACT_TABLES),
        "preserved_current_read_models": _table_counts(conn, CURRENT_READ_MODEL_TABLES),
        "active_state": _active_news_state(conn, now_ms=now),
    }
    if dry_run:
        return result

    with conn.transaction():
        guard_state = news_intel_hard_cut_runtime_guard(conn, now_ms=now)
        result["active_state"] = guard_state["active_state"]
        result["advisory_locks"] = guard_state["advisory_locks"]
        blockers = guard_state["blockers"]
        result["blockers"] = blockers
        if blockers:
            raise NewsIntelHardCutCleanupAbort(json.dumps({"blockers": blockers}, sort_keys=True))
        cleanup_state = _cleanup_state(conn, current_artifact_version_hash=current_artifact_version_hash)
        result["deleted"] = _delete_retired_artifacts(conn, cleanup_state)
    result["preserved_material_facts"] = _table_counts(conn, MATERIAL_FACT_TABLES)
    result["preserved_current_read_models"] = _table_counts(conn, CURRENT_READ_MODEL_TABLES)
    return result


def _table_counts(conn: Any, table_names: tuple[str, ...]) -> dict[str, int]:
    return {
        table_name: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
        for table_name in table_names
    }


def _current_contract(current_artifact_version_hash: str | None) -> dict[str, str]:
    contract = dict(CURRENT_NEWS_ITEM_BRIEF_CONTRACT)
    if current_artifact_version_hash:
        contract["artifact_version_hash"] = str(current_artifact_version_hash)
    return contract


def _cleanup_state(conn: Any, *, current_artifact_version_hash: str | None) -> dict[str, Any]:
    brief_ids = _retired_brief_ids(conn, current_artifact_version_hash=current_artifact_version_hash)
    run_ids = _retired_run_ids(conn, current_artifact_version_hash=current_artifact_version_hash)
    page_row_ids = _retired_page_row_ids(conn)
    dirty_target_keys = _retired_dirty_target_keys(conn, current_artifact_version_hash=current_artifact_version_hash)
    notification_ids = _retired_notification_ids(conn, page_row_ids=page_row_ids)
    return {
        "brief_ids": brief_ids,
        "run_ids": run_ids,
        "page_row_ids": page_row_ids,
        "dirty_target_keys": dirty_target_keys,
        "notification_ids": notification_ids,
    }


def _legacy_counts_by_contract(
    conn: Any,
    *,
    table_name: str,
    current_artifact_version_hash: str | None,
) -> dict[str, int]:
    if table_name == "news_item_agent_runs":
        counts: dict[str, int] = {}
        for row in _retired_run_rows(conn, current_artifact_version_hash=current_artifact_version_hash):
            key = _contract_key(row)
            counts[key] = counts.get(key, 0) + 1
        return counts
    rows = conn.execute(
        f"""
        SELECT prompt_version,
               schema_version,
               validator_version,
               artifact_version_hash,
               COUNT(*)::int AS count
          FROM {table_name} AS retired_contract
         WHERE {_retired_contract_sql("retired_contract", current_artifact_version_hash=current_artifact_version_hash)}
            OR {_retired_json_field_sql("brief_json")}
         GROUP BY prompt_version, schema_version, validator_version, artifact_version_hash
         ORDER BY prompt_version, schema_version, validator_version, artifact_version_hash
        """
    ).fetchall()
    return {_contract_key(row): int(row["count"]) for row in rows}


def _retired_brief_ids(conn: Any, *, current_artifact_version_hash: str | None) -> list[str]:
    contract_predicate = _retired_contract_sql(
        "retired_contract",
        current_artifact_version_hash=current_artifact_version_hash,
    )
    return [
        str(row["news_item_id"])
        for row in conn.execute(
            f"""
            SELECT news_item_id
              FROM news_item_agent_briefs AS retired_contract
             WHERE {contract_predicate}
                OR {_retired_json_field_sql("brief_json")}
             ORDER BY news_item_id
            """
        ).fetchall()
    ]


def _retired_run_ids(conn: Any, *, current_artifact_version_hash: str | None) -> list[str]:
    return [
        str(row["run_id"])
        for row in _retired_run_rows(conn, current_artifact_version_hash=current_artifact_version_hash)
    ]


def _retired_page_row_ids(conn: Any) -> list[str]:
    return [
        str(row["row_id"])
        for row in conn.execute(
            f"""
            SELECT row_id
              FROM news_page_rows
             WHERE projection_version <> {_sql_literal(NEWS_PAGE_PROJECTION_VERSION)}
                OR {_retired_page_agent_contract_sql()}
                OR {_retired_json_field_sql("agent_brief_json")}
                OR {_retired_json_field_sql("agent_brief_json -> 'brief_json'")}
             ORDER BY row_id
            """
        ).fetchall()
    ]


def _retired_dirty_target_keys(conn: Any, *, current_artifact_version_hash: str | None) -> list[dict[str, str]]:
    contract_predicate = _retired_contract_sql(
        "retired_contract",
        current_artifact_version_hash=current_artifact_version_hash,
    )
    rows = conn.execute(
        f"""
        SELECT targets.projection_name, targets.target_kind, targets.target_id, targets."window"
          FROM news_projection_dirty_targets AS targets
         WHERE targets.projection_name = 'brief_input'
           AND EXISTS (
             SELECT 1
               FROM news_item_agent_briefs AS retired_contract
              WHERE retired_contract.news_item_id = targets.target_id
                AND (
                  {contract_predicate}
                  OR {_retired_json_field_sql("brief_json")}
                )
           )
         ORDER BY targets.projection_name, targets.target_kind, targets.target_id, targets."window"
        """
    ).fetchall()
    return [
        {
            "projection_name": str(row["projection_name"]),
            "target_kind": str(row["target_kind"]),
            "target_id": str(row["target_id"]),
            "window": str(row["window"]),
        }
        for row in rows
    ]


def _retired_notification_ids(conn: Any, *, page_row_ids: list[str]) -> list[str]:
    page_ids = [str(row_id) for row_id in page_row_ids]
    return [
        str(row["notification_id"])
        for row in conn.execute(
            f"""
            SELECT DISTINCT notifications.notification_id
              FROM notifications
              LEFT JOIN news_page_rows AS current_source_rows
                ON notifications.source_table = 'news_page_rows'
               AND current_source_rows.row_id = notifications.source_id
               AND NOT (current_source_rows.row_id = ANY(%s::text[]))
             WHERE notifications.rule_id = 'news_high_signal'
               AND (
                 (
                   notifications.source_table = 'news_page_rows'
                   AND current_source_rows.row_id IS NULL
                 )
                 OR {_retired_json_field_sql("notifications.payload_json")}
                 OR {_retired_json_field_sql("notifications.payload_json -> 'brief_json'")}
               )
             ORDER BY notifications.notification_id
            """,
            (page_ids,),
        ).fetchall()
    ]


def _notification_counts_for_ids(conn: Any, notification_ids: list[str]) -> dict[str, int]:
    ids = [str(notification_id) for notification_id in notification_ids]
    notifications = int(
        conn.execute(
            "SELECT COUNT(*) AS count FROM notifications WHERE notification_id = ANY(%s::text[])", (ids,)
        ).fetchone()["count"]
    )
    reads = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM notification_reads AS reads
             WHERE reads.notification_id = ANY(%s::text[])
            """,
            (ids,),
        ).fetchone()["count"]
    )
    deliveries = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM notification_deliveries AS deliveries
             WHERE deliveries.notification_id = ANY(%s::text[])
            """,
            (ids,),
        ).fetchone()["count"]
    )
    return {
        "notifications": notifications,
        "notification_reads": reads,
        "notification_deliveries": deliveries,
    }


def _delete_retired_artifacts(conn: Any, cleanup_state: dict[str, list[Any]]) -> dict[str, int]:
    notification_ids = [str(notification_id) for notification_id in cleanup_state["notification_ids"]]
    brief_ids = [str(news_item_id) for news_item_id in cleanup_state["brief_ids"]]
    run_ids = [str(run_id) for run_id in cleanup_state["run_ids"]]
    page_row_ids = [str(row_id) for row_id in cleanup_state["page_row_ids"]]
    deleted: dict[str, int] = {}
    notification_counts = _notification_counts_for_ids(conn, notification_ids)
    deleted["notifications"] = int(
        conn.execute(
            """
            DELETE FROM notifications
             WHERE notification_id = ANY(%s::text[])
            """,
            (notification_ids,),
        ).rowcount
        or 0
    )
    deleted["notification_reads"] = notification_counts["notification_reads"]
    deleted["notification_deliveries"] = notification_counts["notification_deliveries"]
    deleted["news_projection_dirty_targets"] = _delete_dirty_targets(conn, cleanup_state["dirty_target_keys"])
    deleted["news_page_rows"] = int(
        conn.execute("DELETE FROM news_page_rows WHERE row_id = ANY(%s::text[])", (page_row_ids,)).rowcount or 0
    )
    deleted["news_item_agent_briefs"] = int(
        conn.execute("DELETE FROM news_item_agent_briefs WHERE news_item_id = ANY(%s::text[])", (brief_ids,)).rowcount
        or 0
    )
    deleted["news_item_agent_runs"] = int(
        conn.execute("DELETE FROM news_item_agent_runs WHERE run_id = ANY(%s::text[])", (run_ids,)).rowcount or 0
    )
    return deleted


def _delete_dirty_targets(conn: Any, keys: list[Any]) -> int:
    deleted = 0
    for key in keys:
        deleted += int(
            conn.execute(
                """
                DELETE FROM news_projection_dirty_targets
                 WHERE projection_name = %s
                   AND target_kind = %s
                   AND target_id = %s
                   AND "window" = %s
                """,
                (key["projection_name"], key["target_kind"], key["target_id"], key["window"]),
            ).rowcount
            or 0
        )
    return deleted


def _retired_contract_sql(alias: str, *, current_artifact_version_hash: str | None) -> str:
    parts = [
        f"({alias}.prompt_version <> {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT['prompt_version'])}"
        f" OR {alias}.schema_version <> {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT['schema_version'])}"
        f" OR {alias}.validator_version <> {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT['validator_version'])}"
    ]
    if current_artifact_version_hash is not None:
        parts.append(f" OR {alias}.artifact_version_hash <> {_sql_literal(current_artifact_version_hash)}")
    return "".join(parts) + ")"


def _retired_page_agent_contract_sql() -> str:
    prompt = _sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"])
    schema = _sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"])
    validator = _sql_literal(CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"])
    return (
        "((NOT (agent_brief_json ? 'prompt_version'))"
        " OR (agent_brief_json ? 'prompt_version' "
        f"AND agent_brief_json ->> 'prompt_version' <> {prompt})"
        " OR (NOT (agent_brief_json ? 'schema_version'))"
        " OR (agent_brief_json ? 'schema_version' "
        f"AND agent_brief_json ->> 'schema_version' <> {schema})"
        " OR (NOT (agent_brief_json ? 'validator_version'))"
        " OR (agent_brief_json ? 'validator_version' "
        f"AND agent_brief_json ->> 'validator_version' <> {validator}))"
    )


def _retired_json_field_sql(expression: str) -> str:
    return (
        "("
        + " OR ".join(
            f"COALESCE(({expression}), '{{}}'::jsonb) ? {_sql_literal(field)}" for field in RETIRED_BRIEF_FIELDS
        )
        + ")"
    )


def _retired_run_rows(conn: Any, *, current_artifact_version_hash: str | None) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT run_id,
                   prompt_version,
                   schema_version,
                   validator_version,
                   artifact_version_hash,
                   request_json,
                   response_json
              FROM news_item_agent_runs
             ORDER BY run_id
            """
        ).fetchall()
    ]
    return [
        row
        for row in rows
        if _is_retired_contract(row, current_artifact_version_hash=current_artifact_version_hash)
        or _has_retired_research_tool_payload(row.get("request_json"))
        or _has_retired_research_tool_payload(row.get("response_json"))
    ]


def _is_retired_contract(row: dict[str, Any], *, current_artifact_version_hash: str | None) -> bool:
    if str(row.get("prompt_version") or "") != CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"]:
        return True
    if str(row.get("schema_version") or "") != CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"]:
        return True
    if str(row.get("validator_version") or "") != CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"]:
        return True
    return current_artifact_version_hash is not None and str(row.get("artifact_version_hash") or "") != str(
        current_artifact_version_hash
    )


def _has_retired_research_tool_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for raw_key, raw_child in value.items():
            key = str(raw_key)
            if key in RETIRED_RESEARCH_PAYLOAD_KEYS:
                return True
            if key in RETIRED_RESEARCH_TOOL_NAME_FIELDS and _is_retired_tool_name_value(raw_child):
                return True
            if _has_retired_research_tool_payload(raw_child):
                return True
        return False
    if isinstance(value, list):
        return any(_has_retired_research_tool_payload(item) for item in value)
    return False


def _is_retired_tool_name_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() in RETIRED_RESEARCH_TOOL_NAMES
    return _has_retired_research_tool_payload(value)


def _contract_key(row: Any) -> str:
    return (
        f"prompt_version={row['prompt_version']}|schema_version={row['schema_version']}|"
        f"validator_version={row['validator_version']}|artifact_version_hash={row['artifact_version_hash']}"
    )


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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
    "MATERIAL_FACT_TABLES",
    "NEWS_WORKER_ADVISORY_LOCK_KEYS",
    "NewsIntelHardCutCleanupAbort",
    "cleanup_news_intel_hard_cut",
    "news_intel_hard_cut_runtime_guard",
]
