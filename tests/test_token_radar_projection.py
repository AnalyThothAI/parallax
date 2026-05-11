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
    _market,
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
    assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v10-current-market"
    assert TOKEN_RADAR_FACTOR_FAMILIES == (
        "identity",
        "social_attention",
        "social_quality",
        "social_semantics",
        "market_quality",
        "timing",
    )
    assert TOKEN_RADAR_SOURCE_TABLE == "token_intent_resolutions+asset_identity_current+current_market"
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

    with pytest.raises(ValueError, match="factor_snapshot_json must be non-empty"):
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
    assert projected["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v1"
    assert projected["factor_snapshot_json"]["subject"]["chain"] == "56"
    assert projected["factor_snapshot_json"]["hard_gates"]["eligible_for_high_alert"] is False
    assert projected["factor_version"] == "token_factor_snapshot_v1"
    assert projected["score_json"] == {}
    assert projected["attention_json"] == {}
    assert projected["market_json"] == {}
    assert projected["price_json"] == {}


def test_project_group_carries_cex_native_market_id_into_market_quality_snapshot():
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
    facts = projected["factor_snapshot_json"]["families"]["market_quality"]["facts"]
    assert facts["target_market_type"] == "cex"
    assert facts["native_market_id"] == "BTC-USDT"


def test_analysis_window_loads_baseline_and_attention_history():
    now_ms = 1_777_800_000_000

    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["5m"]) == now_ms - 7 * 5 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["1h"]) == now_ms - 7 * 60 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["4h"]) == now_ms - 7 * 4 * 60 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["24h"]) == now_ms - 7 * 24 * 60 * 60 * 1000


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
    assert snapshot["schema_version"] == "token_factor_snapshot_v1"
    assert snapshot["families"]["social_attention"]["facts"]["mentions_5m"] == 4
    assert snapshot["families"]["social_attention"]["facts"]["mentions_1h"] == 10
    assert snapshot["families"]["social_attention"]["facts"]["unique_authors"] == 4
    assert snapshot["families"]["social_quality"]["facts"]["mentions"] == 4
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


def test_short_window_projection_reads_existing_market_state_without_preflight(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    now_ms = 1_777_800_060_000
    current_market = FakeCurrentMarket(
        {
            ("Asset", "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"): _current_market_snapshot(
                now_ms=now_ms,
                market_status="fresh",
            )
        }
    )
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar, "current_market": current_market})()

    def source_rows(self, since_ms, scope, now_ms):
        return [source_row("event-1", received_at_ms=now_ms - 60_000)]

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(TokenRadarProjection, "_source_rows", source_rows)

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert "market_hydration" not in result
    market_facts = token_radar.rows[0]["factor_snapshot_json"]["families"]["market_quality"]["facts"]
    assert market_facts["market_status"] == "fresh"
    assert current_market.calls
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_hydrates_market_from_current_market_read_model(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    now_ms = 1_777_800_060_000
    current_market = FakeCurrentMarket(
        {
            ("Asset", "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"): _current_market_snapshot(
                now_ms=now_ms,
                market_status="partial",
                price_status="fresh",
                market_cap_status="stale",
                liquidity_status="stale",
                holders_status="stale",
            )
        }
    )
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar, "current_market": current_market})()

    def source_rows(self, since_ms, scope, now_ms):
        row = source_row("event-1", received_at_ms=now_ms - 60_000)
        for key in list(row):
            if key.startswith("market_"):
                row.pop(key)
        return [row]

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(TokenRadarProjection, "_source_rows", source_rows)

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    facts = token_radar.rows[0]["factor_snapshot_json"]["families"]["market_quality"]["facts"]
    assert facts["market_status"] == "partial"
    assert facts["field_statuses"]["price_usd"] == "fresh"
    assert facts["field_statuses"]["market_cap_usd"] == "stale"
    assert current_market.calls == [
        {
            "subjects": [
                {
                    "target_type": "Asset",
                    "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                }
            ],
            "now_ms": now_ms,
        }
    ]


def test_projection_hydrates_current_market_only_for_scored_window_rows(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    now_ms = 1_777_800_060_000
    window_row = source_row("event-window", received_at_ms=now_ms - 60_000)
    context_row = {
        **source_row("event-context", received_at_ms=now_ms - 20 * 60_000),
        "target_id": "asset:eip155:1:erc20:0xcontext",
        "asset_address": "0xcontext",
    }
    current_market = FakeCurrentMarket(
        {
            ("Asset", window_row["target_id"]): _current_market_snapshot(
                now_ms=now_ms,
                market_status="fresh",
            )
        }
    )
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar, "current_market": current_market})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "_source_rows",
        lambda self, since_ms, scope, now_ms: [context_row, window_row],
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    assert current_market.calls == [
        {
            "subjects": [{"target_type": "Asset", "target_id": window_row["target_id"]}],
            "now_ms": now_ms,
        }
    ]


def test_projection_marks_market_pending_when_no_external_price_refresh_has_arrived(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    current_market = FakeCurrentMarket()
    repos = type("Repos", (), {"conn": object(), "token_radar": token_radar, "current_market": current_market})()
    now_ms = 1_777_800_060_000

    def source_rows(self, since_ms, scope, now_ms):
        return [
            {
                **source_row("event-1", received_at_ms=now_ms - 60_000),
                "market_provider": None,
                "market_observed_at_ms": None,
                "market_price_usd": None,
                "event_price_usd": None,
                "first_price_usd": None,
            }
        ]

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
    assert "market_hydration" not in result
    market_facts = token_radar.rows[0]["factor_snapshot_json"]["families"]["market_quality"]["facts"]
    assert market_facts["market_status"] == "missing"
    assert current_market.calls
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_market_uses_latest_market_snapshot_fields():
    market = _market(
        [
            {
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "received_at_ms": 1_777_800_000_000,
                "market_provider": "gmgn_payload",
                "market_observed_at_ms": 1_777_800_000_000,
                "market_price_usd": 0.01,
                "market_price_quote": None,
                "market_quote_symbol": None,
                "market_price_basis": "usd",
                "market_market_cap_usd": 1_000_000,
                "market_liquidity_usd": 250_000,
                "market_volume_24h_usd": None,
                "market_open_interest_usd": None,
                "market_holders": 1000,
                "event_price_usd": 0.01,
                "event_price_basis": "usd",
                "before_event_price_usd": None,
                "first_price_usd": 0.01,
                "first_price_observed_at_ms": 1_777_800_000_000,
            }
        ],
        resolved=True,
        now_ms=1_777_800_060_000,
    )

    assert market["market_status"] == "fresh"
    assert market["market_observation_status"] == "ready"
    assert market["provider"] == "gmgn_payload"
    assert market["price_usd"] == 0.01
    assert market["market_cap_usd"] == 1_000_000
    assert market["liquidity_usd"] == 250_000
    assert market["holders"] == 1000
    assert market["snapshot_age_ms"] == 60_000
    assert market["snapshot_observed_at_ms"] == 1_777_800_000_000
    assert market["market_readiness"] == {
        "status": "fresh",
        "observation_status": "ready",
        "provider": "gmgn_payload",
        "snapshot_age_ms": 60_000,
        "snapshot_observed_at_ms": 1_777_800_000_000,
    }
    assert market["event_price_readiness"] == {
        "status": "ready",
        "source": "message_or_history",
        "social_signal_start_ms": 1_777_800_000_000,
        "price_at_social_start": 0.01,
        "price_change_status": "ready",
    }


def test_projection_market_uses_social_start_row_not_latest_row():
    market = _market(
        [
            {
                "received_at_ms": 1_777_800_000_000,
                "market_provider": "gmgn_payload",
                "market_observed_at_ms": 1_777_800_120_000,
                "market_price_usd": 1.5,
                "market_price_basis": "usd",
                "event_price_usd": 1.0,
                "event_price_basis": "usd",
                "before_event_price_usd": 0.9,
                "before_event_price_basis": "usd",
                "first_price_usd": 0.8,
                "first_price_observed_at_ms": 1_777_799_000_000,
            },
            {
                "received_at_ms": 1_777_800_120_000,
                "market_provider": "gmgn_payload",
                "market_observed_at_ms": 1_777_800_120_000,
                "market_price_usd": 1.5,
                "market_price_basis": "usd",
                "event_price_usd": 1.4,
                "event_price_basis": "usd",
                "first_price_usd": 0.8,
                "first_price_observed_at_ms": 1_777_799_000_000,
            },
        ],
        resolved=True,
        now_ms=1_777_800_180_000,
    )

    assert market["price_at_social_start"] == 1.0
    assert market["price_at_reference"] == 1.5
    assert market["price_change_since_social_pct"] == 0.5
    assert market["price_at_first_snapshot"] == 0.8
    assert market["price_change_since_first_snapshot_pct"] == 0.875


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
    assert "price_observations" not in conn.sql
    assert "message_event_price" not in conn.sql
    assert "event_history_price" not in conn.sql
    assert "latest_price" not in conn.sql
    assert ") event_price ON true" not in conn.sql
    assert " OR " not in conn.sql
    assert "WITH window_events AS MATERIALIZED" in conn.sql
    assert "events.received_at_ms <= %s" in conn.sql
    assert conn.params == (1, 2, TOKEN_RADAR_RESOLVER_POLICY_VERSION)


def test_projection_commits_ready_coverage_atomically_with_finished_run(monkeypatch):
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {"conn": object(), "token_radar": token_radar, "current_market": FakeCurrentMarket()},
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
        lambda self, since_ms, scope, now_ms: [
            source_row("event-1", received_at_ms=now_ms - 60_000)
        ],
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    assert recorder.finish_calls[-1]["commit"] is False
    assert token_radar.coverage[-1]["status"] == "ready"
    assert token_radar.coverage[-1]["commit"] is True


def test_resolved_pending_market_never_projects_as_high_alert():
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
            "pricefeed_id": "pricefeed:dex-token:gmgn:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
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
    market_facts = snapshot["families"]["market_quality"]["facts"]
    assert market_facts["market_status"] == "missing"
    assert row["decision"] == "discard"
    assert snapshot["composite"]["recommended_decision"] == "discard"
    assert "market_freshness_missing" in snapshot["hard_gates"]["blocked_reasons"]
    assert row["data_health_json"] == {
        "factor_snapshot": "ready",
        "identity": "ready",
        "market": "partial",
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
    assert projected["factor_snapshot_json"]["families"]["market_quality"]["facts"]["market_status"] == "missing"
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
        "pricefeed_id": "pricefeed:dex-token:gmgn:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "display_symbol": "PEPE",
        "asset_symbol": "PEPE",
        "asset_chain_id": "eip155:1",
        "asset_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "asset_registry_status": "candidate",
        "reason_codes_json": [],
        "candidate_ids_json": [],
        "lookup_keys_json": [],
        "market_provider": "gmgn_payload",
        "market_observed_at_ms": received_at_ms,
        "market_price_usd": 0.01,
        "market_price_basis": "usd",
        "event_price_usd": 0.01,
        "event_price_basis": "usd",
        "first_price_usd": 0.01,
        "first_price_observed_at_ms": received_at_ms,
        "market_market_cap_usd": 1_000_000,
        "market_liquidity_usd": 250_000,
        "market_holders": 1_000,
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
            "schema_version": "token_factor_snapshot_v1",
            "composite": {
                "recommended_decision": decision,
                "rank_score": rank_score,
            },
            "families": {
                "identity": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
                "social_attention": {
                    "score": 80,
                    "data_health": "ready",
                    "facts": {
                        "watched_mentions": 1,
                        "mentions_1h": 5,
                        "latest_seen_ms": latest_seen_ms,
                    },
                    "factors": {},
                },
                "social_quality": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
                "social_semantics": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
                "market_quality": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
                "timing": {"score": 80, "data_health": "ready", "facts": {}, "factors": {}},
            },
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


class FakeCurrentMarket:
    def __init__(self, snapshots: dict[tuple[str, str], dict[str, object]] | None = None):
        self.snapshots = snapshots or {}
        self.calls: list[dict[str, object]] = []

    def current_for_subjects(self, subjects, *, now_ms):
        self.calls.append({"subjects": list(subjects), "now_ms": now_ms})
        return {
            key: snapshot
            for key, snapshot in self.snapshots.items()
            if {"target_type": key[0], "target_id": key[1]} in subjects
        }


def _current_market_snapshot(
    *,
    now_ms: int,
    market_status: str,
    price_status: str = "fresh",
    market_cap_status: str = "fresh",
    liquidity_status: str = "fresh",
    holders_status: str = "fresh",
) -> dict[str, object]:
    stale_ms = now_ms - 86_400_000
    fresh_ms = now_ms - 30_000
    return {
        "target_type": "Asset",
        "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "market_status": market_status,
        "fields": {
            "price_usd": {
                "value": 0.104,
                "status": price_status,
                "observed_at_ms": fresh_ms,
                "age_ms": 30_000,
                "provider": "okx_dex_price",
            },
            "market_cap_usd": {
                "value": 51_000_000,
                "status": market_cap_status,
                "observed_at_ms": stale_ms if market_cap_status == "stale" else fresh_ms,
                "age_ms": 86_400_000 if market_cap_status == "stale" else 30_000,
                "provider": "okx_dex_search",
            },
            "liquidity_usd": {
                "value": 3_000_000,
                "status": liquidity_status,
                "observed_at_ms": stale_ms if liquidity_status == "stale" else fresh_ms,
                "age_ms": 86_400_000 if liquidity_status == "stale" else 30_000,
                "provider": "okx_dex_search",
            },
            "holders": {
                "value": 52_000,
                "status": holders_status,
                "observed_at_ms": stale_ms if holders_status == "stale" else fresh_ms,
                "age_ms": 86_400_000 if holders_status == "stale" else 30_000,
                "provider": "okx_dex_search",
            },
        },
    }
