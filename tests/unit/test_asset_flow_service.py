from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService


def _legacy_market_key(*parts: str) -> str:
    return "_".join(parts)


def test_asset_flow_returns_market_context_and_no_legacy_market_fields():
    service = asset_flow_service(
        rows=[
            radar_row(lane="resolved", symbol="BTC", target_type="CexToken", target_id="cex_token:BTC"),
            radar_row(lane="attention", symbol="MIRROR", target_type=None, target_id=None, decision="discard"),
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    btc = result["targets"][0]
    assert btc["target"]["symbol"] == "BTC"
    assert btc["radar"] == {
        "lane": "resolved",
        "rank": 1,
        "listed_at_ms": 1_699_999_880_000,
        "computed_at_ms": 1_700_000_060_000,
        "source_max_received_at_ms": 1_700_000_000_000,
    }
    assert btc["market"]["event_anchor"]["price_usd"] == 70_000.0
    assert btc["market"]["decision_latest"]["price_usd"] == 70_000.0
    assert btc["market"]["readiness"]["anchor_status"] == "ready"
    assert _legacy_market_key("anchor", "price") not in btc
    assert "live_market" not in btc
    assert "current_market" not in btc
    assert result["attention"] == []
    assert result["projection"]["version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert result["projection"]["source"] == "token_radar_rows"
    assert result["projection"]["anchor_coverage"] == {"status": "ready", "ready": 1, "missing": 0, "total": 1}
    assert result["projection"]["unresolved"] == {
        "identity_missing_count": 1,
        "nil_count": 1,
        "ambiguous_count": 0,
        "sample_symbols": ["MIRROR"],
    }


def test_asset_flow_marks_ready_empty_projection_without_missing_rows():
    service = asset_flow_service(rows=[])

    result = service.asset_flow(window="5m", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "fresh"
    assert result["projection"]["computed_at_ms"] is None
    assert result["projection"]["anchor_coverage"] == {"status": "missing", "ready": 0, "missing": 0, "total": 0}


def test_asset_flow_marks_projection_pending_when_coverage_is_missing():
    service = asset_flow_service(rows=[], coverage={})

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["status"] == "pending"
    assert result["projection"]["reason"] == "projection_window_missing"
    assert result["projection"]["anchor_coverage"] == {"status": "pending", "ready": 0, "missing": 0, "total": 0}


def test_asset_flow_does_not_fallback_to_legacy_payloads_when_snapshot_missing():
    row = radar_row(lane="resolved", symbol="BTC", target_type="CexToken", target_id="cex_token:BTC")
    row.pop("factor_snapshot_json")
    row["price_json"] = {"market_status": "legacy_price_ready"}
    row["market_json"] = {"market_status": "legacy_market_ready"}
    row["score_json"] = {"heat": {"score": 99}}
    service = asset_flow_service(rows=[row])

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"] == []
    assert result["attention"] == []
    assert result["projection"]["anchor_coverage"] == {"status": "missing", "ready": 0, "missing": 0, "total": 0}


def test_asset_flow_uses_backend_symbol_without_inventing_contract_label():
    service = asset_flow_service(
        rows=[
            radar_row(
                lane="resolved",
                symbol=None,
                display_symbol="CTc4y2eH",
                target_type="Asset",
                target_id="asset:dex:solana:ctc4",
                chain="solana",
                address="CTc4y2eHbTApoCAo2rNJFHkvPFHMnNygqEcBMyNcpump",
            )
        ]
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["intent"]["display_symbol"] == "CTc4y2eH"
    assert result["targets"][0]["target"]["symbol"] is None
    assert result["targets"][0]["target"]["chain"] == "solana"


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
                    "computed_at_ms": max((int(row.get("computed_at_ms") or 0) for row in self.rows), default=0)
                    or None,
                }
                for window in windows
                for scope in scopes
            }
        return dict(self.coverage)


def asset_flow_service(
    *,
    rows: list[dict],
    coverage: dict[tuple[str, str], dict] | None = None,
) -> AssetFlowService:
    return AssetFlowService(token_radar=FakeTokenRadar(rows=rows, coverage=coverage), profiles=FakeProfiles())


class FakeProfiles:
    def profiles_for_targets(self, targets):
        return {}


def radar_row(
    *,
    lane: str,
    symbol: str | None,
    target_type: str | None,
    target_id: str | None,
    decision: str = "watch",
    display_symbol: str | None = None,
    chain: str | None = None,
    address: str | None = None,
) -> dict:
    event_ids = [f"event:{display_symbol or symbol or target_id or 'unknown'}"]
    snapshot = factor_snapshot_json(
        target_type=target_type,
        target_id=target_id,
        symbol=symbol,
        chain=chain,
        address=address,
        target_market_type="cex" if target_type == "CexToken" else "dex",
        source_event_ids=event_ids,
        decision=decision,
    )
    return {
        "row_id": f"row:{target_id or display_symbol or symbol}",
        "lane": lane,
        "rank": 1,
        "intent_id": f"intent:{display_symbol or symbol or target_id or 'unknown'}",
        "event_id": event_ids[0],
        "target_type": target_type,
        "target_id": target_id,
        "pricefeed_id": None,
        "intent_json": {
            "intent_id": f"intent:{display_symbol or symbol or target_id or 'unknown'}",
            "display_symbol": display_symbol if display_symbol is not None else symbol,
            "display_name": None,
            "evidence": [],
        },
        "target_json": {},
        "factor_snapshot_json": snapshot,
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "resolution_json": {
            "status": "EXACT" if target_id else "NIL",
            "target_type": target_type,
            "target_id": target_id,
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
        },
        "market_json": {},
        "price_json": {},
        "score_json": {},
        "decision": decision,
        "data_health_json": {
            "factor_snapshot": "ready",
            "identity": "ready" if target_id else "partial",
            "market": "ready" if target_id else "missing",
        },
        "source_event_ids_json": event_ids,
        "source_max_received_at_ms": 1_700_000_000_000,
        "computed_at_ms": 1_700_000_060_000,
        "listed_at_ms": 1_699_999_880_000,
    }


def factor_snapshot_json(
    *,
    target_type,
    target_id,
    symbol,
    chain,
    address,
    target_market_type,
    source_event_ids,
    decision,
):
    ready_anchor = target_id is not None
    observation = {
        "target_type": target_type,
        "target_id": target_id,
        "source": "event_anchor",
        "provider": "okx" if ready_anchor else None,
        "pricefeed_id": None,
        "price_usd": 70_000.0 if ready_anchor else None,
        "price_quote": None,
        "quote_symbol": "USD" if ready_anchor else None,
        "price_basis": "usd" if ready_anchor else None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "holders": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "observed_at_ms": 1_700_000_000_500 if ready_anchor else None,
        "received_at_ms": 1_700_000_000_500 if ready_anchor else None,
        "raw_payload_hash": None,
    }
    market = {
        "event_anchor": observation if ready_anchor else None,
        "decision_latest": {**observation, "source": "decision_latest"} if ready_anchor else None,
        "readiness": {
            "anchor_status": "ready" if ready_anchor else "missing",
            "latest_status": "live" if ready_anchor else "missing",
            "dex_floor_status": "ready" if target_type != "Asset" else "missing_fields",
            "missing_fields": [] if target_type != "Asset" else ["holders", "liquidity_usd", "market_cap_usd"],
            "stale_fields": [],
        },
    }
    families = {
        "social_heat": family("social_heat", {"mentions_1h": 1}, weight=0.35),
        "social_propagation": family("social_propagation", {"mentions": 1}, weight=0.30),
        "semantic_catalyst": family("semantic_catalyst", {"direction_counts": {}}, weight=0.25),
        "timing_risk": family(
            "timing_risk",
            {"price_change_status": "live_not_persisted", "social_signal_start_ms": 1_700_000_000_000},
            weight=0.0,
        ),
    }
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {
            "target_type": target_type,
            "target_id": target_id,
            "symbol": symbol,
            "chain": chain,
            "address": address,
            "target_market_type": target_market_type,
        },
        "market": market,
        "families": families,
        "gates": {
            "eligible_for_high_alert": decision == "high_alert",
            "max_decision": "high_alert" if decision == "high_alert" else "watch",
            "blocked_reasons": [] if decision != "discard" else ["identity_unresolved"] if not target_id else [],
            "risk_reasons": [],
        },
        "data_health": {
            "identity": "ready" if target_id else "missing",
            "market": "ready" if ready_anchor else "missing",
            "social": "ready",
            "alpha": "ready",
        },
        "normalization": {"status": "ready", "cohort": {}, "factor_ranks": {}, "alpha_rank": None},
        "composite": {
            "family_scores": {name: item["score"] for name, item in families.items()},
            "rank_score": 55,
            "recommended_decision": decision,
        },
        "provenance": {"source_event_ids": source_event_ids, "computed_at_ms": 1_700_000_060_000},
    }


def family(name: str, facts: dict, *, weight: float):
    return {
        "raw_score": 80,
        "weight": weight,
        "score": 80,
        "data_health": "ready",
        "facts": facts,
        "factors": {"fixture": {"family": name, "score": 80, "data_health": "ready"}},
    }
