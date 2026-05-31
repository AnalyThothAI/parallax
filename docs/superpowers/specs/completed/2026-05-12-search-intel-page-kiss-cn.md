# Spec - Search Intel 二级页 KISS 产品闭环

**Status**: Draft
**Date**: 2026-05-12
**Owner**: Codex with Qinghuan
**Related**:

- `docs/superpowers/specs/active/2026-05-11-search-v2-hard-cut-cn.md`
- `docs/superpowers/specs/completed/2026-05-10-frontend-deep-link-routing.md`
- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`
- `docs/FRONTEND.md`
- `docs/CONTRACTS.md`

## Background

当前 search 已经完成 Search V2 hard-cut 的后端方向：`/api/search` 接受 `q/limit/scope/cursor`，拒绝旧 `symbol/ca/chain/handle` query params，并返回 `query/page/target_candidates/items`。HTTP 入口在 `src/parallax/app/surfaces/api/http.py:118` 到 `src/parallax/app/surfaces/api/http.py:151`；public contract 也明确 `/api/search` 只接受 `q`、`limit`、`scope`、`cursor`，见 `docs/CONTRACTS.md:43` 到 `docs/CONTRACTS.md:50`。

Search read model 已经是 target-first。`SearchService.search(...)` 在 `src/parallax/domains/token_intel/read_models/search_service.py:50` 到 `src/parallax/domains/token_intel/read_models/search_service.py:101` 先 parse query、解析 target candidates、生成 lexical query；如果有 resolved target，则优先走 target page，否则融合 target/handle/lexical/substring/trigram routes。`SearchEventsQuery.resolve_targets(...)` 在 `src/parallax/domains/token_intel/queries/search_events_query.py:30` 到 `src/parallax/domains/token_intel/queries/search_events_query.py:35` 把 symbol / CA 解析到 current production targets；symbol resolver 读取 `cex_tokens` 和 `asset_identity_current`，见 `src/parallax/domains/token_intel/queries/search_events_query.py:82` 到 `src/parallax/domains/token_intel/queries/search_events_query.py:126`。

当前前端 search 仍然是 cockpit 顶部输入框 + 右栏 drawer 的交互。`CockpitLayout` 在 `web/src/components/CockpitLayout.tsx:151` 到 `web/src/components/CockpitLayout.tsx:168` 渲染 search form；提交后 `useLiveSelection.submitEvidenceSearch(...)` 在 `web/src/features/live/useLiveSelection.ts:186` 到 `web/src/features/live/useLiveSelection.ts:214` 先尝试从当前 `tokenItems` 唯一匹配 token，命中则只是选中右栏 token detail，不改变 URL；非 token query 才触发 search 并把结果塞进 `selectedSignal.kind = "query"`。

Search query 的数据请求在 `web/src/features/live/useLiveData.ts:108` 到 `web/src/features/live/useLiveData.ts:118`，通过 TanStack infinite query 调 `/api/search`。展示在 `web/src/components/EvidenceDetailDrawer.tsx:126` 到 `web/src/components/EvidenceDetailDrawer.tsx:218` 的 `SearchQueryDrawer`，它能展示所有 loaded items 和 load-more，但仍被右侧 detail panel 形态限制：用户不能分享 search URL，刷新不会恢复 search 页面，关键词搜索也没有主题聚合、token 关系、timeline 或 AI 解读。

项目已经有 token 二级页。路由在 `web/src/app/CockpitApp.tsx:256` 到 `web/src/app/CockpitApp.tsx:262`：`/token/:targetType/:targetId` 嵌在 live page 下。`TokenTargetPage` 在 `web/src/components/TokenTargetPage.tsx:46` 到 `web/src/components/TokenTargetPage.tsx:101` 从 URL params 得到 target，并拉 `/api/token-radar`、`/api/target-social-timeline`、`/api/target-posts`。这页已经具备 score audit、stage tape、message evidence 的基础，但定位还是“从 Radar 点进来的 audit page”，不是“search 的默认落地页”。

Token timeline read model 已经提供社交传播结构。`/api/target-social-timeline` 在 `src/parallax/app/surfaces/api/http.py:227` 到 `src/parallax/app/surfaces/api/http.py:255` 调 `TokenTargetSocialTimelineService.timeline(...)`；该 service 在 `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py:17` 到 `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py:75` 返回 `summary/market_overlay/stages/buckets/authors/posts/cascade`。阶段由 `build_token_target_stages(...)` 产出，阶段 phase 包括 `seed/ignition/expansion/concentration/chase`，见 `src/parallax/domains/token_intel/read_models/token_target_stage_builder.py:15` 到 `src/parallax/domains/token_intel/read_models/token_target_stage_builder.py:109`。

Token posts read model 已经能把每条 tweet 和价格锚点、post quality、catalyst score、stage annotation 绑定。`/api/target-posts` 在 `src/parallax/app/surfaces/api/http.py:189` 到 `src/parallax/app/surfaces/api/http.py:225` 暴露；`TokenPostsPanel` 在 `web/src/components/TokenPostsPanel.tsx:31` 到 `web/src/components/TokenPostsPanel.tsx:132` 已经支持 `window/ignition/history`、`recent/catalyst/quality`、watched only、hide duplicates、load more。

Signal Pulse 已经有 bounded agent recommendation 读模型。`SignalPulseService.pulse(...)` 在 `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py:23` 到 `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py:71` 返回 `factor_snapshot/agent_recommendation/gate/fact_card`；`SignalLabInspector` 在 `web/src/components/SignalLabInspector.tsx:19` 到 `web/src/components/SignalLabInspector.tsx:229` 展示 agent recommendation、fact card、eligibility gates、data health、alpha families 和 source event ids。Search Intel 可以参考这套 evidence-bound 解释方式，但不能让 LLM 参与 token identity 或 score。

市场数据有硬边界。`price_observations` 表有 `price_usd/market_cap_usd/liquidity_usd/volume_24h_usd/holders` 字段，见 `docs/generated/db-schema.md:567` 到 `docs/generated/db-schema.md:590`；但 `PriceObservationRepository.insert_observation(...)` 当前只允许 `observation_kind = "message_anchor"`，并明确 live/refresh prices 不持久化，见 `src/parallax/domains/asset_market/repositories/price_observation_repository.py:34` 到 `src/parallax/domains/asset_market/repositories/price_observation_repository.py:40`。因此当前 DB 里的 token price 主要是“每条社交信号附近的 anchor price”，不是连续 OHLC K 线。

当前 live market 是 process-local cache。`LivePriceGateway.snapshot(...)` 在 `src/parallax/domains/asset_market/runtime/live_price_gateway.py:123` 到 `src/parallax/domains/asset_market/runtime/live_price_gateway.py:148` 返回最新 in-memory price / mcap / liquidity / holders / 24h volume；`/api/live-market` 在 `src/parallax/app/surfaces/api/http.py:172` 到 `src/parallax/app/surfaces/api/http.py:187` 暴露该 snapshot。Search Intel 可展示 current market facts，但不能把 live cache 当作历史 K 线。

## Problem

Search 现在已经能找证据，但产品形态仍停在“右栏列表”。交易员搜索一个 token 时，需要的是 24h 社交传播、阶段、喊单 tweet、价格反应、市场基本面、score/harness、AI desk note 组成的一页判断链；产品经理搜索一个关键词时，需要的是 24h 提及、主题摘要、相关 token / 产品链路、传播峰值与证据流。当前 search 没有独立 URL、没有主题聚合页、token 搜索不默认进入二级页、右侧 `Select Token` 空态干扰主任务，也没有把已有 timeline/posts/pulse/harness 数据组合成闭环分析面板。

## First Principles

1. **KISS: 一个 search 二级页，不造研究平台。** 本设计只引入一个 Search Intel route 和一个聚合 read model。它组合现有 `/api/search`、target timeline、target posts、Token Radar、live market、Signal Pulse / harness 事实，不新增 ingestion pipeline、不新增 market data worker、不新增外部搜索服务。

2. **可信数据优先，绝不伪装 K 线。** 有 OHLC candles 时显示 K 线；没有 OHLC 数据时显示 anchor price line + social markers，并明确标注 `anchor price, not OHLC`。当前 `price_observations` 是 message anchor，不是连续 candles，这个边界由 `PriceObservationRepository.insert_observation(...)` 的 anchor-only 约束支撑，见 `src/parallax/domains/asset_market/repositories/price_observation_repository.py:34` 到 `src/parallax/domains/asset_market/repositories/price_observation_repository.py:40`。

3. **AI 只解释证据，不决定事实。** Search AI desk note 只能读 deterministic context：target identity、posts、stages、factor snapshot、market facts、harness rows、source event ids。它不得解析 token identity、不得改分、不得发 provider call、不得输出无 evidence ids 的结论。这个边界继承 Token Intel hard boundary：API/front-end 不做 extraction/resolution/provider/scoring，见 `src/parallax/domains/token_intel/ARCHITECTURE.md:101` 到 `src/parallax/domains/token_intel/ARCHITECTURE.md:107`。

4. **闭环定义是可用产品，不是组件堆叠。** 完成标准不是“有一个 route”或“有一个 chart”，而是 token search 和 keyword search 都能从输入到判断闭环：搜索、识别模式、展示摘要、展示 timeline、展示证据、展示数据健康、允许继续 drill down。

## Goals

- G1. WHEN 用户在顶部搜索输入 `$BTC`、`btc`、CA 或 resolved target alias，THEN UI SHALL 导航到 token search 二级页，而不是只选中右侧 drawer。
- G2. WHEN 用户访问 `/search?q=<query>&window=24h&scope=all`，THEN 页面 SHALL 根据 `/api/search` 的 `target_candidates` 自动进入 `token`、`keyword` 或 `ambiguous` 模式。
- G3. WHEN query 解析到唯一 resolved token target，THEN token mode SHALL 在首屏展示 identity、market facts、24h social summary、AI/deterministic desk note、price/social timeline 和关键风险。
- G4. WHEN token mode 有 timeline data，THEN 页面 SHALL 展示 stage sequence，每个 stage 对应代表性 tweet、作者角色、post quality、stage price delta 和可点击证据列表。
- G5. WHEN token mode 有 OHLC candle source，THEN 页面 SHALL 展示 K 线和 tweet/stage markers；WHEN 没有 OHLC source，THEN 页面 SHALL 展示 anchor price line，且明确标注不是 K 线。
- G6. WHEN query 是关键词或主题（例如“挖矿”），THEN keyword mode SHALL 展示 24h mentions timeline、top related tokens、top handles、主题摘要、产品/链路 tags 和 evidence stream。
- G7. WHEN AI configured 且 deterministic context 足够，THEN 页面 SHALL 展示 evidence-bound AI desk note；WHEN AI 未配置、运行失败或 context 不足，THEN 页面 SHALL 展示 deterministic summary 和数据健康原因，不留空白卡片。
- G8. WHEN page 显示任何 score / recommendation，THEN SHALL 展示 component breakdown、gate 或 evidence ids；不出现黑盒结论。
- G9. WHEN search result 有更多证据，THEN 页面 SHALL 支持 cursor load-more，并保持 URL 可刷新、可分享。
- G10. WHEN Search Intel 完成，THEN `/search*` route SHALL 不再显示右侧 `Select Token` 空态；search 是主任务页面，不是 detail drawer 状态。

## Non-goals

- N1. 不引入新的外部 search service、vector DB、embedding pipeline 或 semantic background worker。
- N2. 不新增 market data 持久化 worker 来补齐 DEX OHLC；缺 OHLC 的 target 明确降级为 anchor price line。
- N3. 不让前端从 price anchors 计算伪 OHLC candles。
- N4. 不改变 Search V2 retrieval 排序、resolver policy 或 score 公式。
- N5. 不重写 Token Radar table、Signal Lab page 或 existing drawer；Search Intel 复用它们能用的组件与 read models。
- N6. 不把关键词搜索强行解析成 token；ambiguous query 必须展示候选而不是猜。
- N7. 不在初始闭环里做账户画像二级页、项目主页、跨链资产合并或交易执行入口。

## Target Architecture

Search Intel 是一个 route-first 页面，位于 cockpit shell 内，但使用 focus layout：左侧 rail / topbar 保留，右侧 detail panel 在 `/search*` 下隐藏或折叠。顶部 search form 提交后统一导航到 `/search?q=...&window=24h&scope=<current>`；页面根据后端返回的 search intent 和 target candidates 决定 mode。

核心后端是一个 read-only `SearchInspect` 聚合模型。它不替代 `/api/search`，而是在 page 需要完整上下文时组合现有 read models：

- Search V2：query intent、target candidates、evidence hits、cursor page。
- Token target timeline：stages、buckets、authors、posts、market overlay。
- Token target posts：evidence stream 和 load-more cursor。
- Token Radar / factor snapshot：current score、families、gates、data health。
- Live market：当前价格、mcap、liquidity、holders、24h volume。
- Signal Pulse / harness：已有 agent recommendation、historical outcome/credit context，如存在则展示；不存在则显示缺失原因。

Search Intel 的 UI 分三种模式：

1. `token`：唯一 resolved target。页面以 token 判断链为主，关键词 evidence 只作为补充。
2. `keyword`：没有 resolved token target。页面以主题聚合为主，related tokens 是从 search hits 的 target / token resolutions 聚合出的 drill-down 入口。
3. `ambiguous`：多个 plausible candidates。页面先展示候选比较和关键词 evidence，不自动跳 token mode；用户选择后进入 token mode。

AI 是解释层，不是主数据源。Search Inspect 先返回 deterministic summary；如果 AI configured 且 context 达到最低证据门槛，Search Insight Agent 生成结构化 `agent_note`。该 note 使用与 Signal Pulse 类似的 schema/version/audit/evidence discipline，输出必须引用 evidence event ids。页面永远先可用：AI pending 或 failed 只是 `agent_note.status`，不阻塞 deterministic product。

## Product Design

### Global Search Behaviour

顶部 search form 仍在 topbar，但提交行为改为 route navigation：

- 输入 `$TOKEN`、`TOKEN`、`chain:address`、`0x...`：跳 `/search?q=<encoded>&window=24h&scope=<current>`，由后端判断是否 unique token。
- 输入 `@handle`：仍跳 `/search?q=@handle...`，keyword mode 里按 account source 展示。
- 输入自然语言或中文词：跳 keyword mode。
- 在 Signal Lab 内搜索不再劫持为 Signal Lab `q`，除非用户处在 Signal Lab 专用过滤框。全局 search 永远进入 Search Intel。

默认 window 为 `24h`，因为用户明确希望 token / keyword 都看到过去 24 小时。页面提供 `5m / 1h / 4h / 24h` segmented control，但 initial landing 固定是 24h。

### Token Mode Layout

Token mode 首屏是交易员判断链，垂直布局如下：

1. **Case Header**
   - Token label、target type、chain/address 或 CEX inst id。
   - Status chips：resolved / ambiguous risk / market ready / AI status。
   - Actions：Open venue、copy route、refresh。
   - Window/scope segmented controls。

2. **Market + Social Snapshot Strip**
   - Market：live price、24h volume、market cap、liquidity、holders、provider、age。
   - Social：mentions、unique authors、watched posts、top author share、phase、duplicate share。
   - Score：rank score、recommended decision、gate max decision、blocked reasons count。
   - Data health：identity / market / social / alpha。

3. **Desk Note**
   - Primary read：`看多 / 观察 / 暂不交易 / 数据不足`，来自 agent note 或 deterministic summary。
   - Why now：最多 3 条，必须引用 event ids 或 factor keys。
   - Invalidation：最多 3 条，例如“新增作者未扩散”“价格已 chase”“market data stale”。
   - Residual risks：重复文本、单一作者、缺市场字段、无 watched account。

4. **Social x Market Timeline**
   - 上半：OHLC K 线或 anchor price line。
   - 下半：mentions histogram、new authors、watched posts。
   - Markers：stage start、representative tweets、watched posts、price chase。
   - 交互：hover 显示该时间 bucket 的 posts/authors/price；click stage marker 过滤 evidence stream。

5. **Stage Narrative**
   - 横向 stage tape：seed / ignition / expansion / concentration / chase。
   - 每个 stage card：时间范围、posts/authors、top author share、price delta、representative tweet、risks。
   - 点击 card 后下方 Evidence Stream 进入 `stage_id` filter。

6. **Evidence Stream**
   - 复用 TokenPostsPanel 的语义：range、sort、watched only、hide duplicates、load more。
   - 每条 evidence 展示：handle、time、stage phase、author role、post quality、catalyst score、price at mention、link。

7. **Score / Harness**
   - Score Ledger：复用 factor snapshot breakdown。
   - Harness Context：如果有 snapshots/outcomes/credits，展示同 target 或同 symbol 的历史 outcome；如果没有，显示“no settled harness sample”而不是空表。

### Keyword Mode Layout

Keyword mode 是产品经理 / 研究员视角，不假装它是 token 页面。

1. **Topic Header**
   - Query text、window/scope、returned hits、has more、search mode。
   - Data health：FTS/trigram/target route 命中情况。

2. **Topic Summary**
   - Deterministic summary：mentions、unique authors、watched mentions、peak bucket、top handles、top related tokens。
   - AI summary：过去 24h 主要在讨论什么、涉及哪些产品链路、哪些 token 被带出、是否有刷屏/单点传播风险。

3. **Mention Timeline**
   - 24h bucket histogram：posts、unique authors、watched posts。
   - Peak bucket click 过滤 evidence stream。
   - 不展示 price chart，除非用户选择某个 related token。

4. **Related Tokens**
   - 从 `SearchResultItem.target` 和 event token resolutions 聚合。
   - 每行：symbol / target id、mentions、authors、latest seen、market data readiness、top stage if available。
   - 点击进入同一 route 的 token mode：`/search/token/:targetType/:targetId?q=<original>&window=24h&scope=...` 或等价 query-state。

5. **Product / Chain Tags**
   - 从 hashtags、domains、cashtags、chain/address、known target metadata 聚合。
   - 只作为导航/filter chips，不作为 score。

6. **Evidence Stream**
   - Search hits cursor list：recent / relevance / watched filters。
   - 每条展示 match route、text、handle、target candidate if any、source link。

### Ambiguous Mode Layout

Ambiguous mode 不猜 token。页面顶部显示 candidate comparison：

- Candidate rows：target type、symbol、chain/address、source、reason、status、recent mentions。
- 默认展示 keyword evidence 和 related tokens。
- 用户点击 candidate 后进入 token mode，并保留 original query 作为 context。

## Component Model

`SearchIntelPage` owns route params, window/scope query params, and mode switching. It does not call low-level API clients directly; it consumes search inspect hooks.

`SearchCaseHeader` renders query / token identity / controls / status chips.

`SearchSnapshotStrip` renders market/social/score/data-health facts. It is dense and scanner-friendly, not card-heavy marketing UI.

`SearchDeskNotePanel` renders deterministic summary and optional AI note. It must show status: `deterministic_only`, `agent_pending`, `agent_ready`, `agent_failed`, or `insufficient_context`.

`SocialMarketTimeline` renders token mode timeline. It chooses:

- `candlestick` when OHLC candles are present.
- `anchor_line` when only message anchors are present.
- `social_only` when no usable price points exist.

`StageNarrativeRail` renders the stage tape and stage cards.

`KeywordTopicPanel` renders keyword summary, product/chain tags, and related tokens.

`SearchEvidenceStream` renders either token posts or search hits through a shared row shape, with cursor load-more.

`SearchHarnessPanel` renders score ledger plus settled / pending harness context.

KISS component rule: no nested card-in-card layouts; repeated entities can be cards, page sections are full-width bands or unframed dense panels.

## Data Contract

`SearchInspectData` is the semantic page contract:

- `query`: normalized query intent and original text.
- `mode`: `token | keyword | ambiguous`.
- `window`, `scope`.
- `target_candidates`: deterministic candidates from Search V2.
- `selected_target`: target ref when mode is token.
- `search_page`: cursor page of search evidence.
- `topic`: keyword rollup, present for keyword/ambiguous mode.
- `token_case`: token rollup, present for token mode.
- `agent_note`: AI/deterministic note status and payload.
- `data_health`: explicit readiness for search, identity, market, social, alpha, agent.

`TokenCase` contains:

- `identity`: same target identity semantics as Token Radar.
- `market_snapshot`: live market plus anchor/readiness context.
- `radar_snapshot`: factor snapshot, score, gates, source event ids.
- `timeline`: summary, buckets, stages, authors, posts.
- `price_series`: `kind = candlestick | anchor_line | social_only`, points, provider, caveat.
- `posts_page`: current evidence page.
- `pulse`: best matching Signal Pulse item if available.
- `harness`: snapshots/outcomes/credits summary if available.

`TopicRollup` contains:

- `mentions`, `authors`, `watched_mentions`, `peak_bucket`.
- `timeline_buckets`.
- `related_tokens`.
- `top_handles`.
- `product_chain_tags`.
- `evidence_clusters`.

`SearchInsightNote` contains:

- `status`.
- `summary_zh`.
- `trader_read` or `pm_read`.
- `primary_reasons`.
- `timeline_notes`.
- `upgrade_conditions`.
- `invalidation_conditions`.
- `residual_risks`.
- `evidence_event_ids`.
- `model/audit` when agent-backed.

## Interface Contracts

`GET /api/search/inspect`

Inputs:

- `q`: required search text.
- `window`: `5m | 1h | 4h | 24h`, default `24h`.
- `scope`: `all | matched`, default inherited from UI if present, otherwise `all`.
- `target_type` and `target_id`: optional explicit target override used when user selected an ambiguous candidate.
- `cursor`: optional evidence cursor for the active evidence stream.

Output:

- `ok=true` with `SearchInspectData`.
- `ok=false, error="empty_query"` for empty query.
- `ok=false, error="invalid_cursor"` for malformed cursor.
- `ok=false, error="target_required"` when explicit target override is incomplete.

Existing `/api/search` remains available for raw evidence search and is consumed by Search Inspect internally or by lightweight clients.

`GET /api/search/insight-note` is not a separate public surface in the KISS design. Agent note status is part of `/api/search/inspect`; the backend may compute deterministic note synchronously and agent note asynchronously/cached, but the page reads one contract.

WebSocket contracts do not change. Live market updates continue through existing `/ws` subscription machinery; Search Intel may subscribe to selected token target when in token mode.

## Completion Definition

The feature is not complete until all of the following are true in one user-visible flow:

- Global search navigates to a shareable Search Intel URL.
- Unique token query renders token mode with 24h timeline, stage cards, market facts, evidence stream, score/gate context, and desk note.
- Keyword query renders keyword mode with topic summary, mention timeline, related tokens, tags, evidence stream, and desk note.
- Ambiguous query renders candidate comparison and lets the user choose a token without losing original query context.
- AI unavailable state still leaves a useful deterministic product.
- Missing OHLC state is explicit and cannot be mistaken for a true K line.
- Right-side `Select Token` empty panel is not visible on Search Intel routes.

This definition prevents shipping a route shell, chart shell, or agent shell as a “done” product.

## Landing Order And Closed-Loop Gates

Implementation may be sliced internally, but the user-facing feature remains incomplete until the full completion definition passes.

1. **Navigation gate**: top search opens `/search`, URL state restores on refresh, focus layout hides the right empty detail panel. This gate is necessary but not sufficient; it cannot ship as the final product.
2. **Deterministic data gate**: `/api/search/inspect` returns token/keyword/ambiguous modes by composing current read models. Token and keyword pages are useful without AI. This is the first closed-loop internal dogfood point.
3. **Timeline/market gate**: token mode renders social timeline, stage cards, evidence stream, and price panel with honest `candlestick | anchor_line | social_only` status. No fake K line is allowed.
4. **Insight gate**: deterministic summary and optional agent note share one panel and one data-health contract. AI failure is visible, bounded, and non-blocking.
5. **Harness/product gate**: score/gates/harness context, related-token drilldown, load-more, and route shareability all pass manual UI verification.

The route must not be presented as complete before gate 5, even if gates 1-4 are individually working.

## Visualization And Open-Source Components

Use one charting dependency only.

Recommended: TradingView Lightweight Charts for token mode market chart because it is optimized for financial charts and supports candlestick series, live updates, resize handling, and markers. It should be used only where we have real OHLC candles or explicit anchor-line data. Social bars can remain a lightweight React/CSS layer aligned by time buckets to avoid forcing a heavy charting abstraction across every panel.

Rejected for initial implementation: Apache ECharts. It is more flexible for custom mixed visualizations, but Search Intel does not need custom multi-coordinate rendering if we keep the KISS split: market chart above, social timeline below, stage cards beside/below. ECharts remains a future option if we later need dense custom overlays.

## Acceptance Criteria

- AC1. WHEN user submits `btc`, `$BTC`, or a resolvable CA in global search, THEN browser URL SHALL become `/search?q=...&window=24h&scope=...` and page SHALL render token mode if exactly one resolved target exists.
- AC2. WHEN user hard-refreshes a token-mode Search Intel URL, THEN page SHALL restore the same target, window, scope, timeline, evidence stream, and desk note state from HTTP data.
- AC3. WHEN user searches `挖矿`, THEN page SHALL render keyword mode with 24h mention buckets, top handles, related tokens, product/chain tags, summary, and evidence stream.
- AC4. WHEN search has multiple plausible targets, THEN page SHALL render ambiguous mode and SHALL NOT auto-pick a token.
- AC5. WHEN token timeline has stages, THEN clicking a stage SHALL filter/highlight representative evidence and show that stage's price/social facts.
- AC6. WHEN token has OHLC candles, THEN market panel SHALL display candlesticks with tweet/stage markers.
- AC7. WHEN token lacks OHLC candles but has anchor prices, THEN market panel SHALL display anchor price line with an explicit caveat and SHALL NOT render candlesticks.
- AC8. WHEN token lacks usable market points, THEN market panel SHALL display social-only timeline plus data-health reason.
- AC9. WHEN AI is configured and evidence context passes minimum thresholds, THEN desk note SHALL include evidence-bound AI summary with event ids.
- AC10. WHEN AI is not configured, pending, failed, or insufficient context, THEN desk note SHALL show deterministic summary and status reason.
- AC11. WHEN score or recommendation appears, THEN component breakdown/gates/evidence ids SHALL be visible in the same page.
- AC12. WHEN evidence stream has more pages, THEN load-more SHALL append non-overlapping rows and preserve route state.
- AC13. WHEN on `/search*`, THEN right detail panel SHALL not show `Select Token` empty state.
- AC14. WHEN UI verification runs, THEN affected routes SHALL pass hard reload, no failed `/api/*`, expected WebSocket/live-market behaviour where applicable, and no score without breakdown.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Scope creep turns search into a full research terminal | High | One route, one inspect contract, reuse current read models; no new external search, no new market worker, no account/project pages. |
| Users mistake anchor prices for K lines | High | `price_series.kind` is explicit; UI labels anchor line as not OHLC; candlestick rendering requires real candles. |
| AI hallucinates unsupported narratives | High | Agent note must include evidence event ids; deterministic summary is always shown; AI cannot alter identity, score, or gates. |
| Keyword mode becomes a raw list with a nicer header | High | Acceptance requires mention timeline, related tokens, tags, summary, and evidence stream before completion. |
| Token mode only works for current Radar top 48 | Medium | Search Inspect resolves target from Search V2 and target timeline/posts directly; Token Radar snapshot is optional context, not the only way to render. |
| Related token aggregation overstates ambiguous symbols | Medium | Related tokens preserve candidate status/source/reason and do not auto-enter token mode unless user selects. |
| Chart dependency increases UI complexity | Medium | Use Lightweight Charts only in `SocialMarketTimeline`; keep social bars and stage cards as normal React. |
| Search Inspect endpoint becomes a god service | Medium | It composes existing read models and exposes a page contract; no raw scoring, provider calls, ingestion, or mutation. |

## Evolution Path

After this closed-loop page is stable, the next useful expansions are:

- Real CEX OHLC candles from the existing OKX CEX integration boundary for CEX targets that have `native_market_id`.
- DEX candle provider evaluation as a separate market-data spec.
- Semantic retrieval / embedding for long-form keyword queries, only after deterministic keyword rollup is measured.
- Account/profile drilldown from top handles.
- Persisted Search Insight agent cache if on-demand agent cost becomes material.

The design must not foreclose these, but none of them are required for the initial closed-loop Search Intel product.

## Alternatives Considered

- **Keep search in the right drawer and make it prettier** - rejected because it cannot satisfy shareable URL, refresh restore, keyword topic timeline, or route-level focus layout.
- **Make only `/token/:targetType/:targetId` better and skip keyword page** - rejected because user explicitly needs keyword searches like “挖矿” to show 24h mentions, summaries, products, and related tokens. Token-only would be a half product.
- **Build a full new research workspace with saved searches, accounts, projects, semantic search, and custom market workers** - rejected because it violates KISS and would delay a usable closed-loop search page.
- **Use AI first, deterministic UI second** - rejected because AI cannot decide identity or compensate for missing timeline/market evidence. The deterministic page must be useful when AI is unavailable.
- **Render K lines from message anchor prices** - rejected because anchor observations are sparse event-time prices, not OHLC candles. This would be misleading.
- **Use Apache ECharts immediately for a unified custom timeline** - rejected because Lightweight Charts plus existing React timeline components cover the needed financial chart and social evidence interactions with less complexity.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Global search opens a URL-backed Search Intel page. |
| Always | Unique target query enters token mode; keyword query enters keyword mode; multiple candidates enter ambiguous mode. |
| Always | Token mode shows market/social/stage/evidence/score/insight in one page. |
| Always | Keyword mode shows topic summary/timeline/related tokens/tags/evidence/insight in one page. |
| Always | Missing data is rendered as explicit data health, not hidden. |
| Always | AI output cites evidence ids and never overrides deterministic facts. |
| Ask first | Adding embeddings, external search service, DEX candle worker, account pages, saved searches, or trade execution. |
| Ask first | Persisting new search insight tables beyond existing agent audit/cache patterns. |
| Never | Show fake candlesticks from anchor prices. |
| Never | Ship only route shell, chart shell, or AI shell as complete. |
| Never | Let `/search*` fall back to the right-panel `Select Token` empty state. |
| Never | Let frontend recompute scores or token identity. |
