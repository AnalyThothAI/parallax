# Token Radar Storage Root Fix Clean Reset Plan

## 目标

把 Token Radar 从 `token_radar_rows` 单表承担 current read model、历史 rank、完整 JSONB audit 三种职责，硬切成三张独立 read model 表：

- `token_radar_current_rows`: 只保存当前可服务页面/API/CLI 的最新集合。
- `token_radar_rank_history`: 保存轻量 rank/decision 历史，不存完整 snapshot。
- `token_radar_snapshot_audit`: 保存完整 factor snapshot audit，按 `computed_at_ms` 分区。

旧 `token_radar_rows` 和 `token_radar_retention_runs` 不迁移、不兼容、不保留运行时 fallback。迁移完成后从 0 重新同步 Token Radar 派生数据。

## 根因

详情页卡顿的数据库根因不是业务数据量本身大，而是物理存储被旧设计放大：

- hot projection 高频写入完整 `factor_snapshot_json`。
- `token_radar_rows` 长期追加历史 batch，单表同时服务当前读取和历史/settlement。
- JSONB snapshot 进入 TOAST，表、索引、TOAST 三部分一起膨胀。
- retention 只能小批量 DELETE，不能从结构上阻止继续膨胀。
- current 页面读取虽然只需要最新几千行，却会落到一个历史巨表和大索引上。

因此根治必须改变存储边界，而不是只加索引或调 autovacuum。

## 落地方案

### Schema hard cut

新增 migration `20260523_0085_token_radar_storage_root_fix.py`：

- 创建 `token_radar_current_rows`。
- 创建 partitioned `token_radar_rank_history` 和默认分区。
- 创建 partitioned `token_radar_snapshot_audit` 和默认分区。
- 创建 `token_radar_storage_maintenance_runs`。
- 创建 current read、target lookup、rank history、snapshot audit settlement 索引。
- `DROP TABLE IF EXISTS token_radar_rows CASCADE`。
- `DROP TABLE IF EXISTS token_radar_retention_runs`。
- 清空 `token_radar_target_first_seen`。
- 删除 Token Radar projection coverage/offset/run 控制行。

### Runtime write path

`TokenRadarRepository.publish_rows(...)` 替代旧 `replace_rows(...)`：

- 对 `(projection_version, window, scope)` 加事务 advisory lock。
- stale writer guard 同时读取 current rows 和 coverage watermark，0-row 新批次也能阻断旧 writer。
- current 表先删除同 key 旧 rows，再插入本轮最新 rows。
- rank history 和 snapshot audit 按当前 `computed_at_ms` 写入。
- first-seen 只从 `token_radar_target_first_seen` 读取/更新，不再从历史大表回填。
- factor snapshot contract 在写入前强校验，旧 snapshot 形状直接拒绝。

### Runtime read path

所有 runtime consumer 读取新表：

- 当前 Radar / asset flow / pulse candidate / profile source / image source 读 `token_radar_current_rows`。
- settlement、factor diagnostics、需要 point-in-time snapshot 的路径读 `token_radar_snapshot_audit`。
- 不再有 `token_radar_rows` runtime reference。

### Ops hard reset

新增：

```bash
uv run gmgn-twitter-intel ops clean-reset-token-radar-storage --dry-run
uv run gmgn-twitter-intel ops clean-reset-token-radar-storage --execute
```

该命令可重复执行：

- drop legacy Token Radar storage。
- truncate new Token Radar read models 和 `token_radar_target_first_seen`。
- 删除 Token Radar projection controls。
- 不触碰 facts: `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, `enriched_events`。

Cross-domain cleanup commands, such as CEX Binance cleanup, may report impacted Token Radar rows but must not delete Token Radar tables directly. Run this clean reset after those fact-level cleanups.

## 成功标准

- 最新 schema 中不存在 `token_radar_rows` / `token_radar_retention_runs`。
- runtime source 中 `token_radar_rows` 只允许出现在 explicit reset/drop 代码和历史 migrations。
- 新 projection 能写入 `token_radar_current_rows`, `token_radar_rank_history`, `token_radar_snapshot_audit`。
- current read path 不扫描历史 snapshot/audit 表。
- old prune/backfill-first-seen CLI 被移除。
- fact ingestion 不被 migration/reset 清理。

## 验证命令

```bash
uv run pytest tests/unit/test_token_radar_repository.py tests/unit/domains/token_intel/test_token_radar_first_seen.py -q
uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py -q
uv run pytest tests/unit/test_cli.py tests/unit/test_ops_backfill_commands.py tests/unit/domains/token_intel/test_token_radar_storage_reset.py -q
uv run pytest tests/unit/test_postgres_schema.py::test_alembic_revision_ids_are_unique tests/unit/test_postgres_schema.py::test_alembic_revision_graph_has_single_head tests/unit/test_postgres_schema.py::test_token_radar_storage_root_fix_migration_hard_cuts_old_storage -q
uv run ruff check src/gmgn_twitter_intel/domains/token_intel src/gmgn_twitter_intel/platform/db/postgres_audit.py tests/unit/test_token_radar_repository.py
```

## 运行备注

真实数据切换前先确认：

```bash
uv run gmgn-twitter-intel config
```

只报告 `config_path` / `workers_config_path`、布尔状态和表大小，不打印 secret。执行 `clean-reset-token-radar-storage --execute` 后，重启/触发 Token Radar worker 从 facts 重新构建。
