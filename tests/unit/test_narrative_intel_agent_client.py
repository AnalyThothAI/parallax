from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    DiscussionDigestResult,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)
from gmgn_twitter_intel.integrations.openai_agents.narrative_intel_agent_client import (
    OpenAIAgentsNarrativeIntelClient,
)
from gmgn_twitter_intel.platform.agent_execution import (
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)


class FakeGateway:
    def __init__(self, output):
        self.output = output
        self.audit_calls = []
        self.execute_calls = []

    def model_for_lane(self, lane: str) -> str:
        if lane == "narrative.discussion_digest":
            return "gpt-digest"
        return "gpt-narrative"

    def request_audit(self, stage):
        self.audit_calls.append(stage)
        return AgentExecutionRequestAudit(
            model=self.model_for_lane(stage.lane),
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            sdk_trace_id=f"trace-{stage.stage}",
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash="artifact:test",
            input_hash=stage.input_hash,
            trace_metadata=dict(stage.trace_metadata),
        )

    async def execute(self, stage, *, reservation=None):
        assert reservation is None
        self.execute_calls.append(stage)
        request_audit = self.request_audit(stage)
        return AgentExecutionResult(
            final_output=self.output,
            audit=AgentExecutionResultAudit(
                **request_audit.model_dump(
                    mode="json",
                    exclude={
                        "status",
                        "execution_started",
                        "output_hash",
                        "parse_mode",
                        "safety_net",
                    },
                ),
                status=AgentExecutionStatus.DONE,
                execution_started=True,
                output_hash="sha256:output",
                parse_mode="strict",
                safety_net={"safety_net_used": False, "safety_net_retries": 0},
            ),
            raw_result=SimpleNamespace(final_output=self.output),
        )


def test_narrative_label_mentions_request_audit_builds_gateway_stage():
    gateway = FakeGateway({"labels": [], "failures": []})
    client = OpenAIAgentsNarrativeIntelClient(agent_gateway=gateway)
    request = _mention_request()

    audit = client.request_audit_for_label_mentions(run_id="run-mention-1", request=request)

    assert audit["lane"] == "narrative.mention_semantics"
    assert audit["stage"] == "mention_semantics"
    assert audit["agent_name"] == "NarrativeMentionSemanticsAgent"
    assert audit["workflow_name"] == "gmgn-twitter-intel.narrative_intel"
    assert audit["trace_metadata"]["run_id"] == "run-mention-1"
    assert audit["trace_metadata"]["mention_count"] == 1
    stage = gateway.audit_calls[0]
    assert stage.output_type.__name__ == "MentionSemanticsAgentPayload"
    assert '"event_id": "event-1"' in stage.input_payload
    assert "Label only the supplied token mention text" in stage.instructions


def test_narrative_client_labels_mentions_through_execution_gateway():
    gateway = FakeGateway(
        {
            "labels": [
                {
                    "event_id": "event-1",
                    "target_type": "asset",
                    "target_id": "asset:solana:token:So11111111111111111111111111111111111111112",
                    "language": "en",
                    "trade_stance": "bullish",
                    "attention_valence": "celebratory",
                    "narrative_cluster_key": "sol-rotation",
                    "claim_type": "rotation",
                    "evidence_type": "opinion",
                    "semantic_confidence": 0.83,
                    "co_mentioned_targets": [],
                    "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
                    "status": "labeled",
                }
            ],
            "failures": [],
        }
    )
    client = OpenAIAgentsNarrativeIntelClient(
        agent_gateway=gateway,
        max_turns=2,
    )
    request = _mention_request()

    result = asyncio.run(client.label_mentions(run_id="run-mention-1", request=request))

    assert isinstance(result, MentionSemanticsBatchResult)
    assert result.labels[0].trade_stance == "bullish"
    assert result.raw_response["labels"][0]["event_id"] == "event-1"
    assert result.agent_run_audit["backend"] == "openai_agents_sdk"
    assert result.agent_run_audit["input_hash"].startswith("sha256:")
    assert result.agent_run_audit["output_hash"] == "sha256:output"
    assert len(gateway.execute_calls) == 1
    stage = gateway.execute_calls[0]
    assert stage.lane == "narrative.mention_semantics"
    assert client.model == "gpt-narrative"
    assert stage.group_id == "event-1"
    assert stage.max_turns == 2


def test_narrative_summarize_discussion_request_audit_builds_gateway_stage():
    gateway = FakeGateway({"digest": _digest_payload()})
    client = OpenAIAgentsNarrativeIntelClient(agent_gateway=gateway)
    request = _digest_request()

    audit = client.request_audit_for_summarize_discussion(run_id="run-digest-1", request=request)

    assert audit["lane"] == "narrative.discussion_digest"
    assert audit["stage"] == "discussion_digest"
    assert audit["agent_name"] == "TokenDiscussionDigestAgent"
    assert audit["trace_metadata"]["run_id"] == "run-digest-1"
    assert audit["trace_metadata"]["target_id"] == request.target_id
    assert audit["trace_metadata"]["window"] == "24h"
    assert audit["trace_metadata"]["scope"] == "matched"
    stage = gateway.audit_calls[0]
    assert stage.output_type.__name__ == "DiscussionDigestAgentPayload"
    assert '"target_id": "' + request.target_id + '"' in stage.input_payload
    assert "Summarize only the supplied labeled mentions" in stage.instructions


def test_narrative_client_summarizes_discussion_through_execution_gateway():
    gateway = FakeGateway({"digest": _digest_payload()})
    client = OpenAIAgentsNarrativeIntelClient(
        agent_gateway=gateway,
    )
    request = _digest_request()

    result = asyncio.run(client.summarize_discussion(run_id="run-digest-1", request=request))

    assert isinstance(result, DiscussionDigestResult)
    assert result.digest["headline_zh"] == "SOL 讨论从价格防守切到轮动叙事。"
    assert result.raw_response["digest"]["target_id"] == request.target_id
    assert result.agent_run_audit["output_hash"] == "sha256:output"
    assert len(gateway.execute_calls) == 1
    stage = gateway.execute_calls[0]
    assert stage.lane == "narrative.discussion_digest"
    assert stage.agent_name == "TokenDiscussionDigestAgent"
    assert stage.group_id == request.target_id
    assert stage.trace_metadata["mention_count"] == 1


def _mention_request() -> MentionSemanticsBatchRequest:
    return MentionSemanticsBatchRequest(
        run_id="run-mention-1",
        schema_version="narrative_v1",
        prompt_version="mention-v1",
        mentions=[
            {
                "event_id": "event-1",
                "target_type": "asset",
                "target_id": "asset:solana:token:So11111111111111111111111111111111111111112",
                "text": "$SOL bids are rotating back.",
                "allowed_refs": [{"ref_id": "event:event-1", "kind": "event"}],
            }
        ],
    )


def _digest_request() -> DiscussionDigestRequest:
    target_id = "asset:solana:token:So11111111111111111111111111111111111111112"
    return DiscussionDigestRequest(
        run_id="run-digest-1",
        schema_version="narrative_v1",
        prompt_version="digest-v1",
        target_type="asset",
        target_id=target_id,
        window="24h",
        scope="matched",
        mentions=[{"event_id": "event-1", "summary_zh": "SOL 轮动。"}],
        context={"source_event_count": 3, "independent_author_count": 3},
        allowed_refs=[{"ref_id": "event:event-1", "kind": "event"}],
    )


def _digest_payload() -> dict:
    target_id = "asset:solana:token:So11111111111111111111111111111111111111112"
    return {
        "target_type": "asset",
        "target_id": target_id,
        "window": "24h",
        "scope": "matched",
        "schema_version": "narrative_v1",
        "model_version": "gpt-narrative",
        "status": "ready",
        "headline_zh": "SOL 讨论从价格防守切到轮动叙事。",
        "dominant_narratives": [
            {
                "cluster_key": "sol-rotation",
                "label_zh": "SOL 轮动",
                "summary_zh": "交易员把 SOL 当作主流反弹 beta。",
                "representative_event_ids": ["event-1"],
                "confidence": 0.78,
                "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
            }
        ],
        "bull_view": {
            "summary_zh": "多头认为资金从小盘回流 SOL。",
            "strength": "medium",
            "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
        },
        "bear_view": {
            "summary_zh": "空头担心只是情绪回补。",
            "strength": "weak",
            "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
        },
        "stance_mix": {"bullish": 0.7, "bearish": 0.3},
        "attention_valence_mix": {"celebratory": 0.7, "skeptical": 0.3},
        "propagation_read": {"primary_channel": "trader_replies"},
        "reflexivity_read": {"loop_state": "early_attention", "primary_reflexive_driver": "attention"},
        "data_gaps": [],
        "semantic_coverage": 1.0,
        "source_event_count": 3,
        "labeled_event_count": 3,
        "independent_author_count": 3,
        "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
        "model_run_id": "run-digest-1",
        "computed_at_ms": 1_800_000_000_000,
    }
