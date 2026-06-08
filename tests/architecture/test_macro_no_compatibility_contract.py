from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
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
        ROOT / "docs" / "superpowers" / "specs" / "completed" / "2026-05-21-binance-usdt-perp-oi-radar-worker-cn.md",
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


def test_cex_binance_hard_cut_cleanup_runtime_surface_is_removed() -> None:
    removed_paths = [
        SRC / "domains/asset_market/services/cex_binance_hard_cut_cleanup.py",
        SRC / "domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py",
        ROOT / "tests/unit/test_cex_binance_hard_cut_cleanup.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []

    forbidden_runtime_tokens = {
        "cex-binance-hard-cut-cleanup",
        "cleanup_cex_binance_hard_cut",
        "CexBinanceHardCutAbort",
        "cex_binance_hard_cut_cleanup_repository",
    }
    scanned_paths = [
        SRC / "app/surfaces/cli/parser.py",
        SRC / "app/surfaces/cli/commands/ops.py",
        ROOT / "Makefile",
        ROOT / "tests/architecture/test_token_radar_sql_surface_inventory_contract.py",
    ]
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in scanned_paths
        for token in forbidden_runtime_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
