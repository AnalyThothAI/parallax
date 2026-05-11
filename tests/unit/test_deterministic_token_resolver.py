from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.domains.token_intel.services.deterministic_token_resolver import (
    DeterministicTokenResolver,
    MentionKeys,
)


def test_symbol_prefers_confirmed_cex_token_before_chain_assets():
    registry = FakeRegistry(
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
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
                "pricefeed_id": "pricefeed:cex:okx:spot:PEPE-USDT",
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
    assert result.pricefeed_id == "pricefeed:cex:okx:spot:PEPE-USDT"
    assert result.candidate_ids == ["pricefeed:cex:okx:spot:PEPE-USDT", "cex_token:PEPE"]


def test_cex_native_pricefeed_is_exact_before_symbol_resolution():
    registry = FakeRegistry(
        cex_pricefeeds={
            ("binance", "PEPEUSDT"): {
                "pricefeed_id": "pricefeed:cex:binance:spot:PEPEUSDT",
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
    assert result.pricefeed_id == "pricefeed:cex:binance:spot:PEPEUSDT"
    assert result.reason_codes == ["CEX_NATIVE_PRICEFEED_EXACT"]


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


class FakeRegistry:
    def __init__(
        self,
        *,
        cex_tokens=None,
        cex_pricefeeds=None,
        preferred_cex_pricefeeds=None,
        symbol_assets=None,
        address_assets=None,
    ):
        self.cex_tokens = cex_tokens or {}
        self.cex_pricefeeds = cex_pricefeeds or {}
        self.preferred_cex_pricefeeds = preferred_cex_pricefeeds or {}
        self.symbol_assets = symbol_assets or {}
        self.address_assets = address_assets or {}

    def find_cex_token(self, symbol):
        return self.cex_tokens.get(str(symbol).upper())

    def find_cex_pricefeed(self, *, exchange, native_market_id):
        return self.cex_pricefeeds.get((str(exchange).lower(), str(native_market_id).upper()))

    def find_preferred_cex_pricefeed(self, base_symbol):
        return self.preferred_cex_pricefeeds.get(str(base_symbol).upper())

    def find_assets_by_symbol_with_identity_metadata(self, symbol):
        return [_registry_asset_row(row) for row in self.symbol_assets.get(str(symbol).upper(), [])]

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
