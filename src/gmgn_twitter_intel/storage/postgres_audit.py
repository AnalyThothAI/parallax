from __future__ import annotations

from typing import Any

CORE_TABLES = (
    "raw_frames",
    "events",
    "event_entities",
    "assets",
    "asset_aliases",
    "asset_venues",
    "asset_mentions",
    "asset_attributions",
    "tokens",
    "token_market_snapshots",
    "token_market_observations",
    "asset_market_snapshots",
    "enrichment_jobs",
    "social_event_extractions",
    "harness_snapshots",
    "token_signal_snapshots",
    "notifications",
)

PROJECTION_TABLES = (
    "projection_offsets",
    "projection_runs",
    "projection_dirty_ranges",
    "asset_attention_buckets",
    "asset_attention_bucket_authors",
    "asset_flow_window_snapshots",
)

FOREIGN_KEY_CHECKS = {
    "event_entities_missing_events": """
        SELECT COUNT(*) AS count
        FROM event_entities child
        LEFT JOIN events parent ON parent.event_id = child.event_id
        WHERE parent.event_id IS NULL
    """,
    "asset_mentions_missing_events": """
        SELECT COUNT(*) AS count
        FROM asset_mentions child
        LEFT JOIN events parent ON parent.event_id = child.event_id
        WHERE parent.event_id IS NULL
    """,
    "asset_attributions_missing_events": """
        SELECT COUNT(*) AS count
        FROM asset_attributions child
        LEFT JOIN events parent ON parent.event_id = child.event_id
        WHERE parent.event_id IS NULL
    """,
    "asset_attributions_missing_assets": """
        SELECT COUNT(*) AS count
        FROM asset_attributions child
        LEFT JOIN assets parent ON parent.asset_id = child.asset_id
        WHERE parent.asset_id IS NULL
    """,
    "market_snapshots_missing_tokens": """
        SELECT COUNT(*) AS count
        FROM token_market_snapshots child
        LEFT JOIN tokens parent ON parent.token_id = child.token_id
        WHERE parent.token_id IS NULL
    """,
    "harness_outcomes_missing_snapshots": """
        SELECT COUNT(*) AS count
        FROM harness_outcomes child
        LEFT JOIN harness_snapshots parent ON parent.snapshot_id = child.snapshot_id
        WHERE parent.snapshot_id IS NULL
    """,
}


HOT_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "name": "recent_all",
        "sql": """
            SELECT event_id
            FROM events
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT 50
        """,
        "params": (),
    },
    {
        "name": "recent_watched",
        "sql": """
            SELECT event_id
            FROM events
            WHERE is_watched = true
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT 50
        """,
        "params": (),
    },
    {
        "name": "search_fts",
        "sql": """
            WITH query AS (SELECT websearch_to_tsquery('simple', %s) AS tsq)
            SELECT e.event_id
            FROM events e, query
            WHERE e.search_tsv @@ query.tsq
            ORDER BY ts_rank_cd(e.search_tsv, query.tsq) DESC, e.received_at_ms DESC, e.event_id DESC
            LIMIT 20
        """,
        "params": ("pepe",),
    },
    {
        "name": "asset_flow_5m_shape",
        "sql": """
            SELECT aa.asset_id, COUNT(DISTINCT aa.event_id) AS post_count
            FROM asset_attributions aa
            WHERE aa.decision_time_ms >= %s
              AND aa.decision_time_ms < %s
              AND aa.attribution_status IN ('direct', 'selected', 'unresolved', 'ambiguous')
              AND aa.confidence > 0
            GROUP BY aa.asset_id
            ORDER BY post_count DESC, aa.asset_id DESC
            LIMIT 50
        """,
        "params": (0, 300_000),
    },
    {
        "name": "asset_posts_recent",
        "sql": """
            SELECT aa.event_id
            FROM asset_attributions aa
            WHERE aa.asset_id = (
                SELECT asset_id FROM assets ORDER BY first_seen_ms DESC, asset_id DESC LIMIT 1
            )
              AND aa.attribution_status IN ('direct', 'selected', 'unresolved', 'ambiguous')
              AND aa.confidence > 0
            ORDER BY aa.decision_time_ms DESC, aa.event_id DESC
            LIMIT 50
        """,
        "params": (),
    },
)


class PostgresOperationalAudit:
    def __init__(self, conn: Any):
        self.conn = conn

    def run(self) -> dict[str, Any]:
        counts = self._counts(CORE_TABLES)
        projection_schema = self._table_presence(PROJECTION_TABLES)
        foreign_key_checks = self._foreign_key_checks()
        migration_version = self._migration_version()
        orphan_count = sum(int(value) for value in foreign_key_checks.values())
        return {
            "ok": orphan_count == 0 and all(projection_schema.values()),
            "engine": "postgresql",
            "migration_version": migration_version,
            "counts": counts,
            "projection_schema": projection_schema,
            "foreign_key_checks": foreign_key_checks,
        }

    def _counts(self, table_names: tuple[str, ...]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table_name in table_names:
            if not self._table_exists(table_name):
                counts[table_name] = -1
                continue
            row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
            counts[table_name] = int(row["count"] if row else 0)
        return counts

    def _table_presence(self, table_names: tuple[str, ...]) -> dict[str, bool]:
        return {table_name: self._table_exists(table_name) for table_name in table_names}

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 AS ok
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _foreign_key_checks(self) -> dict[str, int]:
        checks: dict[str, int] = {}
        for name, sql in FOREIGN_KEY_CHECKS.items():
            row = self.conn.execute(sql).fetchone()
            checks[name] = int(row["count"] if row else 0)
        return checks

    def _migration_version(self) -> str | None:
        row = self.conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return str(row["version_num"]) if row else None


class PostgresQueryAudit:
    def __init__(self, conn: Any):
        self.conn = conn

    def run(self, *, analyze: bool = False) -> dict[str, Any]:
        queries = [self._explain(item, analyze=analyze) for item in HOT_QUERIES]
        return {
            "ok": all(item["ok"] for item in queries),
            "engine": "postgresql",
            "analyze": bool(analyze),
            "queries": queries,
        }

    def _explain(self, item: dict[str, Any], *, analyze: bool) -> dict[str, Any]:
        prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)" if analyze else "EXPLAIN (FORMAT TEXT)"
        try:
            rows = self.conn.execute(f"{prefix} {item['sql']}", item["params"]).fetchall()
            return {
                "ok": True,
                "name": item["name"],
                "plan": [_plan_line(row) for row in rows],
            }
        except Exception as exc:
            return {
                "ok": False,
                "name": item["name"],
                "error": type(exc).__name__,
                "detail": str(exc),
                "plan": [],
            }


class ProjectionValidationAudit:
    def __init__(self, conn: Any):
        self.conn = conn

    def run(self, *, sample: int) -> dict[str, Any]:
        sample_size = max(0, int(sample))
        snapshot_rows = self.conn.execute(
            """
            SELECT snapshot_id, asset_id
            FROM asset_flow_window_snapshots
            ORDER BY decision_time_ms DESC, rank ASC
            LIMIT %s
            """,
            (sample_size,),
        ).fetchall()
        missing_tokens = 0
        for row in snapshot_rows:
            asset = self.conn.execute(
                "SELECT 1 AS ok FROM assets WHERE asset_id = %s",
                (row["asset_id"],),
            ).fetchone()
            if asset is None:
                missing_tokens += 1
        offsets = self.conn.execute("SELECT COUNT(*) AS count FROM projection_offsets").fetchone()
        status = "ready" if int(offsets["count"] if offsets else 0) > 0 else "projection_missing"
        return {
            "ok": missing_tokens == 0,
            "status": status,
            "sample": sample_size,
            "checked_count": len(snapshot_rows),
            "mismatch_count": missing_tokens,
            "checks": {
                "asset_flow_window_snapshots_missing_assets": missing_tokens,
            },
        }


def _plan_line(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("QUERY PLAN") or row.get("?column?") or next(iter(row.values()), ""))
    return str(row[0])
