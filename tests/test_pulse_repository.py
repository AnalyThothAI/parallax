from __future__ import annotations

import base64
import json
from typing import Any

from gmgn_twitter_intel.storage import pulse_repository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.pulse_repository import PulseRepository
from gmgn_twitter_intel.storage.repository_session import repositories_for_connection
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_enqueue_job_and_claim_due_job_marks_running(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-claim",
            candidate_id="candidate-claim",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-a",
            timeline_signature="timeline-a",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        assert repo.claim_due_job(now_ms=999) is None
        claimed = repo.claim_due_job(now_ms=1_000)
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["job_id"] == "job-claim"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["updated_at_ms"] == 1_000


def test_mark_job_failed_retries_then_dead_and_succeeded_sets_done(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-fail",
            candidate_id="candidate-fail",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-fail",
            timeline_signature="timeline-fail",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        first_claim = repo.claim_due_job(now_ms=1_000)
        first_failure = repo.mark_job_failed(first_claim, "model unavailable", now_ms=2_000)
        second_claim = repo.claim_due_job(now_ms=first_failure["next_run_at_ms"])
        second_failure = repo.mark_job_failed(second_claim, "model unavailable again", now_ms=3_000)

        repo.enqueue_job(
            job_id="job-success",
            candidate_id="candidate-success",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-success",
            timeline_signature="timeline-success",
            priority=5,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        success_claim = repo.claim_due_job(now_ms=1_000)
        success = repo.mark_job_succeeded("job-success", now_ms=4_000)
    finally:
        conn.close()

    assert first_failure is not None
    assert first_failure["status"] == "failed"
    assert first_failure["last_error"] == "model unavailable"
    assert second_failure is not None
    assert second_failure["status"] == "dead"
    assert success_claim is not None
    assert success_claim["attempt_count"] == 1
    assert success is not None
    assert success["status"] == "done"
    assert success["last_error"] is None


def test_reenqueue_dead_job_resets_attempts_and_is_claimable(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-reenqueue",
            candidate_id="candidate-reenqueue",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-old",
            timeline_signature="timeline-old",
            priority=10,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        first_claim = repo.claim_due_job(now_ms=1_000)
        dead = repo.mark_job_failed(first_claim, "exhausted", now_ms=1_100)

        repo.enqueue_job(
            job_id="job-reenqueue-new",
            candidate_id="candidate-reenqueue",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-new",
            timeline_signature="timeline-new",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_200,
            now_ms=1_200,
        )
        claimed = repo.claim_due_job(now_ms=1_200)
    finally:
        conn.close()

    assert dead is not None
    assert dead["status"] == "dead"
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["max_attempts"] == 2
    assert claimed["trigger_signature"] == "trigger-new"
    assert claimed["timeline_signature"] == "timeline-new"


def test_claim_due_job_recovers_stale_running_without_exceeding_max_attempts(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn, running_timeout_ms=100)
        repo.enqueue_job(
            job_id="job-stale",
            candidate_id="candidate-stale",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale",
            timeline_signature="timeline-stale",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        first_claim = repo.claim_due_job(now_ms=1_000)
        early_reclaim = repo.claim_due_job(now_ms=1_050)
        stale_reclaim = repo.claim_due_job(now_ms=1_201)
    finally:
        conn.close()

    assert first_claim is not None
    assert first_claim["status"] == "running"
    assert first_claim["attempt_count"] == 1
    assert early_reclaim is None
    assert stale_reclaim is not None
    assert stale_reclaim["status"] == "running"
    assert stale_reclaim["attempt_count"] == 2


def test_claim_due_job_marks_exhausted_stale_running_dead(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn, running_timeout_ms=100)
        enqueued = repo.enqueue_job(
            job_id="job-stale-dead",
            candidate_id="candidate-stale-dead",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale-dead",
            timeline_signature="timeline-stale-dead",
            priority=10,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        first_claim = repo.claim_due_job(now_ms=1_000)
        stale_reclaim = repo.claim_due_job(now_ms=1_201)
        stored = conn.execute(
            "SELECT * FROM pulse_agent_jobs WHERE job_id = %s",
            (enqueued["job_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert first_claim is not None
    assert first_claim["attempt_count"] == 1
    assert stale_reclaim is None
    assert stored is not None
    assert stored["status"] == "dead"


def test_insert_agent_run_and_finish_agent_run_store_audit_json(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-run",
            candidate_id="candidate-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-run",
            timeline_signature="timeline-run",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        run = repo.insert_agent_run(
            run_id="run-1",
            job_id="job-run",
            candidate_id="candidate-run",
            provider="openai",
            model="gpt-5-mini",
            sdk_trace_id="trace-1",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_agent",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-prompt-v1",
            schema_version="pulse-schema-v1",
            input_hash="input-hash",
            trace_metadata_json={"candidate_id": "candidate-run"},
            usage_json={"input_tokens": 10},
            status="running",
            request_json={"messages": [{"role": "user", "content": "inspect"}]},
            started_at_ms=1_100,
        )
        finished = repo.finish_agent_run(
            "run-1",
            "done",
            response_json={"verdict": "token_watch"},
            output_hash="output-hash",
            usage_json={"output_tokens": 20},
            finished_at_ms=1_350,
        )
    finally:
        conn.close()

    assert run["request_json"] == {"messages": [{"role": "user", "content": "inspect"}]}
    assert run["trace_metadata_json"] == {"candidate_id": "candidate-run"}
    assert finished is not None
    assert finished["status"] == "done"
    assert finished["response_json"] == {"verdict": "token_watch"}
    assert finished["usage_json"] == {"output_tokens": 20}
    assert finished["output_hash"] == "output-hash"
    assert finished["latency_ms"] == 250


def test_upsert_candidate_and_list_candidates_contract_filters_and_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-newer", updated_at_ms=3_000))
        repo.upsert_candidate(
            **_candidate_payload("candidate-older", symbol="PEPE", subject_key="pepewhale", updated_at_ms=2_000)
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-blocked",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=1_000,
            )
        )

        first_page = repo.list_candidates(window="1h", scope="global", status="token_watch", limit=1)
        second_page = repo.list_candidates(
            window="1h",
            scope="global",
            status="token_watch",
            limit=1,
            cursor=first_page["next_cursor"],
        )
        blocked = repo.list_candidates(window="1h", scope="global", status="blocked_low_information", limit=10)
        handle_filtered = repo.list_candidates(window="1h", scope="global", handle="@pepewhale", limit=10)
        query_filtered = repo.list_candidates(window="1h", scope="global", q="pep", limit=10)
    finally:
        conn.close()

    assert [item["candidate_id"] for item in first_page["items"]] == ["candidate-newer"]
    assert first_page["items"][0]["thesis_json"] == {"summary": "watch social acceleration"}
    assert first_page["items"][0]["gate_reasons_json"] == ["fresh_attention"]
    assert second_page["items"][0]["candidate_id"] == "candidate-older"
    assert second_page["next_cursor"] is None
    assert [item["candidate_id"] for item in blocked["items"]] == ["candidate-blocked"]
    assert [item["candidate_id"] for item in handle_filtered["items"]] == ["candidate-older"]
    assert [item["candidate_id"] for item in query_filtered["items"]] == ["candidate-older"]


def test_handle_filter_matches_candidate_source_event_author(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(
            make_event("event-watch", author_handle="traderpow", received_at_ms=1_000),
            is_watched=True,
        )
        EvidenceRepository(conn).insert_event(
            make_event("event-other", author_handle="otheralpha", received_at_ms=1_100),
            is_watched=True,
        )
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-watch-source",
                symbol="PEPE",
                subject_key="PEPE",
                source_event_ids=["event-watch"],
                evidence_event_ids=["event-watch"],
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-other-source",
                symbol="BONK",
                subject_key="BONK",
                source_event_ids=["event-other"],
                evidence_event_ids=["event-other"],
                updated_at_ms=2_000,
            )
        )

        filtered = repo.list_candidates(window="1h", scope="global", handle="@traderpow", limit=10)
        summary = repo.pulse_summary(window="1h", scope="global", handle="@traderpow")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in filtered["items"]] == ["candidate-watch-source"]
    assert summary["candidate_count"] == 1
    assert summary["summary"]["token_watch"] == 1


def test_candidate_handle_filter_clause_checks_source_event_authors() -> None:
    clause, params = pulse_repository._candidate_handle_filter_clause("candidate", "@TraderPow")

    assert "candidate.subject_key" in clause
    assert "candidate.source_event_ids_json" in clause
    assert "candidate.evidence_event_ids_json" in clause
    assert "jsonb_array_elements_text" in clause
    assert "events" in clause
    assert "social_event_extractions" in clause
    assert params == ["traderpow", "traderpow"]


def test_list_candidates_ignores_malformed_structured_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-cursor", updated_at_ms=3_000))
        cursor = base64.urlsafe_b64encode(
            json.dumps({"updated_at_ms": {}, "candidate_id": "x"}).encode("utf-8")
        ).decode("ascii")

        result = repo.list_candidates(window="1h", scope="global", limit=10, cursor=cursor)
        invalid_base64 = repo.list_candidates(window="1h", scope="global", limit=10, cursor="not-a-valid-cursor")
        non_ascii = repo.list_candidates(window="1h", scope="global", limit=10, cursor="☃")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in result["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in invalid_base64["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in non_ascii["items"]] == ["candidate-cursor"]


def test_list_candidates_preserves_source_seed_theme_and_risk_enum_semantics(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-theme-source",
                candidate_type="source_seed",
                pulse_status="theme_watch",
                verdict="theme_watch",
                score_band="speculative",
                social_phase="seed",
                narrative_type="ecosystem_spillover",
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-risk-source",
                candidate_type="source_seed",
                pulse_status="risk_rejected_high_info",
                verdict="risk_rejected_high_info",
                score_band="speculative",
                social_phase="unknown",
                narrative_type="risk_event",
                updated_at_ms=2_000,
            )
        )

        theme = repo.list_candidates(window="1h", scope="global", status="theme_watch", limit=10)
        risk = repo.list_candidates(window="1h", scope="global", status="risk_rejected_high_info", limit=10)
    finally:
        conn.close()

    assert theme["next_cursor"] is None
    assert risk["next_cursor"] is None
    assert [
        {
            "candidate_id": item["candidate_id"],
            "candidate_type": item["candidate_type"],
            "pulse_status": item["pulse_status"],
            "verdict": item["verdict"],
            "score_band": item["score_band"],
            "social_phase": item["social_phase"],
            "narrative_type": item["narrative_type"],
        }
        for item in theme["items"]
    ] == [
        {
            "candidate_id": "candidate-theme-source",
            "candidate_type": "source_seed",
            "pulse_status": "theme_watch",
            "verdict": "theme_watch",
            "score_band": "speculative",
            "social_phase": "seed",
            "narrative_type": "ecosystem_spillover",
        }
    ]
    assert [
        {
            "candidate_id": item["candidate_id"],
            "candidate_type": item["candidate_type"],
            "pulse_status": item["pulse_status"],
            "verdict": item["verdict"],
            "score_band": item["score_band"],
            "social_phase": item["social_phase"],
            "narrative_type": item["narrative_type"],
        }
        for item in risk["items"]
    ] == [
        {
            "candidate_id": "candidate-risk-source",
            "candidate_type": "source_seed",
            "pulse_status": "risk_rejected_high_info",
            "verdict": "risk_rejected_high_info",
            "score_band": "speculative",
            "social_phase": "unknown",
            "narrative_type": "risk_event",
        }
    ]


def test_get_health_counts_candidates_blocked_low_information_and_dead_jobs(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-trade",
                pulse_status="trade_candidate",
                score_band="high_conviction",
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-low-info",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=2_000,
            )
        )
        repo.enqueue_job(
            job_id="job-dead",
            candidate_id="candidate-dead-job",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-dead",
            timeline_signature="timeline-dead",
            priority=1,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        claimed = repo.claim_due_job(now_ms=1_000)
        repo.mark_job_failed(claimed, "exhausted", now_ms=1_500)
        health = repo.get_health(window="1h", scope="global")
    finally:
        conn.close()

    assert health["candidate_count"] == 2
    assert health["blocked_low_information_count"] == 1
    assert health["dead_job_count"] == 1


def test_playbook_snapshot_and_outcome_use_explicit_spec_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-playbook", updated_at_ms=3_000))
        snapshot = repo.upsert_playbook_snapshot(
            playbook_id="playbook-1",
            candidate_id="candidate-playbook",
            target_type="cex_token",
            target_id="binance:SOLUSDT",
            horizon="6h",
            decision_time_ms=3_100,
            playbook_status="pending_confirmation",
            side="long",
            setup={"trigger": "social ignition"},
            confirmation={"price": "breakout"},
            invalidation={"social": "attention fades"},
            risk={"max_loss": 0.05},
            entry_market={"price": 145.2},
            playbook_version="playbook-v1",
            outcome_status="pending",
            created_at_ms=3_100,
        )
        outcome = repo.upsert_playbook_outcome(
            playbook_id="playbook-1",
            settled_at_ms=4_000,
            actual_return=0.12,
            benchmark_return=0.04,
            abnormal_return=0.08,
            max_favorable_excursion=0.15,
            max_adverse_excursion=-0.03,
            confirmation_hit=True,
            invalidation_hit=False,
            outcome={"label": "worked"},
            created_at_ms=4_000,
        )
    finally:
        conn.close()

    assert snapshot["playbook_id"] == "playbook-1"
    assert snapshot["setup_json"] == {"trigger": "social ignition"}
    assert snapshot["confirmation_json"] == {"price": "breakout"}
    assert snapshot["invalidation_json"] == {"social": "attention fades"}
    assert snapshot["risk_json"] == {"max_loss": 0.05}
    assert snapshot["entry_market_json"] == {"price": 145.2}
    assert outcome["playbook_id"] == "playbook-1"
    assert outcome["actual_return"] == 0.12
    assert outcome["confirmation_hit"] is True
    assert outcome["outcome_json"] == {"label": "worked"}


def test_repository_session_exposes_pulse_repository(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(conn)
    finally:
        conn.close()

    assert isinstance(repos.pulse, PulseRepository)


def _candidate_payload(
    candidate_id: str,
    *,
    symbol: str = "SOL",
    subject_key: str = "toly",
    candidate_type: str = "token_target",
    pulse_status: str = "token_watch",
    verdict: str | None = None,
    score_band: str = "watch",
    social_phase: str = "ignition",
    narrative_type: str = "direct_token",
    source_event_ids: list[str] | None = None,
    evidence_event_ids: list[str] | None = None,
    updated_at_ms: int,
) -> dict[str, Any]:
    resolved_verdict = verdict if verdict is not None else pulse_status
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "subject_key": subject_key,
        "target_type": "asset",
        "target_id": f"asset:{symbol.lower()}",
        "symbol": symbol,
        "window": "1h",
        "scope": "global",
        "pulse_status": pulse_status,
        "verdict": resolved_verdict,
        "social_phase": social_phase,
        "narrative_type": narrative_type,
        "candidate_score": 0.82,
        "score_band": score_band,
        "trigger_signature": f"trigger:{candidate_id}",
        "timeline_signature": f"timeline:{candidate_id}",
        "thesis_json": {"summary": "watch social acceleration"},
        "radar_score_json": {"score": 0.82},
        "market_context_json": {"regime": "risk_on"},
        "gate_reasons_json": ["fresh_attention"],
        "risk_reasons_json": ["thin_liquidity"],
        "evidence_event_ids_json": evidence_event_ids or ["event-1"],
        "source_event_ids_json": source_event_ids or ["event-1"],
        "pulse_version": "pulse-v1",
        "gate_version": "gate-v1",
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
        "created_at_ms": updated_at_ms - 100,
        "updated_at_ms": updated_at_ms,
    }
