from __future__ import annotations

from gmgn_twitter_intel.pipeline.entity_extractor import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.pipeline.token_evidence_builder import build_token_evidence
from gmgn_twitter_intel.pipeline.token_intent_builder import build_token_intents
from gmgn_twitter_intel.pipeline.token_intent_resolver import TokenIntentResolver


def test_token_intent_resolver_uses_cex_token_before_chain_candidates():
    registry = FakeRegistry(
        cex_tokens={"PEPE": {"cex_token_id": "cex_token:PEPE", "base_symbol": "PEPE"}},
        symbol_assets={"PEPE": [{"asset_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"}]},
    )
    evidence = _evidence("$PEPE")
    intent = build_token_intents(event_id="event-pepe", evidence=evidence, created_at_ms=1_778_145_100_000)[0]

    decision = TokenIntentResolver(registry=registry, resolutions=FakeResolutions()).resolve(
        intent,
        evidence,
        decision_time_ms=1_778_145_100_000,
    )

    assert decision.resolution_status == "UNIQUE_BY_CONTEXT"
    assert decision.target_type == "CexToken"
    assert decision.target_id == "cex_token:PEPE"
    assert decision.reason_codes == ["CONFIRMED_CEX_TOKEN"]


def test_token_intent_resolver_resolves_base_ca_as_exact_asset():
    address = "0x2cc0db4f8977accadb5b7da59c5923e14328eba3"
    registry = FakeRegistry(
        address_assets={
            ("eip155:8453", address): {
                "asset_id": f"asset:eip155:8453:erc20:{address}",
                "chain_id": "eip155:8453",
                "address": address,
            }
        }
    )
    evidence = _evidence(f"$VERSA {address} on Base")
    intents = build_token_intents(event_id="event-versa", evidence=evidence, created_at_ms=1)
    intent = [item for item in intents if item.address_hint][0]

    decision = TokenIntentResolver(registry=registry, resolutions=FakeResolutions()).resolve(
        intent,
        evidence,
        decision_time_ms=1_778_145_100_000,
    )

    assert decision.resolution_status == "EXACT"
    assert decision.target_type == "Asset"
    assert decision.target_id == f"asset:eip155:8453:erc20:{address}"
    assert decision.reason_codes == ["CHAIN_ADDRESS_EXACT"]


def test_token_intent_resolver_keeps_low_quality_symbol_candidates_ambiguous():
    registry = FakeRegistry(
        symbol_assets={
            "SATO": [
                {
                    "asset_id": "asset:eip155:1:erc20:0x1111111111111111111111111111111111111111",
                    "observed_at_ms": 1_778_145_000_000,
                    "market_cap_usd": 100_000,
                    "liquidity_usd": 90_000,
                    "holders": 500,
                },
                {
                    "asset_id": "asset:eip155:8453:erc20:0x2222222222222222222222222222222222222222",
                    "observed_at_ms": 1_778_145_000_000,
                    "market_cap_usd": 90_000,
                    "liquidity_usd": 80_000,
                    "holders": 450,
                },
            ]
        }
    )
    evidence = _evidence("$SATO")
    intent = build_token_intents(event_id="event-sato", evidence=evidence, created_at_ms=1_778_145_100_000)[0]

    decision = TokenIntentResolver(registry=registry, resolutions=FakeResolutions()).resolve(
        intent,
        evidence,
        decision_time_ms=1_778_145_100_000,
    )

    assert decision.resolution_status == "AMBIGUOUS"
    assert decision.reason_codes == ["NO_MARKET_DOMINANT_CHAIN_ASSET"]
    assert len(decision.candidate_ids) == 2
    assert "symbol:SATO" in decision.lookup_keys


def test_token_intent_resolver_resolves_retained_symbol_candidates_without_freshness_gate():
    registry = FakeRegistry(
        symbol_assets={
            "SLOP": [
                {
                    "asset_id": "asset:solana:token:slop",
                    "observed_at_ms": 1_778_145_000_000,
                    "market_cap_usd": 10_000_000,
                    "liquidity_usd": 900_000,
                    "holders": 4_000,
                }
            ]
        }
    )
    evidence = _evidence("$SLOP")
    intent = build_token_intents(event_id="event-slop", evidence=evidence, created_at_ms=1_778_145_100_000)[0]

    decision = TokenIntentResolver(registry=registry, resolutions=FakeResolutions()).resolve(
        intent,
        evidence,
        decision_time_ms=1_778_145_000_000 + 25 * 60_000,
    )

    assert decision.resolution_status == "UNIQUE_BY_CONTEXT"
    assert decision.target_id == "asset:solana:token:slop"
    assert decision.reason_codes == ["SINGLE_ACTIVE_CHAIN_ASSET"]
    assert decision.candidate_ids == ["asset:solana:token:slop"]


def _evidence(text: str):
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])
    return build_token_evidence(event_id="event-pepe", entities=entities, token_snapshot=None, created_at_ms=1)


class FakeRegistry:
    def __init__(self, *, cex_tokens=None, symbol_assets=None, address_assets=None):
        self.cex_tokens = cex_tokens or {}
        self.symbol_assets = symbol_assets or {}
        self.address_assets = address_assets or {}

    def find_cex_token(self, symbol):
        return self.cex_tokens.get(str(symbol).upper())

    def find_preferred_cex_pricefeed(self, base_symbol):
        return None

    def find_assets_by_symbol_with_latest_observation(self, symbol):
        return list(self.symbol_assets.get(str(symbol).upper(), []))

    def find_assets_by_address(self, *, chain_id=None, address):
        key = (chain_id, str(address).lower())
        if chain_id:
            row = self.address_assets.get(key)
            return [row] if row else []
        return [
            row
            for (_chain_id, stored_address), row in self.address_assets.items()
            if stored_address == str(address).lower()
        ]


class FakeResolutions:
    def __init__(self):
        self.items = []

    def insert_resolution(self, decision, *, commit=True):
        self.items.append(decision)
        return {}
