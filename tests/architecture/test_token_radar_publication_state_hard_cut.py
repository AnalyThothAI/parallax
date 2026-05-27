from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"

BANNED_RUNTIME_TOKENS = (
    "payload_hash changed during selected-row hydration",
    "_rank_and_hydrate_selected_rows",
    "_hydrate_ranked_rows",
    "_patch_hydrated_rank_row",
    "load_target_feature_payloads_for_ranked_keys",
    "rebuild_rank_inputs_full",
    "list_rank_input_rebuild_keys",
    "stale_rank_input_count",
    "rank_input_readiness_for_work_items",
    "latest_snapshot_audit_rows",
    "token_radar_projection_coverage",
    "token_radar_target_projection_coverage",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_postgres_hard_reset",
    "runtime_worker_dirty_targets",
    "reset-token-radar-postgres-hard-cut",
    "enqueue-runtime-worker-dirty-targets",
    "side_effect_status",
    ":claimed:",
)

ONLINE_PATHS = (
    SRC / "app/surfaces/api/routes_radar.py",
    SRC / "domains/token_intel/read_models/asset_flow_service.py",
    SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py",
    SRC / "domains/pulse_lab/queries/pulse_policy_evaluator.py",
    SRC / "domains/notifications/services/notification_rules.py",
    SRC / "domains/narrative_intel/repositories/narrative_repository.py",
    SRC / "domains/asset_market/repositories/registry_repository.py",
)

FORBIDDEN_ONLINE_TABLES = (
    "token_radar_target_features",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_rank_source_events",
)

def _runtime_files() -> list[Path]:
    roots = (SRC / "app", SRC / "domains")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def test_legacy_token_radar_publication_paths_are_removed() -> None:
    violations: list[str] = []
    for path in _runtime_files():
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} contains {token}" for token in BANNED_RUNTIME_TOKENS if token in text
        )
    assert violations == []


def test_token_radar_runtime_repair_and_hard_reset_modules_are_removed() -> None:
    removed_paths = (
        SRC / "app/runtime/runtime_worker_dirty_targets.py",
        SRC / "app/runtime/token_radar_postgres_hard_reset.py",
    )

    assert [str(path.relative_to(ROOT)) for path in removed_paths if path.exists()] == []


def test_online_token_radar_paths_do_not_read_private_or_cold_tables() -> None:
    violations: list[str] = []
    for path in ONLINE_PATHS:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} reads {table}" for table in FORBIDDEN_ONLINE_TABLES if table in text
        )
    assert violations == []
