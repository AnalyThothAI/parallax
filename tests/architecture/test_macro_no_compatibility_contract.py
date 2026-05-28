from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
ALEMBIC_VERSIONS = SRC / "platform" / "db" / "alembic" / "versions"

FORBIDDEN_MACRO_COMPATIBILITY_TOKENS = (
    "macro_regime_v3",
    "macro_module_view_v1",
    "macro_module_view_v2",
    "macro_observation_series_active_generation",
    "macro_observation_series_generations",
    "macro_view_snapshots_compact",
    "macro_view_snapshot_generations",
    "macro_regime_snapshots",
)

RETIRED_CEX_RUN_SERVING_DOC_TOKENS = (
    "CREATE TABLE IF NOT EXISTS cex_oi_radar_runs",
    "Write `cex_oi_radar_runs`",
    "写 `cex_oi_radar_runs`",
    "Replace rows for a `run_id`",
    "按 `run_id` 重建",
)


def test_runtime_source_does_not_reference_retired_macro_serving_contracts() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if ALEMBIC_VERSIONS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains {token}"
            for token in FORBIDDEN_MACRO_COMPATIBILITY_TOKENS
            if token in text
        )

    assert offenders == []


def test_completed_docs_do_not_republish_retired_cex_run_serving_instructions() -> None:
    docs = (
        ROOT / "docs" / "superpowers" / "plans" / "completed" / "2026-05-21-cex-binance-hard-cut-plan-cn.md",
        ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "completed"
        / "2026-05-21-binance-usdt-perp-oi-radar-worker-cn.md",
    )
    offenders: list[str] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains retired CEX run-serving instruction {token!r}"
            for token in RETIRED_CEX_RUN_SERVING_DOC_TOKENS
            if token in text
        )

    assert offenders == []
