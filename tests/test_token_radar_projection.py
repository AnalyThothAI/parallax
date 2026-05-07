from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_projection import _display_symbol, _market, _project_group


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


def test_projection_market_uses_latest_market_snapshot_fields():
    market = _market(
        {
            "primary_venue_id": "venue:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "market_provider": "gmgn_payload",
            "market_observed_at_ms": 1_777_800_000_000,
            "market_price_usd": 0.01,
            "market_market_cap_usd": 1_000_000,
            "market_liquidity_usd": 250_000,
            "market_volume_24h_usd": None,
            "market_open_interest_usd": None,
            "market_holders": 1000,
            "market_price_change_5m_pct": 1.2,
            "market_price_change_1h_pct": 3.4,
            "market_price_change_24h_pct": None,
        },
        identity_status="resolved",
        now_ms=1_777_800_060_000,
    )

    assert market["market_status"] == "fresh"
    assert market["market_observation_status"] == "ready"
    assert market["provider"] == "gmgn_payload"
    assert market["price_usd"] == 0.01
    assert market["market_cap_usd"] == 1_000_000
    assert market["liquidity_usd"] == 250_000
    assert market["holders"] == 1000
    assert market["snapshot_age_ms"] == 60_000
    assert market["snapshot_observed_at_ms"] == 1_777_800_000_000


def test_resolved_pending_market_never_projects_as_driver():
    rows = [
        {
            "event_id": f"event-{index}",
            "intent_id": f"intent-{index}",
            "received_at_ms": 1_777_800_000_000 + index,
            "author_handle": f"voice{index}",
            "is_watched": True,
            "resolution_identity_status": "resolved",
            "resolution_status": "resolved",
            "resolution_confidence": 0.9,
            "resolved_asset_id": "asset:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "primary_venue_id": "venue:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "display_symbol": "PEPE",
            "canonical_symbol": "PEPE",
            "asset_type": "dex_asset",
            "reasons_json": [],
            "risks_json": [],
        }
        for index in range(7)
    ]

    row = _project_group(rows, now_ms=1_777_800_060_000, window="5m", scope="all")

    assert row["market_json"]["market_observation_status"] == "pending_refresh"
    assert row["decision"] == "watch"
