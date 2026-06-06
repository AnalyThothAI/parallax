from __future__ import annotations

import pytest
from pydantic import ValidationError

from parallax.domains.news_intel.types.news_item_brief import (
    AffectedEntity,
    NewsItemBriefEntityLane,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
    TransmissionPath,
    default_news_item_brief_agent_config,
)


def test_default_news_item_brief_agent_config_uses_market_wide_validator_v2() -> None:
    config = default_news_item_brief_agent_config(model="gpt-5-mini", artifact_version_hash="artifact-v2")

    assert config.prompt_version == "news-item-brief-market-wide-v2"
    assert config.schema_version == "news_item_brief_market_v1"
    assert config.validator_version == "news_item_brief_validator_market_v2"


def test_news_item_brief_payload_uses_market_wide_entities() -> None:
    payload = NewsItemBriefPayload(
        status="ready",
        direction="mixed",
        decision_class="driver",
        event_type="earnings_guidance",
        title_zh="英伟达指引牵动 AI 半导体链",
        summary_zh="英伟达上调收入指引，市场关注 AI 半导体需求外溢。",
        market_read_zh="影响路径横跨美股、AI 半导体板块和宏观风险偏好。",
        market_domains=["us_equity", "ai_semiconductors", "macro_rates"],
        transmission_paths=[
            TransmissionPath(
                market_domain="ai_semiconductors",
                channel="earnings_revision",
                direction="bullish",
                strength="moderate",
                explanation_zh="公司指引改善可能带动 AI 算力链收入预期。",
                evidence_refs=["item:title"],
            )
        ],
        affected_entities=[
            AffectedEntity(
                label="NVIDIA",
                symbol="NVDA",
                name="NVIDIA",
                entity_type="equity",
                market_domain="us_equity",
                resolution_status="known_symbol",
                target_type="equity_symbol",
                target_id="ticker:NVDA",
                impact_direction="bullish",
                reason_zh="新闻文本直接提到 NVIDIA 指引。",
                evidence_refs=["item:title"],
            )
        ],
        evidence_refs=["item:title"],
    )

    assert payload.event_type == "earnings_guidance"
    assert payload.market_domains == ["us_equity", "ai_semiconductors", "macro_rates"]
    assert payload.affected_entities[0].entity_type == "equity"


def test_news_item_brief_payload_rejects_legacy_affected_assets_field() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="watch",
            summary_zh="事件摘要",
            market_read_zh="市场解读",
            bull_view={"strength": "moderate", "thesis_zh": "利多叙事", "evidence_refs": ["item:title"]},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            affected_assets=[],
            evidence_refs=["item:title"],
        )


def test_news_item_brief_input_packet_uses_entity_lanes() -> None:
    packet = NewsItemBriefInputPacket(
        packet_id="packet-1",
        news_item=NewsItemBriefNewsItem(news_item_id="item-1", title="SEC delays spot ETF decision"),
        entity_lanes=[
            NewsItemBriefEntityLane(
                entity_id="entity-sec",
                observed_label="SEC",
                display_name="U.S. Securities and Exchange Commission",
                entity_type="regulator",
                market_domain="regulation",
                role="mentioned",
                evidence_refs=["entity:entity-sec"],
            )
        ],
        market_scope=["regulation", "crypto"],
        agent_admission={"status": "eligible", "reason": "provider_score_high"},
        similarity={"exact_duplicate": False},
        material_delta={"status": "material"},
        prompt_version="prompt-v1",
        schema_version="schema-v1",
    )

    payload = packet.model_dump(mode="json")
    assert payload["entity_lanes"][0]["entity_type"] == "regulator"
    assert payload["market_scope"] == ["regulation", "crypto"]
    assert "token_lanes" not in payload


def test_news_item_brief_input_packet_rejects_legacy_token_lanes_field() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefInputPacket.model_validate(
            {
                "packet_id": "packet-legacy",
                "news_item": {"news_item_id": "item-1"},
                "token_lanes": [],
                "prompt_version": "prompt-v1",
                "schema_version": "schema-v1",
            }
        )


def test_news_item_brief_entity_type_is_hard_cut_to_market_wide_enum() -> None:
    with pytest.raises(ValidationError):
        AffectedEntity(
            label="Legacy",
            entity_type="equity_symbol",
            market_domain="us_equity",
        )
