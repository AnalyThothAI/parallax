from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types import PulseEvidencePacket
from tests.postgres_test_utils import (
    connect_postgres_test,
    repository_session_for_connection,
)
from tests.postgres_test_utils import (
    reset_postgres_schema as migrate,
)


def test_pulse_evidence_repository_upserts_and_reconstructs_packet(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_run(conn, run_id="run-1", candidate_id="candidate-1")
        packet = _packet(run_id="run-1", candidate_id="candidate-1", packet_id="packet-1").sealed_copy()

        with repository_session_for_connection(conn) as repos:
            repos.pulse_evidence.upsert_packet(packet)
            by_hash = repos.pulse_evidence.get_packet_by_hash(packet.evidence_packet_hash)
            by_run = repos.pulse_evidence.get_packet_for_run("run-1")
            latest = repos.pulse_evidence.latest_packet_for_candidate("candidate-1")
    finally:
        conn.close()

    assert by_hash == packet
    assert by_run == packet
    assert latest == packet


def test_pulse_evidence_repository_upsert_replaces_summary_without_losing_packet(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_run(conn, run_id="run-1", candidate_id="candidate-1")
        packet = _packet(run_id="run-1", candidate_id="candidate-1", packet_id="packet-1").sealed_copy()
        replacement = packet.model_copy(update={"summary_json": {"status": "replayed"}})

        with repository_session_for_connection(conn) as repos:
            repos.pulse_evidence.upsert_packet(packet)
            repos.pulse_evidence.upsert_packet(replacement)
            stored = repos.pulse_evidence.get_packet_by_hash(packet.evidence_packet_hash)
    finally:
        conn.close()

    assert stored == replacement
    assert stored.summary_json == {"status": "replayed"}


def test_repository_session_exposes_pulse_evidence_repositories(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        with repository_session_for_connection(conn) as repos:
            assert repos.pulse_evidence.get_packet_by_hash("missing") is None
            assert repos.pulse_evidence_sources.list_source_events(["missing"]) == []
    finally:
        conn.close()


def test_pulse_evidence_source_reads_market_tick_for_asset_candidate(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        conn.execute(
            """
            INSERT INTO market_ticks(
              tick_id, target_type, target_id, chain, token_address, exchange, instrument,
              pricefeed_id, source_tier, source_provider, observed_at_ms, received_at_ms,
              price_usd, liquidity_usd, volume_24h_usd, market_cap_usd, holders,
              raw_payload_json, created_at_ms
            )
            VALUES (
              'tick-asset-1', 'chain_token', 'solana:Token111', 'solana', 'Token111', NULL, NULL,
              NULL, 'tier1_ws', 'okx_dex_ws', 1800000000000, 1800000000001,
              0.42, 250000, 12000, 420000, 1000, '{}'::jsonb, 1800000000001
            )
            """,
        )
        conn.commit()
        context = SimpleNamespace(
            target_type="Asset",
            target_id="asset:solana:token:Token111",
            factor_snapshot={
                "subject": {
                    "target_type": "Asset",
                    "target_id": "asset:solana:token:Token111",
                    "target_market_type": "dex",
                }
            },
        )
        with repository_session_for_connection(conn) as repos:
            rows = repos.pulse_evidence_sources.list_market_facts(context, max_age_ms=10_000_000_000)
    finally:
        conn.close()

    assert rows
    assert rows[0]["source_table"] == "market_ticks"
    assert rows[0]["route"] == "meme"
    assert rows[0]["target_market_type"] == "dex"
    assert float(rows[0]["price_usd"]) == 0.42


def test_pulse_evidence_source_reads_cex_market_tick_by_pricefeed_id(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        conn.execute(
            """
            INSERT INTO price_feeds(
              pricefeed_id, feed_type, provider, subject_type, subject_id,
              native_market_id, base_symbol, quote_symbol, status, evidence_level,
              first_seen_at_ms, updated_at_ms
            )
            VALUES (
              'pricefeed:cex:binance:swap:NVDAUSDT', 'swap', 'binance', 'CexToken', 'cex_token:NVDA',
              'NVDAUSDT', 'NVDA', 'USDT', 'canonical', 'provider_exact',
              1800000000000, 1800000000001
            )
            """,
        )
        conn.execute(
            """
            INSERT INTO market_ticks(
              tick_id, target_type, target_id, chain, token_address, exchange, instrument,
              pricefeed_id, source_tier, source_provider, observed_at_ms, received_at_ms,
              price_usd, liquidity_usd, volume_24h_usd, open_interest_usd, market_cap_usd, holders,
              raw_payload_json, created_at_ms
            )
            VALUES (
              'tick-cex-1', 'cex_symbol', 'binance:NVDAUSDT', NULL, NULL, 'binance', 'NVDAUSDT',
              'pricefeed:cex:binance:swap:NVDAUSDT', 'tier2_poll', 'binance_cex_rest',
              1800000000000, 1800000000001, 228.44, NULL, 46036.11, 3200000, NULL, NULL,
              '{}'::jsonb, 1800000000001
            )
            """,
        )
        conn.commit()
        context = SimpleNamespace(
            target_type="CexToken",
            target_id="cex_token:NVDA",
            factor_snapshot={
                "market": {
                    "decision_latest": {
                        "target_type": "CexToken",
                        "target_id": "cex_token:NVDA",
                        "pricefeed_id": "pricefeed:cex:binance:swap:NVDAUSDT",
                    }
                }
            },
        )
        with repository_session_for_connection(conn) as repos:
            rows = repos.pulse_evidence_sources.list_market_facts(context, max_age_ms=10_000_000_000)
    finally:
        conn.close()

    assert rows
    assert rows[0]["route"] == "cex"
    assert rows[0]["target_market_type"] == "cex"
    assert rows[0]["instrument_ref"] == "pricefeed:cex:binance:swap:NVDAUSDT"
    assert float(rows[0]["price_usd"]) == 228.44
    assert float(rows[0]["open_interest_usd"]) == 3_200_000


def test_pulse_evidence_source_returns_last_ready_digest_with_currentness_when_admission_changed(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_narrative_admission(
            conn,
            target_type="chain_token",
            target_id="solana:abc",
            window="24h",
            scope="matched",
            source_event_ids=["event-old", "event-new"],
            source_fingerprint="fingerprint-current",
            source_event_count=2,
            independent_author_count=2,
        )
        _insert_discussion_digest(
            conn,
            digest_id="digest-last-ready",
            target_type="chain_token",
            target_id="solana:abc",
            window="24h",
            scope="matched",
            source_event_ids=["event-old"],
            source_fingerprint="fingerprint-old",
            source_event_count=1,
            independent_author_count=1,
            is_current=False,
        )
        conn.commit()

        with repository_session_for_connection(conn) as repos:
            digest = repos.pulse_evidence_sources.get_current_discussion_digest(
                target_type="chain_token",
                target_id="solana:abc",
                window="24h",
                scope="matched",
                schema_version="narrative_intel_v1",
            )
    finally:
        conn.close()

    assert digest is not None
    assert digest["digest_id"] == "digest-last-ready"
    assert digest["currentness"]["display_status"] == "updating"
    assert digest["currentness"]["reason"] == "digest_updating"
    assert digest["currentness"]["ready_source_fingerprint"] == "fingerprint-old"
    assert digest["currentness"]["current_source_fingerprint"] == "fingerprint-current"
    assert digest["currentness"]["delta_source_event_count"] == 1
    assert digest["currentness"]["delta_independent_author_count"] == 1


def _insert_run(conn: Any, *, run_id: str, candidate_id: str) -> None:
    conn.execute(
        """
        INSERT INTO pulse_agent_jobs(
          job_id, candidate_id, candidate_type, subject_key, target_type, target_id,
          "window", scope, trigger_signature, timeline_signature, context_json,
          priority, status, attempt_count, max_attempts, next_run_at_ms,
          last_error, created_at_ms, updated_at_ms
        )
        VALUES (
          'job-1', %s, 'token_target', 'Asset:asset-1', 'cex_symbol', 'BNB',
          '1h', 'all', 'trigger', 'timeline', '{}'::jsonb,
          10, 'running', 1, 3, 1, NULL, 1, 1
        )
        """,
        (candidate_id,),
    )
    conn.execute(
        """
        INSERT INTO pulse_agent_runs(
          run_id, job_id, candidate_id, provider, model, backend, execution_trace_id,
          workflow_name, agent_name, artifact_version_hash, prompt_version,
          schema_version, runtime_version, runtime_hash, input_hash, output_hash,
          trace_metadata_json, usage_json, latency_ms, status, outcome,
          decision_route, decision_stage_count, request_json, response_json, error,
          started_at_ms, finished_at_ms
        )
        VALUES (
          %s, 'job-1', %s, 'test', 'test-model', 'unit', NULL,
          'pulse_evidence_first', 'decision_maker', 'artifact', 'prompt',
          'schema', 'runtime', 'runtime-hash', 'input-hash', NULL,
          '{}'::jsonb, '{}'::jsonb, 0, 'running', 'running',
          'cex', 0, '{}'::jsonb, NULL, NULL, 1, 1
        )
        """,
        (run_id, candidate_id),
    )
    conn.commit()


def _insert_narrative_admission(
    conn: Any,
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    source_event_ids: list[str],
    source_fingerprint: str,
    source_event_count: int,
    independent_author_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO narrative_admissions(
          admission_id, target_type, target_id, "window", scope, schema_version,
          status, reason, priority, source_event_ids_json, source_fingerprint,
          source_max_received_at_ms, admitted_at_ms, last_seen_at_ms,
          next_semantics_due_at_ms, next_digest_due_at_ms, suppressed_at_ms,
          updated_at_ms, projection_computed_at_ms, source_window_start_ms,
          source_window_end_ms, source_event_count, independent_author_count,
          admission_generation
        )
        VALUES (
          'admission-current', %s, %s, %s, %s, 'narrative_intel_v1',
          'admitted', 'test', 10, %s::jsonb, %s,
          1800000000200, 1800000000000, 1800000000200,
          0, 0, NULL, 1800000000200, 1800000000200, 1800000000000,
          1800000000200, %s, %s, 'test-generation'
        )
        """,
        (
            target_type,
            target_id,
            window,
            scope,
            json.dumps(source_event_ids),
            source_fingerprint,
            source_event_count,
            independent_author_count,
        ),
    )


def _insert_discussion_digest(
    conn: Any,
    *,
    digest_id: str,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    source_event_ids: list[str],
    source_fingerprint: str,
    source_event_count: int,
    independent_author_count: int,
    is_current: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO token_discussion_digests(
          digest_id, target_type, target_id, "window", scope, schema_version,
          model_version, status, is_current, source_fingerprint, label_fingerprint,
          headline_zh, dominant_narratives_json, bull_view_json, bear_view_json,
          stance_mix_json, attention_valence_mix_json, propagation_read_json,
          reflexivity_read_json, watch_triggers_json, invalidation_conditions_json,
          data_gaps_json, semantic_coverage, source_event_count,
          labeled_event_count, independent_author_count, evidence_refs_json,
          model_run_id, computed_at_ms, expires_at_ms, superseded_at_ms,
          epoch_id, epoch_policy_version, source_event_ids_json,
          source_window_start_ms, source_window_end_ms, epoch_closed_at_ms,
          display_current_until_ms, refresh_reason
        )
        VALUES (
          %s, %s, %s, %s, %s, 'narrative_intel_v1',
          'test-model', 'ready', %s, %s, 'labels-old',
          '上一版叙事', %s::jsonb, %s::jsonb, %s::jsonb,
          '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
          '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
          '[]'::jsonb, 0.8, %s,
          %s, %s, %s::jsonb,
          NULL, 1800000000100, 1800003600100, NULL,
          'epoch-old', 'token-narrative-epoch-v1', %s::jsonb,
          1800000000000, 1800000000100, 1800000000100,
          1800003600100, 'material_delta_due'
        )
        """,
        (
            digest_id,
            target_type,
            target_id,
            window,
            scope,
            is_current,
            source_fingerprint,
            json.dumps([{"cluster_key": "last-ready", "summary_zh": "上一版叙事"}]),
            json.dumps({"summary_zh": "多头背景", "evidence_refs": [{"ref_id": "event:event-old"}]}),
            json.dumps({"summary_zh": "风险背景", "evidence_refs": [{"ref_id": "event:event-old"}]}),
            source_event_count,
            source_event_count,
            independent_author_count,
            json.dumps([{"ref_id": "event:event-old"}]),
            json.dumps(source_event_ids),
        ),
    )


def _packet(*, run_id: str, candidate_id: str, packet_id: str) -> PulseEvidencePacket:
    return PulseEvidencePacket(
        evidence_packet_id=packet_id,
        run_id=run_id,
        evidence_packet_hash="",
        schema_version="pulse_evidence_packet_v1",
        candidate_id=candidate_id,
        target_type="cex_symbol",
        target_id="BNB",
        symbol="BNB",
        window="1h",
        scope="all",
        snapshot_at_ms=1_800_000_000_000,
        source_event_ids=("event-1",),
        allowed_evidence_refs=(
            {
                "ref_id": "event:event-1",
                "ref_type": "event",
                "source_table": "events",
                "source_id": "event-1",
                "observed_at_ms": 1_800_000_000_000,
                "summary_zh": "官方账号提及 BNB。",
                "quality": "high",
            },
            {
                "ref_id": "metric:market:price_usd",
                "ref_type": "metric",
                "source_table": "market_ticks",
                "source_id": "tick-1",
                "observed_at_ms": 1_800_000_000_000,
                "summary_zh": "价格可用。",
                "quality": "high",
            },
        ),
        social_evidence={"status": "complete", "event_refs": ("event:event-1",), "summary_zh": "社交证据可用"},
        market_evidence={
            "status": "partial",
            "route": "cex",
            "target_market_type": "cex",
            "price_usd": 600.0,
            "venue_ref": "binance",
            "instrument_ref": "pf-1",
            "observed_at_ms": 1_800_000_000_000,
            "freshness_status": "fresh",
            "source_provider": "binance_cex_rest",
            "pricefeed_id": "pf-1",
        },
        identity_evidence={
            "status": "complete",
            "identity_refs": (),
            "profile_refs": (),
            "summary_zh": "身份证据可用",
        },
        quality_metrics={"ref_count": 2, "high_quality_ref_count": 2, "fresh_ref_count": 2},
        data_gaps=(),
        risk_flags=(),
        source_fingerprints={"factor_snapshot": {"candidate_score": 0.82}},
        admission_context={"candidate_score": 0.82},
        summary_json={"status": "built"},
    )
