# Spec - Radar Candidate Market Hydration

**Status**: Draft
**Date**: 2026-05-09
**Owner**: aaurix / Codex
**Related**:
- `docs/superpowers/specs/2026-05-08-auditable-token-radar-design-cn.md`
- `docs/superpowers/specs/2026-05-09-token-extraction-pipeline-audit.md`
- `docs/superpowers/specs/2026-05-09-token-extraction-pipeline-audit-claude.md`

## Background

今天的系统已经有一条相对成熟的 token 提取和解析状态机。`IngestService.ingest_event` 在一个事务里完成事件入库、实体抽取、token evidence 构建、token intent 构建、GMGN payload / CA registry upsert、deterministic resolution、lookup key 写入、GMGN payload message price 写入以及 alert/enrichment 入队；这说明 token 身份事实的生成在 ingest 边界内同步完成，不依赖 radar 投影后补判定。证据见 `src/parallax/pipeline/ingest_service.py:61-120`。其中 GMGN payload 会按 chain/address 写入 registry，CA intent 也会按 chain/address 写入 registry，GMGN payload 自带价格会以 `message_payload` 观察写入 price observations，见 `src/parallax/pipeline/ingest_service.py:150-232`。

token evidence 的语义是确定性的：CA entity 产生 address/chain 强证据，cashtag 产生 symbol 中等证据，GMGN payload 产生 token payload 强证据；去重基于稳定 evidence id。证据见 `src/parallax/pipeline/token_evidence_builder.py:33-48`、`src/parallax/pipeline/token_evidence_builder.py:51-135`。token intent 的语义也是确定性的：优先用带 address 的 strong identity 生成 `ca:<chain>:<address>` intent，剩余 cashtag 生成 `symbol:<SYMBOL>` intent；这也是后续 resolver 和 lookup key 的状态机入口。证据见 `src/parallax/pipeline/token_intent_builder.py:37-84`、`src/parallax/pipeline/token_intent_builder.py:91-119`。

当前 resolver 的状态机已经把身份解析拆成三条清晰路径：chain+address 精确解析、address 无链上下文解析、symbol 解析。chain+address 命中 registry 时给出 `EXACT / CHAIN_ADDRESS_EXACT`，address 无链唯一时给出 `UNIQUE_BY_CONTEXT`，symbol 先尝试 CEX token / CEX pricefeed，再按 registry asset 的 symbol 与最新市场观察排序，必要时返回 `AMBIGUOUS`。证据见 `src/parallax/pipeline/deterministic_token_resolver.py:42-80`、`src/parallax/pipeline/deterministic_token_resolver.py:138-215`、`src/parallax/pipeline/deterministic_token_resolver.py:217-296`。

symbol discovery 已经做过一次 KISS 修正：OKX DEX symbol search 会过滤 exact symbol，并按 chain 保留有限候选，其余同 symbol 搜索资产被 demote；address lookup 仍按地址精确匹配，不走 symbol fanout。证据见 `src/parallax/pipeline/token_discovery_worker.py:224-268`、`src/parallax/pipeline/token_discovery_worker.py:271-356`。因此“几千个冷资产”的主要原因不再是单次 symbol 搜索无限写入，而是 registry 作为历史身份记忆不断累积，同时 market refresh 还把整个 active registry 当作刷新 universe。

token radar 投影现在从当前 resolver 结果读取 source rows，再按 window 分组、构建 resolved lane / attention lane、排序并写入 `token_radar_rows`。窗口内打分使用 `computed_at_ms - window_ms` 之后的 rows，历史 rows 只用于 baseline/context。证据见 `src/parallax/pipeline/token_radar_projection.py:34-72`、`src/parallax/pipeline/token_radar_projection.py:377-472`。API `/api/token-radar` 读取 latest projection，而不是在线实时计算，见 `src/parallax/api/http.py:152-168`、`src/parallax/retrieval/asset_flow_service.py:19-50`、`src/parallax/storage/token_radar_repository.py:86-129`。

radar 当前的 market 语义是“读取 source rows 中最新 market observation，若 observation age 小于 5 分钟则 fresh，否则 stale；没有 resolved target 或没有 observation 则 missing/pending_refresh”。同时它会尝试从 event/message observation 或事件前 observation 推导 social start price。证据见 `src/parallax/pipeline/token_radar_projection.py:577-646`。score block 已经把 market 状态喂给 tradeability / timing，但刷新动作本身不是由当前 radar 候选集驱动；feature builder 只是消费已经存在的 market row，见 `src/parallax/pipeline/token_radar_feature_builder.py:27-83`、`src/parallax/pipeline/token_radar_feature_builder.py:203-264`。

DEX 当前价格刷新由 `sync_okx_dex_prices` 从 `registry.chain_assets_needing_price_refresh` 拉全局 stale/missing active assets，再对缺 metadata 的地址做 search，之后批量 token_prices。证据见 `src/parallax/pipeline/asset_market_sync.py:79-190`。而 `chain_assets_needing_price_refresh` 的 universe 是所有 `candidate/canonical` registry assets，排序是最旧 price observation 优先，不知道当前 5m/1h radar 正在展示什么。证据见 `src/parallax/storage/registry_repository.py:288-318`。

message/start price 观察也存在同类错位：`observe_message_market` 选择“没有 message_payload/message_quote 的 current resolved rows”，但排序是 `events.received_at_ms ASC`，即最旧事件优先；在积压很大时，最近 5m/1h 事件的 start price 会排在历史 backlog 后面。证据见 `src/parallax/pipeline/message_market_observation.py:11-55`、`src/parallax/pipeline/message_market_observation.py:58-144`。

2026-05-09 本地 PostgreSQL 快照显示，这个问题已经是架构错位而不是单个 token 的偶发脏数据：active registry 中有 `candidate/gmgn_payload = 69`、`candidate/okx_dex_search = 6482`、`candidate/tweet_ca = 2300`，另有 `demoted_search/okx_dex_search = 5337`。最新 `token-radar-v6-auditable` 的 `5m/all` resolved Asset 只有 13 行，其中 fresh 3、stale 10；`1h/all` resolved Asset 有 76 行，其中 fresh 15、stale 61。多个最新 5m stale 资产在全局刷新队列中排到约 5k-8.7k 名之后，例如 UPEG 约 8693、SHIT 约 8697、ARENA 约 8585、HANTA 类长尾在 1h 中也可排到 8800 之后。message quote backlog 同时存在：pending message observation 约 Asset 23785、CexToken 5407，其中最近 1h 仍 pending Asset 381、CexToken 100。

因此，当前系统里“几千个冷资产”本身不是等同于“5m/1h radar 有几千个候选”。真实情况是：registry 是历史身份记忆，radar window 是社交事件候选集；问题在于市场刷新把前者当成了后者的 SLA 队列，导致最近窗口的候选价格被历史冷资产挡住。

## Problem

用户在 5m / 1h radar 中看到大量候选价格 stale 或 missing，并看到类似 HANTA 这类长尾重复资产污染 active registry，进而无法判断 radar 是“按社交热度选币后价格没跟上”，还是“选币逻辑本身把几千个冷资产当作当前候选”。系统可见的问题是：identity extraction、symbol discovery、registry memory、current radar candidate selection、current market hydration 这几个职责边界没有被强制隔离；价格刷新和 message/start price 补齐仍由全局历史 backlog 驱动，而不是由当前 radar 候选集驱动。

## First principles

1. **当前窗口候选集来自社交事件，不来自 registry 全量资产。** 5m / 1h / 24h 切换时，候选应该先由当前窗口内的 token intents 和 current resolutions 生成；registry 只是身份解析和市场 metadata 的记忆层。当前投影已经按 window rows 计算 lane 和 rank，见 `src/parallax/pipeline/token_radar_projection.py:377-472`，但 market refresh 没有遵守这个边界。

2. **token 提取状态机是上游事实层，不能为了 market freshness 被重写。** CA、cashtag、GMGN payload 的 evidence 生成、intent key 生成、resolver status taxonomy、lookup key 写入，是当前成熟链路。它们位于 ingest/resolver 边界，见 `src/parallax/pipeline/ingest_service.py:61-120`、`src/parallax/pipeline/token_intent_builder.py:91-119`、`src/parallax/pipeline/deterministic_token_resolver.py:42-80`。本设计只改变 radar 候选市场水位的拥有者，不把 market 失败反向解释成“token 没提取到”。

3. **价格有两个不同问题：事件起点价格和当前可交易价格。** `message_payload/message_quote` 应回答“这条社交信号出现时能看到什么价格”；latest market observation 应回答“现在 radar 上能不能交易/评估”。当前代码已经在 projection 中区分 event price、before_event_price、latest market price，见 `src/parallax/pipeline/token_radar_projection.py:180-207`、`src/parallax/pipeline/token_radar_projection.py:310-330`、`src/parallax/pipeline/token_radar_projection.py:577-646`，但两个价格的补齐调度都没有 current-window SLA。

4. **hard cut 优先于兼容分支。** 本设计不保留旧 radar market fallback、不做双版本读取、不让 API 同时服务旧 projection 语义。历史 rows 和历史 observations 可以保留作为审计事实，但最新 `/api/token-radar` 只读取新 projection version；下游需要一次性切换。

5. **KISS 的判断标准是减少错误 owner，而不是堆更多补丁。** 如果只是提高全局 refresh limit、或者给 registry queue 加一个热度权重，系统仍然会把历史身份记忆和当前交易候选混在一起。本设计优先替换 ownership：当前候选集拥有当前市场 hydration 的预算。

## Goals

- G1. 最新 `5m/all` 和 `1h/all` resolved Asset radar rows 中，至少 95% 在 projection 写入时拥有 `fresh` current market snapshot，或拥有明确的 `missing_market` / `provider_error` / `rate_limited` 原因；不得因为全局 registry refresh rank 排在几千名之后而呈现 stale。
- G2. radar market hydration 的输入 universe 100% 来自当前 projection candidate set，包括 resolved targets 和需要展示在 attention lane 的 unresolved lookup keys；不得从全局 `candidate/canonical` registry assets oldest-first 队列中隐式抢预算。
- G3. 最近 5m / 1h 已 resolved 的 source event，在 provider 可用时至少 90% 在被 projection 消费前拥有 event/start price observation；如果没有 observation，radar row 必须暴露 lag/status，而不是把缺失混成普通 `insufficient_history`。
- G4. CA/chain-address、address-only、symbol-only、GMGN payload 的 evidence / intent / resolver 状态机保持语义不变。已有 `EXACT`、`UNIQUE_BY_CONTEXT`、`AMBIGUOUS`、`NIL` 的含义不因 market hydration 改动；除非后续 plan 明确改变 resolver 语义，否则不 bump resolver policy version。
- G5. active registry 中数千个历史冷资产不再影响 5m / 1h radar 市场 SLA。长尾 search 污染资产可以被 demote 出 active refresh universe，但 radar 正确性不依赖物理删除历史 registry rows。
- G6. `/api/token-radar` 返回的每个排名 row 继续包含 score component breakdown，并额外明确 identity、market readiness、event price readiness、current price age，使用户能区分“社交热度高但价格未就绪”和“价格就绪可评估”。
- G7. 不新增 LLM 调用、不新增概率模型、不引入训练/标注链路；本次只调整 deterministic candidate ownership 和 market hydration 生命周期。

## Non-goals

- N1. 不重写 entity extraction、token evidence builder、token intent builder、deterministic resolver 的核心状态机。
- N2. 不把 symbol-only 提及强行合并成单个“项目级 token”。同一 symbol 多链多合约仍应按 target identity 展示，直到另一个 spec 定义 project-level aggregation。
- N3. 不为历史 registry 全量资产提供 5 分钟级刷新 SLA。冷资产页面、历史审计、长尾 discovery 可以 best-effort，但不能占用 current radar SLA。
- N4. 不引入新的持久化 candidate queue / materialized view 作为第一步。除非后续测量证明 projection-time candidate hydration 无法满足延迟或成本要求，否则复用现有 `price_feeds`、`price_observations`、`token_radar_rows`。
- N5. 不做物理删除历史 price observations 或 audit facts。对 HANTA 类长尾污染的“移除”默认指从 active candidate/refresh universe 中 demote 或隔离；物理删除属于数据删除行为，需要单独确认和回滚策略。
- N6. 不改变 GMGN public stream 覆盖语义，不把 `coverage=public_stream` 宣传成完整 Twitter firehose。
- N7. 不在 API 中保留 legacy radar market payload 的兼容分支；本 spec 承认这是一次 versioned hard cut。

## Target architecture

目标架构把 token radar 拆成四个职责清楚的层：上游事实层、当前候选层、候选市场 hydration 层、投影/API 层。

上游事实层保持现状：collector/ingest 继续把事件、entities、token evidence、token intents、intent resolutions、lookup keys、GMGN payload observations 写入同一个 PostgreSQL store。这个层只回答“社交消息中提到了什么身份线索、当前 deterministic resolver 怎么解释它”。market provider 是否能取到价格，不能反向改变 evidence 或 intent 的存在性。

当前候选层成为 radar 的第一拥有者。每次 `5m`、`1h`、`24h` projection 都先从 source rows 形成该 window/scope 的 candidate set。candidate set 包含：

- resolved Asset / CexToken targets；
- unresolved attention intents 及其 lookup keys；
- 每个 target 对应的 source event ids、social start time、latest seen time、resolution status；
- 每个 target 在当前窗口内的社交统计输入。

candidate set 是内存中的投影输入模型，不是新的长期事实表。它的生命周期跟 projection run 一致。这样可以保持 KISS：当前系统已经能从 source rows 重建 window candidate set，没必要先加一张 queue 表来复制同样的事实。

候选市场 hydration 层取代当前“全局 registry oldest-first 刷新对 radar 生效”的语义。它只对当前 candidate set 消耗市场预算，并分两条 lane：

- **current quote lane**：为当前 projection candidate set 中的 resolved targets 获取最新可交易市场 snapshot。CEX target 走 CEX ticker/pricefeed，DEX Asset 走 chain/address token price，必要时只对当前 candidate 的缺 metadata 地址做 exact address search。
- **event quote lane**：为当前 candidate set 中最近窗口内的 source resolutions 补齐 message/start price observation。它优先处理最新 5m/1h 事件，而不是历史 oldest-first backlog。

两条 lane 都写回现有 `price_observations` / `price_feeds`，并通过 observation kind、source event/resolution link、observed_at_ms、event_received_at_ms 区分“事件起点价格”和“当前价格”。投影继续只读数据库事实，保持可审计；不同的是 projection run 在读取/写入最新 rows 前，先确保当前 candidate set 的市场水位被 bounded hydration 尝试过。

冷 registry steward 从 radar SLA 中降级。现有全局 registry refresh 可以保留为低优先级 metadata/历史维护能力，但它的结果不再是 radar 是否 fresh 的主要路径；如果 provider budget 紧张，current candidate hydration 必须优先于 cold registry steward。HANTA 类长尾 search 污染资产，即使还留在 registry 作为审计记忆，也不能因为 active 状态排进 radar 市场 SLA 队列。

registry hygiene 采用 hard cut active-universe 语义：active registry 不再等于 radar-refresh universe。`candidate/canonical` 可以继续表示 resolver 可见身份，但 market refresh eligibility 必须由“是否属于当前 candidate set、是否 exact identity、是否 retained symbol candidate、是否被显式 canonical 化”决定。长尾 symbol search 产物如果不在 retained policy、没有近期 exact evidence、没有当前 candidate 引用，应从 active refresh universe 中移除；默认行为是 demotion，不是删除。

投影/API 层 bump radar projection version，并只读取新版本。旧 `token-radar-v6-auditable` rows 仍可作为历史数据库事实存在，但 API 不做双读、不做字段 fallback、不把 legacy `market_json` 解释成新语义。新 radar row 的 decision 必须显式受 market readiness 约束：market 未就绪的 row 可以进入 watch/attention，但不得被呈现为可交易 driver。

对 token 提取状态机的影响评估如下：

- **CA 精确路径**：不应改变。chain/address evidence 仍在 ingest 内写入 registry，并由 resolver 返回 exact asset target。hydration 只使用 resolved target 的 chain/address 拉价格，不改变 evidence、intent、resolution status。
- **GMGN payload 路径**：不应改变。payload token snapshot 继续作为强身份和可选 message payload price。hydration 可补充 current quote，但不能覆盖 payload event price 的审计含义。
- **symbol-only 路径**：不应改变 resolver 状态含义。symbol discovery 可继续按 exact symbol、per-chain retained policy 写 candidate；hydration 不能因为价格缺失而把 `AMBIGUOUS` 改成 `NIL`，也不能因为某个 search candidate 有价格就把多候选 symbol 偷偷合并。
- **lookup key 路径**：不应改变 lookup key 的生成语义。unresolved attention lane 可以展示 discovery status 和 market readiness 缺失原因，但不能生成新的 lookup key 格式来绕开 resolver。
- **policy version**：如果实现只改变 market hydration 和 projection contract，则 bump projection version，不 bump resolver policy version。如果后续 plan 发现必须改变 resolver 选择规则，例如 symbol dominance 阈值或 candidate merge 规则，则必须另开 resolver spec 并 bump resolver policy version。

## Conceptual data flow

```
GMGN public WS
  → collector
  → ingest facts
    → token evidence / token intents / deterministic resolutions / lookup keys
  → token discovery
    → registry identity memory
  → radar candidate set by window
    → candidate-scoped market hydration
      → current quote observations
      → event/start quote observations
  → radar projection rows
  → retrieval / HTTP / WS consumers
```

Changed arrows:

- `radar candidate set by window → candidate-scoped market hydration` becomes the new owner of radar price freshness.
- `registry identity memory → global oldest-first market refresh → radar freshness` is removed from the radar-critical path.
- `token evidence / token intents / deterministic resolutions` remains upstream of hydration and does not receive feedback from price success/failure.

No new collector, LLM worker, or real-time channel is introduced. The existing store-first architecture remains: external provider calls may enrich market facts, but API consumers read committed rows rather than mutable in-memory state.

## Core models

**RadarCandidate**

Semantic projection-run object representing one current window candidate. It is derived from token intents/resolutions/events and is not a new source of truth.

- `window`, `scope`
- `lane`: resolved or attention
- `target_type`, `target_id`, `pricefeed_id` when resolved
- `intent_id`, `resolution_id`, `lookup_keys`, `resolution_status`
- `source_event_ids`
- `social_start_ms`, `latest_seen_ms`
- `identity_basis`: exact_ca, gmgn_payload, cex_symbol, symbol_unique, ambiguous_symbol, unresolved

Invariant: two candidates with the same display symbol but different chain/address or CEX identity remain distinct candidates.

**MarketHydrationRequest**

Bounded request generated from a RadarCandidate, not from global registry scan.

- `target_type`, `target_id`
- `quote_kind`: current_quote or event_quote
- `provider_family`: cex or dex
- `freshness_sla_ms`
- `source_event_id` / `source_resolution_id` for event quote
- `attempt_reason`: missing, stale, event_quote_missing, provider_retry

Invariant: a request is eligible for radar budget only if it belongs to the current projection candidate set or is a direct dependency of one of those candidates.

**MarketSnapshot**

Current market observation used by tradeability/timing.

- provider, pricefeed id, observed time
- price, quote symbol, price basis
- market cap, liquidity, volume, open interest, holders when available
- status: fresh, stale, missing, provider_error, rate_limited, unsupported_chain
- age and lag fields

Invariant: `fresh` is a freshness claim about observation age, not a claim that the asset is high quality or canonical.

**EventPriceObservation**

Event-anchored observation used for social-start price.

- source event id
- source intent id
- source resolution id
- event received time
- provider and observed time
- price fields and price basis
- observation kind: message_payload or message_quote
- lag/status when provider result is late or unavailable

Invariant: event price never pretends to be a historical tick at exact tweet time unless provider actually returns that timestamp. If fetched after the event, lag is visible.

**RadarRow**

Public read model emitted by projection.

- identity block: resolution status, target identity, lookup keys, discovery status
- social block: attention, heat, propagation, discussion quality
- market readiness block: current quote readiness, event quote readiness, status reason, age/lag
- score block: component breakdown and final decision
- data health block: identity, market, coverage, projection version

Invariant: a row can rank socially without being market-ready, but a row cannot be marked as actionable driver without market readiness.

**ColdRegistryAsset**

Historical identity/metadata memory outside radar SLA.

- chain/address identity
- symbol/name/metadata
- primary source and status
- retained/demoted refresh eligibility

Invariant: existence in registry does not imply membership in current radar candidate set and does not imply price refresh SLA.

## Interface contracts

`/api/token-radar`

- Endpoint name and query parameters remain `window`, `scope`, `limit`.
- Response is a hard-cut new projection version. The service reads only the new radar projection version and does not fallback to legacy rows.
- `targets` contains resolved candidates; `attention` contains unresolved or not-yet-actionable candidates.
- Every row exposes identity, social score components, market readiness, event price readiness, decision, data health, source event ids, and projection version.
- Legacy ambiguity where `market_json` and `price_json` are identical may be removed. Consumers must read explicit market readiness fields rather than infer from a single stale/missing string.
- Error mode for missing projection remains a normal empty/missing projection response, not an online provider call from the API handler.

WebSocket consumers

- No new real-time route is introduced.
- If token radar updates are pushed through existing event payloads in a later plan, the payload must carry the same projection version and market readiness semantics as HTTP.
- Production live event delivery remains `/ws`; MCP/FastMCP stays optional control/query infrastructure.

CLI / ops surfaces

- Existing query/ops commands may surface projection version, hydration status, provider error counts, and cold registry counts.
- CLI must not silently merge old and new projection versions in one report.
- Any destructive physical cleanup of historical registry rows requires an explicit operator command and confirmation; demotion from active refresh universe can be part of normal hygiene.

Database/read model semantics

- Existing historical `token_radar_rows`, `price_observations`, and registry rows remain audit facts.
- New projection writes a new version and API reads only that version.
- Market observations remain append-only facts; freshness is computed from observed time and projection time.
- Registry status alone is not the market refresh eligibility contract for radar.

## Acceptance criteria

- AC1. WHEN a `5m/all` or `1h/all` projection run starts THEN system SHALL derive market hydration input exclusively from that run's RadarCandidate set and its direct dependencies.
- AC2. WHEN an active registry asset is stale but is not part of the current RadarCandidate set THEN system SHALL NOT spend radar-critical market hydration budget on it.
- AC3. WHEN a current resolved Asset candidate has chain/address identity and the DEX provider returns a quote THEN system SHALL write a current quote observation before the projection row is committed, and the row SHALL report `fresh` with an observation age.
- AC4. WHEN a current resolved CexToken candidate has a preferred CEX pricefeed and the CEX provider returns a quote THEN system SHALL write a current quote observation before the projection row is committed, and the row SHALL report `fresh`.
- AC5. WHEN provider returns no market or rate-limits a current candidate THEN system SHALL expose `missing`, `provider_error`, or `rate_limited` with status reason and SHALL NOT rank the row as an actionable driver.
- AC6. WHEN a source event has a resolved target and provider quote succeeds for event/start price THEN system SHALL attach the observation to source event / intent / resolution and expose event price readiness in the radar row.
- AC7. WHEN message/start quote backlog contains old rows THEN recent 5m/1h candidate rows SHALL still be attempted before old backlog rows for radar-critical hydration.
- AC8. WHEN a tweet contains a chain+CA token mention THEN evidence id, intent key shape, resolver status meaning, lookup keys, and target identity SHALL remain the same before and after this design, except for additive market observations.
- AC9. WHEN a tweet contains only a cashtag with multiple active chain assets THEN hydration SHALL NOT collapse the candidates into one hidden symbol-level row; rows SHALL remain distinct by target identity or remain attention/ambiguous according to resolver result.
- AC10. WHEN a GMGN payload includes price or market cap THEN the payload observation SHALL remain an event/message observation and SHALL NOT be overwritten by later current quote semantics.
- AC11. WHEN active registry contains thousands of cold assets THEN `/api/token-radar?window=5m` SHALL still show only current window candidates and market statuses derived from current candidate hydration.
- AC12. WHEN downstream clients call `/api/token-radar` after rollout THEN they SHALL receive only the new projection version; there SHALL be no dual-read legacy fallback or compatibility transform.
- AC13. WHEN score formula semantics are changed in a later plan THEN score/projection version SHALL be bumped and component breakdown SHALL remain present. If formula semantics do not change, this spec requires no resolver policy bump.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Hydration blocks projection and makes radar slower. | High | Use bounded provider budget per projection run; commit rows with explicit provider status when budget is exhausted rather than waiting indefinitely. |
| Provider rate limits increase because current candidates are hydrated more aggressively. | High | Deduplicate by target within a run, batch DEX token price requests by chain/address, cache fresh observations by freshness SLA, and expose `rate_limited` instead of retry storms. |
| Hard cut breaks frontend/client assumptions around `market_json` / `price_json`. | Medium | Treat this as a versioned contract change; update clients in the same release and remove old fallback paths rather than serving mixed semantics. |
| Market failure is mistaken for token extraction failure. | Medium | Keep extraction/resolver tests and invariants separate; hydration status must live in market readiness, never in evidence/intent/resolution status. |
| Event/start price fetched after the event is misread as exact historical price. | Medium | Persist and expose provider observed time, event received time, and quote lag; use explicit status when lag exceeds acceptable threshold. |
| Cold asset pages or historical investigations lose fresh prices after radar budget is isolated. | Low | Keep a low-priority cold registry steward or lazy non-radar refresh path, but make it best-effort and outside radar SLA. |
| Demoting polluted long-tail registry assets hides an asset that later becomes relevant. | Low | Demotion removes refresh priority, not audit history; exact CA or fresh GMGN payload evidence can reintroduce it into current candidate hydration. |
| Same symbol multi-chain assets continue to look like duplicates to users. | Medium | Expose chain/address/identity basis clearly; defer project-level aggregation to a separate spec rather than silently merging distinct contracts. |

## Evolution path

The next plausible expansion is project-level aggregation above target identity: multiple chain contracts or wrapped forms could roll up under a project/entity view while preserving target-level market facts. This should not be added until the target-level candidate hydration contract is stable, because project aggregation can hide the exact source of stale/missing prices.

Another expansion is adaptive provider budgeting: candidate hydration could allocate more budget to high social heat, watched-account first-seen assets, or assets with independent-author propagation. That should remain deterministic and auditable, with component breakdown preserved.

A persistent hydration queue or materialized current candidate table may become justified if projection-time hydration cannot meet latency targets under measured load. If introduced later, it must store derived scheduling state only, not replace events/intents/resolutions as source of truth.

Finally, registry hygiene can become stricter after hard cut: long-tail search candidates that never receive exact CA evidence, current social mentions, or canonical promotion can be archived/demoted more aggressively. Physical deletion should remain a separate operator action with backup and verification.

## Alternatives considered

- Hot-priority patch on the existing global registry queue - rejected because it keeps the wrong owner. It would reduce the symptom for top candidates but still defines market freshness as a property of the entire active registry, so cold history can leak back into radar whenever priority scoring is wrong.

- Increase refresh limits or worker frequency - rejected because it spends more provider budget on the same unbounded universe. The local snapshot already shows current 5m stale targets ranked thousands deep; increasing limit treats the backlog as a capacity problem when it is primarily an ownership problem.

- API-time lazy price fetch - rejected because `/api/token-radar` would become slow, non-idempotent, provider-dependent, and hard to audit. The project architecture is store-first; consumers should read committed projection rows.

- New persistent `radar_candidate_queue` table in the first release - rejected for now because source rows already reconstruct the candidate set per projection run. A new table adds lifecycle and cleanup risk before measuring whether in-memory candidate hydration is insufficient.

- Rewrite token extraction / resolver state machine - rejected because current failures are market hydration and registry refresh ownership failures, not evidence/intent construction failures. Changing extraction would risk breaking the mature CA/cashtag/GMGN payload state machine while leaving stale price scheduling unresolved.

- Keep legacy projection compatibility path - rejected by product direction. This is a hard-cut contract change: old rows can remain as historical facts, but API and retrieval should not mix old/new radar market semantics.

- Physically delete polluted registry rows as the primary fix - rejected as the first move because deletion is destructive and does not solve current candidate hydration. Demotion/removal from active refresh universe is sufficient for radar correctness; physical cleanup can follow with explicit approval.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Build radar candidates from current window source rows before market hydration. |
| Always | Hydrate current radar candidates before writing the new projection when provider budget allows. |
| Always | Keep extraction/evidence/intent/resolver state machine semantics separate from market readiness. |
| Always | Expose market readiness and event price readiness explicitly in radar rows. |
| Always | Bump radar projection contract and hard-cut API reads to the new version. |
| Always | Treat registry as identity memory, not as the radar refresh universe. |
| Ask first | Physically delete registry assets or historical price observations. |
| Ask first | Change resolver semantics, symbol dominance policy, or lookup key format. |
| Ask first | Add a persistent queue/table/materialized view for candidate hydration. |
| Ask first | Change authentication, authorization, billing, or data-deletion behavior. |
| Never | Let a stale global registry refresh rank determine whether a current radar candidate has price. |
| Never | Mark a row as actionable driver when current market readiness is missing/stale/provider-error. |
| Never | Collapse distinct chain/address targets into one symbol row without a separate project-aggregation spec. |
| Never | Use LLM calls to decide token identity or market readiness in this design. |
| Never | Route production live updates through MCP instead of `/ws`. |
