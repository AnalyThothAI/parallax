from __future__ import annotations

import pytest

from parallax.domains.pulse_lab.repositories.pulse_evidence_source_repository import (
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


@pytest.mark.parametrize("max_age_ms", [0, -1, True, "3600000"])
def test_market_tick_lookup_rejects_malformed_max_age_before_sql(max_age_ms: object) -> None:
    conn = _Conn(row=None)

    with pytest.raises(ValueError, match="pulse_evidence_max_age_ms_required"):
        PulseEvidenceSourceRepository(conn).get_latest_market_tick(
            "chain_token",
            "asset-1",
            max_age_ms,  # type: ignore[arg-type]
            now_ms=1_800_000_100_000,
        )

    assert conn.sql == ""


@pytest.mark.parametrize("max_age_ms", [0, -1, True, "3600000"])
def test_market_tick_pricefeed_lookup_rejects_malformed_max_age_before_sql(max_age_ms: object) -> None:
    conn = _Conn(row=None)

    with pytest.raises(ValueError, match="pulse_evidence_max_age_ms_required"):
        PulseEvidenceSourceRepository(conn).get_latest_market_tick_by_pricefeed(
            "pf-test",
            max_age_ms,  # type: ignore[arg-type]
            now_ms=1_800_000_100_000,
        )

    assert conn.sql == ""


@pytest.mark.parametrize("max_age_ms", [0, -1, True, "3600000"])
def test_cex_detail_snapshot_lookup_rejects_malformed_max_age_before_sql(max_age_ms: object) -> None:
    conn = _Conn(row=None)

    with pytest.raises(ValueError, match="pulse_evidence_max_age_ms_required"):
        PulseEvidenceSourceRepository(conn).get_latest_cex_detail_snapshot(
            "cex_token",
            "cex_token:BTC",
            max_age_ms,  # type: ignore[arg-type]
            now_ms=1_800_000_100_000,
        )

    assert conn.sql == ""


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
