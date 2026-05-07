from __future__ import annotations

import pytest

from gmgn_twitter_intel.retrieval.asset_flow_service import AssetFlowService


def test_asset_flow_has_resolved_and_attention_lanes_from_token_radar_rows():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(lane="resolved", symbol="BTC", asset_id="asset:cex:BTC"),
                radar_row(
                    lane="attention",
                    symbol="MIRROR",
                    intent_id="intent:mirror",
                    asset_id=None,
                    identity_status="NIL",
                    resolution_status="NIL",
                    decision="investigate",
                ),
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["target"]["symbol"] == "BTC"
    assert result["attention"][0]["intent"]["display_symbol"] == "MIRROR"
    assert result["projection"]["version"] == "token-radar-v4"
    assert result["projection"]["source"] == "token_radar_rows"


def test_asset_flow_marks_projection_missing_when_no_radar_rows():
    service = AssetFlowService(token_radar=FakeTokenRadar(rows=[]))

    result = service.asset_flow(window="5m", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "missing"
    assert result["projection"]["computed_at_ms"] is None


def test_unresolved_attention_keeps_backend_investigate_decision_even_with_high_heat():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="attention",
                    symbol="VERSA",
                    asset_id=None,
                    identity_status="NIL",
                    resolution_status="NIL",
                    score={"heat": score_block(100), "opportunity": score_block(96)},
                    decision="investigate",
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    versa = result["attention"][0]
    assert versa["resolution"]["status"] == "NIL"
    assert versa["score"]["heat"]["score"] == 100
    assert versa["score"]["opportunity"]["score"] == 96
    assert versa["decision"] == "investigate"


def test_btc_cex_row_does_not_require_chain_address():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol="BTC",
                    asset_id="asset:cex:BTC",
                    asset_type="cex_asset",
                    venue={
                        "venue_id": "venue:cex:okx:SPOT:BTC-USDT",
                        "venue_type": "cex",
                        "exchange": "okx",
                        "inst_id": "BTC-USDT",
                        "chain": None,
                        "address": None,
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    btc = result["targets"][0]
    assert btc["target"]["target_type"] == "CexToken"
    assert btc["target"]["native_market_id"] == "BTC-USDT"


def test_asset_flow_exposes_market_snapshot_health_from_read_model():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol="BTC",
                    asset_id="asset:cex:BTC",
                    market={
                        "market_status": "ready",
                        "market_observation_status": "ready",
                        "provider": "okx_cex",
                        "price_usd": 69_000.0,
                        "volume_24h_usd": 123_000_000.0,
                        "snapshot_age_ms": 60_000,
                        "snapshot_observed_at_ms": 1_700_000_000_000,
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    price = result["targets"][0]["price"]
    assert price["market_status"] == "ready"
    assert price["market_observation_status"] == "ready"
    assert price["provider"] == "okx_cex"
    assert price["price_usd"] == 69_000.0
    assert price["snapshot_age_ms"] == 60_000


def test_asset_flow_keeps_diagnosable_missing_market_status():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol="TEST",
                    asset_id="asset:dex:base:test",
                    asset_type="dex_asset",
                    market={
                        "market_status": "missing",
                        "market_observation_status": "provider_not_configured",
                        "price_change_status": "missing_market",
                        "provider": "okx_dex",
                        "price_usd": None,
                        "snapshot_observed_at_ms": None,
                    },
                    data_health={
                        "identity": "EXACT",
                        "market": "provider_not_configured",
                        "coverage": "public_stream",
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    row = result["targets"][0]
    assert row["price"]["market_status"] == "missing"
    assert row["price"]["market_observation_status"] == "provider_not_configured"
    assert row["price"]["snapshot_observed_at_ms"] is None
    assert row["data_health"]["market"] == "provider_not_configured"


def test_asset_flow_uses_backend_symbol_instead_of_contract_address_display():
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol="USDUC",
                    asset_id=f"asset:dex:solana:{address.lower()}",
                    asset_type="dex_asset",
                    venue={
                        "venue_id": f"venue:dex:solana:{address.lower()}",
                        "venue_type": "dex",
                        "exchange": None,
                        "chain": "solana",
                        "address": address,
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["target"]["symbol"] == "USDUC"


def test_asset_flow_does_not_invent_symbol_when_backend_omits_it():
    address = "CTc4y2eHbTApoCAo2rNJFHkvPFHMnNygqEcBMyNcpump"
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol=None,
                    display_symbol="CTc4y2eH",
                    asset_id=f"asset:dex:solana:{address.lower()}",
                    asset_type="dex_asset",
                    venue={
                        "venue_id": f"venue:dex:solana:{address.lower()}",
                        "venue_type": "dex",
                        "exchange": None,
                        "chain": "solana",
                        "address": address,
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["intent"]["display_symbol"] == "CTc4y2eH"
    assert result["targets"][0]["target"]["symbol"] is None


def test_asset_flow_exposes_market_timing_changes_from_projection():
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[
                radar_row(
                    lane="resolved",
                    symbol="BTC",
                    asset_id="asset:cex:BTC",
                    market={
                        "market_status": "ready",
                        "market_observation_status": "ready",
                        "price_change_status": "ready",
                        "provider": "okx_cex",
                        "price_usd": 100.0,
                        "price_change_5m_pct": 0.25,
                        "price_change_1h_pct": 1.0,
                        "price_change_24h_pct": 1.5,
                        "price_at_social_start": 90.0,
                        "price_change_since_social_pct": 1 / 9,
                        "price_change_before_social_pct": 0.2,
                    },
                )
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    price = result["targets"][0]["price"]
    assert price["price_change_status"] == "ready"
    assert price["price_change_5m_pct"] == pytest.approx(0.25)
    assert price["price_change_1h_pct"] == pytest.approx(1.0)
    assert price["price_change_24h_pct"] == pytest.approx(1.5)
    assert price["price_at_social_start"] == 90.0
    assert price["price_change_since_social_pct"] == pytest.approx(1 / 9)
    assert price["price_change_before_social_pct"] == pytest.approx(0.2)


class FakeTokenRadar:
    def __init__(self, *, rows):
        self.rows = rows
        self.calls = []

    def latest_rows(self, *, window, scope, limit):
        self.calls.append({"window": window, "scope": scope, "limit": limit})
        return self.rows[:limit]


def radar_row(
    *,
    lane,
    symbol,
    asset_id,
    intent_id: str | None = None,
    display_symbol: str | None = None,
    asset_type: str = "cex_asset",
    identity_status: str = "EXACT",
    resolution_status: str = "EXACT",
    venue: dict | None = None,
    market: dict | None = None,
    score: dict | None = None,
    decision: str = "watch",
    data_health: dict | None = None,
):
    resolved_intent_id = intent_id or f"intent:{(display_symbol or symbol or asset_id or 'unknown').lower()}"
    return {
        "row_id": f"row:{resolved_intent_id}",
        "lane": lane,
        "rank": 1,
        "intent_id": resolved_intent_id,
        "event_id": f"event:{resolved_intent_id}",
        "target_type": "CexToken" if asset_type == "cex_asset" else "Asset" if asset_id else None,
        "target_id": asset_id,
        "pricefeed_id": None,
        "intent_json": {
            "intent_id": resolved_intent_id,
            "display_symbol": display_symbol if display_symbol is not None else symbol,
            "display_name": None,
            "evidence": [],
        },
        "asset_json": {},
        "target_json": {
            "target_type": "CexToken" if asset_type == "cex_asset" else "Asset" if asset_id else None,
            "target_id": asset_id,
            "symbol": symbol,
            "status": "canonical" if identity_status == "EXACT" else None,
            "native_market_id": (venue or {}).get("inst_id") if asset_type == "cex_asset" else None,
            "chain_id": (venue or {}).get("chain") if asset_type != "cex_asset" else None,
            "address": (venue or {}).get("address") if asset_type != "cex_asset" else None,
        },
        "primary_venue_json": venue
        if venue is not None
        else {
            "venue_id": "venue:cex:okx:SPOT:BTC-USDT",
            "venue_type": "cex",
            "exchange": "okx",
            "chain": None,
            "address": None,
            "inst_id": f"{symbol or 'BTC'}-USDT",
        },
        "attention_json": {
            "mentions_5m": 1,
            "mentions_1h": 1,
            "mentions_window": 1,
            "unique_authors": 1,
            "watched_mentions": 1,
            "latest_seen_ms": 1_700_000_000_000,
        },
        "resolution_json": {
            "status": resolution_status,
            "resolution_status": resolution_status,
            "target_type": "CexToken" if asset_type == "cex_asset" else "Asset" if asset_id else None,
            "target_id": asset_id,
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
        },
        "price_json": market
        if market is not None
        else {
            "market_status": "pending_refresh",
            "market_observation_status": "pending_refresh",
            "price_change_status": "pending_refresh",
            "provider": None,
            "price_usd": None,
        },
        "score_json": score
        if score is not None
        else {
            "heat": score_block(50),
            "quality": score_block(70),
            "propagation": score_block(50),
            "price_health": score_block(60),
            "timing": score_block(50),
            "opportunity": score_block(55),
        },
        "decision": decision,
        "data_health_json": data_health
        if data_health is not None
        else {"identity": identity_status, "market": "pending_refresh", "coverage": "public_stream"},
        "source_event_ids_json": [f"event:{resolved_intent_id}"],
        "source_max_received_at_ms": 1_700_000_000_000,
    }


def score_block(score: int):
    return {
        "score": score,
        "score_version": "token_radar_v4",
        "reasons": [],
        "risks": [],
        "hard_risks": [],
        "contributions": [],
        "risk_caps": [],
    }
