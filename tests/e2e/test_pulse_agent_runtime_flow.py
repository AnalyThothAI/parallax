from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.providers_wiring import OpenAIPulseDecisionProvider
from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateContext,
    PulseCandidateWorker,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import AnalystOpinion, CritiqueReport, FinalDecision
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import (
    OpenAIAgentsPulseDecisionClient,
)
from gmgn_twitter_intel.platform.db.postgres_client import connect_postgres
from tests.postgres_test_utils import repository_session_for_connection

NOW_MS = 1_800_000_000_000


class FakeGateway:
    trace_export_enabled = True

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        return await coro_factory()

    def openai_client(self, *, model, base_url, timeout_s):
        return object()


class FakeDB:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        return repository_session_for_connection(self.conn)


def test_pulse_agent_runtime_flow_persists_stage_ledger_and_public_decision(e2e_postgres: str) -> None:
    conn = connect_postgres(e2e_postgres)
    try:
        runner = FakeRunner(
            [
                AnalystOpinion(
                    route="meme",
                    recommendation="watchlist",
                    confidence=0.64,
                    summary_zh="社交流量开始扩散，值得继续观察。",
                    evidence=["event-e2e-1"],
                ),
                CritiqueReport(
                    route="meme",
                    weaknesses=["流动性仍需继续确认"],
                    missing_fact_impacts=[],
                    confidence_ceiling=0.58,
                    should_abstain=False,
                ),
                FinalDecision(
                    route="meme",
                    recommendation="trade_candidate",
                    confidence=0.58,
                    abstain_reason=None,
                    summary_zh="社交扩散与市场事实共振，但仍需观察流动性延续。",
                    invalidation_conditions=["独立作者数回落。"],
                    residual_risks=["流动性仍可能快速变薄。"],
                    evidence_event_ids=["event-e2e-1"],
                ),
            ]
        )
        provider = OpenAIPulseDecisionProvider(
            OpenAIAgentsPulseDecisionClient(
                api_key="sk-test",
                model="gpt-e2e",
                llm_gateway=FakeGateway(),
                runner=runner,
            )
        )
        context = _candidate_context()
        with repository_session_for_connection(conn) as repos:
            repos.pulse.enqueue_job(
                job_id="job-e2e-pulse",
                candidate_id=context.candidate_id,
                candidate_type=context.candidate_type,
                subject_key=context.subject_key,
                target_type=context.target_type,
                target_id=context.target_id,
                window=context.window,
                scope=context.scope,
                trigger_signature=context.trigger_signature,
                timeline_signature=context.timeline_signature,
                priority=80,
                context_json=context.agent_context(),
                next_run_at_ms=NOW_MS,
                now_ms=NOW_MS,
            )

        worker = PulseCandidateWorker(
            name="pulse_candidate",
            settings=SimpleNamespace(
                enabled=True,
                interval_seconds=60.0,
                timeout_seconds=120.0,
                batch_size=1,
                max_attempts=3,
                statement_timeout_seconds=30.0,
                advisory_lock_key=2026051502,
                windows=("1h",),
                scopes=("all",),
                trigger_thresholds=SimpleNamespace(min_rank_score=45),
                gate_thresholds=SimpleNamespace(
                    trade_candidate_min=72,
                    token_watch_min=45,
                    high_info_rejection_min=30,
                    high_conviction_min=78,
                ),
            ),
            db=FakeDB(conn),
            telemetry=object(),
            decision_client=provider,
        )

        result = worker.process_due_jobs_once(now_ms=NOW_MS)

        with repository_session_for_connection(conn) as repos:
            candidate = repos.pulse.candidate_by_id(context.candidate_id)
            assert candidate is not None
            run_id = str(candidate["agent_run_id"])
            run = conn.execute("SELECT * FROM pulse_agent_runs WHERE run_id = %s", (run_id,)).fetchone()
            harness = conn.execute(
                "SELECT * FROM pulse_agent_harness_versions WHERE harness_hash = %s",
                (run["harness_hash"],),
            ).fetchone()
            steps = repos.pulse.list_agent_run_steps(run_id)
            eval_cases = repos.pulse.list_agent_eval_cases(source_run_id=run_id)
            eval_results = repos.pulse.list_agent_eval_results(eval_case_id=eval_cases[0]["eval_case_id"])
            job = repos.pulse.job_for_candidate(context.candidate_id)
            public_item = SignalPulseService(pulse=repos.pulse).candidate(candidate_id=context.candidate_id)

        assert result == {"claimed": 1, "processed": 1, "failed": 0, "missing_context": 0}
        assert [call["agent"].name for call in runner.calls] == ["MemeAnalyst", "MemeCritic", "MemeJudge"]
        assert all(call["max_turns"] == 1 for call in runner.calls)

        assert job is not None
        assert job["status"] == "done"
        assert run["status"] == "done"
        assert run["outcome"] == "completed"
        assert run["decision_route"] == "meme"
        assert run["decision_stage_count"] == 3
        assert run["harness_version"] == "pulse-decision-harness-v1"
        assert run["harness_hash"].startswith("sha256:")
        assert run["request_json"]["selected_posts"][0]["event_id"] == "event-e2e-1"
        assert run["request_json"]["edge_events"] == ["pulse_status_changed", "score_band_crossed"]
        assert run["trace_metadata_json"]["route"] == "meme"
        assert run["trace_metadata_json"]["completeness"]["hard_blocked"] is False
        assert run["trace_metadata_json"]["harness_version"] == "pulse-decision-harness-v1"

        assert harness is not None
        assert harness["manifest_json"]["runtime"]["stages"] == ["analyst", "critic", "judge"]

        assert [step["stage"] for step in steps] == ["analyst", "critic", "judge"]
        assert steps[0]["input_json"]["context"]["candidate_id"] == context.candidate_id
        assert steps[0]["input_json"]["completeness"]["route"] == "meme"
        assert steps[2]["response_json"]["recommendation"] == "trade_candidate"
        assert steps[0]["started_at_ms"] <= steps[0]["finished_at_ms"]
        assert steps[0]["usage_json"] == {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
        assert run["usage_json"] == {"input_tokens": 30, "output_tokens": 9, "total_tokens": 39}

        assert len(eval_cases) == 1
        assert eval_cases[0]["source_run_id"] == run_id
        assert eval_cases[0]["harness_hash"] == run["harness_hash"]
        assert eval_cases[0]["rubric_json"]["grader_version"] == "pulse-deterministic-harness-v1"
        assert len(eval_results) == 1
        assert eval_results[0]["status"] == "pass"
        assert eval_results[0]["details_json"]["violations"] == []

        assert candidate["decision_route"] == "meme"
        assert candidate["decision_recommendation"] == "trade_candidate"
        assert candidate["decision_stage_count"] == 3
        assert candidate["decision_json"]["summary_zh"] == "社交扩散与市场事实共振，但仍需观察流动性延续。"
        assert candidate["last_edge_events_json"] == ["pulse_status_changed", "score_band_crossed"]
        assert "agent_recommendation_json" not in candidate

        assert public_item is not None
        assert public_item["decision"]["route"] == "meme"
        assert public_item["decision"]["recommendation"] == "trade_candidate"
        assert public_item["decision"]["stage_count"] == 3
        assert public_item["last_edge_events"] == ["pulse_status_changed", "score_band_crossed"]
        assert "agent_recommendation" not in public_item
    finally:
        conn.close()


class FakeRunner:
    def __init__(self, outputs: list[object]):
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    async def run(self, starting_agent, input, *, max_turns, run_config):
        self.calls.append(
            {
                "agent": starting_agent,
                "input": input,
                "max_turns": max_turns,
                "run_config": run_config,
            }
        )
        return SimpleNamespace(
            final_output=self.outputs.pop(0),
            usage={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
        )


def _candidate_context() -> PulseCandidateContext:
    return PulseCandidateContext(
        candidate_id="pulse-e2e-asset-1h-all-asset-test",
        candidate_type="token_target",
        subject_key="TEST",
        window="1h",
        scope="all",
        trigger_signature="trigger-e2e",
        timeline_signature="timeline-e2e",
        priority=80,
        target_type="Asset",
        target_id="asset:test",
        symbol="TEST",
        factor_snapshot=_factor_snapshot(),
        selected_posts=[
            {
                "event_id": "event-e2e-1",
                "author_handle": "toly",
                "text": "$TEST attention is expanding across independent accounts",
                "received_at_ms": NOW_MS - 60_000,
            }
        ],
        gate_result=None,
        edge_state={
            "pulse_status": "trade_candidate",
            "score_band": "80-89",
            "hard_risks": [],
            "recommended_decision": "high_alert",
            "watched_mentions": 1,
        },
        edge_events=("pulse_status_changed", "score_band_crossed"),
        source_event_ids=["event-e2e-1"],
        evidence_event_ids=["event-e2e-1"],
    )


def _factor_snapshot() -> dict[str, Any]:
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "target_type": "Asset",
            "target_id": "asset:test",
            "target_market_type": "dex",
            "symbol": "TEST",
        },
        "market": {
            "event_anchor": None,
            "decision_latest": {
                "target_type": "Asset",
                "target_id": "asset:test",
                "observed_at_ms": NOW_MS - 60_000,
                "received_at_ms": NOW_MS - 60_000,
                "source": "decision_latest",
                "provider": "okx",
                "pricefeed_id": "pf-test",
                "price_usd": 0.42,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 1_000_000,
                "liquidity_usd": 250_000,
                "holders": 1_000,
                "volume_24h_usd": 120_000,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": True,
            "blocked_reasons": [],
            "risk_reasons": [],
            "max_decision": "high_alert",
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": {
                "raw_score": 82,
                "score": 82,
                "weight": 0.35,
                "data_health": "ready",
                "facts": {"mentions_1h": 8, "unique_authors": 7, "watched_mentions": 1},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": 7},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 76,
                "score": 76,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {"phase": "ignition"},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 60,
                "score": 60,
                "weight": 0.1,
                "data_health": "ready",
                "facts": {"price_change_status": "ready"},
                "factors": {},
            },
        },
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {"size": 12, "in_cohort": True},
            "factor_ranks": {},
            "alpha_rank": 0.82,
        },
        "composite": {
            "family_scores": {
                "social_heat": 82,
                "social_propagation": 80,
                "semantic_catalyst": 76,
                "timing_risk": 60,
            },
            "rank_score": 82,
            "recommended_decision": "high_alert",
        },
        "provenance": {"source_event_ids": ["event-e2e-1"], "computed_at_ms": NOW_MS - 60_000},
    }
