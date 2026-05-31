# Token 解析与资产身份闭环生产 Spec

Date: 2026-05-06

## 结论

当前 Token Radar 的根问题不是 cashtag 正则漏掉 `$MIRROR`，而是系统把“推文里出现了一个 token 线索”和“这个线索已经解析成链上 token 且有 chain/address/market snapshot”混成了同一个概念。结果是：

- `$MIRROR` 可以被解析成 symbol mention；
- 原始推文可以通过全文 `mirror` 搜到；
- 但 `$MIRROR` 查询和 Token Radar 只看 resolved token attribution，所以没有本地 alias 或没有 chain/address 时就返回空。

生产级修复必须重做 token 解析链路的领域边界：

```text
Twitter event
-> immutable text facts
-> token mention facts
-> asset identity resolution
-> venue / instrument mapping
-> market observation
-> attribution and radar projections
-> search / radar / timeline
-> resolution and signal quality feedback
```

核心原则：

1. **文本事实永不丢失。** `$SYMBOL`、CA、URL、hashtag、plain keyword 都是可检索事实，不因为未解析成 token 而过滤。
2. **资产身份不等于链上合约。** BTC、TAO、CEX spot/swap、DEX token、unresolved symbol bucket 都是不同类型的 asset identity。
3. **交易场所不等于资产本身。** DEX 用 `chain/address`，CEX 用 `exchange/instId/base/quote/instType`。
4. **Token Radar 先发现注意力，再判断可交易性。** 未解析 symbol 可以上 attention lane，但不能伪装成可交易 resolved asset。
5. **不保留旧兼容运行路径。** 迁移可以从旧事实表 backfill，但 v2 cutover 后 API、projection、tests 只走新资产身份模型。

## 第一性原理

Token Radar 不是一个“链上 token 列表页面”，而是一个社交注意力发现系统。它要回答四个问题：

1. **What was said?** 推文里出现了什么 token 线索？
2. **What could it mean?** 这个线索可能指向哪些资产？
3. **Can it be traded?** 这些资产在哪些场所交易，市场质量如何？
4. **Did the system learn?** 解析、归因、排序是否被后续结果验证或纠错？

这四个问题不能共用一个 `tokens(chain,address)` 表来回答。`tokens` 只能表达 DEX token，不能表达：

- `$BTC`、`$TAO` 这种 CEX-first 资产；
- `$MIRROR` 这种先有社交热度、后解析候选的资产；
- 多链同 symbol 资产；
- 同名 token scam / fork / wrapper；
- plain `mirror` 这种没有 `$` 但全文检索可见的注意力线索。

## Non-Goals

- 不自动交易。
- 不让 LLM 决定 live token facts。
- 不同步全量 DEX token 宇宙。DEX token 数量太大，按 symbol/address/chains on-demand search 并缓存。
- 不把 unresolved symbol 当成可交易 resolved token。
- 不保留旧 `token_aliases -> resolved token only` 的 symbol 搜索语义。
- 不做多套兼容 API。新 API 是 breaking change，前端和测试同步迁移。

## 当前系统必须删除的旧假设

### 1. Symbol 搜索必须先 resolve token

当前 `$SYMBOL` 搜索路径：

```text
parse "$MIRROR" as symbol
-> tokens_for_symbol("MIRROR")
-> no local token_alias
-> unresolved_token_symbol
-> return no events
```

这是错误产品语义。`$MIRROR` 搜索应该首先返回 `$MIRROR` mention events；如果 resolver 有候选，再附带 candidates 和 resolved attribution。

### 2. Token Radar 只展示 chain/address resolved rows

当前 radar 只读取 `token_id IS NOT NULL`、`chain/address IS NOT NULL`、`direct/selected` attribution。这个过滤适合“可交易 DEX token table”，不适合“社交注意力雷达”。

新 radar 必须分两条 lane：

- `resolved_assets`: 已解析、有至少一个可交易 venue 的资产；
- `attention_candidates`: 未解析、模糊、缺市场数据但有社交注意力的 symbol/CA buckets。

### 3. GMGN 是唯一 token identity bootstrap

GMGN public Twitter stream 的 token payload 是重要信号，但不是完整 token universe。GMGN OpenAPI 当前只适合 `chain + address` 的 token info 补充，不能解决 `$MIRROR`、`BTC`、`TAO` 这种 symbol-first 问题。

### 4. `tokens(chain,address)` 是唯一资产模型

`tokens` 表表达的是 DEX token venue，不是 asset identity。新系统中 `tokens` 语义会被 `asset_venues(kind='dex_token')` 替代。

### 5. `gmgn_evm_candidate_chains` 这种未使用配置

未被执行路径使用的解析配置必须删除。链推断只能来自明确事实：CA 格式、explorer URL、文本链 hint、provider 返回结果、人工配置的 chain allowlist。

## 目标数据模型

### `event_entities`

保留为不可变文本事实表。它回答“推文里出现了什么结构化线索”。

职责：

- 存储 CA、cashtag、hashtag、mention、URL/domain、chain hint；
- 不做资产选择；
- 不因为 resolver 失败而删除；
- 支持重新跑 resolver 和 projection。

### `asset_mentions`

替代 `event_token_mentions`。

一条 row 表示一个 event 中出现了一个可能和资产有关的 mention。

关键字段：

```text
mention_id
event_id
mention_type              -- cashtag | ca | plain_symbol | gmgn_payload | url_token
raw_value
normalized_symbol
chain_hint
address_hint
source_entity_id
source                    -- deterministic_extractor | gmgn_payload | backfill
mention_confidence
created_at_ms
```

规则：

- `$MIRROR` 必须写入 `mention_type=cashtag, normalized_symbol=MIRROR`。
- CA 必须写入 `address_hint`，如果没有链，`chain_hint=NULL`，不能伪造 `evm_unknown` 作为可交易链。
- plain `mirror` 默认不写 asset mention，除非来自 watched-account extraction、explicit token context、或用户搜索 projection；全文检索仍走 `events.search_text`。

### `assets`

资产身份表。它回答“这个 mention 代表哪个资产或待解析 bucket”。

关键字段：

```text
asset_id
asset_type                -- dex_asset | cex_asset | unresolved_symbol | ambiguous_symbol
canonical_symbol
display_name
identity_status           -- resolved | unresolved | ambiguous | rejected
confidence
primary_source            -- okx_cex | okx_dex | gmgn | deterministic | operator_review
first_seen_event_id
first_seen_at_ms
updated_at_ms
```

规则：

- `BTC`、`TAO` 可以是 `cex_asset`，不需要 chain/address。
- `$MIRROR` 如果没有可靠候选，创建或复用 `asset_type=unresolved_symbol`。
- 多个高分候选无法选择时，创建或复用 `asset_type=ambiguous_symbol`，并保留 candidate 列表。
- `resolved` 表示资产身份确定，不表示每个 venue 都可交易。

### `asset_aliases`

资产别名表。它回答“哪些文本可以指向这个 asset”。

关键字段：

```text
alias_id
asset_id
alias_type                -- symbol | name | ca | provider_slug
alias_value
normalized_alias
source
confidence
created_at_ms
```

唯一约束：

```text
(alias_type, normalized_alias, asset_id, source)
```

规则：

- 同一个 symbol 可以有多个 asset candidates。
- alias 不负责最终选择，只负责提供候选。

### `asset_venues`

资产交易场所表。它回答“这个 asset 在哪里交易”。

关键字段：

```text
venue_id
asset_id
venue_type                -- dex | cex
provider                  -- gmgn | okx | operator_review
exchange                  -- okx | gmgn | null
chain                     -- dex only
address                   -- dex only
inst_id                   -- cex only, e.g. BTC-USDT or TAO-USDT-SWAP
base_symbol               -- cex only
quote_symbol              -- cex only
inst_type                 -- spot | swap | futures | option
is_active
confidence
source_payload_hash
created_at_ms
updated_at_ms
```

规则：

- DEX venue 的 identity key 是 `dex:{chain}:{address}`。
- CEX venue 的 identity key 是 `cex:{exchange}:{inst_type}:{inst_id}`。
- 一个 asset 可以同时有 OKX spot、OKX swap、多个 DEX chain venues。
- `asset_id` 是雷达聚合主键，`venue_id` 是市场数据主键。

### `asset_resolution_candidates`

候选审计表。它回答“为什么 resolver 选择、拒绝或保持模糊”。

关键字段：

```text
candidate_id
mention_id
asset_id
venue_id
provider
candidate_kind            -- cex_instrument | dex_token | gmgn_payload | local_alias
score
decision                  -- selected | rejected | retained_ambiguous
reasons_json
risks_json
raw_observation_id
created_at_ms
```

规则：

- 所有 provider 返回候选都可审计。
- selected 必须有 reasons。
- ambiguous 不是错误，是可展示状态。

### `asset_attributions`

替代 `event_token_attributions`。

关键字段：

```text
attribution_id
event_id
mention_id
asset_id
venue_id                  -- nullable
attribution_status        -- direct | selected | unresolved | ambiguous | rejected
attribution_weight
confidence
identity_status
reasons_json
risks_json
decision_time_ms
created_at_ms
```

规则：

- unresolved 也必须写 row。
- Radar attention lane 读取 unresolved/ambiguous。
- Resolved lane 只读取 direct/selected 且至少有一个 active venue。
- rejected 保留审计，但默认不展示。

### `asset_market_snapshots`

替代 token-only market snapshots。

关键字段：

```text
snapshot_id
asset_id
venue_id
provider
observed_at_ms
price_usd
market_cap_usd
liquidity_usd
volume_24h_usd
open_interest_usd
holders
price_change_5m_pct
price_change_1h_pct
price_change_24h_pct
source_payload_hash
raw_observation_id
created_at_ms
```

规则：

- DEX snapshot 可以有 holders/liquidity。
- CEX snapshot 可以有 volume/open interest，但没有 holders。
- Tradeability 根据 venue 类型分别评分，不能用 DEX liquidity 逻辑惩罚 CEX spot/swap。

### `asset_resolution_jobs`

异步解析队列表。

关键字段：

```text
job_id
job_type                  -- symbol_resolution | ca_resolution | market_refresh | universe_sync
normalized_symbol
chain_hint
address_hint
status                    -- queued | running | succeeded | failed | exhausted
attempt_count
next_run_at_ms
last_error
created_at_ms
updated_at_ms
```

规则：

- 高频 unresolved symbol 自动排队。
- `MIRROR` 这种新热词可以先进入 attention lane，再由 resolver 补候选。
- job 失败不影响事实入库。

## Provider 策略

### Local Universe First

所有 resolver 先查本地表：

1. exact CA alias；
2. exact symbol alias；
3. active CEX instrument；
4. active DEX venue；
5. unresolved / ambiguous asset bucket。

本地查不到时才调用外部 provider。

### OKX CEX

用途：

- 同步有界 CEX instrument universe；
- 覆盖 BTC、TAO、ETH、SOL 等 CEX-first 资产；
- 提供 spot/swap/futures market snapshots。

官方能力：

- OKX Public Data `GET /api/v5/public/instruments` 可取 open instruments；
- OKX Market Data `GET /api/v5/market/tickers` 可取 tickers；
- OKX Agent Trade Kit 的 `market` module 提供 ticker、orderbook、candles、funding、open interest 等只读行情能力。

设计：

```text
okx_cex_universe_worker
-> /api/v5/public/instruments?instType=SPOT
-> /api/v5/public/instruments?instType=SWAP
-> upsert assets + aliases + asset_venues
```

初始只同步：

- `SPOT`
- `SWAP`

不先做：

- options；
- trading；
- account/private endpoints；
- Agent Trade Kit MCP runtime 集成。

原因：

- 这是 token identity 和行情系统，不是交易系统。
- 直接 HTTP adapter 更容易测试、限流、审计和部署。

### OKX DEX

用途：

- 对 symbol/address 做 DEX 候选搜索；
- 补充 chain/address、liquidity、market cap、holders、price；
- 支持 GMGN 查不到或不准的新链上 token。

官方能力：

- OKX OnchainOS DEX Token Search 支持按 token name、symbol 或 token contract address 搜索；
- symbol/name search 最多返回 100 个相关结果；
- contract address search 返回 exact match；
- response 包含 `chainIndex`、`tokenSymbol`、`tokenContractAddress`、`holders`、`liquidity`、`marketCap`、`price`、`communityRecognized`。

设计：

```text
okx_dex_symbol_resolver
-> GET /api/v6/dex/market/token/search?chains=<allowlist>&search=<symbol>
-> normalize candidates
-> score candidates
-> selected / ambiguous / unresolved
```

KISS 约束：

- 不全量同步 DEX token。
- 只对 attention lane 中超过阈值的 unresolved symbol 调用。
- chain allowlist 来自配置，初始只覆盖当前产品要看的主链。
- provider 原始响应写 raw observation hash，解析结果可重放。

### GMGN

用途：

- GMGN WS payload 仍是强 direct signal；
- GMGN `chain+address` token info 仍可补市场快照；
- 不能作为 symbol-first resolver 的唯一来源。

设计：

- GMGN payload 中自带 chain/address/symbol 时，创建 DEX venue candidate；
- GMGN OpenAPI 只在已有 chain/address 时查 market info；
- 不用 GMGN unknown result 过滤掉 social mention。

## Resolution Policy

Resolver 必须 deterministic，可测试，可解释。

### Input

```text
asset_mentions row
+ current event text facts
+ local aliases
+ provider candidates
+ market snapshots if already available
```

### Decision Order

1. **Exact CA with chain hint**
   - 直接生成或复用 `dex_asset + dex venue`。
   - status: `direct`。

2. **Exact CA without chain hint**
   - 查 local CA aliases；
   - 查 OKX DEX contract search across allowlist；
   - 单一 exact match 可 selected；
   - 多个 match 保持 ambiguous；
   - 无 match 保持 unresolved CA bucket。

3. **GMGN payload with chain/address**
   - 生成或复用 DEX venue；
   - 与 event mention 建 direct attribution。

4. **Symbol with local exact aliases**
   - 如果只有一个 high-confidence asset，selected；
   - 如果多个 candidates，按 resolver score 选择或 ambiguous；
   - 不允许因为 ambiguous 返回空。

5. **Symbol with CEX exact instrument**
   - 如果 symbol 是 OKX CEX base currency 且没有更强 DEX/CA evidence，创建或复用 `cex_asset`；
   - BTC、TAO 这类资产优先走 CEX identity。

6. **Symbol with OKX DEX candidates**
   - 根据 exact symbol、communityRecognized、liquidity、marketCap、holders、chain hint、GMGN corroboration 打分；
   - 高于阈值且与第二名拉开差距才 selected；
   - 否则 ambiguous。

7. **No candidate**
   - 创建或复用 `unresolved_symbol`；
   - attribution_status=`unresolved`；
   - 进入 attention lane。

### Candidate Score

初始 resolver score：

```text
score =
  35 exact_symbol_match
  + 20 source_strength
  + 15 chain_hint_match
  + 10 community_recognized
  + 10 liquidity_depth_bucket
  + 5 holder_bucket
  + 5 market_cap_sanity
  - 30 suspicious_symbol_mismatch
  - 20 thin_liquidity
  - 20 stale_or_missing_market
```

Selection rule：

```text
selected if top_score >= 70 and top_score - second_score >= 15
ambiguous if top_score >= 50 but margin < 15
unresolved otherwise
```

这些阈值是 deterministic policy，不是模型概率。后续可以通过 closure report 调整，但每次调整必须 bump `resolver_policy_version`。

## Ingest Pipeline

### Step 1: Normalize Twitter Event

输入 GMGN public Twitter stream frame。

输出：

- `raw_frames`
- `events`
- `search_text`
- `cashtags_json`

失败策略：

- frame parse 失败只影响当前 frame；
- raw frame 保留；
- event 正常化失败写 ingest error audit。

### Step 2: Extract Text Facts

输入 `events.content_text` 和 quoted/reference text。

输出 `event_entities`：

- CA；
- cashtag；
- hashtag；
- mention；
- URL/domain；
- chain hints。

规则：

- 正则提取只做事实抽取，不做 token 选择；
- cashtag uppercase normalization；
- plain word 不进入 asset mention，除非明确来源给出 token intent。

### Step 3: Build Asset Mentions

输入 `event_entities + GMGN token payload`。

输出 `asset_mentions`。

规则：

- 每个 cashtag 至少一条 asset mention；
- 每个 CA 至少一条 asset mention；
- GMGN payload 可以创建 `mention_type=gmgn_payload`；
- mention 写入和 resolver 解耦，resolver 失败不能回滚 mention。

### Step 4: Resolve Asset Identity

输入 `asset_mentions`。

同步处理：

- exact local CA；
- GMGN payload direct；
- local alias exact hit；
- unresolved bucket upsert。

异步处理：

- OKX CEX universe sync；
- OKX DEX token search；
- market refresh；
- ambiguous candidate re-evaluation。

输出：

- `assets`
- `asset_aliases`
- `asset_venues`
- `asset_resolution_candidates`
- `asset_attributions`
- `asset_resolution_jobs`

### Step 5: Observe Market

输入 selected/direct attributions 和 active venues。

输出 `asset_market_snapshots`。

规则：

- DEX venue 用 GMGN/OKX DEX 补 price/liquidity/holders/market cap；
- CEX venue 用 OKX market tickers/candles/open interest；
- snapshot 缺失是 data health risk，不删除 attribution。

### Step 6: Build Projections

输出：

- `asset_attention_buckets`
- `asset_attention_bucket_authors`
- `asset_flow_window_snapshots`
- `asset_resolution_health_snapshots`

Projection 分类：

- resolved lane；
- attention candidate lane；
- unresolved/ambiguous health；
- provider freshness。

规则：

- projection 可删可重建；
- API 不做 raw fallback；
- projection stale 时显式返回 stale 状态。

### Step 7: Serve APIs

#### `$SYMBOL` Search

新语义：

```text
GET /api/search?q=$MIRROR
```

必须返回：

```json
{
  "ok": true,
  "query": {
    "kind": "symbol",
    "symbol": "MIRROR"
  },
  "resolution": {
    "status": "resolved | unresolved | ambiguous",
    "candidates": []
  },
  "items": [
    {
      "match_type": "asset_mention | asset_attribution | fts",
      "event": {}
    }
  ]
}
```

规则：

- 没有 candidate 也返回 asset mention events；
- ambiguous 也返回 events 和 candidates；
- resolved 时优先返回 selected/direct attribution events，再补 mention events；
- 不再返回 `unresolved_token_symbol` 空结果。

#### Token Radar

新 response 顶层：

```json
{
  "ok": true,
  "data": {
    "resolved_assets": [],
    "attention_candidates": [],
    "projection": {
      "status": "fresh | stale | missing",
      "version": "asset-flow-v1"
    }
  }
}
```

`attention_candidates` row 必须包含：

```json
{
  "asset": {
    "asset_id": "asset:unresolved:MIRROR",
    "symbol": "MIRROR",
    "identity_status": "unresolved"
  },
  "attention": {
    "mentions_5m": 0,
    "mentions_1h": 0,
    "unique_authors": 0,
    "watched_mentions": 0
  },
  "resolution": {
    "status": "queued | running | unresolved | ambiguous | resolved",
    "last_checked_at_ms": null,
    "candidates": []
  },
  "decision": "investigate | watch | discard"
}
```

#### Token Timeline

Timeline accepts `asset_id`, not only `token_id/chain/address`.

```text
GET /api/asset-social-timeline?asset_id=...
```

规则：

- unresolved asset 也能打开 timeline；
- resolved asset timeline 可以 show venue-specific market overlay；
- CEX asset 用 CEX price overlay；
- DEX asset 用 DEX price/liquidity overlay。

## Production Migration

这次是 breaking migration，不做长期兼容层。为了生产可控，分阶段上线，但每个阶段都必须有明确 exit criteria。

### Phase 0: Spec And Audit

交付：

- 本 spec；
- old path inventory；
- new schema migration draft；
- tests to delete / tests to rewrite list。

Exit criteria：

- 所有当前过滤 unresolved symbol 的路径列清楚；
- `$MIRROR`、`BTC`、`TAO`、unknown-chain CA 都有目标行为。

### Phase 1: Schema And Provider Foundation

交付：

- 新 asset schema；
- `AssetRepository`；
- `OkxCexClient`；
- `OkxDexClient`；
- provider raw observation audit；
- `ops sync-okx-cex-universe`；
- `ops resolve-asset-symbol --symbol MIRROR`。

Exit criteria：

- `BTC`、`TAO` 可作为 CEX assets 入库；
- `$MIRROR` 可创建 unresolved asset；
- OKX DEX token search candidate 可写入 audit；
- 旧 `TokenRepository.resolve_symbol()` 不再被新 ingest path 调用。

### Phase 2: Ingest V2 Cutover

交付：

- `AssetMentionBuilder`；
- `AssetResolver`；
- `AssetAttributionBuilder`；
- ingest path 写 `asset_mentions/asset_attributions`；
- 旧 `event_token_mentions/event_token_attributions` 写入逻辑删除。

Exit criteria：

- 新 event ingest 不再写 token-only attribution tables；
- `$MIRROR` event 必然有 `asset_mentions` 和 unresolved/selected attribution；
- GMGN payload direct event 必然有 resolved DEX asset attribution；
- unknown-chain CA 不丢失，进入 unresolved/ambiguous CA state。

### Phase 3: API And Projection Cutover

交付：

- `$symbol` search 新语义；
- `asset-flow` projection；
- `asset-social-timeline`；
- frontend type migration；
- 新增 `/api/asset-flow`，删除旧 `/api/token-flow` route，不保留 alias。

Exit criteria：

- `$MIRROR` 搜索返回 mention events；
- `mirror` 全文搜索仍返回 FTS events；
- BTC/TAO 可出现在 resolved CEX asset lane；
- 未解析 symbol 可出现在 attention candidate lane；
- resolved DEX token 可出现在 resolved asset lane。
- 前端只调用 `/api/asset-flow`，代码库没有 `/api/token-flow` runtime route。

### Phase 4: Backfill And Cleanup

交付：

- 从 `events/event_entities` backfill `asset_mentions`；
- 从旧 `tokens/token_aliases/token_market_snapshots` 迁移 DEX venues 和 snapshots；
- 删除旧 token-only services 和 tests；
- 删除旧 tables 或标记为 archived after backup。

Exit criteria：

- API、worker、tests 没有 `TokenIdentityResolver`、`event_token_attributions`、`token_aliases` 运行依赖；
- `rg "unresolved_token_symbol"` 只允许出现在 migration notes，不允许出现在 runtime；
- `rg "evm_unknown"` 不允许出现在 asset resolution runtime；
- old tables 不再被 app runtime 查询。

## Testing Strategy

### Golden Corpus

必须建立 fixture：

1. `$MIRROR` cashtag event，无 local alias。
   - Expected: search `$MIRROR` returns event; radar attention lane has unresolved asset.

2. `mirror` plain text event，无 cashtag。
   - Expected: FTS search returns event; asset mention 不自动创建。

3. `$BTC` event。
   - Expected: resolves to CEX asset with OKX spot/swap venues if universe synced.

4. `$TAO` event。
   - Expected: resolves to CEX asset, not forced DEX chain/address.

5. Solana CA event。
   - Expected: exact DEX asset attribution.

6. EVM CA without chain hint。
   - Expected: unresolved/ambiguous CA state; not dropped.

7. Same symbol with multiple DEX candidates。
   - Expected: ambiguous search with candidates and events.

8. GMGN payload direct token event。
   - Expected: resolved DEX asset and venue created.

### Unit Tests

- entity extraction writes text facts only；
- asset mention builder creates mention rows for cashtag/CA/GMGN payload；
- resolver policy decisions are deterministic；
- OKX response adapters handle missing fields；
- ambiguous candidates do not become selected；
- unresolved mentions still create attribution rows。

### Integration Tests

- ingest event -> asset mention -> attribution -> search；
- ingest event -> projection -> radar lane；
- OKX CEX universe sync -> BTC/TAO resolution；
- OKX DEX symbol search -> candidate audit；
- market snapshot refresh for CEX and DEX venue types。

### Regression Tests To Flip

Old expectations to delete:

- unresolved `$DOG` search returns empty；
- unknown-chain CA cannot appear in any token flow result；
- symbol query must have exactly one `token_aliases` row。

New expectations:

- unresolved symbol search returns mention evidence；
- unknown-chain CA appears in attention candidate lane；
- ambiguous symbol query returns candidates and evidence；
- resolved lane remains strict about active venue and market health。

## Ops And Observability

### Commands

Add:

```bash
uv run parallax ops sync-okx-cex-universe --inst-type SPOT --inst-type SWAP
uv run parallax ops resolve-asset-symbol --symbol MIRROR
uv run parallax ops asset-resolution-health --window 24h
uv run parallax ops audit-asset-attribution --event-id ...
uv run parallax ops backfill-asset-mentions --since-ms ...
uv run parallax ops rebuild-asset-flow --window 1h
```

### Health Metrics

Expose:

- unresolved symbol mention rate；
- ambiguous symbol mention rate；
- provider error rate by provider；
- provider freshness by universe/snapshot type；
- top unresolved symbols by 5m/1h attention；
- selected candidate override rate；
- market snapshot missing rate by venue type；
- search `$symbol` zero-result rate。

`$symbol` zero-result rate should approach zero for events that contain that cashtag. If it rises, that is a regression.

### Audit Views

Add read services:

- `asset_resolution_trace(mention_id)`；
- `asset_candidates_for_symbol(symbol)`；
- `events_for_asset(asset_id)`；
- `unresolved_attention_leaders(window)`。

## Deletion List

Runtime code to remove or replace:

- `TokenIdentityResolver` -> `AssetResolver`；
- `TokenRepository.resolve_symbol()` runtime use -> `AssetRepository.candidates_for_symbol()`；
- `SearchService` symbol path that returns `unresolved_token_symbol`；
- `RollingTokenFlow` hard filter requiring `token_id/chain/address` for all radar rows；
- `TokenFlowService` identity model that assumes every row is DEX token；
- `token_posts` and `token_social_timeline` APIs that only accept `token_id/chain/address`；
- `market_observation_worker` path that only refreshes selected/direct DEX attributions；
- unused `gmgn_evm_candidate_chains` setting。

Tables to retire after migration and backup:

- `event_token_mentions`；
- `event_token_attributions`；
- `tokens` as identity table；
- `token_aliases`；
- token-only market snapshot tables, after migration into `asset_market_snapshots`。

删除动作在 Phase 3 cutover 验证后执行。迁移期间旧表可以作为 backfill source material 存在，但 app runtime 不能继续使用旧 fallback path。

## Definition Of Done

This project is done only when all statements are true:

1. Searching `$MIRROR` returns the same class of events that `mirror` FTS can see when the original text contains `$MIRROR`。
2. `$MIRROR` without provider match appears as unresolved attention candidate, not as empty result。
3. BTC and TAO resolve as CEX assets without chain/address。
4. DEX CA events resolve to DEX venues when chain/address are known。
5. Unknown-chain CA events are retained as attention candidates until resolved or rejected。
6. Token Radar response separates `resolved_assets` from `attention_candidates`。
7. No runtime path requires every asset to have `chain/address`。
8. No runtime path silently drops unresolved/ambiguous mentions。
9. Resolver decisions are visible through candidate audit rows。
10. Market snapshots are venue-specific and do not force CEX into DEX fields。
11. Old token-only symbol search behavior is deleted。
12. Old tests that expected unresolved symbol empty results are replaced。
13. Ops can explain why a mention is resolved, unresolved, ambiguous, or rejected。
14. Projection freshness is explicit。
15. The full chain can be rebuilt from raw frames, events, event_entities, provider observations, and asset resolution audit。

## Source References

- OKX Agent Trade Kit: https://github.com/okx/agent-trade-kit
- OKX CEX Public Data docs: https://www.okx.com/docs-v5/en/
- OKX DEX Token Search docs: https://web3.okx.com/onchainos/dev-docs-v5/dex-api/dex-market-token-search
- onchain_os OKX provider reference: `/Users/qinghuan/Documents/code/onchain_os/src/onchain_signal/providers/okx_client.py`
- onchain_os OKX adapter reference: `/Users/qinghuan/Documents/code/onchain_os/src/onchain_signal/providers/okx_adapter.py`
