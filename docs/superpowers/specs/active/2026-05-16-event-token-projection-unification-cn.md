# 2026-05-16 Event Token Projection Unification Spec

## 背景

最近 worker runtime 和 event-anchor market capture 重构后，代币详情页、watchlist timeline、实时 tape 出现同一类症状：

- 事件已经有 `token_intent_resolutions`，也有 `enriched_events + market_ticks`。
- token radar / token case 的部分链路能读到价格。
- 但 watchlist、HTTP recent、实时 WS payload 仍可能只返回裸 `token_intent_resolutions`，缺少 `symbol`、事件锚定价格和市场观测状态。

这不是市场 worker 单点失效，而是公共读模型分叉：同一个“帖子里提到了哪个代币、当时价格是多少”的产品语义，被多个入口用不同 SQL/对象拼装。

## 事实表边界

`token_intent_resolutions` 不是旧表，也不应删除。它是当前 Kappa/CQRS 事实层的一部分，职责是回答：

- 某个 `token_intent` 是否解析成功。
- 解析到哪个 `target_type + target_id + pricefeed_id`。
- 解析策略、候选、lookup key、当前记录状态。

它不负责回答：

- 帖子里该代币展示什么 symbol。
- 该事件锚定到了哪条价格 tick。
- 这条价格是否 ready/stale/pending。

这些公共展示语义必须由统一事件代币投影读取：

```text
events/token_intents
  -> token_intent_resolutions
  -> asset_identity_current / cex_tokens / price_feeds
  -> enriched_events
  -> market_ticks
  -> public token_resolutions projection
```

## 产品契约

所有公共事件 payload 中的 `token_resolutions` 表示“事件代币提及投影”，不是裸 DB 行。

返回字段收口为：

- `resolution_id`
- `intent_id`
- `event_id`
- `target_type`
- `target_id`
- `pricefeed_id`
- `resolution_status`
- `reason_codes_json`
- `candidate_ids_json`
- `lookup_keys_json`
- `symbol`
- `price`

其中 `price` 使用统一 `message_price_payload` 结构：

- `status`: `ready` / `stale` / `pending_observation`
- `provider`
- `pricefeed_id`
- `price_usd`
- `price_quote`
- `quote_symbol`
- `observed_at_ms`
- `observation_lag_ms`
- `observation_id`
- `observation_kind`

公共 payload 不再暴露事实表内部历史/审计字段，例如 `asset_id`、`primary_venue_id`、`identity_status`、`confidence`、`resolver_policy_version`、`reasons_json`、`risks_json`、`record_status`、`is_current`、`superseded_at_ms` 或 market join 临时列。

## 入口收口

以下入口必须读取同一个投影：

- `/api/recent`
- WebSocket replay payload
- WebSocket live publish payload
- watchlist timeline

保留内部事实读路径：

- ingest commit 后需要读取 current resolution facts，用于 enrichment gate 和内部 `IngestedEvent` 结果。
- resolver/reprocess/quality/refresh 等生命周期代码可以继续使用 `token_intent_resolutions` 事实表。

## 非目标

- 不做 `token_intent_resolutions` 表删除。
- 不做 destructive schema prune。若未来确认某些列长期无消费者，应单独做 schema audit、迁移和回滚策略。
- 不引入兼容 fallback，不保留旧 public shape 的双写/双读。

## 成功标准

- 公共事件 token projection 只有一个 SQL 实现。
- HTTP/WS/watchlist/collector 不再直接返回 `intent_resolutions.resolutions_for_event()`。
- 实时 tape 新事件和 replay/recent/watchlist 看到同样的 token mention + price 结构。
- 测试覆盖：
  - 投影可返回 symbol 和事件锚定 price。
  - 投影过滤 unresolved/null target。
  - 公共 payload 不含内部事实/market join 字段。
  - HTTP/WS/collector/watchlist 都走统一投影。
