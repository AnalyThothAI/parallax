from __future__ import annotations

import importlib

from parallax.domains.macro_intel.runtime.macro_daily_brief_projection_worker import MacroDailyBriefProjectionWorker
from parallax.platform.config.settings import MacroDailyBriefProjectionWorkerSettings

NOW_MS = 1_779_000_000_000


def test_build_macro_daily_brief_projects_timsun_style_asset_judgment_from_snapshot() -> None:
    module = importlib.import_module("parallax.domains.macro_intel.services.macro_daily_brief")
    snapshot = {
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-05-20",
        "status": "partial",
        "regime": "tightening",
        "computed_at_ms": NOW_MS,
        "features_json": {
            "asset:spx": _feature(5312.4, delta_20d=3.2, source_name="fred"),
            "crypto:btc": _feature(110_000.0, delta_20d=8.5, source_name="yahoo"),
            "fx:dxy": _feature(104.2, delta_20d=-1.1, source_name="yahoo"),
            "commodity:wti_futures": _feature(78.4, delta_20d=2.4, source_name="yahoo"),
            "rates:dgs10": _feature(4.7, delta_20d=0.18, source_name="fred"),
            "vol:vix": _feature(17.2, delta_20d=-2.8, source_name="fred"),
            "credit:hy_oas": _feature(2.8, delta_20d=-0.12, source_name="fred"),
        },
        "source_coverage_json": {
            "latest_coverage_ratio": 0.72,
            "history_coverage_ratio": 0.44,
            "latest_observed_at": "2026-05-20",
        },
        "data_gaps_json": [{"code": "move_index_missing", "severity": "warning"}],
    }

    brief = module.build_macro_daily_brief(snapshot=snapshot, computed_at_ms=NOW_MS)

    assert brief["brief_key"] == "assets_today"
    assert brief["projection_version"] == module.MACRO_DAILY_BRIEF_PROJECTION_VERSION
    assert brief["brief_date"] == "2026-05-20"
    assert brief["asof_date"] == "2026-05-20"
    assert brief["status"] == "partial"
    assert brief["headline"].startswith("今日判断：")
    assert [block["id"] for block in brief["blocks"]] == [
        "cross_correlation",
        "dollar_commodity",
        "risk_appetite",
        "outlook",
    ]
    assert brief["data_quality"] == {
        "status": "partial",
        "latest_coverage_ratio": 0.72,
        "history_coverage_ratio": 0.44,
        "gap_count": 1,
    }
    dollar_block = next(block for block in brief["blocks"] if block["id"] == "dollar_commodity")
    assert "WTI 20日变化 +2.40" in dollar_block["body"]


def test_macro_daily_brief_worker_reads_formal_settings_for_session_timeout_and_zero_write() -> None:
    repo = FakeMacroIntelRepository(changed=False)
    db = FakeDB(repo, expected_statement_timeout=17.0)
    worker = MacroDailyBriefProjectionWorker(
        name="macro_daily_brief_projection",
        settings=MacroDailyBriefProjectionWorkerSettings(statement_timeout_seconds=17.0),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert db.worker_sessions == [{"name": "macro_daily_brief_projection", "statement_timeout_seconds": 17.0}]
    assert repo.latest_snapshot_calls == [{"projection_version": "macro_regime_v4"}]
    assert repo.upsert_calls[0]["brief"]["status"] == "missing"
    assert result.processed == 1
    assert result.notes["rows_written"] == 0


class FakeDB:
    def __init__(self, repo: FakeMacroIntelRepository, *, expected_statement_timeout: float) -> None:
        self.repo = repo
        self.expected_statement_timeout = expected_statement_timeout
        self.worker_sessions: list[dict[str, object]] = []

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == self.expected_statement_timeout
        self.worker_sessions.append(
            {
                "name": name,
                "statement_timeout_seconds": statement_timeout_seconds,
            }
        )
        return FakeRepositorySession(self.repo)


class FakeRepositorySession:
    def __init__(self, repo: FakeMacroIntelRepository) -> None:
        self.macro_intel = repo

    def __enter__(self) -> FakeRepositorySession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeMacroIntelRepository:
    def __init__(self, *, changed: bool) -> None:
        self.changed = changed
        self.latest_snapshot_calls: list[dict[str, object]] = []
        self.upsert_calls: list[dict[str, object]] = []

    def latest_snapshot(self, *, projection_version: str):
        self.latest_snapshot_calls.append({"projection_version": projection_version})

    def upsert_macro_daily_brief(self, brief: dict[str, object], *, now_ms: int) -> bool:
        self.upsert_calls.append({"brief": brief, "now_ms": now_ms})
        return self.changed


def _feature(value: float, *, delta_20d: float, source_name: str) -> dict[str, object]:
    return {
        "latest": {"value": value, "observed_at": "2026-05-20"},
        "delta": {"20d": delta_20d},
        "data_quality": "ok",
        "source": {"name": source_name},
        "history_points": 60,
    }
