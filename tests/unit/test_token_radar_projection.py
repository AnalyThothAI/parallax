from __future__ import annotations

import pytest

import gmgn_twitter_intel.domains.token_intel.services.token_radar_projection as token_radar_projection_module
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import (
    PROJECTION_VERSION,
    WINDOW_MS,
    TokenRadarProjection,
    _analysis_since_ms,
    _display_symbol,
    _market_context,
    _project_group,
    _rank_key,
)


def test_token_radar_row_id_is_unique_per_window_and_scope():
    source_row = {
        "event_id": "event-1",
        "intent_id": "intent-1",
        "received_at_ms": 1_777_800_000_000,
        "author_handle": "toly",
        "is_watched": True,
        "resolution_status": "NIL",
        "target_type": None,
        "target_id": None,
        "pricefeed_id": None,
        "display_symbol": "VERSA",
        "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
        "candidate_ids_json": [],
        "lookup_keys_json": ["symbol:VERSA"],
    }

    all_5m = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="all")
    matched_5m = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="matched")
    all_1h = _project_group([source_row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert len({all_5m["row_id"], matched_5m["row_id"], all_1h["row_id"]}) == 3


def test_token_radar_projection_uses_factor_snapshot_contract():
    assert TOKEN_RADAR_PROJECTION_NAME == "token-radar"
    assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v13-social-attention"
    assert TOKEN_RADAR_FACTOR_FAMILIES == (
        "social_heat",
        "social_propagation",
        "semantic_catalyst",
        "timing_risk",
    )
    assert TOKEN_RADAR_SOURCE_TABLE == "token_intent_resolutions+asset_identity_current+anchor_price"
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION


def test_rank_key_breaks_ties_with_factor_snapshot_latest_seen_ms():
    older = ranking_row(target_id="older", latest_seen_ms=1_777_800_000_000)
    newer = ranking_row(target_id="newer", latest_seen_ms=1_777_800_030_000)

    assert [row["target_id"] for row in sorted([older, newer], key=_rank_key)] == ["newer", "older"]


def test_rank_key_does_not_promote_malformed_snapshot_from_row_decision():
    malformed_high_alert = {
        "target_id": "bad",
        "decision": "high_alert",
        "factor_snapshot_json": {},
    }
    valid_discard = ranking_row(
        target_id="valid-discard",
        latest_seen_ms=1_777_800_030_000,
        decision="discard",
        rank_score=1,
    )

    assert [row["target_id"] for row in sorted([malformed_high_alert, valid_discard], key=_rank_key)] == [
        "valid-discard",
        "bad",
    ]


def test_apply_cross_section_rejects_rows_with_malformed_factor_snapshot():
    rows = [
        {
            "target_id": "asset:bad",
            "target_json": {"symbol": "BAD"},
            "factor_snapshot_json": {},
            "_cohort_high_conf_count": 1,
            "_cohort_kol_count": 0,
        }
    ]

    with pytest.raises(ValueError, match="factor_snapshot_json must be a non-empty factor snapshot"):
        TokenRadarProjection._apply_cross_section(rows)


def test_project_group_outputs_factor_snapshot_not_score_contract():
    row = source_row("event-bov", received_at_ms=1_777_800_000_000)
    row["target_type"] = "Asset"
    row["target_id"] = "asset:bsc:0x1"
    row["asset_symbol"] = "BOV"
    row["asset_chain_id"] = "56"
    row["asset_address"] = "0x1"
    row["market_status"] = "fresh"
    row["market_market_cap_usd"] = 12_087.0
    row["market_liquidity_usd"] = 6_553.0
    row["market_holders"] = 46

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    assert projected["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert projected["factor_snapshot_json"]["subject"]["chain"] == "56"
    assert projected["factor_snapshot_json"]["gates"]["eligible_for_high_alert"] is False
    assert projected["factor_version"] == "token_factor_snapshot_v3_social_attention"
    assert projected["score_json"] == {}
    assert projected["attention_json"] == {}
    assert projected["market_json"] == {}
    assert projected["price_json"] == {}


def test_project_group_populates_v3_data_health_from_top_level_snapshot():
    row = source_row("event-cex", received_at_ms=1_777_800_000_000)
    row["target_type"] = "CexToken"
    row["target_id"] = "cex_token:BTC"
    row["cex_base_symbol"] = "BTC"
    row["cex_token_status"] = "canonical"
    row["native_market_id"] = "BTC-USDT"
    row["market_volume_24h_usd"] = 123_000_000.0
    row["market_open_interest_usd"] = 45_000_000.0

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    snapshot = projected["factor_snapshot_json"]
    assert projected["data_health_json"] == {
        "factor_snapshot": "ready",
        "identity": snapshot["data_health"]["identity"],
        "market": snapshot["data_health"]["market"],
        "social": snapshot["data_health"]["social"],
        "alpha": snapshot["data_health"]["alpha"],
    }


def test_project_group_carries_first_seen_global_into_cross_section_cohort():
    row = source_row("event-first-seen", received_at_ms=1_777_800_000_000)
    row["first_seen_global_24h"] = True

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    assert projected["_cohort_high_conf_count"] == 1
    assert projected["_cohort_kol_count"] == 0
    assert projected["_cohort_first_seen_global_24h"] is True
    assert projected["_cohort_public_followup_count"] == 0

    result = TokenRadarProjection._apply_cross_section([projected])

    cohort = result[0]["factor_snapshot_json"]["normalization"]["cohort"]
    assert cohort["in_cohort"] is True
    assert cohort["first_seen_global_24h"] is True
    assert cohort["public_followup_authors"] == 0
    assert "_cohort_first_seen_global_24h" not in result[0]
    assert "_cohort_public_followup_count" not in result[0]


def test_project_group_carries_public_followup_count_as_cohort_metadata_only():
    rows = [
        source_row("event-seed", received_at_ms=1_777_800_000_000, author="alice"),
        source_row("event-bob", received_at_ms=1_777_800_060_000, author="bob"),
        source_row("event-carol", received_at_ms=1_777_800_120_000, author="carol"),
    ]

    projected = _project_group(rows, now_ms=1_777_800_180_000, window="5m", scope="all")

    assert projected is not None
    assert projected["_cohort_public_followup_count"] == 2

    result = TokenRadarProjection._apply_cross_section([projected])

    cohort = result[0]["factor_snapshot_json"]["normalization"]["cohort"]
    assert cohort["public_followup_authors"] == 2
    assert "_cohort_public_followup_count" not in result[0]


def test_analysis_window_loads_baseline_and_attention_history():
    now_ms = 1_777_800_000_000

    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["5m"]) == now_ms - 7 * 5 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["1h"]) == now_ms - 7 * 60 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["4h"]) == now_ms - 7 * 4 * 60 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["24h"]) == now_ms - 48 * 60 * 60 * 1000


def test_project_group_persists_current_runtime_contract_as_factor_snapshot():
    now_ms = 1_777_800_000_000
    window_ms = WINDOW_MS["5m"]
    score_since_ms = now_ms - window_ms
    rows = [
        source_row(f"current-{index}", received_at_ms=now_ms - 60_000 - index * 1_000, author=f"voice{index}")
        for index in range(4)
    ]
    rows.extend(
        source_row(
            f"baseline-{index}",
            received_at_ms=score_since_ms - index * window_ms - 60_000,
            author=f"base{index}",
        )
        for index in range(6)
    )

    row = _project_group(
        rows,
        now_ms=now_ms,
        window="5m",
        scope="all",
        score_since_ms=score_since_ms,
        window_ms=window_ms,
        total_window_events=4,
    )

    assert row is not None
    snapshot = row["factor_snapshot_json"]
    assert snapshot["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert snapshot["families"]["social_heat"]["facts"]["mentions_5m"] == 4
    assert snapshot["families"]["social_heat"]["facts"]["mentions_1h"] == 10
    assert snapshot["families"]["social_heat"]["facts"]["unique_authors"] == 4
    assert snapshot["families"]["social_propagation"]["facts"]["mentions"] == 4
    assert row["attention_json"] == {}
    assert row["score_json"] == {}


def test_projection_display_symbol_ignores_address_like_labels():
    row = {
        "display_symbol": "3iqrRNGG111111111111111111111111111111wNpump",
        "asset_symbol": "3IQRRNGG111111111111111111111111111111WNPUMP",
        "pricefeed_base_symbol": "REAL",
    }

    assert _display_symbol(row) == "REAL"


def test_projection_display_symbol_returns_none_when_only_ca_is_known():
    row = {
        "display_symbol": None,
        "asset_symbol": "3IQRRNGG111111111111111111111111111111WNPUMP",
        "pricefeed_base_symbol": None,
    }

    assert _display_symbol(row) is None


def test_project_group_keeps_resolved_asset_symbol_separate_from_mention_symbol():
    row = source_row(
        "event-asset-symbol-mismatch",
        received_at_ms=1_777_800_000_000,
    )
    row["display_symbol"] = "SHIT"
    row["asset_symbol"] = "SLOP"
    row["asset_name"] = "Dogeshit"

    projected = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")

    assert projected is not None
    assert projected["intent_json"]["display_symbol"] == "SHIT"
    assert projected["target_json"]["symbol"] == "SLOP"
    assert projected["asset_json"]["symbol"] == "SLOP"


def test_project_group_does_not_fallback_resolved_asset_symbol_to_mention_or_pricefeed():
    row = source_row(
        "event-asset-symbol-missing",
        received_at_ms=1_777_800_000_000,
    )
    row["display_symbol"] = "SATO"
    row["asset_symbol"] = None
    row["asset_name"] = None
    row["asset_identity_confidence"] = "unknown"
    row["asset_identity_reason_codes"] = ["NO_IDENTITY_EVIDENCE"]
    row["asset_identity_conflict_count"] = 0
    row["pricefeed_base_symbol"] = "SLOP"

    projected = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")

    assert projected is not None
    assert projected["intent_json"]["display_symbol"] == "SATO"
    assert projected["target_json"]["symbol"] is None
    assert projected["target_json"]["identity"] == {
        "confidence": "unknown",
        "reason_codes": ["NO_IDENTITY_EVIDENCE"],
        "conflict_count": 0,
    }


def test_projection_marks_unqueried_lookup_keys_as_not_searched():
    source_row = {
        "event_id": "event-1",
        "intent_id": "intent-1",
        "received_at_ms": 1_777_800_000_000,
        "author_handle": "toly",
        "is_watched": True,
        "resolution_status": "NIL",
        "target_type": None,
        "target_id": None,
        "pricefeed_id": None,
        "display_symbol": "UPEG",
        "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
        "candidate_ids_json": [],
        "lookup_keys_json": ["symbol:UPEG"],
        "discovery_results_json": None,
    }

    row = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="all")

    assert row["resolution_json"]["discovery"] == [
        {
            "lookup_key": "symbol:UPEG",
            "lookup_type": "dex_symbol_lookup",
            "status": "not_searched",
            "candidate_count": 0,
            "last_lookup_at_ms": None,
            "next_refresh_at_ms": None,
            "last_error": None,
            "error_count": 0,
        }
    ]


def test_projection_stale_write_does_not_advance_offset(monkeypatch):
    recorder = FakeProjectionRecorder()
    source_row = {
        "event_id": "event-1",
        "intent_id": "intent-1",
        "received_at_ms": 1_777_800_000_000,
        "author_handle": "toly",
        "is_watched": True,
        "resolution_status": "NIL",
        "target_type": None,
        "target_id": None,
        "pricefeed_id": None,
        "display_symbol": "UPEG",
        "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
        "candidate_ids_json": [],
        "lookup_keys_json": ["symbol:UPEG"],
        "discovery_results_json": None,
    }
    repos = type("Repos", (), {"conn": object(), "token_radar": FakeRejectingTokenRadar()})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "_source_rows",
        lambda self, since_ms, scope, now_ms: [source_row],
    )

    result = TokenRadarProjection(repos=repos).rebuild(
        window="5m",
        scope="all",
        now_ms=1_777_800_060_000,
        limit=20,
    )

    assert result == {
        "rows_written": 0,
        "source_rows": 1,
        "computed_at_ms": 1_777_800_060_000,
        "status": "stale_skipped",
    }
    assert recorder.stale_calls == [
        {
            "projection_name": TOKEN_RADAR_PROJECTION_NAME,
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "stale_before_ms": 1_777_800_060_000 - token_radar_projection_module.STALE_RUNNING_PROJECTION_MS,
            "finished_at_ms": 1_777_800_060_000,
            "commit": False,
        }
    ]
    assert recorder.advance_calls == []
    assert recorder.finish_calls == [
        {
            "run_id": "run-1",
            "status": "stale_skipped",
            "rows_read": 1,
            "rows_written": 0,
            "dirty_ranges_written": 0,
            "error": "newer_projection_exists",
            "commit": True,
        }
    ]


def test_projection_does_not_call_current_market_repository(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    now_ms = 1_777_800_060_000
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar})()

    def source_rows(self, since_ms, scope, now_ms):
        return [source_row("event-1", received_at_ms=now_ms - 60_000)]

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(TokenRadarProjection, "_source_rows", source_rows)

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    snapshot = token_radar.rows[0]["factor_snapshot_json"]
    assert snapshot["data_health"]["market"] == "ready"
    assert snapshot["families"]["timing_risk"]["data_health"] != "anchor_only"
    assert not hasattr(repos, "current_market")
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_marks_market_missing_when_anchor_price_has_not_arrived(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar})()
    now_ms = 1_777_800_060_000

    def source_rows(self, since_ms, scope, now_ms):
        row = source_row("event-1", received_at_ms=now_ms - 60_000)
        row["event_price_usd"] = None
        row["event_price_quote"] = None
        row["event_price_provider"] = None
        row["event_price_observed_at_ms"] = None
        row["first_price_usd"] = None
        return [row]

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(TokenRadarProjection, "_source_rows", source_rows)

    result = TokenRadarProjection(repos=repos).rebuild(
        window="5m",
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    snapshot = token_radar.rows[0]["factor_snapshot_json"]
    assert snapshot["data_health"]["market"] == "missing"
    assert "market_freshness_missing" not in snapshot["gates"]["blocked_reasons"]
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_market_uses_latest_market_snapshot_fields():
    row = source_row("event-market", received_at_ms=1_777_800_000_000)
    row["decision_latest_price_usd"] = 0.012
    row["decision_latest_market_cap_usd"] = 1_000_000
    row["decision_latest_liquidity_usd"] = 250_000
    row["decision_latest_volume_24h_usd"] = 12_000
    row["decision_latest_holders"] = 1000

    market = _market_context([row], resolved=True, now_ms=1_777_800_060_000)

    assert market["event_anchor"]["price_usd"] == 0.01
    assert market["event_anchor"]["provider"] == "okx"
    assert market["decision_latest"]["price_usd"] == 0.012
    assert market["decision_latest"]["market_cap_usd"] == 1_000_000
    assert market["decision_latest"]["liquidity_usd"] == 250_000
    assert market["decision_latest"]["volume_24h_usd"] == 12_000
    assert market["decision_latest"]["holders"] == 1000
    assert market["readiness"] == {
        "anchor_status": "ready",
        "latest_status": "live",
        "dex_floor_status": "ready",
        "missing_fields": [],
        "stale_fields": [],
    }
    assert "anchor_price_usd" not in market
    assert "live_price_persisted" not in market


def test_projection_market_uses_social_start_row_not_latest_row():
    market = _market_context(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "received_at_ms": 1_777_800_000_000,
                "market_provider": "okx_dex_search",
                "market_observed_at_ms": 1_777_800_120_000,
                "market_price_usd": 1.5,
                "market_price_basis": "usd",
                "event_price_usd": 1.0,
                "event_price_observed_at_ms": 1_777_800_000_500,
                "event_price_basis": "usd",
                "before_event_price_usd": 0.9,
                "before_event_price_basis": "usd",
                "first_price_usd": 0.8,
                "first_price_observed_at_ms": 1_777_799_000_000,
            },
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "received_at_ms": 1_777_800_120_000,
                "market_provider": "okx_dex_search",
                "market_observed_at_ms": 1_777_800_120_000,
                "market_price_usd": 1.5,
                "market_price_basis": "usd",
                "event_price_usd": 1.4,
                "event_price_observed_at_ms": 1_777_800_120_500,
                "event_price_basis": "usd",
                "first_price_usd": 0.8,
                "first_price_observed_at_ms": 1_777_799_000_000,
            },
        ],
        resolved=True,
        now_ms=1_777_800_180_000,
    )

    assert market["event_anchor"]["price_usd"] == 1.0
    assert market["decision_latest"] is None
    assert market["readiness"]["anchor_status"] == "ready"


def test_source_rows_uses_preferred_cex_pricefeed_when_resolution_has_no_pricefeed():
    conn = FakeConn()
    repos = type("Repos", (), {"conn": conn})()

    TokenRadarProjection(repos=repos)._source_rows(since_ms=1, scope="all", now_ms=2)

    assert "preferred_price_feed" in conn.sql
    assert "COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id)" in conn.sql
    assert "token_intent_resolutions.resolver_policy_version = %s" in conn.sql


def test_source_rows_does_not_read_historical_price_observations():
    conn = FakeConn()
    repos = type("Repos", (), {"conn": conn})()

    TokenRadarProjection(repos=repos)._source_rows(since_ms=1, scope="all", now_ms=2)

    assert "latest_feed_price" not in conn.sql
    assert "latest_subject_price" not in conn.sql
    assert "LEFT JOIN LATERAL" in conn.sql
    assert "event_price_observation" in conn.sql
    assert "decision_latest_observation" in conn.sql
    assert "token_market_price_baselines" not in conn.sql
    assert "message_event_price" not in conn.sql
    assert "event_history_price" not in conn.sql
    assert "latest_price_observation" not in conn.sql
    assert ") event_price ON true" not in conn.sql
    assert " OR " not in conn.sql
    assert "WITH window_events AS MATERIALIZED" in conn.sql
    assert "events.received_at_ms <= %s" in conn.sql
    assert conn.params == (1, 2, TOKEN_RADAR_RESOLVER_POLICY_VERSION, 2)


def test_projection_commits_ready_coverage_atomically_with_finished_run(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {"conn": object(), "token_radar": token_radar},
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "_source_rows",
        lambda self, since_ms, scope, now_ms: [source_row("event-1", received_at_ms=now_ms - 60_000)],
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    assert recorder.finish_calls[-1]["commit"] is False
    assert token_radar.coverage[-1]["status"] == "ready"
    assert token_radar.coverage[-1]["commit"] is True


def test_resolved_missing_anchor_reports_market_missing_without_freshness_block():
    rows = [
        {
            "event_id": f"event-{index}",
            "intent_id": f"intent-{index}",
            "received_at_ms": 1_777_800_000_000 + index,
            "author_handle": f"voice{index}",
            "is_watched": True,
            "resolution_status": "EXACT",
            "target_type": "Asset",
            "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "pricefeed_id": "pricefeed:dex-token:okx_dex_search:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "display_symbol": "PEPE",
            "asset_symbol": "PEPE",
            "asset_registry_status": "candidate",
            "reason_codes_json": [],
            "candidate_ids_json": [],
            "lookup_keys_json": [],
        }
        for index in range(7)
    ]

    row = _project_group(rows, now_ms=1_777_800_060_000, window="5m", scope="all")

    snapshot = row["factor_snapshot_json"]
    assert snapshot["data_health"]["market"] == "missing"
    assert "market_freshness_missing" not in snapshot["gates"]["blocked_reasons"]
    assert "market_metadata_missing" in snapshot["gates"]["risk_reasons"]
    assert row["data_health_json"] == {
        "factor_snapshot": "ready",
        "identity": "ready",
        "market": "missing",
        "social": "ready",
        "alpha": "ready",
    }
    assert row["attention_json"] == {}
    assert row["market_json"] == {}
    assert row["price_json"] == {}
    assert row["score_json"] == {}


def test_demoted_search_asset_does_not_project_as_resolved_high_alert():
    row = source_row(
        "event-1",
        received_at_ms=1_777_800_000_000,
    )
    row["asset_registry_status"] = "demoted_search"

    projected = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")

    assert projected["lane"] == "attention"
    assert projected["factor_snapshot_json"]["data_health"]["market"] == "missing"
    assert projected["data_health_json"]["identity"] == "ready"
    assert projected["market_json"] == {}


def source_row(event_id: str, *, received_at_ms: int, author: str = "alice") -> dict:
    return {
        "event_id": event_id,
        "intent_id": f"intent-{event_id}",
        "received_at_ms": received_at_ms,
        "author_handle": author,
        "is_watched": author == "alice",
        "text": "$PEPE strong follow-through",
        "text_clean": "$pepe strong follow-through",
        "intent_confidence": 1.0,
        "resolution_status": "EXACT",
        "target_type": "Asset",
        "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "pricefeed_id": "pricefeed:dex-token:okx_dex_search:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "display_symbol": "PEPE",
        "asset_symbol": "PEPE",
        "asset_chain_id": "eip155:1",
        "asset_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "asset_registry_status": "candidate",
        "reason_codes_json": [],
        "candidate_ids_json": [],
        "lookup_keys_json": [],
        "market_provider": "okx_dex_search",
        "market_observed_at_ms": received_at_ms,
        "market_price_usd": 0.01,
        "market_price_basis": "usd",
        "event_price_usd": 0.01,
        "event_price_provider": "okx",
        "event_price_observed_at_ms": received_at_ms + 500,
        "event_price_quote": None,
        "event_price_quote_symbol": "USD",
        "event_price_basis": "usd",
        "event_price_market_cap_usd": 1_000_000,
        "event_price_liquidity_usd": 250_000,
        "event_price_volume_24h_usd": None,
        "event_price_open_interest_usd": None,
        "event_price_holders": 1_000,
        "decision_latest_provider": "okx_dex_ws_price_info",
        "decision_latest_pricefeed_id": (
            "pricefeed:dex-token:okx_dex_search:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933"
        ),
        "decision_latest_observed_at_ms": received_at_ms + 1_000,
        "decision_latest_received_at_ms": received_at_ms + 1_000,
        "decision_latest_price_usd": 0.01,
        "decision_latest_price_quote": None,
        "decision_latest_quote_symbol": "USD",
        "decision_latest_price_basis": "usd",
        "decision_latest_market_cap_usd": 1_000_000,
        "decision_latest_liquidity_usd": 250_000,
        "decision_latest_volume_24h_usd": None,
        "decision_latest_open_interest_usd": None,
        "decision_latest_holders": 1_000,
        "first_price_usd": 0.01,
        "first_price_observed_at_ms": received_at_ms,
    }


def ranking_row(
    *,
    target_id: str,
    latest_seen_ms: int,
    decision: str = "watch",
    rank_score: float = 42,
) -> dict:
    return {
        "target_id": target_id,
        "decision": decision,
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {"target_id": target_id},
            "market": {
                "event_anchor": None,
                "decision_latest": None,
                "readiness": {
                    "anchor_status": "missing",
                    "latest_status": "missing",
                    "dex_floor_status": "missing_fields",
                    "missing_fields": [],
                    "stale_fields": [],
                },
            },
            "gates": {"max_decision": "high_alert"},
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "normalization": {"status": "pending_cross_section", "cohort": {}, "factor_ranks": {}, "alpha_rank": None},
            "composite": {
                "recommended_decision": decision,
                "rank_score": rank_score,
            },
            "families": {
                "social_heat": {
                    "score": 80,
                    "raw_score": 80,
                    "weight": 0.45,
                    "data_health": "ready",
                    "facts": {
                        "watched_mentions": 1,
                        "mentions_1h": 5,
                        "latest_seen_ms": latest_seen_ms,
                    },
                    "factors": {},
                },
                "social_propagation": {
                    "score": 80,
                    "raw_score": 80,
                    "weight": 0.40,
                    "data_health": "ready",
                    "facts": {},
                    "factors": {},
                },
                "semantic_catalyst": {
                    "score": 80,
                    "raw_score": 80,
                    "weight": 0.15,
                    "data_health": "ready",
                    "facts": {},
                    "factors": {},
                },
                "timing_risk": {
                    "score": 80,
                    "raw_score": 80,
                    "weight": 0.0,
                    "data_health": "ready",
                    "facts": {},
                    "factors": {},
                },
            },
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": latest_seen_ms},
        },
    }


class FakeConn:
    sql = ""
    params = None

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params
        return self

    def fetchall(self):
        return []


class FakeProjectionRecorder:
    def __init__(self):
        self.stale_calls: list[dict[str, object]] = []
        self.advance_calls: list[dict[str, object]] = []
        self.finish_calls: list[dict[str, object]] = []


class FakeProjectionRepository:
    def __init__(self, *, conn: object, recorder: FakeProjectionRecorder):
        self.conn = conn
        self.recorder = recorder

    def start_run(self, **kwargs):
        return {"run_id": "run-1", **kwargs}

    def mark_stale_running_runs(self, **kwargs):
        self.recorder.stale_calls.append(kwargs)
        return 0

    def advance_offset(self, **kwargs):
        self.recorder.advance_calls.append(kwargs)

    def finish_run(self, **kwargs):
        self.recorder.finish_calls.append(kwargs)


class FakeRejectingTokenRadar:
    def __init__(self):
        self.coverage: list[dict[str, object]] = []

    def mark_coverage(self, **kwargs):
        self.coverage.append(kwargs)

    def replace_rows(self, **kwargs):
        return False


class FakeTokenRadar:
    def __init__(self):
        self.rows: list[dict[str, object]] = []
        self.coverage: list[dict[str, object]] = []

    def mark_coverage(self, **kwargs):
        self.coverage.append(kwargs)

    def replace_rows(self, **kwargs):
        self.rows = list(kwargs["rows"])
        return True
