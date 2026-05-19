# Spec — News Intel Kappa/CQRS Production Loop

**Status**: Implemented in `codex/news-intel-kappa-cqrs`, pending final review
**Date**: 2026-05-19
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKFLOW.md`
- `docs/DESIGN_DISCIPLINE.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-11-search-v2-hard-cut-cn.md`
- `/Users/qinghuan/Documents/code/news-intel/docs/research/2026-04-15-continuity-aware-news-clustering-redesign.md`
- `/Users/qinghuan/Documents/code/news-intel/docs/research/2026-05-02-production-event-quality-layering.md`

## 一句话

在 `gmgn-twitter-intel` 内新增独立 `news_intel` 域，用 PostgreSQL facts + rebuildable read models 重做新闻接入后的生产闭环：先稳定看到原始新闻，再可审计地展示实体抽取、token 身份解析、story 去重、事实候选、拒绝原因和 attention lane；不接入 Token Radar，不做交易闭环，不把 embedding 或 LLM 输出当成事实。

## 背景

当前 `gmgn-twitter-intel` 的全局架构已经是 facts-first Kappa/CQRS。架构文档明确把 `events`、`token_intents`、`token_intent_resolutions`、`asset_identity_current`、`market_ticks`、`enriched_events` 等 PostgreSQL 表定义为业务事实，derived read models 可重建（`docs/ARCHITECTURE.md:31-38`）。同一文档还规定每个 read model 只有一个 runtime writer（`docs/ARCHITECTURE.md:55-70`），`NOTIFY` 只是 wake hint，listener 必须重读数据库并保留 bounded interval catch-up（`docs/ARCHITECTURE.md:71-75`）。这些约束正是新闻系统应复用的基础，不应再引入 LanceDB 作为第二事实源。

现有 token identity 已经比 `news-intel` 更成熟。Token Intel 架构说明从 GMGN frame 到 `token_evidence`、`token_intents`、`token_intent_resolutions`、`registry_assets`、`asset_identity_evidence/current` 的生产链路，且明确 token evidence、intent、resolver、asset identity ledger 各有边界（`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md:7-45`）。同一文档强调：symbol 是 recall key，不是 identity；chain+address 或 CEX registry fact 才是 identity（`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md:118-129`）。

实体抽取已有可复用的 deterministic 基础。`entity_extractor.py` 已经能从文本中抽取 EVM、Solana、TON 地址、cashtag、hashtag、mention、URL、domain，并记录 span、surface、sentence/local group（`src/gmgn_twitter_intel/domains/evidence/services/entity_extractor.py:79-196`）。地址归一化使用链 hint 和地址校验，而不是裸 regex 猜测（`src/gmgn_twitter_intel/domains/evidence/services/entity_extractor.py:198-238`）。

现有 search v2 也已经沉淀了一个对新闻同样关键的经验：先 deterministic target lookup，再 lexical / trigram fallback；embedding 不能掩盖 deterministic retrieval 缺口（`docs/superpowers/specs/active/2026-05-11-search-v2-hard-cut-cn.md:53-68`）。新闻不应重走 `news-intel` 的 embedding-first dedup 路径。

`news-intel` 的失败经验很明确。2026-04-15 的复盘显示，生产里出现 `34 articles -> 31 clusters`、`576 articles -> 452 clusters`、`370 singleton clusters`，原因链条是 article identity 对 rolling updates 友好但 clustering 不恢复 continuity、RSS summary HTML/boilerplate 不稳定、embedding 来自 `title + raw summary`、cluster assignment 依赖单一 semantic threshold（`/Users/qinghuan/Documents/code/news-intel/docs/research/2026-04-15-continuity-aware-news-clustering-redesign.md:10-71`）。2026-05-02 的复盘则说明，系统能 ingest/dedup/LLM/validate/backlog drain 后，真正 blocker 变成 source authority、event-specific slots、realis、tradable identity、novelty、watch 噪音和 unknown token 放行（`/Users/qinghuan/Documents/code/news-intel/docs/research/2026-05-02-production-event-quality-layering.md:5-31`）。

因此这次不应问“怎么把新闻源接进来”，而应问“接入后如何在生产数据流里把观察、mention、identity、story、fact candidate、accepted fact 分层，并让每一步可解释、可重建、可拒绝”。

## 问题

用户现在需要一个独立新闻页，先能看见新闻，同时能观察接入后的处理状态：哪些新闻只停留在 raw，哪些提取出 token mention，哪些 token 被解析或判为 ambiguous/unknown，哪些文章被合并为同一 story，哪些事实候选被接受或拒绝。当前项目没有 `news_intel` 域、没有新闻事实表、没有新闻 worker、没有新闻页面契约。如果直接复制 `news-intel`，会把旧系统的 LanceDB/embedding/LLM/event-board/closed-loop 复杂性带进来，并重复 unknown symbol、singleton story、validator 后置补救的问题。

## 第一性原则

**观察不是事实。** 新闻源 item 只是 provider observation。即使 title 里出现 `$ABC` 或 “ABC token”，它也只是 token mention，不是 token identity，更不是可消费事实。

**配置源必须先物化。** `config.yaml` 里的 sources 是 operator intent，不是 worker backlog。`news_fetch` 每轮必须先把配置源 reconcile 到 `news_sources`，再从 DB claim due sources；否则“配置了源但 DB 无行”会让接入静默失败。

**身份先于事实，来源先于接受。** 一个 fact candidate 只有在 affected target 可解释、required slots 完整、realis 合格、且 source role 足够权威时才能进入 accepted lane。裸 symbol、ambiguous symbol、unknown token，以及普通媒体转述，都进入 attention/rejected lane，而不是伪装成生产事实。

**去重是多信号身份问题，不是向量阈值问题。** story identity 先看 provider item、canonical URL、content hash、title fingerprint、source/time/token overlap；semantic embedding 只能作为未来 candidate recall，不是 V1 truth boundary。

**LLM 只能生成候选。** LLM 或规则可以提出 fact candidate，但 deterministic validator 才能决定 accepted/rejected/attention。每个展示 claim 必须能指回 source item、evidence quote/span、policy version 和 rejection reason。

**事实不能依赖读模。** `news_fact_candidates` 是 material fact/candidate 表，只能引用 material facts（如 `news_items`）。`news_story_groups`、`news_story_members`、`news_page_rows` 是 rebuildable read models；事实表不能通过 FK 依赖它们。

**Provider IO 不持有 DB session。** Worker 可以先从 DB claim source snapshot，关闭 session 后调用 RSS/API provider，再打开 worker session 写回结果。外部网络 IO 不在 transaction 或 pinned DB session 中发生。

**控制面不能级联删除事实。** `news_fetch_runs` 记录一次抓取尝试和诊断状态，但不是产品事实。`news_provider_items`/`news_items` 可以保留 fetch run 引用用于审计；删除或裁剪 fetch run 时不能级联删除 provider item、news item 或下游事实。

**缓存状态只能随成功持久化提交。** `etag`/`last_modified` 是 provider fetch cache，不是产品事实。只有 provider item、news item 和 fetch success audit 同一成功路径提交后，才能更新 source cache；否则一次中途失败可能让后续 `304 Not Modified` 永久跳过从未持久化的新闻。

**读模重建必须能推进。** `news_page_rows` catch-up 不能每轮只扫描最新 N 条；它必须优先选择 missing/stale/projection-version-mismatch 行。删除 read model 后，projection worker 应逐批覆盖完整 backlog，而不是依赖 API raw fallback 掩盖缺失。

**内容更新要打断旧归属。** rolling update 改变 title/summary/body/canonical identity 时，旧 story membership 和 page row 必须清理或标记 stale，让 item 重新走 process/story/page pipeline；否则旧 story 会永久污染页面连续性。

**页面是审计面，不是推理面。** API/Frontend 只能读 facts/read models，不做 provider calls、token resolution、dedup scoring、LLM 调用或 SQL join。

## Goals

- **G1 Raw news visible.** 开启 news worker 后，成功拉取的新闻 item 必须在独立 News 页面可见，且展示 provider、source、published/fetched time、canonical URL、title、summary、lifecycle。
- **G1a Source reconciliation visible.** 配置源被启用后，`news_sources` 必须出现对应行；删除或禁用配置源后，DB 行必须变为 disabled 而不是继续抓取。
- **G2 Token mention lifecycle visible.** 每条新闻的 token/address/symbol mention 必须展示 resolution status：`exact_address`、`known_symbol`、`unique_by_context`、`ambiguous_symbol`、`unknown_attention`、`non_crypto`、`nil`。
- **G3 Story grouping explainable.** 被合并到同一 story 的文章必须记录 match reason，如 `same_provider_item`、`same_canonical_url`、`same_content_hash`、`title_fingerprint_time_overlap`、`trigram_token_overlap`。
- **G4 Fact candidates auditable.** 每个 fact candidate 必须有 event type、claim、realis、evidence quote/span、source role、required slots、affected target status、validation status、rejection reasons。
- **G5 Page read model rebuildable.** `news_page_rows` 是 read model，唯一 runtime writer 是 News Page Projection worker；删除并重建后页面语义一致。
- **G6 No Token Radar coupling.** V1 不写 `token_radar_rows`，不改变 Token Radar scoring，不触发 Pulse，不把新闻 facts 注入现有 trading/agent decision 流。
- **G7 Missed wake safe.** 禁用或丢失 `NOTIFY` 时，所有 news workers 仍通过 `interval_seconds` catch-up 处理 backlog 并刷新页面读模。

## Non-goals

- 不做自动交易、shadow decision、settlement、attribution、learning。
- 不接入 Token Radar，不创建 token alpha score，不改变 Pulse candidate admission。
- 不引入 LanceDB、pgvector、embedding worker、external search service、Kafka、Redis Stream 或 Materialize。
- 不做 full-web crawler。V1 只支持配置的 RSS/Atom/API-like feed sources；正文抓取可以作为后续演进。
- 不让 LLM 决定 token identity。
- 不让 unknown symbol 进入 accepted fact；unknown 只进入 attention lane。
- 不做多语言新闻理解；V1 以英文 feed 为主，其他语言保留 raw 和 token mention，但 fact candidate 可标记 `semantic_unavailable`。

## Target Architecture

新增 `domains/news_intel`，作为独立 bounded context。它读取外部 news sources，并通过现有 domain interfaces 查询 token/asset identity；它不写 Token Radar、不写 Pulse、不写 market ticks。

责任划分：

| Layer | Owns | Does not own |
|-------|------|--------------|
| `news_intel` | news source fetch, raw item normalization, news entities, token mention observations, story grouping, fact candidates, news page read model | Token Radar score, Pulse decisions, market ticks, token identity policy |
| `token_intel` / `asset_market` | current token/asset identity, registry facts, resolution policy | News source ingestion, news story/fact lifecycle |
| API surfaces | Translate `/api/news*` calls into news read services | Provider calls, extraction, scoring, SQL joins, resolution mutation |
| Frontend News page | Render lifecycle, lanes, story/fact detail, filters | Infer sentiment/facts, run dedup, resolve tokens |

Workers:

| Worker | Runtime role | Writes | Wake-in | Wake-out |
|--------|--------------|--------|---------|----------|
| `news_fetch` | Fetch configured feeds with per-source cursor/cache/backoff | `news_fetch_runs`, `news_provider_items`, `news_items`, source fetch state | poll | `news_item_written` |
| `news_item_process` | Extract entities, token mentions, deterministic item-level fact hints | `news_item_entities`, `news_token_mentions`, `news_fact_candidates` | `news_item_written`, poll | `news_item_processed` |
| `news_story_projection` | Build deterministic story groups from item/entity/mention facts | `news_story_groups`, `news_story_members` | `news_item_processed`, poll | `news_story_updated` |
| `news_page_projection` | Build product-facing rows for the independent News page | `news_page_rows` | `news_item_written`, `news_item_processed`, `news_story_updated`, poll | none |

The split is intentionally smaller than `news-intel`: no embedding stage, no event board stage, no closed-loop market-data stage. It still respects one-writer read model ownership: story grouping and page projection have named writers; raw/provider/entity/token/fact rows are facts or candidate facts.

## Conceptual Data Flow

```text
configured RSS/API feed source
  -> news_fetch
  -> news_provider_items + news_items
  -> news_item_process
  -> news_item_entities + news_token_mentions + news_fact_candidates
  -> news_story_projection
  -> news_story_groups + news_story_members
  -> news_page_projection
  -> news_page_rows
  -> /api/news + /api/news/stories/{story_id} + /api/news/items/{news_item_id}
  -> web News page
```

Identity lookup flow:

```text
news_item_entities
  -> token mention candidate
  -> token/asset identity read interface
  -> resolution status + reason codes + candidate targets
  -> news_token_mentions
```

No arrow exists from news facts to `token_radar_rows` in V1. If a future spec wants cross-domain propagation, it must add a separate, explicitly gated projection from accepted news facts to another read model.

## Core Models

**News Source**: configured source identity and operational policy. It distinguishes provider type (`rss`, `atom`, `json_feed`, `manual_api`), source domain, source role, trust tier, refresh interval, and enabled status.

**News Provider Item**: raw provider observation keyed by source/provider item identity plus payload hash. It preserves raw payload for audit and retry diagnostics.

**News Item**: normalized article/feed item. It contains title, summary, optional body text, canonical URL, source domain, published/fetched timestamps, language, content hash, and lifecycle status.

**News Item Entity**: span-aware extracted entity. Entity types include address, symbol/cashtag, project alias, URL, domain, source mention, organization, person, location. Token-relevant entities must retain span and surface.

**News Token Mention**: token-relevant observation plus deterministic identity result. It preserves what the article said separately from what the resolver selected.

**News Story Group**: rebuildable grouping of related news items. It is not an accepted fact; it is a reporting continuity object with match evidence and policy version. Material fact/candidate tables must not FK into story groups.

**News Fact Candidate**: candidate state transition claimed by a source. It carries event type, realis, evidence quote/span, source role, slots, affected target status, validation status, and rejection reasons. It references `news_item_id`; story association is derived through story membership/read queries.

**News Page Row**: denormalized read model for UI. It contains enough lifecycle and evidence summaries to render the news tape without UI joins.

## Interface Contracts

### `GET /api/news`

Returns paginated News page rows. Filters: `window`, `status`, `lane`, `target`, `source`, `q`, `cursor`, `limit`.

Semantics:
- `status` filters lifecycle state, not fetch worker state.
- `lane=attention` returns ambiguous/unknown token mentions and rejected/attention fact candidates.
- `target` filters resolved target id or display symbol; ambiguous symbols must not silently match resolved targets.
- Cursor pagination is stable by `(latest_event_at_ms, news_item_id)`.

### `GET /api/news/items/{news_item_id}`

Returns one news item with raw normalized fields, entities, token mentions, story membership, fact candidates, and fetch/source metadata.

### `GET /api/news/stories/{story_id}`

Returns story group, members, match reasons, source domains, token mention rollup, and fact candidate rollup.

### `GET /api/news/facts/{fact_candidate_id}`

Returns fact candidate detail, validation status, evidence quote/span, slots, source profile, affected target resolution, and rejection reasons.

### `GET /api/news/sources/status`

Returns source health: last fetch, last success, next due, consecutive failures, last error type, item counts.

V1 does not add a news-specific SSE stream. The frontend uses bounded polling through the existing API client; a future stream must be a separate contract change.

## Acceptance Criteria

- **AC1.** WHEN a configured feed returns a valid item THEN system SHALL persist `news_provider_items` and `news_items`, and `/api/news` SHALL return the row with lifecycle `raw`.
- **AC1a.** WHEN `news_intel.sources` contains an enabled source THEN `news_fetch` SHALL reconcile that source into `news_sources` before claiming due work; when the source is removed or disabled in config, it SHALL not be fetched again.
- **AC2.** WHEN a news item contains a valid chain address THEN system SHALL create a token mention with `resolution_status=exact_address` or `nil` with reason codes; it SHALL NOT store only a display symbol.
- **AC3.** WHEN a news item contains a naked unknown symbol THEN system SHALL put it in `unknown_attention` or `ambiguous_symbol`; it SHALL NOT become an accepted fact target.
- **AC4.** WHEN two items have the same canonical URL or content hash THEN story projection SHALL group them and record the exact match reason.
- **AC5.** WHEN two items only have similar titles THEN story projection SHALL require time proximity plus token/source/lexical overlap; it SHALL NOT group solely on trigram similarity.
- **AC6.** WHEN a fact candidate lacks required event slots, lacks production-eligible target identity, has weak realis, or comes only from non-authoritative media reporting THEN validator SHALL keep it out of `accepted` and expose explicit rejection/attention reasons in `/api/news/facts/{id}`.
- **AC7.** WHEN `news_page_rows` is truncated and `news_page_projection` runs catch-up THEN `/api/news` SHALL return semantically equivalent rows rebuilt from facts.
- **AC8.** WHEN wake notifications are not delivered THEN workers SHALL still process due work on interval catch-up.
- **AC9.** WHEN V1 ships THEN repository search SHALL find no runtime writes from `news_intel` to `token_radar_rows`, `pulse_candidates`, or market tick facts.
- **AC10.** WHEN the frontend renders `/news` THEN the first viewport SHALL show the live news tape with lifecycle, token lane, source, story, and fact status without requiring Token Radar data.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| News worker becomes another large closed-loop system | High | V1 has four workers only, no embedding, no trading, no Token Radar write, no Pulse dependency. |
| Unknown tickers contaminate facts | High | Token mention state separates observed symbol from resolved target; accepted facts require production-eligible resolution. |
| Configured sources never become due work | High | `news_fetch` reconciles operator config into `news_sources` before every due-source claim; disabled/removed sources are terminalized as disabled. |
| Candidate facts depend on rebuildable story IDs | High | `news_fact_candidates` references only `news_items`; story links are derived by joining through `news_story_members` at read time. |
| Provider calls exhaust or pin DB sessions | Medium | Worker design snapshots source rows, closes DB session, calls provider, then persists in a fresh worker session. |
| Story grouping over-merges unrelated articles | Medium | Exact matches win first; fuzzy grouping requires multiple signals and stores match reasons. |
| Story grouping under-merges rolling updates | Medium | Canonical URL/content hash/provider continuity are first-class match reasons before lexical scoring. |
| Source aggregators hide original source | Medium | Source model stores provider and source separately; UI exposes provenance. |
| API request path starts doing work | Medium | Contract forbids provider calls, token resolution, extraction, or scoring in API surfaces; architecture tests enforce imports. |
| Page shows stale processing as truth | Medium | Lifecycle states and source/worker status are explicit; page rows are rebuildable and include computed_at/policy_version. |

## Evolution Path

The next plausible expansion is structured LLM fact candidate extraction over story groups, using the same `news_fact_candidates` table and validator. That expansion should add a model run audit table and required slot schemas, but still keep LLM output as candidate-only. Semantic embeddings can later be added as an explicit candidate-recall route for story grouping or search, but only after deterministic URL/content/title/token/source grouping is measured.

Another expansion is an explicit cross-domain projection from accepted news facts into a separate token-news read model. That must be a new spec and must not reuse Token Radar scoring paths by implication.

## Alternatives Considered

- **Copy `/Users/qinghuan/Documents/code/news-intel` into this repo** — rejected because its architecture already mixed LanceDB, embedding-first story grouping, LLM extraction, event board, market data, settlement, and learning. The useful part is the failure evidence and quality gates, not the runtime topology.

- **Use OpenAlice-style RSS JSONL archive only** — rejected because it is good for lightweight tool search, but lacks persisted entity/token/story/fact lifecycle and would not satisfy production audit or page-state requirements.

- **Use Miniflux/FreshRSS as the core service** — rejected for V1 because they solve feed collection/readability, not crypto token identity, story grouping, fact validation, or Kappa/CQRS integration. They can be upstream providers later.

- **Use embedding/vector DB for dedup V1** — rejected because the prior failure came from unstable embedding inputs and threshold-centric assignment. V1 solves exact/near/deterministic grouping first.

- **Use only LLM extraction for entities and facts** — rejected because token identity and factual acceptance must be deterministic and replayable. LLM can propose fact candidates later; it cannot own identity or acceptance.

- **Attach news directly to Token Radar** — rejected because the user explicitly wants an independent page first, and because writing Token Radar before news processing quality is observable would repeat the old closed-loop failure.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve raw provider payloads; reconcile configured sources into DB; separate provider/source/item/story/fact identities; expose lifecycle and rejection reasons; use deterministic token identity reads; keep material facts independent from rebuildable read models; rebuild read models from facts. |
| Ask first | Add LLM fact extraction; add embeddings; add full article scraping; project accepted news facts into Token Radar or Pulse; add paid/news API providers. |
| Never | Treat naked symbol as identity; write Token Radar/Pulse/market facts from News V1; run provider calls or extraction in HTTP handlers; use `NOTIFY` as truth; silently hide rejected/ambiguous rows. |
