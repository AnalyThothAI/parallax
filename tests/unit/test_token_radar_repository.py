from __future__ import annotations

from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    _json_payload,
)
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_projection_publication_round_trips_ready_zero_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v10-current-market",
            window="5m",
            scope="matched",
            source_rows=17,
            row_count=0,
            computed_at_ms=1_778_000_000_000,
            source_max_received_at_ms=1_777_999_900_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
        )

        publications = repo.latest_publications(
            projection_version="token-radar-v10-current-market",
            windows=("5m",),
            scopes=("matched",),
        )
    finally:
        conn.close()

    assert publications == {
        ("5m", "matched"): {
            "status": "ready",
            "refresh_status": "ready",
            "reason": None,
            "source_rows": 17,
            "row_count": 0,
            "computed_at_ms": 1_778_000_000_000,
            "published_computed_at_ms": 1_778_000_000_000,
            "source_max_received_at_ms": 1_777_999_900_000,
            "refresh_started_at_ms": 1_777_999_990_000,
            "refresh_finished_at_ms": 1_778_000_000_000,
            "error": None,
        }
    }


def test_failed_refresh_preserves_published_computed_at(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v10-current-market",
            window="1h",
            scope="all",
            source_rows=10,
            row_count=3,
            computed_at_ms=1_778_000_000_000,
            source_max_received_at_ms=1_777_999_900_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
        )
        repo.mark_refresh_status(
            projection_version="token-radar-v10-current-market",
            window="1h",
            scope="all",
            refresh_status="failed",
            reason="query_timeout",
            source_rows=0,
            row_count=0,
            computed_at_ms=1_778_000_000_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
            error="statement timeout",
        )

        publications = repo.latest_publications(
            projection_version="token-radar-v10-current-market",
            windows=("1h",),
            scopes=("all",),
        )
    finally:
        conn.close()

    assert publications[("1h", "all")]["status"] == "ready"
    assert publications[("1h", "all")]["refresh_status"] == "failed"
    assert publications[("1h", "all")]["reason"] == "query_timeout"
    assert publications[("1h", "all")]["error"] == "statement timeout"
    assert publications[("1h", "all")]["published_computed_at_ms"] == 1_778_000_000_000


def test_latest_rows_reads_last_published_rows_while_refresh_running(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    old_row = _valid_factor_row()
    old_row["row_id"] = "row-old"
    old_row["target_json"] = {"symbol": "OLD"}
    old_row["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=11)
    new_row = _valid_factor_row()
    new_row["row_id"] = "row-new"
    new_row["target_json"] = {"symbol": "NEW"}
    new_row["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=99)
    try:
        migrate(conn)
        _insert_event_intent(conn)
        repo = TokenRadarRepository(conn)
        assert repo.replace_rows(
            projection_version="token-radar-v10-current-market",
            window="24h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[old_row],
        )
        repo.publish_rows(
            projection_version="token-radar-v10-current-market",
            window="24h",
            scope="all",
            source_rows=1,
            row_count=1,
            computed_at_ms=1_778_000_000_000,
            source_max_received_at_ms=1_777_999_900_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
        )
        repo.mark_refresh_status(
            projection_version="token-radar-v10-current-market",
            window="24h",
            scope="all",
            refresh_status="running",
            reason="projection_window_running",
            computed_at_ms=1_778_000_100_000,
            started_at_ms=1_778_000_100_000,
        )
        assert repo.replace_rows(
            projection_version="token-radar-v10-current-market",
            window="24h",
            scope="all",
            computed_at_ms=1_778_000_100_000,
            rows=[new_row],
        )

        latest = repo.latest_rows(
            window="24h",
            scope="all",
            limit=10,
            projection_version="token-radar-v10-current-market",
        )
    finally:
        conn.close()

    assert [row["row_id"] for row in latest] == ["row-old"]


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    snapshot = _valid_factor_snapshot(rank_score=Decimal("12.5"))
    snapshot["nested"] = {"volume_24h_usd": Decimal("123.45")}
    payload = _json_payload(
        {
            "factor_snapshot_json": snapshot,
            "intent_json": {},
            "asset_json": {},
            "primary_venue_json": None,
            "target_json": {},
            "data_health_json": {},
            "source_event_ids_json": [],
            "factor_version": "token_factor_snapshot_v1",
        }
    )

    assert payload["factor_snapshot_json"].obj["composite"]["rank_score"] == 12.5
    assert payload["factor_snapshot_json"].obj["nested"]["volume_24h_usd"] == 123.45


def test_replace_and_latest_rows_persist_factor_snapshot_json(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": None,
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(rank_score=12),
        "factor_version": "token_factor_snapshot_v1",
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }
    try:
        migrate(conn)
        _insert_event_intent(conn)
        repo = TokenRadarRepository(conn)
        repo.replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
        )
        repo.publish_rows(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            source_rows=1,
            row_count=1,
            computed_at_ms=1_778_000_000_000,
            source_max_received_at_ms=1_778_000_000_000,
        )

        latest = repo.latest_rows(
            window="1h",
            scope="all",
            limit=10,
            projection_version="token-radar-v9-factor-snapshot",
        )
    finally:
        conn.close()

    assert latest[0]["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v1"


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
        "pricefeed_id": None,
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": "token_factor_snapshot_v1",
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


def _insert_event_intent(conn) -> None:
    EvidenceRepository(conn).insert_event(
        make_event("event-1", text="$BOV", received_at_ms=1_778_000_000_000),
        is_watched=True,
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          'intent-1', 'event-1', 'symbol:BOV', 'test', NULL,
          'BOV', NULL, NULL, NULL, 'pending', 1.0, 1_778_000_000_000, 1_778_000_000_000
        )
        """
    )
    conn.commit()


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


def test_replace_rows_requires_complete_factor_snapshot_contract_before_insert():
    conn = FakeReplaceConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]["hard_gates"]

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.hard_gates is required"):
        TokenRadarRepository(conn).replace_rows(
            projection_version="token-radar-v9-factor-snapshot",
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


class FakeReplaceConn:
    insert_sql = ""

    def execute(self, sql, params=None):
        text = str(sql)
        if "INSERT INTO token_radar_rows" in text:
            self.insert_sql = text
        return self

    def fetchone(self):
        return {"computed_at_ms": None}


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
        "pricefeed_id": None,
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": "token_factor_snapshot_v1",
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }


def _valid_factor_snapshot(*, rank_score: object = 12) -> dict[str, object]:
    return {
        "schema_version": "token_factor_snapshot_v1",
        "subject": {"target_type": "Asset", "target_id": "asset-1", "symbol": "BOV"},
        "families": {
            "identity": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            "social_attention": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            "social_quality": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            "social_semantics": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            "market_quality": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            "timing": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
        },
        "hard_gates": {
            "eligible_for_high_alert": False,
            "blocked_reasons": ["liquidity_below_high_alert_floor"],
            "gates": [{"reason": "liquidity_below_high_alert_floor", "action": "block_high_alert"}],
        },
        "composite": {"rank_score": rank_score, "recommended_decision": "discard"},
    }
