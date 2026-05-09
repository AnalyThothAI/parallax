# Token Radar V3 Code Review And Runtime Compatibility Audit

Date: 2026-05-07

## Verdict

当前 Token Radar 链路不是缺一个 `$VERSA + CA` 的局部 merge，而是存在三层结构性半成品：

1. **语义主语错位。** `asset_mentions` 被当成最终交易对象，但 mention 只是 evidence。一个事件里的 `$VERSA`、CA、GMGN payload、引用文本应该先聚成 token intent。
2. **新旧 runtime 并存。** `asset_*` identity path、旧 `token_*` market/signal path、未使用的 projection tables、前端自算 scoring 同时存在，导致系统没有单一事实源。
3. **状态不可解释。** resolver、provider、market、score 的失败状态被折叠成 `unresolved` / `provider_not_found` / `market unavailable`，生产排障会失真。

测试当前是绿的，但大量测试在固化旧行为，例如“无链 CA 先 unresolved”“CA job 只回填 CA attribution”“asset-flow-v1 从 asset_attributions 即时 group”。这些测试不能证明新架构正确，只能证明旧兼容路径稳定存在。

## Blocking Findings

### Finding 1: entity facts 丢失 span，导致后续无法可靠构造 intent

Files:

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py:28-36`
- `src/gmgn_twitter_intel/pipeline/entity_extractor.py:45-73`

`ExtractedEntity` 没有 `span_start/span_end/text_surface/sentence_id`。extractor 在 EVM CA 上拿到了 `match.start()/end()`，但只用于 chain hint；cashtag 直接用 `findall()`，完全没有位置。这样 V3 需要的“同一句 / 80 字符内 `$VERSA + CA` 聚合”无法在事实层重放，只能在后面靠同事件 merge，这正是现在耦合的源头。

Impact:

- 无法解释为什么 `$A CA1 $B CA2` 应该或不应该配对。
- 无法区分正文和 quoted/reference text 的 evidence strength。
- 未来 URL/provider evidence 也无法做局部聚类。

Required cut:

- `event_entities` 或新 `token_evidence` 必须保存 span 和 text surface。
- intent builder 只能依赖这些事实，不回头 parse raw text 做隐式逻辑。

### Finding 2: ingest hot path 直接 mention -> attribution，没有 intent 层

Files:

- `src/gmgn_twitter_intel/pipeline/ingest_service.py:65-79`
- `src/gmgn_twitter_intel/pipeline/asset_mention_builder.py:33-55`

`IngestService` 直接 `build_asset_mentions()`、`insert_mentions()`、`resolve_many()`、`persist_asset_decisions()`。`resolve_many()` 对每条 mention 独立解析，所以同一事实会自然拆成多个 Radar 桶。

Impact:

- `$VERSA + 0x2cc0...` 会生成 symbol mention 和 CA mention 两个独立 attribution。
- GMGN payload、text CA、text cashtag 之间没有 evidence role，只能靠后续 backfill 修补。
- store-first payload 对外发布的是 `asset_attributions`，WS/API 都被旧模型绑住。

Required cut:

- ingest 写 `token_evidence` 和 `token_intents`。
- resolver 解析 intent，不解析 mention。
- `asset_mentions` 只能做 migration/debug material，不能进入 Radar runtime。

### Finding 3: 无链 CA 跳过本地 exact CA venue lookup

Files:

- `src/gmgn_twitter_intel/pipeline/asset_resolver.py:65-83`
- `src/gmgn_twitter_intel/storage/asset_repository.py:452-489`
- `tests/test_asset_resolver.py:250-268`

`AssetResolver._resolve_ca()` 在 `_resolve_direct_dex()` 失败后直接 `upsert_unresolved_ca()` 并 queue job。仓库已有 `candidates_for_ca(chain=None,address=...)`，但 resolver 没用。测试还明确断言这个旧行为。

Impact:

- 本地已有 Base venue 的 `0x2cc0...` 仍会先显示 unresolved / market unavailable。
- provider job 不跑、没配置、失败、限流时，这个错误会长期存在。
- 本地 registry 的权威性被 provider availability 反向绑架。

Required cut:

- 无链 CA 必须先查 local exact CA。
- 单一 active venue 直接 selected；多个 venue ambiguous；没有才 queue provider。
- 当前测试要反转为 golden regression。

### Finding 4: provider backfill 回填 mention 类型，不回填 event intent

Files:

- `src/gmgn_twitter_intel/pipeline/asset_resolution_worker.py:93-128`
- `src/gmgn_twitter_intel/storage/asset_repository.py:931-1056`
- `tests/test_asset_resolution_worker.py:107-144`

symbol job 调 `reassign_symbol_attributions()`，CA job 调 `reassign_ca_attributions()`。这两个都是按 mention 类型批量 supersede，不知道同事件内其他 evidence。CA job 成功后不会把同事件 `$VERSA` 从 ambiguous bucket 合并到 resolved CA intent。

Impact:

- 同一事件能同时保留 resolved CA row 和 ambiguous symbol row。
- 回填是全局 symbol/address 维度，缺少 per-event audit context。
- provider candidate 只挂 mention_id，不挂 intent_id，无法回答“这个 event 为什么被选中/拒绝”。

Required cut:

- provider 写 observation/candidates 后触发 intent re-resolution。
- supersede 的对象是旧 intent resolution，不是某个 mention row。
- candidate audit 必须以 intent 为主键。

### Finding 5: Radar projection 仍按 raw attribution asset_id 即时 group

Files:

- `src/gmgn_twitter_intel/storage/asset_repository.py:1240-1492`
- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py:28-45`

`asset_flow_rows()` 从 `asset_attributions` 过滤后按 `asset_id` group。只要一个 event 有两个非 superseded attribution，它就可以进入两个 Radar row。`AssetFlowService` 还声明 projection source 是 `asset_attributions`，不是 materialized read model。

Impact:

- 事件级 dedupe 无法保证。
- attention lane 会继续显示已被 CA evidence 解释过的 symbol。
- 每个 request 都在复杂 SQL 里重做 projection，API path 承担业务计算。

Required cut:

- `token_radar_rows` / V3 materialized read model 成为唯一读取源。
- projection builder 做 event-intent-asset 级 dedupe。
- HTTP 不再 ad hoc group attribution rows。

### Finding 6: market missing 状态被错误折叠为 provider_not_found

Files:

- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py:128-150`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py:65-123`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py:33-88`

当没有 snapshot 或 snapshot 空时，API 统一返回 `market_status=missing` 和 `market_observation_status=provider_not_found`。但市场缺失可能是 identity unresolved、no venue、provider not configured、pending refresh、provider error、rate limited、stale 等。

Impact:

- 截图里的 market unavailable 不可诊断。
- OKX DEX 未配置会被看成 provider 查无结果。
- 价格数据问题和身份解析问题被混在一起，排障方向会错。

Required cut:

- 增加 provider observation/audit table。
- market status 使用 `no_venue/provider_not_configured/provider_not_found/provider_error/rate_limited/pending_refresh/ready/stale/insufficient_history`。
- CEX/DEX tradeability 分开，不让 CEX 缺 DEX 字段。

### Finding 7: 前端重新计算 score/decision，覆盖后端语义

Files:

- `web/src/App.tsx:997-1145`
- `web/src/api/types.ts:207-237`
- `web/src/api/types.ts:392-403`

前端把 `/api/asset-flow` row 转成 `TokenFlowItem` 时重新计算 heat、quality、propagation、tradeability、timing、opportunity，并用本地阈值决定 `driver/watch/discard`。后端 attention row 返回 `investigate` 也会被前端丢失，因为 `Decision` 类型只有 `driver | watch | discard`。

Impact:

- unresolved/ambiguous 可以因 heat 高变成 driver。
- 后端 scoring modules 和 UI 展示不一致。
- 任何后端 hard risk 都可能被前端合成逻辑绕过。

Required cut:

- API 返回完整 score ledger。
- 前端只渲染 `row.score.decision`。
- `assetFlowRowToTokenItem()` 删除或变成纯字段映射，不再计算 score。

### Finding 8: materialized projection tables 存在但没有服务生产读取

Files:

- `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0005_asset_identity_resolution.py:282-365`
- `src/gmgn_twitter_intel/storage/projection_repository.py:7-23`
- `src/gmgn_twitter_intel/cli.py:841-847`

迁移创建了 `asset_attention_buckets` 和 `asset_flow_window_snapshots`，`ProjectionRepository` 也声明了 projection names，但 HTTP/CLI 的 `rebuild-asset-flow` 只是调用 `AssetFlowService.asset_flow()` 返回即时计算结果，没有写 read model。

Impact:

- 看起来已有 read model，实际上 runtime 仍是 request-time SQL。
- projection health 可能显示 schema 存在，但数据路径并没有闭环。
- 后续开发会误以为兼容层已经完成，继续在旧 service 上打补丁。

Required cut:

- 要么删除这些未完成 projection tables/runtime references。
- 要么实现真正 builder + repository + API read path。
- V3 推荐直接新建 `token_radar_rows`，避免继续扩展 asset-flow-v1。

### Finding 9: 旧 token runtime 仍被 app/api/cli/session 主动装配

Files:

- `src/gmgn_twitter_intel/api/app.py:42-43`
- `src/gmgn_twitter_intel/api/app.py:218-223`
- `src/gmgn_twitter_intel/storage/repository_session.py:16-47`
- `src/gmgn_twitter_intel/pipeline/token_signal_settlement.py:79-175`
- `src/gmgn_twitter_intel/pipeline/market_observation_worker.py:89-109`
- `src/gmgn_twitter_intel/api/http.py:235-303`

旧 `TokenRepository`、`MarketObservationRepository`、`TokenSignalRepository` 仍在 runtime session 和 HTTP/CLI 中可用。虽然 `MarketObservationWorker` 没在 serve lifecycle 启动，但它仍是可执行旧路径，settlement 仍读 `token_market_snapshots`。

Impact:

- 价格/收益闭环仍可能落在旧 token_id，而 Radar 显示 asset_id。
- API surface 暴露两套市场事实源。
- 迁移期“兼容”会变成长期双系统。

Required cut:

- runtime session 默认不挂旧 token repos。
- 旧 token endpoints 移到 archived/debug namespace 或删除。
- outcome settlement 迁到 asset/venue snapshots。

### Finding 10: AssetRepository 是跨 bounded context 的大泥球

Files:

- `src/gmgn_twitter_intel/storage/asset_repository.py`

这个文件 1724 行，负责 mentions、assets、aliases、venues、resolution candidates、attributions、market snapshots、jobs、flow SQL、timeline SQL、search helpers。它把 evidence、identity、market、read model、timeline retrieval 混在一个 repository。

Impact:

- 单个改动容易跨层破坏。
- 无法让 resolver policy、market sync、Radar projection 各自拥有清晰契约。
- 兼容代码很难删，因为所有路径都依赖同一个类。

Required cut:

- 拆成 `TokenEvidenceRepository`、`AssetRegistryRepository`、`IntentResolutionRepository`、`MarketRepository`、`TokenRadarRepository`。
- repository 只做 persistence，不放 resolver/read-model policy。

## Module Review

### Collector / Normalizer

Status: mostly solid.

Keep:

- `normalizer.py` 把 GMGN frame 归一到 `TwitterEvent`，并保留 raw payload。
- `gmgn_token_payload.py` 能解析 GMGN token snapshot，作为 strong evidence 很有价值。

Risk:

- `TokenSnapshot` 直接进入 `asset_mention_builder`，没有进入独立 evidence model。

V3 action:

- GMGN payload 写 `token_evidence(source_kind=gmgn_payload,strength=strong)`。

### Text / Entity Extraction

Status: deterministic but incomplete.

Keep:

- regex + `eth_utils` + `solders` 是成熟、KISS 的确定性方法。

Risk:

- 缺 span/text surface。
- plain URL/domain 没有 token URL parser，后续如果加 GMGN/DexScreener URL 会被迫塞进 resolver。

V3 action:

- `ExtractedEntity` 增加 span/surface。
- URL token parser 作为 evidence builder 插件，不进 resolver。

### Mention Builder / Ingest

Status: half-finished compatibility layer.

Risk:

- mention builder 是 V2 临时桥，不应继续作为 Radar source。
- `source_entity_id=None`，事实表和 mention 表没有强 trace。

V3 action:

- 新建 token evidence/intent builder。
- `asset_mentions` 只用于旧数据迁移和 debug。

### Resolver / Resolution Worker

Status: policy shape exists, abstraction层级错误。

Keep:

- provider job 异步化是对的。
- candidate scoring 可以保留思路。

Risk:

- resolver 解析 mention。
- no-chain CA 不查 local venue。
- backfill 按 symbol/address 全局重写，不按 intent。
- candidate audit 挂 mention，不挂 intent。

V3 action:

- `TokenIntentResolver.resolve(intent)`。
- provider observation -> candidate rows -> intent re-resolution。

### Asset Registry / Repository

Status: schema方向对，repository边界不对。

Keep:

- `assets/asset_aliases/asset_venues/asset_market_snapshots` 是正确基础。
- DEX/CEX venue identity 分开是好的。

Risk:

- unresolved/ambiguous 也存在 `assets` 表，容易被当真实 asset 聚合。
- `canonical_symbol` 可被 `_upsert_asset()` 更新，没有显式 source priority guard。
- read-model SQL 和 write-model SQL 混在同一 repository。

V3 action:

- unresolved/ambiguous 属于 intent resolution，不应该污染 asset registry。
- registry 只保存真实 asset 和 alias/venue。

### Market Providers

Status: adapter小而清楚，但缺 observation/audit。

Keep:

- `OkxCexClient` / `OkxDexClient` 作为 provider adapter。
- provider calls 不在 request path。

Risk:

- success snapshot 有记录，not_found/error/rate_limited 没有 provider observation 事实。
- CEX universe sync 和 DEX price refresh 共用 worker 状态，但 market semantics 没写入 read model。

V3 action:

- `market_provider_observations` 必须记录所有 provider call outcome。

### Retrieval / API

Status: public contract 已经在走 asset path，但仍是 V2 compatibility。

Risk:

- `/api/asset-flow` source 是 `asset_attributions`。
- `/api/search`、`/asset-posts`、`/asset-social-timeline` 都围绕 asset attribution。
- `/ws` payload 仍发布 `asset_attributions`，没有 intent/resolution。

V3 action:

- `/api/asset-flow` 读 `token_radar_rows`。
- search/posts/timeline 转为 intent-aware。
- WS payload 增加 `token_intents/token_resolutions`，迁移后删除 `asset_attributions`。

### Scoring

Status: backend modules有价值，但没有接到 Token Radar API。

Keep:

- `social_heat_scoring`、`discussion_quality_scoring`、`propagation_scoring`、`timing_scoring`、`opportunity_scoring` 的 ledger 思路可以复用。

Risk:

- `tradeability_score` 仍用旧 token fields：`identity_status == resolved_ca`、`token_id`、`chain/address`，不支持 CEX venue。
- UI 合成了另一套 scoring。

V3 action:

- backend projection builder 统一调用 scoring modules。
- tradeability 改为 venue-specific。

### Frontend

Status: UI功能完整，但业务逻辑越界。

Risk:

- `App.tsx` 1427 行，包含 data mapping、score policy、decision policy、selection state 和 UI。
- `Decision` 类型不支持 `investigate`，使后端语义被压扁。
- `TokenRadarRow` 展示的是前端合成后的 `TokenFlowItem`。

V3 action:

- 前端类型对齐后端 `TokenRadarRow`。
- score/decision 全部服务端拥有。
- App 拆小，映射层只做格式兼容。

### Tests

Status: coverage多，但很多 skipped，且关键测试锁定旧架构。

Observed:

- `uv run pytest`: 162 passed, 115 skipped。
- `npm test`: 55 passed。
- `uv run ruff check .`: passed。

Risk:

- 测试绿不代表生产链路正确；不少测试在确认旧兼容行为。

V3 action:

- 先写 golden corpus，明确旧行为必须失败。
- 对 `$VERSA + 0x2cc0...`、HANTA、BTC、CA-only、provider-not-configured 建 regression tests。

## Compatibility Paths To Delete Or Quarantine

Hard-cut candidates:

- Radar runtime use of `asset_mentions`.
- Radar runtime use of `asset_attributions`.
- `/api/asset-flow` source `asset-flow-v1`.
- frontend `assetFlowRowToTokenItem()` scoring logic.
- `asset_flow_window_snapshots` if not implementing a real writer.
- `asset_attention_buckets` if not implementing a real writer.
- runtime wiring of `TokenRepository` and `TokenSignalRepository`.
- old `MarketObservationWorker` and `token_market_observations`.
- `token_signal_settlement.py` for live evaluation.

Can remain during migration only:

- old token tables as backfill source material;
- `asset_mentions/asset_attributions` as debug/audit legacy views;
- old CLI under archived/debug namespace.

## Recommended Execution Order

1. Add span-aware evidence model and golden corpus tests.
2. Implement token intent builder and stop adding new Radar features to `asset_attributions`.
3. Implement intent resolver with local CA lookup first.
4. Implement provider observation audit and intent re-resolution.
5. Implement materialized `token_radar_rows` projection.
6. Move backend score ledger into projection.
7. Hard-cut API/WS/frontend to V3 contract.
8. Quarantine old token runtime.
9. Delete old compatibility paths after backfill and parity checks.

## Bottom Line

现在的问题不是“解析器不够聪明”，而是 Token Radar 还没有一个稳定的领域主语。只要 runtime 继续把 mention、asset attribution、token_id、frontend score 四个东西混着当主语，价格缺失、symbol 丢失、driver 误标、重复 row 都会反复出现。

V3 必须硬切到：

```text
event -> evidence -> intent -> resolution -> venue market -> radar row -> outcome
```

这条链路足够简单，也足够生产化。关键是不要再给旧 compatibility path 续命。
