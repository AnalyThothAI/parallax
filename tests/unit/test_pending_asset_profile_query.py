from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.queries.pending_asset_profile_query import PendingAssetProfileQuery
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import (
    GMGN_DEX_PROFILE_PROVIDER,
    MISSING_REFRESH_MS,
    AssetProfileRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_pending_asset_profile_query_returns_assets_without_profile_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        older_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-older",
            intent_id="intent-older",
            resolution_id="resolution-older",
            chain_id="eip155:1",
            address="0x1111111111111111111111111111111111111111",
            symbol="OLD",
            received_at_ms=1_700_000_010_000,
        )
        newer_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-newer",
            intent_id="intent-newer",
            resolution_id="resolution-newer",
            chain_id="solana",
            address="Newer111111111111111111111111111111111111111",
            symbol="NEW",
            received_at_ms=1_700_000_020_000,
        )
        conn.commit()

        rows = PendingAssetProfileQuery(conn).pending_rows(
            provider=GMGN_DEX_PROFILE_PROVIDER,
            now_ms=1_700_000_030_000,
            limit=10,
        )
    finally:
        conn.close()

    assert [row["asset_id"] for row in rows] == [newer_asset_id, older_asset_id]
    assert rows[0]["chain_id"] == "solana"
    assert rows[0]["address"] == "Newer111111111111111111111111111111111111111"
    assert rows[0]["symbol"] == "NEW"
    assert rows[0]["latest_event_received_at_ms"] == 1_700_000_020_000
    assert rows[0]["profile_status"] is None
    assert rows[0]["next_refresh_at_ms"] is None


def test_pending_asset_profile_query_skips_future_refresh_and_includes_due_rows(tmp_path):
    now_ms = 1_700_000_030_000
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        due_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-due",
            intent_id="intent-due",
            resolution_id="resolution-due",
            chain_id="eip155:1",
            address="0x2222222222222222222222222222222222222222",
            symbol="DUE",
            received_at_ms=1_700_000_020_000,
        )
        future_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-future",
            intent_id="intent-future",
            resolution_id="resolution-future",
            chain_id="eip155:1",
            address="0x3333333333333333333333333333333333333333",
            symbol="FUT",
            received_at_ms=1_700_000_025_000,
        )
        profiles = AssetProfileRepository(conn)
        profiles.upsert_status(
            asset_id=due_asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            status="missing",
            observed_at_ms=now_ms - MISSING_REFRESH_MS,
            next_refresh_at_ms=now_ms,
            last_error=None,
            commit=False,
        )
        profiles.upsert_status(
            asset_id=future_asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            status="missing",
            observed_at_ms=now_ms,
            next_refresh_at_ms=now_ms + MISSING_REFRESH_MS,
            last_error=None,
            commit=False,
        )
        conn.commit()

        rows = PendingAssetProfileQuery(conn).pending_rows(
            provider=GMGN_DEX_PROFILE_PROVIDER,
            now_ms=now_ms,
            limit=10,
        )
    finally:
        conn.close()

    assert [row["asset_id"] for row in rows] == [due_asset_id]
    assert rows[0]["profile_status"] == "missing"
    assert rows[0]["next_refresh_at_ms"] == now_ms


def test_pending_asset_profile_query_prioritizes_current_radar_assets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        non_radar_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-new-non-radar",
            intent_id="intent-new-non-radar",
            resolution_id="resolution-new-non-radar",
            chain_id="eip155:1",
            address="0x4444444444444444444444444444444444444444",
            symbol="NEW",
            received_at_ms=1_700_000_025_000,
        )
        radar_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-old-radar",
            intent_id="intent-old-radar",
            resolution_id="resolution-old-radar",
            chain_id="solana",
            address="Radar11111111111111111111111111111111111111",
            symbol="HOT",
            received_at_ms=1_700_000_010_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-hot",
            event_id="event-old-radar",
            intent_id="intent-old-radar",
            asset_id=None,
            target_id=radar_asset_id,
            symbol="HOT",
            rank=1,
            computed_at_ms=1_700_000_029_000,
        )
        conn.commit()

        rows = PendingAssetProfileQuery(conn).pending_rows(
            provider=GMGN_DEX_PROFILE_PROVIDER,
            now_ms=1_700_000_030_000,
            limit=10,
        )
    finally:
        conn.close()

    assert [row["asset_id"] for row in rows] == [radar_asset_id, non_radar_asset_id]
    assert rows[0]["best_radar_rank"] == 1
    assert rows[0]["latest_radar_computed_at_ms"] == 1_700_000_029_000
    assert rows[1]["best_radar_rank"] is None


def _insert_resolved_asset(
    conn: Any,
    *,
    event_id: str,
    intent_id: str,
    resolution_id: str,
    chain_id: str,
    address: str,
    symbol: str,
    received_at_ms: int,
) -> str:
    _insert_event(conn, event_id=event_id, received_at_ms=received_at_ms)
    _insert_intent(conn, intent_id=intent_id, event_id=event_id, observed_at_ms=received_at_ms)
    asset = RegistryRepository(conn).upsert_chain_asset(
        chain_id=chain_id,
        address=address,
        observed_at_ms=received_at_ms,
        commit=False,
    )
    asset_id = str(asset["asset_id"])
    _insert_current_identity(
        conn,
        asset_id=asset_id,
        symbol=symbol,
        observed_at_ms=received_at_ms,
    )
    _insert_resolution(
        conn,
        resolution_id=resolution_id,
        intent_id=intent_id,
        event_id=event_id,
        asset_id=asset_id,
        observed_at_ms=received_at_ms,
    )
    return asset_id


def _insert_event(conn: Any, *, event_id: str, received_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO events(
          event_id, logical_dedup_key, source_provider, source_transport, coverage,
          channel, action, timestamp_ms, received_at_ms, author_tags_json, urls_json,
          cashtags_json, hashtags_json, mentions_json, media_json, matched_handles_json,
          is_watched, matched_at_ms, raw_json, event_json, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, 'gmgn', 'websocket', 'public', 'twitter', 'tweet', %s, %s,
          %s, %s, %s, %s, %s, %s, %s, false, 0, %s, %s, %s, %s
        )
        """,
        (
            event_id,
            f"dedupe:{event_id}",
            received_at_ms,
            received_at_ms,
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb({}),
            Jsonb({"event_id": event_id}),
            received_at_ms,
            received_at_ms,
        ),
    )


def _insert_radar_row(
    conn: Any,
    *,
    row_id: str,
    event_id: str,
    intent_id: str,
    asset_id: str | None,
    target_id: str,
    symbol: str,
    rank: int,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_rows(
          row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
          lane, rank, intent_id, event_id, asset_id, intent_json, asset_json, primary_venue_json,
          attention_json, resolution_json, market_json, score_json, decision, data_health_json,
          source_event_ids_json, created_at_ms, target_type, target_id, pricefeed_id, target_json,
          price_json, factor_snapshot_json, factor_version
        )
        VALUES (
          %s, 'token-radar-v13-social-attention', '24h', 'all', %s, %s,
          'all', %s, %s, %s, %s, %s, %s, NULL,
          %s, %s, %s, %s, 'watch', %s,
          %s, %s, 'Asset', %s, NULL, %s,
          %s, %s, 'token_factor_snapshot_v3_social_attention'
        )
        """,
        (
            row_id,
            computed_at_ms,
            computed_at_ms,
            rank,
            intent_id,
            event_id,
            asset_id,
            Jsonb({"intent_id": intent_id}),
            Jsonb({"asset_id": asset_id, "symbol": symbol}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({"rank_score": max(0, 100 - rank)}),
            Jsonb({"alpha": "ready"}),
            Jsonb([event_id]),
            computed_at_ms,
            target_id,
            Jsonb({"symbol": symbol, "target_id": target_id}),
            Jsonb({}),
            Jsonb({}),
        ),
    )


def _insert_intent(conn: Any, *, intent_id: str, event_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'unit-test', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, f"intent-key:{intent_id}", observed_at_ms, observed_at_ms),
    )


def _insert_current_identity(conn: Any, *, asset_id: str, symbol: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO asset_identity_current(
          asset_id, canonical_symbol, canonical_name, decimals, identity_confidence,
          selection_reason_codes_json, conflict_count, verified_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, NULL, 'provider_exact', %s, 0, %s, %s)
        """,
        (asset_id, symbol, f"{symbol} Token", Jsonb(["SELECTED_PROVIDER_EXACT"]), observed_at_ms, observed_at_ms),
    )


def _insert_resolution(
    conn: Any,
    *,
    resolution_id: str,
    intent_id: str,
    event_id: str,
    asset_id: str,
    observed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
          target_type, target_id, reason_codes_json, candidate_ids_json, lookup_keys_json,
          record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'UNIQUE_BY_CONTEXT', 'token_radar_v5_identity_resolver',
          'Asset', %s, %s, %s, %s, 'current', true, %s, %s
        )
        """,
        (
            resolution_id,
            intent_id,
            event_id,
            asset_id,
            Jsonb(["UNIT_TEST"]),
            Jsonb([asset_id]),
            Jsonb([f"asset:{asset_id}"]),
            observed_at_ms,
            observed_at_ms,
        ),
    )
