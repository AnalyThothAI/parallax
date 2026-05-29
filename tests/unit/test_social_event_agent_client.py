from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from gmgn_twitter_intel.integrations.model_execution.social_event_agent_client import LiteLLMSocialEventClient


class FakeAudit(BaseModel):
    lane: str
    stage: str
    usage: dict[str, Any]
    execution_started: bool
    status: str
    input_hash: str
    output_hash: str
    trace_metadata: dict[str, Any]


class FakeGateway:
    def __init__(self) -> None:
        self.requested_stage = None
        self.executed_stage = None

    def model_for_lane(self, lane: str) -> str:
        assert lane == "social.event_enrichment"
        return "qwen3.6"

    def request_audit(self, stage):
        self.requested_stage = stage
        return FakeAudit(
            lane=stage.lane,
            stage=stage.stage,
            usage={},
            execution_started=False,
            status="planned",
            input_hash=stage.input_hash,
            output_hash="",
            trace_metadata=stage.trace_metadata,
        )

    async def execute(self, stage, reservation=None):
        self.executed_stage = stage

        class Result:
            def __init__(self) -> None:
                self.final_output = {
                    "is_signal_event": True,
                    "event_type": "meme_phrase_seed",
                    "source_action": "posted",
                    "subject": "TROLL social flow",
                    "direction_hint": "attention_positive",
                    "attention_mechanism": "meme_phrase",
                    "impact_hint": 0.74,
                    "semantic_novelty_hint": 0.63,
                    "confidence": 0.9,
                    "anchor_terms": [
                        {
                            "term": "$TROLL social flow",
                            "role": "meme_phrase",
                            "evidence": "$TROLL social flow",
                        }
                    ],
                    "token_candidates": [
                        {
                            "symbol": "TROLL",
                            "project_name": None,
                            "chain": None,
                            "address": None,
                            "evidence": "$TROLL",
                            "confidence": 0.86,
                        }
                    ],
                    "semantic_risks": ["public_stream_coverage"],
                    "summary_zh": "TROLL 社交流正在加速。",
                }
                self.audit = FakeAudit(
                    lane=stage.lane,
                    stage=stage.stage,
                    usage={"input_tokens": 1},
                    execution_started=True,
                    status="done",
                    input_hash=stage.input_hash,
                    output_hash="sha256:out",
                    trace_metadata=stage.trace_metadata,
                )

        return Result()


def test_social_event_client_uses_agent_execution_gateway() -> None:
    gateway = FakeGateway()
    client = LiteLLMSocialEventClient(agent_gateway=gateway)

    result = asyncio.run(
        client.enrich_event(
            event={
                "event_id": "event-1",
                "author_handle": "smoke",
                "text_clean": "$TROLL social flow is accelerating.",
                "search_text": "$TROLL social flow is accelerating.",
            },
            entities=[],
            run_id="run-123",
            job={"job_id": "job-1", "job_type": "watched_social_event_extraction", "attempt_count": 1},
        )
    )

    stage = gateway.executed_stage
    assert stage.lane == "social.event_enrichment"
    assert stage.stage == "social_event"
    assert client.model == "qwen3.6"
    assert stage.workflow_name == "gmgn-twitter-intel.social_event_extraction"
    assert stage.agent_name == "SocialEventExtractionAgent"
    assert stage.group_id == "event-1"
    assert stage.trace_metadata == {
        "run_id": "run-123",
        "event_id": "event-1",
        "job_id": "job-1",
        "job_type": "watched_social_event_extraction",
        "attempt_count": 1,
    }
    assert result.event_type == "meme_phrase_seed"
    assert result.token_candidates[0].symbol == "TROLL"
    assert result.agent_run_audit["usage"] == {"input_tokens": 1}
    assert result.agent_run_audit["execution_started"] is True


def test_social_event_client_request_audit_delegates_to_gateway_and_returns_dict() -> None:
    gateway = FakeGateway()
    client = LiteLLMSocialEventClient(agent_gateway=gateway)

    audit = client.request_audit(
        event={"event_id": "event-fail", "search_text": "$FAIL"},
        entities=[{"entity_type": "cashtag", "normalized_value": "FAIL"}],
        run_id="run-fail",
        job={"job_id": "job-fail", "job_type": "watched_social_event_extraction", "attempt_count": 2},
    )

    assert gateway.requested_stage.lane == "social.event_enrichment"
    assert gateway.requested_stage.stage == "social_event"
    assert audit["execution_started"] is False
    assert audit["trace_metadata"]["event_id"] == "event-fail"
    assert audit["trace_metadata"]["attempt_count"] == 2
