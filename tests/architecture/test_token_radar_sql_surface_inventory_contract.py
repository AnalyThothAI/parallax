from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TOKEN_RADAR_SQL_SURFACES = (
    "src/parallax/app/runtime/ops_cli_queries.py",
    "src/parallax/app/runtime/ops_diagnostics.py",
    "src/parallax/app/runtime/queue_health.py",
    "src/parallax/app/runtime/wake_bus.py",
    "src/parallax/app/surfaces/api/routes_radar.py",
    "src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py",
    "src/parallax/domains/asset_market/repositories/registry_repository.py",
    "src/parallax/domains/narrative_intel/repositories/narrative_repository.py",
    "src/parallax/domains/pulse_lab/queries/pulse_policy_evaluator.py",
    "src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py",
    "src/parallax/domains/token_intel/read_models/asset_flow_service.py",
    "src/parallax/domains/token_intel/repositories/token_radar_repository.py",
    "src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py",
    "src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py",
    "src/parallax/domains/token_intel/services/token_radar_projection.py",
    "src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py",
    "src/parallax/platform/db/postgres_audit.py",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _class_method_source(relpath: str, class_name: str, method_name: str) -> str:
    text = _text(relpath)
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    source = ast.get_source_segment(text, item)
                    assert source is not None
                    return source
    raise AssertionError(f"{class_name}.{method_name} not found in {relpath}")


def test_token_radar_sql_surface_inventory_is_explicit() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src" / "parallax").rglob("*.py"):
        relpath = path.relative_to(ROOT).as_posix()
        if "alembic/versions/" in relpath or relpath.startswith("tests/"):
            continue
        text = path.read_text(encoding="utf-8")
        if (
            "token_radar_" in text
            and any(sql in text for sql in ("SELECT ", "INSERT ", "UPDATE ", "DELETE "))
            and relpath not in TOKEN_RADAR_SQL_SURFACES
        ):
            offenders.append(relpath)
    assert sorted(offenders) == []


def test_token_radar_product_sql_has_no_venue_compatibility_fallback() -> None:
    forbidden = (
        "venue IS NULL",
        "COALESCE(current_rows.venue",
        "COALESCE(state.venue",
        "DEFAULT 'all' /* compatibility",
        "if venue is None",
    )
    offenders: list[str] = []
    for relpath in TOKEN_RADAR_SQL_SURFACES:
        text = _text(relpath)
        offenders.extend(f"{relpath} contains {token}" for token in forbidden if token in text)
    assert offenders == []


def test_all_current_publication_and_first_seen_sql_is_venue_scoped() -> None:
    repo = _text("src/parallax/domains/token_intel/repositories/token_radar_repository.py")

    assert "AND current_rows.venue = %s" in repo
    assert "AND state.venue = current_rows.venue" in repo
    assert 'ON CONFLICT(projection_version, "window", scope, venue)' in repo
    assert 'ON CONFLICT(projection_version, "window", scope, venue, target_type_key, identity_id)' in repo
    assert "stable_generation_id(" in repo
    assert '"venue": venue' in repo


def test_projection_validation_audit_batches_token_radar_reference_checks() -> None:
    source = _class_method_source(
        "src/parallax/platform/db/postgres_audit.py",
        "ProjectionValidationAudit",
        "run",
    )
    forbidden = (
        "for row in radar_rows",
        "SELECT 1 AS ok FROM token_intents WHERE intent_id = %s",
        "SELECT 1 AS ok FROM registry_assets WHERE asset_id = %s",
        "sample_size = max(0, int(sample))",
    )
    required = (
        "WITH sampled_radar_rows AS",
        "LEFT JOIN token_intents",
        "LEFT JOIN registry_assets",
        "COUNT(*) FILTER",
        "projection_validation_sample_required",
    )
    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []
