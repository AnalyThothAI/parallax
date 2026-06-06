# News Brief Market-Wide Validator Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `news_item_brief` 在 market-wide 新闻上被 `unsupported_entity` 误杀的问题，让能源、宏观、美股、监管、crypto 等高分新闻能够生成 source-backed brief，同时继续拦截凭空编造的资产、ticker、合约和交易建议。

**Architecture:** 保持 agent harness 原则：LLM 只产出 JSON，确定性 validator 决定是否 publishable。新增一个小型 deterministic entity support 层，把 packet 中的 entity lanes、fact lanes、正文 token、market_scope、provider evidence 转成可验证的 entity/support key；prompt 只指导模型使用这些可验证实体或受控 market proxy，不引入兼容性字段、不恢复旧 token-only 逻辑。版本 hard cut：只 bump prompt/validator contract，schema 不变。

**Tech Stack:** Python 3.13, Pydantic v2, pytest, ruff, PostgreSQL/Docker runtime, Parallax agent execution harness.

---

## File Structure

- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
  - Replace narrow `_source_backed_entity_labels()` check with market-wide support helper.
  - Keep evidence-ref, no-tool-action, no-trading-instruction checks unchanged.

- Create: `src/parallax/domains/news_intel/services/news_item_brief_entity_support.py`
  - Own deterministic support-key generation and affected-entity validation.
  - No DB access, no LLM calls, no external lookups.

- Modify: `src/parallax/domains/news_intel/prompts/news_item_brief.md`
  - Tell the model to prefer packet entity lanes.
  - Allow controlled market proxies only when supported by packet `market_scope` / transmission evidence.
  - Forbid invented synthetic labels like `XYZ-CL`, fake tickers, or unresolved target ids.

- Modify: `src/parallax/domains/news_intel/_constants.py`
  - Bump `NEWS_ITEM_BRIEF_PROMPT_VERSION` to `news-item-brief-market-wide-v2`.
  - Bump `NEWS_ITEM_BRIEF_VALIDATOR_VERSION` to `news_item_brief_validator_market_v2`.
  - Do not bump `NEWS_ITEM_BRIEF_SCHEMA_VERSION`; payload schema is unchanged.

- Modify: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
  - Add failing tests for real production failure classes: WTI crude, Bitcoin as risk proxy, U.S./Iran country labels, and invented synthetic contract rejection.

- Modify: `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
  - Assert stage uses bumped prompt/validator versions through the default config.

- Optional docs touch: `src/parallax/domains/news_intel/ARCHITECTURE.md`
  - One paragraph clarifying brief validation is market-wide deterministic support, not crypto-only entity matching.

---

### Task 1: Reproduce Market-Wide Validator Failures

**Files:**
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`

- [ ] **Step 1: Add an energy/geopolitics packet fixture**

Append this helper after `_equity_macro_packet()`:

```python
def _energy_geopolitics_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-hormuz",
            "title": "Iran warning shots near Strait of Hormuz lift oil risk",
            "summary": "Warning shots near the Strait of Hormuz increased concern over Gulf shipping and crude supply.",
            "body_text": (
                "The report described military activity around the Strait of Hormuz, a key oil shipping route, "
                "and noted broader risk-asset sensitivity."
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
```

- [ ] **Step 2: Add the failing market proxy acceptance test**

Append this test before `test_validation_rejects_unexpected_tool_or_handoff_audit()`:

```python
def test_validation_allows_source_backed_market_wide_proxy_entities() -> None:
    packet = _energy_geopolitics_packet()
    payload = {
        "status": "ready",
        "direction": "mixed",
        "decision_class": "driver",
        "event_type": "geopolitical_supply",
        "title_zh": "霍尔木兹风险抬升原油与风险资产波动",
        "summary_zh": "伊朗相关警告射击报道提高了海湾航运和原油供应风险。",
        "market_read_zh": "传导主要来自能源供应风险和风险资产避险情绪，方向仍取决于后续是否影响航运。",
        "market_domains": ["energy_geopolitics", "commodity", "crypto"],
        "transmission_paths": [
            {
                "market_domain": "commodity",
                "channel": "supply_disruption",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "霍尔木兹相关风险会影响原油供应风险溢价。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
            {
                "market_domain": "crypto",
                "channel": "risk_sentiment",
                "direction": "mixed",
                "strength": "weak",
                "explanation_zh": "地缘冲突可能影响比特币等风险资产情绪，但来源没有给出成交或链上确认。",
                "evidence_refs": ["item:summary"],
            },
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "供应风险溢价可能支撑原油相关资产。",
            "evidence_refs": ["fact:fact-hormuz"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "报道本身还没有证明航运中断或实际供应损失。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "WTI原油期货",
                "symbol": "CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "来源提到原油供应风险，WTI 原油是受控商品代理。",
                "evidence_refs": ["fact:fact-hormuz"],
            },
            {
                "label": "比特币",
                "symbol": "BTC",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "impact_direction": "mixed",
                "reason_zh": "来源描述地缘风险，crypto 仅作为风险情绪代理，强度较弱。",
                "evidence_refs": ["item:summary"],
            },
            {
                "label": "美国",
                "entity_type": "country",
                "market_domain": "energy_geopolitics",
                "impact_direction": "neutral",
                "reason_zh": "新闻语境涉及地缘冲突和海湾风险，国家标签用于宏观地缘分类。",
                "evidence_refs": ["item:title"],
            },
        ],
        "watch_triggers": ["后续是否出现航运中断、油价跳升或官方确认"],
        "invalidation_conditions": ["事件被澄清为误报或未影响航运"],
        "data_gaps": [{"description_zh": "来源没有提供实际航运中断或成交反应。", "severity": "medium"}],
        "evidence_refs": ["item:title", "item:summary", "fact:fact-hormuz"],
    }

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
```

- [ ] **Step 3: Add invented synthetic ticker rejection test**

Append this test after the previous one:

```python
def test_validation_rejects_invented_synthetic_market_proxy_ticker() -> None:
    packet = _energy_geopolitics_packet()
    payload = _ready_payload(
        market_domains=["commodity"],
        transmission_paths=[
            {
                "market_domain": "commodity",
                "channel": "supply_disruption",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "霍尔木兹风险影响原油供应风险溢价。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        affected_entities=[
            {
                "label": "XYZ-CL原油衍生品",
                "symbol": "XYZ-CL",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "impact_direction": "bullish",
                "reason_zh": "模型编造了一个不存在于输入中的合约标签。",
                "evidence_refs": ["fact:fact-hormuz"],
            }
        ],
        evidence_refs=["fact:fact-hormuz"],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "XYZ-CL原油衍生品"} in result.errors
```

- [ ] **Step 4: Run only the new tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_allows_source_backed_market_wide_proxy_entities tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_rejects_invented_synthetic_market_proxy_ticker -q
```

Expected:

```text
1 failed, 1 passed
```

The first test should fail with `unsupported_entity` for `WTI原油期货`, `比特币`, or `美国`.

- [ ] **Step 5: Commit failing reproduction tests**

```bash
git add tests/unit/domains/news_intel/test_news_item_brief_validation.py
git commit -m "test: reproduce market-wide news brief entity validation"
```

---

### Task 2: Add Deterministic Market-Wide Entity Support

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_brief_entity_support.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`

- [ ] **Step 1: Create entity support module**

Create `src/parallax/domains/news_intel/services/news_item_brief_entity_support.py`:

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefInputPacket

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,31}")
_SYNTHETIC_PLACEHOLDER_RE = re.compile(r"\b(?:XYZ|ABCDEF|TEST)[-_]?[A-Z0-9]{1,12}\b", re.I)

_DOMAIN_PROXY_ALIASES: dict[str, tuple[str, ...]] = {
    "commodity": (
        "wti",
        "cl",
        "crude",
        "crudeoil",
        "oil",
        "wti crude",
        "wti oil",
        "wti原油",
        "wti原油期货",
        "原油",
        "原油期货",
        "布伦特原油",
        "brent",
    ),
    "energy_geopolitics": (
        "iran",
        "israel",
        "us",
        "usa",
        "u.s.",
        "unitedstates",
        "united states",
        "美国",
        "伊朗",
        "以色列",
        "霍尔木兹",
        "霍尔木兹海峡",
        "中东地缘政治风险",
        "geopolitical risk",
        "strait of hormuz",
    ),
    "crypto": (
        "btc",
        "bitcoin",
        "比特币",
        "crypto",
        "加密资产",
        "加密市场",
    ),
    "macro_rates": (
        "treasury yields",
        "us treasury",
        "美债收益率",
        "利率",
        "美元",
        "美元指数",
        "dxy",
        "cpi",
        "通胀",
    ),
    "us_equity": (
        "s&p500",
        "sp500",
        "nasdaq",
        "qqq",
        "美股",
        "标普500",
        "纳斯达克",
    ),
    "ai_semiconductors": (
        "nvidia",
        "nvda",
        "ai semiconductor",
        "ai semiconductors",
        "ai半导体",
        "半导体",
    ),
    "regulation": (
        "sec",
        "cftc",
        "fed",
        "regulator",
        "监管",
        "监管机构",
    ),
    "fx": (
        "usd",
        "dxy",
        "美元",
        "美元指数",
        "外汇",
        "fx",
    ),
}


@dataclass(frozen=True, slots=True)
class EntitySupportDecision:
    supported: bool
    reason: str


def validate_affected_entity_support(
    entity: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    payload: Mapping[str, Any],
) -> EntitySupportDecision:
    labels = _entity_labels(entity)
    if _contains_synthetic_placeholder(labels):
        return EntitySupportDecision(supported=False, reason="synthetic_placeholder")

    supported = source_backed_entity_keys(packet)
    if labels & supported:
        return EntitySupportDecision(supported=True, reason="packet_key")

    domain = _norm(entity.get("market_domain"))
    if domain and domain in _payload_or_packet_domains(packet=packet, payload=payload):
        domain_aliases = {_norm(value) for value in _DOMAIN_PROXY_ALIASES.get(domain, ())}
        if labels & domain_aliases:
            return EntitySupportDecision(supported=True, reason=f"domain_proxy:{domain}")

    return EntitySupportDecision(supported=False, reason="unsupported")


def source_backed_entity_keys(packet: NewsItemBriefInputPacket) -> set[str]:
    labels: set[str] = set()
    text_fields = [
        packet.news_item.title,
        packet.news_item.summary,
        packet.news_item.body_excerpt,
    ]
    for field in text_fields:
        labels.update(_text_keys(field))

    for entity in packet.entity_lanes:
        labels.update(
            _string_keys(
                entity.entity_id,
                entity.observed_label,
                entity.display_symbol,
                entity.display_name,
                entity.target_id,
                entity.target_type,
                entity.market_domain,
            )
        )
        for target in entity.candidate_targets:
            labels.update(_mapping_value_keys(target))

    for fact in packet.fact_lanes:
        labels.update(_text_keys(fact.claim))
        labels.update(_text_keys(fact.evidence_quote))
        labels.update(_string_keys(fact.event_type))
        for target in fact.affected_targets:
            labels.update(_mapping_value_keys(target))

    if packet.provider_signal_evidence is not None:
        provider = packet.provider_signal_evidence
        labels.update(_string_keys(provider.provider, provider.direction, provider.signal, provider.grade))
        labels.update(_text_keys(provider.summary_zh))
        labels.update(_text_keys(provider.summary_en))
        for impact in provider.token_impacts:
            labels.update(_string_keys(impact.symbol, impact.market_type, impact.signal, impact.direction))

    labels.update(_string_keys(*packet.market_scope))
    return {label for label in labels if label}


def _payload_or_packet_domains(*, packet: NewsItemBriefInputPacket, payload: Mapping[str, Any]) -> set[str]:
    domains = {_norm(domain) for domain in packet.market_scope}
    domains.update(_norm(domain) for domain in payload.get("market_domains") or [] if isinstance(domain, str))
    for path in payload.get("transmission_paths") or []:
        if isinstance(path, Mapping):
            domains.add(_norm(path.get("market_domain")))
    return {domain for domain in domains if domain}


def _entity_labels(entity: Mapping[str, Any]) -> set[str]:
    labels = _string_keys(
        entity.get("label"),
        entity.get("symbol"),
        entity.get("name"),
        entity.get("target_id"),
        entity.get("target_type"),
    )
    return {label for label in labels if label}


def _contains_synthetic_placeholder(labels: set[str]) -> bool:
    return any(_SYNTHETIC_PLACEHOLDER_RE.search(label) for label in labels)


def _mapping_value_keys(value: Mapping[str, Any]) -> set[str]:
    labels: set[str] = set()
    for child in value.values():
        if isinstance(child, str):
            labels.update(_string_keys(child))
        elif isinstance(child, Mapping):
            labels.update(_mapping_value_keys(child))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, str):
                    labels.update(_string_keys(item))
                elif isinstance(item, Mapping):
                    labels.update(_mapping_value_keys(item))
    return labels


def _text_keys(value: Any) -> set[str]:
    text = str(value or "")
    labels = _string_keys(text)
    labels.update(_norm(token) for token in _ASCII_TOKEN_RE.findall(text))
    return labels


def _string_keys(*values: Any) -> set[str]:
    labels: set[str] = set()
    for value in values:
        normalized = _norm(value)
        if not normalized:
            continue
        labels.add(normalized)
        labels.add(normalized.replace(" ", ""))
        labels.add(normalized.replace("-", ""))
        labels.add(normalized.replace("_", ""))
    return labels


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = [
    "EntitySupportDecision",
    "source_backed_entity_keys",
    "validate_affected_entity_support",
]
```

- [ ] **Step 2: Wire validator to support module**

In `src/parallax/domains/news_intel/services/news_item_brief_validation.py`, add import:

```python
from parallax.domains.news_intel.services.news_item_brief_entity_support import validate_affected_entity_support
```

Replace `_unsupported_entity_errors()` with:

```python
def _unsupported_entity_errors(payload: dict[str, Any], *, packet: NewsItemBriefInputPacket) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for entity in payload.get("affected_entities") or []:
        if not isinstance(entity, Mapping):
            continue
        decision = validate_affected_entity_support(entity, packet=packet, payload=payload)
        if decision.supported:
            continue
        errors.append(_error("unsupported_entity", str(entity.get("label") or entity.get("symbol") or "unknown")))
    return errors
```

Remove `_source_backed_entity_labels()` from `news_item_brief_validation.py` after confirming no local references remain.

- [ ] **Step 3: Run the reproduction tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_allows_source_backed_market_wide_proxy_entities tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_rejects_invented_synthetic_market_proxy_ticker -q
```

Expected:

```text
2 passed
```

- [ ] **Step 4: Run the full validation unit file**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Run ruff on touched files**

Run:

```bash
uv run ruff check src/parallax/domains/news_intel/services/news_item_brief_validation.py src/parallax/domains/news_intel/services/news_item_brief_entity_support.py tests/unit/domains/news_intel/test_news_item_brief_validation.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 6: Commit deterministic validator support**

```bash
git add src/parallax/domains/news_intel/services/news_item_brief_validation.py src/parallax/domains/news_intel/services/news_item_brief_entity_support.py tests/unit/domains/news_intel/test_news_item_brief_validation.py
git commit -m "fix: support market-wide news brief entities"
```

---

### Task 3: Harden Prompt Against Invented Synthetic Entities

**Files:**
- Modify: `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_stage.py`

- [ ] **Step 1: Update prompt entity instructions**

In `src/parallax/domains/news_intel/prompts/news_item_brief.md`, add this section after `# Impact Detail`:

```markdown
# Entity Discipline

For `affected_entities[]`, prefer packet `entity_lanes[]` first. Copy `entity_type`, `market_domain`, `resolution_status`, `target_type`, and `target_id` from packet lanes when present.

If the packet has no exact entity lane but the packet `market_scope`, source text, fact lanes, or provider evidence supports a broad market transmission, you may use a controlled market proxy:

- commodity: `WTI原油期货`, `原油期货`, `布伦特原油`
- crypto: `比特币` / `BTC` only as a risk-sentiment proxy when crypto is in packet market scope or a crypto transmission path is source-backed
- energy/geopolitics: source-backed countries, regions, or routes such as `美国`, `伊朗`, `以色列`, `霍尔木兹海峡`, `中东地缘政治风险`
- macro rates / FX: `美债收益率`, `美元指数`, `CPI`, `通胀`
- U.S. equities / sectors: `美股`, `标普500`, `纳斯达克`, or packet-backed listed companies

Never invent synthetic symbols, fake contracts, placeholder tickers, or fabricated target ids. Do not output labels like `XYZ-CL`, `ABC-OIL`, `相关衍生品` as if they were real instruments. If only a broad channel is supported, set `target_id` and `target_type` to null and explain the uncertainty in `reason_zh` / `data_gaps`.
```

- [ ] **Step 2: Keep output contract unchanged**

Verify the prompt still says:

```markdown
Only output one JSON object matching the typed `NewsItemBriefPayload` schema.
```

Do not add tool calls, external browsing, chain-of-thought, or side-channel instructions.

- [ ] **Step 3: Add prompt text regression test**

In `tests/unit/domains/news_intel/test_news_item_brief_stage.py`, add:

```python
def test_news_item_brief_prompt_forbids_synthetic_market_entities() -> None:
    instructions = news_item_brief_instructions()

    assert "Never invent synthetic symbols" in instructions
    assert "XYZ-CL" in instructions
    assert "controlled market proxy" in instructions
```

If `news_item_brief_instructions` is not imported at the top, update the import:

```python
from parallax.domains.news_intel.services.news_item_brief_stage import (
    build_news_item_brief_stage,
    news_item_brief_instructions,
)
```

- [ ] **Step 4: Run prompt stage tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_stage.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Commit prompt hardening**

```bash
git add src/parallax/domains/news_intel/prompts/news_item_brief.md tests/unit/domains/news_intel/test_news_item_brief_stage.py
git commit -m "fix: harden news brief prompt for market entities"
```

---

### Task 4: Hard-Cut Prompt and Validator Versions

**Files:**
- Modify: `src/parallax/domains/news_intel/_constants.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_types.py`

- [ ] **Step 1: Bump current contract constants**

Change constants in `src/parallax/domains/news_intel/_constants.py`:

```python
NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-market-wide-v2"
NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_market_v1"
NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_market_v2"
NEWS_ITEM_BRIEF_GUARDRAIL_VERSION = "news_item_brief_guardrails_market_v1"
```

- [ ] **Step 2: Add contract version test**

In `tests/unit/domains/news_intel/test_news_item_brief_types.py`, add:

```python
def test_default_news_item_brief_agent_config_uses_market_wide_validator_v2() -> None:
    config = default_news_item_brief_agent_config(model="gpt-5-mini", artifact_version_hash="artifact-v2")

    assert config.prompt_version == "news-item-brief-market-wide-v2"
    assert config.schema_version == "news_item_brief_market_v1"
    assert config.validator_version == "news_item_brief_validator_market_v2"
```

If `default_news_item_brief_agent_config` is not imported at the top, add it to the existing import list.

- [ ] **Step 3: Run contract tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_stage.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Commit version hard cut**

```bash
git add src/parallax/domains/news_intel/_constants.py tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_stage.py
git commit -m "fix: bump news brief market validator contract"
```

---

### Task 5: Worker-Level Regression for Former Production Failures

**Files:**
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`

- [ ] **Step 1: Add a ready payload fixture with market proxies**

Near `_ready_payload()`, add:

```python
def _energy_ready_payload() -> dict[str, Any]:
    payload = _ready_payload()
    payload.update(
        {
            "direction": "mixed",
            "decision_class": "driver",
            "event_type": "geopolitical_supply",
            "title_zh": "海湾地缘风险抬升原油与风险资产波动",
            "summary_zh": "来源显示海湾风险升温，影响集中在原油供应风险和风险偏好。",
            "market_read_zh": "原油风险溢价可能上升，比特币只作为风险情绪代理，不能视为来源确认的直接资产事件。",
            "market_domains": ["energy_geopolitics", "commodity", "crypto"],
            "affected_entities": [
                {
                    "label": "WTI原油期货",
                    "symbol": "CL",
                    "entity_type": "commodity",
                    "market_domain": "commodity",
                    "impact_direction": "bullish",
                    "reason_zh": "来源提到原油供应风险。",
                    "evidence_refs": ["item:summary"],
                },
                {
                    "label": "比特币",
                    "symbol": "BTC",
                    "entity_type": "crypto_asset",
                    "market_domain": "crypto",
                    "impact_direction": "mixed",
                    "reason_zh": "crypto 仅作为风险情绪代理。",
                    "evidence_refs": ["item:summary"],
                },
            ],
            "evidence_refs": ["item:title", "item:summary"],
        }
    )
    return payload
```

- [ ] **Step 2: Add worker publishable regression**

Add:

```python
def test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure() -> None:
    asyncio.run(_test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure())


async def _test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure() -> None:
    candidate = _candidate(provider_score=90)
    candidate["item"]["title"] = "U.S. attacks Iranian sites after Iran launches drones"
    candidate["item"]["summary"] = "The Gulf flare-up raised concern around crude supply and risk assets."
    candidate["item"]["body_text"] = "The report links Gulf military risk with crude supply concerns."
    candidate["item"]["market_scope_json"] = ["energy_geopolitics", "commodity", "crypto"]
    candidate["entities"] = [
        {
            "entity_id": "entity-iran",
            "raw_value": "Iran",
            "entity_type": "country",
            "confidence": 0.96,
        }
    ]
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_energy_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert result.processed == 1
    assert result.failed == 0
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.runs[0]["outcome"] == "ready"
    assert db.news.briefs[0]["status"] == "ready"
```

- [ ] **Step 3: Run worker tests**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Commit worker regression**

```bash
git add tests/unit/domains/news_intel/test_news_item_brief_worker.py
git commit -m "test: cover market-wide news brief worker validation"
```

---

### Task 6: Focused Full Verification

**Files:**
- No code changes.

- [ ] **Step 1: Run news brief unit suite**

Run:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/domains/news_intel/test_news_item_brief_types.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run broader news suite**

Run:

```bash
uv run pytest tests/unit/domains/news_intel tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_agent_admission_repository.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run ruff**

Run:

```bash
uv run ruff check src/parallax/domains/news_intel tests/unit/domains/news_intel tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_agent_admission_repository.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Run frontend architecture guard**

No frontend files are expected to change, but run the guard because this is a serving-surface fix:

```bash
npm run lint --prefix web
```

Expected:

```text
Test Files  11 passed
Tests  64 passed
```

- [ ] **Step 5: Run whitespace check**

```bash
git diff --check
```

Expected: no output, exit 0.

---

### Task 7: Docker Rebuild, Queue Repair, and Live Quality Check

**Files:**
- No code changes.

- [ ] **Step 1: Rebuild and restart app**

Run:

```bash
docker compose up -d --build app
```

Expected:

```text
Container parallax-app-1  Started
```

- [ ] **Step 2: Confirm service health**

Run:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8765/healthz
docker compose exec -T app parallax db health
```

Expected:

```text
parallax-app-1 Up ... healthy
ok
"migration_status":"ready"
```

- [ ] **Step 3: Re-enqueue recent failed/current-contract brief work**

Run:

```bash
docker compose exec -T app parallax ops enqueue-projection-dirty-targets --domain news --projection brief_input --since-hours 24 --execute
```

Expected:

```text
"ok":true
```

This is a hard-cut reprocess. Do not add compatibility reads for v1 prompt/validator outputs.

- [ ] **Step 4: Check live queues**

Run:

```bash
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
select projection_name, target_kind, "window",
       count(*) as total,
       count(*) filter (where due_at_ms <= extract(epoch from now())::bigint * 1000 and leased_until_ms is null) as due,
       count(*) filter (where leased_until_ms is not null and leased_until_ms > extract(epoch from now())::bigint * 1000) as running,
       count(*) filter (where last_error is not null) as with_last_error
from news_projection_dirty_targets
group by projection_name, target_kind, "window"
order by projection_name, target_kind, "window";
SQL'
```

Expected:

- `page` queue remains `0`.
- `brief_input` queue may be nonzero because `news.item_brief` is single-concurrency.
- `with_last_error` should stop increasing for `domain_validation_failed` once new validator is active.

- [ ] **Step 5: Verify production failure samples no longer fail validation**

Run this query after several brief attempts complete:

```bash
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
with recent as (
  select news_item_id, title,
         coalesce((provider_signal_json->>$q$score$q$)::int, 0) as provider_score
  from news_items
  where published_at_ms >= ((extract(epoch from now())::bigint * 1000) - 24*3600*1000)
), latest_run as (
  select distinct on (r.news_item_id)
         r.news_item_id, r.title, r.provider_score,
         ar.status, ar.outcome, ar.error_class, ar.validation_errors_json, ar.finished_at_ms
  from recent r
  join news_item_agent_runs ar on ar.news_item_id = r.news_item_id
  order by r.news_item_id, ar.finished_at_ms desc
)
select status, outcome, coalesce(error_class, $q$$q$) as error_class, count(*) as count
from latest_run
group by status, outcome, coalesce(error_class, $q$$q$)
order by count desc, status, outcome, error_class;
SQL'
```

Expected:

- `domain_validation_failed` count decreases after reprocessing.
- Any remaining failures should be `provider_error`, schema-invalid genuine malformed output, or synthetic placeholder rejection.

- [ ] **Step 6: Capture residual failed samples**

Run:

```bash
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
with recent as (
  select news_item_id, title,
         coalesce((provider_signal_json->>$q$score$q$)::int, 0) as provider_score
  from news_items
  where published_at_ms >= ((extract(epoch from now())::bigint * 1000) - 24*3600*1000)
), latest_run as (
  select distinct on (r.news_item_id)
         r.news_item_id, r.title, r.provider_score,
         ar.status, ar.outcome, ar.error_class, ar.validation_errors_json, ar.finished_at_ms
  from recent r
  join news_item_agent_runs ar on ar.news_item_id = r.news_item_id
  order by r.news_item_id, ar.finished_at_ms desc
)
select news_item_id, provider_score, left(title, 96) as title, error_class, validation_errors_json
from latest_run
where status = $q$failed$q$ or outcome = $q$failed$q$
order by provider_score desc, finished_at_ms desc
limit 20;
SQL'
```

Expected:

- No residual `unsupported_entity` for `WTI原油期货`, `原油期货`, `比特币`, `美国`, `中东地缘政治风险`.
- Synthetic labels such as `XYZ-CL` remain rejected.

- [ ] **Step 7: Commit final verification notes if docs were changed**

If `ARCHITECTURE.md` was touched:

```bash
git add src/parallax/domains/news_intel/ARCHITECTURE.md
git commit -m "docs: document market-wide news brief validation"
```

---

## Self-Review Checklist

- Spec coverage:
  - Fixes observed `domain_validation_failed` for market-wide brief outputs.
  - Keeps harness separation: LLM output remains JSON-only; deterministic validator owns publishability.
  - Preserves hard-cut posture by bumping prompt/validator contract instead of adding legacy compatibility.
  - Keeps invented ticker rejection.

- Placeholder scan:
  - No `TBD`, `TODO`, `implement later`, or vague "handle edge cases" steps.
  - Every code-changing step names exact files and includes concrete code.

- Type consistency:
  - New helper accepts `NewsItemBriefInputPacket`, same type already used by validator.
  - `NewsMarketDomain` and `NewsEntityType` values match `types/news_item_brief.py`.
  - Version constants match `default_news_item_brief_agent_config()`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/active/2026-06-06-news-brief-market-wide-validator-root-fix-cn.md`.

Recommended execution mode: **Subagent-Driven**. Dispatch one fresh subagent per task, review diffs between tasks, and stop after Task 7 with live DB evidence.
