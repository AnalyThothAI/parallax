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
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_repository import PulseRepository
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    StageRunAudit,
    TradePlaybook,
)
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
    client = _TwoStageClient()
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

    candidate = repos.pulse.candidate_upserts[0]
    decision = candidate["decision_json"]
    assert {"narrative_archetype", "narrative_thesis_zh", "bull_view", "bear_view", "playbook"} <= set(decision)
    assert decision["evidence_event_urls"] == {"event-1": "https://x.com/toly/status/1"}
    assert [step["stage"] for step in repos.pulse.agent_run_steps] == ["investigator", "decision_maker"]
    assert repos.pulse.agent_run_steps[0]["input_json"]["tool_calls"]

    pulse_read = _PulseReadAdapter(repos)
    detail = SignalPulseService(pulse=pulse_read).candidate(candidate_id=candidate["candidate_id"])
    assert detail is not None
    assert detail["decision"]["playbook"]["has_playbook"] is True
    assert detail["decision"]["bull_view"]["strength"] == "moderate"
    assert detail["stages"]["investigator"]["response"]["narrative_archetype_candidate"] == "社交扩散"
    assert detail["stages"]["decision_maker"]["response"]["recommendation"] == "trade_candidate"

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
            decision_client=_TwoStageClient(),
        )

        scan = worker.scan_triggers_once(now_ms=NOW_MS)
        run = worker.process_due_jobs_once(now_ms=NOW_MS)
        assert scan["asset_enqueued"] == 1
        assert run["processed"] == 1

        repo = PulseRepository(conn)
        page = repo.list_candidates(window="1h", scope="all", status="trade_candidate", limit=10)
        assert len(page["items"]) == 1
        stored = page["items"][0]
        ids = {"candidate_id": stored["candidate_id"], "run_id": stored["agent_run_id"]}

        decision = stored["decision_json"]
        assert {"narrative_archetype", "narrative_thesis_zh", "bull_view", "bear_view", "playbook"} <= set(decision)

        steps = repo.list_agent_run_steps(ids["run_id"])
        steps_by_stage = {step["stage"]: step for step in steps}
        assert set(steps_by_stage) == {"investigator", "decision_maker"}
        assert steps_by_stage["investigator"]["input_json"]["tool_calls"]

        detail = SignalPulseService(pulse=repo).candidate(candidate_id=ids["candidate_id"])
        assert detail is not None
        assert detail["decision"]["playbook"]["has_playbook"] is True
        assert detail["decision"]["bull_view"]["strength"] == "moderate"
        assert detail["stages"]["investigator"]["response"]["narrative_archetype_candidate"] == "社交扩散"
        assert detail["stages"]["decision_maker"]["response"]["recommendation"] == "trade_candidate"

        notifications = _notification_engine(repo).evaluate(now_ms=NOW_MS)
        pulse_notifications = [item for item in notifications if item.rule_id == "signal_pulse_candidate"]
        assert len(pulse_notifications) == 1
        notification = pulse_notifications[0]
        signature = notification.payload["notification_signature"]
        assert signature.startswith("sha256:")
        assert notification.dedup_key == f"signal_pulse_candidate:{ids['candidate_id']}:{signature}"
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


class _TwoStageClient:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake-two-stage"

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "backend": "fake",
            "sdk_trace_id": f"trace-{run_id}",
            "workflow_name": "pulse-test",
            "agent_name": "pulse-test-agent",
            "prompt_version": "pulse-decision-prompt-v2",
            "schema_version": "pulse-decision-v2",
            "artifact_version_hash": self.artifact_version_hash,
            "harness_version": harness["harness_version"],
            "harness_hash": "sha256:e2e",
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
        harness: dict[str, Any],
    ) -> PulseDecisionResult:
        investigation = {
            "narrative_archetype_candidate": "社交扩散",
            "narrative_observation_zh": "独立作者和关注账号讨论同步升温，链上质量仍保持可观察状态。",
            "bull_observation": {
                "strength": "moderate",
                "thesis_zh": "独立作者扩散和关注账号确认共同支撑继续观察。",
                "supporting_event_ids": ["event-1"],
            },
            "bear_observation": {
                "strength": "weak",
                "thesis_zh": "讨论窗口仍短，热度可能快速回落。",
                "supporting_event_ids": ["event-1"],
            },
            "data_gaps": [],
        }
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
        )
        audit = self.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            harness=harness,
        )
        return PulseDecisionResult(
            final_decision=final,
            agent_run_audit={**audit, "output_hash": "output-e2e"},
            stage_audits=(
                StageRunAudit(
                    stage="investigator",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={
                        "context": context,
                        "completeness": completeness,
                        "tool_calls": [{"tool_name": "get_target_recent_tweets"}],
                    },
                    prompt_text="investigator prompt",
                    response_json=investigation,
                    trace_metadata_json={},
                    usage_json={"input_tokens": 60},
                    latency_ms=10,
                    status="ok",
                ),
                StageRunAudit(
                    stage="decision_maker",
                    route=route,  # type: ignore[arg-type]
                    attempt_index=0,
                    input_json={"context": context, "completeness": completeness, "investigation": investigation},
                    prompt_text="decision maker prompt",
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
        return self._repos.pulse.candidates.get(candidate_id)

    def list_agent_run_steps(self, run_id: str) -> list[dict[str, Any]]:
        return [step for step in self._repos.pulse.agent_run_steps if step.get("run_id") == run_id]

    def list_candidates(self, **kwargs: Any) -> dict[str, Any]:
        rows = [
            row
            for row in self._repos.pulse.candidates.values()
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
        self.pulse = PulseRepository(conn)
        self.token_radar = _StaticRows(rows=token_radar_rows)
        self.token_targets = _StaticRows(rows=token_target_rows)
        self.harness = _EmptyHarness()


class _StaticRows:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def latest_rows(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)

    def timeline_rows(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)


class _EmptyEvidence:
    def recent_events(self, **_: Any) -> list[dict[str, Any]]:
        return []


class _EmptyAlerts:
    def account_alerts(self, **_: Any) -> list[dict[str, Any]]:
        return []


class _EmptyAssetFlow:
    def asset_flow(self, **_: Any) -> dict[str, Any]:
        return {"targets": [], "attention": []}


class _EmptyHarness:
    def snapshots(self, **_: Any) -> dict[str, list[dict[str, Any]]]:
        return {"items": []}


def _notification_engine(pulse: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=Settings(ws_token="secret"),
        evidence=_EmptyEvidence(),
        account_alerts=_EmptyAlerts(),
        asset_flow=_EmptyAssetFlow(),
        harness=_EmptyHarness(),
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
