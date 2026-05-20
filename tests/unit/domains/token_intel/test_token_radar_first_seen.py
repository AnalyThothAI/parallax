from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository


def test_first_seen_lookup_reads_compact_table_and_falls_back_to_history_for_missing_rows() -> None:
    conn = FirstSeenLookupConn(
        compact_rows=[
            {"target_type_key": "Asset", "identity_id": "asset-1", "first_seen_ms": 100},
        ],
        historical_rows=[
            {"target_type_key": "", "identity_id": "intent-attention", "listed_at_ms": 90},
        ],
    )
    rows = [
        {"target_type": "Asset", "target_id": "asset-1", "intent_id": "intent-1"},
        {"target_type": None, "target_id": None, "intent_id": "intent-attention"},
    ]

    listed_at = TokenRadarRepository(conn).first_seen_by_identity(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        rows=rows,
    )

    assert listed_at == {("Asset", "asset-1"): 100, ("", "intent-attention"): 90}
    assert "FROM token_radar_target_first_seen" in conn.compact_sql
    assert "COALESCE(history.target_type, '') = requested.target_type_key" in conn.history_sql
    assert conn.compact_params == (
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
    assert "WHEN excluded.first_seen_ms <= token_radar_target_first_seen.first_seen_ms" in conn.sql
    assert "WHEN excluded.last_seen_ms >= token_radar_target_first_seen.last_seen_ms" in conn.sql
    assert conn.records[0]["target_type_key"] == ""
    assert conn.records[0]["identity_id"] == "intent-attention"
    assert conn.records[0]["first_seen_ms"] == 50
    assert conn.records[0]["last_seen_ms"] == 200
    assert conn.records[1]["target_type_key"] == "Asset"
    assert conn.records[1]["identity_id"] == "asset-1"
    assert conn.records[1]["first_seen_ms"] == 200


def test_upsert_first_seen_batch_skips_rows_without_identity() -> None:
    conn = UpsertFirstSeenConn()

    count = TokenRadarRepository(conn).upsert_first_seen_batch(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        rows=[{"row_id": "row-empty", "target_type": None, "target_id": "", "intent_id": ""}],
        computed_at_ms=200,
        commit=False,
    )

    assert count == 0
    assert conn.sql == ""


def test_replace_rows_uses_first_seen_before_insert_and_upserts_after_insert() -> None:
    conn = ReplaceRowsFirstSeenConn(first_seen={("Asset", "asset-1"): 100})
    row = _valid_factor_row()

    TokenRadarRepository(conn).replace_rows(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        computed_at_ms=200,
        rows=[row],
        commit=False,
    )

    assert conn.insert_params["listed_at_ms"] == 100
    assert conn.call_labels.index("compact_lookup") < conn.call_labels.index("insert_row")
    assert conn.call_labels.index("insert_row") < conn.call_labels.index("upsert_first_seen")


def test_backfill_first_seen_pages_identities_before_aggregating_history() -> None:
    conn = BackfillFirstSeenConn(
        rows=[
            {
                "projection_version": "token-radar-v13-social-attention",
                "window": "1h",
                "scope": "all",
                "target_type_key": "",
                "identity_id": "intent-attention",
                "first_seen_ms": 50,
                "last_seen_ms": 200,
                "first_row_id": "row-old",
                "latest_row_id": "row-new",
            }
        ]
    )

    result = TokenRadarRepository(conn).backfill_first_seen_from_history(
        batch_size=1,
        after_key=("token-radar-v13-social-attention", "1h", "all", "", "intent-before"),
        commit=False,
    )

    assert result == {
        "rows_upserted": 1,
        "next_after_key": ("token-radar-v13-social-attention", "1h", "all", "", "intent-attention"),
        "has_more": True,
    }
    assert "WITH identity_page AS" in conn.select_sql
    assert "SELECT DISTINCT ON" in conn.select_sql
    assert "%s::text IS NULL" in conn.select_sql
    assert "LIMIT %s" in conn.select_sql
    assert "JOIN token_radar_rows rows" in conn.select_sql
    assert conn.select_params[-1] == 1
    assert conn.upsert_records[0]["target_type_key"] == ""
    assert conn.upsert_records[0]["identity_id"] == "intent-attention"


class FirstSeenLookupConn:
    def __init__(
        self,
        *,
        compact_rows: list[dict[str, Any]] | None = None,
        historical_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.compact_rows = compact_rows or []
        self.historical_rows = historical_rows or []
        self.compact_sql = ""
        self.history_sql = ""
        self.compact_params: tuple[Any, ...] = ()
        self._last_rows: list[dict[str, Any]] = []
        self.execute_calls = 0

    def execute(self, sql: str, params: Any = None) -> FirstSeenLookupConn:
        self.execute_calls += 1
        text = str(sql)
        if "FROM token_radar_target_first_seen" in text:
            self.compact_sql = text
            self.compact_params = tuple(params or ())
            self._last_rows = self.compact_rows
        elif "FROM token_radar_rows history" in text:
            self.history_sql = text
            self._last_rows = self.historical_rows
        else:
            self._last_rows = []
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self._last_rows


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


class ReplaceRowsFirstSeenConn:
    def __init__(self, *, first_seen: dict[tuple[str, str], int]) -> None:
        self.first_seen = first_seen
        self.call_labels: list[str] = []
        self.insert_params: dict[str, Any] = {}
        self._last_rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> ReplaceRowsFirstSeenConn:
        text = str(sql)
        if "MAX(computed_at_ms)" in text:
            self._last_rows = [{"computed_at_ms": None}]
        elif "FROM token_radar_target_first_seen" in text:
            self.call_labels.append("compact_lookup")
            self._last_rows = [
                {"target_type_key": key[0], "identity_id": key[1], "first_seen_ms": value}
                for key, value in self.first_seen.items()
            ]
        elif "FROM token_radar_rows history" in text:
            self.call_labels.append("history_lookup")
            self._last_rows = []
        elif "INSERT INTO token_radar_rows" in text:
            self.call_labels.append("insert_row")
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


class BackfillFirstSeenConn:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.select_sql = ""
        self.select_params: tuple[Any, ...] = ()
        self.upsert_records: list[dict[str, Any]] = []
        self._last_rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> BackfillFirstSeenConn:
        text = str(sql)
        if "WITH identity_page AS" in text:
            self.select_sql = text
            self.select_params = tuple(params or ())
            self._last_rows = self.rows
        elif "INSERT INTO token_radar_target_first_seen" in text:
            flat_params = list(params or [])
            width = 11
            self.upsert_records = [
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
                }
                for index in range(0, len(flat_params), width)
            ]
            self._last_rows = []
        else:
            self._last_rows = []
        return self

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
            "max_decision": "discard",
            "blocked_reasons": [],
            "risk_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "missing", "social": "ready", "alpha": "ready"},
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {},
            "factor_ranks": {},
            "alpha_rank": None,
        },
        "composite": {
            "family_scores": {
                "social_heat": 0,
                "social_propagation": 0,
                "semantic_catalyst": 0,
                "timing_risk": 0,
            },
            "rank_score": 0,
            "recommended_decision": "discard",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 200},
    }
