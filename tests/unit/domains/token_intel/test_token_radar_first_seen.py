from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository


def test_first_seen_lookup_reads_compact_table_only() -> None:
    conn = FirstSeenLookupConn(
        rows=[
            {"target_type_key": "Asset", "identity_id": "asset-1", "first_seen_ms": 100},
        ],
    )

    listed_at = TokenRadarRepository(conn).first_seen_by_identity(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        rows=[
            {"target_type": "Asset", "target_id": "asset-1", "intent_id": "intent-1"},
            {"target_type": None, "target_id": None, "intent_id": "intent-attention"},
        ],
    )

    assert listed_at == {("Asset", "asset-1"): 100}
    assert "FROM token_radar_target_first_seen" in conn.sql
    assert "token_radar_rows" not in conn.sql
    assert conn.params == (
        ["Asset", ""],
        ["asset-1", "intent-attention"],
        "token-radar-v13-social-attention",
        "1h",
        "all",
    )


def test_first_seen_lookup_skips_empty_identity_rows_without_querying() -> None:
    conn = FirstSeenLookupConn()

    listed_at = TokenRadarRepository(conn).first_seen_by_identity(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        rows=[{"target_type": None, "target_id": None, "intent_id": None}],
    )

    assert listed_at == {}
    assert conn.execute_calls == 0


def test_upsert_first_seen_batch_uses_identity_key_and_keeps_first_seen_stable() -> None:
    conn = UpsertFirstSeenConn()
    rows = [
        {
            "row_id": "row-newer",
            "target_type": None,
            "target_id": None,
            "intent_id": "intent-attention",
            "listed_at_ms": 50,
        },
        {
            "row_id": "row-resolved",
            "target_type": "Asset",
            "target_id": "asset-1",
            "intent_id": "intent-1",
        },
    ]

    count = TokenRadarRepository(conn).upsert_first_seen_batch(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        rows=rows,
        computed_at_ms=200,
        commit=False,
    )

    assert count == 2
    assert "first_seen_ms = LEAST(token_radar_target_first_seen.first_seen_ms, excluded.first_seen_ms)" in conn.sql
    assert "last_seen_ms = GREATEST(token_radar_target_first_seen.last_seen_ms, excluded.last_seen_ms)" in conn.sql
    assert conn.records[0]["target_type_key"] == ""
    assert conn.records[0]["identity_id"] == "intent-attention"
    assert conn.records[0]["first_seen_ms"] == 50
    assert conn.records[0]["last_seen_ms"] == 200
    assert conn.records[1]["target_type_key"] == "Asset"
    assert conn.records[1]["identity_id"] == "asset-1"
    assert conn.records[1]["first_seen_ms"] == 200


def test_publish_rows_uses_compact_first_seen_before_insert_and_upserts_after_insert() -> None:
    conn = PublishFirstSeenConn(first_seen={("Asset", "asset-1"): 100})
    row = _valid_factor_row()

    TokenRadarRepository(conn).publish_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=200,
        rows=[row],
        commit=False,
    )

    assert conn.insert_params["listed_at_ms"] == 100
    assert conn.call_labels.index("compact_lookup") < conn.call_labels.index("insert_current_row")
    assert conn.call_labels.index("insert_current_row") < conn.call_labels.index("upsert_first_seen")
    assert all("token_radar_rows" not in sql for sql in conn.sqls)


class FirstSeenLookupConn:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.execute_calls = 0

    def execute(self, sql: str, params: Any = None) -> FirstSeenLookupConn:
        self.execute_calls += 1
        self.sql = str(sql)
        self.params = tuple(params or ())
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class UpsertFirstSeenConn:
    def __init__(self) -> None:
        self.sql = ""
        self.records: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> UpsertFirstSeenConn:
        self.sql = str(sql)
        flat_params = list(params or [])
        width = 11
        self.records = [
            {
                "projection_version": flat_params[index],
                "window": flat_params[index + 1],
                "scope": flat_params[index + 2],
                "target_type_key": flat_params[index + 3],
                "identity_id": flat_params[index + 4],
                "first_seen_ms": flat_params[index + 5],
                "last_seen_ms": flat_params[index + 6],
                "first_row_id": flat_params[index + 7],
                "latest_row_id": flat_params[index + 8],
                "created_at_ms": flat_params[index + 9],
                "updated_at_ms": flat_params[index + 10],
            }
            for index in range(0, len(flat_params), width)
        ]
        return self


class PublishFirstSeenConn:
    def __init__(self, *, first_seen: dict[tuple[str, str], int]) -> None:
        self.first_seen = first_seen
        self.call_labels: list[str] = []
        self.insert_params: dict[str, Any] = {}
        self.sqls: list[str] = []
        self._last_rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> PublishFirstSeenConn:
        text = str(sql)
        self.sqls.append(text)
        if "MAX(computed_at_ms)" in text:
            self._last_rows = [{"computed_at_ms": None}]
        elif "FROM token_radar_target_first_seen" in text:
            self.call_labels.append("compact_lookup")
            self._last_rows = [
                {"target_type_key": key[0], "identity_id": key[1], "first_seen_ms": value}
                for key, value in self.first_seen.items()
            ]
        elif "INSERT INTO token_radar_current_rows" in text:
            self.call_labels.append("insert_current_row")
            self.insert_params = dict(params or {})
            self._last_rows = []
        elif "INSERT INTO token_radar_target_first_seen" in text:
            self.call_labels.append("upsert_first_seen")
            self._last_rows = []
        else:
            self._last_rows = []
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._last_rows[0] if self._last_rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._last_rows


def _valid_factor_row() -> dict[str, object]:
    return {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 200,
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
        "created_at_ms": 200,
    }


def _valid_factor_snapshot() -> dict[str, object]:
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {"target_type": "Asset", "target_id": "asset-1", "symbol": "BOV"},
        "market": {
            "event_anchor": None,
            "decision_latest": None,
            "readiness": {
                "anchor_status": "missing",
                "latest_status": "missing",
                "dex_floor_status": "unknown",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "families": {
            name: {
                "raw_score": 0,
                "score": 0,
                "weight": weight,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            }
            for name, weight in (
                ("social_heat", 0.35),
                ("social_propagation", 0.30),
                ("semantic_catalyst", 0.25),
                ("timing_risk", 0.10),
            )
        },
        "gates": {
            "eligible_for_high_alert": False,
            "eligible_for_watch": True,
            "suppression_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "missing", "social": "ready", "alpha": "ready"},
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {"in_cohort": True, "size": 10},
            "factor_ranks": {},
            "alpha_rank": 0.5,
        },
        "composite": {
            "rank_score": 0,
            "family_scores": {},
            "recommended_decision": "discard",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 200},
    }
