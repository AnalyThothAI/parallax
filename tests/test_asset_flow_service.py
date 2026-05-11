from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService


def test_asset_flow_has_resolved_and_attention_lanes_from_token_radar_rows():
    service = asset_flow_service(
        rows=[
            radar_row(lane="resolved", symbol="BTC", asset_id="asset:cex:BTC"),
            radar_row(
                lane="attention",
                symbol="MIRROR",
                intent_id="intent:mirror",
                asset_id=None,
                identity_status="NIL",
                resolution_status="NIL",
                decision="discard",
            ),
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["target"]["symbol"] == "BTC"
    assert result["attention"][0]["intent"]["display_symbol"] == "MIRROR"
    assert result["attention"][0]["target"]["symbol"] == "MIRROR"
    assert result["projection"]["version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert result["projection"]["source"] == "token_radar_rows"
    assert service.token_radar.calls[0]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION


def test_asset_flow_marks_ready_empty_projection_without_missing_rows():
    service = asset_flow_service(rows=[])

    result = service.asset_flow(window="5m", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "fresh"
    assert result["projection"]["computed_at_ms"] is None
    assert result["projection"]["market_hydration"]["status"] == "missing"


def test_asset_flow_marks_projection_pending_when_coverage_is_missing():
    current_market = FakeCurrentMarket()
    service = asset_flow_service(rows=[], coverage={}, current_market=current_market)

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "pending"
    assert result["projection"]["reason"] == "projection_window_missing"
    assert result["projection"]["computed_at_ms"] is None
    assert current_market.calls == []


def test_asset_flow_treats_ready_zero_row_coverage_as_fresh_empty_projection():
    service = asset_flow_service(
        rows=[],
        coverage={
            ("5m", "matched"): {
                "status": "ready",
                "reason": None,
                "row_count": 0,
                "source_rows": 12,
                "computed_at_ms": 1_700_000_050_000,
            }
        },
    )

    result = service.asset_flow(window="5m", limit=20, scope="matched", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "fresh"
    assert result["projection"]["reason"] is None
    assert result["projection"]["row_count"] == 0
    assert result["projection"]["source_rows"] == 12
    assert result["projection"]["computed_at_ms"] == 1_700_000_050_000


def test_asset_flow_marks_failed_coverage_as_pending_with_reason():
    service = asset_flow_service(
        rows=[],
        coverage={
            ("4h", "all"): {
                "status": "failed",
                "reason": "query_timeout",
                "row_count": 0,
                "source_rows": 0,
                "computed_at_ms": 1_700_000_040_000,
                "error": "statement timeout",
            }
        },
    )

    result = service.asset_flow(window="4h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["projection"]["status"] == "pending"
    assert result["projection"]["reason"] == "projection_window_failed"
    assert result["projection"]["error"] == "statement timeout"


def test_asset_flow_exposes_projection_market_hydration_summary():
    service = asset_flow_service(
        rows=[
            radar_row(lane="resolved", symbol="FRESH", asset_id="asset:dex:fresh"),
            radar_row(lane="resolved", symbol="STALE", asset_id="asset:dex:stale"),
            radar_row(lane="resolved", symbol="MISS", asset_id="asset:dex:missing"),
        ],
        current_market=FakeCurrentMarket(
            {
                ("CexToken", "asset:dex:fresh"): current_market_snapshot(
                    target_type="CexToken",
                    target_id="asset:dex:fresh",
                    market_status="fresh",
                ),
                ("CexToken", "asset:dex:stale"): current_market_snapshot(
                    target_type="CexToken",
                    target_id="asset:dex:stale",
                    market_status="stale",
                ),
            }
        ),
    )

    result = service.asset_flow(window="5m", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["projection"]["market_hydration"] == {
        "status": "partial",
        "fresh": 1,
        "stale": 1,
        "missing": 1,
        "pending": 0,
        "total": 3,
    }


def test_asset_flow_exposes_source_event_ids_for_evidence_counting():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol="BTC",
                asset_id="asset:cex:BTC",
                source_event_ids=["event-a", "event-b", "event-c"],
            )
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["source_event_ids"] == ["event-a", "event-b", "event-c"]


def test_unresolved_attention_uses_snapshot_composite_without_score_fallback():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="attention",
                symbol="VERSA",
                asset_id=None,
                identity_status="NIL",
                resolution_status="NIL",
                rank_score=12,
                decision="discard",
            )
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    versa = result["attention"][0]
    assert versa["resolution"]["status"] == "NIL"
    assert versa["score"] == {
        "family_scores": {
            "identity": 80,
            "social_attention": 80,
            "social_quality": 80,
            "social_semantics": 80,
            "market_quality": 80,
            "timing": 80,
        },
        "rank_score": 12,
        "recommended_decision": "discard",
    }
    assert versa["decision"] == "discard"
    assert versa["score"] == versa["factor_snapshot"]["composite"]


def test_btc_cex_row_does_not_require_chain_address():
    service = asset_flow_service(
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
        ],
        current_market=FakeCurrentMarket(
            {
                ("CexToken", "asset:cex:BTC"): current_market_snapshot(
                    target_type="CexToken",
                    target_id="asset:cex:BTC",
                    fields={"price_usd": {"value": 70_000, "status": "fresh"}},
                )
            }
        ),
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    btc = result["targets"][0]
    assert btc["target"]["target_type"] == "CexToken"
    assert btc["target"]["target_market_type"] == "cex"
    assert btc["target"]["chain"] is None
    assert btc["target"]["address"] is None
    assert btc["factor_snapshot"]["families"]["market_quality"]["facts"]["native_market_id"] == "BTC-USDT"
    assert btc["current_market"]["fields"]["price_usd"]["value"] == 70_000


def test_asset_flow_exposes_current_market_from_asset_market_read_model():
    current_market = FakeCurrentMarket(
        {
            ("CexToken", "cex_token:BTC"): current_market_snapshot(
                target_type="CexToken",
                target_id="cex_token:BTC",
                market_status="fresh",
                fields={
                    "price_usd": {"value": 70_000, "status": "fresh", "age_ms": 15_000},
                    "volume_24h_usd": {"value": 123_000_000, "status": "fresh"},
                    "open_interest_usd": {"value": 45_000_000, "status": "fresh"},
                },
            )
        }
    )
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol="BTC",
                asset_id="cex_token:BTC",
                asset_type="cex_asset",
            )
        ],
        current_market=current_market,
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    row = result["targets"][0]
    assert row["current_market"]["market_status"] == "fresh"
    assert row["current_market"]["fields"]["price_usd"]["value"] == 70_000
    assert row["current_market"]["fields"]["volume_24h_usd"]["value"] == 123_000_000
    assert "price" not in row
    assert "market" not in row


def test_asset_flow_ignores_legacy_market_and_price_payloads():
    row = radar_row(lane="resolved", symbol="BTC", asset_id="asset:cex:BTC")
    row["price_json"] = {"market_status": "legacy_price_ready"}
    row["market_json"] = {"market_status": "legacy_market_ready"}
    service = asset_flow_service(rows=[row])

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["current_market"]["market_status"] == "missing"
    assert "price" not in result["targets"][0]
    assert "market" not in result["targets"][0]


def test_asset_flow_does_not_fallback_to_legacy_payloads_when_snapshot_missing():
    row = radar_row(lane="resolved", symbol="BTC", asset_id="asset:cex:BTC")
    row.pop("factor_snapshot_json")
    row["price_json"] = {"market_status": "legacy_price_ready"}
    row["score_json"] = {"heat": {"score": 99}}
    service = asset_flow_service(rows=[row])

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["current_market"] == {
        "target_type": None,
        "target_id": None,
        "market_status": "missing",
        "fields": {},
    }
    assert "price" not in result["targets"][0]
    assert "market" not in result["targets"][0]
    assert result["targets"][0]["score"] == {}


def test_asset_flow_keeps_diagnosable_missing_market_status():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol="TEST",
                asset_id="asset:dex:base:test",
                asset_type="dex_asset",
                data_health={
                    "factor_snapshot": "ready",
                    "identity": "ready",
                    "market": "partial",
                },
            )
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    row = result["targets"][0]
    assert row["current_market"] == {
        "target_type": "Asset",
        "target_id": "asset:dex:base:test",
        "market_status": "missing",
        "fields": {},
    }
    assert row["data_health"]["market"] == "partial"


def test_asset_flow_uses_backend_symbol_instead_of_contract_address_display():
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    service = asset_flow_service(
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

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["target"]["symbol"] == "USDUC"
    assert result["targets"][0]["target"]["chain"] == "solana"


def test_asset_flow_does_not_invent_symbol_when_backend_omits_it():
    address = "CTc4y2eHbTApoCAo2rNJFHkvPFHMnNygqEcBMyNcpump"
    service = asset_flow_service(
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

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["intent"]["display_symbol"] == "CTc4y2eH"
    assert result["targets"][0]["target"]["symbol"] is None


def test_asset_flow_exposes_market_timing_inside_factor_snapshot():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol="BTC",
                asset_id="asset:cex:BTC",
                market={
                    "market_status": "ready",
                    "volume_24h_usd": 50_000_000.0,
                },
                timing={
                    "social_signal_start_ms": 1_700_000_000_000,
                    "price_change_since_social_pct": 1 / 9,
                    "price_change_before_social_pct": 0.2,
                },
            )
        ],
        current_market=FakeCurrentMarket(
            {
                ("CexToken", "asset:cex:BTC"): current_market_snapshot(
                    target_type="CexToken",
                    target_id="asset:cex:BTC",
                    fields={"volume_24h_usd": {"value": 50_000_000.0, "status": "fresh"}},
                )
            }
        ),
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    timing = result["targets"][0]["factor_snapshot"]["families"]["timing"]["facts"]
    assert timing["price_change_since_social_pct"] == pytest.approx(1 / 9)
    assert timing["price_change_before_social_pct"] == pytest.approx(0.2)
    assert timing["social_signal_start_ms"] == 1_700_000_000_000
    market_facts = result["targets"][0]["factor_snapshot"]["families"]["market_quality"]["facts"]
    assert market_facts["volume_24h_usd"] == 50_000_000.0
    assert result["targets"][0]["current_market"]["fields"]["volume_24h_usd"]["value"] == 50_000_000.0


class FakeTokenRadar:
    def __init__(self, *, rows, coverage=None):
        self.rows = rows
        self.coverage = coverage
        self.calls = []

    def latest_rows(self, *, window, scope, limit, projection_version):
        self.calls.append({"window": window, "scope": scope, "limit": limit, "projection_version": projection_version})
        return self.rows[:limit]

    def latest_coverage(self, *, projection_version, windows, scopes):
        if self.coverage is None:
            return {
                (window, scope): {
                    "status": "ready",
                    "reason": None,
                    "row_count": len(self.rows),
                    "source_rows": len(self.rows),
                    "computed_at_ms": max(
                        (int(row.get("computed_at_ms") or 0) for row in self.rows),
                        default=0,
                    )
                    or None,
                }
                for window in windows
                for scope in scopes
            }
        return dict(self.coverage)


class FakeCurrentMarket:
    def __init__(self, snapshots: dict[tuple[str, str], dict] | None = None):
        self.snapshots = snapshots or {}
        self.calls = []

    def current_for_subjects(self, subjects, *, now_ms):
        self.calls.append({"subjects": list(subjects), "now_ms": now_ms})
        return {
            key: self.snapshots[key]
            for subject in subjects
            if (key := (str(subject.get("target_type")), str(subject.get("target_id")))) in self.snapshots
        }


def asset_flow_service(
    *,
    rows: list[dict],
    coverage: dict[tuple[str, str], dict] | None = None,
    current_market: FakeCurrentMarket | None = None,
) -> AssetFlowService:
    return AssetFlowService(
        token_radar=FakeTokenRadar(rows=rows, coverage=coverage),
        current_market=current_market or FakeCurrentMarket(),
    )


def current_market_snapshot(
    *,
    target_type: str,
    target_id: str,
    market_status: str = "fresh",
    fields: dict | None = None,
) -> dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "market_status": market_status,
        "fields": fields or {"price_usd": {"value": 1.0, "status": market_status}},
    }


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
    attention: dict | None = None,
    timing: dict | None = None,
    rank_score: int = 55,
    decision: str = "watch",
    data_health: dict | None = None,
    source_event_ids: list[str] | None = None,
):
    resolved_intent_id = intent_id or f"intent:{(display_symbol or symbol or asset_id or 'unknown').lower()}"
    target_type = "CexToken" if asset_type == "cex_asset" else "Asset" if asset_id else None
    target_market_type = "cex" if target_type == "CexToken" else "dex"
    target_chain = (venue or {}).get("chain") if asset_type != "cex_asset" else None
    target_address = (venue or {}).get("address") if asset_type != "cex_asset" else None
    subject_symbol = symbol if asset_id else symbol if symbol is not None else display_symbol
    event_ids = source_event_ids or [f"event:{resolved_intent_id}"]
    factor_snapshot = factor_snapshot_json(
        target_type=target_type,
        target_id=asset_id,
        symbol=subject_symbol,
        chain=target_chain,
        address=target_address,
        target_market_type=target_market_type,
        attention=attention,
        market=market,
        timing=timing,
        native_market_id=(venue or {}).get("inst_id") if asset_type == "cex_asset" else None,
        source_event_ids=event_ids,
        rank_score=rank_score,
        decision=decision,
    )
    return {
        "row_id": f"row:{resolved_intent_id}",
        "lane": lane,
        "rank": 1,
        "intent_id": resolved_intent_id,
        "event_id": f"event:{resolved_intent_id}",
        "target_type": target_type,
        "target_id": asset_id,
        "pricefeed_id": None,
        "intent_json": {
            "intent_id": resolved_intent_id,
            "display_symbol": display_symbol if display_symbol is not None else symbol,
            "display_name": None,
            "evidence": [],
        },
        "asset_json": {},
        "target_json": {},
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
        "factor_snapshot_json": factor_snapshot,
        "factor_version": "token_factor_snapshot_v1",
        "attention_json": {},
        "resolution_json": {
            "status": resolution_status,
            "resolution_status": resolution_status,
            "target_type": target_type,
            "target_id": asset_id,
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
        },
        "market_json": {},
        "price_json": {},
        "score_json": {},
        "decision": decision,
        "data_health_json": data_health
        if data_health is not None
        else {
            "factor_snapshot": "ready",
            "identity": "ready" if identity_status == "EXACT" else "partial",
            "market": "partial",
        },
        "source_event_ids_json": event_ids,
        "source_max_received_at_ms": 1_700_000_000_000,
    }


def factor_snapshot_json(
    *,
    target_type,
    target_id,
    symbol,
    chain,
    address,
    target_market_type,
    attention,
    market,
    timing,
    native_market_id,
    source_event_ids,
    rank_score,
    decision,
):
    families = {
        "identity": family(
            "identity",
            {
                "target_type": target_type,
                "target_id": target_id,
                "symbol": symbol,
                "chain": chain,
                "address": address,
            },
        ),
        "social_attention": family(
            "social_attention",
            {
                "mentions_5m": 1,
                "mentions_1h": 1,
                "mentions_4h": 1,
                "mentions_24h": 1,
                "unique_authors": 1,
                "watched_mentions": 1,
                **(attention or {}),
            },
        ),
        "social_quality": family("social_quality", {"duplicate_text_share": 0.0, "mentions": 1}),
        "social_semantics": family("social_semantics", {"direction_counts": {}}),
        "market_quality": family(
            "market_quality",
            {
                "target_market_type": target_market_type,
                "market_status": "missing",
                "holders": None,
                "liquidity_usd": None,
                "market_cap_usd": None,
                "volume_24h_usd": None,
                "open_interest_usd": None,
                "native_market_id": native_market_id,
                **(market or {}),
            },
        ),
        "timing": family(
            "timing",
            {
                "price_change_before_social_pct": None,
                "price_change_since_social_pct": None,
                "social_signal_start_ms": 1_700_000_000_000,
                **(timing or {}),
            },
        ),
    }
    return {
        "schema_version": "token_factor_snapshot_v1",
        "subject": {
            "target_type": target_type,
            "target_id": target_id,
            "symbol": symbol,
            "chain": chain,
            "address": address,
            "target_market_type": target_market_type,
        },
        "families": families,
        "hard_gates": {
            "eligible_for_high_alert": decision == "high_alert",
            "blocked_reasons": [] if decision != "discard" else ["identity_unresolved"] if not target_id else [],
            "gates": [],
        },
        "composite": {
            "family_scores": {name: item["score"] for name, item in families.items()},
            "rank_score": rank_score,
            "recommended_decision": decision,
        },
        "provenance": {
            "source_event_ids": source_event_ids,
            "computed_at_ms": 1_700_000_060_000,
        },
    }


def family(name: str, facts: dict):
    return {
        "family": name,
        "score": 80,
        "data_health": "ready",
        "facts": facts,
        "factors": {"fixture": {"score": 80, "data_health": "ready"}},
    }
