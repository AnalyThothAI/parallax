from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TOKEN_RADAR_SQL_SURFACES = (
    "src/parallax/app/runtime/ops_cli_queries.py",
    "src/parallax/app/runtime/ops_diagnostics.py",
    "src/parallax/app/runtime/queue_health.py",
    "src/parallax/app/runtime/wake_bus.py",
    "src/parallax/app/surfaces/api/routes_radar.py",
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
    "src/parallax/platform/agent_read_tools.py",
    "src/parallax/platform/db/postgres_audit.py",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
