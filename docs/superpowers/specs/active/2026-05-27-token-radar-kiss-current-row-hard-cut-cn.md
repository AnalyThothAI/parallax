# Token Radar KISS Current Row Hard Cut Spec

## 背景

Token Radar 当前在线榜单链路把几类不同问题混在一起：

- 在线服务需要的当前榜单；
- projection 最近一次尝试是否成功；
- target feature / rank input 的增量缓存；
- rank history / snapshot audit 的冷历史；
- downstream dirty target 的副作用；
- payload hash hydration race 的补偿逻辑。

这导致一个坏状态：`token_radar_rank_source_events` 和
`token_radar_target_features` 仍然新鲜，但 `token_radar_current_rows` 陈旧；
coverage failed 后 API 仍可能把旧 rows 包装成 `fresh`；dirty queue 被
`payload_hash changed during selected-row hydration` 堆满。

本 spec 从第一性原理重新收敛 Token Radar 发布模型：在线榜单只需要“当前可服务
rows”和“发布状态”。其它表若存在，必须是 material facts、projection-private
cache，或显式 lazy evidence，不能参与在线 current 服务。

## 第一性原则

1. PostgreSQL material facts 是唯一业务真相。
   `events`、`token_intents`、`token_intent_resolutions`、
   `asset_identity_*`、`market_ticks`、`enriched_events` 等事实表可重放出
   Token Radar。
2. CQRS read model 必须可删可重建。
   `token_radar_current_rows` 和 publication state 是服务用 read model，不是事实。
3. 在线服务只读当前 read model。
   API、CLI、Pulse、notifications、runtime repair 不读
   `token_radar_target_features`、`token_radar_rank_history`、
   `token_radar_snapshot_audit` 或 `token_radar_rank_source_events` 来替代 current。
4. `NOTIFY` 只是 wake hint。
   worker 每次醒来都从 DB 读取 bounded work，不依赖内存消息保证 correctness。
5. 失败必须 fail closed。
   最近一次发布失败时，有旧 current rows 也只能标记为 `stale`；没有旧 rows
   标记为 `failed`。绝不伪装成 `fresh`。

## 目标

- `token_radar_current_rows` 是唯一在线榜单服务表。
- 用一个明确的 publication state 表表达每个
  `(projection_version, window, scope)` 的当前成功 generation 和最近尝试结果。
- current rows 发布为一次稳定 generation 的原子 replace。
- 最近发布失败时保留上一版 current rows，但 API/worker 明确暴露 stale/failed。
- `token_radar_rank_source_events` 只做 projection 输入和 lazy evidence/detail。
- `token_radar_target_features` 若保留，只是 projection 私有 cache。
- 删除 rank-then-hydrate、payload_hash retry、audit-as-current、legacy rebuild、
  fallback reader。
- 从 hot path 移除 `rank_history` / `snapshot_audit`；本轮不建设冷历史。

## 非目标

- 不建设新的历史榜单产品。
- 不保留旧 API freshness 语义。
- 不提供 feature flag 或兼容 reader。
- 不为了审计保留在线发布副作用。需要审计时从 material facts 重放，或另立一个
  独立冷 projection spec。

## 表模型

### 在线服务表：`token_radar_current_rows`

用途：当前可服务榜单 rows。

新增/保留关键字段：

- `projection_version TEXT NOT NULL`
- `"window" TEXT NOT NULL`
- `scope TEXT NOT NULL`
- `lane TEXT NOT NULL`
- `rank BIGINT NOT NULL`
- `target_type_key TEXT NOT NULL`
- `identity_id TEXT NOT NULL`
- `generation_id TEXT NOT NULL`
- `published_at_ms BIGINT NOT NULL`
- `source_frontier_ms BIGINT NOT NULL`
- `computed_at_ms BIGINT NOT NULL`
- `payload_hash TEXT NOT NULL`

约束：

- 同一个 `(projection_version, window, scope)` 在线集合内只允许一个
  `generation_id`。
- current rows 不承载发布失败状态。
- current rows 不写 rank history / audit 副作用。

### 发布状态表：`token_radar_publication_state`

用途：每个 `(projection_version, window, scope)` 的当前成功发布和最近尝试结果。

本轮 hard cut 删除现有 `token_radar_projection_coverage`，新建
`token_radar_publication_state`。不再使用 coverage 作为业务概念。

字段：

- `projection_version TEXT NOT NULL`
- `"window" TEXT NOT NULL`
- `scope TEXT NOT NULL`
- `current_generation_id TEXT`
- `current_published_at_ms BIGINT`
- `current_source_frontier_ms BIGINT`
- `current_row_count BIGINT NOT NULL DEFAULT 0`
- `current_source_rows BIGINT NOT NULL DEFAULT 0`
- `latest_attempt_generation_id TEXT`
- `latest_attempt_status TEXT NOT NULL CHECK (latest_attempt_status IN ('ready', 'failed'))`
- `latest_attempt_started_at_ms BIGINT`
- `latest_attempt_finished_at_ms BIGINT`
- `latest_attempt_error TEXT`
- `updated_at_ms BIGINT NOT NULL`
- primary key `(projection_version, "window", scope)`

状态语义：

- `ready`：最近一次尝试成功；`current_generation_id` 必须等于
  `latest_attempt_generation_id`。
- `failed` + `current_generation_id IS NOT NULL`：上一版 rows 仍可展示，但状态是
  `stale`。
- `failed` + `current_generation_id IS NULL`：没有可服务 rows，状态是 `failed`。
- 缺失 state：状态是 `pending` 或 `missing`，不能返回 `fresh`。

### Projection 私有 cache：`token_radar_target_features`

用途：减少每轮从 material facts 直接 join/aggregate 的成本。

约束：

- 只允许 Token Radar projection writer 写。
- 只允许 Token Radar projection builder 读。
- 不允许 API、Pulse、notifications、CLI read surface、runtime repair 把它当 current
  fallback。
- 不再有 `legacy_needs_rebuild`、stale rank input rebuild、payload hash hydration。

### Lazy evidence：`token_radar_rank_source_events`

用途：

- projection 构建 target feature 的输入；
- detail/evidence 页面按当前 row 明确查询 top edges。

约束：

- 不服务在线榜单。
- lazy evidence 查询必须 bounded by current row key + limit。
- 不返回 provider raw payload 或大 JSON。

### 移除 hot path 的表

本轮不再由 Token Radar 在线发布链路写或读：

- `token_radar_rank_history`
- `token_radar_snapshot_audit`

hard cut migration 必须 drop 这两张表。任何仍需要历史审计或 factor settlement
的用例必须另写冷 projection spec，从 material facts 或 publication state 重建。
本轮不得保留 runtime reader、operator fallback、或测试 fixture 依赖。

## 系统性清理范围

Schema drop 前必须清理所有 runtime 和测试中的旧 surface：

- 删除 `token_radar_projection_coverage` 的所有 runtime reader/writer，调用点改为
  `token_radar_publication_state`。
- 删除 `token_radar_rank_history` / `token_radar_snapshot_audit` 的所有 runtime
  reader/writer，包括 factor evaluation settlement 和 hard reset/manifest 清单。
- 删除 rank input legacy rebuild CLI 和所有 `legacy_needs_rebuild` 恢复测试。
- 删除 selected-row hydration retry 及其 fake/test helper。
- 删除 dirty queue 中把 claim/lease 编码进 `payload_hash` 的 `:claimed:` 模式；如果同一模式存在于相邻 dirty queue，本轮一并清理，不设 runtime 例外。
- 更新 docs、architecture tests、schema tests、integration tests，让旧表和旧字符串无法回归。

## 发布流程

### 成功发布

1. Worker 读取 bounded work item：固定 windows/scopes、dirty hint、interval catch-up。
2. Projection builder 构建一个 in-memory generation：
   - 从 facts / rank source / private cache 读取一次稳定输入；
   - 在内存中 rank；
   - 在内存中生成完整 current row payload；
   - 生成 `generation_id`。
3. Repository 在一个事务内：
   - 获取 `(projection_version, window, scope)` advisory lock；
   - 删除该 set 的旧 current rows；
   - 插入同一 `generation_id` 的新 current rows；
   - upsert `token_radar_publication_state` 为 `ready`；
   - commit。
4. commit 后发送 `token_radar_updated` wake hint。

### 失败发布

1. 如果 build 或 publish 失败，current rows 保持不变。
2. Repository upsert `token_radar_publication_state`：
   - `latest_attempt_status = 'failed'`
   - `latest_attempt_generation_id = attempted_generation_id`
   - `latest_attempt_error = bounded error string`
   - current success fields 保持不变。
3. API 和 worker consumers 读取 state 后返回 `stale` 或 `failed`。

`attempted_generation_id` 必须在 build 前即可确定；build 阶段失败也必须写 failed
state，不能只捕获 publish 阶段异常。

### 没有 rows 的成功发布

如果输入合法且结果为空，仍然是一次成功 generation：

- current rows set 为空；
- state 为 `ready`；
- `current_row_count = 0`；
- API 返回 `fresh` empty。

## API freshness 语义

`fresh` 只在以下条件全部满足时成立：

- publication state 存在；
- `latest_attempt_status = 'ready'`；
- current rows 的 `generation_id` 与 `current_generation_id` 一致；
- 同一个 `(projection_version, window, scope)` 没有混合 generation rows。

返回规则：

- ready + matching rows：`projection.status = "fresh"`。
- failed + current exists：`projection.status = "stale"`，附带
  `latest_attempt_error`。
- failed + no current：`projection.status = "failed"`。
- missing state + no rows：`projection.status = "pending"`。
- missing state + rows：`projection.status = "stale"`。

## Dirty target 语义

Dirty target 是 wake/coalescing 优化，不是业务状态。

- `payload_hash` 只表示 source fingerprint。
- claim/lease 状态不得编码进 `payload_hash`。
- current publish 不依赖“本轮 claim 到 dirty target”才运行。
- enqueue while leased 必须清 lease，让新 fingerprint 可被重新 claim。

## 删除的旧路径

必须删除 runtime 中的以下路径和字符串：

- `payload_hash changed during selected-row hydration`
- `_rank_and_hydrate_selected_rows`
- `_hydrate_ranked_rows`
- `load_target_feature_payloads_for_ranked_keys`
- `rebuild_rank_inputs_full`
- `list_rank_input_rebuild_keys`
- `stale_rank_input_count`
- `rank_input_readiness_for_work_items`
- `latest_snapshot_audit_rows`
- audit-as-current reader
- rank history current fallback
- dirty target `:claimed:` payload hash mutation

## 验收标准

- `token_radar_current_rows` 是唯一在线榜单服务表。
- `token_radar_publication_state` 是唯一 freshness/last-failure 状态表。
- current publish 和 state ready 在同一个事务中提交。
- 最近一次 failed 不能被 API 表示成 fresh。
- `rank_history` / `snapshot_audit` 不在 runtime 中读写，schema 中不存在。
- architecture tests 阻止旧 hydration/rebuild/fallback 字符串回归。
- source scan 对 `src/gmgn_twitter_intel/app` 和 `src/gmgn_twitter_intel/domains`
  不再命中旧 coverage、snapshot audit、rank history、selected-row hydration、
  legacy rebuild、`:claimed:`。
- tests 明确覆盖：build 失败写 failed state、publish 失败保留 current、API failed
  不 fresh、Pulse/notifications/runtime repair 不从 stale rows 派生动作、factor
  evaluation 不再依赖 snapshot audit。
- live 诊断中 1h/24h all/matched publication state ready，current rows 每个 set
  只有一个 generation。
