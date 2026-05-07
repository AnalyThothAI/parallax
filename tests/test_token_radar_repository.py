from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.storage.token_radar_repository import _json_payload


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    payload = _json_payload(
        {
            "price_json": {
                "price_quote": Decimal("2.564"),
                "nested": {"volume_24h_usd": Decimal("123.45")},
            },
            "score_json": {},
            "intent_json": {},
            "asset_json": {},
            "primary_venue_json": None,
            "target_json": {},
            "attention_json": {},
            "resolution_json": {},
            "market_json": {},
            "data_health_json": {},
            "source_event_ids_json": [],
        }
    )

    assert payload["price_json"].obj["price_quote"] == 2.564
    assert payload["price_json"].obj["nested"]["volume_24h_usd"] == 123.45
