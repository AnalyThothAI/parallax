# Spec — Search V2 Hard Cut

**Status**: Implemented in worktree `codex/search-v2-hard-cut`
**Date**: 2026-05-11
**Last Updated**: 2026-05-12
**Owner**: Codex
**Related**: `docs/superpowers/plans/active/2026-05-11-search-v2-hard-cut-plan-cn.md`

## Latest Main Reconciliation

本 spec 已按 2026-05-12 的本地 `main` 重新校准。当前 worktree 基点是 `1e0fa9013a1675fbac68b863f433451cc7a9f603`（`merge: social heat propagation hard cut`）；当时 `origin/main` 落后于本地 `main`，所以实现从本地最新 `main` 切出 `codex/search-v2-hard-cut`。

和原计划相比，核心搜索问题仍然存在：`/api/search` 仍是旧 `symbol/ca/chain/handle` 参数和 `AssetSearchService`，text route 仍依赖 `EvidenceRepository.search_fts/count_fts`，前端仍无 cursor 分页且 drawer 只展示前 8 条。因此 hard cut 方向没有过时。

需要调整的地方只有落地细节：最新 `main` 已经新增 Alembic revision `20260511_0030`，合并时又已包含 `20260512_0031_prune_legacy_pulse_factor_contracts.py`，所以本次搜索迁移最终改为 `20260512_0032_search_v2_hard_cut.py`，`down_revision = "20260512_0031"`；另外 registry chain id 已标准化为 `eip155:1/eip155:8453/eip155:56/solana/ton`，CA search 必须做 chain alias 映射，不能继续假设 `eth/base/bsc` 是库内原始 chain id。

## Background

当前 `/api/search` 入口在 `src/parallax/app/surfaces/api/http.py:118`，接收 `q`、`limit`、`symbol`、`ca`、`chain`、`handle`、`scope`，通过 `_search_query(...)` 把旧的 `symbol/ca/handle` query params 拼回字符串，再调用 `AssetSearchService(...).search(...)`。这个接口没有 `cursor` 或 `offset`，只返回一次有限结果。`limit` 经 `_limit(...)` 约束后进入 service，默认 HTTP 是 20，前端实际在 `web/src/features/live/useLiveData.ts:108` 到 `web/src/features/live/useLiveData.ts:114` 以 `limit=36` 调用。

当前前端提交搜索时，并不总是调用 `/api/search`。`web/src/features/live/useLiveSelection.ts:186` 到 `web/src/features/live/useLiveSelection.ts:214` 先用 `tokenForSearchQuery(...)` 尝试在已加载 Token Radar rows 里唯一匹配；命中时直接选中 token，不发 search API。只有非唯一 token、文本 query、或非 radar 中已有 target 时才提交 `/api/search`。查询结果展示在 `web/src/components/EvidenceDetailDrawer.tsx:155` 到 `web/src/components/EvidenceDetailDrawer.tsx:229`，其中只渲染 `items.slice(0, 8)`，即使 API 返回 36 条也只显示 8 条；`has_more` 只是显示为 yes/no，没有加载更多动作。

当前 `AssetSearchService` 的分流在 `src/parallax/domains/token_intel/read_models/asset_search_service.py:28` 到 `src/parallax/domains/token_intel/read_models/asset_search_service.py:71`。它依赖 `parse_query(...)`，该 parser 在 `src/parallax/domains/token_intel/services/query_parser.py:18` 到 `src/parallax/domains/token_intel/services/query_parser.py:38` 中把 `@...` 解析为 handle，把 `$...` 解析为 symbol，把 `chain:address` 或裸 CA 解析为 CA，其余全部是 `text`。因此 `btc` 与 `$btc` 进入完全不同的搜索路径。

当前 text 搜索在 `src/parallax/domains/evidence/repositories/evidence_repository.py:136` 到 `src/parallax/domains/evidence/repositories/evidence_repository.py:170`，用 `events.search_tsv @@ websearch_to_tsquery('simple', query)`，按 `ts_rank_cd` 和 `received_at_ms` 排序。进入 Postgres 前，`_fts_query(...)` 在 `src/parallax/domains/evidence/repositories/evidence_repository.py:266` 到 `src/parallax/domains/evidence/repositories/evidence_repository.py:269` 会用正则提取最多 16 个 `\w+` token，导致 websearch 原生短语、OR、NOT 等语义在进入数据库前被削弱。

`events.search_tsv` 当前来自初始 Alembic 迁移 `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:66` 到 `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:70`：`author_handle` 是 A 权重，`search_text` 是 B 权重，`text_clean` 是 C 权重。`search_text` 由 `src/parallax/domains/evidence/types/tweet_text.py:26` 到 `src/parallax/domains/evidence/types/tweet_text.py:35` 生成，等于主 tweet clean text 加 reference clean text；`text_clean` 又是主 tweet clean text，因此主文被重复计分，作者 handle 命中也会比正文命中更强。

当前 `$symbol` 和 CA 搜索并不是从生产 target identity 反查。`AssetSearchService._events_for_symbol(...)` 在 `src/parallax/domains/token_intel/read_models/asset_search_service.py:136` 到 `src/parallax/domains/token_intel/read_models/asset_search_service.py:143` 查询 `token_evidence.normalized_symbol = %s`；`AssetSearchEventsQuery` 在 `src/parallax/domains/token_intel/queries/asset_search_events_query.py:25` 到 `src/parallax/domains/token_intel/queries/asset_search_events_query.py:63` 只是基于 `token_evidence` 找事件，并左连接当前 `token_intent_resolutions` 作为元数据。它不会先解析 query 到 `CexToken` 或 `Asset`，也不会查所有 `token_intent_resolutions.target_type/target_id` 指向该 target 的事件。

当前 symbol 候选也落在旧身份模型上。`AssetSearchService._search_symbol(...)` 使用 `self.assets.candidates_for_symbol(...)`，而 repository session 中 `repos.assets` 是 `AssetRepository`，见 `src/parallax/app/runtime/repository_session.py:69` 到 `src/parallax/app/runtime/repository_session.py:79`。`AssetRepository.candidates_for_symbol(...)` 在 `src/parallax/domains/asset_market/repositories/asset_repository.py:203` 到 `src/parallax/domains/asset_market/repositories/asset_repository.py:261` 查询 `assets / asset_aliases / asset_venues`。但当前生产 token identity 已迁到 `cex_tokens / registry_assets / asset_identity_current / token_intent_resolutions`：CEX token 表在 `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py:49` 到 `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py:58` 创建，`asset_identity_current` 在 `src/parallax/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py:40` 到 `src/parallax/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py:51` 创建。

生产解析链路已经具备 target identity。`Token Intel` 架构文档描述生产链路为 GMGN frame 到 `token_evidence`、`token_intents`、`token_intent_lookup_keys`、`token_intent_resolutions`、`registry_assets`、`asset_identity_evidence/current`，见 `src/parallax/domains/token_intel/ARCHITECTURE.md:10` 到 `src/parallax/domains/token_intel/ARCHITECTURE.md:24`。`DeterministicTokenResolver._resolve_symbol(...)` 在 `src/parallax/domains/token_intel/services/deterministic_token_resolver.py:218` 到 `src/parallax/domains/token_intel/services/deterministic_token_resolver.py:298` 已经实现 symbol 解析：先查 `cex_tokens`，再查 `asset_identity_current` 关联的 DEX asset，并输出 `target_type/target_id`。`token_intent_resolutions` 上也已有 target current index，见 `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py:227` 到 `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py:233`。

当前已有 target timeline 查询能力。`TokenTargetRepository.timeline_rows(...)` 在 `src/parallax/domains/token_intel/repositories/token_target_repository.py:12` 到 `src/parallax/domains/token_intel/repositories/token_target_repository.py:158` 通过 `token_intent_resolutions.target_type/target_id` 反查事件，并使用 `(received_at_ms, event_id)` cursor。`TokenTargetPostsService.target_posts(...)` 在 `src/parallax/domains/token_intel/read_models/token_target_posts_service.py:28` 到 `src/parallax/domains/token_intel/read_models/token_target_posts_service.py:88` 已经按 `limit + 1` 判断 `has_more` 和 `next_cursor`。搜索没有复用这套 target-first / cursor 思路。

当前 entity extraction 只把 CA 和 cashtag 变成 token evidence。`entity_extractor.py` 在 `src/parallax/domains/evidence/services/entity_extractor.py:115` 到 `src/parallax/domains/evidence/services/entity_extractor.py:138` 抽取 cashtag symbol，在 `src/parallax/domains/token_intel/services/token_evidence_builder.py:32` 到 `src/parallax/domains/token_intel/services/token_evidence_builder.py:47` 只把 CA、symbol entity、GMGN token payload 转成 token evidence。裸 `BTC chart` 或 `Bitcoin breakout` 如果没有 GMGN token payload，不会自动进入 `token_intent_resolutions`，只能靠 lexical search 召回。

Signal Lab 的 `q` 搜索是另一条链路。`/api/signal-lab/pulse` 在 `src/parallax/app/surfaces/api/http.py:461` 到 `src/parallax/app/surfaces/api/http.py:488` 调 `SignalPulseService`；`PulseRepository.list_candidates(...)` 在 `src/parallax/domains/pulse_lab/repositories/pulse_repository.py:535` 到 `src/parallax/domains/pulse_lab/repositories/pulse_repository.py:540` 只对 `candidate.symbol / subject_key / target_id` 做 `ILIKE`，不参与 `/api/search` 的 event retrieval。

## Problem

用户搜索 `btc`、`$btc`、`bitcoin`、`比特币`、短语或轻微拼写错误时，系统无法稳定返回“所有可解释为同一 target 或同一语义主题的证据事件”，也无法持续翻页。根因不是缺少 embedding，而是当前搜索仍混用旧 asset 候选模型、raw token evidence、弱 FTS、无 cursor API 和前端 8 条展示上限，导致生产解析结果被闲置、相关文本召回不足、排序被作者 handle 污染、用户看不到更多结果。

## First Principles

1. **Symbol 是 recall key，不是 identity。** 当前 Token Intel hard boundary 明确“a symbol is a recall key, not identity”，见 `src/parallax/domains/token_intel/ARCHITECTURE.md:106` 到 `src/parallax/domains/token_intel/ARCHITECTURE.md:107`。搜索必须先把 symbol query 映射到 `CexToken` 或 `Asset` candidate，再以 current resolution 反查事件；不能把 `token_evidence.normalized_symbol` 当成最终 identity。

2. **API / CLI / 前端只读 read model，不做解析、provider call、打分决策。** Token Intel hard boundary 要求 surfaces 只读 projected rows 或 read models，不执行 entity extraction、token resolution、provider calls、SQL joins 或 scoring，见 `src/parallax/domains/token_intel/ARCHITECTURE.md:101` 到 `src/parallax/domains/token_intel/ARCHITECTURE.md:103`。搜索 v2 必须把 SQL 放入 query modules，把 orchestration 放入 read model service，把 public translation 留在 API/CLI。

3. **Hard cut 不保留旧搜索兼容层。** 本 spec 不维护旧 `AssetSearchService` 行为、不继续接受 `symbol/ca/chain/handle` 这些 `/api/search` 参数、不保留 `assets / asset_aliases / asset_venues` 候选读取、不保留 `search_fts/count_fts` 作为 fallback 入口。调用方统一迁到新的 `q + cursor` 搜索契约。

4. **Embedding 不能掩盖 deterministic retrieval 缺口。** 当前 main 已经有 `token_intent_resolutions`、`cex_tokens`、`asset_identity_current`、target cursor 查询和 generated FTS，但 `/api/search` 没正确使用。先修 deterministic entity + lexical retrieval；semantic embedding 作为后续演进，不能进入本 hard cut 的主路径。

## Goals

- G1. WHEN 用户搜索 `btc` 或 `$btc` 且 `cex_tokens.base_symbol='BTC'` 存在，THEN `/api/search` SHALL 把 query 解析为 `CexToken:cex_token:BTC` target candidate，并召回所有 current `token_intent_resolutions` 指向该 target 的事件页。
- G2. WHEN 用户搜索一个 chain/address CA，THEN `/api/search` SHALL 基于 `registry_assets(chain_id, address)` 和 current target resolutions 召回事件，不再基于 raw `token_evidence.address_hint` 作为主路径。
- G3. WHEN query 不是可解析 target 或 target recall 不足，THEN lexical route SHALL 保留 websearch phrase / OR / NOT 语义，并支持 high-confidence alias expansion、english stemming 和 trigram typo/partial fallback。
- G4. WHEN 搜索结果超过一页，THEN HTTP、CLI、前端 SHALL 使用 stable cursor 加载下一页；没有 `limit=20/36` 或 UI `slice(0, 8)` 造成的终止上限。
- G5. WHEN 搜索排序完成，THEN author handle 命中 SHALL 不能压过正文 target / text 命中；`@handle` 查询仍走显式 handle route。
- G6. WHEN hard cut 完成，THEN search runtime SHALL 不再导入或调用 `AssetRepository.candidates_for_symbol(...)`、`AssetRepository.candidates_for_ca(...)`、`EvidenceRepository.search_fts(...)`、`EvidenceRepository.count_fts(...)`。
- G7. WHEN public contracts 生成，THEN OpenAPI、CLI help、frontend `SearchData` 类型 SHALL 只描述新 search v2 契约。
- G8. WHEN `make check-all` 在 implementation worktree 运行，THEN all backend, contract, frontend, integration, and e2e gates SHALL pass with new search tests included.

## Non-goals

- N1. 本 hard cut 不引入 pgvector、embedding provider、semantic summary endpoint、LLM answer generation 或 embedding background worker。
- N2. 本 hard cut 不引入 Meilisearch、Typesense、OpenSearch、Qdrant、Pinecone 或任何外部搜索服务。
- N3. 本 hard cut 不调用 OKX、GMGN、OpenAI 或其他 provider 来响应用户搜索；搜索只读 PostgreSQL 已持久化事实。
- N4. 本 hard cut 不承诺精确 `total_count`。高流量搜索返回 cursor page、`returned_count`、`has_more`、`next_cursor`；精确全量计数不是交互搜索主路径。
- N5. 本 hard cut 不尝试让裸文本 `BTC chart` 进入 `token_intent_resolutions`。裸文本仍由 lexical route 召回；是否扩展 entity extraction 到 naked token mention 是后续独立 spec。
- N6. 本 hard cut 不重做 Signal Lab candidate `q` 搜索；Signal Lab 可在后续复用 search v2 query modules，但不阻塞 event search hard cut。

## Target Architecture

搜索 v2 是一个 target-first, lexical-second, fuzzy-third 的 read model。用户 query 先被规范化成 search intent；单 token、cashtag、CA、handle 会进入 identity resolver。resolver 只读 current production identity 表：`cex_tokens`、`registry_assets`、`asset_identity_current`。它输出一组 `SearchTargetCandidate`，每个 candidate 是 `target_type + target_id + status + display`，而不是旧 asset aliases。

事件召回分三条 route：

1. **target route**：对 resolved target 读取 current `token_intent_resolutions`，JOIN `events`，得到系统已判定属于目标 token 的证据事件；ambiguous candidates 只作为候选上下文返回，不直接扩展 target route。
2. **lexical route**：对 normalized query 加 high-confidence alias expansion 后执行 Postgres FTS，保留 websearch 原生短语、OR、NOT，并对 english / simple 两种配置评分。
3. **trigram route**：当 query 可安全模糊化时，用 `pg_trgm` 对 `events.search_text` 做 typo / partial fallback，限制低质量 substring 噪音。

三条 route 的结果在 read model 中去重并做 RRF-style fusion。target route 的 base weight 高于 lexical route，lexical route 高于 trigram route；同一事件同时被 target 和 lexical 命中时得分合并，并保留 match reasons。最终以 `rank_score DESC, received_at_ms DESC, event_id DESC` 排序，cursor 编码同一组 sort keys。

搜索 v2 不做“双读旧路径”。旧 `AssetSearchService`、旧 raw `token_evidence` 主路径、旧 FTS count fallback、旧 HTTP query aliases 都被替换。前端只读新契约并通过 cursor 加载更多。

## Conceptual Data Flow

```
GMGN frame
  → ingest transaction
      → events.search_text/search_tsv
      → token_evidence/token_intents/token_intent_resolutions
      → cex_tokens/registry_assets/asset_identity_current
  → search v2 read model
      → parse q
      → resolve target candidates from current identity
      → retrieve target + lexical + trigram routes
      → fuse/de-dupe/page
  → /api/search + CLI search
  → frontend search drawer with load-more
```

Changed arrows:

- `search v2 read model → resolve target candidates from current identity` is new because current `/api/search` reads old `assets` candidates and raw `token_evidence`.
- `retrieve target + lexical + trigram routes` replaces the old exclusive branch design where `$btc` and `btc` never meet.
- `fuse/de-dupe/page` replaces single SQL `LIMIT` and the frontend 8-row cap.

No new ingestion or provider arrow is introduced.

## Core Models

`SearchIntent` is the normalized user intent. It records original text, normalized text, kind (`empty`, `handle`, `ca`, `symbol`, `text`), scope, and parse metadata. A bare single token such as `btc` is allowed to be both a symbol probe and lexical text; the model does not force early exclusivity.

`SearchTargetCandidate` is a deterministic target option. It records `target_type`, `target_id`, `symbol`, optional chain/address, candidate status (`resolved`, `ambiguous`, `unresolved`), source (`cex_token`, `asset_identity_current`, `registry_asset_address`), and confidence reason. It is display/context metadata for search, not a new identity source.

`SearchRouteHit` is one event hit from one route. It records `event_id`, route (`target`, `lexical`, `trigram`, `handle`), route rank, route score, matched target if any, and match reasons. Route hits are internal to the read model.

`SearchResultItem` is one fused public result. It records the decoded event, fused score, match type, match reasons, route score breakdown, and target metadata when a target route contributed.

`SearchCursor` is an opaque cursor encoding the final sort tuple. It is not an offset and must not expose SQL internals as a public contract.

## Interface Contracts

`GET /api/search` becomes the only HTTP search surface for evidence events.

Accepted query params:

- `q`: required non-empty search text after trimming.
- `limit`: optional, clamped to the existing API maximum policy.
- `scope`: `all | matched`.
- `cursor`: optional opaque cursor returned by the previous page.

Rejected query params:

- `symbol`, `ca`, `chain`, `handle` are no longer accepted by `/api/search`. Users express these as `q="$BTC"`, `q="eth:0x..."`, `q="0x..."`, or `q="@handle"`.

Response semantics:

- `ok=false, error="empty_query"` for empty `q`.
- `ok=false, error="invalid_cursor"` for malformed cursor.
- `data.query` echoes normalized intent.
- `data.page` contains `returned_count`, `has_more`, `next_cursor`.
- `data.target_candidates` contains deterministic identity candidates considered for target route.
- `data.items` contains fused result items.
- No exact `total_count`, no legacy `resolution`, no legacy `candidates` alias.

`parallax search` mirrors HTTP search semantics. It accepts positional `query`, `--limit`, `--scope`, and `--cursor`. It does not expose `--symbol`, `--ca`, `--chain`, or `--handle`.

WebSocket contracts are unchanged.

Signal Lab contracts are unchanged in this hard cut.

## Acceptance Criteria

- AC1. WHEN `/api/search?q=btc` is called with a database containing `cex_tokens.base_symbol='BTC'` and current `token_intent_resolutions.target_type='CexToken', target_id='cex_token:BTC'`, THEN the first page SHALL include those target-resolution events with match reason `target:cex_token`.
- AC2. WHEN `/api/search?q=$btc` is called against the same database, THEN the target candidates and target-route event set SHALL match `/api/search?q=btc` before lexical/fuzzy additions.
- AC3. WHEN `/api/search?q=bitcoin` is called and alias expansion maps BTC to bitcoin, THEN BTC target/alias related lexical rows SHALL be eligible even if the tweet text does not contain literal `btc`.
- AC4. WHEN `/api/search?q=%22bitcoin%20price%22` is called, THEN phrase search SHALL preserve phrase semantics instead of degrading to `bitcoin & price`.
- AC5. WHEN `/api/search?q=btc%20OR%20eth` is called, THEN lexical route SHALL preserve OR semantics instead of forcing AND across all terms.
- AC6. WHEN `/api/search?q=bitc` is called and FTS finds fewer than one full page, THEN trigram route SHALL contribute partial/fuzzy hits from `events.search_text`.
- AC7. WHEN more than `limit` fused results exist, THEN response SHALL set `page.has_more=true` and a second call with `cursor=page.next_cursor` SHALL return the next non-overlapping page.
- AC8. WHEN a tweet author handle contains `btc` but tweet body and target route do not match BTC, THEN it SHALL not outrank body/target matches for text query `btc`; explicit `@btc...` still searches the author.
- AC9. WHEN frontend displays search results with `has_more=true`, THEN the drawer SHALL render all loaded items and a load-more control that requests the next cursor.
- AC10. WHEN CLI help is regenerated, THEN `parallax search --help` SHALL document `query`, `--limit`, `--scope`, and `--cursor` only for search filters.
- AC11. WHEN implementation is complete, THEN repository-wide search SHALL find no runtime import of `AssetSearchService` and no `/api/search` runtime use of `AssetRepository.candidates_for_symbol`, `AssetRepository.candidates_for_ca`, `EvidenceRepository.search_fts`, or `EvidenceRepository.count_fts`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Target resolver over-recalls ambiguous DEX symbols such as `DOG` | High | Return all candidates with explicit candidate status and use target route only for deterministic CEX / single asset / address-resolved candidates; ambiguous symbols still get lexical route and visible target candidates. |
| Trigram substring search floods results for short queries | High | Enable trigram route only for normalized query length >= 4 or for safe single-token typo cases; cap route rows before fusion and require similarity threshold. |
| Dropping old HTTP params breaks manual callers | Medium | Hard cut is intentional; OpenAPI, CLI help, frontend, and tests are updated in the same change. No compatibility shim remains. |
| Rewriting generated `search_tsv` locks large `events` table | Medium | Rollout uses maintenance window; migration rebuilds generated column/index once. No dual generated columns. |
| Cursor score changes if new events arrive between pages | Medium | Cursor includes fused score plus received time and event id; pagination is stable for the result snapshot order, while live inserts may appear before the current cursor on a fresh search. This is acceptable for live search. |
| Alias dictionary becomes stale | Medium | Only high-confidence canonical crypto aliases are included. Unknown aliases fall back to lexical/trigram. Wider alias governance is an evolution item. |
| Removing exact `total_count` disappoints UI expectations | Low | UI emphasizes loaded count and `has_more`; exact counts are expensive and not necessary for live exploratory search. |

## Evolution Path

The next expansion is semantic retrieval, not a hidden fallback in this hard cut. A later semantic spec should introduce one bounded semantic document model and one explicit vector provider decision. The likely path is `pgvector` over a hot subset of events: watched events, current target events, Signal Pulse candidates, and recent high-heat target timelines. Semantic query should run as a third/fourth route with RRF and should expose evidence event ids used by any summary. It must not replace target identity lookup or lexical search.

If the team wants semantic summaries, the summary layer should be retrieval-grounded: search v2 retrieves evidence events, then an LLM summarizes with cited `event_id`/URL references. The LLM must not decide token identity or silently expand target candidates.

## Alternatives Considered

- **Keep `AssetSearchService` and add target fallback** — rejected because the service is built around mutually exclusive parse branches, old `assets` candidates, and raw token evidence. Keeping it would preserve the exact compatibility layer this hard cut is meant to delete.

- **Use only `token_intent_resolutions` for search** — rejected because naked text mentions such as `BTC chart` and natural-language phrases do not currently enter token evidence/resolutions unless a GMGN token payload exists. Lexical and trigram routes are still required.

- **Use only improved FTS/trigram** — rejected because deterministic target identity already exists and FTS cannot reliably distinguish `BTC` the target from usernames, unrelated text, or same-symbol DEX ambiguity.

- **Introduce Typesense/Meilisearch now** — rejected because current defects are in repository identity use, pagination, and FTS preprocessing. A new service would add sync/operational complexity before the Postgres source-of-truth path is correct.

- **Introduce pgvector/embedding now** — rejected for this hard cut because current main has no embedding provider, vector schema, background worker, hot/cold policy, or retrieval-grounded summary contract. Embeddings solve semantic paraphrase, not the present target and pagination bugs.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Resolve symbol/CA/handle query intent before lexical retrieval; read current production identity tables; fuse target, lexical, and trigram routes; return cursor pages; update API, CLI, frontend, tests, OpenAPI, and CLI docs together. |
| Ask first | Adding embedding/vector retrieval; adding external search service; changing entity extraction to treat naked uppercase symbols as token evidence; adding exact total counts; changing Signal Lab `q` semantics. |
| Never | Keep old `/api/search` `symbol/ca/chain/handle` params; read `assets / asset_aliases / asset_venues` for search identity; use raw `token_evidence.normalized_symbol` as the primary symbol search result set; keep `search_fts/count_fts` fallback; let author handle matches outrank explicit body/target matches. |
