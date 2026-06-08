from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CEX_OI_REPOSITORY = ROOT / "src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py"


def test_cex_oi_board_publish_uses_row_level_serving_updates() -> None:
    text = CEX_OI_REPOSITORY.read_text(encoding="utf-8")

    assert "AND NOT (row_id = ANY(%s::text[]))" in text
    assert "WHERE cex_oi_radar_rows.rank IS DISTINCT FROM excluded.rank" in text
    assert "computed_at_ms IS DISTINCT FROM excluded.computed_at_ms" not in text
