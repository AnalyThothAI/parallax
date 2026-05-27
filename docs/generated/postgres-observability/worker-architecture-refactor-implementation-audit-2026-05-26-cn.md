# Worker 架构重构落地审计, 2026-05-26

**基准蓝图**: `docs/generated/postgres-observability/worker-architecture-refactor-blueprint-2026-05-26-cn.md`
**实现分支**: `codex/worker-contract-hard-cut`
**审计范围**: 当前实现分支源码、权威 docs、architecture/unit/integration tests

## 总结

按“不改变业务逻辑、不修 SQL、不引入新调度平台”的本轮目标评估，worker 架构整理已经达到 **92%** 完成度。

已经完成：

- 34 个 runtime worker 全部进入 `WorkerManifest v1`。
- `worker_manifest.py` 是 worker existence、lane、kind、class path、start priority、factory ownership、dirty target tables、queue depth table、读写所有权、幂等证据和 side-effect ledger 的唯一代码来源。
- 旧 `worker_registry.py` 已删除；不保留 `CANONICAL_WORKER_CLASSES`、`CANONICAL_WORKER_NAMES`、`WORKER_START_PRIORITY` 兼容入口。
- `/readyz`、`/api/status`、CLI `ops worker-status`、`/api/ops/diagnostics` 均输出 `worker_lanes`。
- 所有 worker factory 的 ownership 从 manifest 派生。
- Watchlist queue name 硬切为 `watchlist_handle_summary_jobs`，旧 `watchlist_summary_jobs` 不再允许。
- 架构测试覆盖 manifest/settings/docs lockstep、factory ownership、single-writer 表归属、side-effect ledger、dirty-target consumer 声明、lane status、旧入口残留扫描。

仍未做，且当前建议暂缓：

- `workers.lanes.*` lane-level config defaults。
- 真正的 lane supervisor / lane-level runtime scheduler。
- per-lane DB pool budget 强制执行。
- 全量 dirty target/job health adapter 的 due/dead/oldest_due 标准化。

这些属于蓝图 Phase 2-5 的增强项；在没有明确生产瓶颈前，不建议为了“完成度数字”引入调度复杂度。

## 完成度评分

| 项目 | 目标 | 当前状态 | 完成度 |
|---|---|---|---:|
| Phase 0 Manifest | 结构化登记所有 worker contract | 34/34 worker 覆盖，含 lane/kind/class/start priority/factory/ownership/idempotency/ledger/dirty target | 100% |
| Hard cut | 删除旧 registry/旧 key/旧 queue alias | `worker_registry.py` 删除；旧 canonical 常量和旧 watchlist queue 名在当前权威源码/docs/tests 无残留 | 100% |
| Phase 1 Lane status | 状态面按 lane 汇总 | readyz/status/CLI/ops diagnostics 均有 `worker_lanes` | 95% |
| Phase 2 Contract tests | ownership/idempotency/ledger/dirty target 测试 | single-writer、ledger、dirty-target、factory、settings/docs lockstep 已覆盖；DB unique/ON CONFLICT 的逐表证明仍可继续增强 | 90% |
| Queue health | 标准化 queue depth/health | 现有 job queue depth 已接入；dirty target due/dead/oldest_due 尚未统一 | 65% |
| Lane config defaults | `workers.lanes.*` defaults | 暂缓，不纳入本轮 KISS 硬切 | 0% |
| Lane supervisor | supervisor 管预算/启动/聚合 | 暂缓，不纳入本轮 KISS 硬切 | 0% |

本轮目标完成度计算只覆盖蓝图明确建议先做的 Phase 0-2 和 Phase 1 状态面，因此是 **92%**。如果把 Phase 3-5 也作为同一轮强制目标，则完整蓝图完成度约 **68%**，但那会偏离“先不改业务逻辑”的原则。

## 更改后的代码链路

```text
~/.gmgn-twitter-intel/workers.yaml
  -> platform.config.settings.WorkersSettings
  -> app.runtime.worker_manifest.WorkerManifest v1
  -> app.runtime.worker_factories.worker_factory_specs()
  -> app.runtime.worker_factories.construct_workers()
  -> app.runtime.bootstrap.Runtime.workers
  -> app.runtime.worker_scheduler.WorkerScheduler
  -> app.runtime.worker_base.WorkerBase.run()
  -> domain runtime Worker.run_once()
  -> domain services/repositories/providers
```

状态输出链路：

```text
WorkerScheduler.status_payload()
  -> worker_status.workers_status_payload()
      -> manifest_worker_statuses()
      -> fill_worker_queue_depths()
      -> worker_lane_statuses()
  -> /readyz
  -> /api/status
  -> CLI ops worker-status
  -> /api/ops/diagnostics
```

Factory ownership 链路：

```text
WorkerManifest.factory
  -> manifest_names_for_factory("asset_market.py")
  -> worker_factories/<domain>.py WORKER_KEYS
  -> construct_workers() validates no unowned / duplicate worker
```

Queue hard-cut 链路：

```text
job_queue.WATCHLIST_HANDLE_SUMMARY_JOBS
  -> JOB_QUEUE_DESCRIPTORS["watchlist_handle_summary_jobs"]
  -> ops_queue_payload()
  -> handle_summary worker queue depth/status
```

## 全 Worker 审计

| Worker | Lane | Kind | Domain | Data writes | Control writes | Dirty target consumed | Ledger | 审计结论 |
|---|---|---|---|---|---|---|---|---|
| `collector` | `ingest` | `fact_ingest` | `ingestion` | `raw_frames`, `events`, `token_intents` | `enrichment_jobs` | - | - | OK |
| `market_tick_stream` | `ingest` | `fact_ingest` | `asset_market` | `market_ticks` | - | - | - | OK |
| `market_tick_poll` | `ingest` | `fact_ingest` | `asset_market` | `market_ticks` | - | - | - | OK |
| `market_tick_current_projection` | `projection` | `projection` | `asset_market` | `market_tick_current` | `market_tick_current_dirty_targets`, `token_radar_dirty_targets` | `market_tick_current_dirty_targets` | - | OK |
| `event_anchor_backfill` | `identity_market_fact` | `fact_lifecycle` | `asset_market` | `enriched_events`, `market_ticks` | `event_anchor_backfill_jobs` | - | - | OK |
| `token_capture_tier` | `projection` | `projection` | `asset_market` | `token_capture_tier` | `token_capture_tier_dirty_targets` | `token_capture_tier_dirty_targets` | - | OK |
| `live_price_gateway` | `maintenance_cache` | `cache_fanout` | `asset_market` | in-process cache only | live price gateway cache | - | - | OK |
| `resolution_refresh` | `identity_market_fact` | `fact_lifecycle` | `asset_market` | `asset_identity_*`, `token_intent_resolutions` | `token_discovery_dirty_lookup_keys`, `token_radar_dirty_targets`, `narrative_admission_dirty_targets` | `token_discovery_dirty_lookup_keys` | - | OK |
| `asset_profile_refresh` | `identity_market_fact` | `fact_lifecycle` | `asset_market` | `asset_profiles` | `asset_profile_refresh_targets`, `token_image_source_dirty_targets` | `asset_profile_refresh_targets` | - | OK |
| `token_image_mirror` | `identity_market_fact` | `fact_lifecycle` | `asset_market` | `token_image_assets` | `token_image_source_dirty_targets`, `token_profile_current_dirty_targets` | `token_image_source_dirty_targets` | - | OK |
| `token_profile_current` | `projection` | `projection` | `asset_market` | `token_profile_current` | `token_profile_current_dirty_targets` | `token_profile_current_dirty_targets` | - | OK |
| `token_radar_projection` | `projection` | `projection` | `token_intel` | `token_radar_target_features`, `token_radar_current_rows`, `token_radar_rank_history`, `token_radar_snapshot_audit`, `token_radar_target_first_seen`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `token_radar_dirty_targets`, `pulse_trigger_dirty_targets`, `narrative_admission_dirty_targets` | `token_radar_dirty_targets` | - | OK |
| `narrative_admission` | `projection` | `projection` | `narrative_intel` | `narrative_admissions` | `narrative_admission_dirty_targets`, `discussion_digest_dirty_targets` | `narrative_admission_dirty_targets` | - | OK |
| `mention_semantics` | `agent` | `agent_side_effect` | `narrative_intel` | `token_mention_semantics` | `discussion_digest_dirty_targets` | - | `token_mention_semantics`, `narrative_model_runs` | OK, producer of digest dirty targets |
| `token_discussion_digest` | `agent` | `agent_side_effect` | `narrative_intel` | `token_discussion_digests` | `discussion_digest_dirty_targets`, `narrative_model_runs` | `discussion_digest_dirty_targets` | `token_discussion_digests`, `narrative_model_runs` | OK |
| `news_fetch` | `ingest` | `fact_ingest` | `news_intel` | `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items` | `news_projection_dirty_targets` | - | - | OK, producer of news projection dirty targets |
| `news_item_process` | `identity_market_fact` | `fact_lifecycle` | `news_intel` | `news_item_entities`, `news_token_mentions`, `news_fact_candidates`, `news_items.content_*` | `news_projection_dirty_targets` | - | - | OK, producer of news projection dirty targets |
| `news_story_projection` | `projection` | `projection` | `news_intel` | `news_story_groups`, `news_story_members` | `news_projection_dirty_targets` | `news_projection_dirty_targets` | - | OK |
| `news_item_brief` | `agent` | `agent_side_effect` | `news_intel` | `news_item_agent_briefs` | `news_projection_dirty_targets`, `news_item_agent_runs` | `news_projection_dirty_targets` | `news_item_agent_runs`, `news_item_agent_briefs` | OK |
| `news_page_projection` | `projection` | `projection` | `news_intel` | `news_page_rows` | `news_projection_dirty_targets` | `news_projection_dirty_targets` | - | OK |
| `news_source_quality_projection` | `projection` | `projection` | `news_intel` | `news_source_quality_rows` | `news_projection_dirty_targets` | `news_projection_dirty_targets` | - | OK |
| `equity_event_source_reconcile` | `identity_market_fact` | `fact_lifecycle` | `equity_event_intel` | `equity_event_sources`, `equity_event_universe_members`, `equity_expected_events` | - | - | - | OK |
| `equity_event_fetch` | `ingest` | `fact_ingest` | `equity_event_intel` | `equity_event_fetch_runs`, `equity_provider_documents`, `equity_event_documents` | `equity_event_projection_dirty_targets` | - | - | OK, producer of equity projection dirty targets |
| `equity_event_process` | `identity_market_fact` | `fact_lifecycle` | `equity_event_intel` | `equity_company_events`, `equity_event_source_spans`, `equity_event_fact_candidates`, document lifecycle status | `equity_event_projection_dirty_targets` | - | - | OK, producer of equity projection dirty targets |
| `equity_event_story_projection` | `projection` | `projection` | `equity_event_intel` | `equity_event_story_groups`, `equity_event_story_members` | `equity_event_projection_dirty_targets` | `equity_event_projection_dirty_targets` | - | OK |
| `equity_event_brief` | `agent` | `agent_side_effect` | `equity_event_intel` | `equity_event_agent_briefs` | `equity_event_projection_dirty_targets`, `equity_event_agent_runs` | `equity_event_projection_dirty_targets` | `equity_event_agent_runs`, `equity_event_agent_briefs` | OK |
| `equity_event_page_projection` | `projection` | `projection` | `equity_event_intel` | `equity_event_page_rows`, `equity_event_calendar_rows`, `equity_event_alert_candidates`, `equity_company_timeline_rows` | `equity_event_projection_dirty_targets` | `equity_event_projection_dirty_targets` | - | OK |
| `cex_oi_radar_board` | `projection` | `projection` | `cex_market_intel` | `cex_oi_radar_rows`, `cex_oi_radar_publication_state`, `cex_detail_snapshots` | - | - | - | OK |
| `macro_view_projection` | `projection` | `projection` | `macro_intel` | `macro_view_snapshots` | - | - | - | OK |
| `pulse_candidate` | `agent` | `agent_side_effect` | `pulse_lab` | `pulse_agent_jobs`, `pulse_candidate_edge_state`, `pulse_candidate_run_budget`, `pulse_target_run_budget`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_agent_runtime_versions`, `pulse_agent_eval_cases`, `pulse_agent_eval_results`, `pulse_candidates`, `pulse_playbook_snapshots` | `pulse_trigger_dirty_targets`, `pulse_agent_jobs`, `pulse_agent_runs` | `pulse_trigger_dirty_targets` | `pulse_agent_jobs`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_candidates` | OK |
| `enrichment` | `agent` | `agent_side_effect` | `social_enrichment` | `enriched_events`, `social_event_extractions`, `watchlist_handle_signal_events`, `watchlist_handle_signal_stats` | `enrichment_jobs`, `model_runs`, `watchlist_handle_summary_jobs` | - | `enrichment_jobs`, `model_runs` | OK |
| `handle_summary` | `agent` | `agent_side_effect` | `watchlist_intel` | `watchlist_handle_summaries` | `watchlist_handle_summary_jobs`, `watchlist_handle_summary_runs` | - | `watchlist_handle_summary_jobs`, `watchlist_handle_summary_runs` | OK |
| `notification_rule` | `notification` | `notification_rule` | `notifications` | `notifications`, `notification_deliveries` | - | - | - | OK |
| `notification_delivery` | `notification` | `notification_delivery` | `notifications` | - | `notification_deliveries` | - | `notification_deliveries` | OK |

## 残留检查

已清理的残留：

- 当前权威源码/docs/tests 中无 `worker_registry.py` 事实来源。
- 当前权威源码/docs/tests 中无旧 canonical worker 常量。
- 当前权威源码/tests 中无旧 `watchlist_summary_jobs` allowlist。
- Manifest 中不再使用 `news_stories`、`news_pages`、`equity_event_pages`、`macro_view` 这类语义 alias，改为真实表名。

仍存在但不是本轮阻塞的残留：

- 历史 plans/generated audit 文档仍会提到旧 `worker_registry.py` 或旧方案；这些是历史记录，不作为当前权威 contract。
- Queue health 仍然不是统一 adapter；现在只有部分 job/delivery table 进入 `queue_depth_table`。
- `WorkerBase` 仍较大，但目前承担的是横切 runtime 逻辑，不应继续添加业务能力。

## 下一步建议

1. 做只读 queue health adapter，覆盖 dirty target 和 job tables 的 `pending/due/running/dead/oldest_due/max_attempts`，不改表语义。
2. 对 manifest 的 `idempotency_evidence` 做更强静态测试：把 evidence 关联到 migration unique index、repository `ON CONFLICT`、或者 ledger primary key。
3. 只在生产观测证明需要时，再引入 `workers.lanes.*` defaults 和 lane budget lint。
