# Token Identity Resolution Production Audit

日期：2026-05-06

## 结论

这次复审确认原先的 `$MIRROR` 问题不是单点 bug，而是 asset identity 闭环缺失：

- unresolved/ambiguous placeholder 会进入 symbol 候选集，污染后续真实资产收敛。
- ingest 写入 unresolved 后没有自动 provider resolution job。
- OKX DEX search 参数没有按官方 `search/chains` 合约调用，且缺 Web3 签名能力。
- CEX universe 只同步 instrument，不写 ticker price snapshot。
- DEX provider search 写候选但没有 worker/claim/backfill 闭环。
- CA search、WS symbol/CA subscription 仍绕过 asset_attributions。
- asset-flow 先截断原始 attribution 再聚合，高流量窗口会低估或丢热币。
- timeline/posts 游标只用 timestamp，同毫秒分页会漏数据。
- harness settlement 仍读旧 `tokens/token_market_snapshots`，没有消费新的 `asset_market_snapshots`。

## 生产治理

### 1. 解析层

推文文本和 GMGN payload 统一进入 `asset_mentions`。解析只产出事实，不因为 provider 暂时找不到就丢弃事件：

- cashtag/symbol 无候选：写 `asset:unresolved:{SYMBOL}`，同时入队 `symbol_resolution`。
- symbol 多候选：写 `asset:ambiguous:{SYMBOL}`，同时入队 `symbol_resolution`。
- CA 无完整 chain/address：写 unresolved CA，并入队 `ca_resolution`。
- GMGN payload 或明确 chain+address：直接 upsert DEX asset + venue。

resolver 只把真实 `resolved` asset 当作可选候选，placeholder 不再参与竞争；真实资产出现后 `$MIRROR` 会自然收敛。

### 2. Provider 闭环

新增 `AssetResolutionWorker`：

- claim `asset_resolution_jobs`，支持 `FOR UPDATE SKIP LOCKED`。
- 调 OKX DEX token search。
- upsert DEX asset/venue。
- 写 `asset_resolution_candidates`。
- 写 `asset_market_snapshots`。
- 如果 symbol 只有一个真实 DEX 候选，自动 backfill 历史 unresolved/ambiguous attribution。
- 如果 CA job 只有一个真实 DEX 候选，自动 backfill 历史 unresolved CA attribution。

OKX DEX client 使用官方 Web3 token search 合约：

- endpoint：`/api/v6/dex/market/token/search`
- query params：`search`、`chains`
- 支持 `OK-ACCESS-*` 签名头。

### 3. CEX 闭环

`sync-okx-cex-universe` 不再只是同步交易对列表。现在同一命令会：

- 同步 OKX CEX instruments。
- upsert CEX assets/venues。
- 拉取 tickers。
- 写 `asset_market_snapshots`，包括 `price_usd`、`volume_24h_usd`、`open_interest_usd`。

BTC/TAO 这类 CEX-first 资产因此优先通过 CEX venue 成为 resolved asset，不再依赖 GMGN 链上 token search。symbol-only mention 的 resolver/search 都采用同一条规则：如果本地有唯一 CEX asset，则优先选择该 CEX asset；只有没有唯一 CEX asset 时才进入 DEX 单候选或多候选歧义处理。

### 4. 查询与推送

查询和推送全部回到 asset attribution 事实表：

- `/api/search` 的 CA 查询走 `asset_venues + asset_attributions + asset_mentions`。
- `/ws` symbol/CA subscription 匹配 `asset_attributions`，不再只看 deterministic entities。
- `asset-flow` 改为 SQL 聚合后按 resolved/attention lane 分别 rank，不再先截断原始 attribution。
- `asset-posts` 和 `asset-social-timeline` 使用 `received_at_ms:event_id` 复合游标，避免同毫秒漏页。

### 5. Harness/价格闭环

harness materialization 和 settlement 已切到 asset store：

- social-event token candidates 通过 `AssetRepository` 解析。
- entry readiness 读 `asset_market_snapshots.price_usd`。
- settlement entry/exit 也读 `asset_market_snapshots`。
- runtime 不再启动旧 `MarketObservationWorker`，避免新 asset price 与旧 token price 双轨。

## 当前边界

- unresolved symbol 会保留为 attention candidate，并持续通过新 mention 重新排队 provider resolution。
- 多候选 symbol 不强行自动选择；只有 provider 返回唯一真实候选时自动 backfill。
- CEX ticker 的 `volume_24h_usd` 假设 USDT/USDC quote 可近似 USD；非 USD quote 后续应显式换算。
- OKX DEX worker 需要配置 `providers.okx.dex_api_key/dex_secret_key/dex_passphrase` 才会在服务 runtime 自动启动；CLI 可以手动跑 `ops process-asset-resolution-jobs`。
