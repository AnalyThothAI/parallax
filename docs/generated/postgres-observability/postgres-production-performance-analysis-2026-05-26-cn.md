# PostgreSQL Production Performance Analysis - 2026-05-26

## 范围

本报告基于当前 Docker PostgreSQL 生产实例的实时观测，未打印或复制任何密钥值。

- 应用：`gmgn-twitter-intel`
- PostgreSQL 容器：`gmgn-twitter-intel-postgres-1`
- 应用容器：`gmgn-twitter-intel-app-1`
- 观测入口：`pg_stat_activity`、`pg_stat_statements`、`pg_stat_kcache`、`pg_qualstats`、pgBadger、PoWA、`/readyz`

## Queue Health Adapter

本轮已经落地全量 read-only queue health adapter。

- 新增 `app.runtime.queue_health`，统一读取 status queue 和 dirty-target queue。
- `readyz` worker status 和 lane status 都暴露 `queue_health`。
- `queue_depth` 继续保留，但现在来源于 `queue_health.queue_depth`。
- 不写业务表、不 claim queue、不改变 worker 行为。
- 支持 22 个 manifest queue worker：
  `asset_profile_refresh`、`enrichment`、`equity_event_brief`、
  `equity_event_page_projection`、`equity_event_story_projection`、
  `event_anchor_backfill`、`handle_summary`、`market_tick_current_projection`、
  `mention_semantics`、`narrative_admission`、`news_item_brief`、
  `news_page_projection`、`news_source_quality_projection`、
  `news_story_projection`、`notification_delivery`、`pulse_candidate`,
  `resolution_refresh`、`token_capture_tier`、`token_discussion_digest`、
  `token_image_mirror`、`token_profile_current`、`token_radar_projection`。

旧占位表 `live_market_target_set_dirty_targets` 已从运行时 manifest 和约束测试中移除，并从旧 active plan 的 allowlist 占位描述中清掉。

## Observability Tools

pgBadger 可用：

- 容器内版本：`pgBadger 13.2`
- 最新报告：`/Users/qinghuan/.gmgn-twitter-intel/reports/pgbadger/pgbadger-latest.html`
- 本次报告大小：约 2.7 MB
- 日志样本：36 条 normalized queries、1,551 queries、388 events、平均每 session query duration 约 12m33s
- pgBadger 发现：30 checkpoints、2 次 ShareLock 等待，合计约 4.715s，并记录 1 次 deadlock 事件。

PoWA 可用，且已补齐本地 coalesced history：

- `powa-web` 在 `127.0.0.1:8888` 正常响应并跳转登录页。
- 业务库已加载 `pg_stat_statements`、`pg_stat_kcache`、`pg_qualstats`、`pg_wait_sampling`。
- `shared_preload_libraries` 包含 `pg_stat_statements,powa,pg_stat_kcache,pg_qualstats,pg_wait_sampling`。
- `powa` repository 数据库已安装 `powa 5.1.1`。
- `scripts/powa_configure.sh` 已设置本地 GUC：`powa.coalesce=5`、`powa.frequency=5min`，同时保留 `powa_servers` 的 7 天 retention 配置。
- 最新验证：`powa_statements_history_current` 有 838 行 current snapshot 数据，`powa_statements_history` 有 4,902 行 coalesced history 数据。
- 根因备注：本地 server `powa_take_snapshot(0)` 使用 PostgreSQL GUC `powa.coalesce`，不是 `powa_servers.powa_coalesce`；此前 history 为 0 是因为 GUC 仍为默认 100，快速 6 次 snapshot 不会触发 coalesce。

## 当前生产状态

`/readyz` 当前为 `ok=true`，`reason_count=0`，worker manifest 数 34。Queue health 暴露出实际业务 backlog：

| Lane | Status | Queue Depth | Due | Running | Failed | Blocked | 重点 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| identity_market_fact | blocked | 3126 | 1652 | 49 | 1428 | 1423 | resolution refresh + event anchor 明显积压 |
| agent | blocked | 1307 | 18 | 13 | 36 | 1192 | Pulse/enrichment/semantics 有 dead 或 terminal unavailable |
| projection | ok | 61 | 1 | 0 | 0 | 0 | 普通 dirty projection 基本可追上 |
| notification | idle | 0 | 0 | 0 | 0 | 0 | 当前无积压 |

重点 queue 表：

| Worker | Table | 现象 |
| --- | --- | --- |
| `resolution_refresh` | `token_discovery_dirty_lookup_keys` | total 1708，due 1657，running 50，with_error 12，max_attempt 817 |
| `event_anchor_backfill` | `event_anchor_backfill_jobs` | failed 1413，expired 10，done 28713 |
| `pulse_candidate` | `pulse_agent_jobs` | dead 649，pending 21，running 1，done 301 |
| `enrichment` | `enrichment_jobs` | dead 368，done 92 |
| `mention_semantics` | `token_mention_semantics` | semantic_unavailable 176，retryable_error 36，queued 11 |

结论：当前系统不是 readyz 级别不可用，但已有明确的 worker backlog/terminal failure 压力。Projection lane 不是主要瓶颈；identity/market fact lane 和 agent lane 才是当前需要优先处理的业务积压源。

## PostgreSQL 性能问题

### P0 - Token Radar rank-set query 是当前最大 PostgreSQL 成本

`pg_stat_statements` Top 1：

```sql
SELECT *
FROM token_radar_target_features
WHERE projection_version = $1
  AND "window" = $2
  AND scope = $3
ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
```

观测：

- calls 4618
- total_exec_time 395,952 ms
- mean_exec_time 85.741 ms
- rows 10,344,264
- shared_blks_read 3,409,497
- `pg_stat_kcache` exec CPU 约 378.56s

单次 `EXPLAIN (ANALYZE, BUFFERS)` 显示实际走 `Seq Scan + Sort`：

- 对 `token_radar_target_features` 顺序扫描
- 过滤后返回约 4,837 行
- 每次读取宽行，包含多个 JSONB payload 列

结构判断：

- 现有 rank index 是 `(projection_version, window, scope, lane, rank_score DESC, identity_id)`。
- 查询排序多了 `latest_event_received_at_ms DESC`，且 `SELECT *` 读取宽 JSONB 列，导致 planner 更倾向 seq scan。
- 即使单次 25-85ms 看似可接受，4618 次累计后就是主成本。

建议：

- 后续 SQL 修复优先处理该链路：rank-set 查询不要 `SELECT *` 取全 JSONB，先取 rank 所需窄列，详情 payload 延后按需加载。
- 评估覆盖排序的索引：`(projection_version, window, scope, lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC)`。
- 如果 rank-set 是每轮 projection 重复全量读取，优先检查是否可以只刷新受影响 window/scope，或缓存同一 run 内 rank-set。

### P0 - `token_intent_lookup_keys` 按 `intent_id` 删除缺索引

`pg_stat_statements`：

- calls 8901
- total_exec_time 92,231 ms
- mean_exec_time 10.362 ms
- shared_blks_read 17,417,504

`EXPLAIN` 明确显示：

```text
Delete on token_intent_lookup_keys
  -> Seq Scan on token_intent_lookup_keys
       Filter: intent_id = ...
```

结构判断：

- 表主键是 `(lookup_key, intent_id)`，另有 `idx_token_intent_lookup_keys_lookup(lookup_key)`。
- 但 `replace_lookup_keys()` 每次按 `intent_id` 删除旧 key，没有 `intent_id` 前缀索引。

建议：

- 后续 SQL 修复应新增 `token_intent_lookup_keys(intent_id)` 索引，或把写入策略改成 diff/upsert 后删除多余 key。
- 这条是低风险高收益项，因为当前删除每次扫全表。

### P1 - Event anchor done-mark 扫描两个表

`pg_stat_statements`：

- calls 7224
- total_exec_time 150,600 ms
- mean_exec_time 20.847 ms

`EXPLAIN` 显示 `mark_ready_jobs_done` 对 `event_anchor_backfill_jobs` 和 `enriched_events` 都走 seq scan 后 hash join：

- `event_anchor_backfill_jobs` 过滤 `status <> 'done'`
- `enriched_events` 过滤 `capture_method <> 'unavailable' AND tick_id IS NOT NULL AND tick_lag_ms IS NOT NULL`

结构判断：

- 现有 job 索引主要服务 `status='pending'` due/expired。
- `mark_ready_jobs_done` 用的是 `status <> 'done'`，与 partial index 不匹配。
- `enriched_events` 没有针对“ready anchor”条件的 partial index。

建议：

- 先确认是否还需要高频扫“非 done job”。如果只是清理历史 ready job，应改成状态驱动/小批 repair，而不是每轮扫。
- 若保留，增加匹配条件的 partial index，或者把 ready transition 放到产生 ready anchor 的事务中直接 mark job done。

### P1 - Projection run stale cleanup 高频更新成本偏高

`pg_stat_statements`：

- calls 4616
- total_exec_time 75,330 ms
- mean_exec_time 16.319 ms
- shared_blks_read 17,771,119

`pg_qualstats` 也显示 `projection_runs.status/projection_name/projection_version/started_at_ms` 是高过滤条件。

结构判断：

- 当前索引 `(projection_name, projection_version, started_at_ms DESC)` 可用，但 `status='running'` 是 filter，不在索引前缀。
- `mark_stale_running_runs()` 每轮被调用频率高；即使每次最终更新 0 行，也会反复读索引和 heap。

建议：

- 后续可加 partial index：
  `(projection_name, projection_version, started_at_ms) WHERE status='running'`。
- 更进一步，把 stale cleanup cadence 降低，避免每个 projection tick 都扫。

### P1 - Macro observations request-time dedupe 会写 temp

`pg_stat_statements` mean time Top 1：

- calls 30
- mean_exec_time 352.996 ms
- rows 660,139
- shared_blks_read 248,962
- temp_blks_written 112,049

结构判断：

- 查询使用 `row_number() OVER (PARTITION BY concept_key, observed_at ORDER BY source_priority DESC, ingested_at_ms DESC)`。
- 这是 request-time dedupe/排序型负载，已经触发大量 temp blocks。

建议：

- 短期可调高该路径 statement 的 `work_mem` 或减少请求窗口。
- 架构上更符合 CQRS 的做法是把 deduped latest macro view 物化到 read model，而不是 HTTP 请求时重算。

### P2 - 高频 equity provider/document upsert churn

Top calls：

- `equity_provider_documents` SELECT/INSERT/UPSERT 各约 478,486 calls。
- 单次很快，但累计 CPU 和 I/O 可见。

结构判断：

- 这是 batch 处理或 fetch/process worker 的高频逐行模式。
- 当前不是最大慢点，但会持续制造 WAL、autovacuum 和 index maintenance 压力。

建议：

- 后续检查 batch upsert 是否可以改成 set-based write。
- 保留幂等约束，不为省 SQL 次数破坏 idempotency。

## 表和索引压力

最大表/索引：

- `token_radar_snapshot_audit_202605` total 6473 MB，index 4646 MB。
- `market_ticks_default` total 2035 MB。
- `events` total 1773 MB，index 1236 MB。
- `token_radar_rank_history_202605` total 1055 MB。
- `raw_frames` total 771 MB。

疑似低使用索引候选：

- `token_radar_snapshot_audit_20_factor_version_window_scope_c_idx` 261 MB，`idx_scan=0`
- `token_radar_rank_history_2026_projection_version_window_sco_idx` 152 MB，`idx_scan=0`
- `token_radar_rank_history_2026_target_type_target_id_recorde_idx` 112 MB，`idx_scan=0`
- `idx_raw_frames_channel_received` 45 MB，`idx_scan=0`

注意：`idx_scan=0` 只能作为候选，不能直接删除。需要确认统计 reset 时间、罕见查询、约束语义和 operator class 用途。

Dead tuple 压力：

- `token_intent_lookup_keys` dead 17,868，dead_pct 11.05。
- `event_anchor_backfill_jobs` dead 5,423，dead_pct 15.26。
- `equity_provider_documents` dead 3,424，dead_pct 16.83。
- `token_profile_current` dead 1,692，dead_pct 15.94。
- `token_capture_tier` dead_pct 14.01，`last_autovacuum` 为空。

结论：当前不是单纯“连接数太多”或“锁等爆炸”，而是高频 worker 写入/更新和若干缺索引/宽行全量读取共同造成 CPU、buffer、WAL、vacuum 压力。

## 连接和锁

当前 `pg_stat_activity` 没有发现实时 blocker。

连接分布：

- `gmgn_wake` idle 16
- `gmgn_worker` idle 14
- `gmgn_api` idle 2
- 每个 `worker_lock:*` 基本 1 条 idle 连接
- PoWA collector 1 条 idle 连接

结论：

- 当前瞬时不是连接耗尽事故。
- `application_name` 已具备基础归因，但仍偏粗：普通 worker 查询多显示为 `gmgn_worker`，锁连接显示为 `worker_lock:*`。后续如果要把 Top SQL 直接归因到具体 worker，需要在 worker DB session 或事务级别设置更细粒度 `application_name`。

## 优先级建议

1. P0：先修 `token_intent_lookup_keys(intent_id)` 缺索引，这是最明确的低风险收益。
2. P0：改 Token Radar rank-set 查询，避免 `SELECT *` 宽行 seq scan，必要时加排序匹配索引。
3. P1：重构 `mark_ready_jobs_done`，避免高频扫 `event_anchor_backfill_jobs + enriched_events`。
4. P1：给 `projection_runs` running stale cleanup 加 partial index 或降低 cleanup cadence。
5. P1：处理 backlog：`token_discovery_dirty_lookup_keys` due 1600+ 且 max_attempt 800+，需要查 provider/rate/backoff/poison-key 策略。
6. P1：清理或重新分类 dead/terminal agent queue：Pulse dead 649、enrichment dead 368、semantics unavailable 176。
7. P2：评估最大历史/audit 表分区 retention 与低使用索引。

## 当前结论

PostgreSQL 已经出现实际性能压力，但不是“数据库已经坏掉”的状态。最准确的判断是：

- 数据流仍在跑，`readyz` 通过。
- worker backlog 已经实质存在，且 queue health 现在能直接定位到表和 worker。
- 数据库主要压力来自少数高频宽读、缺索引删除、queue/job 清理扫描和 request-time 重计算。
- PoWA/pgBadger 已经装上并能工作；pgBadger 已产出报告，PoWA 已能生成 coalesced history，可作为后续趋势分析入口。
