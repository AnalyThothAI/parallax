# Spec — Token Radar Hot Resolution and Market Readiness Root Fix

**Status**: Active
**Date**: 2026-05-12
**Owner**: Codex

**Related**
- `docs/superpowers/specs/active/2026-05-12-symbol-only-resolution-gap-cn.md`
- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`
- `src/parallax/domains/evidence/services/ingest_service.py`
- `src/parallax/domains/token_intel/services/deterministic_token_resolver.py`
- `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- `src/parallax/domains/token_intel/read_models/asset_flow_service.py`

---

## 1. Decision

Token Radar 的 "missing" 必须拆成两个不同问题处理：

1. **identity missing**: `token_intent_resolutions.target_type/target_id` 为空。没有 identity，就不能请求价格。
2. **market missing**: 已经有 identity，但 anchor/live market 没有进入当前读模型或 API payload。

根因修复采用一个 KISS 方案：

- 保留一个异步 **ResolutionRefreshWorker** 概念，不引入 Hot Worker + Background Worker 两套系统。
- 把现有 discovery 从 "24h backlog scanner" 收敛为 "热窗口优先的 resolution refresh"。
- read API 默认只向 Token Radar 主列表暴露已解析 target；未解析 NIL/AMBIGUOUS 只作为 diagnostics 计数，不混入主交易列表。
- resolved target 的 live market 在 `/api/token-radar` 读路径做内存 overlay；symbol discovery 不进入读路径。
- 新解析成功的 target 立即触发最小后续动作：reprocess affected intents、补一次 anchor price、重建 5m/1h read model。

这不是新建复杂调度体系，而是把现有 worker 的优先级和职责边界修正。

---

## 2. Root Cause Summary

### 2.1 Resolver "跑完" 不等于解析成功

入库时 `IngestService` 会在同一个事务中完成：

- entity extraction
- `token_evidence`
- `token_intents`
- resolver
- `token_intent_resolutions`
- `token_intent_lookup_keys`

但 `token_intents` 只是 mention fact。它表示 "这条 tweet 提到了一个 token-like entity"，不保证已经映射到某个可交易 target。

对于 `$SYMBOL` 这种 symbol-only mention，入库时 resolver 只查本地事实：

1. `cex_tokens`
2. `us_equity_symbols`
3. `registry_assets + asset_identity_current`

这个顺序是产品边界，不是兼容策略：CEX 已确认 crypto 仍然优先；没有 CEX 且没有地址/链证据时，官方 US equity universe 比 DEX symbol-only 碰撞更强。地址、链地址、GMGN payload 仍走地址解析路径，不受 symbol-only equity 过滤影响。

如果本地 registry 当时没有候选，结果就是：

```text
resolution_status = NIL
reason_codes = ["SYMBOL_NOT_IN_REGISTRY"]
target_type = NULL
target_id = NULL
```

这就是 NIL 的来源。不是前端算出来的，也不是价格缺失。

### 2.2 FLAPPYFARM 真实时间线

`FLAPPYFARM` 是 launch/indexing race 的典型样本：

| 时间 CST | 事实 |
|---|---|
| 2026-05-12 12:45:03 | GMGN WS 入库，只有 `$FLAPPYFARM` cashtag。原始 payload 无 token 字段，引用推文明确说官方合约稍后发布。 |
| 2026-05-12 12:51:37 | OKX discovery 对 `symbol:FLAPPYFARM` 返回 `not_found`, candidate_count=0。 |
| 2026-05-12 13:03:20 | OKX discovery 再跑，返回 BSC 候选，写入 `asset:eip155:56:erc20:0xfcb54d2b664f00f88587377e73c423bff2bf7777`。 |
| 2026-05-12 13:03:20 | intent 当前 resolution 变成 `UNIQUE_BY_CONTEXT / Asset / SINGLE_ACTIVE_CHAIN_ASSET`。 |
| 2026-05-12 13:04:24 | anchor price 写入，`price_usd=0.000010064215561927`。 |
| 2026-05-12 13:11 | 手工重建 `1h/all --limit 300` 后，`FLAPPYFARM` 出现在 resolved lane rank 26，`identity=ready`, `market=partial`。 |

结论：

- 入库时事实确实不足。
- OKX 不是永久搜不到，而是初次查询时尚未索引或链上流动性尚未稳定。
- 后续 discovery 能补上 identity，但 read model 必须足够快地发布新 resolution，否则前端继续显示旧 NIL。

### 2.3 market_missing 与 identity_missing 是不同链路

对 `identity_missing`：

- 没有 chain
- 没有 address
- 没有 CEX inst_id
- 不能订阅 WS
- 不能请求 DEX price

对 `resolved 但 market_missing`：

- 已有 `target_type/target_id`
- 可以用 OKX CEX HTTP、OKX DEX HTTP、DEX WS 或内存 cache 补价格
- 不需要 symbol discovery

因此 "切到 5m 只请求价格就行" 只适用于 resolved target，不适用于 NIL/AMBIGUOUS。

---

## 3. Current Design Problems

### 3.1 Token Radar public payload 混入 unresolved rows

`TokenRadarProjection` 当前会把 unresolved NIL/AMBIGUOUS rows 写入 attention lane。`AssetFlowService.asset_flow(...)` 又把 `targets[:limit] + attention[:limit]` 都返回给前端。

结果是用户看到一个混合列表：

- 可交易 target
- targetless mention
- market missing
- identity missing

这会把两个不同问题混成一个 UI 症状。

### 3.2 `/api/token-radar` 没有 overlay LivePriceGateway cache

`AssetFlowService._missing_live_market(...)` 对所有 rows 都返回 `status="missing"`。前端能靠 WS patch 更新可见行，但用户切窗口、刷新页面或 WS 尚未推送时，API payload 仍会显示 live market missing。

read path 可以读取内存 live cache，但不能做 provider call。这个 overlay 是读模型合成，不是 side effect。

### 3.3 Discovery 对 hot unresolved 的 retry 不够贴近 UI

当前 discovery 是异步正确方向，但它的语义仍偏 "lookup backlog"：

- 以 24h unresolved lookup key 为池子。
- `not_found` 默认 5 分钟后再查。
- 解析成功后只返回 `deferred_to_worker`，依赖 projection worker 后续碰到对应窗口。

对 launch symbol 来说，5 分钟 TTL 足以让 5m UI 错过最关键的第一屏。

### 3.4 Anchor price 与新解析 target 没有强绑定

AnchorPriceWorker 已经存在，也会优先 hot rows。但从 identity discovery 到 anchor price 再到 projection 发布之间仍可能有多轮 worker delay。

对 "刚从 NIL 变 UNIQUE" 的 target，应该在同一轮 refresh 里补一次 anchor price，再重建 hot windows。

---

## 4. Target Architecture

### 4.1 Ingest remains local and deterministic

入库事务不调用 OKX、GMGN search 或任何外部网络。原因：

- 避免 ingestion 被 provider 429/超时拖慢。
- 避免重复用户请求触发同一 symbol search。
- 避免读路径或写路径隐式改 registry。

入库继续写 mention fact 和当时可得的 resolution decision。

### 4.2 One ResolutionRefreshWorker

保留一个 worker 概念，负责 identity refresh，不拆成 Hot Resolution Worker 和 Background Maintenance Worker。

每轮顺序：

1. 选取 hot lookup keys：
   - 最近 5m/1h 的 `NIL/AMBIGUOUS`
   - `symbol:*` 与 `address:*`
   - hot `NIL` 优先于 hot `AMBIGUOUS`
   - hot lookup 可以使用更短的 `not_found` retry TTL
2. 如预算仍有剩余，再处理 24h backlog。
3. 对 due lookup 调 OKX DEX search。
4. 写 `token_discovery_results`、registry、identity evidence/current。
5. 如果候选发生变化或从 not_found 变 found：
   - reprocess affected lookup keys
   - 对新 resolved target 补 anchor price
   - rebuild 5m/1h `all/matched`

### 4.3 Public Token Radar excludes targetless rows

`token_radar_rows` 可以继续持久化 NIL/AMBIGUOUS rows，作为 diagnostics 和 audit 输入。

但 `/api/token-radar` 主 payload：

- `targets`: 只返回 `target_type/target_id` 非空 rows。
- `attention`: 只返回有 target 的 attention rows；如果 attention lane 当前全部 targetless，则返回空数组。
- `projection.unresolved`: 返回 targetless diagnostics 计数和样例 symbol，不作为主交易列表。

这样不破坏内部可观测性，但前端不再把 targetless mention 当可交易资产显示。

### 4.4 Read path overlays live market cache only

`/api/token-radar` 可以使用 `runtime.live_price_gateway.snapshot(target_type, target_id)` 覆盖 `row.live_market`：

- 有 live cache: 返回 `live/stale` snapshot。
- 没 live cache: 返回现有 `missing` payload。
- 不调用 OKX HTTP，不修改数据库。

Anchor price 仍来自 persisted factor snapshot / baseline，不由 API 临时抓 provider。

### 4.5 Price readiness remains target-first

Resolved target 的 market path：

1. anchor observation: 用 HTTP 补 "这条社交信号附近的一次价格"。
2. live market: 用 WS/CEХ polling 提供当前 price/market facts。
3. factor snapshot: 消费已经落库的 anchor/history/current facts。

Price path 不负责把 `$SYMBOL` 变成 target。

---

## 5. Non Goals

- 不在 frontend window switch 时做 OKX search。
- 不在 `/api/token-radar` read path 里做 symbol discovery 或写 DB。
- 不在 ingest transaction 里调用外部 provider。
- 不新增 Hot Worker + Background Worker 两套调度。
- 不把 GMGN 私有网页 search scraping 作为根因修复依赖。
- 不改变 US equity 过滤边界：`MarketInstrument` 继续不进入 crypto Token Radar 主列表。
- 不为了保留旧 public behavior 添加兼容开关。

---

## 7. Production Verification Snapshot

2026-05-12 在 Docker app 容器中重建后执行：

```bash
parallax ops reprocess-token-intents --window 24h --limit 2000 \
  --lookup-key symbol:DELL --lookup-key symbol:AAOI --lookup-key symbol:MRVL \
  --lookup-key symbol:EBAY --lookup-key symbol:BRKB --lookup-key symbol:BRK.B
parallax ops run-resolution-refresh --limit 120 --reprocess-limit 500
parallax ops rebuild-token-radar --window 5m --scope all --limit 300
parallax ops rebuild-token-radar --window 1h --scope all --limit 300
```

关键结果：

- targeted reprocess: `reprocessed_intents=6`, `resolved_intents=5`。
- resolution refresh: `lookups_selected=120`, `lookups_done=112`, `assets_written=16`, `reprocessed_intents=57`, `resolved_intents=53`；8 个 OKX 429 被记录为 provider errors，未中断整轮。
- latest DB `5m/all`: `total=26`, `identity_missing=2`, `nil=2`, `ambiguous=0`, `resolved=24`。
- latest DB `1h/all`: `total=279`, `identity_missing=29`, `nil=28`, `ambiguous=1`, `resolved=250`。
- HTTP `/api/token-radar` public payload: `5m public_targetless=0`, `1h public_targetless=0`。
- API anchor coverage: `5m ready=24/missing=2`, `1h ready=97/missing=3` for the returned public rows.

Compared with the pre-fix snapshot (`5m identity_missing=15`, `1h identity_missing=100`), the hot-window identity leak is reduced materially and targetless rows no longer appear in the public trading lists. Remaining NIL samples such as `RGB`/`HASHPOS` are true unresolved registry/provider coverage gaps, not frontend window-switch matching failures.

---

## 8. Acceptance Criteria

### Identity

- 新 launch symbol 初次 `not_found` 后，如果仍在 5m/1h hot window，下一轮 hot retry 不被 24h backlog 抢预算。
- discovery 从 `not_found` 变 `found` 后，同 lookup key 的 recent intents 在同一轮 reprocess。
- reprocess 后有 target 的 row 在下一次 hot projection 中进入 resolved lane。

### Market

- 对 resolved target，`/api/token-radar` 能返回 live cache overlay。
- 如果 live cache 还没有，anchor price ready 时前端应显示 anchored，而不是把它等同于 identity missing。
- 新解析 target 在同一轮 refresh 后至少尝试一次 anchor price。

### Public API

- `/api/token-radar` `targets` 和 `attention` 不包含 `target.target_id = null` 的主列表 row。
- `projection.unresolved` 暴露 diagnostics，例如 `identity_missing_count`, `nil_count`, `ambiguous_count`, `sample_symbols`。

### Verification

- FLAPPYFARM 类似 launch race 的测试：第一次 search 0 候选，hot retry 后 search 1 候选，最终 API 主列表有 target 且不再 identity missing。
- Resolved market overlay 测试：fake live gateway 有 cache 时，`/api/token-radar` 返回 `live_market.status="live"`。
- Targetless row filter 测试：NIL row 可存在于 `token_radar_rows`，但不进入 public `targets/attention`。

---

## 7. Operational Metrics

每次修复后看这组指标：

```sql
WITH latest AS (
  SELECT "window", scope, MAX(computed_at_ms) AS computed_at_ms
  FROM token_radar_rows
  WHERE projection_version = 'token-radar-v13-social-attention'
    AND scope = 'all'
    AND "window" IN ('5m','1h')
  GROUP BY "window", scope
),
rows AS (
  SELECT r.*
  FROM token_radar_rows r
  JOIN latest l
    ON l."window" = r."window"
   AND l.scope = r.scope
   AND l.computed_at_ms = r.computed_at_ms
)
SELECT
  "window",
  COUNT(*) AS rows,
  COUNT(*) FILTER (WHERE target_type IS NULL) AS persisted_target_null,
  COUNT(*) FILTER (WHERE data_health_json->>'identity'='missing') AS persisted_identity_missing,
  COUNT(*) FILTER (WHERE target_type IS NOT NULL AND data_health_json->>'market'='missing') AS resolved_market_missing
FROM rows
GROUP BY "window"
ORDER BY "window";
```

API-facing success is stricter:

- `targets + attention` returned by `/api/token-radar` should have `target.target_id IS NOT NULL`.
- `projection.unresolved.identity_missing_count` may be non-zero, but it is diagnostics, not a tradable row.

---

## 8. Open Questions

1. 是否把 class/file 直接从 `ResolutionRefreshWorker` rename 成 `ResolutionRefreshWorker`？建议 rename，避免旧 mental model 继续误导。
2. Hot `not_found` retry TTL 取 60 秒还是 90 秒？建议 60 秒，配合 existing lookup limit 和 provider rate limit 观察。
3. `projection.unresolved.sample_symbols` 默认给 10 个还是 20 个？建议 10 个，避免 API payload 膨胀。
