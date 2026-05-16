# 2026-05-16 Event Token Projection Unification Plan

## 目标

把“帖子里的代币提及 + 事件锚定价格”收口为唯一公共读模型，删除 HTTP/WS/collector/watchlist 中重复或裸读 `token_intent_resolutions` 的公共路径。

## 约束

- `token_intent_resolutions` 保留为事实表。
- 不做兼容层，不保留旧 public payload 的历史字段。
- 投影从事实表和 market facts 读取，不写入新状态。
- worker 继续通过 `db.worker_session()` 获取 repository session，不开 raw pool。

## 步骤

1. RED：新增事件代币投影单元测试。
   - 构造 current Asset/CexToken resolution、identity/feed、enriched event、market tick 字段。
   - 断言返回 lean public payload、symbol、price。
   - 断言 unresolved/null target 被过滤。

2. RED：新增公共链路防回归测试。
   - HTTP `_payload_for_event` 使用 `repos.event_tokens.for_event()`，不能调用 `repos.intent_resolutions.resolutions_for_event()`。
   - WS replay payload 使用同一投影。
   - collector live publish 从 store 读取投影，不发布 `ingested.token_resolutions` 裸事实。
   - watchlist repository 委托统一投影，不保留重复 SQL。

3. GREEN：实现 `EventTokenProjectionQuery`。
   - 位置：`domains/token_intel/queries/event_token_projection_query.py`。
   - 对外方法：`for_event(event_id)` 和 `for_events(event_ids)`。
   - 内部 SQL 连接 `token_intent_resolutions`、`asset_identity_current`、`cex_tokens`、`price_feeds`、`enriched_events`、`market_ticks`。
   - 使用 `asset_market.interfaces.message_price_payload` 生成价格 payload。
   - 只返回 spec 中列出的 public 字段。

4. GREEN：接入所有公共入口。
   - `RepositorySession` 增加 `event_tokens`。
   - `http._payload_for_event` 和 `PublicWebSocketHub._payload_for_event` 改读 `repos.event_tokens.for_event(event_id)`。
   - `WatchlistIntelRepository.token_resolutions_for_events()` 改为委托 `EventTokenProjectionQuery(self.conn)`。
   - `IngestStoreProtocol` 增加 `event_token_resolutions(event_id)`，collector live publish 调用它。
   - `_PooledIngestStore` 用 worker session + `repos.event_tokens` 实现投影读取。

5. 清理旧路径。
   - 删除 watchlist 内部重复 SQL、重复 decoder 和 price private-key 清理代码。
   - 保留 `IntentResolutionRepository.resolutions_for_event()` 作为 ingest/enrichment 内部事实读取；禁止 app surface 和 collector publish 直接使用。

6. 验证。
   - 运行新增/受影响 Python 测试。
   - 运行 frontend 类型检查、lint、build，确认 public type shape 不破。
   - 本地 API/WS/watchlist/详情页 smoke。
   - 如通过，提交变更。
