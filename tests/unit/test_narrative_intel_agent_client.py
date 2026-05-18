from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    DiscussionDigestResult,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.narrative_intel_agent_client import (
    OpenAIAgentsNarrativeIntelClient,
)


class FakeRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def run(self, starting_agent, input, *, max_turns, run_config):
        self.calls.append(
            {
                "agent": starting_agent,
                "input": input,
                "max_turns": max_turns,
                "run_config": run_config,
            }
        )
        return SimpleNamespace(final_output=self.output)


class FakeGateway:
    trace_export_enabled = True

    def __init__(self) -> None:
        self.calls = []

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        self.calls.append({"worker_name": worker_name, "stage": stage, "timeout_s": timeout_s})
        return await coro_factory()

    def openai_client(self, *, model, base_url, timeout_s):
        return object()


def test_narrative_client_labels_mentions_through_typed_agent():
    gateway = FakeGateway()
    runner = FakeRunner(
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
        api_key="sk-test",
        model="gpt-narrative",
        llm_gateway=gateway,
        timeout_seconds=11,
        runner=runner,
    )
    request = MentionSemanticsBatchRequest(
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

    result = asyncio.run(client.label_mentions(run_id="run-mention-1", request=request))

    assert isinstance(result, MentionSemanticsBatchResult)
    assert result.labels[0].trade_stance == "bullish"
    assert result.raw_response["labels"][0]["event_id"] == "event-1"
    assert result.agent_run_audit["backend"] == "openai_agents_sdk"
    assert result.agent_run_audit["input_hash"].startswith("sha256:")
    assert gateway.calls == [{"worker_name": "narrative_intel", "stage": "mention_semantics", "timeout_s": 11}]
    call = runner.calls[0]
    assert call["agent"].name == "NarrativeMentionSemanticsAgent"
    assert isinstance(call["agent"].output_type, StrictJsonOutputSchema)
    assert call["agent"].model is None
    assert "Label only the supplied token mention text" in call["agent"].instructions
    assert json.loads(call["input"])["mentions"][0]["event_id"] == "event-1"
    assert call["run_config"].workflow_name == "gmgn-twitter-intel.narrative_intel"
    assert call["run_config"].group_id == "event-1"
    assert call["run_config"].trace_metadata["stage"] == "mention_semantics"
    assert call["run_config"].trace_metadata["schema_version"] == "narrative_v1"


def test_narrative_client_summarizes_discussion_through_typed_agent():
    gateway = FakeGateway()
    target_id = "asset:solana:token:So11111111111111111111111111111111111111112"
    digest_payload = {
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
    runner = FakeRunner({"digest": digest_payload})
    client = OpenAIAgentsNarrativeIntelClient(
        api_key="sk-test",
        model="gpt-narrative",
        llm_gateway=gateway,
        timeout_seconds=11,
        runner=runner,
    )
    request = DiscussionDigestRequest(
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

    result = asyncio.run(client.summarize_discussion(run_id="run-digest-1", request=request))

    assert isinstance(result, DiscussionDigestResult)
    assert result.digest.headline_zh == "SOL 讨论从价格防守切到轮动叙事。"
    assert result.raw_response["digest"]["target_id"] == target_id
    assert result.agent_run_audit["output_hash"].startswith("sha256:")
    assert gateway.calls == [{"worker_name": "narrative_intel", "stage": "discussion_digest", "timeout_s": 11}]
    call = runner.calls[0]
    assert call["agent"].name == "TokenDiscussionDigestAgent"
    assert isinstance(call["agent"].output_type, StrictJsonOutputSchema)
    assert "Summarize only the supplied labeled mentions" in call["agent"].instructions
    assert json.loads(call["input"])["target_id"] == target_id
    assert call["run_config"].workflow_name == "gmgn-twitter-intel.narrative_intel"
    assert call["run_config"].group_id == target_id
    assert call["run_config"].trace_metadata["stage"] == "discussion_digest"
    assert call["run_config"].trace_metadata["window"] == "24h"
