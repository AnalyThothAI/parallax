from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal

import pytest

import parallax.domains.token_intel.services.token_radar_projection as token_radar_projection_module
from parallax.domains.asset_market.repositories.token_capture_tier_dirty_target_repository import (
    token_capture_tier_rank_set_payload_hash,
)
from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.token_intel.interfaces import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from parallax.domains.token_intel.queries.token_radar_rank_source_query import TokenRadarFeatureSourceRequest
from parallax.domains.token_intel.services.token_radar_projection import (
    PROJECTION_VERSION,
    WINDOW_MS,
    TokenRadarProjection,
    TokenRadarProjectionWindowError,
    _analysis_since_ms,
    _claim_attempt_count,
    _compact_rank_key,
    _display_symbol,
    _market_context,
    _narrative_admission_target,
    _patch_ranked_current_row,
    _project_group,
    _rank_source_repair_analysis_since_ms,
    _row_from_target_feature,
    _select_top_ranked_by_lane,
    _source_requests_for_targets,
    _token_profile_current_target,
    token_radar_venue_for_rank_input,
)
from parallax.platform.current_read_model_payload_hash import PAYLOAD_HASH_HEX_LENGTH, PAYLOAD_HASH_PREFIX

DROPPED_CURRENT_ROW_COLUMNS = {
    "asset_json",
    "primary_venue_json",
    "target_json",
    "attention_json",
    "market_json",
    "price_json",
    "score_json",
}


def test_token_radar_projection_uses_factor_snapshot_contract():
    assert TOKEN_RADAR_PROJECTION_NAME == "token-radar"
    assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v13-social-attention"
    assert TOKEN_RADAR_FACTOR_FAMILIES == (
        "social_heat",
        "social_propagation",
        "semantic_catalyst",
        "timing_risk",
    )
    assert TOKEN_RADAR_SOURCE_TABLE == "token_radar_rank_source_events"
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION
    assert not hasattr(token_radar_projection_module, "TokenRadarSourceQuery")


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


@pytest.mark.parametrize(
    ("field", "error"),
    (
        ("raw_composite_score", "token_radar_rank_input_required:raw_composite_score"),
        ("gates_max_decision", "token_radar_rank_input_required:gates_max_decision"),
    ),
)
def test_compact_rank_inputs_require_formal_score_and_gate_fields_without_defaults(field: str, error: str):
    row = _compact_rank_input_from_factor_row(
        _feature_for_target_at(
            target_slug="bad-compact",
            received_at_ms=1_777_800_000_000,
            now_ms=1_777_800_060_000,
            window="1h",
        )
    )
    row.pop(field)

    with pytest.raises(RuntimeError, match=error):
        TokenRadarProjection.rank_compact_inputs([row])


@pytest.mark.parametrize(
    ("field", "error"),
    (
        ("rank_score", "token_radar_rank_input_required:rank_score"),
        ("recommended_decision", "token_radar_rank_input_required:recommended_decision"),
    ),
)
def test_compact_rank_key_requires_formal_ranked_score_and_decision_without_defaults(field: str, error: str):
    row = {
        **_compact_rank_input_from_factor_row(
            _feature_for_target_at(
                target_slug="bad-ranked",
                received_at_ms=1_777_800_000_000,
                now_ms=1_777_800_060_000,
                window="1h",
            )
        ),
        "rank_score": 12.0,
        "recommended_decision": "watch",
    }
    row.pop(field)

    with pytest.raises(RuntimeError, match=error):
        _compact_rank_key(row)


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


def test_current_row_builder_sets_scalar_score_and_quality_without_legacy_blocks():
    projected = _project_group(
        [source_row("event-ready", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }

    current_row = _patch_ranked_current_row(_row_from_target_feature(ranked), ranked)

    assert current_row["rank_score"] == 88
    assert current_row["quality_status"] == "ready"
    assert current_row["degraded_reasons_json"] == []
    assert current_row["factor_snapshot_json"]["composite"]["rank_score"] == 88
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(current_row)


def test_current_row_quality_marks_latest_market_stale_degraded():
    projected = _project_group(
        [source_row("event-stale-market", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }
    ranked["factor_snapshot_json"]["market"]["readiness"]["latest_status"] = "stale"

    current_row = _patch_ranked_current_row(_row_from_target_feature(ranked), ranked)

    assert current_row["quality_status"] == "degraded"
    assert current_row["degraded_reasons_json"] == ["market_latest_stale"]


@pytest.mark.parametrize(
    "field",
    (
        "normalization_status",
        "cohort_status",
        "cohort_size",
        "cohort_metadata",
        "factor_ranks",
        "rank",
        "latest_event_received_at_ms",
        "rank_score",
        "recommended_decision",
    ),
)
def test_patch_ranked_current_row_requires_formal_ranked_metadata_without_defaults(field: str):
    projected = _project_group(
        [source_row(f"event-ranked-metadata-{field}", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }
    current_row = _row_from_target_feature(ranked)
    ranked.pop(field)

    with pytest.raises(RuntimeError, match=f"token_radar_ranked_row_required:{field}"):
        _patch_ranked_current_row(current_row, ranked)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("normalization_status", "pending_cross_section", "token_radar_ranked_row_invalid:normalization_status"),
        ("cohort_status", "not_ranked", "token_radar_ranked_row_invalid:cohort_status"),
        ("cohort_size", -1, "token_radar_ranked_row_invalid:cohort_size"),
        ("cohort_metadata", [], "token_radar_ranked_row_invalid:cohort_metadata"),
        ("factor_ranks", [], "token_radar_ranked_row_invalid:factor_ranks"),
        ("rank", 0, "token_radar_ranked_row_invalid:rank"),
        ("latest_event_received_at_ms", -1, "token_radar_ranked_row_invalid:latest_event_received_at_ms"),
        ("rank_score", "bad", "token_radar_rank_input_invalid:rank_score"),
        ("recommended_decision", "low_info", "token_radar_rank_input_invalid:recommended_decision"),
    ),
)
def test_patch_ranked_current_row_rejects_invalid_ranked_metadata_without_defaults(
    field: str,
    value: object,
    error: str,
):
    projected = _project_group(
        [source_row(f"event-ranked-invalid-{field}", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }
    current_row = _row_from_target_feature(ranked)
    ranked[field] = value

    with pytest.raises(RuntimeError, match=error):
        _patch_ranked_current_row(current_row, ranked)


@pytest.mark.parametrize("field", ("cohort_in_cohort", "alpha_rank"))
def test_patch_ranked_current_row_requires_remaining_normalization_metadata_without_defaults(field: str):
    projected = _project_group(
        [source_row(f"event-ranked-normalization-{field}", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }
    current_row = _row_from_target_feature(ranked)
    ranked.pop(field)

    with pytest.raises(RuntimeError, match=f"token_radar_ranked_row_required:{field}"):
        _patch_ranked_current_row(current_row, ranked)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("cohort_in_cohort", "true", "token_radar_ranked_row_invalid:cohort_in_cohort"),
        ("alpha_rank", "bad", "token_radar_ranked_row_invalid:alpha_rank"),
        ("alpha_rank", None, "token_radar_ranked_row_invalid:alpha_rank"),
        ("factor_ranks", {"social_heat": 0.5}, "token_radar_ranked_row_invalid:factor_ranks"),
        (
            "factor_ranks",
            {family: ("bad" if family == "social_heat" else 0.88) for family in TOKEN_RADAR_FACTOR_FAMILIES},
            "token_radar_ranked_row_invalid:factor_ranks",
        ),
        (
            "factor_ranks",
            {family: (2.0 if family == "social_heat" else 0.88) for family in TOKEN_RADAR_FACTOR_FAMILIES},
            "token_radar_ranked_row_invalid:factor_ranks",
        ),
    ),
)
def test_patch_ranked_current_row_rejects_invalid_remaining_normalization_metadata_without_defaults(
    field: str,
    value: object,
    error: str,
):
    projected = _project_group(
        [source_row(f"event-ranked-invalid-normalization-{field}", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 88,
        "recommended_decision": "watch",
        "normalization_status": "ranked",
        "cohort_status": "ready",
        "cohort_in_cohort": True,
        "cohort_size": 10,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: 0.88 for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.88,
    }
    current_row = _row_from_target_feature(ranked)
    ranked[field] = value

    with pytest.raises(RuntimeError, match=error):
        _patch_ranked_current_row(current_row, ranked)


def test_patch_ranked_current_row_requires_no_signal_alpha_rank_none_without_defaulting():
    projected = _project_group(
        [source_row("event-ranked-no-signal-alpha", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 20,
        "recommended_decision": "discard",
        "normalization_status": "no_signal",
        "cohort_status": "insufficient",
        "cohort_in_cohort": False,
        "cohort_size": 0,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: None for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": None,
    }

    current_row = _patch_ranked_current_row(_row_from_target_feature(ranked), ranked)

    assert current_row["factor_snapshot_json"]["normalization"]["status"] == "no_signal"
    assert current_row["factor_snapshot_json"]["normalization"]["alpha_rank"] is None
    assert current_row["factor_snapshot_json"]["normalization"]["cohort"]["in_cohort"] is False


def test_patch_ranked_current_row_rejects_no_signal_alpha_rank_number_without_defaulting():
    projected = _project_group(
        [source_row("event-ranked-no-signal-alpha-invalid", received_at_ms=1_777_800_000_000)],
        now_ms=1_777_800_060_000,
        window="1h",
        scope="all",
    )
    ranked = {
        **_compact_rank_input_from_factor_row(projected),
        "rank": 1,
        "rank_score": 20,
        "recommended_decision": "discard",
        "normalization_status": "no_signal",
        "cohort_status": "insufficient",
        "cohort_in_cohort": False,
        "cohort_size": 0,
        "cohort_metadata": {"definition_version": "test"},
        "factor_ranks": {family: None for family in TOKEN_RADAR_FACTOR_FAMILIES},
        "alpha_rank": 0.5,
    }
    current_row = _row_from_target_feature(ranked)

    with pytest.raises(RuntimeError, match="token_radar_ranked_row_invalid:alpha_rank"):
        _patch_ranked_current_row(current_row, ranked)


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
    assert projected["chain_id"] == "56"
    assert projected["address"] == "0x1"
    assert projected["factor_snapshot_json"]["gates"]["eligible_for_high_alert"] is False
    assert projected["factor_version"] == "token_factor_snapshot_v3_social_attention"
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(projected)


def test_project_group_populates_v3_data_health_from_top_level_snapshot():
    row = source_row("event-cex", received_at_ms=1_777_800_000_000)
    row["target_type"] = "CexToken"
    row["target_id"] = "cex_token:BTC"
    row["cex_base_symbol"] = "BTC"
    row["cex_token_status"] = "canonical"
    row["pricefeed_provider"] = "binance"
    row["native_market_id"] = "BTC-USDT"
    row["market_volume_24h_usd"] = 123_000_000.0
    row["market_open_interest_usd"] = 45_000_000.0

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    assert projected["provider"] == "binance"
    assert projected["native_market_id"] == "BTC-USDT"
    snapshot = projected["factor_snapshot_json"]
    assert projected["data_health_json"] == {
        "factor_snapshot": "ready",
        "identity": snapshot["data_health"]["identity"],
        "market": snapshot["data_health"]["market"],
        "social": snapshot["data_health"]["social"],
        "alpha": snapshot["data_health"]["alpha"],
    }


def test_row_from_target_feature_derives_cex_live_key_from_pricefeed_id():
    row = source_row("event-cex", received_at_ms=1_777_800_000_000)
    row["target_type"] = "CexToken"
    row["target_id"] = "cex_token:BTC"
    row["cex_base_symbol"] = "BTC"
    row["cex_token_status"] = "canonical"
    row["pricefeed_id"] = "pricefeed:cex:binance:cex_swap:BTCUSDT"
    row["native_market_id"] = None

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    current_row = _row_from_target_feature(_compact_rank_input_from_factor_row(projected))
    assert current_row["provider"] == "binance"
    assert current_row["native_market_id"] == "BTCUSDT"


def test_row_from_target_feature_preserves_selected_intent_resolution_and_event_provenance():
    row = source_row("event-selected", received_at_ms=1_777_800_000_000)
    row["reason_codes_json"] = ["CHAIN_ADDRESS_EXACT"]
    row["candidate_ids_json"] = ["asset-candidate-1"]
    row["lookup_keys_json"] = ["address:eip155:1:0xabc"]

    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    current_row = _row_from_target_feature(_compact_rank_input_from_factor_row(projected))
    assert current_row["intent_id"] == "intent-event-selected"
    assert current_row["event_id"] == "event-selected"
    assert current_row["intent_json"] == projected["intent_json"]
    assert current_row["resolution_json"] == projected["resolution_json"]


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target-type-key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity-id"),
    ],
)
def test_row_from_target_feature_requires_formal_identity_without_alias_or_empty_defaults(
    field: str,
    aliases: dict[str, str],
):
    row = source_row("event-target-feature", received_at_ms=1_777_800_000_000)
    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    compact = _compact_rank_input_from_factor_row(projected)
    compact.pop(field)
    compact.update(aliases)

    with pytest.raises(RuntimeError, match="token_radar_current_identity_required"):
        _row_from_target_feature(compact)


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("projection_version", id="projection-version"),
        pytest.param("window", id="window"),
        pytest.param("scope", id="scope"),
        pytest.param("lane", id="lane"),
    ],
)
def test_row_from_target_feature_requires_formal_row_id_dimensions_without_empty_defaults(field: str):
    row = source_row("event-target-feature-dimensions", received_at_ms=1_777_800_000_000)
    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    compact = _compact_rank_input_from_factor_row(projected)
    compact.pop(field)

    with pytest.raises(RuntimeError, match=f"token_radar_target_feature_current_row_required:{field}"):
        _row_from_target_feature(compact)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("factor_snapshot_json", None, id="missing-snapshot"),
        pytest.param("factor_snapshot_json", [], id="invalid-snapshot-list"),
        pytest.param("intent_json", None, id="missing-intent"),
        pytest.param("intent_json", [], id="invalid-intent-list"),
        pytest.param("resolution_json", None, id="missing-resolution"),
        pytest.param("resolution_json", [], id="invalid-resolution-list"),
        pytest.param("source_event_ids_json", None, id="missing-source-events"),
        pytest.param("source_event_ids_json", [], id="empty-source-events"),
        pytest.param("source_intent_ids_json", None, id="missing-source-intents"),
        pytest.param("source_intent_ids_json", [], id="empty-source-intents"),
        pytest.param("latest_event_received_at_ms", None, id="missing-latest-seen"),
        pytest.param("latest_event_received_at_ms", "not-an-int", id="invalid-latest-seen"),
    ],
)
def test_row_from_target_feature_requires_formal_snapshot_and_latest_seen_without_defaults(
    field: str,
    value: object,
):
    row = source_row("event-target-feature-snapshot", received_at_ms=1_777_800_000_000)
    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    compact = _compact_rank_input_from_factor_row(projected)
    if value is None:
        compact.pop(field)
    else:
        compact[field] = value

    with pytest.raises(RuntimeError, match=f"token_radar_target_feature_current_row_.*:{field}"):
        _row_from_target_feature(compact)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        pytest.param(None, "required", id="missing-last-scored"),
        pytest.param("bad-time", "invalid", id="invalid-last-scored"),
    ],
)
def test_row_from_target_feature_requires_last_scored_time_without_runtime_timestamp_fallback(
    value: object,
    error: str,
):
    row = source_row("event-target-feature-time", received_at_ms=1_777_800_000_000)
    projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

    assert projected is not None
    compact = _compact_rank_input_from_factor_row(projected)
    compact["updated_at_ms"] = 1_777_800_070_000
    if value is None:
        compact.pop("last_scored_at_ms")
    else:
        compact["last_scored_at_ms"] = value

    with pytest.raises(RuntimeError, match=f"token_radar_target_feature_current_row_{error}:last_scored_at_ms"):
        _row_from_target_feature(compact)


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


def test_project_group_rejects_unknown_window_without_1h_fallback():
    row = source_row("event-1", received_at_ms=1_777_800_000_000)

    with pytest.raises(TokenRadarProjectionWindowError):
        _project_group([row], now_ms=1_777_800_060_000, window="7d", scope="all")


def test_rank_source_repair_analysis_requires_explicit_valid_work_item_windows():
    now_ms = 1_777_800_000_000

    with pytest.raises(TokenRadarProjectionWindowError):
        _rank_source_repair_analysis_since_ms(computed_at_ms=now_ms, work_items=())

    with pytest.raises(TokenRadarProjectionWindowError):
        _rank_source_repair_analysis_since_ms(computed_at_ms=now_ms, work_items=(("7d", "all", "all"),))


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
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(row)


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
    assert projected["factor_snapshot_json"]["subject"]["symbol"] == "SLOP"


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
    assert projected["factor_snapshot_json"]["subject"]["symbol"] is None
    assert "target_json" not in projected


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
    }

    row = _project_group([source_row], now_ms=1_777_800_060_000, window="5m", scope="all")

    assert row["target_type_key"] == "LookupKey"
    assert row["identity_id"] == "symbol:UPEG"
    assert row["identity_id"] != "intent-1"
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


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("resolution_status", None, "token_radar_projection_resolution_required:resolution_status"),
        ("resolution_status", "", "token_radar_projection_resolution_invalid:resolution_status"),
        ("reason_codes_json", None, "token_radar_projection_resolution_required:reason_codes_json"),
        ("reason_codes_json", '["EXACT_ADDRESS"]', "token_radar_projection_resolution_invalid:reason_codes_json"),
        ("candidate_ids_json", None, "token_radar_projection_resolution_required:candidate_ids_json"),
        ("candidate_ids_json", {"candidate": "legacy"}, "token_radar_projection_resolution_invalid:candidate_ids_json"),
        ("lookup_keys_json", None, "token_radar_projection_resolution_required:lookup_keys_json"),
        ("lookup_keys_json", '["symbol:PEPE"]', "token_radar_projection_resolution_invalid:lookup_keys_json"),
    ],
)
def test_project_group_requires_formal_resolution_json_fields_without_empty_defaults(
    field: str,
    value: object,
    error: str,
) -> None:
    row = source_row("event-formal-resolution", received_at_ms=1_777_800_000_000)
    row[field] = value

    with pytest.raises(RuntimeError, match=error):
        _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")


def test_unresolved_projection_identity_requires_lookup_key_without_display_symbol_fallback() -> None:
    row = {
        "event_id": "event-lookup-missing",
        "intent_id": "intent-lookup-missing",
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
        "lookup_keys_json": [],
    }

    with pytest.raises(RuntimeError, match="token_radar_projection_identity_required"):
        _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("target_type", None, "token_radar_projection_resolved_target_required:target_type"),
        ("target_type", "", "token_radar_projection_resolved_target_invalid:target_type"),
        ("target_type", "MarketInstrument", "token_radar_projection_resolved_target_invalid:target_type"),
        ("target_id", None, "token_radar_projection_resolved_target_required:target_id"),
        ("target_id", "", "token_radar_projection_resolved_target_invalid:target_id"),
    ],
)
def test_high_confidence_resolution_requires_formal_target_identity_before_resolved_lane(
    field: str,
    value: object,
    error: str,
) -> None:
    row = source_row("event-malformed-resolved-target", received_at_ms=1_777_800_000_000)
    row["lookup_keys_json"] = ["symbol:PEPE"]
    row[field] = value

    with pytest.raises(RuntimeError, match=error):
        _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "asset_identity_confidence",
            None,
            "token_radar_projection_asset_identity_required:asset_identity_confidence",
        ),
        (
            "asset_identity_confidence",
            "",
            "token_radar_projection_asset_identity_invalid:asset_identity_confidence",
        ),
        (
            "asset_identity_reason_codes",
            None,
            "token_radar_projection_asset_identity_required:asset_identity_reason_codes",
        ),
        (
            "asset_identity_reason_codes",
            '["selected_current_identity"]',
            "token_radar_projection_asset_identity_invalid:asset_identity_reason_codes",
        ),
        (
            "asset_identity_conflict_count",
            None,
            "token_radar_projection_asset_identity_required:asset_identity_conflict_count",
        ),
        (
            "asset_identity_conflict_count",
            "",
            "token_radar_projection_asset_identity_invalid:asset_identity_conflict_count",
        ),
    ],
)
def test_resolved_asset_target_requires_formal_asset_identity_current_fields(
    field: str,
    value: object,
    error: str,
) -> None:
    row = source_row("event-malformed-asset-identity", received_at_ms=1_777_800_000_000)
    row[field] = value

    with pytest.raises(RuntimeError, match=error):
        _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")


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
    }
    feature_row = _project_group([row], now_ms=1_777_800_060_000, window="5m", scope="all")
    token_radar = FakeRejectingTokenRadar([feature_row])
    repos = _rank_set_repos(token_radar)

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
        "generation_id": "newer-generation",
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
            "error": "newer_projection_exists",
            "commit": False,
        }
    ]


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
    repos = _rank_set_repos(token_radar)

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "ready"
    assert token_radar.publication_failures == []
    assert len(token_radar.rows) == 1


def test_projection_refresh_rank_set_returns_unchanged_when_publication_skips_current_rows(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    feature_row = _project_group(
        [source_row("event-unchanged", received_at_ms=now_ms - 60_000)],
        now_ms=now_ms,
        window="5m",
        scope="all",
    )

    class FakeUnchangedTokenRadar(FakeTokenRadar):
        def publish_current_generation(self, **kwargs):
            self.rows = list(kwargs["rows"])
            return {"status": "unchanged", "generation_id": "gen-existing", "rows_written": 0}

    repos = _rank_set_repos(FakeUnchangedTokenRadar([feature_row]))

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=now_ms, limit=20)

    assert result["status"] == "unchanged"
    assert result["rows_written"] == 0
    assert result["generation_id"] == "gen-existing"
    assert recorder.advance_calls
    assert recorder.finish_calls[-1]["status"] == "unchanged"
    assert recorder.finish_calls[-1]["rows_written"] == 0


def test_refresh_rank_set_requires_explicit_limit_before_publish():
    token_radar = FakeTokenRadar()
    repos = _rank_set_repos(token_radar)

    with pytest.raises(TypeError, match="limit"):
        TokenRadarProjection(repos=repos).refresh_rank_set(
            window="5m",
            scope="all",
            now_ms=1_777_800_060_000,
        )

    assert token_radar.publish_calls == []


def test_refresh_rank_set_excludes_expired_target_features_without_dirty_claims(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    window = "5m"
    cutoff_ms = now_ms - WINDOW_MS[window]
    expired_feature = _feature_for_target_at(
        target_slug="expired",
        received_at_ms=cutoff_ms - 1,
        now_ms=now_ms,
        window=window,
    )
    fresh_feature = _feature_for_target_at(
        target_slug="fresh",
        received_at_ms=cutoff_ms,
        now_ms=now_ms,
        window=window,
    )
    token_radar = FakeTokenRadar([expired_feature, fresh_feature])
    repos = _rank_set_repos(token_radar)

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).refresh_rank_set(
        window=window,
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert token_radar.list_rank_input_calls == [
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "window": window,
            "scope": "all",
            "min_latest_event_received_at_ms": cutoff_ms,
        }
    ]
    assert result["status"] == "ready"
    assert result["source_rows"] == 1
    assert [row["identity_id"] for row in token_radar.rows] == ["asset:fresh"]
    assert [row["source_max_received_at_ms"] for row in token_radar.rows] == [cutoff_ms]
    assert not hasattr(repos, "token_radar_dirty_targets")


def test_rank_current_rows_requires_latest_event_received_at_ms_without_zero_skip():
    token_radar = FakeTokenRadar()
    row = _compact_rank_input_from_factor_row(
        _feature_for_target_at(
            target_slug="bad-latest",
            received_at_ms=1_777_800_000_000,
            now_ms=1_777_800_060_000,
            window="1h",
        )
    )
    row.pop("latest_event_received_at_ms")
    token_radar.list_rank_inputs_for_rank_set = lambda **kwargs: [row]

    with pytest.raises(RuntimeError, match="token_radar_rank_input_required:latest_event_received_at_ms"):
        TokenRadarProjection(repos=_rank_set_repos(token_radar))._rank_current_rows(
            window="1h",
            scope="all",
            venue="all",
            now_ms=1_777_800_060_000,
            limit=20,
        )


def test_select_top_ranked_by_lane_requires_lane_without_silent_drop():
    row = ranking_row(target_id="bad-lane", latest_seen_ms=1_777_800_000_000)

    with pytest.raises(RuntimeError, match="token_radar_rank_input_required:lane"):
        _select_top_ranked_by_lane([row], limit=20)


def test_refresh_rank_set_publishes_empty_ready_generation_when_no_features_are_window_fresh(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    window = "5m"
    cutoff_ms = now_ms - WINDOW_MS[window]
    expired_feature = _feature_for_target_at(
        target_slug="expired",
        received_at_ms=cutoff_ms - 1,
        now_ms=now_ms,
        window=window,
    )
    token_radar = FakeTokenRadar([expired_feature])
    repos = _rank_set_repos(token_radar)

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).refresh_rank_set(
        window=window,
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert result["rows_written"] == 0
    assert result["source_rows"] == 0
    assert token_radar.publish_calls
    assert token_radar.publish_calls[0]["rows"] == []
    assert token_radar.publish_calls[0]["source_rows"] == 0
    assert token_radar.publish_calls[0]["source_frontier_ms"] == 0
    assert recorder.advance_calls[-1]["source_max_received_at_ms"] == 0
    assert recorder.finish_calls[-1]["rows_read"] == 0
    assert recorder.finish_calls[-1]["status"] == "ready"


def test_refresh_rank_set_does_not_prune_private_cache(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    window = "5m"
    feature_row = _feature_for_target_at(
        target_slug="fresh",
        received_at_ms=now_ms - 1_000,
        now_ms=now_ms,
        window=window,
    )
    token_radar = FakeTokenRadar([feature_row])
    rank_sources = FakeRankSources(token_radar=token_radar, rows_by_request={})
    repos = type(
        "Repos",
        (),
        {"conn": FakeTransactionConn(), "token_radar": token_radar, "token_radar_rank_sources": rank_sources},
    )()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    result = TokenRadarProjection(repos=repos).refresh_rank_set(
        window=window,
        scope="all",
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert "pruned_features" not in result
    assert "pruned_rank_source_edges" not in result
    assert "prune_target_features" not in token_radar.operation_calls
    assert "prune_rank_source_edges" not in token_radar.operation_calls
    assert token_radar.operation_calls[0] == "list_rank_inputs_for_rank_set"
    assert token_radar.prune_target_feature_calls == []
    assert token_radar.prune_rank_source_edge_calls == []


def test_refresh_rank_set_requires_callable_connection_transaction_before_publish(monkeypatch):
    recorder = FakeProjectionRecorder()
    now_ms = 1_777_800_060_000
    window = "5m"
    feature_row = _feature_for_target_at(
        target_slug="fresh",
        received_at_ms=now_ms - 1_000,
        now_ms=now_ms,
        window=window,
    )
    token_radar = FakeTokenRadar([feature_row])
    rank_sources = FakeRankSources(token_radar=token_radar, rows_by_request={})
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeNonCallableTransactionConn(),
            "token_radar": token_radar,
            "token_radar_rank_sources": rank_sources,
        },
    )()

    monkeypatch.setattr(
        token_radar_projection_module,
        "ProjectionRepository",
        lambda conn: FakeProjectionRepository(conn=conn, recorder=recorder),
    )

    with pytest.raises(RuntimeError, match="token_radar_projection_requires_transactional_connection"):
        TokenRadarProjection(repos=repos).refresh_rank_set(
            window=window,
            scope="all",
            now_ms=now_ms,
            limit=20,
        )

    assert token_radar.publish_calls == []
    assert recorder.advance_calls == []
    assert recorder.finish_calls == []


def test_prune_private_cache_is_explicitly_bounded_outside_publish():
    now_ms = 1_777_800_060_000
    target_delete_returns = iter([2, 1, 0, 0])
    token_radar = FakeTokenRadar()

    def prune_target_features(**kwargs):
        token_radar.operation_calls.append("prune_target_features")
        token_radar.prune_target_feature_calls.append(kwargs)
        return next(target_delete_returns)

    token_radar.prune_target_features = prune_target_features
    repos = _rank_set_repos(token_radar)

    result = TokenRadarProjection(repos=repos).prune_private_cache(
        windows=("5m", "1h"),
        scopes=("all", "matched"),
        now_ms=now_ms,
        retention_ms=600_000,
        limit=6,
    )

    assert result == {
        "status": "ready",
        "cutoff_ms": now_ms - 600_000,
        "target_features_deleted": 3,
        "rank_source_edges_deleted": 3,
        "limit": 6,
    }
    assert token_radar.prune_target_feature_calls == [
        {
            "projection_version": token_radar_projection_module.PROJECTION_VERSION,
            "window": "5m",
            "scope": "all",
            "latest_event_before_ms": now_ms - 600_000,
            "limit": 6,
            "commit": False,
        },
        {
            "projection_version": token_radar_projection_module.PROJECTION_VERSION,
            "window": "5m",
            "scope": "matched",
            "latest_event_before_ms": now_ms - 600_000,
            "limit": 4,
            "commit": False,
        },
        {
            "projection_version": token_radar_projection_module.PROJECTION_VERSION,
            "window": "1h",
            "scope": "all",
            "latest_event_before_ms": now_ms - 600_000,
            "limit": 3,
            "commit": False,
        },
        {
            "projection_version": token_radar_projection_module.PROJECTION_VERSION,
            "window": "1h",
            "scope": "matched",
            "latest_event_before_ms": now_ms - 600_000,
            "limit": 3,
            "commit": False,
        },
    ]
    assert token_radar.prune_rank_source_edge_calls == [
        {
            "projection_version": token_radar_projection_module.PROJECTION_VERSION,
            "event_received_before_ms": now_ms - 600_000,
            "limit": 3,
            "commit": False,
        }
    ]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        pytest.param("limit", 0, "token_radar_private_cache_limit_required", id="zero-limit"),
        pytest.param("limit", -1, "token_radar_private_cache_limit_required", id="negative-limit"),
        pytest.param("limit", True, "token_radar_private_cache_limit_required", id="bool-limit"),
        pytest.param("limit", "6", "token_radar_private_cache_limit_required", id="string-limit"),
        pytest.param("retention_ms", 0, "token_radar_private_cache_retention_ms_required", id="zero-retention"),
        pytest.param("retention_ms", -1, "token_radar_private_cache_retention_ms_required", id="negative-retention"),
        pytest.param("retention_ms", True, "token_radar_private_cache_retention_ms_required", id="bool-retention"),
        pytest.param(
            "retention_ms",
            "600000",
            "token_radar_private_cache_retention_ms_required",
            id="string-retention",
        ),
    ),
)
def test_prune_private_cache_rejects_malformed_bounds_before_transaction(
    field: str,
    value: object,
    error: str,
) -> None:
    token_radar = FakeTokenRadar()
    repos = _rank_set_repos(token_radar)
    kwargs = {
        "windows": ("5m",),
        "scopes": ("all",),
        "now_ms": 1_777_800_060_000,
        "retention_ms": 600_000,
        "limit": 6,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=error):
        TokenRadarProjection(repos=repos).prune_private_cache(**kwargs)  # type: ignore[arg-type]

    assert repos.conn.transaction_count == 0
    assert token_radar.operation_calls == []


def test_select_top_ranked_by_lane_allows_zero_limit() -> None:
    rows = token_radar_projection_module._select_top_ranked_by_lane(
        [{"lane": "resolved", "event_id": "event-1"}],
        limit=0,
    )

    assert rows == []


@pytest.mark.parametrize("limit", [-1, True, "1"])
def test_select_top_ranked_by_lane_rejects_malformed_limit(limit: object) -> None:
    with pytest.raises(ValueError, match="token_radar_rank_lane_limit_required"):
        token_radar_projection_module._select_top_ranked_by_lane([], limit=limit)  # type: ignore[arg-type]


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
    repos = _rank_set_repos(token_radar)

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
    repos = _rank_set_repos(token_radar)

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
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(token_radar.rows[0])
    assert token_radar.rows[0]["rank_score"] is not None
    assert token_radar.rows[0]["quality_status"] == "degraded"
    assert "cohort_not_rankable" in token_radar.rows[0]["degraded_reasons_json"]


def test_projection_enqueues_narrative_admission_for_realtime_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "asset_chain_id": "solana",
        "asset_address": "ABCdef123",
        "factor_snapshot_json": {
            "schema_version": "factor",
            "subject": {"symbol": "BONK", "chain_id": "solana", "address": "ABCdef123"},
        },
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


@pytest.mark.parametrize(
    "target_builder",
    (_narrative_admission_target, _token_profile_current_target),
)
def test_downstream_rank_change_targets_require_source_watermark_without_computed_at_fallback(target_builder):
    now_ms = 1_777_800_060_000
    row = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "asset_chain_id": "solana",
        "asset_address": "ABCdef123",
        "factor_snapshot_json": {
            "schema_version": "factor",
            "subject": {"symbol": "BONK", "chain_id": "solana", "address": "ABCdef123"},
        },
        "source_event_ids_json": ["event-1"],
        "payload_hash": "row-hash",
    }

    with pytest.raises(RuntimeError, match="token_radar_downstream_source_watermark_required"):
        target_builder(
            row,
            previous=None,
            window="1h",
            scope="all",
            computed_at_ms=now_ms,
            exited=False,
        )


@pytest.mark.parametrize("source_value", (None, 0, -1, True, "1777800060000"))
@pytest.mark.parametrize(
    "target_builder",
    (_narrative_admission_target, _token_profile_current_target),
)
def test_downstream_rank_change_targets_reject_invalid_source_watermark(target_builder, source_value):
    now_ms = 1_777_800_060_000
    row = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": source_value,
        "payload_hash": "row-hash",
    }

    with pytest.raises(RuntimeError, match="token_radar_downstream_source_watermark_required"):
        target_builder(
            row,
            previous=None,
            window="1h",
            scope="all",
            computed_at_ms=now_ms,
            exited=False,
        )


def test_projection_runtime_gate_suppresses_narrative_admission_dirty_targets() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "asset_chain_id": "solana",
        "asset_address": "ABCdef123",
        "factor_snapshot_json": {
            "schema_version": "factor",
            "subject": {"symbol": "BONK", "chain_id": "solana", "address": "ABCdef123"},
        },
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type(
        "Repos",
        (),
        {
            "narrative_admission_dirty_targets": FakeRuntimeDirtyTargets(),
            "token_profile_current_dirty_targets": FakeRuntimeDirtyTargets(),
            "token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets(),
            "asset_profile_refresh_targets": FakeRuntimeDirtyTargets(),
        },
    )()

    projection = TokenRadarProjection(repos=repos, enqueue_narrative_admission=False)
    projection._enqueue_runtime_dirty_targets_for_rank_changes(
        window="1h",
        scope="all",
        venue="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.token_profile_current_dirty_targets.enqueued
    assert repos.asset_profile_refresh_targets.enqueued
    assert repos.token_capture_tier_dirty_targets.enqueued
    assert repos.narrative_admission_dirty_targets.enqueued == []


@pytest.mark.parametrize(
    ("method_name", "repository_attribute", "kwargs"),
    [
        (
            "_enqueue_narrative_admission_for_rank_changes",
            "narrative_admission_dirty_targets",
            {"window": "1h", "scope": "all"},
        ),
        (
            "_enqueue_token_profile_current_for_rank_changes",
            "token_profile_current_dirty_targets",
            {"window": "5m", "scope": "all"},
        ),
    ],
)
def test_projection_downstream_targets_use_formal_current_identity_over_legacy_aliases(
    method_name: str,
    repository_attribute: str,
    kwargs: dict[str, str],
) -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "LegacyAsset",
        "target_id": "legacy-asset",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "decision": "high_alert",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type("Repos", (), {repository_attribute: FakeRuntimeDirtyTargets()})()

    getattr(TokenRadarProjection(repos=repos), method_name)(
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
        **kwargs,
    )

    enqueued_targets = getattr(repos, repository_attribute).enqueued[0]["targets"]
    assert enqueued_targets[0]["target_type"] == "Asset"
    assert enqueued_targets[0]["target_id"] == "asset-1"


@pytest.mark.parametrize(
    ("method_name", "expected_attribute", "kwargs"),
    [
        (
            "_enqueue_narrative_admission_for_rank_changes",
            "narrative_admission_dirty_targets",
            {"window": "1h", "scope": "all"},
        ),
        (
            "_enqueue_token_profile_current_for_rank_changes",
            "token_profile_current_dirty_targets",
            {"window": "5m", "scope": "all"},
        ),
        (
            "_enqueue_token_capture_tier_for_rank_changes",
            "token_capture_tier_dirty_targets",
            {"window": "24h", "scope": "all"},
        ),
    ],
)
def test_projection_runtime_dirty_target_enqueues_require_formal_repository_contracts(
    method_name: str,
    expected_attribute: str,
    kwargs: dict[str, str],
) -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "decision": "high_alert",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    projection = TokenRadarProjection(repos=type("Repos", (), {})())

    with pytest.raises(AttributeError, match=expected_attribute):
        getattr(projection, method_name)(
            rows=[row],
            exited_rows=[],
            previous_by_key={},
            computed_at_ms=now_ms,
            **kwargs,
        )


@pytest.mark.parametrize(
    ("method_name", "repository_attribute", "kwargs"),
    [
        (
            "_enqueue_narrative_admission_for_rank_changes",
            "narrative_admission_dirty_targets",
            {"window": "1h", "scope": "all"},
        ),
        (
            "_enqueue_token_profile_current_for_rank_changes",
            "token_profile_current_dirty_targets",
            {"window": "5m", "scope": "all"},
        ),
    ],
)
def test_projection_downstream_rank_change_requires_payload_hash_before_skip(
    method_name: str,
    repository_attribute: str,
    kwargs: dict[str, str],
) -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "decision": "high_alert",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "factor_snapshot_json": {"schema_version": "factor"},
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
    }
    repos = type("Repos", (), {repository_attribute: FakeRuntimeDirtyTargets()})()

    with pytest.raises(RuntimeError, match="token_radar_rank_change_payload_hash_required"):
        getattr(TokenRadarProjection(repos=repos), method_name)(
            rows=[row],
            exited_rows=[],
            previous_by_key={("resolved", "Asset", "asset-1"): {**row, "source_max_received_at_ms": now_ms - 2_000}},
            computed_at_ms=now_ms,
            **kwargs,
        )

    assert getattr(repos, repository_attribute).enqueued == []


def test_projection_enqueues_capture_tier_for_default_venue_rank_set_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.token_capture_tier_dirty_targets.enqueued == [
        {
            "reason": "token_radar_capture_tier_rank_set:24h:all",
            "rows": [row],
            "exited_rows": [],
            "source_watermark_ms": now_ms - 1_000,
            "payload_hash": repos.token_capture_tier_dirty_targets.enqueued[0]["payload_hash"],
            "now_ms": now_ms,
            "commit": False,
        }
    ]


@pytest.mark.parametrize(
    "source_value",
    [None, 0, -1, True, "1700000000000"],
)
def test_projection_capture_tier_requires_current_row_source_watermark_without_computed_at_fallback(
    source_value: object,
) -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
    }
    if source_value is not None:
        row["source_max_received_at_ms"] = source_value
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    with pytest.raises(RuntimeError, match="token_radar_downstream_source_watermark_required"):
        TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
            window="24h",
            scope="all",
            rows=[row],
            exited_rows=[],
            previous_by_key={},
            computed_at_ms=now_ms,
        )

    assert repos.token_capture_tier_dirty_targets.enqueued == []


def test_projection_capture_tier_uses_formal_current_identity_over_legacy_aliases() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "LegacyAsset",
        "target_id": "legacy-asset",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88.0,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "chain_id": "solana",
        "address": "abc",
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert len(repos.token_capture_tier_dirty_targets.enqueued) == 1


def test_rank_input_venue_uses_formal_identity_over_legacy_aliases() -> None:
    assert (
        token_radar_venue_for_rank_input(
            {
                "target_type": "Asset",
                "target_type_key": "CexToken",
                "chain_id": "eip155:1",
            }
        )
        == "cex"
    )
    assert (
        token_radar_venue_for_rank_input(
            {
                "target_type": "CexToken",
                "target_type_key": "Asset",
                "chain_id": "eip155:1",
            }
        )
        == "eth"
    )


def test_projection_skips_capture_tier_when_only_source_watermark_artifacts_changed() -> None:
    now_ms = 1_777_800_060_000
    previous = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": now_ms - 10_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    row = {
        **previous,
        "rank_score": 88,
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash-watermark-only",
        "generation_id": "gen-watermark-only",
    }
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={("resolved", "Asset", "asset-1"): previous},
        computed_at_ms=now_ms,
    )

    assert repos.token_capture_tier_dirty_targets.enqueued == []


def test_projection_skips_capture_tier_for_unresolved_attention_rows() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": None,
        "target_id": None,
        "target_type_key": "LookupKey",
        "identity_id": "symbol:UPEG",
        "intent_id": "intent-1",
        "rank": 1,
        "rank_score": 88,
        "lane": "attention",
        "quality_status": "ready",
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.token_capture_tier_dirty_targets.enqueued == []


def test_projection_capture_tier_fingerprint_changes_when_rank_payload_changes_without_watermark_change() -> None:
    now_ms = 1_777_800_060_000
    previous = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    changed = {**previous, "rank_score": 89, "payload_hash": "row-hash-2"}
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[previous],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )
    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[changed],
        exited_rows=[],
        previous_by_key={("resolved", "Asset", "asset-1"): previous},
        computed_at_ms=now_ms,
    )

    first_hash = repos.token_capture_tier_dirty_targets.enqueued[0]["payload_hash"]
    second_hash = repos.token_capture_tier_dirty_targets.enqueued[1]["payload_hash"]
    assert first_hash != second_hash
    assert repos.token_capture_tier_dirty_targets.enqueued[0]["source_watermark_ms"] == now_ms - 1_000
    assert repos.token_capture_tier_dirty_targets.enqueued[1]["source_watermark_ms"] == now_ms - 1_000


def test_capture_tier_rank_set_fingerprint_ignores_source_watermark_metadata() -> None:
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "chain_id": "eip155:1",
        "address": "0xABC",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": 1_777_800_000_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }

    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row]) == (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[
                {
                    **row,
                    "source_max_received_at_ms": 1_777_800_030_000,
                    "payload_hash": "row-hash-watermark-only",
                    "generation_id": "gen-watermark-only",
                }
            ],
        )
    )


def test_capture_tier_rank_set_fingerprint_includes_live_market_key() -> None:
    cex_row = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "provider": "binance",
        "native_market_id": "BTCUSDT",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }
    asset_row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "chain_id": "eip155:1",
        "address": "0xABC",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }

    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[cex_row]) != (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[{**cex_row, "native_market_id": "ETHUSDT"}],
        )
    )
    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[asset_row]) != (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[{**asset_row, "address": "0xDEF"}],
        )
    )


def test_capture_tier_rank_set_fingerprint_accepts_decimal_rank_scores() -> None:
    row = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "provider": "binance",
        "native_market_id": "BTCUSDT",
        "rank": 1,
        "rank_score": Decimal("88.5"),
        "score": Decimal("88.5"),
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
    }

    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row]) == (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[{**row, "rank_score": 88.5, "score": 88.5}],
        )
    )


def test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract() -> None:
    row = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "provider": "binance",
        "native_market_id": "BTCUSDT",
        "rank": 1,
        "rank_score": Decimal("88.5"),
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
    }

    payload_hash = token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row])

    assert payload_hash.startswith(PAYLOAD_HASH_PREFIX)
    assert len(payload_hash.removeprefix(PAYLOAD_HASH_PREFIX)) == PAYLOAD_HASH_HEX_LENGTH


def test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys() -> None:
    row = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "factor_snapshot_json": {
            "subject": {
                123: "legacy",
                "provider": "binance",
                "native_market_id": "BTCUSDT",
            }
        },
    }

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row])


def test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers() -> None:
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "chain_id": "solana",
        "address": "abc",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": {"legacy", "unordered"},
    }

    with pytest.raises(ValueError, match="current payload hash payload has unsupported containers"):
        token_capture_tier_rank_set_payload_hash(reason="repair", rows=[row])


def test_capture_tier_rank_set_fingerprint_uses_factor_snapshot_live_market_key() -> None:
    cex_row = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
        "factor_snapshot_json": {
            "subject": {
                "provider": "binance",
                "native_market_id": "BTCUSDT",
            }
        },
    }
    asset_row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
        "factor_snapshot_json": {
            "subject": {
                "chain_id": "eip155:1",
                "address": "0xABC",
            }
        },
    }

    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[cex_row]) == (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[
                {
                    **cex_row,
                    "provider": "binance",
                    "native_market_id": "BTCUSDT",
                }
            ],
        )
    )
    assert token_capture_tier_rank_set_payload_hash(reason="repair", rows=[asset_row]) == (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[{**asset_row, "chain_id": "eip155:1", "address": "0xABC"}],
        )
    )
    assert token_capture_tier_rank_set_payload_hash(
        reason="repair",
        rows=[{**cex_row, "pricefeed_id": "pricefeed:cex:binance:cex_swap:BTCUSDT"}],
    ) == (
        token_capture_tier_rank_set_payload_hash(
            reason="repair",
            rows=[
                {
                    **cex_row,
                    "provider": "binance",
                    "native_market_id": "BTCUSDT",
                    "pricefeed_id": "pricefeed:cex:binance:cex_swap:BTCUSDT",
                }
            ],
        )
    )


def test_projection_enqueues_capture_tier_when_live_market_key_changes() -> None:
    now_ms = 1_777_800_060_000
    previous = {
        "target_type": "CexToken",
        "target_id": "cex-token:btc",
        "target_type_key": "CexToken",
        "identity_id": "cex-token:btc",
        "rank": 1,
        "rank_score": 88,
        "lane": "resolved",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
        "generation_id": "gen-1",
        "factor_snapshot_json": {"subject": {"provider": "binance", "native_market_id": "BTCUSDT"}},
    }
    row = {
        **previous,
        "factor_snapshot_json": {"subject": {"provider": "binance", "native_market_id": "ETHUSDT"}},
    }
    repos = type("Repos", (), {"token_capture_tier_dirty_targets": FakeCaptureTierDirtyTargets()})()

    TokenRadarProjection(repos=repos)._enqueue_token_capture_tier_for_rank_changes(
        window="24h",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={("resolved", "CexToken", "cex-token:btc"): previous},
        computed_at_ms=now_ms,
    )

    assert len(repos.token_capture_tier_dirty_targets.enqueued) == 1
    assert repos.token_capture_tier_dirty_targets.enqueued[0]["rows"] == [row]


def test_projection_downstream_payload_hash_ignores_factor_snapshot_computed_at_noise() -> None:
    now_ms = 1_777_800_060_000
    base_snapshot = {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "composite": {"rank_score": 88},
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": now_ms},
    }
    row = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "factor_snapshot_json": base_snapshot,
        "source_event_ids_json": ["event-1"],
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "stable-row-hash",
    }
    noisy_timestamp_row = {
        **row,
        "factor_snapshot_json": {
            **base_snapshot,
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": now_ms + 60_000},
        },
    }
    business_change_row = {
        **row,
        "factor_snapshot_json": {
            **base_snapshot,
            "composite": {"rank_score": 89},
        },
    }

    base_target = _narrative_admission_target(
        row,
        previous=None,
        window="1h",
        scope="all",
        computed_at_ms=now_ms,
        exited=False,
    )
    noisy_timestamp_target = _narrative_admission_target(
        noisy_timestamp_row,
        previous=None,
        window="1h",
        scope="all",
        computed_at_ms=now_ms,
        exited=False,
    )
    business_change_target = _narrative_admission_target(
        business_change_row,
        previous=None,
        window="1h",
        scope="all",
        computed_at_ms=now_ms,
        exited=False,
    )

    assert base_target is not None
    assert noisy_timestamp_target is not None
    assert business_change_target is not None
    assert noisy_timestamp_target["payload_hash"] == base_target["payload_hash"]
    assert business_change_target["payload_hash"] != base_target["payload_hash"]


def test_projection_enqueues_token_profile_current_for_realtime_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "target_type_key": "CexToken",
        "identity_id": "cex_token:BTC",
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


def test_projection_enqueues_asset_profile_refresh_for_dex_asset_rank_changes() -> None:
    now_ms = 1_777_800_060_000
    row = {
        "target_type": "Asset",
        "target_id": "legacy-asset-alias",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "rank": 1,
        "lane": "resolved",
        "decision": "high_alert",
        "asset_chain_id": "solana",
        "asset_address": "ABCdef123",
        "factor_snapshot_json": {
            "subject": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "symbol": "BONK",
                "chain_id": "solana",
                "address": "ABCdef123",
            }
        },
        "source_max_received_at_ms": now_ms - 1_000,
        "payload_hash": "row-hash",
    }
    repos = type(
        "Repos",
        (),
        {"asset_profile_refresh_targets": FakeRuntimeDirtyTargets()},
    )()

    TokenRadarProjection(repos=repos)._enqueue_asset_profile_refresh_for_rank_changes(
        window="5m",
        scope="all",
        rows=[row],
        exited_rows=[],
        previous_by_key={},
        computed_at_ms=now_ms,
    )

    assert repos.asset_profile_refresh_targets.enqueued == [
        {
            "targets": [
                {
                    "provider": "gmgn_dex_profile",
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "chain_id": "solana",
                    "address": "ABCdef123",
                    "symbol": "BONK",
                    "source_watermark_ms": now_ms - 1_000,
                    "payload_hash": repos.asset_profile_refresh_targets.enqueued[0]["targets"][0]["payload_hash"],
                    "priority": 80,
                    "due_at_ms": now_ms,
                },
                {
                    "provider": "binance_web3_profile",
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "chain_id": "solana",
                    "address": "ABCdef123",
                    "symbol": "BONK",
                    "source_watermark_ms": now_ms - 1_000,
                    "payload_hash": repos.asset_profile_refresh_targets.enqueued[0]["targets"][1]["payload_hash"],
                    "priority": 80,
                    "due_at_ms": now_ms,
                },
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
    repos = _rank_set_repos(token_radar)

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
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(token_radar.rows[0])
    assert token_radar.rows[0]["quality_status"] == "degraded"
    assert "market_anchor_missing" in token_radar.rows[0]["degraded_reasons_json"]


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
                "source_event_ids_json": ["event-1"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": True},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 1, "source_rows": 1, "status": "ready"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert token_radar.rank_source_populate_batches == [
        {
            "targets": [
                {
                    "target_type_key": "Asset",
                    "identity_id": "asset-1",
                    "payload_hash": "claim-hash",
                    "lease_owner": "projection-worker",
                    "attempt_count": 1,
                    "source_event_ids_json": ["event-1"],
                }
            ],
            "projected_at_ms": now_ms,
            "analysis_since_ms": now_ms - 7 * 5 * 60 * 1000 - 5 * 60 * 1000,
            "commit": False,
        }
    ]
    assert len(token_radar.source_request_batches) == 1
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


def test_projection_rebuild_dirty_targets_isolates_source_target_failures(monkeypatch):
    token_radar = FakeTokenRadar()
    source_dirty_events = FakeDirtyTargets([])
    good_claim = {
        "projection_version": "token_radar_v1",
        "source_event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-good",
        "payload_hash": "source-good-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
    }
    bad_claim = {
        "projection_version": "token_radar_v1",
        "source_event_id": "event-2",
        "target_type_key": "Asset",
        "identity_id": "asset-bad",
        "payload_hash": "source-bad-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
    }
    rank_sources = FakeRankSources(
        token_radar=token_radar,
        rows_by_request={},
        affected_targets=[
            {"target_type_key": "Asset", "identity_id": "asset-good"},
            {"target_type_key": "Asset", "identity_id": "asset-bad"},
        ],
    )
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": FakeDirtyTargets([]),
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": rank_sources,
        },
    )()

    def project_source_request(self, *, target, **kwargs):
        if target["identity_id"] == "asset-bad":
            raise RuntimeError("token_radar_projection_asset_identity_required:asset_identity_confidence")
        return {"source_rows": 1, "status": "updated", "rank_set_changed": False}

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", project_source_request)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
        claimed_source_events=(good_claim, bad_claim),
    )

    assert result["status"] == "failed"
    assert source_dirty_events.done == [
        {
            "projection_version": "token_radar_v1",
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-good",
            "payload_hash": "source-good-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]
    assert source_dirty_events.errors == [
        {
            "projection_version": "token_radar_v1",
            "source_event_id": "event-2",
            "target_type_key": "Asset",
            "identity_id": "asset-bad",
            "payload_hash": "source-bad-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
            "error": "token_radar_projection_asset_identity_required:asset_identity_confidence",
        }
    ]


@pytest.mark.parametrize(
    "omitted_keyword",
    [
        pytest.param("rank_limit", id="rank-limit"),
        pytest.param("lease_owner", id="lease-owner"),
        pytest.param("max_attempts", id="max-attempts"),
    ],
)
def test_projection_rebuild_dirty_targets_requires_explicit_worker_policy_before_claiming(
    omitted_keyword: str,
):
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
    source_dirty_events = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": FakeTokenRadar(),
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=FakeTokenRadar(), rows_by_request={}),
        },
    )()
    kwargs = {
        "lease_ms": 120_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "windows": ("5m",),
        "scopes": ("all",),
        "now_ms": 1_777_800_060_000,
        "limit": 20,
        "rank_limit": 20,
        "lease_owner": "projection-worker",
    }
    kwargs.pop(omitted_keyword)

    with pytest.raises(TypeError, match=omitted_keyword):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(**kwargs)

    assert dirty_targets.claim_due_calls == []
    assert source_dirty_events.claim_due_calls == []


@pytest.mark.parametrize(
    ("policy_field", "policy_value"),
    [
        pytest.param("lease_ms", 0, id="zero-lease"),
        pytest.param("lease_ms", -1, id="negative-lease"),
        pytest.param("retry_ms", 0, id="zero-retry"),
        pytest.param("retry_ms", -1, id="negative-retry"),
        pytest.param("max_attempts", 0, id="zero-max-attempts"),
        pytest.param("max_attempts", -1, id="negative-max-attempts"),
    ],
)
def test_projection_rebuild_dirty_targets_rejects_non_positive_worker_policy_before_claiming(
    policy_field: str,
    policy_value: int,
):
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
    source_dirty_events = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": FakeTokenRadar(),
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=FakeTokenRadar(), rows_by_request={}),
        },
    )()
    kwargs = {
        "lease_ms": 120_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "windows": ("5m",),
        "scopes": ("all",),
        "now_ms": 1_777_800_060_000,
        "limit": 20,
        "rank_limit": 20,
        "lease_owner": "projection-worker",
    }
    kwargs[policy_field] = policy_value

    with pytest.raises(ValueError, match=f"token_radar_projection_{policy_field}_invalid"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(**kwargs)

    assert dirty_targets.claim_due_calls == []
    assert source_dirty_events.claim_due_calls == []


def test_projection_rebuild_dirty_targets_requires_target_claim_attempt_contract_before_work(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "source_event_ids_json": ["event-1"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": True},
    )

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_attempt_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert token_radar.source_request_batches == []
    assert dirty_targets.done == []
    assert dirty_targets.errors == []


@pytest.mark.parametrize("attempt_count", [0, -1, True, "1"])
def test_projection_dirty_claim_attempt_rejects_malformed_values_without_cast(attempt_count: object) -> None:
    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_attempt_contract_required"):
        _claim_attempt_count({"attempt_count": attempt_count})


def test_projection_rebuild_dirty_targets_requires_source_claim_attempt_contract_before_work():
    token_radar = FakeTokenRadar()
    source_dirty_events = FakeDirtyTargets(
        [
            {
                "projection_version": "token_radar_v1",
                "source_event_id": "event-1",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "source-claim-hash",
                "lease_owner": "projection-worker",
            }
        ]
    )
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": FakeDirtyTargets([]),
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_attempt_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert source_dirty_events.done == []
    assert source_dirty_events.errors == []


@pytest.mark.parametrize(
    ("field", "aliases", "error"),
    [
        pytest.param(
            "target_type_key",
            {"target_type": "Asset"},
            "token_radar_dirty_claim_identity_contract_required",
            id="target-type-key",
        ),
        pytest.param(
            "identity_id",
            {"target_id": "asset-1", "intent_id": "intent-1"},
            "token_radar_dirty_claim_identity_contract_required",
            id="identity-id",
        ),
    ],
)
def test_projection_rebuild_dirty_targets_requires_target_claim_identity_contract_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
    error: str,
    monkeypatch,
):
    token_radar = FakeTokenRadar()
    claim = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_event_ids_json": ["event-1"],
    }
    claim.pop(field)
    claim.update(aliases)
    dirty_targets = FakeDirtyTargets([claim])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: pytest.fail("target claim work should not start without formal identity"),
    )

    with pytest.raises(RuntimeError, match=error):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert token_radar.source_request_batches == []
    assert dirty_targets.done == []
    assert dirty_targets.errors == []


@pytest.mark.parametrize(
    ("field", "aliases", "error"),
    [
        pytest.param(
            "projection_version",
            {},
            "token_radar_source_dirty_claim_identity_contract_required",
            id="projection-version",
        ),
        pytest.param(
            "source_event_id",
            {"event_id": "event-1"},
            "token_radar_source_dirty_claim_identity_contract_required",
            id="source-event-id",
        ),
        pytest.param(
            "target_type_key",
            {"target_type": "Asset"},
            "token_radar_source_dirty_claim_identity_contract_required",
            id="target-type-key",
        ),
        pytest.param(
            "identity_id",
            {"target_id": "asset-1"},
            "token_radar_source_dirty_claim_identity_contract_required",
            id="identity-id",
        ),
    ],
)
def test_projection_rebuild_dirty_targets_requires_source_claim_identity_contract_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
    error: str,
):
    token_radar = FakeTokenRadar()
    claim = {
        "projection_version": "token_radar_v1",
        "source_event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "source-claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
    }
    claim.pop(field)
    claim.update(aliases)
    source_dirty_events = FakeDirtyTargets([claim])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": FakeDirtyTargets([]),
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    with pytest.raises(RuntimeError, match=error):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert source_dirty_events.done == []
    assert source_dirty_events.errors == []


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target-type-key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity-id"),
    ],
)
def test_projection_source_requests_for_targets_require_formal_identity_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
):
    target = {"target_type_key": "Asset", "identity_id": "asset-1"}
    target.pop(field)
    target.update(aliases)

    with pytest.raises(RuntimeError, match=f"token_radar_projection_target_identity_required:{field}"):
        _source_requests_for_targets(
            [target],
            (("5m", "all", "all"),),
            now_ms=1_777_800_060_000,
        )


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target-type-key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity-id"),
    ],
)
def test_projection_project_source_request_requires_formal_target_identity_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
):
    token_radar = FakeTokenRadar(delete_return=1)
    target = {"target_type_key": "Asset", "identity_id": "asset-1"}
    target.pop(field)
    target.update(aliases)
    request = TokenRadarFeatureSourceRequest(
        request_key="target-0:asset-1:5m:all:all",
        target_type_key="Asset",
        identity_id="asset-1",
        window="5m",
        scope="all",
        venue="all",
        analysis_since_ms=1_777_799_760_000,
        score_since_ms=1_777_799_760_000,
        now_ms=1_777_800_060_000,
    )

    with pytest.raises(RuntimeError, match=f"token_radar_projection_target_identity_required:{field}"):
        TokenRadarProjection(repos=_rank_set_repos(token_radar))._project_source_request(
            request=request,
            target=target,
            source_rows=[],
            now_ms=1_777_800_060_000,
        )

    assert token_radar.deletes == []
    assert token_radar.upserts == []


def test_projection_rebuild_dirty_targets_requires_target_claim_lease_owner_contract_before_work(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "attempt_count": 1,
                "source_event_ids_json": ["event-1"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: pytest.fail("target claim work should not start without lease_owner"),
    )

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_lease_owner_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert token_radar.source_request_batches == []
    assert dirty_targets.done == []
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_requires_source_claim_lease_owner_contract_before_work():
    token_radar = FakeTokenRadar()
    source_dirty_events = FakeDirtyTargets(
        [
            {
                "projection_version": "token_radar_v1",
                "source_event_id": "event-1",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "source-claim-hash",
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
            "token_radar_dirty_targets": FakeDirtyTargets([]),
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_lease_owner_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert source_dirty_events.done == []
    assert source_dirty_events.errors == []


def test_projection_rebuild_dirty_targets_requires_target_claim_payload_hash_contract_before_work(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_event_ids_json": ["event-1"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: pytest.fail("target claim work should not start without payload_hash"),
    )

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_payload_hash_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert token_radar.source_request_batches == []
    assert dirty_targets.done == []
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_requires_source_claim_payload_hash_contract_before_work():
    token_radar = FakeTokenRadar()
    source_dirty_events = FakeDirtyTargets(
        [
            {
                "projection_version": "token_radar_v1",
                "source_event_id": "event-1",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
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
            "token_radar_dirty_targets": FakeDirtyTargets([]),
            "token_radar_source_dirty_events": source_dirty_events,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    with pytest.raises(RuntimeError, match="token_radar_dirty_claim_payload_hash_contract_required"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert token_radar.rank_source_populate_batches == []
    assert source_dirty_events.done == []
    assert source_dirty_events.errors == []


def test_projection_rebuild_dirty_targets_processes_claims_inside_explicit_transaction(monkeypatch):
    conn = FakeTransactionConn()
    token_radar = FakeTokenRadar()

    class TransactionAwareDirtyTargets(FakeDirtyTargets):
        def __init__(self):
            super().__init__(
                [
                    {
                        "target_type_key": "Asset",
                        "identity_id": "asset-1",
                        "payload_hash": "claim-hash",
                        "lease_owner": "projection-worker",
                        "attempt_count": 1,
                        "source_event_ids_json": ["event-1"],
                    }
                ]
            )
            self.claim_depths: list[int] = []
            self.done_depths: list[int] = []
            self.done_kwargs: list[dict[str, object]] = []

        def claim_due(self, **kwargs):
            self.claim_depths.append(conn.transaction_depth)
            return super().claim_due(**kwargs)

        def mark_done(self, keys, **kwargs):
            self.done_depths.append(conn.transaction_depth)
            self.done_kwargs.append(kwargs)
            return super().mark_done(keys, **kwargs)

    class TransactionAwareRankSources(FakeRankSources):
        def __init__(self):
            super().__init__(token_radar=token_radar, rows_by_request={})
            self.populate_depths: list[int] = []

        def populate_edges_for_targets(self, targets, *, projected_at_ms, analysis_since_ms, commit):
            self.populate_depths.append(conn.transaction_depth)
            return super().populate_edges_for_targets(
                targets,
                projected_at_ms=projected_at_ms,
                analysis_since_ms=analysis_since_ms,
                commit=commit,
            )

    dirty_targets = TransactionAwareDirtyTargets()
    rank_sources = TransactionAwareRankSources()
    refresh_depths: list[int] = []
    repos = type(
        "Repos",
        (),
        {
            "conn": conn,
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": rank_sources,
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": True},
    )

    def refresh(self, **kwargs):
        refresh_depths.append(conn.transaction_depth)
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert conn.transaction_count == 1
    assert dirty_targets.claim_depths == [1]
    assert rank_sources.populate_depths == [1]
    assert refresh_depths == [1]
    assert dirty_targets.done_depths == [1]
    assert dirty_targets.claim_due_calls[0]["commit"] is False
    assert dirty_targets.done_kwargs == [{"now_ms": 1_777_800_060_000, "commit": False}]
    assert token_radar.rank_source_populate_batches[0]["commit"] is False


def test_projection_rebuild_dirty_targets_requires_transaction_before_claiming() -> None:
    dirty_targets = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeNonCallableTransactionConn(),
            "token_radar": FakeTokenRadar(),
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=FakeTokenRadar(), rows_by_request={}),
        },
    )()

    with pytest.raises(RuntimeError, match="token_radar_projection_requires_transactional_connection"):
        TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("5m",),
            scopes=("all",),
            now_ms=1_777_800_060_000,
            limit=20,
            rank_limit=20,
            lease_owner="projection-worker",
        )

    assert dirty_targets.claim_due_calls == []


def test_projection_rebuild_dirty_targets_bounds_rank_source_repair_by_analysis_window(monkeypatch):
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 0, "status": "unchanged", "rank_set_changed": False},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 0, "source_rows": 0, "status": "unchanged"},
    )

    TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("24h",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert token_radar.rank_source_populate_batches[0]["analysis_since_ms"] == (
        now_ms - 48 * 60 * 60 * 1000 - 5 * 60 * 1000
    )


def test_projection_rebuild_dirty_targets_copies_source_event_ids_into_requests(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_dirty": True,
                "market_dirty": False,
                "repair_dirty": False,
                "source_event_ids_json": ["event-2", "event-1"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 0, "status": "empty", "rank_set_changed": False},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    loaded_request = token_radar.source_request_batches[0][0]
    assert len(token_radar.rank_source_populate_batches) == 1
    assert token_radar.rank_source_populate_batches[0]["commit"] is False
    assert token_radar.rank_source_populate_batches[0]["targets"][0]["target_type_key"] == "Asset"
    assert not hasattr(loaded_request, "source_event_ids")
    assert dirty_targets.done
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_marks_source_dirty_without_event_ids_error(monkeypatch):
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_dirty": True,
                "market_dirty": False,
                "repair_dirty": False,
                "source_event_ids_json": [],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def fail_if_scored(self, **kwargs):
        raise AssertionError("source-dirty claim without event ids should not be scored")

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", fail_if_scored)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "failed"
    assert len(token_radar.rank_source_populate_batches) == 1
    assert token_radar.rank_source_populate_batches[0]["commit"] is False
    assert token_radar.rank_source_populate_batches[0]["targets"][0]["target_type_key"] == "Asset"
    assert len(token_radar.source_request_batches) == 1
    assert dirty_targets.done == []
    assert dirty_targets.errors == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
            "error": "source-dirty claim without event ids should not be scored",
        }
    ]


def test_projection_rebuild_dirty_targets_does_not_populate_source_edges_for_market_only_claim(monkeypatch):
    token_radar = FakeTokenRadar(upsert_return=0)
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_dirty": False,
                "market_dirty": True,
                "repair_dirty": False,
                "source_event_ids_json": [],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(
                token_radar=token_radar,
                rows_by_request={"*": [source_row("event-market-only", received_at_ms=1_777_800_000_000)]},
            ),
        },
    )()

    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 0, "source_rows": 1, "status": "ready"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert token_radar.rank_source_populate_batches == []
    assert len(token_radar.source_request_batches) == 1
    assert dirty_targets.done == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_unchanged_feature_claim_marks_done_without_rank_publish(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    now_ms = 1_777_800_060_000
    claim = {
        "target_type_key": "Asset",
        "identity_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "payload_hash": "claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_event_ids_json": ["event-unchanged"],
    }
    token_radar = FakeTokenRadar(upsert_return=0, delete_return=0)
    dirty_targets = FakeDirtyTargets([claim])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(
                token_radar=token_radar,
                rows_by_request={"*": [source_row("event-unchanged", received_at_ms=now_ms - 60_000)]},
            ),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert result["claimed"] == 1
    assert refresh_calls == []
    assert dirty_targets.done == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]
    assert dirty_targets.errors == []
    assert len(token_radar.upserts) == 1


def test_projection_rebuild_dirty_targets_explicit_due_work_item_publishes_even_when_feature_unchanged(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    now_ms = 1_777_800_060_000
    token_radar = FakeTokenRadar(upsert_return=0, delete_return=0)
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_event_ids_json": ["event-due-unchanged"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(
                token_radar=token_radar,
                rows_by_request={"*": [source_row("event-due-unchanged", received_at_ms=now_ms - 60_000)]},
            ),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 0, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        work_items=(("5m", "all"),),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert refresh_calls == [("5m", "all")]
    assert dirty_targets.done


def test_projection_rebuild_dirty_targets_deleted_feature_claim_publishes_touched_rank_set(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    now_ms = 1_777_800_060_000
    claim = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_event_ids_json": ["event-deleted"],
    }
    token_radar = FakeTokenRadar(delete_return=1)
    dirty_targets = FakeDirtyTargets([claim])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 0, "source_rows": 0, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert refresh_calls == [("5m", "all")]
    assert len(token_radar.deletes) == 2
    assert dirty_targets.done == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]


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
                "source_event_ids_json": ["event-score"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
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
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m", "1h", "4h", "24h"),
        scopes=("all", "matched"),
        work_items=(("5m", "all"), ("1h", "matched")),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert len(token_radar.rank_source_populate_batches) == 1
    assert token_radar.rank_source_populate_batches[0]["commit"] is False
    assert token_radar.rank_source_populate_batches[0]["targets"][0]["target_type_key"] == "Asset"
    assert [(request.window, request.scope) for request in token_radar.source_request_batches[0]] == [
        ("5m", "all"),
        ("1h", "matched"),
    ]
    assert score_calls == [("5m", "all"), ("1h", "matched")]
    assert refresh_calls == [("1h", "matched"), ("5m", "all")]
    assert set(result["windows"]) == {"5m:all:all", "1h:matched:all"}


def test_projection_rebuild_dirty_targets_separates_score_work_from_due_publish_work(monkeypatch):
    score_calls: list[tuple[str, str]] = []
    refresh_calls: list[tuple[str, str]] = []
    token_radar = FakeTokenRadar(upsert_return=0, delete_return=0)
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_event_ids_json": ["event-score-all"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def score(self, **kwargs):
        score_calls.append((kwargs["request"].window, kwargs["request"].scope))
        return {"source_rows": 0, "status": "unchanged", "rank_set_changed": False}

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 0, "source_rows": 0, "status": "unchanged"}

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", score)
    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        work_items=(("5m", "all"),),
        score_work_items=(("5m", "all"), ("1h", "all")),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert score_calls == [("5m", "all"), ("1h", "all")]
    assert refresh_calls == [("5m", "all")]
    assert set(result["windows"]) == {"5m:all:all"}
    assert dirty_targets.done


def test_projection_rebuild_dirty_targets_publishes_requested_work_items_without_dirty_claims(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 0, "source_rows": 0, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        work_items=(("5m", "all"),),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert result["claimed"] == 0
    assert refresh_calls == [("5m", "all")]
    assert result["windows"]["5m:all:all"]["status"] == "ready"


def test_projection_rebuild_dirty_targets_accepts_unchanged_due_rank_result(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 0, "source_rows": 10, "status": "unchanged"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        work_items=(("5m", "all"),),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "ready"
    assert result["rows_written"] == 0
    assert refresh_calls == [("5m", "all")]
    assert result["windows"]["5m:all:all"] == {"rows_written": 0, "source_rows": 10, "status": "unchanged"}
    assert dirty_targets.errors == []


def test_projection_rebuild_dirty_targets_does_not_runtime_scan_recent_resolved_targets_when_idle(monkeypatch):
    refresh_calls: list[tuple[str, str]] = []
    token_radar = FakeTokenRadar()
    dirty_targets = FakeDirtyTargets([])
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def refresh(self, **kwargs):
        refresh_calls.append((kwargs["window"], kwargs["scope"]))
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m", "1h"),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "idle"
    assert result["claimed"] == 0
    assert result["catch_up_enqueued"] == 0
    assert dirty_targets.catch_up_calls == []
    assert len(dirty_targets.claim_due_calls) == 1
    assert refresh_calls == []


def test_projection_rebuild_dirty_targets_marks_error_with_payload_hash_on_failure(monkeypatch):
    dirty_targets = FakeDirtyTargets(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "projection-worker",
                "attempt_count": 1,
                "source_event_ids_json": ["event-fail"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    def fail_score(self, **kwargs):
        raise RuntimeError("target boom")

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", fail_score)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
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
                "source_event_ids_json": ["event-rank-fail"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": True},
    )

    def fail_refresh(self, **kwargs):
        raise RuntimeError("rank publish failed")

    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", fail_refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
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


def test_projection_marks_noop_claim_done_when_another_claim_publish_fails(monkeypatch):
    noop_claim = {
        "target_type_key": "Asset",
        "identity_id": "asset-noop",
        "payload_hash": "noop-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_event_ids_json": ["event-noop"],
    }
    changed_claim = {
        "target_type_key": "Asset",
        "identity_id": "asset-changed",
        "payload_hash": "changed-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_event_ids_json": ["event-changed"],
    }
    dirty_targets = FakeDirtyTargets([noop_claim, changed_claim])
    token_radar = FakeTokenRadar()
    repos = type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_dirty_targets": dirty_targets,
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()

    def score(self, **kwargs):
        target = kwargs["target"]
        return {
            "source_rows": 1,
            "status": "updated",
            "rank_set_changed": target["identity_id"] == "asset-changed",
        }

    def fail_refresh(self, **kwargs):
        raise RuntimeError("rank publish failed")

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", score)
    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", fail_refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_777_800_060_000,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
    )

    assert result["status"] == "failed"
    assert dirty_targets.done == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-noop",
            "payload_hash": "noop-hash",
            "lease_owner": "projection-worker",
            "attempt_count": 1,
        }
    ]
    assert dirty_targets.errors == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-changed",
            "payload_hash": "changed-hash",
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
                "source_event_ids_json": ["event-stale-skip"],
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
            "token_radar_source_dirty_events": FakeDirtyTargets([]),
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request={}),
        },
    )()
    now_ms = 1_777_800_060_000

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": True},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 0, "source_rows": 1, "status": "stale_skipped"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=20,
        lease_owner="projection-worker",
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
            "asset_identity_confidence": "symbol_evidence",
            "asset_identity_reason_codes": ["selected_current_identity"],
            "asset_identity_conflict_count": 0,
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
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(row)


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
    assert DROPPED_CURRENT_ROW_COLUMNS.isdisjoint(projected)


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
        "asset_identity_confidence": "symbol_evidence",
        "asset_identity_reason_codes": ["selected_current_identity"],
        "asset_identity_conflict_count": 0,
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


def _feature_for_target_at(
    *,
    target_slug: str,
    received_at_ms: int,
    now_ms: int,
    window: str,
    scope: str = "all",
) -> dict:
    row = source_row(f"event-{target_slug}", received_at_ms=received_at_ms)
    row["target_id"] = f"asset:{target_slug}"
    row["pricefeed_id"] = f"pricefeed:{target_slug}"
    row["display_symbol"] = target_slug.upper()
    row["asset_symbol"] = target_slug.upper()
    projected = _project_group([row], now_ms=now_ms, window=window, scope=scope)
    assert projected is not None
    return projected


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
        self.transaction_depth = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        self.transaction_depth += 1
        try:
            yield
        finally:
            self.transaction_depth -= 1


class FakeNonCallableTransactionConn:
    transaction = "not-callable"


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
        self.publication_failures: list[dict[str, object]] = []
        self.operation_calls: list[str] = []
        self.prune_target_feature_calls: list[dict[str, object]] = []
        self.prune_rank_source_edge_calls: list[dict[str, object]] = []

    def mark_publication_failed(self, **kwargs):
        self.publication_failures.append(kwargs)

    def list_rank_inputs_for_rank_set(self, **kwargs):
        self.operation_calls.append("list_rank_inputs_for_rank_set")
        return [_compact_rank_input_from_factor_row(row) for row in self.feature_rows]

    def publish_current_generation(self, **kwargs):
        return {"status": "stale_skipped", "generation_id": "newer-generation", "rows_written": 0}

    def prune_target_features(self, **kwargs):
        self.operation_calls.append("prune_target_features")
        self.prune_target_feature_calls.append(kwargs)
        return 0


class FakeDirtyTargets:
    def __init__(self, claims: list[dict[str, object]]):
        self.claims = claims
        self.claim_due_calls: list[dict[str, object]] = []
        self.catch_up_calls: list[dict[str, object]] = []
        self.done: list[dict[str, object]] = []
        self.errors: list[dict[str, object]] = []

    def claim_due(self, **kwargs):
        self.claim_due_calls.append(kwargs)
        return list(self.claims)

    def enqueue_recent_resolved_targets(self, **kwargs):
        self.catch_up_calls.append(kwargs)
        return 0

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


class FakeCaptureTierDirtyTargets:
    def __init__(self):
        self.enqueued: list[dict[str, object]] = []

    def enqueue_rank_set(
        self,
        *,
        reason,
        rows,
        exited_rows,
        source_watermark_ms,
        now_ms,
        commit,
    ):
        row_list = list(rows)
        exited_list = list(exited_rows)
        payload_hash = token_capture_tier_rank_set_payload_hash(
            reason=reason,
            rows=row_list,
            exited_rows=exited_list,
        )
        self.enqueued.append(
            {
                "reason": reason,
                "rows": row_list,
                "exited_rows": exited_list,
                "source_watermark_ms": source_watermark_ms,
                "payload_hash": payload_hash,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": 1, "payload_hash": payload_hash}


class FakeRankSources:
    def __init__(
        self,
        *,
        token_radar: FakeTokenRadar,
        rows_by_request: dict[str, list[dict[str, object]]],
        affected_targets: list[dict[str, object]] | None = None,
    ):
        self.token_radar = token_radar
        self.rows_by_request = rows_by_request
        self.affected_targets = affected_targets or []

    def affected_targets_for_event_ids(self, requests):
        return list(self.affected_targets)

    def load_rows_for_requests(self, requests):
        request_list = list(requests)
        self.token_radar.source_request_batches.append(request_list)
        return {
            request.request_key: list(self.rows_by_request.get(request.request_key, self.rows_by_request.get("*", [])))
            for request in request_list
        }

    def populate_edges_for_event_ids(self, requests, *, projected_at_ms, commit):
        self.token_radar.rank_source_populate_batches.append(
            {
                "requests": list(requests),
                "projected_at_ms": projected_at_ms,
                "commit": commit,
            }
        )
        return len(requests)

    def populate_edges_for_targets(self, targets, *, projected_at_ms, analysis_since_ms, commit):
        self.token_radar.rank_source_populate_batches.append(
            {
                "targets": list(targets),
                "projected_at_ms": projected_at_ms,
                "analysis_since_ms": analysis_since_ms,
                "commit": commit,
            }
        )
        return len(targets)

    def latest_market_context_for_targets(self, targets):
        return {}

    def prune_edges(self, **kwargs):
        self.token_radar.operation_calls.append("prune_rank_source_edges")
        self.token_radar.prune_rank_source_edge_calls.append(kwargs)
        return 3


def _rank_set_repos(token_radar, *, rows_by_request: dict[str, list[dict[str, object]]] | None = None):
    return type(
        "Repos",
        (),
        {
            "conn": FakeTransactionConn(),
            "token_radar": token_radar,
            "token_radar_rank_sources": FakeRankSources(token_radar=token_radar, rows_by_request=rows_by_request or {}),
        },
    )()


class FakeTokenRadar:
    def __init__(
        self,
        feature_rows: list[dict[str, object] | None] | None = None,
        *,
        hydrated_payload_hash: str | None = None,
        stale_rank_inputs: int = 0,
        stale_by_work_item: dict[tuple[str, str], int] | None = None,
        upsert_return: int = 1,
        delete_return: int = 0,
    ):
        self.feature_rows = [row for row in feature_rows or [] if row is not None]
        self.rows: list[dict[str, object]] = []
        self.publication_failures: list[dict[str, object]] = []
        self.hydrated_payload_hash = hydrated_payload_hash
        self.stale_rank_inputs = int(stale_rank_inputs)
        self.stale_by_work_item = stale_by_work_item or {}
        self.rebuild_keys: list[dict[str, object]] = []
        self.list_rebuild_calls: list[dict[str, object]] = []
        self.score_calls: list[dict[str, object]] = []
        self.refresh_calls: list[dict[str, object]] = []
        self.source_request_batches: list[list[TokenRadarFeatureSourceRequest]] = []
        self.rank_source_populate_batches: list[dict[str, object]] = []
        self.list_rank_input_calls: list[dict[str, object]] = []
        self.publish_calls: list[dict[str, object]] = []
        self.operation_calls: list[str] = []
        self.prune_target_feature_calls: list[dict[str, object]] = []
        self.prune_rank_source_edge_calls: list[dict[str, object]] = []
        self.upserts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []
        self.upsert_return = int(upsert_return)
        self.delete_return = int(delete_return)

    def mark_publication_failed(self, **kwargs):
        self.publication_failures.append(kwargs)

    def list_rank_inputs_for_rank_set(self, **kwargs):
        self.operation_calls.append("list_rank_inputs_for_rank_set")
        self.list_rank_input_calls.append(kwargs)
        return [_compact_rank_input_from_factor_row(row) for row in self.feature_rows]

    def publish_current_generation(self, **kwargs):
        self.publish_calls.append(kwargs)
        self.rows = list(kwargs["rows"])
        return {
            "status": "published",
            "generation_id": str(kwargs["generation_id"]),
            "rows_written": len(self.rows),
        }

    def upsert_target_feature(self, **kwargs):
        self.upserts.append(kwargs)
        return self.upsert_return

    def delete_target_feature(self, **kwargs):
        self.deletes.append(kwargs)
        return self.delete_return

    def prune_target_features(self, **kwargs):
        self.operation_calls.append("prune_target_features")
        self.prune_target_feature_calls.append(kwargs)
        return 2


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
    intent_id = str(row.get("intent_id") or "intent-1")
    event_id = str(row.get("event_id") or "event-1")
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
        "factor_snapshot_json": snapshot,
        "intent_json": row.get("intent_json")
        or {
            "intent_id": intent_id,
            "event_id": event_id,
            "display_symbol": snapshot["subject"].get("symbol"),
        },
        "resolution_json": row.get("resolution_json")
        or {
            "status": "EXACT" if target_id else "NIL",
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
        },
        "source_event_ids_json": row.get("source_event_ids_json") or ["event-1"],
        "source_intent_ids_json": row.get("source_intent_ids_json") or [intent_id],
        "source_resolution_ids_json": row.get("source_resolution_ids_json")
        or [row.get("resolution_id") or "resolution-1"],
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
