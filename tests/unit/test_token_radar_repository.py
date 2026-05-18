from __future__ import annotations

from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    _json_payload,
)


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    snapshot = _valid_factor_snapshot(rank_score=Decimal("12.5"))
    snapshot["families"]["social_heat"]["facts"]["volume_24h_usd"] = Decimal("123.45")
    payload = _json_payload(
        {
            "factor_snapshot_json": snapshot,
            "intent_json": {},
            "asset_json": {},
            "primary_venue_json": None,
            "target_json": {},
            "data_health_json": {},
            "source_event_ids_json": [],
            "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        }
    )

    assert payload["factor_snapshot_json"].obj["composite"]["rank_score"] == 12.5
    assert payload["factor_snapshot_json"].obj["families"]["social_heat"]["facts"]["volume_24h_usd"] == 123.45


def test_replace_rows_insert_uses_factor_snapshot_columns_without_legacy_score_contract():
    conn = FakeReplaceConn()
    row = {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }

    TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v9-factor-snapshot",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_000_000,
        rows=[row],
        commit=False,
    )

    assert "factor_snapshot_json" in conn.insert_sql
    assert "factor_version" in conn.insert_sql
    assert "score_json" not in conn.insert_sql


def test_replace_rows_insert_materializes_listed_at_ms():
    conn = FakeReplaceConn()
    row = _valid_factor_row()

    TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_000_000,
        rows=[row],
        commit=False,
    )

    assert "listed_at_ms" in conn.insert_sql
    assert conn.insert_params["listed_at_ms"] == 1_778_000_000_000


def test_replace_rows_listed_at_lookup_uses_ordered_index_seek():
    conn = FakeReplaceConn()
    row = _valid_factor_row()

    TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_000_000,
        rows=[row],
        commit=False,
    )

    assert "LEFT JOIN LATERAL" in conn.listed_sql
    assert "ORDER BY history.computed_at_ms ASC" in conn.listed_sql
    assert "MIN(history.computed_at_ms)" not in conn.listed_sql
    assert "GROUP BY requested.target_type_key" not in conn.listed_sql


def test_replace_rows_requires_factor_snapshot_json_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]

    with pytest.raises(ValueError, match="factor_snapshot_json is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_empty_factor_snapshot_json_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"] = {}

    with pytest.raises(ValueError, match="factor_snapshot_json must be non-empty"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_requires_factor_version_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    del row["factor_version"]

    with pytest.raises(ValueError, match="factor_version is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_hard_gates_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["hard_gates"] = {"eligible_for_high_alert": True}

    with pytest.raises(ValueError, match="hard_gates"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_requires_v3_top_level_sections_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]["data_health"]

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.data_health is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_requires_v3_factor_families_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]["families"]["semantic_catalyst"]

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.semantic_catalyst is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_empty_v3_provenance_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["provenance"] = {}

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.provenance\.computed_at_ms is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_empty_v3_source_event_ids_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["provenance"]["source_event_ids"] = []

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.provenance\.source_event_ids is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_empty_v3_family_block_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["families"]["social_heat"] = {}

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.social_heat\.data_health is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_extra_v3_top_level_keys_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["nested"] = {"volume_24h_usd": 123.45}

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.nested is not allowed"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_extra_v3_family_keys_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["families"]["market_quality"] = {"facts": {"market_status": "fresh"}}

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.market_quality is not allowed"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_rejects_factor_snapshot_version_mismatch_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["schema_version"] = "token_factor_snapshot_legacy"

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.schema_version must match factor_version"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.insert_sql == ""


def test_replace_rows_delete_is_scoped_to_run_computed_at_ms():
    conn = FakeReplaceConn()

    TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v11-factor-alpha-gated",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_000_000,
        rows=[],
        commit=False,
    )

    assert "AND computed_at_ms = %s" in conn.delete_sql
    assert conn.delete_params == (
        "token-radar-v11-factor-alpha-gated",
        "1h",
        "all",
        1_778_000_000_000,
    )


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


def test_latest_rows_reads_materialized_listed_at_without_history_lateral():
    conn = FakeConn()

    TokenRadarRepository(conn).latest_rows(
        window="1h",
        scope="all",
        limit=50,
        projection_version="token-radar-v13-social-attention",
    )

    assert "LEFT JOIN LATERAL" not in conn.sql
    assert "token_radar_rows history" not in conn.sql


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


class FakeReplaceConn:
    def __init__(self) -> None:
        self.insert_sql = ""
        self.insert_params = {}
        self.delete_sql = ""
        self.delete_params = ()
        self.listed_sql = ""

    def execute(self, sql, params=None):
        text = str(sql)
        if "WITH requested(target_type_key, identity_id)" in text:
            self.listed_sql = text
        if "INSERT INTO token_radar_rows" in text:
            self.insert_sql = text
            self.insert_params = dict(params or {})
        if "DELETE FROM token_radar_rows" in text:
            self.delete_sql = text
            self.delete_params = params or ()
        return self

    def fetchone(self):
        return {"computed_at_ms": None}

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


def _valid_factor_row() -> dict[str, object]:
    return {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }


def _valid_factor_snapshot(*, rank_score: object = 12) -> dict[str, object]:
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {"target_type": "Asset", "target_id": "asset-1", "symbol": "BOV"},
        "market": {
            "event_anchor": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_000_000,
                "received_at_ms": 1_778_000_000_000,
                "source": "event_anchor",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.0,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": None,
                "liquidity_usd": None,
                "holders": None,
                "volume_24h_usd": None,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "decision_latest": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_030_000,
                "received_at_ms": 1_778_000_030_000,
                "source": "decision_latest",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.1,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 1_000_000,
                "liquidity_usd": 250_000,
                "holders": 1000,
                "volume_24h_usd": 12_000,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "families": {
            "social_heat": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.35,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.30,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.10,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
        },
        "gates": {
            "eligible_for_high_alert": False,
            "max_decision": "watch",
            "blocked_reasons": ["liquidity_below_high_alert_floor"],
            "risk_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {},
            "factor_ranks": {},
            "alpha_rank": None,
        },
        "composite": {
            "family_scores": {
                "social_heat": 80,
                "social_propagation": 80,
                "semantic_catalyst": 80,
                "timing_risk": 80,
            },
            "rank_score": rank_score,
            "recommended_decision": "discard",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_000_000},
    }
