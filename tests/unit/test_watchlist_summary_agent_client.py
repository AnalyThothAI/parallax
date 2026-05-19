from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import (
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)
from gmgn_twitter_intel.integrations.openai_agents.watchlist_summary_agent_client import (
    OpenAIAgentsWatchlistSummaryClient,
    _coerce_summary_payload,
)


class FakeAgentGateway:
    def __init__(self, output):
        self.output = output
        self.audit_calls = []
        self.execute_calls = []

    def request_audit(self, stage):
        self.audit_calls.append(stage)
        return AgentExecutionRequestAudit(
            model=stage.model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            sdk_trace_id="trace-run-1",
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash="artifact:test",
            input_hash=stage.input_hash,
            trace_metadata={"handle": stage.group_id},
        )

    async def execute(self, stage):
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
    client = OpenAIAgentsWatchlistSummaryClient(
        model="gpt-test",
        agent_gateway=gateway,
        max_turns=2,
    )

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
    assert stage.model == "gpt-test"
    assert stage.group_id == "watched"
    assert stage.max_turns == 2
    assert result["summary_zh"] == "账户围绕 SOL 客户端进展反复发声。"
    assert result["agent_run_audit"]["status"] == "done"


def test_watchlist_summary_client_parses_fenced_json_output():
    payload = _coerce_summary_payload(
        """
```json
{
  "summary_zh": "账户围绕 SOL 客户端进展反复发声。",
  "topics": [{
    "title": "SOL 客户端",
    "description": "Firedancer 进展被连续提及。",
    "event_count": 2,
    "top_event_ids": ["event-1"],
    "symbols": ["SOL"],
    "confidence": 0.82
  }],
  "residual_risks": []
}
```
"""
    )

    assert payload.summary_zh == "账户围绕 SOL 客户端进展反复发声。"
    assert payload.topics[0].title == "SOL 客户端"
    assert payload.topics[0].top_event_ids == ["event-1"]


def test_watchlist_summary_client_recovers_markdown_topic_output():
    payload = _coerce_summary_payload(
        """
**1. Coinbase 内部高管变动**
*   **描述**：Brian Armstrong 宣布辞去 0x 联合 CEO 职务，但保留董事会席位。
*   **事件数**：1
*   **Top Event IDs**：2d70702b-62cc-4300-8101-afa9a6d56da4
*   **关联标的**：0x
*   **置信度**：高

**2. 美国加密监管政策利好**
*   **描述**：转发内容高度评价数字资产市场清晰度法案听证会。
*   **事件数**：2
*   **Top Event IDs**：event-a,event-b
*   **关联标的**：BTC, ETH
*   **置信度**：0.7
"""
    )

    assert "Coinbase 内部高管变动" in payload.summary_zh
    assert len(payload.topics) == 2
    assert payload.topics[0].event_count == 1
    assert payload.topics[0].symbols == ["0x"]
    assert payload.topics[0].confidence == 0.85
    assert payload.topics[1].top_event_ids == ["event-a", "event-b"]


def test_watchlist_summary_client_wraps_single_topic_json_object():
    payload = _coerce_summary_payload(
        {
            "title": "Solana P-Token",
            "description": "账号围绕 P-Token 质押叙事持续发声。",
            "event_count": 3,
            "top_event_ids": ["event-1", "event-2"],
            "symbols": ["P"],
            "confidence": 0.95,
        }
    )

    assert payload.summary_zh == "Solana P-Token：账号围绕 P-Token 质押叙事持续发声。"
    assert payload.topics[0].event_count == 3
    assert payload.topics[0].symbols == ["P"]


def test_watchlist_summary_client_wraps_topic_json_array():
    payload = _coerce_summary_payload(
        """[
  {"title":"宏观风险","description":"霍尔木兹紧张推高能源风险。","event_count":2,"confidence":0.8}
]"""
    )

    assert payload.summary_zh == "宏观风险：霍尔木兹紧张推高能源风险。"
    assert payload.topics[0].confidence == 0.8
