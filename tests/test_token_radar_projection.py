from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_projection import _display_symbol, _project_group


def test_token_radar_row_id_is_unique_per_window_and_scope():
    source_row = {
        "event_id": "event-1",
        "intent_id": "intent-1",
        "received_at_ms": 1_777_800_000_000,
        "author_handle": "toly",
        "is_watched": True,
        "resolution_identity_status": "unresolved",
        "resolution_status": "unresolved",
        "resolution_confidence": 0.4,
        "resolved_asset_id": None,
        "primary_venue_id": None,
        "display_symbol": "VERSA",
        "asset_type": None,
        "reasons_json": ["no_exact_ca"],
        "risks_json": [],
    }

    all_5m = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="all")
    matched_5m = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="matched")
    all_1h = _project_group([source_row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert len({all_5m["row_id"], matched_5m["row_id"], all_1h["row_id"]}) == 3


def test_projection_display_symbol_ignores_address_like_labels():
    row = {
        "display_symbol": "3iqrRNGG111111111111111111111111111111wNpump",
        "canonical_symbol": "3IQRRNGG111111111111111111111111111111WNPUMP",
        "base_symbol": "REAL",
    }

    assert _display_symbol(row) == "REAL"


def test_projection_display_symbol_returns_none_when_only_ca_is_known():
    row = {
        "display_symbol": None,
        "canonical_symbol": "3IQRRNGG111111111111111111111111111111WNPUMP",
        "base_symbol": None,
    }

    assert _display_symbol(row) is None
