from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.asset_market.services.cex_binance_hard_cut_cleanup import (
    CexBinanceHardCutAbort,
    cleanup_cex_binance_hard_cut,
)

TOKEN_RADAR_CURRENT_ROWS_TABLE = "token_radar_current_rows"
TOKEN_CAPTURE_TIER_TABLE = "token_capture_tier"
LEGACY_PRICE_TABLE = "price" + "_observations"


def test_dry_run_reports_planned_counts_without_lock_or_mutation() -> None:
    conn = RecordingConn(
        counts={
            "binance_canonical_usdt_perp_feeds": 512,
            "current_resolutions_to_repoint": 7,
            "current_resolutions_to_remove": 3,
            "token_radar_current_rows_to_reset": 11,
            "token_radar_rank_history_to_reset": 12,
            "token_radar_snapshot_audit_to_reset": 13,
            "okx_market_ticks_to_delete": 13,
        }
    )

    result = cleanup_cex_binance_hard_cut(
        conn,
        dry_run=True,
        execute=False,
        min_binance_feeds=400,
        now_ms=1_779_321_600_000,
    )

    assert result["mode"] == "dry_run"
    assert result["aborted"] is False
    assert result["counts"]["binance_canonical_usdt_perp_feeds"] == 512
    assert result["counts"]["current_resolutions_to_repoint"] == 7
    assert result["counts"]["current_resolutions_to_remove"] == 3
    assert result["counts"]["token_radar_current_rows_to_reset"] == 11
    assert result["counts"]["token_radar_rank_history_to_reset"] == 12
    assert result["counts"]["token_radar_snapshot_audit_to_reset"] == 13
    assert result["counts"]["okx_market_ticks_to_delete"] == 13
    assert result["token_radar_storage"]["command"] == "ops reset-token-radar-postgres-hard-cut --execute"
    assert conn.transaction_entries == 0
    assert not _has_statement(conn.sqls, "pg_advisory_xact_lock")
    assert not _has_mutation(conn.sqls)


def test_cleanup_sql_does_not_reference_removed_legacy_price_table() -> None:
    conn = RecordingConn(counts={"binance_canonical_usdt_perp_feeds": 512})

    cleanup_cex_binance_hard_cut(
        conn,
        dry_run=False,
        execute=True,
        min_binance_feeds=400,
        now_ms=1_779_321_600_000,
    )

    assert not _has_statement(conn.sqls, LEGACY_PRICE_TABLE)


def test_execute_only_passes_params_to_now_ms_sql_and_escapes_literal_percent() -> None:
    conn = RecordingConn(counts={"binance_canonical_usdt_perp_feeds": 512})

    cleanup_cex_binance_hard_cut(
        conn,
        dry_run=False,
        execute=True,
        min_binance_feeds=400,
        now_ms=1_779_321_600_000,
    )

    cleanup_calls = list(zip(conn.sqls, conn.params, strict=True))[1:]
    for sql, params in cleanup_calls:
        if "%(now_ms)s" in sql:
            assert params == {"now_ms": 1_779_321_600_000}
            assert "LIKE 'okx:%'" not in sql
        else:
            assert params is None


def test_execute_acquires_transaction_lock_and_aborts_below_min_binance_feeds() -> None:
    conn = RecordingConn(counts={"binance_canonical_usdt_perp_feeds": 12})

    with pytest.raises(CexBinanceHardCutAbort, match="below min_binance_feeds"):
        cleanup_cex_binance_hard_cut(
            conn,
            dry_run=False,
            execute=True,
            min_binance_feeds=400,
            now_ms=1_779_321_600_000,
        )

    assert conn.transaction_entries == 1
    assert _first_statement_index(conn.sqls, "pg_advisory_xact_lock") == 0
    assert not _has_mutation(conn.sqls)


def test_execute_supersedes_current_cex_resolutions_and_inserts_replacements() -> None:
    conn = RecordingConn(counts={"binance_canonical_usdt_perp_feeds": 512})

    result = cleanup_cex_binance_hard_cut(
        conn,
        dry_run=False,
        execute=True,
        min_binance_feeds=400,
        now_ms=1_779_321_600_000,
    )

    assert result["mode"] == "execute"
    assert result["constraint_validated"] is True
    lifecycle_sql = "\n".join(sql for sql in conn.sqls if "token_intent_resolutions" in sql and "WITH clock AS" in sql)
    assert "to_repoint AS" in lifecycle_sql
    assert "cex_binance_hard_cut_repointed" in lifecycle_sql
    assert "to_remove AS" in lifecycle_sql
    assert "cex_binance_hard_cut_removed" in lifecycle_sql
    assert "UPDATE token_intent_resolutions" in lifecycle_sql
    assert "record_status = 'superseded'" in lifecycle_sql
    assert "is_current = false" in lifecycle_sql
    assert "INSERT INTO token_intent_resolutions" in lifecycle_sql
    assert "resolution_status" in lifecycle_sql
    assert "'NIL'" in lifecycle_sql
    assert "SET pricefeed_id" not in lifecycle_sql


def test_execute_runs_cleanup_in_fk_safe_order_and_validates_constraint() -> None:
    conn = RecordingConn(counts={"binance_canonical_usdt_perp_feeds": 512})

    cleanup_cex_binance_hard_cut(
        conn,
        dry_run=False,
        execute=True,
        min_binance_feeds=400,
        now_ms=1_779_321_600_000,
    )

    assert _first_statement_index(conn.sqls, "pg_advisory_xact_lock") == 0
    assert not _has_statement(conn.sqls, f"DELETE FROM {TOKEN_RADAR_CURRENT_ROWS_TABLE}")
    assert not _has_statement(conn.sqls, "DELETE FROM token_radar_rank_history")
    assert not _has_statement(conn.sqls, "DELETE FROM token_radar_snapshot_audit")
    assert _first_statement_index(conn.sqls, "UPDATE token_intent_resolutions") < _first_statement_index(
        conn.sqls, "UPDATE enriched_events"
    )
    assert _first_statement_index(conn.sqls, "UPDATE enriched_events") < _first_statement_index(
        conn.sqls, "UPDATE event_anchor_backfill_jobs"
    )
    assert _first_statement_index(conn.sqls, "UPDATE event_anchor_backfill_jobs") < _first_statement_index(
        conn.sqls, "DELETE FROM market_ticks"
    )
    assert _first_statement_index(conn.sqls, "DELETE FROM market_ticks") < _first_statement_index(
        conn.sqls, f"DELETE FROM {TOKEN_CAPTURE_TIER_TABLE}"
    )
    assert _first_statement_index(conn.sqls, f"DELETE FROM {TOKEN_CAPTURE_TIER_TABLE}") < _first_statement_index(
        conn.sqls, "DELETE FROM price_feeds"
    )
    assert _first_statement_index(conn.sqls, "DELETE FROM price_feeds") < _first_statement_index(
        conn.sqls, "DELETE FROM cex_tokens"
    )
    assert _first_statement_index(conn.sqls, "DELETE FROM cex_tokens") < _first_statement_index(
        conn.sqls, "VALIDATE CONSTRAINT market_ticks_source_provider_check"
    )


class RecordingConn:
    def __init__(self, *, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {}
        self.sqls: list[str] = []
        self.params: list[object] = []
        self.transaction_entries = 0

    def execute(self, sql: str, params: object | None = None) -> RecordingResult:
        self.sqls.append(_normalize_sql(sql))
        self.params.append(params)
        return RecordingResult(self._count_for(sql))

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)

    def _count_for(self, sql: str) -> int:
        normalized = _normalize_sql(sql)
        for key, value in self.counts.items():
            if f"AS {key}" in normalized:
                return value
        return 0


class RecordingTransaction:
    def __init__(self, conn: RecordingConn) -> None:
        self.conn = conn

    def __enter__(self) -> RecordingTransaction:
        self.conn.transaction_entries += 1
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class RecordingResult:
    def __init__(self, count: int) -> None:
        self.count = count
        self.rowcount = count

    def fetchone(self) -> dict[str, int]:
        return {"count": self.count}


def _normalize_sql(sql: str) -> str:
    return " ".join(str(sql).split())


def _has_statement(sqls: list[str], needle: str) -> bool:
    return any(needle in sql for sql in sqls)


def _has_mutation(sqls: list[str]) -> bool:
    mutation_prefixes = ("UPDATE ", "DELETE ", "INSERT ", "ALTER TABLE ")
    return any(sql.startswith(mutation_prefixes) for sql in sqls)


def _first_statement_index(sqls: list[str], needle: str) -> int:
    for index, sql in enumerate(sqls):
        if needle in sql:
            return index
    raise AssertionError(f"statement not found: {needle}")
