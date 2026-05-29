from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gmgn_twitter_intel.integrations.model_execution.watchlist_summary_agent_client import (
    LiteLLMWatchlistSummaryClient,
    _coerce_summary_payload,
)
from gmgn_twitter_intel.platform.agent_execution import (
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)


class FakeAgentGateway:
    def __init__(self, output):
        self.output = output
        self.audit_calls = []
        self.execute_calls = []

    def model_for_lane(self, lane: str) -> str:
        assert lane == "watchlist.handle_summary"
        return "gpt-test"

    def request_audit(self, stage):
        self.audit_calls.append(stage)
        return AgentExecutionRequestAudit(
            model=self.model_for_lane(stage.lane),
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            execution_trace_id="trace-run-1",
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash="artifact:test",
            input_hash=stage.input_hash,
            trace_metadata={"handle": stage.group_id},
        )

    async def execute(self, stage, reservation=None):
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


def test_watchlist_summary_client_runs_summary_through_gateway():
    gateway = FakeAgentGateway(
        {
            "summary_zh": "账户围绕 SOL 客户端进展反复发声。",
            "topics": [],
            "residual_risks": [],
        }
    )
    client = LiteLLMWatchlistSummaryClient(agent_gateway=gateway)

    result = asyncio.run(
        client.summarize_handle(
            handle="watched",
            events=[],
            run_id="run-1",
            job={"handle": "watched", "attempt_count": 1},
            context={"window_days": 1},
        )
    )

    assert len(gateway.execute_calls) == 1
    stage = gateway.execute_calls[0]
    assert stage.lane == "watchlist.handle_summary"
    assert client.model == "gpt-test"
    assert stage.group_id == "watched"
    assert result["summary_zh"] == "账户围绕 SOL 客户端进展反复发声。"
    assert result["agent_run_audit"]["status"] == "done"


def test_watchlist_summary_client_rejects_compat_markdown_output():
    with pytest.raises(ValidationError):
        _coerce_summary_payload(
            """
**1. Coinbase 内部高管变动**
*   **描述**：Brian Armstrong 宣布辞去 0x 联合 CEO 职务，但保留董事会席位。
*   **事件数**：1
*   **Top Event IDs**：2d70702b-62cc-4300-8101-afa9a6d56da4
*   **关联标的**：0x
*   **置信度**：高
"""
        )


def test_watchlist_summary_client_rejects_topic_only_object():
    with pytest.raises(ValidationError):
        _coerce_summary_payload(
            {
                "title": "Solana P-Token",
                "description": "账号围绕 P-Token 质押叙事持续发声。",
                "event_count": 3,
                "top_event_ids": ["event-1", "event-2"],
                "symbols": ["P"],
                "confidence": 0.95,
            }
        )


def test_watchlist_summary_client_rejects_topic_array_string():
    with pytest.raises(ValidationError):
        _coerce_summary_payload(
            """
[
  {"title":"宏观风险","description":"霍尔木兹紧张推高能源风险。","event_count":2,"confidence":0.8}
]
"""
        )
