from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.pipeline.deterministic_token_resolver import (
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

    def find_assets_by_symbol_with_latest_observation(self, symbol):
        return list(self.symbol_assets.get(str(symbol).upper(), []))

    def find_assets_by_address(self, *, chain_id=None, address):
        normalized = str(address).lower()
        if chain_id:
            row = self.address_assets.get((chain_id, normalized))
            return [row] if row else []
        return [
            row
            for (_stored_chain, stored_address), row in self.address_assets.items()
            if stored_address == normalized
        ]
