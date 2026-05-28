# Spec - News Intel 去重根治与 6551/OpenNews 同步契约

**Status**: Implemented core hard-cut slice in `codex/news-intel-dedup-root-fix`
**Date**: 2026-05-28
**Owner**: qinghuan / Codex
**Related**: `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`, `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`, `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`, `docs/WORKERS.md`

## Background

News Intel 的既有边界是独立的 News domain：它拥有 `news_provider_items`、`news_items`、`news_item_entities`、`news_token_mentions`、`news_fact_candidates`、`news_story_groups`、`news_story_members`、`news_page_rows` 等事实与读模型，不拥有 Token Radar、Pulse 或 market read models；domain map 明确把 provider raw input、processed item/entity facts、story/page/source-quality projections 分层描述在 `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md:14` 和 `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md:39`。全局架构要求 PostgreSQL material facts 是业务真相，read models 必须稳定、可重建、单写者，并且 unchanged projections 写零 serving rows，见 `docs/ARCHITECTURE.md:70`、`docs/ARCHITECTURE.md:137`、`docs/ARCHITECTURE.md:157`。

当前 worker 链路是 `news_fetch -> news_item_process -> news_story_projection -> news_item_brief -> news_page_projection -> /api/news`。`news_fetch` 在每轮 reconcile configured sources 后 claim due source、创建 fetch run、调用 provider，并把 observation upsert 到 `news_provider_items` 后再 upsert 到 `news_items`，见 `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py:57`、`src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py:120`、`src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py:218`。`news_item_process` 对 item 抽实体、token mention 和 fact candidate，见 `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py:38` 和 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:868`。`news_story_projection` 写 `news_story_groups/news_story_members`，见 `src/gmgn_twitter_intel/domains/news_intel/runtime/news_story_projection_worker.py:33`。`news_item_brief` 以单个 `news_item_id` 为单位运行 agent brief，见 `src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_brief_worker.py:123`。`news_page_projection` 以 item 为单位构建 `news_page_rows`，其 row id seed 包含 `news_item_id`，见 `src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py:39`，`/api/news` 直接读取 page rows，见 `src/gmgn_twitter_intel/domains/news_intel/queries/news_page_query.py:23` 和 `src/gmgn_twitter_intel/app/surfaces/api/routes_news.py:17`。

当前 DB 身份约束把 provider observation 和 public item 绑得过紧：`news_provider_items` 仅在 `(source_id, source_item_key)` 唯一，见 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:87`；`news_items` 仅在 `provider_item_id` 唯一，见 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:102` 和 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:126`；`canonical_url/content_hash/title_fingerprint` 只有普通索引，见 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:133`。repository 也按 `source_id + source_item_key`、`provider_item_id` upsert，见 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:437` 和 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:502`。

Story projection 现在同时承担“同一文章去重”和“同一事件聚合”两种语义。`choose_story_assignment` 会因相同 `canonical_url` 或 `content_hash` 合并 story，见 `src/gmgn_twitter_intel/domains/news_intel/services/news_story_grouping.py:23`，但 candidate query 没有取 `content_hash`，所以 exact content path 实际缺证据，见 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:1141`。同时，新 story id 使用 `policy_version + news_item_id` 作为 seed，见 `src/gmgn_twitter_intel/domains/news_intel/services/news_story_grouping.py:60`，重放顺序会影响 story identity。`upsert_news_item(status="updated")` 还会从 fetch path 删除 `news_story_members` 并刷新 `news_story_groups` 计数，见 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:599`，这和 story read model 单写者边界冲突。

2026-05-28 对真实 runtime 只读诊断确认 active config 来自 `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`，workers config 来自 `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`，未输出 secret。当前 enabled OpenNews sources 为 `opennews-news`、`opennews-listing`、`opennews-onchain`，配置分别订阅 `engineTypes: {"news":[]}`、`{"listing":[]}`、`{"onchain":[]}`，刷新间隔 10 秒，`hasCoin=true`。DB 里 enabled `source_item_key` duplicate groups 为 0，说明 source 内 provider key 层没有重复爆炸；但 enabled `canonical_url` duplicate groups 为 552，涉及 1678 rows，最大单 URL 123 rows；enabled `content_hash` duplicate groups 为 512，涉及 1070 rows；enabled `title_fingerprint` duplicate groups 为 787，涉及 1765 rows。`news_page_rows` 总数 6337，其中 disabled source page rows 1999，主要来自 `yahoo-finance` 1440、`opennews-realtime` 166、`cointelegraph` 82、`decrypt` 70、`coindesk` 55。Story groups 总数 4365，multi-item 842，最大 story 123 items；match reason 中 `same_canonical_url` 有 2271 members，表明 homepage/live/container URL 正在造成过度合并。

6551/OpenNews 官方文档显示 OpenNews 是 84+ sources、6 engine categories 的聚合服务；`engineType` 包括 `news`、`listing`、`onchain`、`meme`、`market`、`prediction`，`newsType` 是 engine 下的 source code；文章带 AI impact score、trading signal 和中英 summaries。官方 README 还定义 WebSocket endpoint `wss://ai.6551.io/open/news_wss?token=<redacted>`、`news.subscribe` filters、`news.update` 与 `news.ai_update` 推送，并把 article `id` 描述为 unique article id，字段包括 `text`、`newsType`、`engineType`、`link`、`coins`、`aiRating`、`ts`。这些语义见 6551Team/opennews-mcp README 的 Data Sources、WebSocket 和 Data Structure 部分：https://github.com/6551Team/opennews-mcp 。官方 usage guide 也把 `id`、`engineType`、`newsType`、`aiRating.status="done"` 等字段列为 article contract：https://github.com/6551Team/opennews-mcp/blob/main/knowledge/guide.md 。

本地 OpenNews client 已经把同一 fetch 内的 `news.update`、`news.ai_update` 和 REST item 按 entry id merge，见 `src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py:411` 和 `src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py:446`。但 hybrid fetch 仍是短 WS 后单次 REST，见 `src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py:136` 和 `src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py:176`；REST body 默认 `page=1`，见 `src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py:353`；provider wiring 丢弃 `since_ms` 和 `cursor`，见 `src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py:53`。这意味着 `/open/news_search` 现在被当成最新一页轮询，而不是 bounded catch-up。

## Problem

News 模块现在把 provider observation、真实文章事实、story/event grouping 和 public page row 混在 `news_item_id` 这一层处理，导致重复数据不能在正确层级审计和折叠，homepage/live/container URL 又会在 story 层过度合并不相干新闻；同时 OpenNews REST 同步没有持久 watermark/overlap/page scan，disabled sources 的旧 page rows 仍被 `/api/news` 服务，最终表现为用户可见重复新闻、错误 story、agent brief 重复成本、读模型污染和潜在漏数。

## First Principles

1. Provider observation 不是产品事实。`news_provider_items` 应表达“某 source 在某次 provider 同步中看见了某条上游 payload”，而不是“一篇可展示新闻”。当前 schema 的 `(source_id, source_item_key)` 唯一性只能保证 source 内 observation 幂等，见 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:87`，不能承担跨 source 或跨 provider article 的产品去重。

2. Article identity、duplicate identity 和 story identity 必须分层。`news_items(provider_item_id)` 现状让每个 provider observation 都长成一个 item，见 `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py:126`；`news_story_groups` 是 read model，见 `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md:29`，不能作为事实层去重账本。去重事实必须可审计、可重放、顺序无关，story 只负责“多篇规范化文章属于同一发展事件”。

3. Canonical URL 是证据，不天然是唯一键。`canonicalize_url` 当前只做 host lower、tracking query stripping 和 trailing slash 处理，见 `src/gmgn_twitter_intel/domains/news_intel/services/text_normalization.py:32`；homepage、publisher root、live blog 和 aggregator URL 会承载多个不同事实，不能直接触发 hard dedup 或 exact story merge。

4. Serving row 是产品视图，不是 raw item dump。`news_page_rows` 当前按 `news_item_id` 出 row，见 `src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py:39`，API 又直接读取这些 rows，见 `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:789`。默认 public tape 必须只服务 enabled sources 的 representative rows，并通过 detail surface 展开 observations 和 duplicate evidence。

5. OpenNews sync 必须 at-least-once、idempotent、bounded catch-up。官方 OpenNews `id` 是 article id，WS `news.update` 和 `news.ai_update` 是同一文章的版本化输入，REST `page` 是搜索分页而非持久 cursor；本地 provider interface 已有 `since_ms/cursor` 形状但 OpenNews path 当前丢弃它们，见 `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py:136` 和 `src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py:53`。

## Goals

- G1. `/api/news` 默认结果中，同一 canonical item 最多出现 1 条 representative row；同一 `content_hash` 的 exact duplicate 在 public list 中 visible duplicate excess 为 0，同时 raw observations 与 source evidence 保留。
- G2. Disabled source 不再污染 serving read model；当 source 被配置移除或 disabled 后，projection catch-up 完成时 `/api/news` 和 `news_page_rows` 的 disabled-source serving rows SHALL 为 0。
- G3. OpenNews 同一 article `id` 的 `news.update`、`news.ai_update` 和 REST item SHALL 合并为同一 provider article observation/canonical item 更新，不新增 public row；partial payload 不得覆盖 ready `aiRating.status="done"` payload。
- G4. OpenNews REST catch-up SHALL 使用 per-source durable high watermark + overlap scan；worker restart 或短暂停顿后，只要 missed articles 仍在 bounded overlap/page budget 内，系统 SHALL 补齐而不是只读最新 `page=1`。
- G5. URL identity SHALL 区分 `article`、`live_page`、`homepage`、`aggregator`、`unknown` 等语义；只有 article-like URL 能单独触发 hard URL dedup 或 exact URL story merge。`https://tass.ru/`、`https://www.afp.com` 这类 container URL 不得再把不同标题/内容强行合并成一个 story。
- G6. Story rebuild SHALL 顺序无关：同一 fixture 乱序输入时，canonical item ids、duplicate clusters、story ids、page row ids 和 visible rows 完全一致。
- G7. Agent brief 默认以 canonical item 或 story representative 为输入；同一 canonical item 在相同 artifact/input hash 下最多产生 1 个 current brief。
- G8. News read models 继续遵守 Kappa/CQRS：story/page/source-quality projections 各自单写者，unchanged rows 写入数为 0，dirty target catch-up bounded，不引入全表 idle scans。

## Non-Goals

- N1. 不做 frontend-only hide、API-only filter 作为根修；API enabled-source filtering 可作为 guardrail，但 source of truth 必须在事实身份和 projection。
- N2. 不删除 material facts 作为第一手段；历史 raw observations、provider payload、duplicate evidence 和 backfill audit 必须保留。
- N3. 不把 `market`、`meme`、`prediction` engine 混入现有 News tape，除非另开产品 spec；当前只规范 `news`、`listing`、`onchain`。
- N4. 不引入 embeddings、vector DB、LLM fuzzy dedup 或人工黑名单作为第一阶段方案；第一阶段只做 deterministic identity、弱匹配证据和可审计 projection。
- N5. 不重写 Token Radar、Pulse、market data 或跨 domain scoring；News 可以产出 facts，但不直接写其他 domain read models。
- N6. 不把 provider fetch run id、attempt id、timestamp、UUID 作为 current serving identity。
- N7. 不保证 OpenNews REST 全历史回补；本 spec 只要求 bounded catch-up 和可配置 backfill/repair。

## Target Architecture

目标架构采用五层 KISS 模型：Raw Observation、Canonical Item、Duplicate Edge/Cluster、Story、Serving Row。必要时允许对 News identity/projection 子系统做 bounded rewrite，但不重写整个 News 模块和跨 domain pipeline。

Raw Observation 层保留 `news_provider_items` 的语义：它只表示 source/provider 看见的上游 item 或 patch。`source_id + source_item_key` 仍可作为 source 内幂等键；对 OpenNews，还必须记录 provider-global article identity，即 `provider_type=opennews + article_id=id`。如果同一 OpenNews `id` 经多个 source config 或 WS/REST 路径到达，系统只把它当同一 provider article 的多个 observation/version，而不是多个 public news。

Canonical Item 层表达“一篇规范化新闻内容”。它的 identity 由 strongest deterministic evidence 决定：OpenNews provider article id when valid、article-like normalized URL、strong content hash。URL 是 container/live/homepage 时不能成为 hard key；content hash 和 title fingerprint 可作为补充证据。Canonical item 保存当前 winner payload：title/body/summary/link/published_at/source precedence/AI metadata/token evidence，并保留它来自哪些 provider observations。

Duplicate Edge/Cluster 层是事实账本，不是 read model 临时状态。每条 edge 记录 observation 或 legacy item 与 canonical item 的关系、match type、policy version、confidence、evidence。`same_provider_article_id`、`same_article_url`、`same_content_hash` 是 deterministic strong edge；`near_title_same_source_window` 只能是 weak edge，需要保留 evidence 和 attention/diagnostic 状态，不能静默覆盖 strong identity。

Story 层只表达“多个 canonical items 属于同一发展事件/主题”。同一篇转载或同一 provider article 的多个版本不应膨胀为多个 story members。Story id 必须由 canonical story key 或确定性最小 key 生成，不能依赖谁先被处理。Story projection 是 `news_story_groups/news_story_members` 的唯一 runtime writer；fetch/upsert path 不得直接删除或修改 story read model。

Serving Row 层是 public product view。`/api/news` 默认按 canonical item 或 story representative identity 出 row，而不是按 provider observation/legacy `news_item_id` 出 row。Row payload 展示 `duplicate_count`、`source_count`、source names、primary source、representative title、AI score、token mentions、story context；detail surface 展开 raw observations、duplicate edges 和 source evidence。Projection 对 disabled source 的 rows 做删除或不生成；unchanged payload 通过 payload hash 零写。

OpenNews Sync 层使用 WS 低延迟、REST 权威 catch-up 的混合契约。WS `news.update` 和 `news.ai_update` 都是 provider input patch；REST `/open/news_search` 从 `page=1, limit=100` 开始 bounded scan，直到页内最老 `ts` 早于 `high_watermark_ts_ms - overlap_ms` 或达到 `max_pages/max_items`。Watermark 只在 DB commit 成功后推进；overlap 覆盖 AI rating 延迟和 worker interval 抖动。REST `page` 不持久化为 cursor，持久化的是 source-level high watermark、overlap policy 和可选 `seen_ids_at_highwater`。

## Conceptual Data Flow

```
settings.news_intel.sources
  -> source reconcile
  -> provider fetch / OpenNews WS + REST catch-up
  -> raw provider observations
  -> canonical item resolver
  -> duplicate edges / canonical clusters
  -> canonical item processing
  -> story projection from canonical items
  -> brief projection for canonical representative
  -> page projection representative rows
  -> /api/news and detail endpoints
```

Changed arrows:

- `provider fetch -> raw provider observations` remains at-least-once and source-scoped, but OpenNews adds provider-global article id semantics and durable catch-up watermark.
- `raw provider observations -> canonical item resolver` is the new root fix. It prevents observation count from becoming public item count.
- `canonical item resolver -> duplicate edges / canonical clusters` makes dedup auditable and rebuildable instead of hiding it inside story assignment.
- `story projection from canonical items -> page projection representative rows` separates same-article dedup from same-event grouping.
- `page projection representative rows -> /api/news` makes enabled-source and representative-row policy part of serving read model, with API guardrails as defense in depth.

## Core Models

Provider Observation:

- Semantic key: provider/source observation identity, currently `source_id + source_item_key`; for OpenNews also includes provider-global `article_id`.
- Invariants: at-least-once input; raw payload preserved; delayed fields may update same observation; partial payload cannot overwrite ready analysis.

Provider Article Version:

- Semantic key: `provider_type + provider_article_id`.
- Invariants: OpenNews `news.update`, `news.ai_update` and REST payload with same `id` are versions of one article; version merge is deterministic and status-aware.

Canonical Item:

- Semantic key: strongest deterministic dedup key selected by policy version.
- Candidate fields: canonical item id, dedup key, dedup key kind, dedup key confidence, URL identity kind, representative payload, published timestamp, current content hash, title fingerprint, source precedence, lifecycle status.
- Invariants: one real article/content fact maps to one canonical item; key does not depend on fetch run, processing order, attempt id or timestamp.

Duplicate Edge:

- Semantic fields: source observation or legacy item id, canonical item id, match type, confidence, policy version, evidence, first/last seen timestamps.
- Invariants: exact edges are deterministic and idempotent; weak edges are auditable and never silently override stronger keys.

URL Identity:

- Semantic kinds: `article`, `live_page`, `homepage`, `aggregator`, `unknown`.
- Invariants: only `article` can be a hard URL dedup key by itself; `live_page/homepage/aggregator` require content/title/time evidence and cannot force exact story merge.

Story:

- Semantic key: deterministic story key over canonical items and event evidence.
- Invariants: story grouping is a read model over canonical items; same-document duplicates do not create extra story members; rebuild is order-independent.

Public News Row:

- Semantic key: product representative identity, normally canonical item id or story representative id + stable product window.
- Invariants: default list shows enabled-source representative rows only; duplicate evidence is summarized, not dropped; unchanged projection writes zero rows.

OpenNews Source Checkpoint:

- Semantic fields: source id, high watermark `ts`, overlap policy, last successful catch-up metadata, sync lag diagnostics, optional ids seen at the watermark boundary.
- Invariants: checkpoint advances only after durable write; REST page number is scan state, not durable identity.

## Interface Contracts

`/api/news`:

- Default semantics: returns representative rows only, filtered to enabled serving sources. Each row represents a canonical item or story representative, not a raw provider observation.
- Output semantics: rows include duplicate/source counts and enough source summary to explain why multiple observations collapsed.
- Idempotency: repeated projection of unchanged canonical items produces the same row ids and payload hashes.
- Diagnostics mode: any explicit include-disabled or include-duplicates behavior must be opt-in and labelled diagnostic, not default product behavior.

`/api/news/items/{id}`:

- Accepts canonical item id as the product item identity.
- Returns canonical payload, current source evidence, duplicate edges, provider observations, entity/token/fact evidence and brief state.
- Legacy provider-item-scoped `news_item_id` lookup is not kept. This endpoint accepts the canonical item id only, and the response makes canonical identity and observation evidence explicit.

`/api/news/stories/{id}`:

- Returns story over canonical items. Same-document duplicate observations are nested under their canonical item, not listed as independent story members.
- Story members expose match reason/evidence and canonical item ids.

`/api/news/sources/status`:

- Adds sync/dedup diagnostics: enabled serving row count, disabled serving row count, raw observations, canonical items, duplicate edges, dedupe ratio, OpenNews watermark lag, REST pages scanned, overlap stop reason, partial/ready merge counts.
- Must not expose secrets or bearer tokens.

Worker/CLI diagnostics:

- A repair/backfill command may enqueue bounded canonicalization/story/page rebuild windows.
- Diagnostics must distinguish source-level duplicate fetches from cross-source/cross-id canonical duplicates, so `items_duplicate` alone is not treated as health.

## Acceptance Criteria

- AC1. WHEN the current runtime config is loaded THEN diagnostics SHALL report config paths under `/Users/qinghuan/.gmgn-twitter-intel/` and SHALL NOT print secret values.
- AC2. WHEN two OpenNews payloads have the same article `id` through WS `news.update`, WS `news.ai_update`, or REST catch-up THEN system SHALL merge them into one provider article/canonical item and SHALL NOT create a second `/api/news` row.
- AC3. WHEN a ready OpenNews payload has `aiRating.status="done"` and a later partial payload for the same `id` arrives THEN system SHALL preserve ready AI fields unless the later payload is also ready and newer by provider timestamp/version evidence.
- AC4. WHEN REST `/open/news_search` returns more than one page newer than the previous checkpoint THEN OpenNews catch-up SHALL scan bounded pages until overlap stop condition or page budget, and SHALL persist high watermark only after DB commit.
- AC5. WHEN the worker restarts after downtime within the configured overlap/page budget THEN articles newer than `high_watermark_ts_ms - overlap_ms` SHALL be observed and upserted idempotently.
- AC6. WHEN the same exact `content_hash` appears under multiple provider item ids for enabled sources THEN `/api/news` SHALL show one representative row with duplicate/source evidence, while raw observations remain queryable.
- AC7. WHEN an article-like canonical URL appears through multiple enabled sources with equivalent title/content THEN system SHALL create one canonical item, multiple observation/duplicate edges, and one default public row.
- AC8. WHEN a container URL such as `https://tass.ru/`, `https://www.afp.com`, a publisher homepage, or a live blog URL contains different titles/content THEN system SHALL NOT merge those facts solely because `canonical_url` is equal.
- AC9. WHEN source config disables or removes a source THEN page projection catch-up SHALL remove or stop serving its rows, and disabled-source rows in default `/api/news` SHALL be 0.
- AC10. WHEN story projection rebuilds the same canonical items in different processing orders THEN story ids, story membership, page row ids and visible list rows SHALL be identical.
- AC11. WHEN canonical item input hash is unchanged THEN page/story/brief projections SHALL record zero changed serving rows for that item.
- AC12. WHEN duplicate observations collapse into one canonical item THEN agent brief SHALL run at most once per canonical item per artifact/input hash.
- AC13. WHEN migration/backfill is run repeatedly on the same data window THEN canonical item count, duplicate edge count and public row count SHALL not grow after the first successful run.
- AC14. WHEN diagnostics query current DB after projection rebuild THEN previously observed disabled page row pollution baseline of 1999 SHALL drop to 0, and enabled exact content duplicate visible excess SHALL drop to 0.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Over-collapsing genuinely distinct live updates into one canonical item | High | Treat homepage/live/container URLs as weak evidence; require exact content/provider id or strong article URL for hard dedup. |
| Under-collapsing syndicated duplicates from different providers | Medium | Use strong content hash and article-like URL rules; expose duplicate diagnostics to tune policy without LLM guesses. |
| Losing audit trail during migration | High | Additive migration first; preserve raw observations and duplicate edges; never delete facts as the root fix. |
| Breaking Kappa/CQRS single-writer boundaries | High | Move story membership changes out of fetch/upsert path; projections own their read models. |
| OpenNews high-churn periods exceed page budget | Medium | Expose watermark lag, pages scanned and overlap stop reason; allow bounded operator backfill. |
| AI brief cost remains high during migration | Medium | Gate brief input on canonical representative and artifact/input hash; do not keep a legacy item brief path. |
| Official OpenNews `id` semantics changes or is absent for some rows | Medium | Use provider-global id when present; fall back to article URL/content hash with evidence; surface missing-id diagnostics. |
| Rebuild/backfill load impacts Postgres | Medium | Batch by source/time/canonical key; avoid idle full-table scans; keep repair commands bounded and reentrant. |

## Evolution Path

After this spec lands and the deterministic canonicalization path is stable, the next expansion can add richer source-quality weighting, source precedence tuning, and optional weak-duplicate review queues. The design must not foreclose future embeddings or LLM-assisted near-duplicate review, but those tools must remain advisory evidence layered on top of deterministic facts, not the primary identity contract.

The same canonical item/duplicate edge model can later support provider comparisons, source reliability dashboards, story-level narrative summaries and cross-domain event anchors. That expansion should remain pull-based from News facts; News should not directly write Token Radar, Pulse or market serving rows.

## Alternatives Considered

- Frontend-only dedup hiding. Rejected because it leaves duplicate facts, duplicate agent cost, wrong story grouping and disabled-source read model pollution intact; it also makes API consumers inconsistent.
- API-only `DISTINCT` or source-enabled filter. Rejected as a root fix because projection would still be polluted and facts would remain un-auditable. API filtering is acceptable only as defense in depth.
- Unique index on `canonical_url`. Rejected because current data shows homepage/live/container URLs like `https://tass.ru/` and `https://www.afp.com` map to many distinct titles/content and would cause severe over-dedup.
- Unique index on `content_hash` only. Rejected because exact content duplicates should collapse, but article identity also needs provider-global id and article URL evidence; a raw unique hash would erase observation/source evidence unless paired with duplicate edges.
- Reusing story groups as the dedup layer. Rejected because story is a read model and currently mixes article dedup with event grouping; it is order-sensitive and not a durable fact identity.
- Full News module rewrite. Rejected for now because the fetch/process/story/page worker skeleton is usable. The necessary rewrite is bounded to identity, duplicate evidence, OpenNews checkpointing and representative projections.
- Embedding/vector/LLM dedup first. Rejected because the current failures are deterministic identity bugs and serving contract bugs. Fuzzy methods can be added later as evidence, not as the first-principles identity layer.
- Deleting all old page rows and relying on fresh ingest. Rejected because it may reduce symptoms temporarily without fixing item identity, story over-merge or OpenNews catch-up semantics.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve raw provider observations and source evidence; default public rows are enabled-source representatives; OpenNews `id` is provider article identity when present; article-like URL/content hash are deterministic dedup evidence; projections remain single-writer and rebuildable. |
| Ask first | Expanding News tape to `market/meme/prediction`; deleting historical facts; changing public API compatibility for legacy `news_item_id`; adding LLM/embedding duplicate decisions; cross-domain propagation into Token Radar/Pulse. |
| Never | Use fetch run/timestamp/UUID as serving identity; perform frontend-only dedup as root fix; let disabled sources serve by default; let homepage/live/container URL alone hard-merge different content; let fetch worker directly mutate story read models. |
