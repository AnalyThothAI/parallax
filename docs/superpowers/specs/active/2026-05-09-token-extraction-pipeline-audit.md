# Spec — Token 匹配与价格同步 KISS 修复

**Status**: Draft
**Date**: 2026-05-09
**Owner**: aaurix / Codex
**Related**: `docs/superpowers/specs/2026-05-08-auditable-token-radar-design-cn.md`, `docs/superpowers/plans/2026-05-06-token-identity-resolution-production.md`

## Background

当前 token 提取本身不是主要问题。文本实体抽取已经把 CA、Solana 地址、TON 地址、cashtag 分开识别，cashtag 被标为 `symbol` 且链为空，见 `src/gmgn_twitter_intel/pipeline/entity_extractor.py:79`、`src/gmgn_twitter_intel/pipeline/entity_extractor.py:93`、`src/gmgn_twitter_intel/pipeline/entity_extractor.py:105`、`src/gmgn_twitter_intel/pipeline/entity_extractor.py:115`。证据层也清楚地区分 CA 强证据和 cashtag 中等证据，见 `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py:41`、`src/gmgn_twitter_intel/pipeline/token_evidence_builder.py:84`。intent 构造中，CA intent 用 `ca:<chain>:<address>`，symbol-only intent 用 `symbol:<SYMBOL>`，见 `src/gmgn_twitter_intel/pipeline/token_intent_builder.py:114`。

解析层的优先级也基本正确：带 chain+address 的 intent 先走精确链上资产，symbol intent 先找 CEX token，再找链上 symbol 候选，见 `src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py:64`、`src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py:228`、`src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py:248`。因此这次不重写提取、不重写 intent 构造、不重写 CEX 优先原则。

真正失控的是 DEX symbol discovery 的候选入库边界。`TokenDiscoveryWorker` 对 `symbol:*` 调 OKX DEX search 后，会遍历所有 exact-symbol 候选并逐个写入 registry、pricefeed、price observation，见 `src/gmgn_twitter_intel/pipeline/token_discovery_worker.py:235`、`src/gmgn_twitter_intel/pipeline/token_discovery_worker.py:237`、`src/gmgn_twitter_intel/pipeline/token_discovery_worker.py:296`。registry 的 identity key 本身是正确的：`asset_id` 由 chain、token standard、address 组成，见 `src/gmgn_twitter_intel/storage/registry_repository.py:59`，迁移还建立了 `chain_id + lower(address)` 唯一索引，见 `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_deterministic_registry.py:197`。

本机 PostgreSQL 只读审计显示，`HANTA` 在 registry 里约 600 个不是同一 CA 重复污染，而是数百个不同 `chain_id + address` 的 OKX search 候选；其中大多数来自 `okx_dex_search`，且大量不是当前 resolution 的 target 或 current candidate。这个数据形状符合代码路径：symbol search 的历史候选会累积，registry 没有“每 symbol 每链最多保留几个高质量候选”的准入规则。

价格同步随后放大这个问题。`sync_okx_dex_prices` 只调用 `chain_assets_needing_price_refresh(stale_before_ms, limit)`，见 `src/gmgn_twitter_intel/pipeline/asset_market_sync.py:88`；该查询对所有 `candidate/canonical` registry assets 按最旧价格排序，未区分 CA 直证据、当前 target、当前候选、search-only 长尾，见 `src/gmgn_twitter_intel/storage/registry_repository.py:268`。结果是价格刷新预算被历史 symbol search 长尾稀释。

## Problem

系统把“OKX 搜索到的同 symbol 资产”当成“值得长期进入 registry 和价格刷新循环的资产”。对于 HANTA 这种易被仿盘复用的 symbol，一轮又一轮 search 会把大量假币、冷门币、无交易价值候选累计进 registry。数据库没有重复写坏，但 registry 被低价值候选撑大，价格同步再无差别扫描，导致真正有意义的 token 价格 freshness 变差。问题不是 token 提取，而是 DEX/CEX 匹配与价格数据入口缺少 KISS 的候选准入。

## First Principles

1. **CA/address 是身份，symbol 只是弱标签。** 带 chain+address 的证据可以直接落 registry；symbol-only search 只能产生有限候选，不能无限扩大身份空间。现有 intent key 已体现这个边界，见 `src/gmgn_twitter_intel/pipeline/token_intent_builder.py:114`。
2. **CEX canonical 优先于 DEX 同名候选。** 如果 symbol 已在 CEX universe 里确认，解析优先 CEX token；DEX search 只服务未解决或模糊的链上候选，见 `src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py:228`。
3. **价格同步服务“可被解析/展示的候选”，不服务历史搜索垃圾。** price refresh queue 应只围绕 CA 直证据、当前 target、当前保留候选运行；search-only 长尾不应常驻刷新循环。

## Goals

- **G1**：DEX symbol search 写入 registry 的候选数从“OKX 返回多少写多少”改为“每条 chain 最多 3 个保留候选”，5 条配置链最多 15 个。
- **G2**：对 `HANTA`、`UAP`、`VIRUS` 这类高碰撞 symbol，current eligible DEX 候选数 bounded；历史 search-only 长尾不再参与 symbol 解析和价格刷新。
- **G3**：CA/address lookup 不受 symbol cap 影响；推文明确给出的 chain+address 仍然精确入库、精确解析。
- **G4**：CEX token 解析路径保持不变；已确认 CEX symbol 仍优先返回 `CexToken`。
- **G5**：价格刷新队列中，search-only 且未被 current target/candidate 引用的资产占比为 0。
- **G6**：不新增表、不新增 worker、不引入 LLM、不重写 token extraction。

## Non-goals

- 不改 entity extractor、token evidence builder、token intent builder。
- 不拆 `IngestService` 事务。
- 不修 token radar feature_builder、driver lane、UI 展示。
- 不引入概率模型、Bayesian 合并、人工标注、holdout/cross-validation。
- 不删除历史 events、intents、resolutions、price observations。
- 不扩大 public API / WebSocket payload 合约。

## Target Architecture

目标架构是“候选准入在 discovery 边界解决”，而不是让下游刷新队列补救一个无限增长的 registry。

**DEX symbol candidate admission**

对 `symbol:*` lookup，OKX DEX search 结果先按 exact normalized symbol 过滤，再按链分组。每条链只保留质量最高的最多 3 个候选，其余 search result 不写入 `registry_assets`、不写入 `price_feeds`、不写入 `price_observations`、不进入 `token_discovery_results.candidate_ids_json`。

候选质量使用 OKX 已返回的字段做确定性排序：

```
quality = 0.50 * log10(market_cap_usd + 1)
        + 0.30 * log10(liquidity_usd + 1)
        + 0.20 * log10(holders + 1)
```

缺失字段按 0 计。排序 tie-breaker 是：有 price 的优先、有 community-recognized 标记的优先、原始 provider 顺序优先、asset identity 字典序兜底。这个排序只用于内部 candidate admission，不是对外 ranking score，不改变 `score_version`。

**Address candidate admission**

address lookup 与推文 CA 直证据不走 symbol cap。只要 chain+address 明确，系统可以写入对应 registry asset，因为这类输入已经是身份而不是弱 symbol label。

**Existing registry cleanup**

历史已经累积的 search-only 长尾不删除，但从 resolver/refresh eligible set 中退出。准则是：不是 CA/payload 来源、不是 current resolution target、不是 current resolution candidate、且不在该 symbol+chain 的 top 3 retained candidates 内的资产，不再以 `candidate/canonical` 身份参与解析与价格刷新。具体状态值由 plan 选择，但语义必须是“不被 current resolver 和 refresh selector 读取”。

**Price refresh simplification**

价格刷新选择器只扫描可展示资产：CA/payload 来源资产、current resolution target、current retained candidate。它不再扫描所有 registry assets。先保持现有 refresh limit，不通过加大吞吐掩盖候选入库失控；如果候选 cap 落地后 freshness 仍不达标，再单独评估 limit。

**Resolver freshness**

resolver 不新增状态枚举。它继续返回现有 `EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS / NIL`，但 symbol-only 解析只看 retained candidates。价格新鲜度作为 market data health 处理：候选身份足够明确但价格 stale 时，可以保留 identity 决策，下游价格状态显示 stale；不要因为 registry 里存在大量旧候选就把 identity 直接冲成 NIL。

## Conceptual Data Flow

```
tweet text / GMGN payload
  → entity extraction / evidence / intent
  → resolver
      → CEX symbol match first
      → chain+address exact match
      → DEX symbol retained candidates only
  → price refresh
      → current target + retained candidates only
  → radar / timeline / alerts
```

变化只发生在 DEX symbol discovery 到 registry 的入口，以及 price refresh 的候选选择。collector、entity extraction、intent construction、CEX universe、API/WS payload 都保持原状。

## Core Models

- **Retained DEX Candidate**：由 provider search 返回、symbol exact match、在其 chain 的 quality 排名前 3、可进入 registry 和 discovery candidate list 的链上资产。
- **Rejected Search Candidate**：provider search 返回但未进入 top 3 的链上资产。它不进入 registry，不参与解析，不参与刷新；若未来被 CA 明确提及，会通过 address 路径重新入库。
- **Search-only Historical Asset**：过去已由 `okx_dex_search` 写入，但当前既不是 target，也不是 retained candidate。它可以保留审计历史，但不再被当作 active candidate。
- **Canonical CEX Token**：由 CEX universe 确认的 symbol 级资产。CEX 解析优先级不变。

## Interface Contracts

- **HTTP / WebSocket**：payload 形状不变。解析状态仍使用现有 `EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS / NIL`。
- **CLI**：不新增子命令。现有 ops 命令输出可以在 plan 阶段增加 retained/rejected 计数，但不是公共契约。
- **Storage**：不新增表。可以复用 `registry_assets.status`、`token_discovery_results.candidate_ids_json`、现有 price observation 表达保留候选与价格观测。
- **Provider calls**：OKX DEX search 调用方式不变；变化是写入前做 per-chain top K admission。

## Acceptance Criteria

- **AC1**：WHEN `symbol:HANTA` 的 OKX DEX search 返回同一链 100 个 exact-symbol 候选，THEN 系统 SHALL 最多写入该链 3 个 retained candidates。
- **AC2**：WHEN DEX symbol search 返回 5 条配置链的候选，THEN 单次 lookup SHALL 最多向 registry 写入 15 个 retained candidates。
- **AC3**：WHEN 某候选因 per-chain top 3 被拒绝，THEN 系统 SHALL 不写入 `registry_assets`、不写入 pricefeed、不写入 price observation、不进入 discovery result candidate list。
- **AC4**：WHEN 推文包含明确 chain+address，THEN 该 CA SHALL 不受 per-symbol cap 限制并继续精确解析。
- **AC5**：WHEN symbol 存在 confirmed CEX token，THEN resolver SHALL 保持 CEX token 优先，DEX retained candidates 不抢占 CEX 结果。
- **AC6**：WHEN 价格刷新队列选择资产，THEN search-only 且未被 current target/candidate 引用的 historical assets SHALL 不进入队列。
- **AC7**：WHEN 对当前库的 HANTA 历史数据执行 cleanup/demotion 后，THEN active eligible HANTA DEX candidates SHALL 不超过 `configured_chain_count * 3`，且同链同地址唯一性仍为 0 重复。
- **AC8**：WHEN retained candidates 全部价格 stale 但 identity 仍唯一或 market-dominant，THEN resolver SHALL 不因为 rejected historical candidates 存在而返回 `SYMBOL_CANDIDATES_STALE`。
- **AC9**：WHEN token extraction 单测运行，THEN CA、cashtag、GMGN payload evidence 与 intent construction 既有行为 SHALL 不变。

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Top 3 cap 过滤掉后来变热的低排候选 | Medium | 明确 CA/address 提及时不受 cap；下一次 symbol search 也会按最新 market data 重新排序。 |
| OKX 返回 market fields 缺失导致排序误判 | Medium | 缺失字段按 0，tie-breaker 使用 provider 顺序和 identity；无指标候选不会挤掉有市值/流动性/holders 的候选。 |
| 历史 demotion 误伤 current target | High | cleanup 只处理 search-only 且非 current target/candidate 的资产。 |
| CEX 与 DEX 同 symbol 混淆 | Low | CEX resolver 优先级保持现状，DEX cap 只影响 DEX candidate admission。 |
| 仍有少数 spam 候选进入 top 3 | Low | 这是可接受边界：每链最多 3 个比无限累积更可控，后续可用 CA evidence 或 watched confirmation 提升精度。 |

## Evolution Path

下一步如果 top 3 仍不够，可以只在 retained candidate 内增加更严格的质量门槛，例如最低 liquidity 或 holder 下限。不要先引入新表、物化视图、复杂 hot/warm/cold 调度或在线学习；先证明简单 candidate admission 已经把 registry 和 price refresh 拉回可控规模。

## Alternatives Considered

- **刷新队列 hot/warm/cold 分层**：否决作为第一步。它能缓解扫描 14k registry 的症状，但没有阻止 symbol search 垃圾继续累计，复杂度也更高。
- **把 DEX refresh limit 从 80 提到 200**：否决作为第一步。提高吞吐会掩盖候选准入失控，而且增加 provider 限速风险。
- **新增候选表或物化视图**：否决。现有 `registry_assets.status`、`token_discovery_results`、current resolutions 已足够表达 active candidate，不需要新持久化层。
- **resolver 内实时 lazy fetch OKX**：否决。会把 provider 延迟和错误带进读/解析路径，且不解决历史 search-only 候选膨胀。
- **删除所有历史 HANTA search assets**：否决。需要保留审计历史；正确做法是 demote/exclude from active eligibility，而不是破坏历史数据。

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | DEX symbol search 每链最多保留 3 个候选；CA/address 路径不受 cap；CEX 优先级不变；price refresh 不扫 search-only orphan。 |
| Ask first | 调整 per-chain cap 大小；加入最低 liquidity/holders 门槛；真正删除历史 registry rows；提高 DEX refresh limit。 |
| Never | 为本修复新增表、新 worker、LLM 调用、概率模型、评分重写、token extraction 重写。 |
