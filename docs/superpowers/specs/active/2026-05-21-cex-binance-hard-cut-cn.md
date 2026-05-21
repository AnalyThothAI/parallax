# CEX Binance Hard Cut Spec

日期：2026-05-21
状态：active spec
范围：把项目内所有 CEX identity/routing/quote/candle/OI/radar 链路完全切到 Binance USDT 永续；移除 OKX CEX runtime、配置、CLI、测试 fixture 和旧 DB 数据。

## 结论

CEX 模块做 hard cut：**Binance 是唯一 CEX venue，默认且唯一交易范围是 USDT perpetual**。

不做兼容层：

- 不保留 OKX CEX fallback。
- 不做 OKX/Binance provider mux。
- 不保留 `sync-okx-cex-universe`。
- 不保留 `OkxCexClient` 作为当前 runtime dependency。
- 不保留 OKX CEX `price_feeds` / `market_ticks` / capture tier 数据。
- 不让 read path 在 Binance 缺数据时回退 OKX。

边界：

- OKX DEX discovery / quote / WS 不是 CEX 模块，是否保留由 DEX 链路决定。它可以继续存在，但必须从命名和 wiring 上与 CEX 完全拆开。
- 历史 Alembic migration 里出现 `okx_cex` 字符串可以保留，因为 migration 是历史事实；当前 runtime、active docs、default config、tests 不应再依赖 OKX CEX。

## 为什么要 hard cut

之前的 mux 方案不优雅，问题在于：

- 产品语义混乱：CEX route 可能是 OKX，但 derivatives/OI/CoinGlass 默认是 Binance。
- 代码复杂：所有 CEX read/write path 都要携带 provider 分发，且大量旧测试继续围绕 `okx_cex_rest`。
- 数据混杂：`cex_tokens` 是 venue-neutral identity，但 `price_feeds` 和 `market_ticks` 混入 OKX spot/swap 后，详情页、Pulse evidence、Radar target 的 venue 解释成本上升。
- 后续产品目标是 Binance USDT perp market board；OKX CEX coverage 不是核心能力。

Hard cut 后：

```text
Binance USD-M USDT perpetual universe
  -> cex_tokens
  -> price_feeds(provider='binance', feed_type='cex_swap', quote_symbol='USDT')
  -> market_ticks(source_provider='binance_cex_rest')
  -> CEX Token Case / live market / event anchors
  -> cex_oi_radar_runs + cex_oi_radar_rows
  -> CoinGlass top-K enrichment using Binance instrument
```

这样 CEX 页面、Token Case、Pulse evidence、OI/radar board、CoinGlass instrument 全部指向同一 venue。

## 当前 CEX 依赖面

当前 OKX CEX 不是单点依赖，hard cut 需要处理这些面：

| 面 | 当前状态 | Hard cut 后 |
|---|---|---|
| Config | `providers.okx.cex_base_url`, `cex_sync_enabled`, `cex_inst_types` | 删除 OKX CEX config；Binance 增加 USD-M futures config |
| Provider wiring | `OkxProviderBundle` 同时装 CEX + DEX | 拆掉 bundle 中 CEX 字段，只保留 OKX DEX wiring |
| Runtime provider slots | `sync_cex_market`, `message_cex_market` | 改成单一 `binance_cex_market` 或 `cex_market`，实现只有 Binance |
| CLI | `ops sync-okx-cex-universe` | 删除；新增 `ops sync-binance-usdt-perp-universe` |
| Sync service | `asset_market_sync.sync_cex_routes` 默认 OKX ticker shape | 改成 Binance explicit route sync，不从 native id 猜 base/quote |
| Market tick poll | CEX source 固定 `okx_cex_rest` | 固定 `binance_cex_rest` |
| Event anchor CEX backfill | 注释和 source 指向 OKX CEX REST | 改为 Binance CEX REST |
| CEX candles | `okx_cex_candles` | `binance_cex_candles` |
| Registry preference | spot 优先、OKX 数据可能被选中 | Binance USDT swap 是唯一 preferred CEX feed |
| DB data | OKX CEX `price_feeds`, `market_ticks`, `token_capture_tier` | 删除 |
| Tests | 大量 fixture 使用 `okx_cex_rest` | 改成 Binance fixture |

## 目标状态

### Providers

新增或正式化：

```text
src/gmgn_twitter_intel/integrations/binance/usdm_futures_client.py
src/gmgn_twitter_intel/app/runtime/provider_wiring/binance.py
```

Binance CEX provider 负责：

- `exchangeInfo`：USDT perpetual universe。
- `ticker/24hr`：ticker / volume。
- `premiumIndex`：mark price / current funding。
- `openInterestHist`：全市场 OI board 的 OI history。
- `ticker(symbol)`：`MarketTickPollWorker` CEX target quote。
- `candles(symbol, interval, limit)`：CEX Token Case / target chart。

删除或迁移：

- 删除 `OkxCexMarketProvider`。
- 删除 `OkxCexClient` runtime use。
- 如果 `integrations/okx/dex_client.py` 复用了 `okx/cex_client.py` 的 HTTP helper，先把共享 helper 移到 `integrations/okx/http_utils.py`，再删除 CEX client。
- `OkxProviderBundle` 改名或拆掉，不再有 `sync_cex_market` / `message_cex_market` 字段。

### Config

`providers.okx` 只保留 DEX 字段：

```yaml
providers:
  okx:
    dex_base_url: "https://web3.okx.com"
    dex_chain_indexes: ["501", "1", "56", "8453", "607"]
    dex_ws_url: "wss://wsdex.okx.com/ws/v6/dex"
    dex_api_key:
    dex_secret_key:
    dex_passphrase:
    timeout_seconds: 15
```

`providers.binance` 拥有 CEX profile + USD-M futures：

```yaml
providers:
  binance:
    enabled: true
    web3_base_url: "https://web3.binance.com"
    cex_profile_base_url: "https://www.binance.com"
    usdm_futures_base_url: "https://fapi.binance.com"
    timeout_seconds: 15
    cex_universe_quote_symbol: "USDT"
    cex_universe_contract_type: "PERPETUAL"
```

说明：

- 不复用 `cex_base_url` 同时表达 profile 和 futures，避免把 profile client 指到 futures host。
- `config` 命令不再展示 OKX CEX 配置。
- 默认配置里不再有 `okx.cex_*`。

### Registry

`cex_tokens` 继续保留，含义改为“Binance USDT perpetual backed CEX token identity”。

`price_feeds` 的 CEX 当前集合只允许：

```text
provider = "binance"
feed_type = "cex_swap"
quote_symbol = "USDT"
native_market_id = Binance USD-M symbol, e.g. "BTCUSDT"
```

`find_preferred_cex_pricefeed(base_symbol)` 改为：

```sql
SELECT *
FROM price_feeds
WHERE subject_type = 'CexToken'
  AND base_symbol = :base_symbol
  AND provider = 'binance'
  AND feed_type = 'cex_swap'
  AND quote_symbol = 'USDT'
  AND status = 'canonical'
ORDER BY updated_at_ms DESC, native_market_id ASC
LIMIT 1
```

不再排序 spot/swap/provider fallback。没有 Binance USDT perp feed 就返回 `None`。

`DeterministicTokenResolver` policy：

- Symbol-only `$BTC` 可解析到 `cex_token:BTC`，前提是 Binance USDT perp feed 存在。
- Explicit exchange lookup 只支持 Binance。`exchange=okx` 不走 OKX CEX，也不造 OKX route。
- OKX-only CEX symbol 在 hard cut 后应 unresolved 或落到 DEX identity，不保留旧 CEX identity。

### Market facts

`MarketTickSourceProvider` 改为：

```python
Literal["okx_dex_ws", "okx_dex_rest", "gmgn_dex_quote", "binance_cex_rest"]
```

数据库 `market_ticks.source_provider` check constraint 同步改为：

```sql
CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'gmgn_dex_quote', 'binance_cex_rest'))
```

所有 CEX writes：

- `target_type='cex_symbol'`
- `target_id='binance:<native_market_id>'`
- `exchange='binance'`
- `instrument='<native_market_id>'`
- `source_provider='binance_cex_rest'`

不允许写 `okx_cex_rest`。

### CEX universe sync

新增：

```text
uv run gmgn-twitter-intel ops sync-binance-usdt-perp-universe --execute
```

语义：

1. 调 Binance USD-M `exchangeInfo`。
2. filter `status=TRADING`, `contractType=PERPETUAL`, `quoteAsset=USDT`。
3. Upsert `cex_tokens`。
4. Upsert `price_feeds(provider='binance', feed_type='cex_swap', quote_symbol='USDT')`。
5. 删除或 demote 不在 Binance USDT perp universe 的 `cex_tokens`，不能留 OKX-only CEX identity。

`--dry-run` 输出：

- `binance_usdt_perp_seen`
- `cex_tokens_to_insert`
- `cex_tokens_to_delete`
- `pricefeeds_to_insert`
- `old_okx_cex_rows_to_delete`
- `duration_ms`

### 全 Binance OI/radar board

沿用 Binance-only board 方向，但删除 mux/OKX 术语：

- Universe 来源只读 Binance-backed `price_feeds`。
- Board worker 不需要知道 OKX。
- CoinGlass enrichment 使用 `exchange='Binance'` + `symbol=base_symbol`。
- Board row 的 `target_id` 永远是 `binance:<native_market_id>`。

## DB 清理策略

这是 destructive cleanup，需要维护窗口和备份。不要做“标记 legacy 后继续兼容”的中间状态。

Implementation note：具体执行以 hard-cut implementation plan 为准。由于 Docker Compose 会先运行 `migrate` 再启动 `app`，Alembic 只能做 additive / `NOT VALID` 约束前置；真正 provider-dependent 的删除必须由 `ops cex-binance-hard-cut-cleanup --dry-run/--execute` 执行。`token_intent_resolutions` 不能就地把 current row 改空，必须按现有 lifecycle supersede 旧 current row，再插入 Binance-repointed 或 NIL current row。

### 删除范围

必须清掉：

```sql
-- OKX CEX routes
DELETE FROM price_feeds
WHERE provider = 'okx'
  AND feed_type LIKE 'cex_%';

-- OKX CEX ticks
DELETE FROM market_ticks
WHERE target_type = 'cex_symbol'
  AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest');

-- OKX CEX capture tiers
DELETE FROM token_capture_tier
WHERE target_type = 'cex_symbol'
  AND target_id LIKE 'okx:%';

-- Legacy CEX observations if still present in partitioned price_observations
DELETE FROM price_observations
WHERE provider IN ('okx_cex', 'okx')
   OR pricefeed_id LIKE 'pricefeed:cex:okx:%';
```

但实际 migration 顺序不能这样直接执行，因为 FK 和 current resolution 引用需要先处理。

### 安全顺序

1. 停止 app workers，确保没有 OKX CEX writer 继续写。
2. 用新代码同步 Binance USDT perp universe，确认 Binance `price_feeds` 数量大于最低阈值，例如 400。
3. 失效 current CEX resolutions 中的 OKX route，以及不再有 Binance USDT perp feed 的 CEX target。这里不能直接 `UPDATE` current row：
   - 如果同一个 `CexToken` 已有 Binance USDT perp feed，则 supersede 旧 current resolution，再插入新 current resolution，指向 Binance pricefeed，并追加 reason `cex_binance_hard_cut_repointed`。
   - 如果没有 Binance USDT perp feed，则 supersede 旧 current resolution，再插入 NIL current resolution，追加 reason `cex_binance_hard_cut_removed`。
   - 具体 SQL CTE 在 implementation plan 的 cleanup command 中维护，必须在一个 advisory-lock transaction 内执行。

4. 删除可重建 read models：

```sql
DELETE FROM token_radar_rows
WHERE target_type = 'CexToken'
   OR pricefeed_id LIKE 'pricefeed:cex:okx:%';
```

5. 对引用 OKX CEX tick 的 `enriched_events` 先改成 unavailable，再删 tick：

```sql
UPDATE enriched_events
SET tick_id = NULL,
    tick_lag_ms = NULL,
    capture_method = 'unavailable',
    capture_reason = 'cex_okx_removed'
WHERE tick_id IN (
  SELECT tick_id
  FROM market_ticks
  WHERE target_type = 'cex_symbol'
    AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
);
```

6. 删除 OKX CEX `market_ticks`。
7. 删除 OKX CEX `token_capture_tier`。
8. 删除 OKX CEX `price_observations`。
9. 删除 OKX CEX `price_feeds`。
10. 删除不再有 Binance USDT perp feed 的 `cex_tokens`：

```sql
DELETE FROM cex_tokens
WHERE NOT EXISTS (
  SELECT 1
  FROM price_feeds
  WHERE price_feeds.subject_type = 'CexToken'
    AND price_feeds.subject_id = cex_tokens.cex_token_id
    AND price_feeds.provider = 'binance'
    AND price_feeds.feed_type = 'cex_swap'
    AND price_feeds.quote_symbol = 'USDT'
    AND price_feeds.status = 'canonical'
);
```

11. Drop/recreate `market_ticks.source_provider` check，拒绝 `okx_cex_rest`。
12. 启动 `resolution_refresh` / `token_radar_projection` 重建 current read surface。

### 关于历史事实

这个 spec 明确选择删除 OKX CEX 历史 market data，而不是保留审计兼容。代价是：旧事件的 OKX CEX anchor tick 会变成 unavailable。收益是：数据库和产品层不再混有非目标 venue。

如果需要审计备份，使用 DB backup 或一次性 CSV export，不在生产表保留 legacy rows。

## 代码删除清单

删除：

- `src/gmgn_twitter_intel/integrations/okx/cex_client.py`
- `OkxCexMarketProvider`
- `okx_cex_market(...)`
- `sync-okx-cex-universe` parser + command handler
- `settings.okx_cex_base_url`
- `settings.okx_cex_sync_enabled`
- `settings.okx_cex_inst_types`
- `OkxProviderBundle.sync_cex_market`
- `OkxProviderBundle.message_cex_market`
- runtime constants `CEX_SOURCE_PROVIDER = "okx_cex_rest"`
- docs 中当前架构描述的 OKX CEX backfill
- tests 中当前 fixture 的 `okx_cex_rest` CEX 语义

替换：

- `message_cex_market` -> `cex_market`，实现只有 Binance。
- `sync_cex_routes(...)` -> `sync_binance_usdt_perp_universe(...)` 或 explicit `CexRoute` sync。
- `okx_cex_candles` -> `binance_cex_candles`。
- `okx_cex_rest` -> `binance_cex_rest`。

保留但拆名：

- OKX DEX discovery/quote/ws。
- OKX DEX source providers：`okx_dex_ws`, `okx_dex_rest`。
- Historical migrations 中的 OKX CEX strings。

## Worker 与公共面影响

### Worker

| Worker | 改动 |
|---|---|
| `market_tick_poll` | CEX branch 调 Binance provider，写 `binance_cex_rest` |
| `event_anchor_backfill` | CEX backfill 调 Binance provider |
| `token_capture_tier` | CEX target id 只会是 `binance:*` |
| `live_price_gateway` | 只发布 Binance CEX ticks |
| `token_radar_projection` | 重建后 CEX target pricefeed 只来自 Binance |
| `pulse_candidate` | evidence 中 CEX market provider 只会是 Binance |
| `cex_oi_radar_board` | universe 来源是 Binance CEX feeds |

### HTTP / WS / CLI

- `/api/live-market` CEX response provider 变为 `binance_cex_rest`。
- Token Case CEX market block 显示 Binance USDT perpetual。
- Search / target resolution 不再出现 OKX CEX pricefeed。
- CLI 删除 `sync-okx-cex-universe`，新增 `sync-binance-usdt-perp-universe`。
- `config` 输出不再展示 OKX CEX settings。

### Frontend

- CEX label 默认 Binance Perp / Binance USDT Perp。
- 不展示 OKX CEX venue。
- 旧 rows 如果因清理变 stale/unavailable，应显示 unavailable，不显示 OKX fallback。

## Rollout

这是 breaking cleanup/migration，不按滚动兼容发布。推荐维护窗口：

1. 备份 DB 和 `~/.gmgn-twitter-intel/config.yaml`。
2. 执行 standalone config migration，移除旧 OKX CEX config keys，添加 Binance futures config。
3. 停止 app / workers。
4. 构建 Docker image，并验证 `coinglass-cli --help` / `coinglass-cli canary`。
5. 执行 additive migration：只添加 Binance CEX source provider 约束，使用 `NOT VALID`，不清库。
6. 运行 Binance universe sync dry-run，确认 active USDT perp 数量合理。
7. 执行 Binance universe sync。
8. 执行 `ops cex-binance-hard-cut-cleanup --dry-run`，确认 counts 合理。
9. 执行 `ops cex-binance-hard-cut-cleanup --execute`，清理 OKX CEX rows 并 validate constraint。
10. 启动 app。
11. 运行 rebuild：
   - `resolution_refresh` catch-up。
   - `token_radar_projection` run once。
   - `token_capture_tier` run once。
   - `market_tick_poll` run once。
12. 验证 DB 不再有 OKX CEX rows。
13. 打开 CEX Token Case / live-market / Pulse evidence smoke。

不提供 runtime OKX fallback。失败恢复走 DB backup + code rollback，不是在新代码里保留旧路径。

## 验收标准

### Code

- `rg "OkxCex|okx_cex_rest|sync-okx-cex-universe|cex_inst_types|cex_sync_enabled"` 在当前 runtime code 和 tests 中无命中；历史 migrations 允许。
- `integrations/okx/dex_client.py` 不再 import `integrations.okx.cex_client`。
- `MarketTickSourceProvider` 包含 `binance_cex_rest`，不包含 `okx_cex_rest`。
- `AssetMarketProviders` 没有 `sync_cex_market` / `message_cex_market` 双 CEX slot。
- `MarketCandlesService` CEX source 是 `binance_cex_candles`。
- CLI help 没有 `sync-okx-cex-universe`，有 `sync-binance-usdt-perp-universe`。

### DB

以下查询必须返回 0：

```sql
SELECT count(*) FROM price_feeds WHERE provider = 'okx' AND feed_type LIKE 'cex_%';
SELECT count(*) FROM market_ticks WHERE source_provider = 'okx_cex_rest';
SELECT count(*) FROM market_ticks WHERE target_type = 'cex_symbol' AND target_id LIKE 'okx:%';
SELECT count(*) FROM token_capture_tier WHERE target_type = 'cex_symbol' AND target_id LIKE 'okx:%';
SELECT count(*) FROM price_observations WHERE provider IN ('okx_cex', 'okx') OR pricefeed_id LIKE 'pricefeed:cex:okx:%';
SELECT count(*)
FROM token_intent_resolutions AS tir
WHERE tir.target_type = 'CexToken'
  AND NOT EXISTS (
    SELECT 1 FROM cex_tokens WHERE cex_tokens.cex_token_id = tir.target_id
  );
```

以下查询必须返回正数：

```sql
SELECT count(*)
FROM price_feeds
WHERE provider = 'binance'
  AND feed_type = 'cex_swap'
  AND quote_symbol = 'USDT'
  AND status = 'canonical';
```

### Product

- `$BTC` 解析到 `cex_token:BTC` 且 preferred feed 是 `binance:BTCUSDT`。
- CEX live market tick 写入 `target_id='binance:BTCUSDT'` 和 `source_provider='binance_cex_rest'`。
- Token Case 不展示 OKX CEX。
- Pulse evidence packet 中 CEX `venue_ref` / `source_provider` 指向 Binance。
- OI/radar board row 的 `target_id` 永远是 `binance:<symbol>USDT`。

## 测试计划

- Unit：Binance exchangeInfo parser 只接收 `TRADING + PERPETUAL + USDT`。
- Unit：`1000BONKUSDT` 使用 `baseAsset/quoteAsset`，不从字符串猜 base。
- Unit：Binance universe sync 插入 `cex_tokens` + `price_feeds`，删除非 Binance-backed `cex_tokens`。
- Unit：`find_preferred_cex_pricefeed` 只返回 Binance USDT swap。
- Unit：explicit `exchange=okx` 不产生 OKX CEX pricefeed。
- Unit：market tick poll CEX branch 写 `binance_cex_rest`。
- Unit：event anchor CEX backfill 写 `binance_cex_rest`。
- Unit：CEX candles source 是 `binance_cex_candles`。
- Integration：hard-cut cleanup 删除 OKX CEX rows，处理 `enriched_events.tick_id` FK。
- Integration：Token Radar projection rebuild 后 CEX rows 只引用 Binance pricefeeds。
- Architecture：当前 runtime code 禁止 import `integrations.okx.cex_client`。
- CLI：`sync-binance-usdt-perp-universe --dry-run` 输出计划，不写 DB。

## 风险

| 风险 | 影响 | 处理 |
|---|---|---|
| Binance universe sync 失败后清库 | CEX identity 暂空 | 维护窗口先 dry-run，低于阈值则 abort |
| 删除 OKX CEX ticks 影响旧 event anchors | 旧 CEX anchor 变 unavailable | 接受；这是 hard cut 的数据代价 |
| OKX-only symbols 不再解析为 CEX | 覆盖面下降 | 接受；产品目标是 Binance USDT perp |
| DEX client 依赖 OKX CEX helper | 删除 CEX client 时破坏 DEX | 先提取 shared `okx/http_utils.py` |
| 测试大面积变红 | fixture 旧 venue 太多 | 批量迁移到 Binance fixture，不保留旧 fixture |
| Rollback 没有 runtime fallback | 恢复慢 | DB backup + code rollback 是唯一 rollback 路径 |

## 最终判断

这个 hard cut 比 mux 方案更干净：CEX 是 Binance，DEX 可以继续是 GMGN/OKX，二者在 provider 命名、数据表、产品语义上彻底拆开。

代价是一次破坏性迁移和部分历史 CEX market data 删除；收益是后续 Token Case、Pulse、OI/radar board 和 CoinGlass enrichment 都围绕 Binance USDT perp 一条主线，不再需要解释 OKX route 与 Binance derivatives proxy 的差异。
