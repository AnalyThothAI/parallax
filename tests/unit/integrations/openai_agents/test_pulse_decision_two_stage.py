"""Two-stage Investigator → DecisionMaker pulse client behaviour tests.

The SDK ``Runner`` is replaced with a ``FakeRunner`` per test that returns a
``FakeRunResult`` whose ``final_output`` is the pre-constructed
``InvestigationReport`` / ``FinalDecision`` we want the stage to produce. This
exercises the client's stage orchestration, hallucination guard, tool budget
fan-out and evidence URL enrichment without booting a real SDK or PostgreSQL.

We import the SDK's ``ToolCallItem`` so the ``new_items`` synthesised by the
test mirrors the real SDK shape exactly (the client extracts
``tool_calls`` metadata from this list into ``StageRunAudit.input_json``).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from agents import Agent, ToolCallItem

from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import (
    build_pulse_harness_manifest,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    InvestigationReport,
    PulseStageFailure,
    TradePlaybook,
)
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import (
    OpenAIAgentsPulseDecisionClient,
)
from gmgn_twitter_intel.integrations.openai_agents.tools import (
    PulseToolContext,
    ToolBudgetExceeded,
)

# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeRunResult:
    """Minimal SDK ``RunResult`` shim sufficient for the client to consume.

    The client touches ``final_output``, ``new_items`` (for ``tool_calls``
    extraction) and ``usage`` (for the audit payload); other fields default
    to empty.
    """

    final_output: Any
    raw_responses: list = field(default_factory=list)
    new_items: list = field(default_factory=list)
    context_wrapper: Any = None
    usage: Any = None


class FakeRunner:
    """Deterministic ``Runner.run`` replacement.

    Each ``outcomes`` entry is either a ``FakeRunResult`` (returned) or an
    ``Exception`` (raised). Stage agents are dispatched in order; the runner
    also captures every call so tests can assert ordering / context.
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def run(self, agent, input, *, max_turns, run_config, context=None):
        self.calls.append(
            {
                "agent": agent,
                "input": input,
                "max_turns": max_turns,
                "run_config": run_config,
                "context": context,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeGateway:
    """LLMGateway stub: just runs the supplied callable."""

    trace_export_enabled = True

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        return await coro_factory()


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.queries: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        self.queries.append((sql, params))
        return _FakeCursor(self._rows)


class FakeDbPool:
    """Minimal connection-pool stub with a context-manager ``connection()``."""

    def __init__(self, event_rows: list[dict[str, Any]] | None = None) -> None:
        self._event_rows = event_rows or []
        self.conn = _FakeConn(self._event_rows)

    @contextmanager
    def connection(self):
        yield self.conn


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_client(
    runner: Any,
    *,
    db_pool: Any | None = None,
    investigator_budgets: dict[str, int] | None = None,
    enable_fallback_tool: bool = True,
    safety_net: Any | None = None,
) -> OpenAIAgentsPulseDecisionClient:
    return OpenAIAgentsPulseDecisionClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=FakeGateway(),
        db_pool=db_pool or FakeDbPool(),
        runner=runner,
        safety_net=safety_net,
        investigator_max_tool_calls_by_route=investigator_budgets,
        decision_maker_enable_fallback_tool=enable_fallback_tool,
    )


def _context(
    *,
    evidence_event_ids: list[str] | None = None,
    source_event_ids: list[str] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "subject_key": "asset:pepe",
        "target_type": "Asset",
        "target_id": "asset:pepe",
    }
    if evidence_event_ids is not None:
        ctx["evidence_event_ids"] = evidence_event_ids
    if source_event_ids is not None:
        ctx["source_event_ids"] = source_event_ids
    return ctx


def _harness() -> dict[str, Any]:
    return build_pulse_harness_manifest(
        provider="openai",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )


def _investigation(
    *,
    bull_ids: list[str] | None = None,
    bear_strength: str = "absent",
    bear_ids: list[str] | None = None,
) -> InvestigationReport:
    if bull_ids is None:
        bull_ids = ["evt-1"]
    bull = BullBearView(
        strength="moderate",
        thesis_zh="社交注意力持续走高,买盘情绪显著。",
        supporting_event_ids=bull_ids,
    )
    if bear_strength == "absent":
        bear = BullBearView(strength="absent")
    else:
        bear = BullBearView(
            strength=bear_strength,
            thesis_zh="流动性偏薄,可能出现波动。",
            supporting_event_ids=bear_ids or ["evt-2"],
        )
    return InvestigationReport(
        narrative_archetype_candidate="社交热度叙事",
        narrative_observation_zh=(
            "PEPE 在过去 24 小时内出现多次高粉丝账号转发,链上交易笔数同步抬升,需要继续观察持续性。"
        ),
        bull_observation=bull,
        bear_observation=bear,
        data_gaps=[],
    )


def _final_decision(
    *,
    evidence_event_ids: list[str] | None = None,
) -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="trade_candidate",
        confidence=0.55,
        abstain_reason=None,
        summary_zh="社交与市场事实共振。",
        narrative_archetype="社交热度叙事",
        narrative_thesis_zh=(
            "社交注意力扩散叠加链上买盘抬升,短期主题动能成立,但需要持续跟进流动性变化与回撤幅度。"
        ),
        bull_view=BullBearView(
            strength="moderate",
            thesis_zh="社交关注度抬升提供主题动能。",
            supporting_event_ids=["evt-1"],
        ),
        bear_view=BullBearView(
            strength="weak",
            thesis_zh="深度仍然有限,需警惕回撤。",
            supporting_event_ids=["evt-1"],
        ),
        playbook=TradePlaybook(
            has_playbook=True,
            watch_signals=["社交注意力维持"],
            exit_triggers=["热度回落"],
            monitoring_horizon="4h",
        ),
        invalidation_conditions=["热度迅速回落"],
        residual_risks=["流动性深度不足"],
        evidence_event_ids=list(evidence_event_ids or ["evt-1"]),
    )


_AGENT_STUB = Agent(name="stub", instructions="")


def _tool_call_item(name: str, args: str = "{}") -> ToolCallItem:
    """Synthesise a ToolCallItem so ``_extract_tool_calls`` sees real shape.

    ``RunItemBase.__post_init__`` stores a weakref to ``agent`` which means
    we need a real Agent instance (not None); a no-op stub is enough.
    """

    return ToolCallItem(
        agent=_AGENT_STUB,
        raw_item={"name": name, "arguments": args, "call_id": f"call-{name}"},
    )


# ---------------------------------------------------------------------------
# happy path + ordering
# ---------------------------------------------------------------------------


def test_investigator_then_decision_maker_in_order() -> None:
    runner = FakeRunner(
        [
            FakeRunResult(
                final_output=_investigation(),
                new_items=[_tool_call_item("get_target_recent_tweets")],
            ),
            FakeRunResult(final_output=_final_decision()),
        ]
    )
    client = _build_client(runner)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    assert [call["agent"].name for call in runner.calls] == [
        "PulseInvestigatorMeme",
        "PulseDecisionMakerMeme",
    ]
    assert [audit.stage for audit in result.stage_audits] == [
        "investigator",
        "decision_maker",
    ]
    assert result.final_decision.recommendation == "trade_candidate"
    assert result.run_audit["agent_name"] == "PulseDecisionDesk"
    # investigator step recorded the SDK tool call into input_json.tool_calls.
    investigator_audit = result.stage_audits[0]
    assert investigator_audit.input_json["tool_calls"][0]["tool_name"] == "get_target_recent_tweets"


def test_investigator_uses_configured_max_turns_and_carries_tool_context() -> None:
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation()),
            FakeRunResult(final_output=_final_decision()),
        ]
    )
    client = _build_client(runner, investigator_budgets={"meme": 5})

    asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    investigator_call = runner.calls[0]
    decision_call = runner.calls[1]
    assert investigator_call["max_turns"] == 5
    assert decision_call["max_turns"] == 3
    assert isinstance(investigator_call["context"], PulseToolContext)
    assert investigator_call["context"].investigator_max_tool_calls == 5
    # Both stages share the SAME PulseToolContext so the budget carries over.
    assert investigator_call["context"] is decision_call["context"]


def test_tool_budget_counts_are_recorded_for_investigator_and_decision_fallback() -> None:
    class CountingRunner(FakeRunner):
        async def run(self, agent, input, *, max_turns, run_config, context=None):
            if isinstance(context, PulseToolContext):
                if agent.name == "PulseInvestigatorMeme":
                    context.tool_calls_count += 2
                elif agent.name == "PulseDecisionMakerMeme":
                    context.tool_calls_count += 1
            return await super().run(agent, input, max_turns=max_turns, run_config=run_config, context=context)

    runner = CountingRunner(
        [
            FakeRunResult(final_output=_investigation()),
            FakeRunResult(final_output=_final_decision()),
        ]
    )
    client = _build_client(runner)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    investigator_meta = result.stage_audits[0].trace_metadata_json
    decision_meta = result.stage_audits[1].trace_metadata_json
    assert investigator_meta["tool_calls_count_before"] == 0
    assert investigator_meta["tool_calls_count_after"] == 2
    assert investigator_meta["tool_calls_count_delta"] == 2
    assert decision_meta["tool_calls_count_before"] == 2
    assert decision_meta["tool_calls_count_after"] == 3
    assert decision_meta["tool_calls_count_delta"] == 1


def test_decision_maker_fallback_tool_disabled_when_flag_false() -> None:
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation()),
            FakeRunResult(final_output=_final_decision()),
        ]
    )
    client = _build_client(runner, enable_fallback_tool=False)

    asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    decision_call = runner.calls[1]
    assert decision_call["agent"].tools == []


def test_safety_net_strict_success_preserves_sdk_tool_calls_and_budget_counts() -> None:
    class FakeSafetyNet:
        async def run_with_safety_net(
            self,
            *,
            agent,
            input_payload,
            run_config,
            pydantic_output_type,
            context=None,
            max_turns,
            return_result=False,
        ):
            assert return_result is True
            if isinstance(context, PulseToolContext):
                context.tool_calls_count += 1
            result = FakeRunResult(
                final_output=_investigation(),
                new_items=[_tool_call_item("get_target_recent_tweets")],
            )
            return result.final_output, {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
                "usage": {"total_tokens": 42},
            }, result

    client = _build_client(FakeRunner([]), safety_net=FakeSafetyNet())
    tool_ctx = PulseToolContext(db_pool=FakeDbPool(), investigator_max_tool_calls=5)
    audit = client.request_audit(
        context=_context(evidence_event_ids=["evt-1"]),
        run_id="run-1",
        job={},
        route="meme",
        completeness={"score": 1.0, "missing_fields": []},
        harness=_harness(),
    )

    stage = asyncio.run(
        client._run_stage(
            stage="investigator",
            route="meme",
            agent=Agent[PulseToolContext](name="PulseInvestigatorMeme", instructions=""),
            output_type=InvestigationReport,
            input_payload={
                "route": "meme",
                "context": _context(evidence_event_ids=["evt-1"]),
                "completeness": {"score": 1.0, "missing_fields": []},
            },
            prompt="prompt",
            audit=audit,
            tool_ctx=tool_ctx,
            max_turns=5,
        )
    )

    assert stage.status == "ok"
    assert stage.input_json["tool_calls"][0]["tool_name"] == "get_target_recent_tweets"
    assert stage.trace_metadata_json["tool_calls_count_before"] == 0
    assert stage.trace_metadata_json["tool_calls_count_after"] == 1
    assert stage.trace_metadata_json["tool_calls_count_delta"] == 1


# ---------------------------------------------------------------------------
# failure modes
# ---------------------------------------------------------------------------


def test_investigator_failure_short_circuits_with_one_audit() -> None:
    runner = FakeRunner([RuntimeError("model parse error")])
    client = _build_client(runner)

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    failure = exc_info.value
    assert len(failure.audits) == 1
    assert failure.audits[0].stage == "investigator"
    assert failure.audits[0].status == "failed"
    assert "model parse error" in (failure.audits[0].error or "")


def test_decision_maker_failure_preserves_two_audits() -> None:
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation()),
            RuntimeError("decision parse error"),
        ]
    )
    client = _build_client(runner)

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(evidence_event_ids=["evt-1"]),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    failure = exc_info.value
    assert [audit.stage for audit in failure.audits] == ["investigator", "decision_maker"]
    assert failure.audits[0].status == "ok"
    assert failure.audits[1].status == "failed"


# ---------------------------------------------------------------------------
# hallucination guard
# ---------------------------------------------------------------------------


def test_hallucination_guard_rejects_unknown_supporting_event_ids() -> None:
    # bull_observation cites evt-unknown but tool contributions + context have
    # only evt-real → guard must flip stage to failed and raise.
    runner = FakeRunner(
        [FakeRunResult(final_output=_investigation(bull_ids=["evt-unknown"]))]
    )
    client = _build_client(runner)

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(evidence_event_ids=["evt-real"]),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    failure = exc_info.value
    assert len(failure.audits) == 1
    investigator_audit = failure.audits[0]
    assert investigator_audit.status == "failed"
    assert "unknown event ids" in (investigator_audit.error or "")


def test_hallucination_guard_accepts_ids_from_tool_contributions() -> None:
    # A tool emitted evt-tool, investigator legitimately cites it → no failure.
    def runner_factory() -> FakeRunner:
        return FakeRunner(
            [
                FakeRunResult(final_output=_investigation(bull_ids=["evt-tool"])),
                FakeRunResult(
                    final_output=_final_decision(evidence_event_ids=["evt-tool"]).model_copy(
                        update={
                            "bull_view": BullBearView(
                                strength="moderate",
                                thesis_zh="社交关注度抬升提供主题动能。",
                                supporting_event_ids=["evt-tool"],
                            ),
                            "bear_view": BullBearView(
                                strength="weak",
                                thesis_zh="深度仍然有限,需警惕回撤。",
                                supporting_event_ids=["evt-tool"],
                            ),
                        }
                    )
                ),
            ]
        )

    runner = runner_factory()
    client = _build_client(runner)

    # Simulate a tool having contributed evt-tool to the shared context.
    async def _seed_then_run() -> None:
        # We inject by monkey-wrapping the first runner.run to seed the ctx.
        original_run = runner.run

        async def wrapped(agent, input, *, max_turns, run_config, context=None):
            if context is not None and isinstance(context, PulseToolContext):
                context.contributed_event_ids.add("evt-tool")
            return await original_run(agent, input, max_turns=max_turns, run_config=run_config, context=context)

        runner.run = wrapped  # type: ignore[method-assign]
        await client.run_decision_pipeline(
            context=_context(),  # no evidence_event_ids in context
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )

    asyncio.run(_seed_then_run())


def test_final_evidence_guard_rejects_unknown_final_evidence_event_ids() -> None:
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(final_output=_final_decision(evidence_event_ids=["evt-unknown"])),
        ]
    )
    client = _build_client(runner)

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(evidence_event_ids=["evt-1"]),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    failure = exc_info.value
    assert [audit.stage for audit in failure.audits] == ["investigator", "decision_maker"]
    decision_audit = failure.audits[1]
    assert decision_audit.status == "failed"
    assert "unknown event ids" in (decision_audit.error or "")
    assert "evidence_event_ids" in (decision_audit.error or "")


def test_final_evidence_guard_rejects_unknown_bull_and_bear_supporting_ids() -> None:
    final = _final_decision(evidence_event_ids=["evt-1"])
    final = final.model_copy(
        update={
            "bull_view": BullBearView(
                strength="moderate",
                thesis_zh="社交关注度抬升提供主题动能。",
                supporting_event_ids=["evt-unknown-bull"],
            ),
            "bear_view": BullBearView(
                strength="weak",
                thesis_zh="深度仍然有限,需警惕回撤。",
                supporting_event_ids=["evt-unknown-bear"],
            ),
        }
    )
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(final_output=final),
        ]
    )
    client = _build_client(runner)

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(evidence_event_ids=["evt-1"]),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    decision_audit = exc_info.value.audits[1]
    assert decision_audit.status == "failed"
    assert "bull_view.supporting_event_ids" in (decision_audit.error or "")


def test_final_evidence_guard_accepts_context_tool_and_investigator_ids() -> None:
    final = _final_decision(evidence_event_ids=["evt-context", "evt-source", "evt-tool", "evt-investigator"])
    final = final.model_copy(
        update={
            "bull_view": BullBearView(
                strength="moderate",
                thesis_zh="社交关注度抬升提供主题动能。",
                supporting_event_ids=["evt-tool"],
            ),
            "bear_view": BullBearView(
                strength="weak",
                thesis_zh="深度仍然有限,需警惕回撤。",
                supporting_event_ids=["evt-investigator"],
            ),
        }
    )
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-investigator"])),
            FakeRunResult(final_output=final),
        ]
    )
    client = _build_client(runner)

    async def _seed_then_run():
        original_run = runner.run

        async def wrapped(agent, input, *, max_turns, run_config, context=None):
            if agent.name == "PulseInvestigatorMeme" and isinstance(context, PulseToolContext):
                context.contributed_event_ids.add("evt-tool")
                context.contributed_event_ids.add("evt-investigator")
            return await original_run(agent, input, max_turns=max_turns, run_config=run_config, context=context)

        runner.run = wrapped  # type: ignore[method-assign]
        return await client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-context"], source_event_ids=["evt-source"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )

    result = asyncio.run(_seed_then_run())
    assert result.final_decision.evidence_event_ids == ["evt-context", "evt-source", "evt-tool", "evt-investigator"]


# ---------------------------------------------------------------------------
# tool budget overflow
# ---------------------------------------------------------------------------


def test_tool_budget_exceeded_surfaces_as_investigator_failure() -> None:
    # SDK runner raises ToolBudgetExceeded (which is what the real SDK does
    # when the wrapped tool re-raises out of Runner.run).
    runner = FakeRunner([ToolBudgetExceeded("budget exceeded: 6 > 5")])
    client = _build_client(runner, investigator_budgets={"meme": 5})

    with pytest.raises(PulseStageFailure) as exc_info:
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )

    failure = exc_info.value
    assert failure.audits[0].status == "failed"
    assert "budget exceeded" in (failure.audits[0].error or "")


# ---------------------------------------------------------------------------
# evidence_event_urls enrichment
# ---------------------------------------------------------------------------


def test_evidence_event_urls_enriched_from_events_table() -> None:
    db_pool = FakeDbPool(
        event_rows=[
            {"event_id": "evt-1", "author_handle": "alice", "tweet_id": "111"},
            {"event_id": "evt-2", "author_handle": "bob", "tweet_id": "222"},
            # evt-3 row exists but no tweet_id → should NOT show up in urls.
            {"event_id": "evt-3", "author_handle": "carol", "tweet_id": None},
        ]
    )
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(
                final_output=_final_decision(evidence_event_ids=["evt-1", "evt-2", "evt-3"])
            ),
        ]
    )
    client = _build_client(runner, db_pool=db_pool)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1", "evt-2", "evt-3"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    urls = result.final_decision.evidence_event_urls
    assert urls == {
        "evt-1": "https://x.com/alice/status/111",
        "evt-2": "https://x.com/bob/status/222",
    }
    query = db_pool.conn.queries[-1][0]
    assert "canonical_url" in query
    assert "event_payload_json" not in query
    # evt-3 missing tweet_id → omitted, surface card degrades to "no link".


def test_evidence_event_urls_prefers_canonical_url_from_payload() -> None:
    db_pool = FakeDbPool(
        event_rows=[
            {
                "event_id": "evt-1",
                "author_handle": "alice",
                "tweet_id": "111",
                "canonical_url": "https://x.com/canonical/status/999",
            },
        ]
    )
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(final_output=_final_decision(evidence_event_ids=["evt-1"])),
        ]
    )
    client = _build_client(runner, db_pool=db_pool)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    assert result.final_decision.evidence_event_urls == {
        "evt-1": "https://x.com/canonical/status/999",
    }


def test_evidence_event_urls_overwrite_model_supplied_urls_on_db_error() -> None:
    class _ExplodingPool:
        @contextmanager
        def connection(self):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover -- unreachable

    final = _final_decision(evidence_event_ids=["evt-1"]).model_copy(
        update={"evidence_event_urls": {"evt-1": "https://evil.example/forged"}}
    )
    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(final_output=final),
        ]
    )
    client = _build_client(runner, db_pool=_ExplodingPool())

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    assert result.final_decision.evidence_event_urls == {}


def test_evidence_event_urls_include_bull_and_bear_supporting_ids() -> None:
    final = _final_decision(evidence_event_ids=[]).model_copy(
        update={
            "evidence_event_ids": [],
            "bull_view": BullBearView(
                strength="moderate",
                thesis_zh="社交关注度抬升提供主题动能。",
                supporting_event_ids=["evt-bull"],
            ),
            "bear_view": BullBearView(
                strength="weak",
                thesis_zh="流动性偏薄,需要警惕波动。",
                supporting_event_ids=["evt-bear"],
            ),
        }
    )
    db_pool = FakeDbPool(
        event_rows=[
            {
                "event_id": "evt-bull",
                "author_handle": "alice",
                "tweet_id": "111",
                "canonical_url": "https://x.com/alice/status/111",
            },
            {
                "event_id": "evt-bear",
                "author_handle": "bob",
                "tweet_id": "222",
                "canonical_url": "https://x.com/bob/status/222",
            },
        ]
    )
    runner = FakeRunner(
        [
            FakeRunResult(
                final_output=_investigation(
                    bull_ids=["evt-bull"],
                    bear_strength="weak",
                    bear_ids=["evt-bear"],
                )
            ),
            FakeRunResult(final_output=final),
        ]
    )
    client = _build_client(runner, db_pool=db_pool)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-bull", "evt-bear"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    assert result.final_decision.evidence_event_urls == {
        "evt-bull": "https://x.com/alice/status/111",
        "evt-bear": "https://x.com/bob/status/222",
    }


def test_evidence_event_urls_db_error_degrades_silently() -> None:
    class _ExplodingPool:
        @contextmanager
        def connection(self):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover -- unreachable

    runner = FakeRunner(
        [
            FakeRunResult(final_output=_investigation(bull_ids=["evt-1"])),
            FakeRunResult(final_output=_final_decision(evidence_event_ids=["evt-1"])),
        ]
    )
    client = _build_client(runner, db_pool=_ExplodingPool())

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(evidence_event_ids=["evt-1"]),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    # Enrichment is best-effort; missing urls leave the dict empty.
    assert result.final_decision.evidence_event_urls == {}


# ---------------------------------------------------------------------------
# harness manifest
# ---------------------------------------------------------------------------


def test_pulse_harness_manifest_advertises_two_stages_and_tools_enabled() -> None:
    manifest = build_pulse_harness_manifest(
        provider="openai",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )

    runtime = manifest["runtime"]
    assert runtime["stages"] == ["investigator", "decision_maker"]
    assert runtime["tools_enabled"] is True
    assert runtime["max_turns_per_stage"] == {"investigator": 5, "decision_maker": 3}
