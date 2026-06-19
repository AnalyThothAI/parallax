from __future__ import annotations

import pytest

from parallax.domains.news_intel.types.news_material_identity import (
    material_title_fingerprint,
    material_title_is_eligible,
    provider_symbol_set,
    symbol_sets_compatible,
)


def test_material_title_fingerprint_strips_known_source_prefix() -> None:
    assert material_title_fingerprint(
        "COINDESK: Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated"
    ) == material_title_fingerprint("Live Markets: Bitcoin crashes to $62,000 as billions of longs get liquidated")


def test_material_title_fingerprint_strips_mixed_case_and_compact_source_prefixes() -> None:
    assert material_title_fingerprint("CoinDesk: Live Markets: Bitcoin crashes sharply again") == (
        material_title_fingerprint("Live Markets: Bitcoin crashes sharply again")
    )
    assert material_title_fingerprint("FINANCEFEEDS: Bessent urges lawmakers to pass crypto clarity act") == (
        material_title_fingerprint("Bessent urges lawmakers to pass crypto clarity act")
    )
    assert material_title_fingerprint("AFP: Fed leaves interest rates unchanged after meeting") == (
        material_title_fingerprint("Fed leaves interest rates unchanged after meeting")
    )


def test_material_title_fingerprint_keeps_non_source_prefix() -> None:
    assert material_title_fingerprint("SEC: New crypto policy expected") == "sec new crypto policy expected"


def test_material_title_requires_enough_tokens() -> None:
    assert material_title_is_eligible("bitcoin crashes to lows") is False
    assert (
        material_title_is_eligible("live markets bitcoin crashes to 62 000 as billions of longs get liquidated") is True
    )


def test_symbol_sets_are_compatible_when_overlapping_or_missing() -> None:
    assert provider_symbol_set([{"symbol": "btc"}, {"symbol": "BILL"}]) == {"BTC", "BILL"}
    assert symbol_sets_compatible({"BTC"}, {"BTC", "ETH"}) is True
    assert symbol_sets_compatible({" BTC "}, {"BTC"}) is True
    assert symbol_sets_compatible({"SOL"}, {"BTC", "ETH"}) is False
    assert symbol_sets_compatible(set(), {"BTC"}) is True


def test_provider_symbol_set_accepts_mapping_values_and_rejects_json_strings() -> None:
    assert provider_symbol_set({"symbol": "btc"}) == {"BTC"}
    assert provider_symbol_set({"btc": {"symbol": "btc"}, "eth": {"symbol": "ETH"}}) == {"BTC", "ETH"}
    with pytest.raises(ValueError, match="news_material_identity_provider_token_impacts_json_required"):
        provider_symbol_set('[{"symbol": "sol"}, {"symbol": "BTC"}]')
    with pytest.raises(ValueError, match="news_material_identity_provider_token_impacts_json_required"):
        provider_symbol_set('{"primary": {"symbol": "xrp"}}')
