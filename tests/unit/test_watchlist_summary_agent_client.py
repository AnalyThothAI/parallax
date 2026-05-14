from gmgn_twitter_intel.integrations.openai_agents.watchlist_summary_agent_client import _coerce_summary_payload


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
