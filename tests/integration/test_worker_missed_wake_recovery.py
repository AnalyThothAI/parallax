from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    PulseTriggerThresholds,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateThresholds
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

FIXED_NOW_MS = 1_800_000_000_000
EVENT_MS = FIXED_NOW_MS - 10 * 60 * 1000
ASSET_ADDRESS = "0x2222222222222222222222222222222222222222"


def test_token_radar_projection_worker_catches_up_from_db_without_wake(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_resolved_radar_source(conn)
        conn.commit()

        worker = TokenRadarProjectionWorker(
            name="token_radar_projection",
            settings=_radar_settings(),
            db=_DB(conn),
            telemetry=object(),
        )

        catch_up_result = asyncio.run(worker.run_once(now_ms=FIXED_NOW_MS))
        result = asyncio.run(worker.run_once(now_ms=FIXED_NOW_MS))

        assert catch_up_result.failed == 0
        assert catch_up_result.processed == 0
        assert catch_up_result.notes["catch_up_enqueued"] >= 1
        assert result.failed == 0
        assert result.processed >= 1
        assert result.notes["source_rows"] >= 1
        assert result.notes["rows_written"] >= 1
        row = conn.execute(
            """
            SELECT count(*) AS count
            FROM token_radar_current_rows
            WHERE "window" = '1h' AND scope = 'all'
            """,
        ).fetchone()
        coverage = conn.execute(
            """
            SELECT status, source_rows, row_count
            FROM token_radar_projection_coverage
            WHERE "window" = '1h' AND scope = 'all'
            """,
        ).fetchone()
        assert row["count"] >= 1
        assert coverage["status"] == "ready"
        assert coverage["source_rows"] >= 1
        assert coverage["row_count"] >= 1
    finally:
        conn.close()


def test_pulse_candidate_worker_catches_up_from_persisted_token_radar_without_wake(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_resolved_radar_source(conn)
        conn.commit()
        radar_worker = TokenRadarProjectionWorker(
            name="token_radar_projection",
            settings=_radar_settings(),
            db=_DB(conn),
            telemetry=object(),
        )
        catch_up_result = asyncio.run(radar_worker.run_once(now_ms=FIXED_NOW_MS))
        radar_result = asyncio.run(radar_worker.run_once(now_ms=FIXED_NOW_MS))
        assert catch_up_result.notes["catch_up_enqueued"] >= 1
        assert radar_result.notes["rows_written"] >= 1

        pulse_worker = PulseCandidateWorker(
            name="pulse_candidate",
            settings=SimpleNamespace(
                enabled=True,
                interval_seconds=0,
                soft_timeout_seconds=1,
                hard_timeout_seconds=2,
                windows=("1h",),
                scopes=("all",),
                batch_size=10,
                max_attempts=3,
            ),
            db=_DB(conn),
            telemetry=object(),
            decision_client=_FakeDecisionClient(),
            trigger_thresholds=PulseTriggerThresholds(min_rank_score=0),
            gate_thresholds=PulseGateThresholds(
                trade_candidate_min=72,
                token_watch_min=1,
                high_info_rejection_min=30,
                high_conviction_min=78,
            ),
        )

        scan = pulse_worker.scan_triggers_once(now_ms=FIXED_NOW_MS)

        assert scan["asset_seen"] >= 1
        assert scan["asset_enqueued"] >= 1
        job = conn.execute(
            """
            SELECT status
            FROM pulse_agent_jobs
            ORDER BY created_at_ms DESC
            LIMIT 1
            """,
        ).fetchone()
        assert job is not None
        assert job["status"] == "pending"
        assert _FakeDecisionClient.calls == 0
    finally:
        conn.close()


class _DB:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    @contextmanager
    def worker_session(self, name: str, **_: Any):
        yield repositories_for_connection(self.conn)


class _FakeDecisionClient:
    calls = 0

    async def decide(self, *_: Any, **__: Any) -> Any:
        type(self).calls += 1
        raise AssertionError("scan_triggers_once should not call the decision client")


def _radar_settings() -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        interval_seconds=0,
        soft_timeout_seconds=1,
        hard_timeout_seconds=2,
        windows=("1h",),
        scopes=("all",),
        hot_windows=(),
        cold_interval_seconds=0,
        batch_size=10,
        statement_timeout_seconds=5,
    )


def _seed_resolved_radar_source(conn: Any) -> None:
    event_id = "event-worker-missed-wake"
    intent_id = "intent-worker-missed-wake"
    resolution_id = "resolution-worker-missed-wake"

    EvidenceRepository(conn).insert_event(
        make_event(
            event_id=event_id,
            author_handle="missed_wake_builder",
            text="$WAKE fresh onchain momentum",
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
        tick_id="tick-worker-missed-wake-anchor",
        observed_at_ms=EVENT_MS,
        received_at_ms=EVENT_MS,
    )
    _insert_market_tick(
        conn,
        tick_id="tick-worker-missed-wake-latest",
        observed_at_ms=FIXED_NOW_MS - 30_000,
        received_at_ms=FIXED_NOW_MS - 30_000,
    )
    _insert_enriched_event(
        conn,
        event_id=event_id,
        intent_id=intent_id,
        resolution_id=resolution_id,
        tick_id="tick-worker-missed-wake-anchor",
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
        VALUES (%s, %s, 'symbol:WAKE', 'integration-test', 'WAKE',
                'Wake Recovery Token', 'active', 1.0, %s, %s)
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
        VALUES (%s, 'WAKE', 'Wake Recovery Token', 18, 'provider_exact',
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
            Jsonb(["symbol:WAKE", f"address:eip155:1:{ASSET_ADDRESS.lower()}"]),
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
    t_event_ms: int,
) -> None:
    target_id = f"eip155:1:{ASSET_ADDRESS.lower()}"
    conn.execute(
        """
        INSERT INTO enriched_events(
          event_id, intent_id, resolution_id, target_type, target_id,
          t_event_ms, tick_observed_at_ms, tick_id, tick_lag_ms,
          capture_method, capture_reason, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'chain_token', %s,
          %s, %s, %s, 0, 'tier3_inline', 'integration_seed', %s
        )
        """,
        (event_id, intent_id, resolution_id, target_id, t_event_ms, t_event_ms, tick_id, t_event_ms),
    )
