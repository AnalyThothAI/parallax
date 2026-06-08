from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MACRO_REPOSITORY = ROOT / "src/parallax/domains/macro_intel/repositories/macro_intel_repository.py"


def test_macro_series_publish_uses_row_level_payload_hash_updates() -> None:
    text = MACRO_REPOSITORY.read_text(encoding="utf-8")

    assert "FROM unnest(%s::text[], %s::date[])" in text
    assert "AND NOT EXISTS" in text
    assert "ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET" in text
    assert "WHERE macro_observation_series_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in text
