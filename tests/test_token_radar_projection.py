from __future__ import annotations

import gmgn_twitter_intel.pipeline.token_radar_projection as token_radar_projection_module
from gmgn_twitter_intel.pipeline.token_radar_contract import (
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from gmgn_twitter_intel.pipeline.token_radar_projection import (
    PROJECTION_VERSION,
    WINDOW_MS,
    TokenRadarProjection,
    _analysis_since_ms,
    _display_symbol,
    _market,
    _project_group,
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


def test_token_radar_projection_uses_v5_auditable_contract():
    assert TOKEN_RADAR_PROJECTION_NAME == "token-radar"
    assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v5-auditable"
    assert TOKEN_RADAR_SOURCE_TABLE == "token_intent_resolutions+price_observations"
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION


def test_analysis_window_caps_small_windows_to_previous_window():
    now_ms = 1_777_800_000_000

    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["5m"]) == now_ms - 10 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["1h"]) == now_ms - 2 * 60 * 60 * 1000
    assert _analysis_since_ms(computed_at_ms=now_ms, window_ms=WINDOW_MS["24h"]) == now_ms - 24 * 60 * 60 * 1000


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
    monkeypatch.setattr(TokenRadarProjection, "_source_rows", lambda self, since_ms, scope, now_ms: [source_row])

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


def test_resolved_pending_market_never_projects_as_driver():
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
            "reason_codes_json": [],
            "candidate_ids_json": [],
            "lookup_keys_json": [],
        }
        for index in range(7)
    ]

    row = _project_group(rows, now_ms=1_777_800_060_000, window="5m", scope="all")

    assert row["market_json"]["market_observation_status"] == "pending_refresh"
    assert row["decision"] == "discard"
    assert set(row["score_json"]) == {"heat", "quality", "propagation", "tradeability", "timing", "opportunity"}
    assert "price_health" not in row["score_json"]
    for block in row["score_json"].values():
        assert block["score_version"]
        assert block["contributions"]


class FakeConn:
    sql = ""

    def execute(self, sql, params=None):
        self.sql = str(sql)
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
    def replace_rows(self, **kwargs):
        return False
