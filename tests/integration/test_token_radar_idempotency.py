from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.services.token_radar_projection import (
    PROJECTION_VERSION,
    TokenRadarProjection,
)
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

FIXED_NOW_MS = 1_800_000_000_000
EVENT_MS = FIXED_NOW_MS - 10 * 60 * 1000
ASSET_ADDRESS = "0x1111111111111111111111111111111111111111"


def test_token_radar_rebuild_is_idempotent_from_explicit_repair_dirty_targets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_resolved_radar_source(conn)
        conn.commit()

        projection = TokenRadarProjection(
            repos=repositories_for_connection(
                conn,
                notification_delivery_running_timeout_ms=300_000,
                notification_delivery_stale_running_terminalization_batch_size=100,
            )
        )
        first_enqueued = _enqueue_radar_repair_targets(conn, now_ms=FIXED_NOW_MS)
        first_result = projection.rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("1h",),
            scopes=("all",),
            now_ms=FIXED_NOW_MS,
            limit=10,
            rank_limit=10,
            lease_owner="test_token_radar_idempotency",
        )
        first_rows = _radar_rows(conn)

        second_enqueued = _enqueue_radar_repair_targets(conn, now_ms=FIXED_NOW_MS)
        second_result = projection.rebuild_dirty_targets(
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            windows=("1h",),
            scopes=("all",),
            now_ms=FIXED_NOW_MS,
            limit=10,
            rank_limit=10,
            lease_owner="test_token_radar_idempotency",
        )
        second_rows = _radar_rows(conn)
    finally:
        conn.close()

    assert first_result["status"] == "ready"
    assert second_result["status"] == "idle"
    assert first_enqueued == 1
    assert second_enqueued == 0
    assert first_result["rows_written"] >= 1
    assert second_result["rows_written"] == 0
    assert first_rows, "seeded current facts should produce at least one radar row"
    assert _semantic_rows(first_rows) == _semantic_rows(second_rows)


def _enqueue_radar_repair_targets(conn: Any, *, now_ms: int) -> int:
    repos = repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
    return int(
        repos.token_radar_dirty_targets.enqueue_recent_resolved_targets(
            since_ms=now_ms - 60 * 60 * 1000,
            now_ms=now_ms,
            limit=10,
            reason="integration_catch_up",
            commit=True,
        )
    )


def _radar_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          lane,
          rank,
          intent_id,
          event_id,
          target_type,
          target_id,
          decision,
          factor_snapshot_json,
          data_health_json,
          source_event_ids_json
        FROM token_radar_current_rows
        WHERE projection_version = %s
          AND "window" = '1h'
          AND scope = 'all'
        ORDER BY lane, rank, target_type, target_id, intent_id
        """,
        (PROJECTION_VERSION,),
    ).fetchall()
    return [dict(row) for row in rows]


def _semantic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_json_stable(row) for row in rows]


def _json_stable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _seed_resolved_radar_source(conn: Any) -> None:
    event_id = "event-radar-idempotent"
    intent_id = "intent-radar-idempotent"
    resolution_id = "resolution-radar-idempotent"

    EvidenceRepository(conn).insert_event(
        make_event(
            event_id=event_id,
            author_handle="signal_builder",
            text="$IDEMP fresh onchain momentum",
            received_at_ms=EVENT_MS,
            is_watched=True,
        ),
        is_watched=True,
    )
    _insert_intent(conn, intent_id=intent_id, event_id=event_id, observed_at_ms=EVENT_MS)
    asset_id = _insert_asset(conn, observed_at_ms=EVENT_MS)
    _insert_current_identity(conn, asset_id=asset_id, observed_at_ms=EVENT_MS)
    _insert_resolution(
        conn,
        resolution_id=resolution_id,
        intent_id=intent_id,
        event_id=event_id,
        asset_id=asset_id,
        observed_at_ms=EVENT_MS,
    )
    _insert_market_tick(
        conn,
        tick_id="tick-radar-idempotent-anchor",
        observed_at_ms=EVENT_MS,
        received_at_ms=EVENT_MS,
    )
    _insert_market_tick(
        conn,
        tick_id="tick-radar-idempotent-latest",
        observed_at_ms=FIXED_NOW_MS - 30_000,
        received_at_ms=FIXED_NOW_MS - 30_000,
    )
    _insert_enriched_event(
        conn,
        event_id=event_id,
        intent_id=intent_id,
        resolution_id=resolution_id,
        tick_id="tick-radar-idempotent-anchor",
        tick_observed_at_ms=EVENT_MS,
        t_event_ms=EVENT_MS,
    )


def _insert_asset(conn: Any, *, observed_at_ms: int) -> str:
    asset = RegistryRepository(conn).upsert_chain_asset(
        chain_id="eip155:1",
        address=ASSET_ADDRESS,
        observed_at_ms=observed_at_ms,
        status="candidate",
        commit=False,
    )
    return str(asset["asset_id"])


def _insert_intent(conn: Any, *, intent_id: str, event_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, display_symbol,
          display_name, intent_status, intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, 'symbol:IDEMP', 'integration-test', 'IDEMP',
                'Idempotency Token', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, observed_at_ms, observed_at_ms),
    )


def _insert_current_identity(conn: Any, *, asset_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO asset_identity_current(
          asset_id, canonical_symbol, canonical_name, decimals, identity_confidence,
          selection_reason_codes_json, conflict_count, verified_at_ms, updated_at_ms
        )
        VALUES (%s, 'IDEMP', 'Idempotency Token', 18, 'provider_exact',
                %s, 0, %s, %s)
        """,
        (asset_id, Jsonb(["SELECTED_PROVIDER_EXACT"]), observed_at_ms, observed_at_ms),
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
          target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
          lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'UNIQUE_BY_CONTEXT', %s,
          'Asset', %s, NULL, %s, %s, %s,
          'current', true, %s, %s
        )
        """,
        (
            resolution_id,
            intent_id,
            event_id,
            TOKEN_RADAR_RESOLVER_POLICY_VERSION,
            asset_id,
            Jsonb(["INTEGRATION_TEST"]),
            Jsonb([asset_id]),
            Jsonb(["symbol:IDEMP", f"address:eip155:1:{ASSET_ADDRESS.lower()}"]),
            observed_at_ms,
            observed_at_ms,
        ),
    )


def _insert_market_tick(conn: Any, *, tick_id: str, observed_at_ms: int, received_at_ms: int) -> None:
    target_id = f"eip155:1:{ASSET_ADDRESS.lower()}"
    conn.execute(
        """
        INSERT INTO market_ticks(
          tick_id, target_type, target_id, chain, token_address,
          exchange, instrument, pricefeed_id, source_tier, source_provider,
          observed_at_ms, received_at_ms, price_usd, liquidity_usd,
          volume_24h_usd, market_cap_usd, holders, raw_payload_json, created_at_ms
        )
        VALUES (
          %s, 'chain_token', %s, 'eip155:1', %s,
          NULL, NULL, NULL, 'tier3_inline', 'okx_dex_rest',
          %s, %s, 1.25, 100000, 500000, 1000000, 1000, %s, %s
        )
        """,
        (tick_id, target_id, ASSET_ADDRESS.lower(), observed_at_ms, received_at_ms, Jsonb({}), received_at_ms),
    )


def _insert_enriched_event(
    conn: Any,
    *,
    event_id: str,
    intent_id: str,
    resolution_id: str,
    tick_id: str,
    tick_observed_at_ms: int,
    t_event_ms: int,
) -> None:
    target_id = f"eip155:1:{ASSET_ADDRESS.lower()}"
    conn.execute(
        """
        INSERT INTO enriched_events(
          event_id, intent_id, resolution_id, target_type, target_id,
          t_event_ms, tick_observed_at_ms, tick_id, tick_lag_ms, capture_method, capture_reason, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'chain_token', %s,
          %s, %s, %s, 0, 'tier3_inline', 'integration_seed', %s
        )
        """,
        (event_id, intent_id, resolution_id, target_id, t_event_ms, tick_observed_at_ms, tick_id, t_event_ms),
    )
