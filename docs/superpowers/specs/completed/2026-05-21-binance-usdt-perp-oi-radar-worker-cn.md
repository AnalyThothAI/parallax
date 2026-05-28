# Binance USDT Perp Universe And OI Radar Worker Spec

> 2026-05-27 hard-cut update: the run-table DDL and `run_id` FK design below
> are retired. The OI radar board now uses current-only
> `cex_oi_radar_rows` plus `cex_oi_radar_publication_state`; do not implement
> `cex_oi_radar_runs`.

日期：2026-05-21
状态：superseded by `docs/superpowers/specs/active/2026-05-21-cex-binance-hard-cut-cn.md`
范围：把 Binance USDT 永续合约 universe 低频写入现有 CEX registry 表，并新增一个可定期全量扫描 Binance USDT 永续的 OI/radar board worker。

> 2026-05-21 更新：CEX 方向已从“OKX/Binance provider mux”改为“Binance-only hard cut”。执行以 `2026-05-21-cex-binance-hard-cut-cn.md` 为准。本文件只保留 OI/radar board 的容量估算和 Binance data endpoint 分析，不再作为 CEX provider 迁移方案。

## 结论

默认只接 Binance USDT perpetual。USDC perpetual、spot、COIN-M futures 都不进入 V1。

这条链路可以做，而且应该分成两层：

1. **Universe sync**：低频、幂等地把 Binance USDT 永续合约写入 `cex_tokens` 和 `price_feeds(provider='binance', feed_type='cex_swap')`。这是 identity/routing，不是衍生品 enrichment。
2. **OI/radar board worker**：周期性扫描全 Binance USDT 永续 universe，写入独立的 OI/radar facts + read model。它不写 `token_radar_rows`，不改变 Token Radar 主排序，不在 HTTP request-time 调 provider。

关键架构点：

- 全量 OI 使用 Binance 官方 USD-M futures data endpoint，因为它直接给 `sumOpenInterestValue`，覆盖全 USDT 永续更快、更稳定。
- CoinGlass 有价值，但不适合作为 527 个合约每轮全家桶调用。V1 用 CoinGlass 做 top-K 深度 enrichment，尤其 liquidation levels、CVD、top-trader/long-short 语境。
- 写 `provider='binance'` 的 `price_feeds` 之前，必须补 Binance CEX market provider 或 provider mux。否则现有 `market_tick_poll` 可能把 `binance:BTCUSDT` 交给 OKX CEX provider，产生无效 ticker 调用。
- Worker 可以长一点，但必须有 advisory lock、rate limiter、timeout、resume、degradation report 和 retention。

## 当前事实

### 项目内表与 worker 边界

现有 CEX identity/routing 表已经可承载 Binance 合约：

- `cex_tokens`：按 `base_symbol` 唯一，表示 CEX token identity。
- `price_feeds`：按 `(provider, feed_type, native_market_id)` 唯一，表示交易所市场路由。
- `market_ticks`：append-only market fact，已经支持 `open_interest_usd`。

现有 `sync_cex_routes(...)` 目前按 OKX tickers 写 `cex_tokens` / `price_feeds`，并且 `_base_quote_from_inst_id(...)` 依赖 OKX `BTC-USDT-SWAP` 这种带 `-` 的 inst id。Binance native id 是 `BTCUSDT`，必须从 `exchangeInfo.baseAsset` / `quoteAsset` 显式取 base/quote，不能复用 OKX parser。

现有 `MarketTickPollWorker` 的 CEX path 只有单个 `message_cex_market`，且 `source_provider` 固定为 `okx_cex_rest`。因此 Binance `price_feeds` 进入 active live target 前，需要 provider mux：

```text
target_id = "binance:BTCUSDT"
  -> provider mux 根据 target.exchange = "binance" 选择 BinanceCexMarketProvider
  -> MarketTick.source_provider = "binance_cex_rest"
```

如果不做 mux，Binance route 会污染 CEX poll，而不是增强它。

### Binance universe 基准

2026-05-21 实测 Binance USD-M Futures `exchangeInfo`：

| 过滤条件 | 数量 |
|---|---:|
| `status=TRADING` 且 `contractType=PERPETUAL` | 567 |
| 其中 `quoteAsset=USDT` | 527 |
| 其中 `quoteAsset=USDC` | 38 |

V1 默认只取 `quoteAsset=USDT`，所以容量设计按约 527 个合约估算，但实现不能硬编码 527 或历史口径的 483。

官方 endpoint 特征：

| 用途 | Endpoint | 覆盖 | 限制/权重 |
|---|---|---|---|
| Universe | `GET /fapi/v1/exchangeInfo` | 全 USD-M symbols | weight 1 |
| 24h ticker | `GET /fapi/v1/ticker/24hr` no symbol | 全 symbols | weight 40 |
| mark/funding current | `GET /fapi/v1/premiumIndex` no symbol | 全 symbols | weight 10 |
| OI history | `GET /futures/data/openInterestHist` | 单 symbol | IP 1000 requests / 5 min |
| funding history | `GET /fapi/v1/fundingRate` | 单 symbol 或多 symbol 最近记录 | 500 / 5 min shared limit |
| global long/short | `GET /futures/data/globalLongShortAccountRatio` | 单 symbol | IP 1000 requests / 5 min |
| taker buy/sell | `GET /futures/data/takerlongshortRatio` | 单 symbol | IP 1000 requests / 5 min |

外部参考：

- Binance USD-M Futures Exchange Information: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information>
- Binance USD-M Futures Open Interest Statistics: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics>
- Binance USD-M Futures 24hr Ticker: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics>
- Binance USD-M Futures Mark Price and Funding: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price>
- Binance USD-M Futures Long/Short Ratio: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio>
- Binance USD-M Futures Taker Buy/Sell Volume: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume>

## 产品目标

### 用户价值

这个 board 解决的是“CEX 杠杆参与是否真的跟上了市场关注”的问题，不是替代社交 Token Radar。

V1 输出：

- 全 Binance USDT 永续 OI 排名。
- OI 4h / 24h delta。
- 24h price、volume、turnover、funding current。
- 设置质量分：价格动量 + OI 参与 + funding 风险 + 可交易性 gate。
- Top-K 加深：CoinGlass liquidation zones / CVD / long-short / top-trader，如果上游可用。
- 每轮 degraded symbols 和 provider latency 报告。

### 不做的事

- 不把全 Binance board 写进 `token_radar_rows`。
- 不让 Token Radar 的 social score 被全量 CEX OI 直接覆盖。
- 不在 token detail / CEX page HTTP request 内实时打 Binance/CoinGlass。
- 不默认扫 USDC perpetual。
- 不默认对 527 个合约调用 CoinGlass 全数据族。

## 数据架构

### Universe sync 写现有表

新增一个 Binance futures universe provider：

```text
src/gmgn_twitter_intel/integrations/binance/usdm_futures_client.py
src/gmgn_twitter_intel/app/runtime/provider_wiring/binance.py
```

Provider 输出显式 route，不输出 OKX 风格 ticker：

```python
@dataclass(frozen=True, slots=True)
class CexRoute:
    provider: str              # "binance"
    feed_type: str             # "cex_swap"
    native_market_id: str      # "BTCUSDT"
    base_symbol: str           # "BTC"
    quote_symbol: str          # "USDT"
    status: str                # "TRADING"
    contract_type: str         # "PERPETUAL"
    raw: dict[str, Any]
```

Sync service：

```text
Binance exchangeInfo
  -> filter status=TRADING, contractType=PERPETUAL, quoteAsset=USDT
  -> upsert cex_tokens(base_symbol)
  -> upsert price_feeds(provider='binance', feed_type='cex_swap', native_market_id=symbol)
  -> mark missing Binance USDT swap feeds inactive
```

规则：

- `cex_tokens` 不因 Binance delist 自动 inactive，因为同一 base symbol 可能仍在 OKX 或其他 venue。
- `price_feeds(provider='binance', feed_type='cex_swap', quote_symbol='USDT')` 可以按本轮 absent set 标记 inactive。
- `base_symbol` 按 Binance `baseAsset`，不要从 `BTCUSDT` 字符串猜。
- `native_market_id` 保存原始 Binance `symbol`，例如 `1000BONKUSDT`。
- `target_id` 仍是现有形态 `binance:<native_market_id>`，例如 `binance:BTCUSDT`。

入口：

- `uv run gmgn-twitter-intel ops sync-binance-usdt-perp-universe`
- `scripts/sync_binance_usdt_perp_universe.sh` 只作为 cron/launchd wrapper，业务逻辑仍在 app service + repository。
- 可选新增轻量 worker `binance_cex_universe_sync`，默认 disabled；如果开启，建议 `interval_seconds=21600`。

### Binance CEX market provider

为了让 Binance route 不破坏现有 market tick poll，必须把 CEX provider 从单 provider 改成 provider mux：

```text
AssetMarketProviders.cex_markets = {
  "okx": OkxCexMarketProvider,
  "binance": BinanceUsdmFuturesMarketProvider,
}
```

`MarketTickPollWorker` 处理 CEX target 时：

1. 从 target id 解析 `exchange`。
2. 通过 mux 找 provider。
3. 调 `provider.ticker(inst_id=target.instrument)`。
4. 写 `MarketTick(source_provider='binance_cex_rest')` 或 `okx_cex_rest`。

`MarketTickSourceProvider` literal 要增加 `binance_cex_rest`。

Binance ticker mapping：

| Binance field | MarketTick field |
|---|---|
| `lastPrice` | `price_usd` |
| `quoteVolume` | `volume_24h_usd` |
| `closeTime` | `observed_at_ms` |
| current OI hist latest `sumOpenInterestValue` | `open_interest_usd` when coming from OI board snapshot, not from 24h ticker |

### 全量 OI facts

新增 append-only / upsert-on-natural-key fact table，用于高频 OI/ratio series。不要每轮把完整 48/100 点历史塞进一个巨大的 JSON snapshot。

```sql
CREATE TABLE IF NOT EXISTS cex_derivative_series_points (
  point_id TEXT PRIMARY KEY,
  source_provider TEXT NOT NULL,
  exchange TEXT NOT NULL,
  instrument TEXT NOT NULL,
  base_symbol TEXT NOT NULL,
  quote_symbol TEXT NOT NULL,
  family TEXT NOT NULL,
  period TEXT NOT NULL,
  timestamp_ms BIGINT NOT NULL,
  observed_at_ms BIGINT NOT NULL,
  received_at_ms BIGINT NOT NULL,
  open_interest NUMERIC,
  open_interest_usd NUMERIC,
  funding_rate NUMERIC,
  long_short_ratio NUMERIC,
  long_account NUMERIC,
  short_account NUMERIC,
  taker_buy_volume NUMERIC,
  taker_sell_volume NUMERIC,
  taker_buy_sell_ratio NUMERIC,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL,
  UNIQUE(source_provider, exchange, instrument, family, period, timestamp_ms)
);

CREATE INDEX IF NOT EXISTS idx_cex_derivative_series_points_latest
ON cex_derivative_series_points(exchange, instrument, family, period, timestamp_ms DESC);
```

V1 必填 family：

- `open_interest_hist` from Binance `openInterestHist`, period default `1h`, limit default `48`。

V1 可选 family：

- `global_long_short_ratio`，默认只 top-K 或低频全量。
- `taker_buy_sell_volume`，默认只 top-K 或低频全量。
- `funding_rate_history`，默认不全量，current funding 用 `premiumIndex`。

### Board read model

新增 rebuildable read model，唯一 writer 是 board worker：

```sql
CREATE TABLE IF NOT EXISTS cex_oi_radar_rows (
  row_id TEXT PRIMARY KEY,
  period TEXT NOT NULL,
  board_provider TEXT NOT NULL,
  board_exchange TEXT NOT NULL,
  board_quote_symbol TEXT NOT NULL,
  board_contract_type TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT 'cex_symbol',
  target_id TEXT NOT NULL,
  cex_token_id TEXT REFERENCES cex_tokens(cex_token_id) ON DELETE SET NULL,
  pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
  exchange TEXT NOT NULL,
  instrument TEXT NOT NULL,
  base_symbol TEXT NOT NULL,
  quote_symbol TEXT NOT NULL,
  price_usd NUMERIC,
  volume_24h_usd NUMERIC,
  open_interest_usd NUMERIC,
  open_interest_delta_4h_pct NUMERIC,
  open_interest_delta_24h_pct NUMERIC,
  funding_rate NUMERIC,
  price_change_24h_pct NUMERIC,
  quality_score NUMERIC,
  direction_confidence NUMERIC,
  uncertainty_multiplier NUMERIC,
  composite_score NUMERIC,
  side TEXT,
  bucket TEXT NOT NULL,               -- "act_now" / "watch" / "monitor" / "discard"
  labels_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  degraded BOOLEAN NOT NULL DEFAULT false,
  computed_at_ms BIGINT NOT NULL,
  UNIQUE(board_provider, board_exchange, board_quote_symbol, board_contract_type, period, target_id)
);

CREATE TABLE IF NOT EXISTS cex_oi_radar_publication_state (
  board_key TEXT PRIMARY KEY,
  current_payload_hash TEXT,
  latest_attempt_status TEXT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);
```

`cex_oi_radar_rows` 是 current read model，不是 business fact。它按 board identity 和 target identity 幂等发布，不能被其他 worker 写。

### CoinGlass top-K snapshots

沿用 CoinGlass integration spec 的 `cex_derivatives_snapshots`。在 full board 中，它只服务 top-K enrichment：

- `liquidation-levels`：top 30，默认 7d。
- `cvd-history`：top 30 或 disabled。
- `long-short-ratio-history`：top 30 或 disabled；如果 Binance ratio 已覆盖，可只做 cross-check。
- `top-trader-position-history`：top 30 或 disabled。
- `oi-history`：top-K cross-check 或 Binance OI degradation fallback，不做全 527 默认调用。

## Worker 设计

### `binance_cex_universe_sync`

轻量同步 worker 或 ops command。

默认配置：

```yaml
binance_cex_universe_sync:
  enabled: false
  interval_seconds: 21600
  quote_symbol: "USDT"
  contract_type: "PERPETUAL"
  advisory_lock_key: 2026052102
  hard_timeout_seconds: 60
```

一次 run：

1. 调 Binance `exchangeInfo`。
2. filter active USDT perpetual。
3. DB worker session upsert `cex_tokens` 和 `price_feeds`。
4. mark absent Binance USDT swap feeds inactive。
5. 返回 `seen/written/inactivated/duration_ms`。

性能预期：

- Provider：1 个 HTTP request。
- DB：约 527 个 `cex_tokens` upsert + 527 个 `price_feeds` upsert + 1 个 inactive update。
- 运行时间：正常 1-5 秒；冷 DB 或慢网络 5-15 秒。
- 频率：6 小时一次足够；也可以每日 cron。

### `cex_oi_radar_board`

新增独立 worker，建议放在新 domain：

```text
src/gmgn_twitter_intel/domains/cex_market_intel/
  runtime/cex_oi_radar_board_worker.py
  repositories/cex_derivative_series_repository.py
  repositories/cex_oi_radar_repository.py
  services/binance_oi_radar_builder.py
  scoring/oi_radar_scoring.py
```

放新 domain 的原因：

- `asset_market` 继续拥有 market facts 和 provider integration。
- `token_intel` 继续拥有 social Token Radar。
- `cex_market_intel` 拥有“CEX market-wide board”这种产品 read model，避免把 OI board 误塞进 Token Radar。

默认配置：

```yaml
cex_oi_radar_board:
  enabled: false
  interval_seconds: 1800
  soft_timeout_seconds: 720
  hard_timeout_seconds: 900
  concurrency: 8
  request_rate_per_second: 2.8
  quote_symbol: "USDT"
  contract_type: "PERPETUAL"
  oi_period: "1h"
  oi_limit: 48
  min_quote_volume_24h_usd: 10000000
  radar_depth: 50
  coinglass_enrichment_enabled: false
  coinglass_depth: 30
  retention_days: 14
  advisory_lock_key: 2026052103
```

一次 run：

1. 获取 active Binance USDT perpetual universe。优先读 DB `price_feeds(provider='binance', feed_type='cex_swap', quote_symbol='USDT')`，若为空或 stale，则 run 内触发一次 `exchangeInfo` sync。
2. 调 `ticker/24hr` no symbol，一次拿全市场 24h price/volume。
3. 调 `premiumIndex` no symbol，一次拿全市场 mark price + latest funding。
4. 对每个 active USDT perpetual 调 `openInterestHist(symbol, period='1h', limit=48)`，受全局 rate limiter 控制。
5. Upsert 新的 OI series points。已存在 timestamp 点跳过。
6. 对每个 symbol 计算 features：latest OI USD、4h/24h delta、price 24h、volume 24h、funding current、可交易性 gate。
7. 生成 deterministic ranking rows。
8. 如果 `coinglass_enrichment_enabled=true`，只对 top `coinglass_depth` 调 CoinGlass heavy families，写 `cex_derivatives_snapshots`，再重算 top-K 的 labels/degradations。
9. 发布 `cex_oi_radar_rows` 和 `cex_oi_radar_publication_state`，发送 wake hint `cex_oi_radar_updated`。

DB session 规则：

- Provider IO 前先读取 target list，然后关闭 DB session。
- HTTP calls 全部在 DB session 外。
- 写入 series points 和 board rows 时批量开短 session。
- 单 run 使用 advisory lock，禁止重叠。

## Scoring 规则

沿用 CEX radar 技能的排序层级：

```text
investability gate
  -> momentum / price regime
  -> setup quality
  -> OI participation + funding confirmation
  -> secondary context
```

V1 feature：

| Feature | 来源 | 角色 |
|---|---|---|
| `quoteVolume` | Binance `ticker/24hr` | investability gate |
| `priceChangePercent` | Binance `ticker/24hr` | momentum |
| `sumOpenInterestValue` latest | Binance `openInterestHist` | OI participation |
| OI 4h / 24h delta | stored OI points | participation confirmation |
| `lastFundingRate` | Binance `premiumIndex` | crowding / risk |
| liquidation clusters | CoinGlass top-K | secondary risk context |
| CVD / long-short / top-trader | CoinGlass top-K or Binance ratio endpoints | secondary confirmation |

不可用时降级：

- OI 缺失：row 可以进入 `monitor`，不能进入 `act_now`。
- Funding 缺失：降低 uncertainty，不 hard fail。
- CoinGlass 缺失：只移除 secondary labels，不影响全量 OI board 生成。
- Volume 太低：直接 `discard`，不让小币 OI 百分比异常污染榜单。

## 性能评估

### Universe sync

当前 USDT 永续约 527 个。每 6 小时同步一次：

- HTTP requests：1。
- DB writes：约 1054 次 upsert + 1 次 inactive batch update。
- 时间：1-5 秒常态，慢网络 15 秒内。
- DB 影响：极低。`cex_tokens` / `price_feeds` 是小表，且 upsert 按唯一索引命中。

### Binance-only full OI board

默认每 30 分钟一轮，N=527。

请求量：

```text
exchangeInfo: 0-1 request, usually DB fresh so skipped
ticker/24hr all: 1 request, weight 40
premiumIndex all: 1 request, weight 10
openInterestHist: N requests = about 527
```

Binance `openInterestHist` IP limit 是 1000 requests / 5 min。用 `request_rate_per_second=2.8`：

```text
527 / 2.8 = 188 秒
```

加网络延迟、retry、DB batch write，合理估计：

| 场景 | 时间 |
|---|---:|
| 正常网络，少量 retry | 4-6 分钟 |
| 慢网络，上游偶发 429/5xx | 6-10 分钟 |
| 超过 10 分钟 | 本轮标记 partial，保留可用 rows，不阻塞下一轮 |

DB 写入量：

如果 `oi_period=1h, oi_limit=48`：

- 首轮最多插入 `527 * 48 = 25,296` 个 OI points。
- 后续每小时大约新增 527 个 OI points；每 30 分钟跑一次时，另一半 run 通常只发现重复点。
- `cex_oi_radar_rows` 每轮写约 527 行；30 分钟频率是 `527 * 48 = 25,296` 行/天。
- 保留 14 天约 354k board rows。这个量对 PostgreSQL 很轻。

如果改成 `oi_period=15m` 并 15 分钟跑一次：

- 每天新增约 `527 * 96 = 50,592` 个 OI points。
- 每天 board rows 也是约 50k。
- 14 天约 708k rows。仍可控，但 API 和上游风险翻倍，不建议 V1 默认。

### CoinGlass top-K enrichment

CoinGlass heavy families 不适合全量默认跑。以 top 30、concurrency 2、单调用 8-15 秒估算：

| Families | 调用数 | 估计时间 |
|---|---:|---:|
| liquidation-levels only | 30 | 2-5 分钟 |
| levels + CVD + long-short | 90 | 6-12 分钟 |
| levels + CVD + long-short + top-trader | 120 | 8-16 分钟 |

如果对 527 个合约跑 4 个 CoinGlass family：

```text
527 * 4 = 2108 calls
2108 * 8s / 2 = 2.3 小时
2108 * 15s / 2 = 4.4 小时
```

这不适合作为 30 分钟 worker，也会显著放大上游协议漂移和容器 Playwright 资源风险。所以 V1 只允许 top-K。

### 主服务影响

影响可控，前提是遵守以下约束：

- Worker provider IO 不持有 DB session。
- 全局 HTTP rate limiter 不超过 Binance 公开限制的 80%。
- Worker 使用 advisory lock，禁止并发重叠 run。
- Board rows 写入单独表，不写 `token_radar_rows`。
- CEX page / Token Case 只读 DB latest run 或 latest snapshots，不同步打 provider。
- CoinGlass top-K enrichment 默认关闭，开启时单独 hard timeout。

风险点：

| 风险 | 影响 | 缓解 |
|---|---|---|
| Binance route 写入后 market poll 走错 provider | 大量无效 CEX quote | 先做 provider mux，再启用 Binance price_feeds 到 active target |
| OI worker 超过 interval | run 重叠、DB 和上游压力 | advisory lock + skip if active + hard timeout |
| 429 / IP limit | partial board | 2.8 rps limiter + exponential backoff + degradation |
| DB JSON 膨胀 | 表膨胀、查询慢 | OI series 用列式 numeric points，不存整段 raw series |
| CoinGlass Playwright 重 | CPU/内存尖峰 | top-K、concurrency 1-2、默认 disabled |
| 小币 OI 百分比噪声 | 排名污染 | quote volume gate + OI USD floor |

## 产品接入

### CEX 页面

新增 “Binance OI Radar” tab 或 section：

- Latest run time / freshness。
- Rows：rank、symbol、price 24h、volume、OI USD、OI 4h/24h delta、funding、bucket、labels。
- Degradation banner：partial symbols、provider latency、CoinGlass availability。
- Filter：bucket、min volume、funding hot/cold、OI rising/falling。

默认展示最新 succeeded 或 partial run。若最新 run 超过 freshness TTL，显示 stale，不在页面同步刷新。

### Token Case / CEX Token detail

详情页读取：

- 最新 `cex_oi_radar_rows` 中该 `target_id` 的 row。
- 最新 `cex_derivatives_snapshots` 中 top-K CoinGlass enrichment，如果存在。

详情页可以 enqueue refresh request，但仍由 worker 异步处理。页面显示 `queued/stale/fresh/degraded`。

### Token Radar / Pulse

Token Radar：

- V1 只显示 CEX badge 或链接到 CEX board。
- 不改 rank score。

Pulse agent：

- 可以读取 sealed evidence：最新 OI board row + top-K derivatives snapshot refs。
- 不能自行调用 Binance/CoinGlass。
- OI/funding/liquidation 只能作为 leverage/crowding/risk context。

## 配置建议

`config.yaml`：

```yaml
providers:
  binance:
    enabled: true
    cex_base_url: "https://www.binance.com"
    usdm_futures_base_url: "https://fapi.binance.com"
    usdm_futures_data_base_url: "https://fapi.binance.com"
    timeout_seconds: 15
  coinglass:
    enabled: false
    default_exchange: "Binance"
    default_quote: "USDT"
    timeout_seconds: 45
```

`cex_base_url` 保持给现有 `BinanceCexProfileClient` 使用；USD-M futures 不复用这个字段，避免把 profile source 从 `www.binance.com` 误切到 futures API host。

`workers.yaml`：

```yaml
binance_cex_universe_sync:
  enabled: false
  interval_seconds: 21600
  quote_symbol: "USDT"
  contract_type: "PERPETUAL"
  hard_timeout_seconds: 60
  advisory_lock_key: 2026052102

cex_oi_radar_board:
  enabled: false
  interval_seconds: 1800
  soft_timeout_seconds: 720
  hard_timeout_seconds: 900
  concurrency: 8
  request_rate_per_second: 2.8
  quote_symbol: "USDT"
  contract_type: "PERPETUAL"
  oi_period: "1h"
  oi_limit: 48
  min_quote_volume_24h_usd: 10000000
  radar_depth: 50
  coinglass_enrichment_enabled: false
  coinglass_depth: 30
  retention_days: 14
  advisory_lock_key: 2026052103
```

默认 disabled，先通过 manual ops smoke，再由 operator 打开。

## Rollout

1. **Binance official client**
   - 新增 USD-M futures client。
   - 覆盖 `exchangeInfo`、`ticker/24hr`、`premiumIndex`、`openInterestHist`。
   - Unit 用 fixture，不打真实网络。

2. **Universe sync**
   - 新增 `CexRoute` 和 generic route sync service。
   - OKX path 迁移到 explicit route，避免继续依赖字符串 split。
   - 新增 `ops sync-binance-usdt-perp-universe`。
   - 支持 absent Binance feeds inactive。

3. **Provider mux**
   - `AssetMarketProviders` 增加 CEX provider map。
   - `MarketTickPollWorker` 按 `target.exchange` dispatch。
   - `MarketTickSourceProvider` 增加 `binance_cex_rest`。
   - 不做完 mux，不允许生产开启 Binance `price_feeds` 到 active market poll。

4. **OI series facts**
   - Migration：`cex_derivative_series_points`。
   - Repository：批量 upsert points。
   - Retention：默认 30 天。

5. **Radar board read model**
   - Migration：`cex_oi_radar_rows`、`cex_oi_radar_publication_state`。
   - Worker：`cex_oi_radar_board`。
   - Scoring service：deterministic，fixture 可回放。

6. **API / UI**
   - `/api/cex/radar-board` 返回 latest run + rows。
   - CEX 页面新增 board。
   - Token Case 增加 latest board row + derivatives snapshot block。

7. **CoinGlass top-K enrichment**
   - 先跑 canary。
   - 默认关闭，手动开启 top 30。
   - 失败只 degraded，不让 board fail。

## 验收标准

- `ops sync-binance-usdt-perp-universe --dry-run` 输出 active USDT perpetual count，不写 DB。
- `ops sync-binance-usdt-perp-universe --execute` 后，DB 存在 `price_feeds(provider='binance', feed_type='cex_swap', quote_symbol='USDT')`。
- 缺席本轮 Binance USDT universe 的旧 Binance feeds 被标记 inactive，`cex_tokens` 不被误删。
- Market tick poll 能按 `target_id='binance:BTCUSDT'` dispatch 到 Binance provider。
- `cex_oi_radar_board.run_once()` 在 25-symbol fixture 下写入 run + rows + OI points。
- 527-symbol dry run 能估算请求数、预计耗时、rate limiter 配置，不调用 provider。
- Worker provider IO 不持有 DB session。
- Board worker 不 import 或写 `token_radar_rows`。
- HTTP route、frontend、Pulse agent 不 import Binance/CoinGlass integration adapter。
- Partial run 可展示，degradations 可读。
- Retention job 能 prune 旧 board rows 和旧 series points。

## 测试计划

- Unit：Binance `exchangeInfo` parser，过滤 `TRADING + PERPETUAL + USDT`。
- Unit：`1000BONKUSDT` 这类 symbol 使用 `baseAsset/quoteAsset`，不靠字符串猜 base。
- Unit：route sync upsert + inactive mark。
- Unit：provider mux dispatch OKX/Binance。
- Unit：OI delta 4h/24h 计算。
- Unit：scoring gate，低 volume 小币不能进 `act_now`。
- Unit：partial degradation，单 symbol OI 失败不 abort run。
- Integration：migration + repository batch upsert + latest board query。
- Worker：DB session boundary，provider IO outside session。
- Architecture：`cex_oi_radar_board` 是 `cex_oi_radar_rows` 唯一 writer。
- Docker smoke：app image 内能运行 Binance client smoke；CoinGlass top-K 开启时再跑 `coinglass-cli canary`。

## 需要拒绝的替代方案

| 方案 | 为什么不采用 |
|---|---|
| 详情页打开时实时拉 Binance/CoinGlass | 请求放大、不可回放、HTTP 超时、无法统一限流 |
| 只写 Binance `price_feeds`，不做 provider mux | 会让 market poll 用错 provider |
| 对 527 个合约每轮跑 CoinGlass 全 family | 2-4 小时级别，不适合周期 worker |
| 把 board row 塞进 `token_radar_rows` | 破坏 Token Radar 的 social attention 语义和单写者边界 |
| 用 USDT + USDC 默认混扫 | universe 和 quote 语义混杂，先把 USDT 做稳定 |

## 最终判断

这个功能合理，默认 USDT 永续即可。性能上，Binance-only 全 OI board 每 30 分钟跑一轮是可接受的，典型耗时 4-6 分钟，慢时 6-10 分钟；DB 增长在 14 天 retention 下是几十万行量级，轻。

真正不合理的是“全 Binance 合约每轮调用 CoinGlass 全数据族”。CoinGlass 的正确位置是 top-K 加深和 liquidation/risk context，而不是全市场基础 OI 数据源。
