from __future__ import annotations

from contextlib import contextmanager

import pytest

import gmgn_twitter_intel.domains.token_intel.services.token_radar_projection as token_radar_projection_module
from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import TokenRadarSourceRequest
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
    assert TOKEN_RADAR_SOURCE_TABLE == ("token_intent_resolutions+asset_identity_current+enriched_events+market_ticks")
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION
    assert not hasattr(token_radar_projection_module, "TokenRadarSourceQuery")


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


def test_compact_rank_inputs_preserves_rank_key_tie_breakers_from_scalar_columns():
    base = ranking_row(target_id="base", latest_seen_ms=1_777_800_000_000, decision="watch", rank_score=42)
    newer = ranking_row(target_id="newer", latest_seen_ms=1_777_800_030_000, decision="watch", rank_score=42)
    fallback_mentions = ranking_row(
        target_id="fallback-mentions",
        latest_seen_ms=1_777_800_010_000,
        decision="watch",
        rank_score=42,
    )
    fallback_mentions["factor_snapshot_json"]["families"]["social_heat"]["facts"]["mentions_1h"] = 0
    fallback_mentions["factor_snapshot_json"]["families"]["social_propagation"]["facts"]["mentions"] = 12
    high_alert = ranking_row(
        target_id="high-alert",
        latest_seen_ms=1_777_800_000_000,
        decision="high_alert",
        rank_score=5,
    )
    rows = [base, newer, fallback_mentions, high_alert]
    for row in rows:
        row.update(
            {
                "projection_version": PROJECTION_VERSION,
                "window": "1h",
                "scope": "all",
                "lane": "resolved",
                "target_type_key": "Asset",
                "identity_id": row["target_id"],
                "latest_event_received_at_ms": row["factor_snapshot_json"]["families"]["social_heat"]["facts"][
                    "latest_seen_ms"
                ],
                "payload_hash": f"hash-{row['target_id']}",
                "rank_input_version": "token-radar-rank-input-v1",
                "last_scored_at_ms": 1_777_800_060_000,
            }
        )

    compact_rows = TokenRadarProjection.rank_compact_inputs([_compact_rank_input_from_factor_row(row) for row in rows])

    assert [row["identity_id"] for row in compact_rows] == [
        "fallback-mentions",
        "newer",
        "base",
        "high-alert",
    ]
    fallback = next(row for row in compact_rows if row["identity_id"] == "fallback-mentions")
    assert fallback["social_heat_mentions_1h"] == 0
    assert fallback["social_propagation_mentions"] == 12


def test_compact_rank_inputs_does_not_admit_unresolved_identity_id_into_cohort():
    resolved = ranking_row(
        target_id="asset-resolved",
        latest_seen_ms=1_777_800_030_000,
        decision="watch",
        rank_score=35,
    )
    resolved["factor_snapshot_json"]["subject"]["symbol"] = "GOOD"
    unresolved = ranking_row(
        target_id="",
        latest_seen_ms=1_777_800_040_000,
        decision="watch",
        rank_score=99,
    )
    unresolved.update({"target_id": None, "identity_id": "symbol:HOT"})
    unresolved["factor_snapshot_json"]["subject"]["target_id"] = None
    unresolved["factor_snapshot_json"]["subject"]["symbol"] = "HOT"
    rows = [resolved, unresolved]

    compact_rows = TokenRadarProjection.rank_compact_inputs(
        [
            {
                **_compact_rank_input_from_factor_row(row),
                "cohort_high_confidence_mentions": 5,
                "cohort_kol_mentions": 3,
                "cohort_first_seen_global_24h": True,
            }
            for row in rows
        ]
    )

    unresolved_rank = next(row for row in compact_rows if row["identity_id"] == "symbol:HOT")
    assert unresolved_rank["target_id"] is None
    assert unresolved_rank["cohort_in_cohort"] is False
    assert unresolved_rank["factor_ranks"] == {family: None for family in TOKEN_RADAR_FACTOR_FAMILIES}


def test_full_rank_input_rebuild_enumerates_legacy_rows_and_scores_owner_path(monkeypatch):
    now_ms = 1_777_800_060_000
    recorder = FakeProjectionRecorder()
    token_radar = FakeTokenRadar()
    token_radar.rebuild_keys = [
        {
            "projection_version": PROJECTION_VERSION,
            "window": "1h",
            "scope": "all",
            "lane": "resolved",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "target_type": "Asset",
            "target_id": "asset-1",
            "payload_hash": "legacy-hash",
            "rank_input_version": "legacy_needs_rebuild",
        }
    ]
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: token_radar.score_calls.append(kwargs) or {"source_rows": 2, "rows_written": 1},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: (
            token_radar.refresh_calls.append(kwargs)
            or {"status": "ready", "source_rows": 1, "rows_written": 1, "computed_at_ms": kwargs["now_ms"]}
        ),
    )

    result = TokenRadarProjection(repos=repos).rebuild_rank_inputs_full(
        windows=("1h",),
        scopes=("all",),
        now_ms=now_ms,
        batch_size=100,
    )

    assert result["status"] == "ready"
    assert result["legacy_rows_seen"] == 1
    assert token_radar.list_rebuild_calls == [
        {
            "projection_version": PROJECTION_VERSION,
            "windows": ("1h",),
            "scopes": ("all",),
            "limit": 100,
        },
        {
            "projection_version": PROJECTION_VERSION,
            "windows": ("1h",),
            "scopes": ("all",),
            "limit": 100,
        },
    ]
    assert token_radar.source_request_batches[0][0].identity_id == "asset-1"
    assert token_radar.score_calls[0]["target"]["identity_id"] == "asset-1"
    assert token_radar.refresh_calls == [{"window": "1h", "scope": "all", "now_ms": now_ms, "limit": 100}]


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


def test_project_group_carries_first_seen_global_into_compact_rank_input_cohort():
    row = source_row("event-first-seen", received_at_ms=1_777_800_000_000)
    row["first_seen_global_24h"] = True

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    assert projected["_cohort_high_conf_count"] == 1
    assert projected["_cohort_kol_count"] == 0
    assert projected["_cohort_first_seen_global_24h"] is True
    assert projected["_cohort_public_followup_count"] == 0

    result = TokenRadarProjection.rank_compact_inputs([_compact_rank_input_from_factor_row(projected)])

    assert result[0]["cohort_in_cohort"] is True
    assert result[0]["cohort_metadata"]["first_seen_global_24h"] is True
    assert result[0]["cohort_metadata"]["public_followup_authors"] == 0


def test_project_group_carries_public_followup_count_as_compact_cohort_metadata():
    rows = [
        source_row("event-seed", received_at_ms=1_777_800_000_000, author="alice"),
        source_row("event-bob", received_at_ms=1_777_800_060_000, author="bob"),
        source_row("event-carol", received_at_ms=1_777_800_120_000, author="carol"),
    ]

    projected = _project_group(rows, now_ms=1_777_800_180_000, window="5m", scope="all")

    assert projected is not None
    assert projected["_cohort_public_followup_count"] == 2

    result = TokenRadarProjection.rank_compact_inputs([_compact_rank_input_from_factor_row(projected)])

    assert result[0]["cohort_metadata"]["public_followup_authors"] == 2


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
    row = {
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
    feature_row = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": FakeRejectingTokenRadar([feature_row])})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
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
            "commit": False,
        }
    ]


def test_projection_refuses_partial_rank_publish_when_rank_inputs_need_rebuild() -> None:
    row = source_row("event-1", received_at_ms=1_777_800_000_000)
    feature_row = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")
    token_radar = FakeTokenRadar([feature_row], stale_rank_inputs=1)
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    with pytest.raises(RuntimeError, match="token_radar_rank_inputs_require_full_rebuild"):
        TokenRadarProjection(repos=repos).refresh_rank_set(
            window="5m",
            scope="all",
            now_ms=1_777_800_060_000,
            limit=20,
        )

    assert token_radar.rows == []
    assert token_radar.coverage[-1]["status"] == "failed"
    assert token_radar.coverage[-1]["error"] == "token_radar_rank_inputs_require_full_rebuild"


def test_projection_refresh_rank_set_does_not_mark_user_coverage_running(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    feature_row = _project_group(
        [source_row("event-1", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="5m",
        scope="all",
    )
    token_radar = FakeTokenRadar([feature_row])
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    assert [call["status"] for call in token_radar.coverage] == ["ready"]


def test_projection_stale_cleanup_is_throttled_per_window_scope(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    feature_row = _project_group(
        [source_row("event-1", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="5m",
        scope="all",
    )
    token_radar = FakeTokenRadar([feature_row])
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    projection = TokenRadarProjection(repos=repos)
    first = projection.rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)
    second = projection.rebuild(window="5m", scope="all", now_ms=now_ms + 1_000, limit=20)

    assert first["status"] == "ready"
    assert second["status"] == "ready"
    assert len(recorder.stale_calls) == 1
    assert recorder.stale_calls[0]["stale_before_ms"] == (
        now_ms - token_radar_projection_module.STALE_RUNNING_PROJECTION_MS
    )


def test_projection_does_not_call_current_market_repository(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    feature_row = _project_group(
        [source_row("event-1", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="5m",
        scope="all",
    )
    token_radar = FakeTokenRadar([feature_row])
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    snapshot = token_radar.rows[0]["factor_snapshot_json"]
    assert snapshot["data_health"]["market"] == "ready"
    assert snapshot["families"]["timing_risk"]["data_health"] != "anchor_only"
    assert not hasattr(repos, "current_market")
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_hydration_payload_hash_mismatch_does_not_publish(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    projected = _project_group(
        [source_row("event-1", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="5m",
        scope="all",
    )
    assert projected is not None
    token_radar = FakeTokenRadar([projected], hydrated_payload_hash="changed-hash")
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    with pytest.raises(RuntimeError, match="payload_hash changed"):
        TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert token_radar.rows == []
    assert [call["status"] for call in token_radar.coverage] == ["failed"]


def test_projection_enqueues_narrative_admission_for_realtime_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type(
        "Repos",
        (),
        {"narrative_admission_dirty_targets": FakeRuntimeDirtyTargets()},
    )()

    TokenRadarProjection(repos=repos)._enqueue_narrative_admission_for_rank_changes(
        window="1h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.narrative_admission_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "source_watermark_ms": now_ms - 1_000,
                    "payload_hash": repos.narrative_admission_dirty_targets.enqueued[0]["targets"][0]["payload_hash"],
                    "priority": 40,
                    "due_at_ms": now_ms,
                }
            ],
            "reason": "token_radar_entered",
            "now_ms": now_ms,
            "commit": False,
        }
    ]


def test_projection_enqueues_pulse_trigger_for_matched_realtime_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type(
        "Repos",
        (),
        {"pulse_trigger_dirty_targets": FakeRuntimeDirtyTargets()},
    )()

    TokenRadarProjection(repos=repos)._enqueue_pulse_triggers_for_rank_changes(
        window="1h",
        scope="matched",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.pulse_trigger_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "matched",
                    "source_watermark_ms": now_ms - 1_000,
                    "payload_hash": repos.pulse_trigger_dirty_targets.enqueued[0]["targets"][0]["payload_hash"],
                    "priority": 40,
                    "due_at_ms": now_ms,
                }
            ],
            "reason": "token_radar_entered",
            "now_ms": now_ms,
            "commit": False,
        }
    ]


def test_projection_enqueues_token_profile_current_for_realtime_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type(
        "Repos",
        (),
        {"token_profile_current_dirty_targets": FakeRuntimeDirtyTargets()},
    )()

    TokenRadarProjection(repos=repos)._enqueue_token_profile_current_for_rank_changes(
        window="5m",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.token_profile_current_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "CexToken",
                    "target_id": "cex_token:BTC",
                    "source_watermark_ms": now_ms - 1_000,
                    "payload_hash": repos.token_profile_current_dirty_targets.enqueued[0]["targets"][0]["payload_hash"],
                    "priority": 70,
                    "due_at_ms": now_ms,
                }
            ],
            "reason": "token_radar_entered",
            "now_ms": now_ms,
            "commit": False,
        }
    ]


def test_projection_skips_narrative_admission_enqueue_outside_realtime_window_scope() -> None:
    repos = type("Repos", (), {})()

    TokenRadarProjection(repos=repos)._enqueue_narrative_admission_for_rank_changes(
        window="5m",
        scope="all",
        rows=[],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=1_777_800_060_000,
    )

    assert not hasattr(repos, "narrative_admission_dirty_targets")


def test_projection_marks_market_missing_when_event_market_tick_has_not_arrived(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000

    row = source_row("event-1", received_at_ms=now_ms - 60_000)
    row["event_price_usd"] = None
    row["event_price_quote"] = None
    row["event_price_provider"] = None
    row["event_price_observed_at_ms"] = None
    row["event_price_capture_method"] = "unavailable"
    row["event_price_capture_reason"] = "provider_no_quote"
    row["event_price_tick_lag_ms"] = None
    row["first_price_usd"] = None
    token_radar = FakeTokenRadar([_project_group([row], now_ms=now_ms, window="5m", scope="all")])
    repos = type("Repos", (), {"conn": FakeTransactionConn(), "token_radar": token_radar})()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).rebuild(
        window="5m",
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    snapshot = token_radar.rows[0]["factor_snapshot_json"]
    assert snapshot["data_health"]["market"] == "missing"
    assert snapshot["market"]["capture_method"] == "unavailable"
    assert snapshot["market"]["capture_reason"] == "provider_no_quote"
    assert snapshot["market"]["tick_lag_ms"] is None
    assert "market_freshness_missing" not in snapshot["gates"]["blocked_reasons"]
    assert token_radar.rows[0]["market_json"] == {}


def test_projection_market_uses_event_capture_and_latest_market_tick_fields():
    row = source_row("event-market", received_at_ms=1_777_800_000_000)
    row["event_price_capture_method"] = "tier3_inline"
    row["event_price_capture_reason"] = "inline_quote"
    row["event_price_tick_lag_ms"] = 500
    row["latest_price_usd"] = 0.012
    row["latest_price_market_cap_usd"] = 1_000_000
    row["latest_price_liquidity_usd"] = 250_000
    row["latest_price_volume_24h_usd"] = 12_000
    row["latest_price_holders"] = 1000

    market = _market_context([row], resolved=True, now_ms=1_777_800_060_000)

    assert market["event_anchor"]["price_usd"] == 0.01
    assert market["event_anchor"]["source"] == "tier3_inline"
    assert market["event_anchor"]["provider"] == "okx"
    assert "observation_kind" not in market["event_anchor"]
    assert market["capture_method"] == "tier3_inline"
    assert market["capture_reason"] == "inline_quote"
    assert market["tick_lag_ms"] == 500
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
    assert "_".join(("anchor", "price", "usd")) not in market
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
                "event_price_capture_method": "tier1_ws",
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
                "event_price_capture_method": "tier2_poll",
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


def test_projection_rebuild_dirty_targets_marks_claim_done_with_payload_hash(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated"},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 1, "source_rows": 1, "status": "ready"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert dirty_targets.done == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_blocks_before_claim_when_rank_inputs_are_stale():
    token_radar = FakeTokenRadar(stale_by_work_item={("5m", "all"): 3, ("1h", "matched"): 1})
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        work_items=(("5m", "all"), ("1h", "matched")),
        now_ms=1_777_800_060_000,
        limit=20,
    )

    assert result["status"] == "blocked"
    assert result["blocked_precondition"] is True
    assert result["reason"] == "token_radar_rank_inputs_require_full_rebuild"
    assert result["stale_rank_input_count"] == 4
    assert result["stale_rank_input_counts"] == {"5m:all": 3, "1h:matched": 1}
    assert dirty_targets.claim_due_calls == []
    assert dirty_targets.done == []
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_scores_only_selected_work_items(monkeypatch):
    score_calls: list[tuple[str, str]] = []
    refresh_calls: list[tuple[str, str]] = []
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def score(self, **kwargs):
        score_calls.append((kwargs["request"].window, kwargs["request"].scope))
        return {"source_rows": 1, "status": "updated"}

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", score)
    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m", "1h", "4h", "24h"),
        scopes=("all", "matched"),
        work_items=(("5m", "all"), ("1h", "matched")),
        now_ms=1_777_800_060_000,
        limit=20,
    )

    assert result["status"] == "ready"
    assert [(request.window, request.scope) for request in token_radar.source_request_batches[0]] == [
        ("5m", "all"),
        ("1h", "matched"),
    ]
    assert score_calls == [("5m", "all"), ("1h", "matched")]
    assert refresh_calls == [("1h", "matched"), ("5m", "all")]
    assert set(result["windows"]) == {"5m:all", "1h:matched"}


def test_projection_rebuild_dirty_targets_marks_error_with_payload_hash_on_failure(monkeypatch):
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    def fail_score(self, **kwargs):
        raise RuntimeError("target boom")

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", fail_score)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "failed"
    assert dirty_targets.done == []
    assert dirty_targets.errors == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
            "error": "target boom",
        }
    ]


def test_projection_keeps_claim_dirty_when_rank_refresh_fails(monkeypatch):
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated"},
    )

    def fail_refresh(self, **kwargs):
        raise RuntimeError("rank publish failed")

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", fail_refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "failed"
    assert dirty_targets.done == []
    assert dirty_targets.errors == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
            "error": "rank publish failed",
        }
    ]


def test_projection_keeps_claim_dirty_when_rank_refresh_stale_skips(monkeypatch):
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
            }
        ]
    )
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated"},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 0, "source_rows": 1, "status": "stale_skipped"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "failed"
    assert dirty_targets.done == []
    assert dirty_targets.errors == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
            "error": "rank refresh did not publish current rows: stale_skipped",
        }
    ]


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
        "event_price_capture_method": "tier1_ws",
        "event_price_capture_reason": "fresh_tick",
        "event_price_tick_lag_ms": 500,
        "latest_price_provider": "okx_dex_ws_price_info",
        "latest_price_pricefeed_id": (
            "pricefeed:dex-token:okx_dex_search:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933"
        ),
        "latest_price_observed_at_ms": received_at_ms + 1_000,
        "latest_price_received_at_ms": received_at_ms + 1_000,
        "latest_price_usd": 0.01,
        "latest_price_quote": None,
        "latest_price_quote_symbol": "USD",
        "latest_price_basis": "usd",
        "latest_price_market_cap_usd": 1_000_000,
        "latest_price_liquidity_usd": 250_000,
        "latest_price_volume_24h_usd": None,
        "latest_price_open_interest_usd": None,
        "latest_price_holders": 1_000,
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


class FakeTransactionConn:
    def __init__(self):
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield

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
    def __init__(self, feature_rows: list[dict[str, object] | None] | None = None):
        self.feature_rows = [row for row in feature_rows or [] if row is not None]
        self.coverage: list[dict[str, object]] = []

    def mark_coverage(self, **kwargs):
        self.coverage.append(kwargs)

    def list_rank_inputs_for_rank_set(self, **kwargs):
        return [_compact_rank_input_from_factor_row(row) for row in self.feature_rows]

    def stale_rank_input_count(self, **kwargs):
        return 0

    def load_target_feature_payloads_for_ranked_keys(self, keys):
        rows = []
        for row, key in zip(self.feature_rows, keys, strict=False):
            rows.append({**dict(row), **{field: key[field] for field in _RANK_KEY_FIELDS}})
        return rows

    def publish_rows(self, **kwargs):
        return False


class FakeDirtyTargets:
    def __init__(self, claims: list[dict[str, object]]):
        self.claims = claims
        self.claim_due_calls: list[dict[str, object]] = []
        self.done: list[dict[str, object]] = []
        self.errors: list[dict[str, object]] = []

    def claim_due(self, **kwargs):
        self.claim_due_calls.append(kwargs)
        return list(self.claims)

    def mark_done(self, keys, **kwargs):
        self.done.extend(dict(key) for key in keys)
        return len(self.done)

    def mark_error(self, keys, *, error, **kwargs):
        for key in keys:
            self.errors.append({**dict(key), "error": error})
        return len(self.errors)


class FakeRuntimeDirtyTargets:
    def __init__(self):
        self.enqueued: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms, commit):
        self.enqueued.append(
            {
                "targets": list(targets),
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": len(targets)}


class FakeRankSources:
    def __init__(
        self,
        *,
        token_radar: FakeTokenRadar,
        rows_by_request: dict[str, list[dict[str, object]]],
    ):
        self.token_radar = token_radar
        self.rows_by_request = rows_by_request

    def load_rows_for_requests(self, requests):
        request_list = list(requests)
        self.token_radar.source_request_batches.append(request_list)
        return {
            request.request_key: list(self.rows_by_request.get(request.request_key, [])) for request in request_list
        }


class FakeTokenRadar:
    def __init__(
        self,
        feature_rows: list[dict[str, object] | None] | None = None,
        *,
        hydrated_payload_hash: str | None = None,
        stale_rank_inputs: int = 0,
        stale_by_work_item: dict[tuple[str, str], int] | None = None,
    ):
        self.feature_rows = [row for row in feature_rows or [] if row is not None]
        self.rows: list[dict[str, object]] = []
        self.coverage: list[dict[str, object]] = []
        self.hydrated_payload_hash = hydrated_payload_hash
        self.stale_rank_inputs = int(stale_rank_inputs)
        self.stale_by_work_item = stale_by_work_item or {}
        self.rebuild_keys: list[dict[str, object]] = []
        self.list_rebuild_calls: list[dict[str, object]] = []
        self.score_calls: list[dict[str, object]] = []
        self.refresh_calls: list[dict[str, object]] = []
        self.source_request_batches: list[list[TokenRadarSourceRequest]] = []
        self.upserts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []
        self.target_projection_coverage: list[dict[str, object]] = []

    def mark_coverage(self, **kwargs):
        self.coverage.append(kwargs)

    def list_rank_inputs_for_rank_set(self, **kwargs):
        return [_compact_rank_input_from_factor_row(row) for row in self.feature_rows]

    def stale_rank_input_count(self, **kwargs):
        return self.stale_rank_inputs

    def rank_input_readiness_for_work_items(self, **kwargs):
        from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
            TokenRadarRankInputReadiness,
        )

        work_items = tuple(kwargs["work_items"])
        stale_by_work_item = {
            (str(window), str(scope)): int(self.stale_by_work_item.get((str(window), str(scope)), 0))
            for window, scope in work_items
            if int(self.stale_by_work_item.get((str(window), str(scope)), 0))
        }
        return TokenRadarRankInputReadiness(
            ready=not stale_by_work_item,
            stale_count=sum(stale_by_work_item.values()),
            stale_by_work_item=stale_by_work_item,
        )

    def load_target_feature_payloads_for_ranked_keys(self, keys):
        rows = []
        for row, key in zip(self.feature_rows, keys, strict=False):
            hydrated = dict(row)
            hydrated.update({field: key[field] for field in _RANK_KEY_FIELDS})
            hydrated["payload_hash"] = self.hydrated_payload_hash or key["payload_hash"]
            rows.append(hydrated)
        return rows

    def list_rank_input_rebuild_keys(self, **kwargs):
        self.list_rebuild_calls.append(kwargs)
        rows = list(self.rebuild_keys)
        self.rebuild_keys = []
        return rows

    def publish_rows(self, **kwargs):
        self.rows = list(kwargs["rows"])
        return True

    def upsert_target_feature(self, **kwargs):
        self.upserts.append(kwargs)
        return 1

    def delete_target_feature(self, **kwargs):
        self.deletes.append(kwargs)
        return 0

    def mark_target_projection_coverage(self, **kwargs):
        self.target_projection_coverage.append(kwargs)


def _compact_rank_input_from_factor_row(row: dict[str, object]) -> dict[str, object]:
    snapshot = row["factor_snapshot_json"]
    families = snapshot["families"]
    social_heat = families["social_heat"]
    social_propagation = families["social_propagation"]
    semantic_catalyst = families["semantic_catalyst"]
    timing_risk = families["timing_risk"]
    social_heat_facts = social_heat.get("facts") or {}
    social_propagation_facts = social_propagation.get("facts") or {}
    target_id = row.get("target_id")
    if target_id is None:
        target_id = snapshot["subject"].get("target_id")
    target_id = str(target_id) if target_id is not None else None
    return {
        "projection_version": row.get("projection_version") or PROJECTION_VERSION,
        "window": row.get("window") or "5m",
        "scope": row.get("scope") or "all",
        "lane": row.get("lane") or "attention",
        "target_type_key": row.get("target_type_key") or row.get("target_type") or "Asset",
        "identity_id": row.get("identity_id") or target_id or "",
        "target_type": row.get("target_type") or "Asset",
        "target_id": target_id,
        "pricefeed_id": row.get("pricefeed_id"),
        "latest_event_received_at_ms": row.get("source_max_received_at_ms")
        or row.get("latest_event_received_at_ms")
        or social_heat_facts.get("latest_seen_ms")
        or 0,
        "latest_market_observed_at_ms": row.get("latest_market_observed_at_ms"),
        "social_heat_raw_score": social_heat.get("raw_score", social_heat.get("score")),
        "social_heat_weight": social_heat.get("weight") or 0,
        "social_propagation_raw_score": social_propagation.get("raw_score", social_propagation.get("score")),
        "social_propagation_weight": social_propagation.get("weight") or 0,
        "semantic_catalyst_raw_score": semantic_catalyst.get("raw_score", semantic_catalyst.get("score")),
        "semantic_catalyst_weight": semantic_catalyst.get("weight") or 0,
        "timing_risk_raw_score": timing_risk.get("raw_score", timing_risk.get("score")),
        "timing_risk_weight": timing_risk.get("weight") or 0,
        "cohort_high_confidence_mentions": row.get("_cohort_high_conf_count") or 0,
        "cohort_kol_mentions": row.get("_cohort_kol_count") or 0,
        "cohort_public_followup_authors": row.get("_cohort_public_followup_count") or 0,
        "cohort_first_seen_global_24h": row.get("_cohort_first_seen_global_24h") is True,
        "cohort_symbol": snapshot["subject"].get("symbol") or "",
        "social_heat_watched_mentions": social_heat_facts.get("watched_mentions") or 0,
        "social_heat_mentions_1h": social_heat_facts.get("mentions_1h") or 0,
        "social_propagation_mentions": social_propagation_facts.get("mentions") or 0,
        "social_heat_latest_seen_ms": social_heat_facts.get("latest_seen_ms"),
        "raw_composite_score": snapshot["composite"].get("rank_score"),
        "recommended_decision": snapshot["composite"].get("recommended_decision") or "discard",
        "gates_max_decision": snapshot["gates"].get("max_decision") or "discard",
        "rank_input_version": "token-radar-rank-input-v1",
        "payload_hash": row.get("payload_hash") or f"feature-hash:{target_id}",
        "last_scored_at_ms": row.get("last_scored_at_ms") or 1_777_800_060_000,
    }


_RANK_KEY_FIELDS = (
    "projection_version",
    "window",
    "scope",
    "lane",
    "target_type_key",
    "identity_id",
    "payload_hash",
)
