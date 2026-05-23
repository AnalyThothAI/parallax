from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    _json_payload,
    _payload_hash,
    _runtime_row_payload,
)


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    snapshot = _valid_factor_snapshot(rank_score=12.5)
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


def test_publish_rows_upserts_changed_current_row_and_writes_change_history_without_legacy_table():
    conn = FakePublishConn()
    row = _valid_factor_row()

    written = TokenRadarRepository(conn).publish_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_000_000,
        rows=[row],
        commit=False,
    )

    joined_sql = "\n".join(conn.sqls)
    assert written is True
    assert "INSERT INTO token_radar_current_rows" in joined_sql
    assert 'ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id)' in joined_sql
    assert "DELETE FROM token_radar_current_rows" not in joined_sql
    assert "INSERT INTO token_radar_rank_history" in joined_sql
    assert "INSERT INTO token_radar_snapshot_audit" in joined_sql
    assert "token_radar_rows" not in joined_sql
    assert conn.current_insert_params["target_type_key"] == "Asset"
    assert conn.current_insert_params["identity_id"] == "asset-1"
    assert conn.current_insert_params["payload_hash"]
    assert conn.current_insert_params["listed_at_ms"] == 1_778_000_000_000
    assert conn.rank_history_params["target_type_key"] == "Asset"
    assert conn.rank_history_params["identity_id"] == "asset-1"
    assert conn.rank_history_params["payload_hash"] == conn.current_insert_params["payload_hash"]
    assert conn.rank_history_params["recorded_at_ms"] == 1_778_000_000_000
    assert conn.rank_history_params["previous_rank"] is None
    assert conn.rank_history_params["rank_delta"] is None
    assert conn.rank_history_params["rank_score"] == 12.0
    assert conn.snapshot_audit_params["snapshot_id"] == "row-factor-1"
    assert conn.snapshot_audit_params["audit_reason"] == "rank_enter"
    assert conn.snapshot_audit_params["recorded_at_ms"] == 1_778_000_000_000


def test_publish_rows_skips_history_and_audit_when_payload_hash_is_unchanged():
    row = _valid_factor_row()
    existing_payload = _payload_hash(
        _runtime_row_payload(
            row,
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            listed_at_ms=1_778_000_000_000,
        )
    )
    conn = FakePublishConn(
        existing_current={
            "row_id": "row-factor-existing",
            "projection_version": "token-radar-v13-social-attention",
            "window": "1h",
            "scope": "all",
            "lane": "resolved",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": existing_payload,
            "rank": 1,
            "decision": "discard",
        }
    )

    written = TokenRadarRepository(conn).publish_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=1_778_000_060_000,
        rows=[row],
        commit=False,
    )

    assert written is True
    assert conn.current_insert_params["payload_hash"] == existing_payload
    assert conn.rank_history_params == {}
    assert conn.snapshot_audit_params == {}


def test_publish_rows_requires_factor_snapshot_json_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]

    with pytest.raises(ValueError, match="factor_snapshot_json is required"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_empty_factor_snapshot_json_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"] = {}

    with pytest.raises(ValueError, match="factor_snapshot_json must be non-empty"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_publish_rows_requires_factor_version_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_version"]

    with pytest.raises(ValueError, match="factor_version is required"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_hard_gates_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["hard_gates"] = {"eligible_for_high_alert": True}

    with pytest.raises(ValueError, match="hard_gates"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_missing_v3_factor_family_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]["families"]["semantic_catalyst"]

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.semantic_catalyst is required"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_factor_snapshot_version_mismatch_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["schema_version"] = "token_factor_snapshot_legacy"

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.schema_version must match factor_version"):
        TokenRadarRepository(conn).publish_rows(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
            commit=False,
        )

    assert conn.current_insert_params == {}


def test_latest_current_rows_limits_each_lane_independently():
    conn = FakeConn()

    rows = TokenRadarRepository(conn).latest_current_rows(
        window="5m",
        scope="all",
        limit=8,
        projection_version="token-radar-v13-social-attention",
    )

    assert rows == []
    assert "FROM token_radar_current_rows current_rows" in conn.sql
    assert "PARTITION BY lane" in conn.sql
    assert "lane_rank <= %s" in conn.sql
    assert conn.params[-2:] == (8, 16)


def test_latest_current_rows_reads_materialized_listed_at_without_history_lateral():
    conn = FakeConn()

    TokenRadarRepository(conn).latest_current_rows(
        window="1h",
        scope="all",
        limit=50,
        projection_version="token-radar-v13-social-attention",
    )

    assert "LEFT JOIN LATERAL" not in conn.sql
    assert "token_radar_rows" not in conn.sql


def test_upsert_target_feature_writes_compact_projection_row():
    conn = FakeConn()
    row = _valid_factor_row()

    count = TokenRadarRepository(conn).upsert_target_feature(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        row=row,
        computed_at_ms=1_778_000_000_000,
        commit=False,
    )

    assert count == 1
    assert "INSERT INTO token_radar_target_features" in conn.sql
    assert 'ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id)' in conn.sql
    assert conn.params["target_type_key"] == "Asset"
    assert conn.params["identity_id"] == "asset-1"
    assert conn.params["source_event_ids_json"].obj == ["event-1"]
    assert conn.params["source_intent_ids_json"].obj == ["intent-1"]
    assert conn.params["payload_hash"]


def test_delete_target_feature_uses_projection_identity_key():
    conn = FakeConn()

    TokenRadarRepository(conn).delete_target_feature(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        lane="resolved",
        target_type_key="Asset",
        identity_id="asset-1",
        commit=False,
    )

    assert "DELETE FROM token_radar_target_features" in conn.sql
    assert "target_type_key = %s" in conn.sql
    assert conn.params == ("token-radar-v13-social-attention", "1h", "all", "resolved", "Asset", "asset-1")


def test_list_target_features_for_rank_set_rehydrates_public_row_payload():
    conn = FakeConn(
        rows=[
            {
                "projection_version": "token-radar-v13-social-attention",
                "window": "1h",
                "scope": "all",
                "lane": "resolved",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "target_type": "Asset",
                "target_id": "asset-1",
                "pricefeed_id": "pf-1",
                "latest_event_received_at_ms": 1_778_000_000_000,
                "factor_snapshot_json": _valid_factor_snapshot(rank_score=12.0),
                "source_event_ids_json": ["event-1"],
                "source_intent_ids_json": ["intent-1"],
                "source_resolution_ids_json": ["resolution-1"],
            }
        ]
    )

    rows = TokenRadarRepository(conn).list_target_features_for_rank_set(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
    )

    assert "FROM token_radar_target_features" in conn.sql
    assert rows[0]["intent_id"] == "intent-1"
    assert rows[0]["event_id"] == "event-1"
    assert rows[0]["target_type_key"] == "Asset"
    assert rows[0]["identity_id"] == "asset-1"
    assert rows[0]["resolution_json"]["target_id"] == "asset-1"
    assert rows[0]["data_health_json"]["factor_snapshot"] == "ready"


def test_publish_rows_rejects_stale_projection_writer():
    conn = FakeStalePublishConn(existing_computed_at_ms=1_700_000_100_000)

    written = TokenRadarRepository(conn).publish_rows(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        computed_at_ms=1_700_000_000_000,
        rows=[],
        commit=False,
    )

    assert written is False
    assert not any("DELETE FROM" in sql for sql in conn.sqls)


def test_publish_rows_rejects_stale_writer_after_newer_zero_row_publication():
    conn = FakeStalePublishConn(existing_computed_at_ms=1_700_000_100_000)

    written = TokenRadarRepository(conn).publish_rows(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        computed_at_ms=1_700_000_000_000,
        rows=[_valid_factor_row()],
        commit=False,
    )

    assert written is False
    watermark_sql = conn.sqls[1]
    assert "FROM token_radar_current_rows" in watermark_sql
    assert "FROM token_radar_projection_coverage" in watermark_sql
    assert "publication_watermark" in watermark_sql
    assert not any("INSERT INTO token_radar_current_rows" in sql for sql in conn.sqls)


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.sql = ""
        self.params = ()
        self.calls = 0
        self.rows = rows or []

    def execute(self, sql, params=None):
        self.calls += 1
        self.sql = str(sql)
        self.params = params or ()
        return self

    def fetchone(self):
        return {"computed_at_ms": 1_700_000_000_000}

    def fetchall(self):
        return self.rows


class FakePublishConn:
    def __init__(self, *, existing_current: dict[str, Any] | None = None) -> None:
        self.sqls: list[str] = []
        self.existing_current = existing_current
        self.current_insert_params: dict[str, Any] = {}
        self.rank_history_params: dict[str, Any] = {}
        self.snapshot_audit_params: dict[str, Any] = {}
        self._last_rows: list[dict[str, Any]] = []

    def execute(self, sql, params=None):
        text = str(sql)
        self.sqls.append(text)
        self._last_rows = []
        if "SELECT *" in text and "FROM token_radar_current_rows" in text:
            self._last_rows = [self.existing_current] if self.existing_current is not None else []
        if "INSERT INTO token_radar_current_rows" in text:
            self.current_insert_params = dict(params or {})
        if "INSERT INTO token_radar_rank_history" in text:
            self.rank_history_params = dict(params or {})
        if "INSERT INTO token_radar_snapshot_audit" in text:
            self.snapshot_audit_params = dict(params or {})
        return self

    def fetchone(self):
        if self._last_rows:
            return self._last_rows[0]
        return {"computed_at_ms": None}

    def fetchall(self):
        return self._last_rows


class FakeStalePublishConn:
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
        "attention_json": {},
        "resolution_json": {},
        "market_json": {},
        "price_json": {},
        "score_json": {},
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
                "latest_status": "fresh",
                "dex_floor_status": "pass",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "families": {
            "social_heat": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 1,
                "data_health": "ready",
                "facts": {"volume_24h_usd": 1000},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
        },
        "composite": {
            "rank_score": rank_score,
            "family_scores": {},
            "recommended_decision": "discard",
        },
        "gates": {
            "eligible_for_high_alert": False,
            "eligible_for_watch": True,
            "suppression_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "normalization": {},
        "provenance": {
            "computed_at_ms": 1_778_000_000_000,
            "source_event_ids": ["event-1"],
        },
    }
