from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_validation import (
    validate_news_item_brief_output,
)
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig
from parallax.platform.agent_hashing import json_sha256


def _agent_config() -> NewsItemBriefAgentConfig:
    return NewsItemBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def _crypto_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "title": "Exchange lists ABC perpetuals",
            "summary": "ABC perpetual contract will be available today.",
            "body_text": "The exchange says ABC perpetual contract support is live for eligible users.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
            "market_scope_json": ["crypto"],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[],
        token_mentions=[
            {
                "mention_id": "token-1",
                "observed_symbol": "ABC",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:abc",
                "display_symbol": "ABC",
                "display_name": "ABC Token",
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "event_type": "listing",
                "claim": "Exchange lists ABC perpetuals.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "ABC"}],
                "evidence_quote": "ABC perpetual contract support is live",
            }
        ],
        agent_config=_agent_config(),
    )


def _equity_macro_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-equity-macro",
            "title": "NVIDIA rallies as Treasury yields fall after CPI",
            "summary": "NVIDIA and AI semiconductor shares rose while CPI cooled and Treasury yields fell.",
            "body_text": "The CPI print lowered rate expectations and supported AI semiconductor risk appetite.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:equity-macro",
            "market_scope_json": ["us_equity", "ai_semiconductors", "macro_rates"],
            "agent_admission_json": {"status": "eligible", "reason": "market_wide_driver"},
        },
        entities=[
            {
                "entity_id": "entity-nvda",
                "raw_value": "NVIDIA",
                "normalized_value": "nvidia",
                "entity_type": "company",
                "confidence": 0.96,
            },
            {
                "entity_id": "entity-cpi",
                "raw_value": "CPI",
                "normalized_value": "cpi",
                "entity_type": "macro_factor",
                "confidence": 0.9,
            },
        ],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-cpi",
                "event_type": "macro_data",
                "claim": "CPI cooled and Treasury yields fell while NVIDIA rose.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "NVDA"}, {"label": "CPI"}],
                "evidence_quote": "CPI cooled and Treasury yields fell",
            }
        ],
        agent_config=_agent_config(),
    )


def _energy_geopolitics_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-hormuz",
            "title": "Iran warning shots near Strait of Hormuz lift oil risk for U.S. markets",
            "summary": (
                "Warning shots near the Strait of Hormuz increased concern over Gulf shipping, crude supply, "
                "and United States market sensitivity."
            ),
            "body_text": (
                "The report described military activity around the Strait of Hormuz, a key oil shipping route, "
                "and noted broader U.S. risk-asset sensitivity."
            ),
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:hormuz",
            "market_scope_json": ["energy_geopolitics", "commodity", "crypto"],
            "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        },
        entities=[
            {
                "entity_id": "entity-iran",
                "raw_value": "Iran",
                "normalized_value": "iran",
                "entity_type": "country",
                "confidence": 0.96,
            },
            {
                "entity_id": "entity-hormuz",
                "raw_value": "Strait of Hormuz",
                "normalized_value": "strait of hormuz",
                "entity_type": "macro_factor",
                "confidence": 0.91,
            },
            {
                "entity_id": "entity-us",
                "raw_value": "U.S.",
                "normalized_value": "united states",
                "entity_type": "country",
                "confidence": 0.94,
            },
        ],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-hormuz",
                "event_type": "geopolitical_supply",
                "claim": "Warning shots near the Strait of Hormuz increased crude supply risk.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [
                    {"label": "WTI crude", "market_domain": "commodity"},
                    {"label": "Bitcoin", "market_domain": "crypto"},
                ],
                "evidence_quote": "Strait of Hormuz increased concern over Gulf shipping and crude supply",
            }
        ],
        agent_config=_agent_config(),
    )


def _us_energy_firms_hormuz_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-hormuz-us-energy-firms",
            "title": (
                "Rosneft Chief Says US Energy Firms Gain From Strait Of Hormuz Closure Amid Global Oil "
                "Disruption"
            ),
            "summary": "The report links a potential Hormuz closure to global oil disruption.",
            "body_text": (
                "Rosneft's chief said US Energy Firms would gain from a Strait of Hormuz closure as global oil "
                "flows face disruption."
            ),
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:hormuz-us-energy-firms",
            "market_scope_json": ["energy_geopolitics", "commodity", "us_equity"],
            "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-hormuz-us-energy-firms",
                "event_type": "geopolitical_supply",
                "claim": "US Energy Firms could gain from a Strait of Hormuz closure.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [
                    {"label": "US Energy Firms", "market_domain": "us_equity"},
                    {"label": "WTI crude", "market_domain": "commodity"},
                    {"label": "Bitcoin", "market_domain": "crypto"},
                ],
                "evidence_quote": "US Energy Firms would gain from a Strait of Hormuz closure",
            }
        ],
        agent_config=_agent_config(),
    )


def _us_energy_firms_fact_only_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-hormuz-us-energy-firms-fact-only",
            "title": "Strait of Hormuz closure risk adds to global oil disruption debate",
            "summary": "The report discusses Hormuz closure risk and global oil disruption.",
            "body_text": "The source text describes shipping disruption scenarios around the Strait of Hormuz.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:hormuz-us-energy-firms-fact-only",
            "market_scope_json": ["energy_geopolitics", "commodity", "us_equity"],
            "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-hormuz-us-energy-firms-fact-only",
                "event_type": "geopolitical_supply",
                "claim": "US Energy Firms could gain from a Strait of Hormuz closure.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [
                    {"label": "US Energy Firms", "market_domain": "us_equity"},
                    {"label": "WTI crude", "market_domain": "commodity"},
                ],
                "evidence_quote": "US Energy Firms would gain from a Strait of Hormuz closure",
            }
        ],
        agent_config=_agent_config(),
    )


def _us_energy_firms_provider_only_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-hormuz-us-energy-firms-provider-only",
            "title": "Strait of Hormuz closure risk adds to global oil disruption debate",
            "summary": "The report discusses Hormuz closure risk and global oil disruption.",
            "body_text": "The source text describes shipping disruption scenarios around the Strait of Hormuz.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:hormuz-us-energy-firms-provider-only",
            "market_scope_json": ["energy_geopolitics", "commodity", "us_equity"],
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "partial",
                "direction": "bullish",
                "summary_en": "Provider summary says US Energy Firms could gain from a Hormuz closure.",
            },
            "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _crypto_market_scope_only_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-crypto-market-scope-only",
            "title": "Broad crypto market update without asset-specific support",
            "summary": "The report discusses crypto market conditions without naming a specific token.",
            "body_text": (
                "No provider token impact, fact target, entity lane, or asset-specific source text is present."
            ),
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:crypto-market-scope-only",
            "market_scope_json": ["crypto"],
            "agent_admission_json": {"status": "eligible", "reason": "market_wide_driver"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _provider_btc_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-provider-btc",
            "title": "Provider flags market impact",
            "summary": "The source text does not name the affected crypto asset directly.",
            "body_text": "Provider evidence supplies the token-specific impact.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:provider-btc",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "mixed",
            },
            "provider_token_impacts_json": [
                {"symbol": "BTC", "market_type": "cex", "score": 80, "signal": "proxy", "grade": "B"}
            ],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _provider_cl_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-provider-cl",
            "title": "Provider flags commodity impact",
            "summary": "The source text does not name the affected commodity directly.",
            "body_text": "Provider evidence supplies the commodity-specific impact.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:provider-cl",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "mixed",
            },
            "provider_token_impacts_json": [
                {"symbol": "CL", "market_type": "commodity", "score": 80, "signal": "proxy", "grade": "B"}
            ],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _provider_wlfi_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-provider-wlfi",
            "title": "Provider flags token impact",
            "summary": "The source text does not name the affected crypto asset directly.",
            "body_text": "Provider evidence supplies the token-specific impact.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:provider-wlfi",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "mixed",
            },
            "provider_token_impacts_json": [
                {"symbol": "WLFI", "market_type": "cex", "score": 82, "signal": "proxy", "grade": "B"}
            ],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _gold_commodity_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-gold",
            "title": "Gold futures rise as haven demand improves",
            "summary": "Gold climbed after investors moved into precious metals.",
            "body_text": "The commodity report focused on bullion and COMEX gold contracts.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:gold",
            "market_scope_json": ["commodity"],
            "agent_admission_json": {"status": "eligible", "reason": "market_wide_driver"},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-gold",
                "event_type": "commodity_move",
                "claim": "Gold futures rose on haven demand.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"label": "Gold", "market_domain": "commodity"}],
                "evidence_quote": "Gold climbed after investors moved into precious metals",
            }
        ],
        agent_config=_agent_config(),
    )


def _htx_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-htx",
            "title": "HTX lists new spot pair",
            "summary": "HTX said the spot market would open for eligible users.",
            "body_text": "The exchange notice came from HTX and described spot trading support.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:htx",
            "market_scope_json": ["crypto"],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[
            {
                "entity_id": "entity-htx",
                "raw_value": "HTX",
                "normalized_value": "htx",
                "entity_type": "company",
                "confidence": 0.96,
            }
        ],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )


def _ready_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "listing",
        "title_zh": "ABC 永续合约上线带来交易覆盖变化",
        "summary_zh": "交易所上线 ABC 永续合约，事件本身提高了该资产的可交易关注度。",
        "market_read_zh": "影响主要来自交易入口和衍生品关注度增加，但仍需核对流动性和真实成交反应。",
        "market_domains": ["crypto"],
        "transmission_paths": [
            {
                "market_domain": "crypto",
                "channel": "derivatives_access",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "永续合约上线扩大交易覆盖。",
                "evidence_refs": ["fact:fact-1"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "上线永续合约可能扩大 ABC 的交易覆盖面。",
            "evidence_refs": ["fact:fact-1", "entity:token-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "公告没有提供成交深度或持续需求证据。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "ABC",
                "symbol": "ABC",
                "name": "ABC Token",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:abc",
                "impact_direction": "bullish",
                "reason_zh": "输入 entity lane 直接提到 ABC。",
                "evidence_refs": ["entity:token-1"],
            }
        ],
        "watch_triggers": ["后续公告补充市场深度或交易量证据"],
        "invalidation_conditions": ["公告被撤回或 entity 身份被证伪"],
        "data_gaps": [],
        "evidence_refs": ["item:summary", "fact:fact-1", "entity:token-1"],
    }
    payload.update(overrides)
    return payload


def test_valid_ready_payload_is_publishable_and_hashes_normalized_output() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(payload=_ready_payload(), packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
    assert result.payload is not None
    assert result.output_hash == json_sha256(result.payload)


def test_validation_rejects_unknown_evidence_refs() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(evidence_refs=["item:summary", "fact:missing"]),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unknown_evidence_ref", "message": "fact:missing"} in result.errors


def test_validation_rejects_ready_without_source_backed_refs() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            evidence_refs=[],
            bull_view={"strength": "moderate", "thesis_zh": "上线永续合约扩大交易覆盖。", "evidence_refs": []},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            transmission_paths=[],
            affected_entities=[
                {
                    **_ready_payload()["affected_entities"][0],
                    "evidence_refs": [],
                }
            ],
        ),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {
        "code": "missing_ready_evidence_ref",
        "message": "ready output requires at least one valid evidence ref",
    } in result.errors


def test_validation_rejects_unsupported_entities() -> None:
    packet = _crypto_packet()
    payload = _ready_payload(
        affected_entities=[
            *_ready_payload()["affected_entities"],
            {
                "label": "XYZ",
                "symbol": "XYZ",
                "name": "Unsupported Token",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "resolution_status": "unknown",
                "target_type": "asset",
                "target_id": "asset:xyz",
                "impact_direction": "bullish",
                "reason_zh": "模型输出了输入中没有来源支撑的资产。",
                "evidence_refs": ["item:summary"],
            },
        ],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "XYZ"} in result.errors


def test_validation_rejects_fake_label_laundered_by_source_backed_symbol() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        market_domains=["energy_geopolitics", "commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "shipping_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "霍尔木兹扰动抬高原油供应风险。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "霍尔木兹扰动抬高原油供应风险。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "来源没有支持新占位实体。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "ABC crude proxy",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "模型把真实 CL 符号附加到来源中没有的占位实体。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "ABC crude proxy"} in result.errors


def test_validation_rejects_fake_target_id_laundered_by_source_backed_symbol() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        market_domains=["energy_geopolitics", "commodity", "crypto"],
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "risk_asset_sensitivity",
                "direction": "mixed",
                "strength": "weak",
                "explanation_zh": "来源支持 Bitcoin 作为风险资产敏感目标。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "来源支持 Bitcoin 作为风险资产敏感目标。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "来源没有支持模型给出的 target_id。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "Bitcoin",
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "target_type": "asset",
                "target_id": "asset:xyz",
                "impact_direction": "mixed",
                "reason_zh": "模型把来源支撑的 BTC 符号绑定到来源中没有的 target_id。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "Bitcoin"} in result.errors


@pytest.mark.parametrize("symbol", ["asset", "listing", "crypto"])
def test_validation_rejects_invented_entities_named_after_generic_classification_keys(symbol: str) -> None:
    packet = _crypto_packet()
    payload = _ready_payload(
        affected_entities=[
            {
                "label": f"Invented {symbol}",
                "symbol": symbol,
                "name": f"Invented {symbol}",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "resolution_status": "unknown",
                "target_type": "asset",
                "target_id": f"invented:{symbol}",
                "impact_direction": "bullish",
                "reason_zh": "模型输出了 generic 分类词，不是来源支撑的真实实体。",
                "evidence_refs": ["item:summary"],
            }
        ],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": f"Invented {symbol}"} in result.errors


def test_validation_rejects_commodity_proxy_when_packet_does_not_source_commodity_domain() -> None:
    packet = _crypto_packet()
    payload = _ready_payload(
        market_domains=["commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "payload 自称 commodity 传导，但 packet 没有 commodity 来源支撑。",
                "evidence_refs": ["item:summary"],
            }
        ],
        affected_entities=[
            {
                "label": "WTI原油期货",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "payload 自行引入了 commodity proxy。",
                "evidence_refs": ["item:summary"],
            }
        ],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "WTI原油期货"} in result.errors


def test_validation_rejects_oil_proxy_when_packet_only_sources_gold_commodity() -> None:
    packet = _gold_commodity_packet()
    payload = _ready_payload(
        direction="bullish",
        decision_class="driver",
        event_type="commodity_move",
        market_domains=["commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "haven_demand",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "来源只支持黄金商品走势。",
                "evidence_refs": ["fact:fact-gold"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "来源只支持黄金商品走势。",
            "evidence_refs": ["fact:fact-gold"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "来源没有支持 WTI 或 CL。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "WTI原油期货",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "模型把黄金商品范围泛化成原油代理。",
                "evidence_refs": ["fact:fact-gold"],
            }
        ],
        evidence_refs=["item:summary", "fact:fact-gold"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "WTI原油期货"} in result.errors


def test_validation_rejects_btc_proxy_when_only_crypto_market_scope_is_source_backed() -> None:
    packet = _crypto_market_scope_only_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="market_update",
        market_domains=["crypto"],
        bull_view={
            "strength": "weak",
            "thesis_zh": "来源只有 broad crypto market scope。",
            "evidence_refs": ["item:summary"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "来源没有 BTC 或 Bitcoin 证据。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "market_beta",
                "direction": "mixed",
                "strength": "weak",
                "explanation_zh": "市场范围是 crypto，但来源没有 BTC 或 Bitcoin 证据。",
                "evidence_refs": ["item:summary"],
            }
        ],
        affected_entities=[
            {
                "label": "Bitcoin",
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "模型仅凭 crypto market_scope 插入了 BTC。",
                "evidence_refs": ["item:summary"],
            }
        ],
        evidence_refs=["item:summary"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "Bitcoin"} in result.errors


def test_validation_allows_btc_proxy_when_provider_token_impact_sources_symbol() -> None:
    packet = _provider_btc_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 BTC。",
            "evidence_refs": ["provider:token:BTC"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider token impact 仍需后续市场反应确认。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "provider token impact 明确给出 BTC。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        affected_entities=[
            {
                "label": "Bitcoin",
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "provider token impact 明确给出 BTC。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:BTC"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


@pytest.mark.parametrize("label", ["Market Token", "Provider Token", "Impact Token", "Source Token"])
def test_validation_rejects_source_word_label_laundered_by_real_provider_symbol(label: str) -> None:
    packet = _provider_btc_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 BTC。",
            "evidence_refs": ["provider:token:BTC"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "来源没有支持伪造展示标签。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "provider token impact 明确给出 BTC，但未支持伪造展示标签。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        affected_entities=[
            {
                "label": label,
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "模型把普通来源词与真实 BTC 符号拼成伪造资产标签。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:BTC"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": label} in result.errors


@pytest.mark.parametrize("label", ["WLFI Token", "WLFI代币"])
def test_validation_allows_provider_token_label_with_generic_descriptor(label: str) -> None:
    packet = _provider_wlfi_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 WLFI。",
            "evidence_refs": ["provider:token:WLFI"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider token impact 仍需后续市场反应确认。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "provider token impact 明确给出 WLFI。",
                "evidence_refs": ["provider:token:WLFI"],
            }
        ],
        affected_entities=[
            {
                "label": label,
                "symbol": "WLFI",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "provider token impact 明确给出 WLFI。",
                "evidence_refs": ["provider:token:WLFI"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:WLFI"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_source_backed_exchange_label_with_generic_descriptor() -> None:
    packet = _htx_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="listing",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "来源直接提到 HTX。",
            "evidence_refs": ["entity:entity-htx"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "公告没有提供成交深度或持续需求证据。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "exchange_listing",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "来源直接提到 HTX 交易入口。",
                "evidence_refs": ["entity:entity-htx"],
            }
        ],
        affected_entities=[
            {
                "label": "HTX交易所",
                "symbol": "HTX",
                "entity_type": "company",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "entity lane 直接提到 HTX。",
                "evidence_refs": ["entity:entity-htx"],
            }
        ],
        evidence_refs=["item:summary", "entity:entity-htx"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


@pytest.mark.parametrize("label", ["Bitcoin Token", "比特币现货"])
def test_validation_allows_provider_btc_label_with_generic_descriptor(label: str) -> None:
    packet = _provider_btc_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 BTC。",
            "evidence_refs": ["provider:token:BTC"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider token impact 仍需后续市场反应确认。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "provider token impact 明确给出 BTC。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        affected_entities=[
            {
                "label": label,
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "provider token impact 明确给出 BTC。",
                "evidence_refs": ["provider:token:BTC"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:BTC"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_provider_cl_proxy_when_provider_sources_cl() -> None:
    packet = _provider_cl_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["commodity"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 CL。",
            "evidence_refs": ["provider:token:CL"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider token impact 仍需后续市场反应确认。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "provider_commodity_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "provider token impact 明确给出 CL。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        affected_entities=[
            {
                "label": "WTI crude futures",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "mixed",
                "reason_zh": "provider token impact 明确给出 CL。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:CL"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_rejects_commodity_provider_symbol_as_crypto_entity() -> None:
    packet = _provider_cl_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 CL commodity，不支持 crypto 资产。",
            "evidence_refs": ["provider:token:CL"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider impact 的 market_type 是 commodity。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "payload 试图把 commodity provider symbol 当作 crypto 资产。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        affected_entities=[
            {
                "label": "CL Token",
                "symbol": "CL",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "模型把 commodity provider impact 泛化为 crypto token。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:CL"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "CL Token"} in result.errors


def test_validation_rejects_exact_commodity_provider_symbol_as_crypto_entity() -> None:
    packet = _provider_cl_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 CL commodity，不支持 crypto 资产。",
            "evidence_refs": ["provider:token:CL"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider impact 的 market_type 是 commodity。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "crypto",
                "channel": "provider_token_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "payload 试图把 commodity provider symbol 当作 crypto 资产。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        affected_entities=[
            {
                "label": "CL",
                "symbol": "CL",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "模型把 commodity provider impact 泛化为 crypto token。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:CL"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "CL"} in result.errors


def test_validation_rejects_commodity_provider_symbol_as_crypto_entity_with_mixed_payload_domains() -> None:
    packet = _provider_cl_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="provider_signal",
        market_domains=["crypto", "commodity"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "provider token impact 明确给出 CL commodity，不支持 crypto 资产。",
            "evidence_refs": ["provider:token:CL"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "provider impact 的 market_type 是 commodity。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "provider_commodity_impact",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "commodity provider symbol 不能给 crypto affected entity 背书。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        affected_entities=[
            {
                "label": "CL Token",
                "symbol": "CL",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "模型把 commodity provider impact 泛化为 crypto token。",
                "evidence_refs": ["provider:token:CL"],
            }
        ],
        evidence_refs=["item:summary", "provider:token:CL"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "CL Token"} in result.errors


def test_validation_allows_oil_proxy_when_packet_sources_crude_risk() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        market_domains=["commodity"],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "来源明确提到 crude supply risk。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道未证明供应已经中断。",
            "evidence_refs": ["item:summary"],
        },
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "shipping_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "霍尔木兹扰动抬高原油供应风险。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        affected_entities=[
            {
                "label": "WTI原油期货",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "来源明确提到 crude supply risk。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


@pytest.mark.parametrize(
    "phrase",
    [
        "建议开仓做多 ABC，并使用 5 倍杠杆。",
        "可以卖出 ABC，并设置止损和止盈。",
        "long this after the listing and use a 5x leverage order.",
        "Recommended position size is 5% with a target price.",
    ],
)
def test_validation_rejects_trading_instruction_language(phrase: str) -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "trading_instruction" for error in result.errors)


@pytest.mark.parametrize(
    "phrase",
    [
        "open interest 上升说明衍生品关注度增加，但方向仍需成交确认。",
        "Deleveraging and liquidations could increase near-term volatility.",
        "现有杠杆头寸的清算风险可能放大 sell pressure。",
        "The event may draw derivatives attention without proving spot demand.",
    ],
)
def test_validation_allows_descriptive_derivatives_mechanics(phrase: str) -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_valid_equity_and_macro_payload_is_publishable() -> None:
    packet = _equity_macro_packet()
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "macro_data",
        "title_zh": "CPI 降温支撑 AI 半导体风险偏好",
        "summary_zh": "CPI 降温和美债收益率回落，与 NVIDIA 及 AI 半导体上涨同向出现。",
        "market_read_zh": "宏观利率路径通过贴现率和成长股风险偏好传导到 AI 半导体板块。",
        "market_domains": ["macro_rates", "us_equity", "ai_semiconductors"],
        "transmission_paths": [
            {
                "market_domain": "macro_rates",
                "channel": "discount_rate",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "CPI 降温压低收益率预期，改善成长股贴现率叙事。",
                "evidence_refs": ["fact:fact-cpi"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "收益率回落支持 AI 半导体估值弹性。",
            "evidence_refs": ["fact:fact-cpi", "entity:entity-nvda"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "单次 CPI 不能证明需求或盈利持续改善。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "NVIDIA",
                "symbol": "NVDA",
                "name": "NVIDIA",
                "entity_type": "equity",
                "market_domain": "us_equity",
                "impact_direction": "bullish",
                "reason_zh": "新闻和 entity lane 均提到 NVIDIA。",
                "evidence_refs": ["entity:entity-nvda"],
            },
            {
                "label": "CPI",
                "entity_type": "macro_factor",
                "market_domain": "macro_rates",
                "impact_direction": "bullish",
                "reason_zh": "CPI 是本次宏观触发因素。",
                "evidence_refs": ["entity:entity-cpi"],
            },
        ],
        "watch_triggers": ["后续收益率和 AI 半导体成交是否延续"],
        "invalidation_conditions": ["后续通胀数据重新抬升利率预期"],
        "data_gaps": [],
        "evidence_refs": ["item:summary", "fact:fact-cpi", "entity:entity-nvda", "entity:entity-cpi"],
    }

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_source_backed_market_wide_proxy_entities() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹海峡扰动抬高原油供应风险",
        summary_zh="伊朗相关警告射击提升了市场对海湾航运和原油供应的担忧。",
        market_read_zh="霍尔木兹海峡扰动通过原油供应风险、通胀预期和风险资产情绪传导到跨市场定价。",
        market_domains=["energy_geopolitics", "commodity", "crypto"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "shipping_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "海湾航运风险提升原油供应风险溢价。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
            {
                "market_domain": "crypto",
                "channel": "risk_asset_sensitivity",
                "direction": "mixed",
                "strength": "weak",
                "explanation_zh": "能源冲击可能影响风险资产情绪和美元流动性预期。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "霍尔木兹海峡扰动抬高原油供给风险和通胀尾部风险。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道未证明供应已经中断，影响可能停留在风险溢价。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "WTI原油期货",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "fact lane 将原油供应风险列为受影响目标。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
            {
                "label": "比特币",
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "fact lane 将 Bitcoin 列为风险资产敏感目标。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
            {
                "label": "美国",
                "entity_type": "country",
                "market_domain": "energy_geopolitics",
                "impact_direction": "mixed",
                "reason_zh": "霍尔木兹风险通过能源价格和通胀预期影响美国市场。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
        ],
        watch_triggers=["后续航运中断证据、油价和风险资产波动是否扩大"],
        invalidation_conditions=["相关军事活动降级或航运风险被证伪"],
        data_gaps=[],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_source_backed_translated_us_energy_sector_label() -> None:
    packet = _us_energy_firms_hormuz_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹关闭情境下美国能源企业或受益",
        summary_zh="来源明确称 US Energy Firms 可能从霍尔木兹海峡关闭和全球原油扰动中受益。",
        market_read_zh="受益方来自来源文本直接点名的美国能源企业，传导仍取决于实际航运中断和油价反应。",
        market_domains=["energy_geopolitics", "commodity", "us_equity"],
        transmission_paths=[
            {
                "market_domain": "energy_geopolitics",
                "channel": "shipping_disruption",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "来源将霍尔木兹关闭与全球原油扰动联系起来。",
                "evidence_refs": ["item:title"],
            },
            {
                "market_domain": "us_equity",
                "channel": "energy_sector_relative_benefit",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "来源文本明确称 US Energy Firms 可能受益。",
                "evidence_refs": ["item:body_excerpt"],
            },
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "如果霍尔木兹关闭推高能源供给风险，美国能源企业可能获得相对受益叙事。",
            "evidence_refs": ["item:title", "item:body_excerpt"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道仍是情境表述，未证明航运已经中断或企业盈利已经改变。",
            "evidence_refs": ["item:body_excerpt"],
        },
        affected_entities=[
            {
                "label": "美国能源企业",
                "entity_type": "sector",
                "market_domain": "energy_geopolitics",
                "impact_direction": "bullish",
                "reason_zh": "来源文本明确提到 US Energy Firms。",
                "evidence_refs": ["item:title"],
            },
            {
                "label": "U.S. Energy Equities (sector proxy)",
                "entity_type": "sector",
                "market_domain": "us_equity",
                "impact_direction": "bullish",
                "reason_zh": "来源文本明确提到 US Energy Firms。",
                "evidence_refs": ["item:body_excerpt"],
            },
        ],
        watch_triggers=["是否出现实际霍尔木兹航运关闭、油价跳升或美国能源股相对强势"],
        invalidation_conditions=["航运扰动降级，或来源观点被后续事实证伪"],
        data_gaps=[],
        evidence_refs=["item:title", "item:body_excerpt"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_translated_us_energy_sector_label_from_fact_evidence() -> None:
    packet = _us_energy_firms_fact_only_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹关闭情境下美国能源企业或受益",
        summary_zh="fact evidence 明确称 US Energy Firms 可能从霍尔木兹关闭中受益。",
        market_read_zh="受益方来自 fact lane 直接点名的美国能源企业，传导仍取决于实际航运中断和油价反应。",
        market_domains=["energy_geopolitics", "commodity", "us_equity"],
        transmission_paths=[
            {
                "market_domain": "us_equity",
                "channel": "energy_sector_relative_benefit",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "fact lane 明确称 US Energy Firms 可能受益。",
                "evidence_refs": ["fact:fact-hormuz-us-energy-firms-fact-only"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "如果霍尔木兹关闭推高能源供给风险，美国能源企业可能获得相对受益叙事。",
            "evidence_refs": ["fact:fact-hormuz-us-energy-firms-fact-only"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道仍是情境表述，未证明航运已经中断或企业盈利已经改变。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "美国能源企业",
                "entity_type": "sector",
                "market_domain": "energy_geopolitics",
                "impact_direction": "bullish",
                "reason_zh": "fact lane 明确提到 US Energy Firms。",
                "evidence_refs": ["fact:fact-hormuz-us-energy-firms-fact-only"],
            }
        ],
        watch_triggers=["是否出现实际霍尔木兹航运关闭、油价跳升或美国能源股相对强势"],
        invalidation_conditions=["航运扰动降级，或 fact evidence 被后续事实证伪"],
        data_gaps=[],
        evidence_refs=["item:summary", "fact:fact-hormuz-us-energy-firms-fact-only"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_translated_us_energy_sector_label_from_provider_summary() -> None:
    packet = _us_energy_firms_provider_only_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹关闭情境下美国能源企业或受益",
        summary_zh="provider summary 明确称 US Energy Firms 可能从霍尔木兹关闭中受益。",
        market_read_zh="受益方来自 provider summary 直接点名的美国能源企业，传导仍取决于实际航运中断和油价反应。",
        market_domains=["energy_geopolitics", "commodity", "us_equity"],
        transmission_paths=[
            {
                "market_domain": "us_equity",
                "channel": "energy_sector_relative_benefit",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "provider summary 明确称 US Energy Firms 可能受益。",
                "evidence_refs": ["provider:signal"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "如果霍尔木兹关闭推高能源供给风险，美国能源企业可能获得相对受益叙事。",
            "evidence_refs": ["provider:signal"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道仍是情境表述，未证明航运已经中断或企业盈利已经改变。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "美国能源企业",
                "entity_type": "sector",
                "market_domain": "energy_geopolitics",
                "impact_direction": "bullish",
                "reason_zh": "provider summary 明确提到 US Energy Firms。",
                "evidence_refs": ["provider:signal"],
            }
        ],
        watch_triggers=["是否出现实际霍尔木兹航运关闭、油价跳升或美国能源股相对强势"],
        invalidation_conditions=["航运扰动降级，或 provider signal 被后续事实证伪"],
        data_gaps=[],
        evidence_refs=["item:summary", "provider:signal"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_rejects_translated_us_energy_sector_label_without_explicit_source_text() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹海峡扰动抬高原油供应风险",
        summary_zh="报道提到霍尔木兹、原油供应和美国市场敏感性，但没有点名美国能源企业。",
        market_read_zh="霍尔木兹扰动可能影响原油供应风险和风险资产情绪，但来源未明确支持美国能源企业标签。",
        market_domains=["energy_geopolitics", "commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "shipping_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "海湾航运风险提升原油供应风险溢价。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "霍尔木兹海峡扰动抬高原油供给风险。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道未证明供应已经中断。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "美国能源企业",
                "entity_type": "sector",
                "market_domain": "energy_geopolitics",
                "impact_direction": "bullish",
                "reason_zh": "模型将原油地缘政治新闻泛化为美国能源企业受益。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        watch_triggers=["后续航运中断证据和油价波动是否扩大"],
        invalidation_conditions=["相关军事活动降级或航运风险被证伪"],
        data_gaps=[],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert result.errors == [{"code": "unsupported_entity", "message": "美国能源企业"}]


def test_validation_rejects_invented_synthetic_market_proxy_ticker() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        direction="mixed",
        decision_class="driver",
        event_type="geopolitical_supply",
        title_zh="霍尔木兹海峡扰动抬高原油供应风险",
        summary_zh="伊朗相关警告射击提升了市场对海湾航运和原油供应的担忧。",
        market_read_zh="霍尔木兹海峡扰动通过原油供应风险和风险资产情绪传导到跨市场定价。",
        market_domains=["energy_geopolitics", "commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "shipping_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "海湾航运风险提升原油供应风险溢价。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        bull_view={
            "strength": "moderate",
            "thesis_zh": "霍尔木兹海峡扰动抬高原油供给风险。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        bear_view={
            "strength": "weak",
            "thesis_zh": "报道未证明供应已经中断。",
            "evidence_refs": ["item:summary"],
        },
        affected_entities=[
            {
                "label": "XYZ-CL原油衍生品",
                "symbol": "XYZ-CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "模型输出了输入中没有来源支撑的合成代理标的。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        watch_triggers=["后续航运中断证据和油价波动是否扩大"],
        invalidation_conditions=["相关军事活动降级或航运风险被证伪"],
        data_gaps=[],
        evidence_refs=["item:summary", "fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert result.errors == [{"code": "unsupported_entity", "message": "XYZ-CL原油衍生品"}]


def test_validation_rejects_unexpected_tool_or_handoff_audit() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(),
        packet=packet,
        audit={"tool_calls": [{"name": "web"}], "handoffs": []},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unexpected_agent_action", "message": "tool_calls"} in result.errors
