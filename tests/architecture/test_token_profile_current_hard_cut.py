from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"


def test_public_token_profile_read_model_reads_current_facts_only() -> None:
    text = (SRC / "domains/asset_market/read_models/token_profile_read_model.py").read_text(encoding="utf-8")

    assert "GMGN_DEX_PROFILE_PROVIDER" not in text
    assert "profiles_for_asset_ids" not in text
    assert "asset_profiles" not in text
    assert "current_for_targets" in text


def test_public_read_paths_construct_token_profile_read_model_with_current_repository() -> None:
    violations: list[str] = []
    for path in [
        SRC / "app/surfaces/api/http.py",
        SRC / "app/surfaces/cli/main.py",
        SRC / "app/runtime/bootstrap.py",
    ]:
        text = path.read_text(encoding="utf-8")
        if "TokenProfileReadModel(asset_profiles=" in text:
            violations.append(path.as_posix())

    assert violations == []


def test_public_read_paths_do_not_call_profile_providers() -> None:
    public_paths = [
        SRC / "app/surfaces/api/http.py",
        SRC / "app/surfaces/cli/main.py",
        SRC / "domains/token_intel/read_models/asset_flow_service.py",
    ]
    violations: list[str] = []
    for path in public_paths:
        text = path.read_text(encoding="utf-8")
        if ".token_profile(" in text:
            violations.append(f"{path}: token_profile call")

    assert violations == []


def test_public_token_profile_read_model_requires_formal_current_row_fields_without_defaults() -> None:
    text = (SRC / "domains/asset_market/read_models/token_profile_read_model.py").read_text(encoding="utf-8")

    assert "token_profile_current_public_required" in text
    assert "token_profile_current_public_invalid" in text
    assert '(_clean(row.get("status")) or "pending").lower()' not in text
    assert 'return dict(payload) if isinstance(payload, dict) else {}' not in text
    assert "if not isinstance(value, (list, tuple)):\n        return []" not in text


def test_no_cex_token_registry_icon_compatibility_path_remains() -> None:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        if "/platform/db/alembic/versions/" in path.as_posix():
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "cex_tokens.logo" in line or "update_cex_token_icon" in line or "cex_token_icon_static" in line:
                violations.append(f"{path.relative_to(SRC).as_posix()}:{index}:{line.strip()}")

    assert violations == []


def test_token_radar_frontend_has_no_raw_icon_fallback() -> None:
    frontend_paths = [
        ROOT / "web/src/shared/model/tokenRadarCompactCase.ts",
        ROOT / "web/src/features/live/ui/TokenRadarTable.tsx",
    ]
    forbidden = ("token_snapshot", "raw_payload_json", "tokenLogoUrl")
    violations = [
        f"{path.relative_to(ROOT)} uses {token}"
        for path in frontend_paths
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]

    assert violations == []


def test_token_profile_current_dirty_target_source_watermark_has_no_runtime_fallback() -> None:
    repository = (
        SRC / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py"
    ).read_text(encoding="utf-8")
    ops_queries = (SRC / "app/runtime/ops_cli_queries.py").read_text(encoding="utf-8")
    producers = [
        SRC / "domains/asset_market/runtime/asset_profile_refresh_worker.py",
        SRC / "domains/asset_market/runtime/token_image_mirror_worker.py",
    ]
    forbidden = (
        'target.get("source_watermark_ms") or target.get("computed_at_ms")',
        'target.get("computed_at_ms") or target.get("updated_at_ms")',
        'target.get("updated_at_ms") or default',
        'int(row["source_watermark_ms"] or now_ms)',
        'int(row.get("source_watermark_ms") or now_ms)',
        'int(claim.get("source_watermark_ms") or now_ms)',
        '"source_watermark_ms": int(row.get("source_watermark_ms") or now_ms)',
        '"source_watermark_ms": int(claim.get("source_watermark_ms") or now_ms)',
    )

    assert "token_profile_current_dirty_target_source_watermark_required" in repository
    assert "token_profile_image_repair_source_watermark_required" in ops_queries
    assert [token for token in forbidden if token in repository or token in ops_queries] == []
    assert [
        f"{path.relative_to(SRC)} contains {token}"
        for path in producers
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ] == []
