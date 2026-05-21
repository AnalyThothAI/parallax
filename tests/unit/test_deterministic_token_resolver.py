from __future__ import annotations

from decimal import Decimal

import pytest

from gmgn_twitter_intel.domains.token_intel.services.deterministic_token_resolver import (
    DeterministicTokenResolver,
    MentionKeys,
)


def test_symbol_prefers_confirmed_cex_token_before_chain_assets():
    registry = FakeRegistry(
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
        preferred_cex_pricefeeds={
            "PEPE": {
                "pricefeed_id": "pricefeed:cex:binance:swap:PEPEUSDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:PEPE",
            }
        },
        symbol_assets={
            "PEPE": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "chain_id": "eip155:1",
                    "symbol": "PEPE",
                    "market_cap_usd": Decimal("1700624651.5"),
                    "holders": 552439,
                    "liquidity_usd": Decimal("28815241.64"),
                    "observed_at_ms": 1_778_145_000_000,
                }
            ],
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-pepe",
        event_id="event-pepe",
        keys=MentionKeys(symbol="PEPE"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "CexToken"
    assert result.target_id == "cex_token:PEPE"
    assert result.reason_codes == ["CONFIRMED_CEX_TOKEN"]


def test_symbol_cex_token_binds_preferred_usdt_pricefeed():
    registry = FakeRegistry(
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
        preferred_cex_pricefeeds={
            "PEPE": {
                "pricefeed_id": "pricefeed:cex:binance:swap:PEPEUSDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:PEPE",
            }
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-pepe",
        event_id="event-pepe",
        keys=MentionKeys(symbol="PEPE"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "CexToken"
    assert result.target_id == "cex_token:PEPE"
    assert result.pricefeed_id == "pricefeed:cex:binance:swap:PEPEUSDT"
    assert result.candidate_ids == ["pricefeed:cex:binance:swap:PEPEUSDT", "cex_token:PEPE"]


def test_symbol_cex_token_without_binance_pricefeed_does_not_resolve_cex():
    registry = FakeRegistry(
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
        symbol_assets={
            "PEPE": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    "chain_id": "eip155:1",
                    "symbol": "PEPE",
                    "observed_at_ms": 1_778_145_000_000,
                }
            ],
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-pepe",
        event_id="event-pepe",
        keys=MentionKeys(symbol="PEPE"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert result.reason_codes == ["SINGLE_ACTIVE_CHAIN_ASSET"]


def test_symbol_prefers_confirmed_cex_token_before_us_equity_symbol():
    registry = FakeRegistry(
        cex_tokens={"COIN": {"cex_token_id": "cex_token:COIN", "base_symbol": "COIN"}},
        preferred_cex_pricefeeds={
            "COIN": {
                "pricefeed_id": "pricefeed:cex:binance:swap:COINUSDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:COIN",
            }
        },
        us_equities={
            "COIN": {
                "market_instrument_id": "market_instrument:us_equity:COIN",
                "symbol": "COIN",
                "status": "active",
            }
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-coin",
        event_id="event-coin",
        keys=MentionKeys(symbol="COIN"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "CexToken"
    assert result.target_id == "cex_token:COIN"
    assert result.reason_codes == ["CONFIRMED_CEX_TOKEN"]


def test_symbol_prefers_confirmed_us_equity_before_symbol_only_chain_asset():
    registry = FakeRegistry(
        symbol_assets={
            "ON": [
                {
                    "asset_id": "asset:solana:token:onchain",
                    "chain_id": "solana",
                    "symbol": "ON",
                    "market_cap_usd": Decimal("500000"),
                    "holders": 2_000,
                    "liquidity_usd": Decimal("120000"),
                    "observed_at_ms": 1_778_145_000_000,
                }
            ],
        },
        us_equities={
            "ON": {
                "market_instrument_id": "market_instrument:us_equity:ON",
                "symbol": "ON",
                "status": "active",
            }
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-on",
        event_id="event-on",
        keys=MentionKeys(symbol="ON"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "NON_CRYPTO"
    assert result.target_type == "MarketInstrument"
    assert result.target_id == "market_instrument:us_equity:ON"
    assert result.reason_codes == ["CONFIRMED_US_EQUITY"]
    assert result.lookup_keys == []


def test_symbol_without_crypto_candidates_resolves_confirmed_us_equity_as_non_crypto():
    registry = FakeRegistry(
        us_equities={
            "AAOI": {
                "market_instrument_id": "market_instrument:us_equity:AAOI",
                "symbol": "AAOI",
                "status": "active",
            }
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-aaoi",
        event_id="event-aaoi",
        keys=MentionKeys(symbol="AAOI"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "NON_CRYPTO"
    assert result.target_type == "MarketInstrument"
    assert result.target_id == "market_instrument:us_equity:AAOI"
    assert result.reason_codes == ["CONFIRMED_US_EQUITY"]
    assert result.candidate_ids == ["market_instrument:us_equity:AAOI"]
    assert result.lookup_keys == []


def test_us_equity_symbol_wins_over_dex_symbol_only_candidates_after_cex_check():
    registry = FakeRegistry(
        us_equities={
            "DELL": {
                "market_instrument_id": "market_instrument:us_equity:DELL",
                "symbol": "DELL",
                "status": "active",
            }
        },
        symbol_assets={
            "DELL": [
                {
                    "asset_id": "asset:solana:token:dell",
                    "chain_id": "solana",
                    "address": "dell",
                    "symbol": "DELL",
                    "observed_at_ms": 1_778_145_000_000,
                    "market_cap_usd": 10_000_000,
                    "liquidity_usd": 500_000,
                    "holders": 10_000,
                    "provider_rank": 0,
                    "provider_rank_observed_at_ms": 1_778_145_000_000,
                }
            ]
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-dell",
        event_id="event-dell",
        keys=MentionKeys(symbol="DELL"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "NON_CRYPTO"
    assert result.target_type == "MarketInstrument"
    assert result.target_id == "market_instrument:us_equity:DELL"
    assert result.reason_codes == ["CONFIRMED_US_EQUITY"]
    assert result.lookup_keys == []


def test_us_equity_symbol_wins_over_mixed_dex_symbol_only_candidates():
    registry = FakeRegistry(
        us_equities={
            "DELL": {
                "market_instrument_id": "market_instrument:us_equity:DELL",
                "symbol": "DELL",
                "status": "active",
            }
        },
        symbol_assets={
            "DELL": [
                {
                    "asset_id": "asset:solana:token:dell-one",
                    "chain_id": "solana",
                    "address": "dell-one",
                    "symbol": "DELL",
                    "observed_at_ms": 1_778_145_000_000,
                    "provider_rank": 0,
                    "provider_rank_observed_at_ms": 1_778_145_000_000,
                },
                {
                    "asset_id": "asset:solana:token:dell-two",
                    "chain_id": "solana",
                    "address": "dell-two",
                    "symbol": "DELL",
                    "observed_at_ms": 1_778_145_000_000,
                },
            ]
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-dell",
        event_id="event-dell",
        keys=MentionKeys(symbol="DELL"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "NON_CRYPTO"
    assert result.target_type == "MarketInstrument"
    assert result.target_id == "market_instrument:us_equity:DELL"
    assert result.reason_codes == ["CONFIRMED_US_EQUITY"]
    assert result.lookup_keys == []


def test_cex_token_still_wins_over_us_equity_symbol():
    registry = FakeRegistry(
        cex_tokens={"COIN": {"cex_token_id": "cex_token:COIN", "base_symbol": "COIN"}},
        preferred_cex_pricefeeds={
            "COIN": {
                "pricefeed_id": "pricefeed:cex:binance:swap:COINUSDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:COIN",
            }
        },
        us_equities={
            "COIN": {
                "market_instrument_id": "market_instrument:us_equity:COIN",
                "symbol": "COIN",
                "status": "active",
            }
        },
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-coin",
        event_id="event-coin",
        keys=MentionKeys(symbol="COIN"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "CexToken"
    assert result.target_id == "cex_token:COIN"
    assert result.reason_codes == ["CONFIRMED_CEX_TOKEN"]


def test_cex_native_pricefeed_is_exact_before_symbol_resolution():
    registry = FakeRegistry(
        cex_pricefeeds={
            ("binance", "PEPEUSDT"): {
                "pricefeed_id": "pricefeed:cex:binance:swap:PEPEUSDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:PEPE",
            }
        },
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-pepe",
        event_id="event-pepe",
        keys=MentionKeys(symbol="PEPE", exchange="binance", cex_pricefeed_id="PEPEUSDT"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "EXACT"
    assert result.target_type == "CexToken"
    assert result.target_id == "cex_token:PEPE"
    assert result.pricefeed_id == "pricefeed:cex:binance:swap:PEPEUSDT"
    assert result.reason_codes == ["CEX_NATIVE_PRICEFEED_EXACT"]


def test_okx_cex_native_pricefeed_is_not_supported_after_binance_hard_cut():
    registry = FakeRegistry(
        cex_pricefeeds={
            ("okx", "PEPE-USDT"): {
                "pricefeed_id": "pricefeed:cex:okx:swap:PEPE-USDT",
                "subject_type": "CexToken",
                "subject_id": "cex_token:PEPE",
            }
        },
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-pepe",
        event_id="event-pepe",
        keys=MentionKeys(symbol="PEPE", exchange="okx", cex_pricefeed_id="PEPE-USDT"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "NIL"
    assert result.target_type is None
    assert result.target_id is None
    assert result.pricefeed_id is None
    assert result.reason_codes == ["CEX_EXCHANGE_NOT_SUPPORTED"]


def test_symbol_without_cex_token_selects_market_dominant_chain_asset():
    registry = FakeRegistry(
        symbol_assets={
            "UPEG": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
                    "chain_id": "eip155:1",
                    "symbol": "UPEG",
                    "market_cap_usd": Decimal("13215222.41"),
                    "holders": 4913,
                    "liquidity_usd": Decimal("1029326.55"),
                    "observed_at_ms": 1_778_145_000_000,
                },
                {
                    "asset_id": "asset:solana:token:EmCSyLkoao9Q2y4M4AMWREorzrrmVrUDVENgKp5rtEob",
                    "chain_id": "solana",
                    "symbol": "UPEG",
                    "market_cap_usd": Decimal("12748.88"),
                    "holders": 105,
                    "liquidity_usd": Decimal("21208.79"),
                    "observed_at_ms": 1_778_145_000_000,
                },
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-upeg",
        event_id="event-upeg",
        keys=MentionKeys(symbol="UPEG"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"
    assert result.reason_codes == ["MARKET_DOMINANT_CHAIN_ASSET"]
    assert result.candidate_ids == [
        "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
        "asset:solana:token:EmCSyLkoao9Q2y4M4AMWREorzrrmVrUDVENgKp5rtEob",
    ]


def test_symbol_without_dominance_returns_ambiguous_with_candidates():
    registry = FakeRegistry(
        symbol_assets={
            "TIE": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x1111111111111111111111111111111111111111",
                    "chain_id": "eip155:1",
                    "symbol": "TIE",
                    "market_cap_usd": Decimal("100000"),
                    "holders": 500,
                    "liquidity_usd": Decimal("90000"),
                    "observed_at_ms": 1_778_145_000_000,
                },
                {
                    "asset_id": "asset:eip155:8453:erc20:0x2222222222222222222222222222222222222222",
                    "chain_id": "eip155:8453",
                    "symbol": "TIE",
                    "market_cap_usd": Decimal("90000"),
                    "holders": 450,
                    "liquidity_usd": Decimal("80000"),
                    "observed_at_ms": 1_778_145_000_000,
                },
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-tie",
        event_id="event-tie",
        keys=MentionKeys(symbol="TIE"),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "AMBIGUOUS"
    assert result.target_type is None
    assert result.target_id is None
    assert result.reason_codes == ["NO_MARKET_DOMINANT_CHAIN_ASSET"]
    assert "symbol:TIE" in result.lookup_keys


def test_symbol_dominance_requires_field_freshness():
    registry = FakeRegistry(
        symbol_assets={
            "TROLL": [
                {
                    "asset_id": "asset:solana:token:TROLL-A",
                    "chain_id": "solana",
                    "symbol": "TROLL",
                    "market_cap_usd": Decimal("100000000"),
                    "liquidity_usd": Decimal("4000000"),
                    "holders": 55_000,
                    "market_cap_observed_at_ms": 1_700_000_000_000,
                    "liquidity_observed_at_ms": 1_700_000_000_000,
                    "holders_observed_at_ms": 1_700_000_000_000,
                    "market_cap_status": "stale",
                    "liquidity_status": "stale",
                    "holders_status": "stale",
                },
                {
                    "asset_id": "asset:solana:token:TROLL-B",
                    "chain_id": "solana",
                    "symbol": "TROLL",
                    "market_cap_usd": Decimal("500000"),
                    "liquidity_usd": Decimal("200000"),
                    "holders": 2_000,
                    "market_cap_observed_at_ms": 1_700_000_000_000,
                    "liquidity_observed_at_ms": 1_700_000_000_000,
                    "holders_observed_at_ms": 1_700_000_000_000,
                    "market_cap_status": "stale",
                    "liquidity_status": "stale",
                    "holders_status": "stale",
                },
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-troll",
        event_id="event-troll",
        keys=MentionKeys(symbol="TROLL"),
        decision_time_ms=1_700_086_430_000,
    )

    assert result.resolution_status == "AMBIGUOUS"
    assert result.target_type is None
    assert result.target_id is None
    assert result.reason_codes == ["NO_MARKET_DOMINANT_CHAIN_ASSET"]


@pytest.mark.parametrize(
    ("market_fields", "field_age_ms", "expected_status", "expected_target_id"),
    [
        ({"market_cap_usd": Decimal("600000")}, 60_000, "UNIQUE_BY_CONTEXT", "asset:eip155:1:erc20:0xaaaa"),
        ({"holders": 5_000}, 60_000, "UNIQUE_BY_CONTEXT", "asset:eip155:1:erc20:0xaaaa"),
        ({"liquidity_usd": Decimal("250000")}, 60_000, "UNIQUE_BY_CONTEXT", "asset:eip155:1:erc20:0xaaaa"),
        (
            {"market_cap_usd": Decimal("600000"), "holders": 5_000},
            25 * 60 * 60 * 1000,
            "AMBIGUOUS",
            None,
        ),
        (
            {"holders": 5_000, "liquidity_usd": Decimal("250000")},
            25 * 60 * 60 * 1000,
            "AMBIGUOUS",
            None,
        ),
        (
            {"market_cap_usd": Decimal("600000"), "holders": 5_000, "liquidity_usd": Decimal("250000")},
            25 * 60 * 60 * 1000,
            "AMBIGUOUS",
            None,
        ),
    ],
)
def test_symbol_market_dominance_accepts_any_one_fresh_market_field(
    market_fields,
    field_age_ms,
    expected_status,
    expected_target_id,
):
    decision_time_ms = 1_778_200_000_000
    observed_at_ms = decision_time_ms - field_age_ms
    registry = FakeRegistry(
        symbol_assets={
            "SPARSE": [
                _market_asset(
                    "asset:eip155:1:erc20:0xaaaa",
                    market_fields=market_fields,
                    observed_at_ms=observed_at_ms,
                ),
                _market_asset(
                    "asset:eip155:56:erc20:0xbbbb",
                    market_fields=_smaller_market_fields(market_fields),
                    observed_at_ms=observed_at_ms,
                ),
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-sparse",
        event_id="event-sparse",
        keys=MentionKeys(symbol="SPARSE"),
        decision_time_ms=decision_time_ms,
    )

    assert result.resolution_status == expected_status
    assert result.target_id == expected_target_id
    if expected_status == "UNIQUE_BY_CONTEXT":
        assert result.reason_codes == ["MARKET_DOMINANT_CHAIN_ASSET"]
    else:
        assert result.reason_codes == ["NO_MARKET_DOMINANT_CHAIN_ASSET"]


def test_symbol_without_dominance_falls_back_to_fresh_provider_rank():
    decision_time_ms = 1_778_200_000_000
    registry = FakeRegistry(
        symbol_assets={
            "RANKED": [
                _provider_rank_asset(
                    "asset:eip155:1:erc20:0xaaaa",
                    provider_rank=1,
                    observed_at_ms=decision_time_ms - 60_000,
                ),
                _provider_rank_asset(
                    "asset:eip155:56:erc20:0xbbbb",
                    provider_rank=0,
                    observed_at_ms=decision_time_ms - 60_000,
                ),
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-ranked",
        event_id="event-ranked",
        keys=MentionKeys(symbol="RANKED"),
        decision_time_ms=decision_time_ms,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:56:erc20:0xbbbb"
    assert result.reason_codes == ["RESOLVED_BY_PROVIDER_RANK"]


def test_symbol_provider_rank_fallback_requires_fresh_identity_evidence():
    decision_time_ms = 1_778_200_000_000
    registry = FakeRegistry(
        symbol_assets={
            "RANKED": [
                _provider_rank_asset(
                    "asset:eip155:1:erc20:0xaaaa",
                    provider_rank=1,
                    observed_at_ms=decision_time_ms - 25 * 60 * 60 * 1000,
                ),
                _provider_rank_asset(
                    "asset:eip155:56:erc20:0xbbbb",
                    provider_rank=0,
                    observed_at_ms=decision_time_ms - 25 * 60 * 60 * 1000,
                ),
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-ranked",
        event_id="event-ranked",
        keys=MentionKeys(symbol="RANKED"),
        decision_time_ms=decision_time_ms,
    )

    assert result.resolution_status == "AMBIGUOUS"
    assert result.target_id is None
    assert result.reason_codes == ["NO_MARKET_DOMINANT_CHAIN_ASSET"]


def test_symbol_selects_market_dominant_asset_when_lead_is_clear_but_not_extreme():
    registry = FakeRegistry(
        symbol_assets={
            "SLOP": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                    "chain_id": "eip155:1",
                    "symbol": "SLOP",
                    "market_cap_usd": Decimal("2274499.25"),
                    "holders": 1935,
                    "liquidity_usd": Decimal("861143.63"),
                    "observed_at_ms": 1_778_161_505_208,
                },
                {
                    "asset_id": "asset:solana:token:FqvtZ2UFR9we82Ni4LeacC1zyTiQ77usDo31DUokpump",
                    "chain_id": "solana",
                    "symbol": "SLOP",
                    "market_cap_usd": Decimal("49054.27"),
                    "holders": 6850,
                    "liquidity_usd": Decimal("51296.73"),
                    "observed_at_ms": 1_778_161_505_208,
                },
                {
                    "asset_id": "asset:eip155:1:erc20:0x0557cb4750c828aa192948384ec8a19805a41869",
                    "chain_id": "eip155:1",
                    "symbol": "SLOP",
                    "market_cap_usd": Decimal("117802.82"),
                    "holders": 26,
                    "liquidity_usd": Decimal("31489.35"),
                    "observed_at_ms": 1_778_161_505_208,
                },
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-slop",
        event_id="event-slop",
        keys=MentionKeys(symbol="SLOP"),
        decision_time_ms=1_778_162_003_774,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108"
    assert result.reason_codes == ["MARKET_DOMINANT_CHAIN_ASSET"]


def test_symbol_selects_highest_quality_market_asset_without_gap_threshold():
    registry = FakeRegistry(
        symbol_assets={
            "ALICE": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x1111111111111111111111111111111111111111",
                    "chain_id": "eip155:1",
                    "symbol": "ALICE",
                    "market_cap_usd": Decimal("10000000"),
                    "holders": 5000,
                    "liquidity_usd": Decimal("1000000"),
                    "observed_at_ms": 1_778_161_505_208,
                },
                {
                    "asset_id": "asset:eip155:56:erc20:0x2222222222222222222222222222222222222222",
                    "chain_id": "eip155:56",
                    "symbol": "ALICE",
                    "market_cap_usd": Decimal("9500000"),
                    "holders": 4800,
                    "liquidity_usd": Decimal("950000"),
                    "observed_at_ms": 1_778_161_505_208,
                },
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-alice",
        event_id="event-alice",
        keys=MentionKeys(symbol="ALICE"),
        decision_time_ms=1_778_162_003_774,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:1:erc20:0x1111111111111111111111111111111111111111"
    assert result.reason_codes == ["MARKET_DOMINANT_CHAIN_ASSET"]


def test_symbol_resolution_uses_retained_asset_even_when_price_observation_is_stale():
    registry = FakeRegistry(
        symbol_assets={
            "UPEG": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
                    "chain_id": "eip155:1",
                    "symbol": "UPEG",
                    "market_cap_usd": Decimal("13215222.41"),
                    "holders": 4913,
                    "liquidity_usd": Decimal("1029326.55"),
                    "observed_at_ms": 1_778_145_000_000,
                }
            ],
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-upeg-stale",
        event_id="event-upeg-stale",
        keys=MentionKeys(symbol="UPEG"),
        decision_time_ms=1_778_145_000_000 + 8 * 60 * 60 * 1000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"
    assert result.reason_codes == ["SINGLE_ACTIVE_CHAIN_ASSET"]


def test_chain_address_is_exact_asset_and_beats_symbol():
    registry = FakeRegistry(
        address_assets={
            ("eip155:8453", "0x2cc0db4f8977accadb5b7da59c5923e14328eba3"): {
                "asset_id": "asset:eip155:8453:erc20:0x2cc0db4f8977accadb5b7da59c5923e14328eba3",
                "chain_id": "eip155:8453",
                "address": "0x2cc0db4f8977accadb5b7da59c5923e14328eba3",
                "symbol": "VERSA",
            }
        },
        cex_tokens={"VERSA": {"cex_token_id": "cex_token:VERSA", "base_symbol": "VERSA"}},
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-versa",
        event_id="event-versa",
        keys=MentionKeys(
            symbol="VERSA",
            chain_id="eip155:8453",
            address="0x2cc0db4f8977accadb5b7da59c5923e14328eba3",
        ),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "EXACT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:eip155:8453:erc20:0x2cc0db4f8977accadb5b7da59c5923e14328eba3"
    assert result.reason_codes == ["CHAIN_ADDRESS_EXACT"]


def test_ton_chain_address_is_exact_asset():
    address = "EQC1RZb5BF_eWrR0AYCtpUig5c4CQoupQ_v-ABsRmO5pbgQL"
    registry = FakeRegistry(
        address_assets={
            ("ton", address.lower()): {
                "asset_id": f"asset:ton:token:{address}",
                "chain_id": "ton",
                "address": address,
                "symbol": "MTGA",
            }
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-mtga",
        event_id="event-mtga",
        keys=MentionKeys(symbol="MTGA", chain_id="ton", address=address),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "EXACT"
    assert result.target_type == "Asset"
    assert result.target_id == f"asset:ton:token:{address}"
    assert result.reason_codes == ["CHAIN_ADDRESS_EXACT"]


def test_address_without_chain_selects_solana_when_same_address_exists_on_multiple_chains():
    address = "shared-address"
    registry = FakeRegistry(
        address_assets={
            ("eip155:1", address): {
                "asset_id": "asset:eip155:1:erc20:shared-address",
                "chain_id": "eip155:1",
                "address": address,
            },
            ("solana", address): {
                "asset_id": "asset:solana:token:shared-address",
                "chain_id": "solana",
                "address": address,
            },
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-address",
        event_id="event-address",
        keys=MentionKeys(address=address),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_type == "Asset"
    assert result.target_id == "asset:solana:token:shared-address"
    assert result.reason_codes == ["RESOLVED_BY_CHAIN_PRIORITY"]
    assert result.candidate_ids == [
        "asset:solana:token:shared-address",
        "asset:eip155:1:erc20:shared-address",
    ]


def test_address_without_chain_selects_ethereum_before_other_evm_chains():
    address = "0xabc0000000000000000000000000000000000000"
    registry = FakeRegistry(
        address_assets={
            ("eip155:8453", address): {
                "asset_id": f"asset:eip155:8453:erc20:{address}",
                "chain_id": "eip155:8453",
                "address": address,
            },
            ("eip155:56", address): {
                "asset_id": f"asset:eip155:56:erc20:{address}",
                "chain_id": "eip155:56",
                "address": address,
            },
            ("eip155:1", address): {
                "asset_id": f"asset:eip155:1:erc20:{address}",
                "chain_id": "eip155:1",
                "address": address,
            },
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-address",
        event_id="event-address",
        keys=MentionKeys(address=address),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_id == f"asset:eip155:1:erc20:{address}"
    assert result.reason_codes == ["RESOLVED_BY_CHAIN_PRIORITY"]


def test_address_without_chain_uses_stable_fallback_for_unknown_chains():
    address = "unknown-address"
    registry = FakeRegistry(
        address_assets={
            ("chain-z", address): {
                "asset_id": "asset:chain-z:token:unknown-address",
                "chain_id": "chain-z",
                "address": address,
            },
            ("chain-a", address): {
                "asset_id": "asset:chain-a:token:unknown-address",
                "chain_id": "chain-a",
                "address": address,
            },
        }
    )

    result = DeterministicTokenResolver(registry=registry).resolve(
        intent_id="intent-address",
        event_id="event-address",
        keys=MentionKeys(address=address),
        decision_time_ms=1_778_145_100_000,
    )

    assert result.resolution_status == "UNIQUE_BY_CONTEXT"
    assert result.target_id == "asset:chain-a:token:unknown-address"
    assert result.reason_codes == ["RESOLVED_BY_CHAIN_PRIORITY"]


class FakeRegistry:
    def __init__(
        self,
        *,
        cex_tokens=None,
        cex_pricefeeds=None,
        preferred_cex_pricefeeds=None,
        symbol_assets=None,
        address_assets=None,
        us_equities=None,
    ):
        self.cex_tokens = cex_tokens or {}
        self.cex_pricefeeds = cex_pricefeeds or {}
        self.preferred_cex_pricefeeds = preferred_cex_pricefeeds or {}
        self.symbol_assets = symbol_assets or {}
        self.address_assets = address_assets or {}
        self.us_equities = us_equities or {}

    def find_cex_token(self, symbol):
        return self.cex_tokens.get(str(symbol).upper())

    def find_cex_pricefeed(self, *, exchange, native_market_id):
        return self.cex_pricefeeds.get((str(exchange).lower(), str(native_market_id).upper()))

    def find_preferred_cex_pricefeed(self, base_symbol):
        return self.preferred_cex_pricefeeds.get(str(base_symbol).upper())

    def find_assets_by_symbol_with_identity_metadata(self, symbol):
        return [_registry_asset_row(row) for row in self.symbol_assets.get(str(symbol).upper(), [])]

    def find_us_equity_symbol(self, symbol):
        return self.us_equities.get(str(symbol).upper())

    def find_assets_by_address(self, *, chain_id=None, address):
        normalized = str(address).lower()
        if chain_id:
            row = self.address_assets.get((chain_id, normalized))
            return [row] if row else []
        return [
            row for (_stored_chain, stored_address), row in self.address_assets.items() if stored_address == normalized
        ]


def _registry_asset_row(row):
    if row.get("market_cap_observed_at_ms") is not None:
        return row
    observed_at_ms = row.get("observed_at_ms")
    if observed_at_ms is None:
        return row
    return {
        **row,
        "price_observed_at_ms": observed_at_ms,
        "market_cap_observed_at_ms": observed_at_ms,
        "liquidity_observed_at_ms": observed_at_ms,
        "holders_observed_at_ms": observed_at_ms,
        "market_cap_status": "fresh",
        "liquidity_status": "fresh",
        "holders_status": "fresh",
    }


def _market_asset(asset_id: str, *, market_fields: dict[str, object], observed_at_ms: int) -> dict[str, object]:
    row: dict[str, object] = {
        "asset_id": asset_id,
        "chain_id": asset_id.split(":")[1],
        "symbol": "SPARSE",
        "market_cap_usd": None,
        "holders": None,
        "liquidity_usd": None,
        "market_cap_observed_at_ms": None,
        "holders_observed_at_ms": None,
        "liquidity_observed_at_ms": None,
    }
    observed_keys = {
        "market_cap_usd": "market_cap_observed_at_ms",
        "holders": "holders_observed_at_ms",
        "liquidity_usd": "liquidity_observed_at_ms",
    }
    for field, value in market_fields.items():
        row[field] = value
        row[observed_keys[field]] = observed_at_ms
    return row


def _smaller_market_fields(market_fields: dict[str, object]) -> dict[str, object]:
    smaller = {
        "market_cap_usd": Decimal("100000"),
        "holders": 50,
        "liquidity_usd": Decimal("10000"),
    }
    return {field: smaller[field] for field in market_fields}


def _provider_rank_asset(asset_id: str, *, provider_rank: int, observed_at_ms: int) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "chain_id": asset_id.split(":")[1],
        "symbol": "RANKED",
        "provider_rank": provider_rank,
        "provider_rank_observed_at_ms": observed_at_ms,
    }
