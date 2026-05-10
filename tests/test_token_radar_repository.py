from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    _json_payload,
)


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    payload = _json_payload(
        {
            "price_json": {
                "price_quote": Decimal("2.564"),
                "nested": {"volume_24h_usd": Decimal("123.45")},
            },
            "score_json": {},
            "intent_json": {},
            "asset_json": {},
            "primary_venue_json": None,
            "target_json": {},
            "attention_json": {},
            "resolution_json": {},
            "market_json": {},
            "data_health_json": {},
            "source_event_ids_json": [],
        }
    )

    assert payload["price_json"].obj["price_quote"] == 2.564
    assert payload["price_json"].obj["nested"]["volume_24h_usd"] == 123.45


def test_latest_rows_limits_each_lane_independently():
    conn = FakeConn()

    rows = TokenRadarRepository(conn).latest_rows(
        window="5m",
        scope="all",
        limit=8,
        projection_version="token-radar-v5-auditable",
    )

    assert rows == []
    assert "PARTITION BY lane" in conn.sql
    assert "lane_rank <= %s" in conn.sql
    assert conn.params[-2:] == (8, 16)


def test_replace_rows_rejects_stale_projection_writer():
    conn = FakeStaleReplaceConn(existing_computed_at_ms=1_700_000_100_000)

    written = TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v5-auditable",
        window="5m",
        scope="all",
        computed_at_ms=1_700_000_000_000,
        rows=[],
        commit=False,
    )

    assert written is False
    assert not any("DELETE FROM token_radar_rows" in sql for sql in conn.sqls)


class FakeConn:
    sql = ""
    params = ()
    calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        self.sql = str(sql)
        self.params = params or ()
        return self

    def fetchone(self):
        return {"computed_at_ms": 1_700_000_000_000}

    def fetchall(self):
        return []


class FakeStaleReplaceConn:
    def __init__(self, *, existing_computed_at_ms: int):
        self.existing_computed_at_ms = existing_computed_at_ms
        self.sqls: list[str] = []

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        return self

    def fetchone(self):
        return {"computed_at_ms": self.existing_computed_at_ms}

    def commit(self):
        raise AssertionError("stale writer should not commit")
