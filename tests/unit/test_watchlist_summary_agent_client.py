from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.integrations.openai_agents.watchlist_summary_agent_client import (
    OpenAIAgentsWatchlistSummaryClient,
    _coerce_summary_payload,
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


def test_watchlist_summary_client_runs_summary_through_gateway():
    gateway = FakeGateway()
    runner = FakeRunner(
        {
            "summary_zh": "账户围绕 SOL 客户端进展反复发声。",
            "topics": [],
            "residual_risks": [],
        }
    )
    client = OpenAIAgentsWatchlistSummaryClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=gateway,
        timeout_seconds=9,
        runner=runner,
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

    assert gateway.calls == [{"worker_name": "handle_summary", "stage": "summary", "timeout_s": 9}]
    assert runner.calls[0]["run_config"].group_id == "watched"
    assert runner.calls[0]["run_config"].tracing_disabled is False
    assert result["summary_zh"] == "账户围绕 SOL 客户端进展反复发声。"


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
