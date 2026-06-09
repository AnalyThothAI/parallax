from __future__ import annotations

import importlib

NOW_MS = 1_779_000_000_000


def test_build_macro_daily_brief_projects_timsun_style_asset_judgment_from_snapshot() -> None:
    module = importlib.import_module("parallax.domains.macro_intel.services.macro_daily_brief")
    snapshot = {
        "snapshot_id": "macro-view:macro_regime_v4:current",
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-05-20",
        "status": "partial",
        "regime": "tightening",
        "computed_at_ms": NOW_MS,
        "features_json": {
            "asset:spx": _feature(5312.4, delta_20d=3.2, source_name="fred"),
            "crypto:btc": _feature(110_000.0, delta_20d=8.5, source_name="yahoo"),
            "fx:dxy": _feature(104.2, delta_20d=-1.1, source_name="yahoo"),
            "commodity:wti": _feature(78.4, delta_20d=2.4, source_name="fred"),
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
    rendered = str(brief)
    assert "macro-view:macro_regime_v4:current" not in rendered
    assert "snapshot_id" not in rendered


def _feature(value: float, *, delta_20d: float, source_name: str) -> dict[str, object]:
    return {
        "latest": {"value": value, "observed_at": "2026-05-20"},
        "delta": {"20d": delta_20d},
        "data_quality": "ok",
        "source": {"name": source_name},
        "history_points": 60,
    }
