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
    assert _constants.MACRO_MODULE_VIEW_VERSION == "macro_module_view_v2"
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


def test_repository_concept_history_counts_returns_deduped_point_contract() -> None:
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
    assert "PARTITION BY concept_key, observed_at" in query
    assert "ORDER BY source_priority DESC, ingested_at_ms DESC" in query
    assert "LEFT JOIN aggregated" in query
    assert "COALESCE(aggregated.points, 0)" in query
    assert params == (["asset:spx"], 60)


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> "FakeCursor":
        self.executions.append((query, params))
        return FakeCursor(self.rows)


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows
