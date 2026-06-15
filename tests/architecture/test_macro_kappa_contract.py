from __future__ import annotations

from pathlib import Path

from parallax.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
MACRO_REPOSITORY = ROOT / "src/parallax/domains/macro_intel/repositories/macro_intel_repository.py"
MACRO_MODULE_VIEWS = ROOT / "src/parallax/domains/macro_intel/services/macro_module_views.py"


def test_macro_series_publish_uses_row_level_payload_hash_updates() -> None:
    text = MACRO_REPOSITORY.read_text(encoding="utf-8")

    assert "FROM unnest(%s::text[], %s::date[])" in text
    assert "AND NOT EXISTS" in text
    assert "ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET" in text
    assert "WHERE macro_observation_series_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in text


def test_macro_series_existing_payload_hash_is_required_without_empty_fallback() -> None:
    text = MACRO_REPOSITORY.read_text(encoding="utf-8")

    assert 'str(row.get("payload_hash") or "")' not in text
    assert 'row.get("payload_hash") or ""' not in text
    assert "_existing_series_payload_hash(row)" in text


def test_macro_view_snapshot_repository_requires_formal_json_sections_without_defaults() -> None:
    text = MACRO_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'Jsonb(snapshot.get("panels_json") or {})',
        'Jsonb(snapshot.get("indicators_json") or {})',
        'Jsonb(snapshot.get("triggers_json") or [])',
        'Jsonb(snapshot.get("data_gaps_json") or [])',
        'Jsonb(snapshot.get("source_coverage_json") or {})',
        'Jsonb(snapshot.get("features_json") or {})',
        'Jsonb(snapshot.get("chain_json") or {})',
        'Jsonb(snapshot.get("scenario_json") or {})',
        'Jsonb(snapshot.get("scorecard_json") or {})',
        '"panels_json": snapshot.get("panels_json") or {}',
        '"indicators_json": snapshot.get("indicators_json") or {}',
        '"triggers_json": snapshot.get("triggers_json") or []',
        '"data_gaps_json": snapshot.get("data_gaps_json") or []',
        '"source_coverage_json": snapshot.get("source_coverage_json") or {}',
        '"features_json": snapshot.get("features_json") or {}',
        '"chain_json": snapshot.get("chain_json") or {}',
        '"scenario_json": snapshot.get("scenario_json") or {}',
        '"scorecard_json": snapshot.get("scorecard_json") or {}',
    )
    required = (
        '_required_snapshot_mapping(snapshot, "panels_json")',
        '_required_snapshot_mapping(snapshot, "indicators_json")',
        '_required_snapshot_mapping(snapshot, "source_coverage_json")',
        '_required_snapshot_mapping(snapshot, "features_json")',
        '_required_snapshot_mapping(snapshot, "chain_json")',
        '_required_snapshot_mapping(snapshot, "scenario_json")',
        '_required_snapshot_mapping(snapshot, "scorecard_json")',
        '_required_snapshot_list(snapshot, "triggers_json")',
        '_required_snapshot_list(snapshot, "data_gaps_json")',
    )

    assert [token for token in forbidden if token in text] == []
    for token in required:
        assert token in text


def test_macro_module_view_requires_formal_snapshot_sections_without_defaults() -> None:
    text = MACRO_MODULE_VIEWS.read_text(encoding="utf-8")
    forbidden = (
        '_mapping(snapshot.get("features_json"))',
        '_mapping(snapshot.get("scenario_json"))',
        '_mapping(snapshot.get("chain_json"))',
        '_sequence(snapshot.get("data_gaps_json"))',
    )
    required = (
        "_macro_module_view_snapshot_sections(snapshot)",
        '_required_snapshot_mapping(snapshot, "panels_json")',
        '_required_snapshot_mapping(snapshot, "indicators_json")',
        '_required_snapshot_mapping(snapshot, "source_coverage_json")',
        '_required_snapshot_mapping(snapshot, "features_json")',
        '_required_snapshot_mapping(snapshot, "chain_json")',
        '_required_snapshot_mapping(snapshot, "scenario_json")',
        '_required_snapshot_mapping(snapshot, "scorecard_json")',
        '_required_snapshot_list(snapshot, "triggers_json")',
        '_required_snapshot_list(snapshot, "data_gaps_json")',
        "macro_module_view_snapshot_section_required",
        "macro_module_view_snapshot_section_invalid",
    )

    assert [token for token in forbidden if token in text] == []
    for token in required:
        assert token in text


def test_macro_daily_brief_worker_is_projection_read_model_without_provider_io() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    manifest = manifests["macro_daily_brief_projection"]

    assert manifest.kind == "projection"
    assert manifest.uses_provider_io is False
    assert manifest.wakes_on == ("macro_view_snapshot_updated",)
    assert manifest.writes_read_models == ("macro_daily_briefs",)
    assert manifest.current_read_model_identities == (("macro_daily_briefs", ("brief_key",)),)
    assert manifest.input_contract == ("macro_view_snapshots current", "macro_observation_series_rows current")
