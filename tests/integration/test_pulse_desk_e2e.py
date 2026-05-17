from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.notifications.services.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.platform.config.settings import Settings
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
def test_pulse_agent_desk_e2e_worker_read_model_and_notification_surface() -> None:
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


def _notification_engine(pulse: _PulseReadAdapter) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=Settings(ws_token="secret"),
        evidence=_EmptyEvidence(),
        account_alerts=_EmptyAlerts(),
        asset_flow=_EmptyAssetFlow(),
        harness=_EmptyHarness(),
        pulse=pulse,
    )
