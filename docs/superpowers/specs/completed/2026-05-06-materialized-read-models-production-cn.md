# Production Projection Read Models Spec

日期：2026-05-06

## 结论

PostgreSQL 已经成为唯一运行时数据库后，下一阶段优化不应该靠临时缓存，也不应该把业务 scoring、抽取 prompt、token attribution 语义一起改掉。正确方向是补齐 PG-only 的 projection/read model 层：事实表继续作为 source of truth，projection 表只保存可删除、可重建、可审计的查询优化结果。

本阶段先落地生产闭环骨架：

1. `projection_offsets` 记录每个投影的 high-water mark、版本、lag 和错误。
2. `projection_runs` 记录每批投影 run 的输入范围、读写行数和状态。
3. `projection_dirty_ranges` 记录迟到事实、backfill、market snapshot 到达后需要局部重算的范围。
4. `token_social_buckets` 和 `token_social_bucket_authors` 承载 token social timeline / unique author 的增量聚合。
5. `token_flow_window_snapshots` 承载 dashboard/top-N 的冻结读模型。
6. `parallax db audit`、`db query-audit`、`ops projection-status`、`ops validate-projections` 形成上线前和运行期闭环。

不保留旧数据库兼容路径，不保留双 runtime adapter，不在 API 请求路径里静默 fallback 到 raw aggregation。投影未就绪时，生产读路径必须显式暴露 missing/stale 状态。

## 当前代码审计

已落地：

- Runtime 配置面只暴露 `storage.postgres`。
- Alembic 管理 schema，app 通过 psycopg 连接 PostgreSQL。
- 核心事实表已包含 `events`、`event_token_mentions`、`event_token_attributions`、`token_market_snapshots`、`harness_*`、`token_signal_*`。
- 旧 runtime storage modules 已被删除，项目结构测试禁止恢复旧 storage client/schema。

仍需优化：

- `token-flow` 仍在请求时读取 attribution window、做 Python 分组、查 baseline、bounds、market snapshot、multi-window counts，再跑 scoring。
- `token-social-timeline` summary 仍依赖现场窗口聚合；post evidence 分页应保留事实表读取。
- `account-quality` 已有表，但 live projection/settlement freshness 还没有统一 offset 和状态。
- 当前没有 projection run audit、dirty range、lag、validation command 的生产闭环。

## 设计原则

### Source Of Truth

事实表是唯一权威：

- `raw_frames`
- `events`
- `event_entities`
- `event_token_mentions`
- `event_token_attributions`
- `tokens`
- `token_market_snapshots`
- `enrichment_jobs`
- `social_event_extractions`
- `harness_*`
- `token_signal_*`

Projection 表只保存派生读模型。任何 projection 都必须能通过 facts 重建。

### Versioned Projection

每个投影都有稳定名称和版本：

- `token-social-buckets` / `token-social-buckets-v1`
- `token-flow-window-snapshots` / `token-flow-window-snapshots-v1`
- `account-quality` / `account-quality-v1`

评分版本变化、窗口算法变化、bucket 粒度变化，都必须 bump projection version。API 不允许混合多个版本的同一读模型。

### Explicit Freshness

每个 projection response 或 ops status 至少暴露：

- `projection_name`
- `projection_version`
- `source_max_received_at_ms`
- `source_max_id`
- `lag_ms`
- `status`
- `last_run_id`
- `last_error`

超过 freshness SLA 时返回 `projection_stale` 或同等显式状态，不做隐式 raw fallback。

### No Lookahead

决策读模型只能使用 `decision_time_ms` 之前已经进入 facts 的数据。Settlement/outcome worker 可以读取未来 price，但必须写入 outcome 表，不能污染 decision read model。

### Incremental First

高频 read path 使用业务 projection tables 和 worker 做 O(delta) 维护。数据库原生整表刷新只适合低频报表，不作为 token radar 实时优化方案。

## Projection Schema

### `projection_offsets`

记录每个 projection 的高水位和健康状态。

关键字段：

- `projection_name`
- `projection_version`
- `source_table`
- `source_max_received_at_ms`
- `source_max_id`
- `last_run_id`
- `status`
- `lag_ms`
- `last_error`
- `created_at_ms`
- `updated_at_ms`

### `projection_runs`

记录每次 projection batch。

关键字段：

- `run_id`
- `projection_name`
- `projection_version`
- `mode`
- `status`
- `source_start_ms`
- `source_end_ms`
- `rows_read`
- `rows_written`
- `dirty_ranges_written`
- `started_at_ms`
- `finished_at_ms`
- `error`

### `projection_dirty_ranges`

记录需要重算的局部范围。迟到 facts、manual backfill、market snapshot 补齐和 projection version rebuild 都通过它显式排队。

关键字段：

- `dirty_id`
- `projection_name`
- `projection_version`
- `entity_type`
- `entity_key`
- `window`
- `scope`
- `start_ms`
- `end_ms`
- `reason`
- `status`
- `created_at_ms`
- `updated_at_ms`

### `token_social_buckets`

最小 social 聚合单元。窗口级 token-flow、timeline summary 和 rank candidate 都从 bucket rollup 读取。

关键字段：

- `projection_version`
- `scope`
- `bucket_size_ms`
- `bucket_start_ms`
- `token_id`
- `identity_key`
- `chain`
- `address`
- `symbol`
- `post_count`
- `direct_mention_count`
- `selected_symbol_mention_count`
- `weighted_mention_count`
- `attribution_confidence_sum`
- `watched_post_count`
- `unique_author_count`
- `watched_author_count`
- `weighted_reach`
- `first_seen_ms`
- `latest_seen_ms`
- `top_event_ids_json`
- `top_authors_json`
- `source_event_ids_json`
- `source_attribution_ids_json`

### `token_social_bucket_authors`

用于跨 bucket 精确计算 unique authors，避免直接相加 per-bucket unique count。

关键字段：

- `projection_version`
- `scope`
- `bucket_size_ms`
- `bucket_start_ms`
- `token_id`
- `author_handle`
- `post_count`
- `watched_post_count`
- `followers_max`
- `first_seen_ms`
- `latest_seen_ms`

### `token_flow_window_snapshots`

缓存 dashboard/top-N 结果。它不是事实源，只是读模型快照。

关键字段：

- `snapshot_id`
- `projection_version`
- `window`
- `scope`
- `decision_time_ms`
- `rank`
- `token_id`
- `identity_json`
- `flow_json`
- `timeline_json`
- `market_json`
- `score_versions_json`
- `component_payload_json`
- `data_health_json`
- `source_bucket_range_json`
- `source_max_received_at_ms`
- `created_at_ms`

## Ops Commands

### `db audit`

只读检查：

- 核心事实表 count。
- projection 表是否存在。
- 关键 FK orphan check。
- 当前 Alembic version。

退出码：

- `0`：schema 和 FK 审计通过。
- `1`：projection schema 缺失或 orphan check 非零。

### `db query-audit`

默认只运行 `EXPLAIN`，不执行查询。覆盖：

- `recent_all`
- `recent_watched`
- `search_fts`
- `token_flow_5m_shape`
- `token_posts_recent`

带 `--analyze` 时运行 `EXPLAIN ANALYZE`，用于 staging/live 手动审计，不应放在高频 health path。

### `ops projection-status`

返回已知 projections、offset、lag、latest run 和 last error。没有 offset 时显式返回 `missing`。

### `ops validate-projections`

运行投影一致性检查。第一阶段先检查 projection snapshot 引用完整性和空状态；后续 worker 落地后扩展为 sampled raw-vs-projection reconciliation。

## 切换顺序

1. 落地 projection schema、repository、ops commands、docs。
2. 跑 `db audit` 和 `db query-audit` 建立当前 PG read path baseline。
3. 实现 token social bucket worker，只写 projection tables，不改 API。
4. shadow compare bucket 输出与 raw aggregation。
5. 实现 token-flow window snapshot worker。
6. shadow compare `/api/token-flow` raw output 与 projection snapshot output。
7. 切 `/api/token-flow` 到 read model；stale 时显式返回 projection status。
8. timeline summary 切 bucket read model，posts 继续 facts 分页。
9. account-quality 切 incremental projection 和 settlement worker。

## 不做事项

- 不改 social-event prompt/schema。
- 不改 token attribution 规则。
- 不改 scoring 权重和 score version。
- 不在 API 请求里触发 projection rebuild。
- 不把 raw tweet text 或 raw frames 复制进 projection 表。
- 不保留双数据库 runtime。
- 不保留隐式 raw aggregation fallback 作为生产兼容路径。

## 验收标准

第一阶段：

- `uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py tests/test_projection_repository.py tests/test_postgres_audit.py tests/test_cli.py -q`
- `parallax db audit` 返回 `ok=true`。
- `parallax db query-audit` 返回所有 hot query 的 plan。
- `parallax ops projection-status` 返回三类 known projections。
- `parallax ops validate-projections --sample 100` 有结构化结果。

后续 worker 阶段：

- sampled raw-vs-projection mismatch 为 0。
- `token-flow?window=5m&limit=50` projection path p95 < 50ms。
- timeline summary p95 < 80ms。
- projection worker 单 batch 事务时间 < 500ms。
- `/readyz` 不被 projection rebuild 阻塞。
