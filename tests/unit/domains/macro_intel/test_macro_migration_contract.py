from pathlib import Path

from gmgn_twitter_intel.domains.macro_intel import _constants
from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = (
    ROOT
    / "src"
    / "gmgn_twitter_intel"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260521_0080_macro_concept_key_hard_cut.py"
)
RUNTIME_DB_PERFORMANCE_HARD_CUT_MIGRATION = (
    ROOT
    / "src"
    / "gmgn_twitter_intel"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260527_0114_runtime_db_performance_hard_cut.py"
)


def test_macro_concept_key_migration_backfills_historical_stooq_rows_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    expected_historical_stooq = {
        "stooq:spy.us": "asset:spy",
        "stooq:qqq.us": "asset:qqq",
        "stooq:iwm.us": "asset:iwm",
        "stooq:tlt.us": "asset:tlt",
        "stooq:hyg.us": "asset:hyg",
        "stooq:lqd.us": "asset:lqd",
        "stooq:gld.us": "asset:gld",
        "stooq:uso.us": "asset:uso",
        "stooq:btc.us": "crypto:btc",
        "stooq:eth.us": "crypto:eth",
        "stooq:dxy.us": "fx:dxy",
    }
    for historical_key, concept_key in expected_historical_stooq.items():
        assert f"WHEN '{historical_key}' THEN '{concept_key}'" in source

    assert "source_name = 'stooq'" in source
    assert "THEN 10" in source


def test_macro_hard_cut_constants_and_core_concept_metadata_are_exported() -> None:
    assert _constants.MACRO_VIEW_PROJECTION_VERSION == "macro_regime_v4"
    assert _constants.MACRO_MODULE_VIEW_VERSION == "macro_module_view_v3"
    assert _constants.MACRO_MIN_CHART_POINTS == 2
    assert _constants.MACRO_REQUIRED_DELTA_POINTS == {"5d": 6, "20d": 21, "60d": 61}
    assert _constants.MACRO_REQUIRED_STAT_POINTS == 126

    assert _constants.MACRO_CONCEPT_METADATA["asset:spx"] == {
        "label": "标普500",
        "short_label": "SPX",
        "description": "美国大盘股风险偏好基准",
        "unit_label": "点",
    }
    assert _constants.MACRO_CONCEPT_METADATA["rates:dgs10"]["short_label"] == "10Y"
    assert _constants.MACRO_CONCEPT_METADATA["liquidity:tga"]["unit_label"] == "百万美元"
    assert _constants.MACRO_CONCEPT_METADATA["credit:hy_oas"]["label"] == "高收益债 OAS"
    assert _constants.MACRO_CONCEPT_METADATA["vol:vix"]["unit_label"] == "点"


def test_repository_latest_observations_reads_projected_rows() -> None:
    rows = [
        {
            "concept_key": "asset:spx",
            "observed_at": "2026-05-21",
            "value_numeric": 2.0,
            "source_name": "fred",
        }
    ]
    conn = FakeConnection(rows)
    repo = MacroIntelRepository(conn)

    result = repo.latest_observations(limit=25, concept_keys=("asset:spx",))

    assert result == rows
    query, params = conn.executions[0]
    assert "FROM macro_observation_series_rows AS rows" in query
    assert "macro_observation_series_active_generation" not in query
    assert "generation_id" not in query
    assert "projection_version = %s" in query
    assert "series_rank = 1" in query
    assert "FROM macro_observations" not in query
    assert "row_number() OVER" not in query
    assert params == ("macro_regime_v4", ["asset:spx"], 25)


def test_repository_concept_history_counts_returns_projected_point_contract() -> None:
    rows = [
        {
            "concept_key": "asset:spx",
            "points": 2,
            "latest_observed_at": "2026-05-21",
            "oldest_observed_at": "2026-05-20",
            "sources": ["fred"],
        }
    ]
    conn = FakeConnection(rows)
    repo = MacroIntelRepository(conn)

    result = repo.concept_history_counts(concept_keys=("asset:spx",), lookback_days=60)

    assert result == rows
    query, params = conn.executions[0]
    assert "WITH requested AS" in query
    assert "FROM macro_observation_series_rows AS rows" in query
    assert "macro_observation_series_active_generation" not in query
    assert "generation_id" not in query
    assert "projection_version = %s" in query
    assert "FROM macro_observations" not in query
    assert "row_number() OVER" not in query
    assert "LEFT JOIN aggregated" in query
    assert "COALESCE(aggregated.points, 0)" in query
    assert params == (["asset:spx"], "macro_regime_v4", 60)


def test_repository_refresh_observation_series_rows_writes_current_read_model() -> None:
    conn = FakeRefreshConnection(row_count=1)
    repo = MacroIntelRepository(conn)

    result = repo.refresh_observation_series_rows(
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        lookback_days=730,
        limit_per_series=252,
    )

    assert result["status"] == "published"
    assert result["rows_written"] == 1
    assert result["source_rows"] == 1
    queries = "\n".join(query for query, _params in conn.executions)
    assert "DELETE FROM macro_observation_series_rows" in queries
    assert "INSERT INTO macro_observation_series_rows" in queries
    assert "INSERT INTO macro_observation_series_publication_state" in queries
    assert "generation_id" not in queries
    assert "macro_observation_series_generations" not in queries
    assert "macro_observation_series_active_generation" not in queries
    assert "FROM macro_observations" in queries
    assert "row_number() OVER" in queries
    assert "PARTITION BY concept_key, observed_at" in queries
    assert "PARTITION BY concept_key" in queries
    select_query, select_params = conn.executions[0]
    assert "WITH source_ranked AS" in select_query
    assert select_params == (730, "macro_regime_v4", 1_779_000_000_000, 252)


def test_macro_observation_series_contract_is_current_only_after_hard_cut() -> None:
    migration_sql = RUNTIME_DB_PERFORMANCE_HARD_CUT_MIGRATION.read_text(encoding="utf-8")
    repository_sql = (
        ROOT
        / "src"
        / "gmgn_twitter_intel"
        / "domains"
        / "macro_intel"
        / "repositories"
        / "macro_intel_repository.py"
    ).read_text(encoding="utf-8")

    assert "macro_observation_series_rows_compact" in migration_sql
    assert "observed_at TIMESTAMPTZ NOT NULL" in migration_sql
    assert "value_numeric DOUBLE PRECISION NOT NULL" in migration_sql
    assert "macro_observation_series_rows_compact_pkey" in migration_sql
    assert "PRIMARY KEY (projection_version, concept_key, observed_at)" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS macro_observation_series_publication_state" in migration_sql
    assert "DROP TABLE IF EXISTS macro_observation_series_active_generation" in migration_sql
    assert "DROP TABLE IF EXISTS macro_observation_series_generations" in migration_sql
    assert "INSERT INTO macro_observation_series_generations" not in repository_sql
    assert "macro_observation_series_active_generation" not in repository_sql
    assert "_generation_id" not in repository_sql


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> "FakeCursor":
        self.executions.append((query, params))
        return FakeCursor(self.rows, rowcount=self.rowcount)


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeRefreshConnection:
    def __init__(self, *, row_count: int) -> None:
        self.row_count = row_count
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.rows = [
            {
                "projection_version": "macro_regime_v4",
                "concept_key": "rates:dgs10",
                "observed_at": "2026-05-20",
                "series_rank": 1,
                "value_numeric": 4.7,
                "source_name": "fred",
                "series_key": "fred:DGS10",
                "source_priority": 100,
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-05-20",
                "raw_payload_json": {},
                "ingested_at_ms": 1,
                "projected_at_ms": 1_779_000_000_000,
            }
        ]

    def execute(self, query: str, params: tuple[object, ...]) -> FakeCursor:
        self.executions.append((query, params))
        if "WITH source_ranked AS" in query:
            return FakeCursor(self.rows[: self.row_count])
        if "FROM macro_observation_series_publication_state" in query:
            return FakeCursor([])
        return FakeCursor([], rowcount=self.row_count)

    def transaction(self):
        return FakeTransaction()


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False
