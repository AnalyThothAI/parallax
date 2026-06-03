from __future__ import annotations

from parallax.domains.cex_market_intel.repositories.cex_detail_snapshot_repository import (
    CexDetailSnapshotRepository,
    _detail_payload_hash,
)


def test_detail_payload_hash_ignores_computed_at_and_computed_source_ref_timestamps():
    first = _snapshot(computed_at_ms=1_778_000_000_000, observed_at_ms=None)
    second = _snapshot(computed_at_ms=1_778_000_999_999, observed_at_ms=None)

    assert _detail_payload_hash(first) == _detail_payload_hash(second)


def test_detail_payload_hash_keeps_provider_observed_market_freshness():
    first = _snapshot(computed_at_ms=1_778_000_000_000, observed_at_ms=1_778_000_000_123)
    second = _snapshot(computed_at_ms=1_778_000_000_000, observed_at_ms=1_778_000_000_456)

    assert _detail_payload_hash(first) != _detail_payload_hash(second)


def test_upsert_many_returns_changed_rowcount_and_gates_on_payload_hash():
    conn = _RecordingConn(rowcounts=[1, 0])
    first = _snapshot(computed_at_ms=1_778_000_000_000)
    second = _snapshot(computed_at_ms=1_778_000_999_999)

    written = CexDetailSnapshotRepository(conn).upsert_many([first, second])

    assert written == 1
    assert conn.commits == 1
    all_sql = "\n".join(conn.sql_calls)
    assert "payload_hash" in all_sql
    assert (
        "WHERE cex_detail_snapshots.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash"
        in all_sql
    )


def test_computed_at_change_only_does_not_update_detail_serving_row():
    conn = _RecordingConn(rowcounts=[1, 0])
    repo = CexDetailSnapshotRepository(conn)

    first = _snapshot(computed_at_ms=1_778_000_000_000)
    second = _snapshot(computed_at_ms=1_778_000_999_999)

    first_written = repo.upsert_snapshot(first)
    second_written = repo.upsert_snapshot(second)

    assert _detail_payload_hash(first) == _detail_payload_hash(second)
    assert first_written == 1
    assert second_written == 0


def _snapshot(*, computed_at_ms: int, observed_at_ms: int | None = None) -> dict:
    source_observed_at_ms = observed_at_ms or computed_at_ms
    return {
        "snapshot_id": "cex-detail:binance:BTCUSDT",
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "exchange": "binance",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "status": "ready",
        "baseline_status": "ready",
        "coinglass_status": "ready",
        "price_usd": 72_000.0,
        "mark_price": 72_001.0,
        "funding_rate": 0.0001,
        "volume_24h_usd": 1_000_000.0,
        "open_interest_usd": 2_000_000.0,
        "oi_change_pct_1h": 10.0,
        "oi_change_pct_4h": 12.0,
        "oi_change_pct_24h": 25.0,
        "cvd_delta_1h": 100.0,
        "cvd_delta_4h": 250.0,
        "cvd_delta_24h": 500.0,
        "long_short_ratio": 1.2,
        "top_trader_position_ratio": 1.4,
        "level_bands": [{"kind": "resistance", "price": 73_000.0, "size": 2_000_000.0}],
        "degraded_reasons": [],
        "source_refs": [
            {
                "ref_id": "market:cex:binance:BTCUSDT",
                "ref_type": "market",
                "source_table": "cex_detail_snapshots",
                "source_id": "pf-btc",
                "observed_at_ms": source_observed_at_ms,
                "quality": "high",
            }
        ],
        "observed_at_ms": observed_at_ms,
        "computed_at_ms": computed_at_ms,
    }


class _RecordingCursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _RecordingConn:
    def __init__(self, *, rowcounts: list[int]) -> None:
        self.sql_calls: list[str] = []
        self.params_calls: list[tuple] = []
        self.rowcounts = list(rowcounts)
        self.commits = 0

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        self.params_calls.append(tuple(params or ()))
        return _RecordingCursor(self.rowcounts.pop(0))

    def commit(self):
        self.commits += 1
