# Spec — News Intel 硬切根修

**Status**: Draft
**Date**: 2026-06-05
**Owner**: qinghuan / Codex
**Related**: `docs/superpowers/specs/active/2026-06-01-news-intel-kiss-simplification-cn.md`, `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`, `docs/superpowers/specs/active/2026-05-30-news-item-brief-llm-cost-root-fix-cn.md`

## Background

News Intel 的事实边界已经定义清楚：`news_provider_items` 和 `news_items` 是 provider 输入与规范化新闻事实，`news_item_entities`、`news_token_mentions`、`news_fact_candidates` 是确定性观察/候选事实，`news_page_rows` 是可重建的 News 页读模型，`news_item_agent_runs` / `news_item_agent_briefs` 是单条新闻 agent brief 的审计/当前产物。见 `src/parallax/domains/news_intel/ARCHITECTURE.md:13`、`src/parallax/domains/news_intel/ARCHITECTURE.md:43`、`src/parallax/domains/news_intel/ARCHITECTURE.md:51`。

公开读取契约也已写死：`/api/news` 只能读 `news_page_rows`，不能 fallback 到 raw `news_items`；`/api/news/items/{news_item_id}` 返回确定性抽取事实、当前 item brief 和脱敏 latest run summary。见 `docs/CONTRACTS.md:169`、`docs/CONTRACTS.md:213`。

本地当前 NewsItemBrief 合约是轻量无工具版本：常量为 `news-item-brief-v3` / `news_item_brief_v1` / `news_item_brief_validator_v3`，见 `src/parallax/domains/news_intel/_constants.py:5`；prompt 明确要求“你不调用工具，不请求外部数据，不使用 packet 外知识”，见 `src/parallax/domains/news_intel/prompts/news_item_brief.md:5`；输入 packet 只由 item、token lanes、fact lanes、provider signal evidence 和 evidence refs 构成，见 `src/parallax/domains/news_intel/services/news_item_brief_input.py:28`。

但 live runtime 仍在写旧研究工具版 artifact。2026-06-05 的只读 DB 审计显示，`news_item_agent_briefs` 仍有 `news-item-brief-synthesizer-v1` / `news_item_brief_v2` / `news_item_brief_validator_v4`：`ready=309`、`insufficient=28`、`failed=2`，最新更新时间为 `2026-06-05 01:10:50 UTC`；而本地当前 v3 brief 最新更新时间停在 `2026-06-03 22:07:28 UTC`。这说明运行容器和当前本地源码已经分叉，不是单条页面缓存问题。

即使本地 worker 会把版本不一致的 current brief 判为 stale，读取和投影链路仍会泄露旧 current brief。`NewsItemBriefWorker` 的 freshness gate 检查 `input_hash`、`artifact_version_hash`、`prompt_version`、`schema_version`、`validator_version`，见 `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:690`；但 page/detail loader 直接 join `news_item_agent_briefs`，没有版本过滤，见 `src/parallax/domains/news_intel/repositories/news_repository.py:2545`、`src/parallax/domains/news_intel/repositories/news_repository.py:2635`、`src/parallax/domains/news_intel/repositories/news_repository.py:2728`；page projection 会压缩并公开传入的 current brief，见 `src/parallax/domains/news_intel/services/news_page_projection.py:175`。

当前准入逻辑也过宽。`news_item_process` 优先把 provider `coins[]` / `provider_token_impacts_json` 转成实体，见 `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:61`；brief admission 主要依赖 provider signal score >= 80 和“有 market context”，见 `src/parallax/domains/news_intel/services/news_item_agent_policy.py:31`；`market context` 对 `unknown_attention`、`ambiguous_symbol` 和非 rejected fact candidate 过于宽容，见 `src/parallax/domains/news_intel/services/news_item_agent_policy.py:72`。News page 的 in-app high-signal eligibility 对 provider score >= 70 直接放行，见 `src/parallax/domains/news_intel/services/news_page_projection.py:322`。

去重还是 item 级，不是 story 级。canonical identity 优先 hard public URL、provider article id、qualified content hash，最后退到 same-source title hour window，见 `src/parallax/domains/news_intel/services/news_canonical_identity.py:74`；page dirty target 仍是 `news_item` 粒度，见 `src/parallax/domains/news_intel/runtime/news_projection_work.py:12` 和 `src/parallax/domains/news_intel/runtime/news_projection_work.py:168`。这会让 SpaceX、JPM/Citi tokenized deposit、Trump/Iran 等同一故事碎片以多条 page rows 和多条通知候选出现。

最近窗口审计确认问题不是 SpaceX 个案。2026-06-05 `01:52:43 UTC` 的 6 小时只读审计中，排除 SpaceX 后共有 536 条新闻，其中 453 条是 `low_signal`；provider score >=80 的 36 条里，23 条是 `low_signal`、9 条是 `energy_geopolitics`，只有 3 条 `crypto_market` 和 1 条 Zcash security。常见误报包括地缘/油价、三星/DRAM/玉米大豆/黄金/港股、以及 `TRUMP`、`BILL`、`W`、`FIL`、`COIN`、`CRCL` 等 ticker/普通词/股票碰撞。Provider 70-79 区间也有 Coinbase/BTC mortgage、HYPE whale、Sui、BNB/Anoma 等 crypto-relevant 行没有 brief，说明单一 score 阈值同时带来误报和漏报。

## Problem

News Intel 现在把旧 agent artifact、provider 高分、ticker 碰撞和 item 级重复碎片混在同一个公开读路径里，导致页面/detail 会展示旧 schema 分析、`get_target_news_context` 等旧工具的错误诊断会被当作结论，股票/宏观/商品新闻会被误提升为 crypto 信号，真实 crypto 低分新闻又可能没有进入分析，最终无法在语义级别表达“同一故事、不同资产命名空间、不同分析准入状态”。

## First principles

- Facts are truth, derived rows are disposable. `news_items`、observation edges、entities、token mentions、fact candidates 是事实；`news_page_rows` 和 current agent brief 是可硬切/可重建产物。见 `src/parallax/domains/news_intel/ARCHITECTURE.md:15`、`src/parallax/domains/news_intel/ARCHITECTURE.md:20`。
- No runtime compatibility for retired contracts. 当前 public routes 必须读当前 projection/current contract，不迁就旧 prompt/schema 字段；`/api/news` 不允许 raw fallback，见 `docs/CONTRACTS.md:171`。
- One writer, stable current identity, zero unchanged writes. 当前 read model 必须有单一 writer、稳定 product identity，不能靠 run/timestamp/UUID/generation 保持正确；未变化 projection 写 0 行。见 `docs/RELIABILITY.md:199`、`docs/RELIABILITY.md:210`。
- Provider signal is evidence, not final crypto truth. Prompt 已要求 provider scores/token impacts 是输入而不是最终真相，见 `src/parallax/domains/news_intel/prompts/news_item_brief.md:44`。
- Ticker is not identity. 一个 symbol/cashtag 只有在 namespace、venue/chain、instrument type、issuer/entity 和时间上下文足够时才是可分析资产；否则必须保持 attention/page-only。

## Goals

- G1. 旧数据硬切：执行 cleanup 后，`news_item_agent_briefs`、公开 `news_page_rows.agent_brief_json`、`/api/news/items` 当前 brief 中不得存在 `news-item-brief-synthesizer-v1`、`news_item_brief_v2`、`retrieval_notes_zh`、`source_consensus_zh`、`confirmation_state`、`used_tool_call_ids` 等退休字段；旧 News agent run/request/response payload 不保留在 live DB 中。
- G2. Runtime 不再写旧版本：部署后的 30 分钟只读审计中，新增 News item brief 只能写 `news-item-brief-v3` / `news_item_brief_v1` / `news_item_brief_validator_v3` 或后续明确批准版本。
- G3. 广义新闻可见、crypto 分析准入分离：股票、商品、宏观、地缘新闻可以在 News 页面作为 `page_only` / `research_context` 可见，但不能生成 crypto agent brief、不能作为 high-signal notification candidate，除非有明确 crypto-native subject 或 production crypto asset evidence。
- G4. 最近 4-6 小时误报压降：审计样本中 provider score >=80 的非 crypto-native 新闻不得因为 provider score 或 ambiguous/common-word token 被标成 admitted crypto analysis；SpaceX、Samsung、DRAM、corn/soy/oil、Trump/Iran/Hormuz/Cuba sanctions 进入 page-only/context，而不是 crypto driver/watch。
- G5. 漏报控制：provider score 70-79 但有 crypto-native subject 的新闻，例如 Zcash follow-up、Coinbase/BTC-backed mortgage、HYPE whale、Sui/BNB/Anoma/Kaia/QTUM 等，不得只因 score <80 被系统性排除在 brief admission 外。
- G6. Story 级投影：JPM/Citi tokenized deposit、SpaceX valuation/IPO/AI revenue、Trump/Iran、Ukraine sanctions 等多 URL/多标题碎片应合并为一个 stable story page row 或明确显示 story member count，通知候选以 story key 去重。
- G7. 检索/上下文链路语义正确：如果未来需要 context retrieval，它必须由 host deterministic packet 构造，返回 `matched_count`、`returned_count`、`emitted_count`，不能让压缩后 0 行伪装成 DB 无命中；不能用 `for` 等 stopword 或 `source_title` 当 story similarity。

## Non-goals

- N1. 不删除 material news facts：本次硬切不删除 `news_provider_items`、`news_items`、observation edges、entities、token mentions、fact candidates、source rows。删除范围限于退休 agent artifact、退休 read-model artifact、退休 dirty targets 或其公开投影。
- N2. 不恢复旧 `get_target_news_context` / `search_news_archive` / `get_observation_history` runtime tools。旧工具链的设计被判定为错误方向。
- N3. 不在本 spec 里指定 SQL DDL、具体函数签名或逐文件修改；这些属于批准后的 plan。
- N4. 不把 News Intel 变成股票新闻或宏观交易建议系统；股票/宏观可作为 context，但 crypto analysis 要有明确准入。
- N5. 不要求首版引入向量数据库。语义级别可以先用 deterministic story keys、full-text/trigram candidate retrieval、resolved subject constraints 和 source/time evidence 实现；embedding/hybrid retrieval 是后续增强。

## Target Architecture

News Intel 保持 Kappa/CQRS：ingest 和 processing 写事实，page projection 写唯一公开读模型，brief worker 只对准入后的 item/story 做可选分析。变化是把“新闻可见性”和“crypto 分析资格”拆成两个独立状态。

第一层是 item facts：每条 `news_item` 仍保留 canonical item identity、source classification、content classification、deterministic entities/token mentions/fact candidates。Provider token impacts 只作为 provider-native evidence，不再自动证明 crypto subject。

第二层是 analysis admission：item processing 产出一个可审计的 admission verdict，表达该 item 是 `admitted`、`page_only`、`research_context`、`suppressed` 还是 `needs_review`。Admission verdict 必须记录 reason/basis：content class、source role/trust/coverage、provider market type、resolved production crypto asset、accepted crypto fact、ambiguous/common-word collision、non-crypto instrument evidence 等。

第三层是 story identity：多个 item 可以归入同一 stable story key。Story 是 rebuildable projection over facts，不是新的 material truth。Story identity 由 canonical URL/material title fingerprint、provider article keys、resolved subjects、entities/concepts、time window、source set、content class 和 optional lexical/trigram similarity 共同产生。Story row 选择 representative item，同时保留 member ids/count/source domains/provider article keys。

第四层是 optional brief：NewsItemBrief 只接收当前 no-tool packet。Packet 可以包含 host-built bounded context，但 context 必须由 deterministic query/service 预先构造，不能让 LLM 自主调用 runtime tools。旧 research packet/tool result 字段彻底移除。

第五层是 notifications：News high-signal candidates 只从 story-level page rows 中读取 admitted crypto analysis；in-app 和 external push 都以 story key + decision/admission signature 去重。External push 继续要求 ready agent brief 和 publishable summary。

## Conceptual Data Flow

```text
news_fetch
  -> news_item_process
       -> deterministic facts
       -> analysis admission verdict
       -> story identity
       -> dirty story/page targets
       -> optional brief targets only for admitted crypto analysis
  -> news_item_brief
       -> current no-tool brief only
  -> news_page_projection
       -> story-shaped news_page_rows
  -> /api/news, /api/news/items, notification_rule
```

Changed arrows:

- `news_item_process -> news_item_brief` changes from provider-score + loose market-context admission to explicit crypto analysis admission.
- `news_item_process -> news_page_projection` changes from item-only dirty targets to story-aware dirty targets while keeping durable queue semantics.
- `news_page_projection -> notification_rule` changes from provider-score in-app eligibility to story-level admitted eligibility.
- Runtime agent tools are removed from the data flow. Deterministic context, if used, is packet construction, not model-selected retrieval.

## Core Models

`NewsAnalysisAdmission`

- Fields: status, reason, basis, score basis, crypto subject evidence, non-crypto instrument evidence, ambiguous/common-word evidence, source/content gates, computed version.
- Invariant: only `admitted` can enqueue item/story brief work or high-signal notification work.

`NewsStoryIdentity`

- Fields: story key, representative item id, member item ids, title/material fingerprints, provider article keys, source domains, subject refs, concept/entity refs, time bounds, confidence.
- Invariant: story key is stable product identity, not run/generation/timestamp identity.

`NewsSubjectRef`

- Fields: subject type, namespace, id, display label, evidence basis, resolution confidence.
- Invariant: stock/equity/private-company/legal-entity refs and crypto asset refs are different namespaces even when labels collide.

`NewsContextPacket`

- Fields: observation edge summary, resolved-subject history rows, story members, source quality compact state, bounded snippets, matched/returned/emitted counts.
- Invariant: counts report actual query matches separately from presentation truncation; rows are deterministic and auditable by ids.

`LegacyNewsArtifactPurge`

- Fields: cutoff contract versions, purge counts, affected row classes, started/finished timestamps, dry-run/execute mode.
- Invariant: purged old artifact payloads are not migrated or retained as compatibility data; material facts are not purged.

## Interface Contracts

`/api/news`

- Continues to be read-only and backed only by `news_page_rows`.
- Rows become story-shaped: a row may represent one or more member items. It exposes representative headline/summary, member count, source domains, content/admission state, compact provider signal, compact current agent signal if current, and story identity metadata.
- It must not expose old agent fields or old prompt/schema versions.
- Broad non-crypto news may appear with `analysis_admission_status != admitted`, but must not appear as crypto high-signal driver/watch solely from provider score.

`/api/news/items/{news_item_id}`

- Returns deterministic facts for the requested item, plus story membership and current-contract brief if present.
- If only old brief artifacts exist, the route returns pending/stale/absent brief state rather than old `brief_json`.
- Latest run summary remains sanitized and must not expose raw provider request/response or retired research tool payloads.

`notification_rule`

- News high-signal candidate discovery reads admitted story-level rows only.
- Dedup key includes stable story key and admission/decision signature.
- External push continues requiring ready agent brief and publishable summary.

Ops / CLI

- A dry-run cleanup report must list old artifact counts by prompt/schema/validator/status and affected page rows before execute.
- Execute mode purges retired News agent artifacts/read-model artifacts and enqueues/rebuilds current rows.
- Cleanup must refuse to execute if the active runtime can still write the retired prompt/schema.

## Acceptance Criteria

- AC1. WHEN cleanup runs in dry-run mode THEN system SHALL report counts for old briefs, old runs, old page rows, old dirty targets, and affected news item/story ids without writing DB.
- AC2. WHEN cleanup runs in execute mode after current runtime is deployed THEN system SHALL delete retired News agent artifact payloads and retired page/read-model rows while preserving material news facts.
- AC3. WHEN `/api/news/items/news-item-984430947977437cd1872cd8e5423a50` is read after cleanup THEN system SHALL not expose `news_item_brief_v2`, `retrieval_notes_zh`, `source_consensus_zh`, `confirmation_state`, `novelty_status`, or `used_tool_call_ids`.
- AC4. WHEN a current brief is joined for page/detail/projection THEN system SHALL require current prompt/schema/validator/artifact contract; non-current rows are treated as absent.
- AC5. WHEN SpaceX private-company/valuation/IPO fragments arrive THEN system SHALL group them as a story/context row and SHALL NOT admit them as crypto driver/watch unless an explicit crypto instrument/source exists.
- AC6. WHEN JPM/Citi tokenized-deposit variants arrive within the same story window THEN system SHALL project one story row or one explicit grouped story with member count and SHALL produce at most one notification candidate.
- AC7. WHEN Samsung shares, DRAM, corn/soy/oil, Hormuz, Ukraine/Russia sanctions, Cuba sanctions, or Trump/Iran headlines have only macro/stock/commodity evidence THEN system SHALL classify them as page-only/context, not crypto admitted.
- AC8. WHEN Zcash security, Coinbase/BTC mortgage, HYPE whale, Sui/BNB/Anoma/Kaia/QTUM crypto-native rows score 65-79 THEN system SHALL be eligible for analysis based on crypto-native evidence rather than excluded only by provider score.
- AC9. WHEN a future context query matches DB rows but emitted rows are truncated THEN system SHALL report non-zero `matched_count` and `returned_count`; it SHALL NOT report `row_count=0` as if the database had no context.
- AC10. WHEN projection recomputes an unchanged story/page row THEN system SHALL write zero serving rows or update only when payload materially differs.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cleanup deletes useful material facts | High | Scope purge to retired agent/read-model artifacts only; dry-run report and explicit row-class counts before execute. |
| Old container keeps regenerating old v2 briefs | High | Cleanup execute refuses unless runtime constants match current no-tool contract and no old writer files are importable in the running process. |
| Story grouping over-merges unrelated macro items | Medium | Require deterministic anchors: time window, material title/subject refs, source set, concept/entity overlap, and confidence; expose member evidence. |
| Strict admission misses broad macro crypto drivers | Medium | Allow `research_context` and macro-specific admitted path only when crypto transmission evidence is explicit and auditable. |
| Removing old run ledger weakens auditability | Medium | Keep purge summary counts and migration/ops event; do not retain retired prompt/tool payloads in live DB per hard-cut requirement. |
| Hybrid/semantic retrieval becomes another black box | Medium | Treat retrieval as candidate generation only; final admission/story grouping must cite deterministic refs and counts. |

## Evolution Path

The next expansion can add embeddings or external search only as a candidate retrieval layer, fused with lexical/full-text/trigram results and deterministic subject refs. PostgreSQL full-text search ranking supports lexical/proximity/structure-aware ranking; `pg_trgm` supports trigram similarity and indexes for fuzzy matching; Elasticsearch/OpenSearch document hybrid retrieval patterns use rank/score fusion to combine keyword and semantic signals. Event Registry-style concepts/stories/events show the right product shape: articles can be clustered into stories/events with entity/concept/category metadata, but those clusters remain separate from article facts. OpenFIGI-style symbology reinforces that ticker strings need namespace and instrument identity before they become financial subjects.

References:

- PostgreSQL full-text ranking: https://www.postgresql.org/docs/17/textsearch-controls.html
- PostgreSQL text-search functions and `ts_rank_cd`: https://www.postgresql.org/docs/18/functions-textsearch.html
- PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/current/pgtrgm.html
- Elasticsearch reciprocal rank fusion: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion
- OpenSearch hybrid search: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
- Event Registry terminology for concepts, stories, and events: https://github-wiki-see.page/m/EventRegistry/event-registry-python/wiki/Terminology
- Event Registry duplicate/event filters: https://help.eventregistry.org/search-filter-for-articles-miscellaneous/
- OpenFIGI identifier mapping: https://www.openfigi.com/api/documentation
- GDELT DOC API time-window/news search reference: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

## Alternatives Considered

- Keep old research tools and only fix prompt wording — rejected because the old tools have incorrect contracts: exact target context excludes unresolved/ambiguous subjects, archive search can match stopwords such as `for`, observation history is only current-item edge history, and compaction can turn real SQL matches into `row_count=0`.
- Keep provider-score-first admission — rejected because recent live data shows provider score >=80 is not crypto-specific enough and score 70-79 can contain important crypto-native items.
- Delete all recent News facts and start over — rejected because provider/news item facts are the only business truth and are needed to rebuild current projections.
- Add vector search first — rejected for the first root fix because it does not solve namespace collisions, old artifact leakage, or page/notification admission; it can be layered later as candidate retrieval.
- Restore old story projection wholesale — rejected because the target needs stable story identity plus current-row hygiene and no retired compatibility fields, not resurrection of an old design.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Purge retired News agent/read-model artifacts instead of migrating them; deploy only current no-tool brief contract; treat provider score as evidence; separate page visibility from crypto analysis admission; group semantic story fragments before notification dedup. |
| Ask first | Deleting material news facts, changing provider credentials/source configuration, adding external paid APIs/vector services, or widening this into equity/macro product scope. |
| Never | Serve old brief fields, retain old research tool payloads as public/current data, let LLM choose DB tools at runtime for News brief, treat a bare ticker/common word as crypto identity, or let provider score alone make a crypto driver/watch row. |
