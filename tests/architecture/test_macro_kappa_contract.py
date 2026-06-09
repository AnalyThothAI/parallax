from __future__ import annotations

from pathlib import Path

from parallax.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
MACRO_REPOSITORY = ROOT / "src/parallax/domains/macro_intel/repositories/macro_intel_repository.py"


def test_macro_series_publish_uses_row_level_payload_hash_updates() -> None:
    text = MACRO_REPOSITORY.read_text(encoding="utf-8")

    assert "FROM unnest(%s::text[], %s::date[])" in text
    assert "AND NOT EXISTS" in text
    assert "ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET" in text
    assert "WHERE macro_observation_series_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in text


def test_macro_daily_brief_worker_is_projection_read_model_without_provider_io() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    manifest = manifests["macro_daily_brief_projection"]

    assert manifest.kind == "projection"
    assert manifest.uses_provider_io is False
    assert manifest.wakes_on == ("macro_view_snapshot_updated",)
    assert manifest.writes_read_models == ("macro_daily_briefs",)
    assert manifest.current_read_model_identities == (("macro_daily_briefs", ("brief_key",)),)
    assert manifest.input_contract == ("macro_view_snapshots current", "macro_observation_series_rows current")
