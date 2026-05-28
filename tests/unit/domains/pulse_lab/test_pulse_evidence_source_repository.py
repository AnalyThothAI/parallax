from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_evidence_source_repository import (
    PulseEvidenceSourceRepository,
)


def test_cex_detail_snapshot_lookup_uses_current_cex_token_target_id() -> None:
    conn = _Conn(
        row={
            "snapshot_id": "cex-detail:binance:BTCUSDT",
            "target_type": "CexToken",
            "target_id": "cex_token:BTC",
            "exchange": "binance",
            "native_market_id": "BTCUSDT",
            "computed_at_ms": 1_800_000_000_000,
        }
    )

    snapshot = PulseEvidenceSourceRepository(conn).get_latest_cex_detail_snapshot(
        "cex_token",
        "cex_token:BTC",
        3_600_000,
        now_ms=1_800_000_100_000,
    )

    assert snapshot["snapshot_id"] == "cex-detail:binance:BTCUSDT"
    assert "target_id = %s" in conn.sql
    assert conn.params == ["cex_token:BTC", 1_799_996_500_000]


class _Conn:
    def __init__(self, *, row):
        self.row = row
        self.sql = ""
        self.params = []

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = list(params or [])
        return self

    def fetchone(self):
        return self.row
