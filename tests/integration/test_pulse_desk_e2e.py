from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from psycopg import errors as psycopg_errors
from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.notifications.services.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import fetch_evidence_event_urls
from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_evidence_repository import PulseEvidenceRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_read_repository import PulseReadRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BearCaseMemo,
    BullBearView,
    EvidenceClaim,
    FinalDecision,
    SignalAnalystMemo,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation
from gmgn_twitter_intel.platform.config.settings import Settings
from tests.postgres_test_utils import connect_postgres_test, reset_postgres_schema
from tests.unit.test_pulse_candidate_worker import (
    NOW_MS,
    FakeDB,
    FakeRepos,
    _factor_snapshot,
    _radar_row,
    _settings,
    _timeline_row,
)


@pytest.mark.integration
def test_pulse_agent_desk_synthetic_worker_surface_smoke() -> None:
    """Synthetic fake-repository smoke; real Postgres dataflow coverage is below."""

    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    client = _ResearchCommitteeClient()
    worker = PulseCandidateWorker(
        name="pulse_candidate",
        settings=_settings(),
        db=FakeDB(repos),
        telemetry=object(),
        decision_client=client,
    )

    scan = worker.scan_triggers_once(now_ms=NOW_MS)
    run = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert scan["asset_enqueued"] == 1
    assert run["processed"] == 1

    candidate = repos.pulse_candidates.candidate_upserts[0]
    decision = candidate["decision_json"]
    assert {"narrative_archetype", "narrative_thesis_zh", "bull_view", "bear_view", "playbook"} <= set(decision)
    assert decision["evidence_event_urls"] == {"event-1": "https://x.com/toly/status/1"}
    steps_by_stage = {step["stage"]: step for step in repos.pulse_runs.agent_run_steps}
    assert set(steps_by_stage) == _RESEARCH_COMMITTEE_STAGES
    assert steps_by_stage["evidence_pack"]["response_json"]["evidence_packet_hash"] == candidate["evidence_packet_hash"]
    assert "tool_calls" not in steps_by_stage["signal_analyst"]["input_json"]

    pulse_read = _PulseReadAdapter(repos)
    detail = SignalPulseService(pulse_read=pulse_read, pulse_runs=pulse_read).candidate(
        candidate_id=candidate["candidate_id"]
    )
    assert detail is not None
    assert detail["decision"]["playbook"]["has_playbook"] is True
    assert detail["decision"]["bull_view"]["strength"] == "moderate"
    assert detail["stages"]["signal_analyst"]["response"]["what_changed_zh"] == "基于封闭证据包的正向信号完成。"
    assert detail["stages"]["risk_portfolio_judge"]["response"]["recommendation"] == "trade_candidate"

    notifications = _notification_engine(pulse_read).evaluate(now_ms=NOW_MS)
    pulse_notifications = [item for item in notifications if item.rule_id == "signal_pulse_candidate"]
    assert len(pulse_notifications) == 1
    body = pulse_notifications[0].body
    assert "叙事" in body
    assert "看多" in body
    assert "看空" in body
    assert "Playbook" in body
    assert "https://x.com/toly/status/1" in body


@pytest.mark.integration
def test_pulse_agent_desk_real_postgres_read_model_and_notification_dataflow(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        worker = PulseCandidateWorker(
            name="pulse_candidate",
            settings=_settings(),
            db=_RealWorkerDb(
                conn=conn,
                token_radar_rows=[_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))],
                token_target_rows=[_timeline_row("event-1", NOW_MS - 1_000)],
            ),
            telemetry=object(),
            decision_client=_ResearchCommitteeClient(),
        )
        _insert_event(
            conn,
            event_id="event-1",
            received_at_ms=NOW_MS - 1_000,
            canonical_url="https://x.com/toly/status/1",
        )
        conn.commit()

        scan = worker.scan_triggers_once(now_ms=NOW_MS)
        run = worker.process_due_jobs_once(now_ms=NOW_MS)
        assert scan["asset_enqueued"] == 1
        assert run["processed"] == 1

        pulse_read = PulseReadRepository(conn)
        pulse_runs = PulseRunsRepository(conn)
        page = pulse_read.list_candidates(window="1h", scope="all", status="trade_candidate", limit=10)
        assert len(page["items"]) == 1
        stored = page["items"][0]
        ids = {"candidate_id": stored["candidate_id"], "run_id": stored["agent_run_id"]}

        decision = stored["decision_json"]
        assert {"narrative_archetype", "narrative_thesis_zh", "bull_view", "bear_view", "playbook"} <= set(decision)

        steps = pulse_runs.list_agent_run_steps(ids["run_id"])
        steps_by_stage = {step["stage"]: step for step in steps}
        assert set(steps_by_stage) == _RESEARCH_COMMITTEE_STAGES
        packet_step = steps_by_stage["evidence_pack"]
        assert packet_step["response_json"]["evidence_packet_hash"] == stored["evidence_packet_hash"]
        assert "tool_calls" not in steps_by_stage["signal_analyst"]["input_json"]

        detail = SignalPulseService(pulse_read=pulse_read, pulse_runs=pulse_runs).candidate(
            candidate_id=ids["candidate_id"]
        )
        assert detail is not None
        assert detail["decision"]["playbook"]["has_playbook"] is True
        assert detail["decision"]["bull_view"]["strength"] == "moderate"
        assert detail["stages"]["signal_analyst"]["response"]["what_changed_zh"] == "基于封闭证据包的正向信号完成。"
        assert detail["stages"]["risk_portfolio_judge"]["response"]["recommendation"] == "trade_candidate"

        notifications = _notification_engine(pulse_read).evaluate(now_ms=NOW_MS)
        pulse_notifications = [item for item in notifications if item.rule_id == "signal_pulse_candidate"]
        assert len(pulse_notifications) == 1
        notification = pulse_notifications[0]
        signature = notification.payload["notification_signature"]
        assert signature.startswith("sha256:")
        external_identity = notification.payload.get("external_push_signature") or "in_app"
        assert notification.dedup_key == f"signal_pulse_candidate:{signature}:{external_identity}"
        body = notification.body
        assert "叙事" in body
        assert "看多" in body
        assert "看空" in body
        assert "Playbook" in body
        assert "https://x.com/toly/status/1" in body
    finally:
        conn.close()


@pytest.mark.integration
def test_pulse_agent_tool_queries_read_seeded_events_through_read_only_connection(tmp_path) -> None:
    write_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(write_conn)
        _insert_event(
            write_conn,
            event_id="event-readonly",
            received_at_ms=NOW_MS - 1_000,
            canonical_url="https://x.com/toly/status/read-only",
        )
        write_conn.commit()
    finally:
        write_conn.close()

    read_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=True)
    try:
        with pytest.raises(psycopg_errors.ReadOnlySqlTransaction):
            read_conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at_ms) VALUES (%s, %s, %s)",
                (999_999_999, "read-only-check", NOW_MS),
            )
        read_conn.rollback()

        urls = fetch_evidence_event_urls(_SingleConnectionPool(read_conn), event_ids=["event-readonly"])
        assert urls == {"event-readonly": "https://x.com/toly/status/read-only"}
    finally:
        read_conn.close()


_RESEARCH_COMMITTEE_STAGES = {
    "evidence_pack",
    "evidence_completeness_gate",
    "signal_analyst",
    "bear_case",
    "claim_verifier",
    "risk_portfolio_judge",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
}


class _ResearchCommitteeClient:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake-research-committee"

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        scope: str | None = None,
    ) -> AgentCapacityReservation:
        return AgentCapacityReservation(lane=lane, acquired=True)

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "backend": "fake",
            "sdk_trace_id": f"trace-{run_id}",
            "workflow_name": "pulse-test",
            "agent_name": "pulse-test-agent",
            "prompt_version": "pulse-decision-prompt-v2",
            "schema_version": "pulse-decision-v2",
            "artifact_version_hash": self.artifact_version_hash,
            "runtime_version": runtime_manifest["runtime_version"],
            "runtime_hash": "sha256:e2e",
            "trace_metadata": {"candidate_id": context["candidate_id"], "route": route},
            "input_hash": "input-e2e",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> PulseDecisionResult:
        allowed_refs = [
            str(ref.get("ref_id"))
            for ref in context.get("evidence_packet", {}).get("allowed_evidence_refs", [])
            if isinstance(ref, dict) and ref.get("ref_id")
        ]
        supporting_refs = tuple(ref for ref in allowed_refs if ref.startswith("event:"))[:1]
        risk_refs = tuple(ref for ref in allowed_refs if ref.startswith("market:"))[:1]
        signal_memo = SignalAnalystMemo(
            bull_claims=(
                EvidenceClaim(
                    claim="独立作者扩散和关注账号确认共同支撑继续观察。",
                    evidence_refs=supporting_refs,
                    stance="bull",
                ),
            ),
            what_changed_zh="基于封闭证据包的正向信号完成。",
            allowed_evidence_ref_ids=tuple(allowed_refs),
        )
        bear_memo = BearCaseMemo(
            risk_claims=(
                EvidenceClaim(
                    claim="讨论窗口仍短，热度可能快速回落。",
                    evidence_refs=risk_refs or supporting_refs,
                    stance="risk",
                ),
            ),
            confidence_ceiling=0.78,
            missing_fact_impacts=(),
            allowed_evidence_ref_ids=tuple(allowed_refs),
        )
        final = FinalDecision(
            route=route,  # type: ignore[arg-type]
            recommendation="trade_candidate",
            confidence=0.72,
            summary_zh="社交扩散和链上质量同步支持继续观察。",
            narrative_archetype="社交扩散",
            narrative_thesis_zh="独立作者和关注账号讨论同步升温，链上质量没有明显恶化，适合观察扩散是否延续。",
            bull_view=BullBearView(
                strength="moderate",
                thesis_zh="独立作者扩散和关注账号确认共同支撑继续观察。",
                supporting_event_ids=["event-1"],
            ),
            bear_view=BullBearView(
                strength="weak",
                thesis_zh="讨论窗口仍短，热度可能快速回落。",
                supporting_event_ids=["event-1"],
            ),
            playbook=TradePlaybook(
                has_playbook=True,
                watch_signals=["关注独立作者是否继续扩散"],
                exit_triggers=["独立作者讨论快速降温"],
                monitoring_horizon="4h",
            ),
            evidence_event_urls={"event-1": "https://x.com/toly/status/1"},
            invalidation_conditions=["独立作者数回落。"],
            residual_risks=["流动性确认仍需观察。"],
            evidence_event_ids=["event-1"],
            supporting_evidence_refs=supporting_refs,
            risk_evidence_refs=risk_refs,
        )
        audit = self.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
        )
        return PulseDecisionResult(
            final_decision=final,
            agent_run_audit={**audit, "output_hash": "output-e2e"},
            stage_audits=(
                StageRunAudit(
                    stage="signal_analyst",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={
                        "evidence_packet_hash": context["evidence_packet"]["evidence_packet_hash"],
                        "completeness": completeness,
                    },
                    prompt_text="signal analyst prompt",
                    response_json=signal_memo.model_dump(mode="json"),
                    trace_metadata_json={},
                    usage_json={"input_tokens": 60},
                    latency_ms=10,
                    status="ok",
                ),
                StageRunAudit(
                    stage="bear_case",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={
                        "evidence_packet_hash": context["evidence_packet"]["evidence_packet_hash"],
                        "completeness": completeness,
                        "signal_memo": signal_memo.model_dump(mode="json"),
                    },
                    prompt_text="bear case prompt",
                    response_json=bear_memo.model_dump(mode="json"),
                    trace_metadata_json={},
                    usage_json={"output_tokens": 20},
                    latency_ms=11,
                    status="ok",
                ),
                StageRunAudit(
                    stage="risk_portfolio_judge",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={
                        "evidence_packet_hash": context["evidence_packet"]["evidence_packet_hash"],
                        "completeness": completeness,
                        "signal_memo": signal_memo.model_dump(mode="json"),
                        "bear_memo": bear_memo.model_dump(mode="json"),
                    },
                    prompt_text="risk portfolio judge prompt",
                    response_json=final.model_dump(mode="json"),
                    trace_metadata_json={},
                    usage_json={"output_tokens": 40},
                    latency_ms=12,
                    status="ok",
                ),
            ),
        )


class _PulseReadAdapter:
    def __init__(self, repos: FakeRepos) -> None:
        self._repos = repos

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self._repos.pulse_candidates.candidates.get(candidate_id)

    def list_agent_run_steps(self, run_id: str) -> list[dict[str, Any]]:
        return [step for step in self._repos.pulse_runs.agent_run_steps if step.get("run_id") == run_id]

    def list_candidates(self, **kwargs: Any) -> dict[str, Any]:
        rows = [
            row
            for row in self._repos.pulse_candidates.candidates.values()
            if row.get("window") == kwargs.get("window") and row.get("scope") == kwargs.get("scope")
        ]
        return {"items": rows, "next_cursor": None}


class _RealWorkerDb:
    def __init__(
        self,
        *,
        conn: Any,
        token_radar_rows: list[dict[str, Any]],
        token_target_rows: list[dict[str, Any]],
    ) -> None:
        self.repos = _RealWorkerRepos(
            conn=conn,
            token_radar_rows=token_radar_rows,
            token_target_rows=token_target_rows,
        )

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        yield self.repos


class _RealWorkerRepos:
    def __init__(
        self,
        *,
        conn: Any,
        token_radar_rows: list[dict[str, Any]],
        token_target_rows: list[dict[str, Any]],
    ) -> None:
        self.conn = conn
        self.pulse_jobs = PulseJobsRepository(conn)
        self.pulse_admission = PulseAdmissionRepository(conn)
        self.pulse_candidates = PulseCandidatesRepository(conn)
        self.pulse_runs = PulseRunsRepository(conn)
        self.pulse_agent_eval = PulseAgentEvalRepository(conn)
        self.pulse_playbooks = PulsePlaybooksRepository(conn)
        self.pulse_evidence = PulseEvidenceRepository(conn)
        self.pulse_evidence_sources = _RealWorkerEvidenceSources(conn)
        self.token_radar = _StaticRows(rows=token_radar_rows)
        self.token_targets = _StaticRows(rows=token_target_rows)


class _StaticRows:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def latest_current_rows(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)

    def timeline_rows(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)


class _RealWorkerEvidenceSources:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def list_source_events(self, event_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        ids = sorted({str(event_id).strip() for event_id in event_ids if str(event_id).strip()})
        if not ids:
            return []
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT
                  event_id,
                  received_at_ms AS observed_at_ms,
                  created_at_ms,
                  text_clean AS summary_zh,
                  canonical_url AS url,
                  'events' AS source_table,
                  'high' AS quality
                FROM events
                WHERE event_id = ANY(%s)
                ORDER BY received_at_ms DESC, event_id ASC
                """,
                (ids,),
            ).fetchall()
        ]

    def list_enriched_events(self, event_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        return []

    def list_market_facts(self, context: Any, *, max_age_ms: int, now_ms: int) -> list[dict[str, Any]]:
        return [
            {
                "ref_id": "market:pf-test",
                "route": "meme",
                "target_market_type": "dex",
                "price_usd": 0.42,
                "liquidity_usd": 250_000,
                "market_cap_usd": 1_000_000,
                "volume_24h_usd": 12_000,
                "pricefeed_id": "pf-test",
                "instrument_ref": "pf-test",
                "source_provider": "okx",
                "observed_at_ms": NOW_MS - 1_000,
                "freshness_status": "fresh",
                "source_table": "market_ticks",
            }
        ]

    def list_identity_facts(self, context: Any) -> list[dict[str, Any]]:
        return [
            {
                "source_id": "identity:asset-1",
                "target_id": "asset-1",
                "symbol": "TEST",
                "summary_zh": "TEST 目标身份已解析",
                "quality": "high",
                "observed_at_ms": NOW_MS - 1_000,
                "source_table": "asset_identity_current",
            }
        ]


class _EmptyEvidence:
    def recent_events(self, **_: Any) -> list[dict[str, Any]]:
        return []


class _EmptyAlerts:
    def account_alerts(self, **_: Any) -> list[dict[str, Any]]:
        return []


class _EmptyAssetFlow:
    def asset_flow(self, **_: Any) -> dict[str, Any]:
        return {"targets": [], "attention": []}


def _notification_engine(pulse: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=Settings(ws_token="secret"),
        evidence=_EmptyEvidence(),
        account_alerts=_EmptyAlerts(),
        asset_flow=_EmptyAssetFlow(),
        pulse=pulse,
    )


def _insert_event(conn: Any, *, event_id: str, received_at_ms: int, canonical_url: str | None) -> None:
    conn.execute(
        """
        INSERT INTO events(
          event_id, logical_dedup_key, canonical_url, source_provider, source_transport, coverage,
          channel, action, tweet_id, timestamp_ms, received_at_ms, author_handle, author_followers,
          author_tags_json, text, text_raw, text_clean, search_text, urls_json, cashtags_json,
          hashtags_json, mentions_json, media_json, matched_handles_json, is_watched, matched_at_ms,
          raw_json, event_json, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, %s, 'gmgn', 'websocket', 'public', 'twitter', 'tweet', %s, %s, %s, 'toly', 1000,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, 0, %s, %s, %s, %s
        )
        """,
        (
            event_id,
            f"dedupe:{event_id}",
            canonical_url,
            event_id,
            received_at_ms,
            received_at_ms,
            Jsonb([]),
            "$TEST read-only",
            "$TEST read-only",
            "$TEST read-only",
            "$TEST read-only",
            Jsonb([]),
            Jsonb(["TEST"]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb({"event_id": event_id}),
            Jsonb({"event_id": event_id}),
            received_at_ms,
            received_at_ms,
        ),
    )


class _SingleConnectionPool:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    @contextmanager
    def connection(self):
        yield self._conn
