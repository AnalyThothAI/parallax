from __future__ import annotations

from contextlib import nullcontext
from typing import Any

ADVISORY_LOCK_KEY = 2026052107
TOKEN_RADAR_ROWS_TABLE = "token_radar_" "rows"
TOKEN_CAPTURE_TIER_TABLE = "token_capture_" "tier"
LEGACY_PRICE_TABLE = "price_" "observations"


class CexBinanceHardCutAbort(RuntimeError):
    """Raised when hard-cut cleanup safety gates fail before mutation."""


def cleanup_cex_binance_hard_cut(
    target: Any,
    *,
    dry_run: bool,
    execute: bool,
    min_binance_feeds: int,
    now_ms: int,
) -> dict[str, Any]:
    """Plan or execute the CEX Binance hard-cut cleanup SQL.

    ``target`` may be a psycopg connection or a repository/session object with
    a ``conn`` or ``connection`` attribute.
    """

    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute must be true")
    if min_binance_feeds < 0:
        raise ValueError("min_binance_feeds must be non-negative")

    conn = _connection_from(target)
    if dry_run:
        counts = _collect_counts(conn)
        return {
            "mode": "dry_run",
            "aborted": False,
            "min_binance_feeds": min_binance_feeds,
            "counts": counts,
            "planned_actions": counts,
            "constraint_validated": False,
        }

    with _transaction(conn):
        _execute(conn, "SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
        before_counts = _collect_counts(conn)
        binance_feeds = before_counts["binance_canonical_usdt_perp_feeds"]
        if binance_feeds < min_binance_feeds:
            raise CexBinanceHardCutAbort(
                "binance_canonical_usdt_perp_feeds "
                f"{binance_feeds} below min_binance_feeds {min_binance_feeds}"
            )

        executed_counts = _execute_cleanup(conn, now_ms=now_ms)
        after_counts = _collect_counts(conn)
        return {
            "mode": "execute",
            "aborted": False,
            "min_binance_feeds": min_binance_feeds,
            "counts": before_counts,
            "before_counts": before_counts,
            "executed_counts": executed_counts,
            "after_counts": after_counts,
            "constraint_validated": True,
        }


def _connection_from(target: Any) -> Any:
    if hasattr(target, "execute"):
        return target
    for attr in ("conn", "connection"):
        conn = getattr(target, attr, None)
        if conn is not None and hasattr(conn, "execute"):
            return conn
    raise TypeError("target must be a connection or expose conn/connection.execute")


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _collect_counts(conn: Any) -> dict[str, int]:
    return {name: _select_count(conn, sql) for name, sql in COUNT_SQL.items()}


def _select_count(conn: Any, sql: str) -> int:
    row = _execute(conn, sql).fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        if "count" in row:
            return int(row["count"] or 0)
        return int(next(iter(row.values())) or 0)
    if hasattr(row, "__getitem__"):
        return int(row[0] or 0)
    return int(row or 0)


def _execute_cleanup(conn: Any, *, now_ms: int) -> dict[str, int]:
    params = {"now_ms": now_ms}
    executed: dict[str, int] = {}
    for name, sql in CLEANUP_SQL:
        result = _execute(conn, sql, params)
        executed[name] = _rowcount(result)
    return executed


def _execute(conn: Any, sql: str, params: Any | None = None) -> Any:
    if params is None:
        return conn.execute(sql)
    return conn.execute(sql, params)


def _rowcount(result: Any) -> int:
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None or rowcount < 0:
        return 0
    return int(rowcount)


BINANCE_CANONICAL_FEED_WHERE = """
    subject_type = 'CexToken'
    AND provider = 'binance'
    AND feed_type = 'cex_swap'
    AND quote_symbol = 'USDT'
    AND status = 'canonical'
"""


COUNT_SQL: dict[str, str] = {
    "binance_canonical_usdt_perp_feeds": f"""
        SELECT COUNT(*)::bigint AS binance_canonical_usdt_perp_feeds
        FROM price_feeds
        WHERE {BINANCE_CANONICAL_FEED_WHERE}
    """,
    "current_resolutions_to_repoint": f"""
        WITH binance_feed AS (
          SELECT DISTINCT ON (subject_id)
            subject_id AS target_id,
            pricefeed_id
          FROM price_feeds
          WHERE {BINANCE_CANONICAL_FEED_WHERE}
          ORDER BY subject_id, updated_at_ms DESC, native_market_id ASC
        )
        SELECT COUNT(*)::bigint AS current_resolutions_to_repoint
        FROM token_intent_resolutions tir
        JOIN binance_feed ON binance_feed.target_id = tir.target_id
        WHERE tir.is_current = true
          AND tir.target_type = 'CexToken'
          AND COALESCE(tir.pricefeed_id, '') <> binance_feed.pricefeed_id
    """,
    "current_resolutions_to_remove": f"""
        WITH binance_feed AS (
          SELECT DISTINCT ON (subject_id)
            subject_id AS target_id,
            pricefeed_id
          FROM price_feeds
          WHERE {BINANCE_CANONICAL_FEED_WHERE}
          ORDER BY subject_id, updated_at_ms DESC, native_market_id ASC
        )
        SELECT COUNT(*)::bigint AS current_resolutions_to_remove
        FROM token_intent_resolutions tir
        LEFT JOIN binance_feed ON binance_feed.target_id = tir.target_id
        WHERE tir.is_current = true
          AND tir.target_type = 'CexToken'
          AND binance_feed.target_id IS NULL
    """,
    "token_radar_rows_to_delete": f"""
        SELECT COUNT(*)::bigint AS token_radar_rows_to_delete
        FROM {TOKEN_RADAR_ROWS_TABLE}
        WHERE target_type = 'CexToken'
           OR pricefeed_id LIKE 'pricefeed:cex:okx:%'
    """,
    "enriched_events_to_detach": """
        SELECT COUNT(*)::bigint AS enriched_events_to_detach
        FROM enriched_events
        WHERE tick_id IN (
          SELECT tick_id
          FROM market_ticks
          WHERE target_type = 'cex_symbol'
            AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
        )
    """,
    "backfill_jobs_to_mark_failed": """
        SELECT COUNT(*)::bigint AS backfill_jobs_to_mark_failed
        FROM event_anchor_backfill_jobs
        WHERE target_type = 'cex_symbol'
          AND target_id LIKE 'okx:%'
          AND status = 'pending'
    """,
    "okx_market_ticks_to_delete": """
        SELECT COUNT(*)::bigint AS okx_market_ticks_to_delete
        FROM market_ticks
        WHERE target_type = 'cex_symbol'
          AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
    """,
    "okx_token_capture_tier_to_delete": f"""
        SELECT COUNT(*)::bigint AS okx_token_capture_tier_to_delete
        FROM {TOKEN_CAPTURE_TIER_TABLE}
        WHERE target_type = 'cex_symbol'
          AND target_id LIKE 'okx:%'
    """,
    "okx_legacy_price_rows_to_delete": f"""
        SELECT COUNT(*)::bigint AS okx_legacy_price_rows_to_delete
        FROM {LEGACY_PRICE_TABLE}
        WHERE provider IN ('okx_cex', 'okx')
           OR pricefeed_id LIKE 'pricefeed:cex:okx:%'
    """,
    "okx_price_feeds_to_delete": """
        SELECT COUNT(*)::bigint AS okx_price_feeds_to_delete
        FROM price_feeds
        WHERE provider = 'okx'
          AND feed_type LIKE 'cex_%'
    """,
    "cex_tokens_to_delete": """
        SELECT COUNT(*)::bigint AS cex_tokens_to_delete
        FROM cex_tokens
        WHERE NOT EXISTS (
          SELECT 1
          FROM price_feeds
          WHERE price_feeds.subject_type = 'CexToken'
            AND price_feeds.subject_id = cex_tokens.cex_token_id
            AND price_feeds.provider = 'binance'
            AND price_feeds.feed_type = 'cex_swap'
            AND price_feeds.quote_symbol = 'USDT'
            AND price_feeds.status = 'canonical'
        )
    """,
}


REPOINT_CURRENT_RESOLUTIONS_SQL = """
    WITH clock AS (
      SELECT %(now_ms)s::bigint AS now_ms
    ),
    binance_feed AS (
      SELECT DISTINCT ON (subject_id)
        subject_id AS target_id,
        pricefeed_id
      FROM price_feeds
      WHERE subject_type = 'CexToken'
        AND provider = 'binance'
        AND feed_type = 'cex_swap'
        AND quote_symbol = 'USDT'
        AND status = 'canonical'
      ORDER BY subject_id, updated_at_ms DESC, native_market_id ASC
    ),
    to_repoint AS (
      SELECT tir.*, binance_feed.pricefeed_id AS binance_pricefeed_id
      FROM token_intent_resolutions tir
      JOIN binance_feed ON binance_feed.target_id = tir.target_id
      WHERE tir.is_current = true
        AND tir.target_type = 'CexToken'
        AND COALESCE(tir.pricefeed_id, '') <> binance_feed.pricefeed_id
    ),
    superseded AS (
      UPDATE token_intent_resolutions tir
      SET record_status = 'superseded',
          is_current = false,
          superseded_at_ms = (SELECT now_ms FROM clock)
      FROM to_repoint
      WHERE tir.resolution_id = to_repoint.resolution_id
      RETURNING to_repoint.*
    )
    INSERT INTO token_intent_resolutions(
      resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
      target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
      lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
    )
    SELECT
      'cex-binance-hard-cut-repointed:' || resolution_id,
      intent_id, event_id, resolution_status, resolver_policy_version,
      target_type, target_id, binance_pricefeed_id,
      COALESCE(reason_codes_json, '[]'::jsonb) || '["cex_binance_hard_cut_repointed"]'::jsonb,
      candidate_ids_json, lookup_keys_json,
      'current', true, (SELECT now_ms FROM clock), (SELECT now_ms FROM clock)
    FROM superseded
    ON CONFLICT (resolution_id) DO NOTHING
"""


REMOVE_CURRENT_RESOLUTIONS_SQL = """
    WITH clock AS (
      SELECT %(now_ms)s::bigint AS now_ms
    ),
    binance_feed AS (
      SELECT DISTINCT ON (subject_id)
        subject_id AS target_id,
        pricefeed_id
      FROM price_feeds
      WHERE subject_type = 'CexToken'
        AND provider = 'binance'
        AND feed_type = 'cex_swap'
        AND quote_symbol = 'USDT'
        AND status = 'canonical'
      ORDER BY subject_id, updated_at_ms DESC, native_market_id ASC
    ),
    to_remove AS (
      SELECT tir.*
      FROM token_intent_resolutions tir
      LEFT JOIN binance_feed ON binance_feed.target_id = tir.target_id
      WHERE tir.is_current = true
        AND tir.target_type = 'CexToken'
        AND binance_feed.target_id IS NULL
    ),
    superseded AS (
      UPDATE token_intent_resolutions tir
      SET record_status = 'superseded',
          is_current = false,
          superseded_at_ms = (SELECT now_ms FROM clock)
      FROM to_remove
      WHERE tir.resolution_id = to_remove.resolution_id
      RETURNING to_remove.*
    )
    INSERT INTO token_intent_resolutions(
      resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
      target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
      lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
    )
    SELECT
      'cex-binance-hard-cut-removed:' || resolution_id,
      intent_id, event_id, 'NIL', resolver_policy_version,
      NULL, NULL, NULL,
      COALESCE(reason_codes_json, '[]'::jsonb) || '["cex_binance_hard_cut_removed"]'::jsonb,
      candidate_ids_json, lookup_keys_json,
      'current', true, (SELECT now_ms FROM clock), (SELECT now_ms FROM clock)
    FROM superseded
    ON CONFLICT (resolution_id) DO NOTHING
"""


CLEANUP_SQL: tuple[tuple[str, str], ...] = (
    ("current_resolutions_repointed", REPOINT_CURRENT_RESOLUTIONS_SQL),
    ("current_resolutions_removed", REMOVE_CURRENT_RESOLUTIONS_SQL),
    (
        "token_radar_rows_deleted",
        f"""
        DELETE FROM {TOKEN_RADAR_ROWS_TABLE}
        WHERE target_type = 'CexToken'
           OR pricefeed_id LIKE 'pricefeed:cex:okx:%'
        """,
    ),
    (
        "enriched_events_detached",
        """
        UPDATE enriched_events
        SET tick_id = NULL,
            tick_lag_ms = NULL,
            capture_method = 'unavailable',
            capture_reason = 'cex_okx_removed'
        WHERE tick_id IN (
          SELECT tick_id
          FROM market_ticks
          WHERE target_type = 'cex_symbol'
            AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
        )
        """,
    ),
    (
        "backfill_jobs_failed",
        """
        UPDATE event_anchor_backfill_jobs
        SET status = 'failed',
            last_reason = 'cex_okx_removed',
            updated_at_ms = %(now_ms)s
        WHERE target_type = 'cex_symbol'
          AND target_id LIKE 'okx:%'
          AND status = 'pending'
        """,
    ),
    (
        "okx_market_ticks_deleted",
        """
        DELETE FROM market_ticks
        WHERE target_type = 'cex_symbol'
          AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
        """,
    ),
    (
        "okx_token_capture_tier_deleted",
        f"""
        DELETE FROM {TOKEN_CAPTURE_TIER_TABLE}
        WHERE target_type = 'cex_symbol'
          AND target_id LIKE 'okx:%'
        """,
    ),
    (
        "okx_legacy_price_rows_deleted",
        f"""
        DELETE FROM {LEGACY_PRICE_TABLE}
        WHERE provider IN ('okx_cex', 'okx')
           OR pricefeed_id LIKE 'pricefeed:cex:okx:%'
        """,
    ),
    (
        "okx_price_feeds_deleted",
        """
        DELETE FROM price_feeds
        WHERE provider = 'okx'
          AND feed_type LIKE 'cex_%'
        """,
    ),
    (
        "cex_tokens_deleted",
        """
        DELETE FROM cex_tokens
        WHERE NOT EXISTS (
          SELECT 1
          FROM price_feeds
          WHERE price_feeds.subject_type = 'CexToken'
            AND price_feeds.subject_id = cex_tokens.cex_token_id
            AND price_feeds.provider = 'binance'
            AND price_feeds.feed_type = 'cex_swap'
            AND price_feeds.quote_symbol = 'USDT'
            AND price_feeds.status = 'canonical'
        )
        """,
    ),
    (
        "market_ticks_source_provider_check_validated",
        """
        ALTER TABLE market_ticks
          VALIDATE CONSTRAINT market_ticks_source_provider_check
        """,
    ),
)
