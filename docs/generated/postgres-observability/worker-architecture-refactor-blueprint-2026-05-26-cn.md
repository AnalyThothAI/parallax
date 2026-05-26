# Worker 架构整理蓝图, 2026-05-26

## 目标

在不改变业务逻辑、不改事实表语义、不改变现有 worker 输出的前提下，把
当前扁平的 34 个 worker 整理成更可读、可维护、可观测的运行架构。

核心方向不是立刻合并代码，而是先把运行时从“worker 列表”升级为
“lane + manifest + contract”的模型：

- 人看系统时先看 lane，再 drill down 到 worker。
- 代码仍保持小 worker，避免一次性大重构。
- 每个 worker 的事实表、read model、dirty queue、side effect ledger、
  idempotency key、wake in/out 都显式登记。
- 架构测试继续守住 single writer、provider IO outside DB session、
  bounded catch-up、side-effect audit 等约束。

## 成熟方法论

### DDD Bounded Context

按业务边界组织 worker，而不是按“有多少定时任务”组织 worker。

当前上下文基本已经存在：

- `ingestion`: 公共流输入和规范化。
- `asset_market`: 身份、市场 tick、profile、图片、capture tier。
- `token_intel`: Token Radar 投影和搜索读模型。
- `narrative_intel`: admission、semantics、digest。
- `news_intel`: news facts、story、brief、page。
- `equity_event_intel`: SEC/IR 事件、story、brief、page。
- `pulse_lab`: agent decision read model。
- `notifications`: rule 和 delivery。
- `macro_intel` / `cex_market_intel`: 独立市场视图。

整理原则：跨 context 的 worker 不互相写 read model；跨 context 通信只通过
PostgreSQL facts/read models/dirty targets/wake hints。

### CQRS + Kappa

当前系统已经是 PostgreSQL-first Kappa/CQRS，应该继续强化：

- Facts 是业务真相。
- Read models 可重建，且 exactly one runtime writer。
- Dirty targets 是控制面，不是业务事实。
- NOTIFY 只是 wake hint；每个 listener 必须 bounded catch-up。

整理原则：所有 worker 在 manifest 中声明 `writes_facts`、`writes_read_models`
和 `writes_control_plane`，架构测试根据声明校验冲突。

### Ports And Adapters

worker 不应该承载 provider client 细节、SQL 拼接细节、LLM SDK 细节。

目标形态：

```text
WorkerBase / LaneSupervisor
  -> UseCase / Service
  -> Repository Port / Provider Port / Agent Gateway
  -> PostgreSQL / External Provider / LLM SDK
```

整理原则：worker 是 orchestration shell；业务规则在 domain service；
provider IO 在 adapter；持久化在 repository。

### Pipes And Filters

很多 worker 本质是一个有序数据管道：

```text
source -> normalize -> fact -> projection -> agent -> delivery
```

整理原则：每条业务链路用 stage map 表达，worker 名字只代表一个 stage。
对 news/equity 这种多 stage 链路，用 lane supervisor 展示链路状态，而不是
把每个 worker 都作为顶层概念暴露给 operator。

### Process Manager / Saga

Pulse、News brief、Equity brief、Notification delivery 都是多步流程：
claim、reserve capacity、external call、validate、persist audit、publish result。

整理原则：这些流程必须有 durable attempt ledger；worker 重启后从 ledger
恢复，而不是从内存状态恢复。

### Bulkhead / Backpressure

当前 worker 数量多，最大的运维风险不是逻辑错误，而是连接数、LLM 容量、
provider rate limit、projection churn 相互影响。

整理原则：

- 每条 lane 有独立并发预算。
- 每条 lane 有 DB pool budget。
- Agent lane 统一经过 `AgentExecutionGateway`。
- 连接和 provider backpressure 作为 lane status 暴露。

### Outbox / Inbox / Idempotent Consumer

当前系统已经大量使用 dirty queue、delivery rows、run ledgers。整理时要把
这些约束显式化：

- 外部副作用 worker 必须有 delivery/run ledger。
- 多写事实表必须有 logical idempotency key。
- 每个 dirty target 必须有唯一键、lease、retry/backoff、retention/SLO。

## 当前 Worker 分类

### Lane 1: Ingest Lane

职责：接收外部输入，写入原始事实或 provider-natural-key facts。

Workers:

- `collector`: GMGN public stream -> `IngestService` facts。
- `market_tick_stream`: OKX DEX WS -> `market_ticks(tier1_ws)`。
- `market_tick_poll`: REST quote providers -> `market_ticks(tier2_poll)`。
- `news_fetch`: configured feeds -> news provider/item facts。
- `equity_event_fetch`: SEC/IR providers -> equity provider/document facts。

设计要求：

- Provider IO 不持有 DB session。
- Append-only fact 或 provider-natural-key upsert。
- 失败状态进入 source/fetch run audit，不进入 read model。

### Lane 2: Identity And Market Fact Lane

职责：身份发现、profile/source cache、图片镜像、event anchor lifecycle。

Workers:

- `resolution_refresh`
- `asset_profile_refresh`
- `token_image_mirror`
- `event_anchor_backfill`
- `equity_event_source_reconcile`
- `equity_event_process`
- `news_item_process`

设计要求：

- 多写事实表必须靠 logical key/idempotency key 防重复。
- lifecycle update 必须只更新自己拥有的状态列。
- 不直接写下游 read model，改为 enqueue dirty target 或 emit wake hint。

### Lane 3: Projection Lane

职责：从 facts/control-plane 构建可重建 read models。

Workers:

- `token_capture_tier`
- `market_tick_current_projection`
- `token_profile_current`
- `token_radar_projection`
- `narrative_admission`
- `news_story_projection`
- `news_page_projection`
- `news_source_quality_projection`
- `equity_event_story_projection`
- `equity_event_page_projection`
- `macro_view_projection`
- `cex_oi_radar_board`

设计要求：

- 每个 read model exactly one writer。
- 空 dirty queue 不做大表兜底扫描。
- projection output 必须可重建。
- 大表 projection 必须有 partition/retention/index SLO。

### Lane 4: Agent Lane

职责：所有 LLM / paid provider / semantic side-effect。

Workers:

- `enrichment`
- `mention_semantics`
- `token_discussion_digest`
- `news_item_brief`
- `equity_event_brief`
- `pulse_candidate`
- `handle_summary`

设计要求：

- 先 reserve agent capacity，再 claim 会消耗 attempt 的 DB job。
- 所有调用必须经过 `AgentExecutionGateway`。
- 每次执行写 domain audit/run ledger。
- provider no-start 是 backpressure，不消耗业务 retry。

### Lane 5: Notification Lane

职责：规则评估和外部投递。

Workers:

- `notification_rule`
- `notification_delivery`

设计要求：

- rule evaluation 和 delivery 分离。
- `notifications.dedup_key` 防重复通知。
- `notification_deliveries(notification_id, channel_id)` 是 delivery log。
- delivery worker 必须从 durable rows 恢复。

### Lane 6: Runtime Support / Cache Lane

职责：不写业务表或只写 cache/control-plane。

Workers:

- `live_price_gateway`

设计要求：

- 不写 facts/read models。
- cache-only fanout，重启可丢。
- 读 bounded target set，不扫描大 read model。

## 推荐的代码组织

### 1. Worker Manifest

新增只读 manifest，不改变 worker 实现：

```python
@dataclass(frozen=True)
class WorkerManifest:
    name: str
    lane: WorkerLane
    domain: str
    role: WorkerRole
    writes_facts: tuple[str, ...]
    writes_read_models: tuple[str, ...]
    writes_control_plane: tuple[str, ...]
    side_effect_ledgers: tuple[str, ...]
    idempotency_keys: tuple[str, ...]
    advisory_lock_key: int | None
    wakes_on: tuple[str, ...]
    wakes_out: tuple[str, ...]
```

位置建议：

```text
src/gmgn_twitter_intel/app/runtime/worker_manifest.py
```

现有 `worker_registry.py` 继续保留 canonical class map；manifest 是
运行语义层，不替代 import registry。

### 2. Lane Supervisor

新增 lane-level view，不改 worker loop：

```text
WorkerScheduler
  -> WorkerBase instances
  -> LaneStatusView
      -> ingest-lane
      -> identity-lane
      -> projection-lane
      -> agent-lane
      -> notification-lane
      -> support-lane
```

第一阶段只聚合状态：

- enabled/running count
- last success/error
- active run age
- queue backlog
- DB connections by application_name
- agent capacity/circuit snapshot

### 3. Lane Config Defaults

当前 `workers.yaml` 是 per-worker flat config。目标是兼容式扩展：

```yaml
workers:
  lanes:
    ingest:
      statement_timeout_seconds: 30
      db_pool_budget: 8
    projection:
      statement_timeout_seconds: 120
      db_pool_budget: 10
    agent:
      statement_timeout_seconds: 30
      max_concurrency: 4
  token_radar_projection:
    lane: projection
    batch_size: 20
```

迁移期保持旧字段优先级：per-worker override > lane default > global default。

### 4. Contract Tests

在现有架构测试基础上增加：

- 每个 canonical worker 必须有 manifest entry。
- 每个 read model 只能有一个 manifest writer。
- side-effect worker 必须声明 ledger。
- 多写 fact table 必须声明 idempotency key。
- 每个 `wakes_on` 必须有 bounded interval catch-up。
- agent worker 必须声明 agent lane 和 run ledger。

## 可以合并的只是“运行面”，不是业务逻辑

建议合并为 supervisor/status，不建议立刻把业务代码揉成大 worker。

### News Lane

保留：

- `news_fetch`
- `news_item_process`
- `news_story_projection`
- `news_item_brief`
- `news_page_projection`
- `news_source_quality_projection`

新增：

```text
news-lane status:
  fetch -> process -> story -> brief -> page/source-quality
```

收益：operator 看到一条 news pipeline，而不是 6 个散点。

### Equity Event Lane

保留：

- `equity_event_source_reconcile`
- `equity_event_fetch`
- `equity_event_process`
- `equity_event_story_projection`
- `equity_event_brief`
- `equity_event_page_projection`

新增：

```text
equity-event-lane status:
  reconcile -> fetch -> process -> story -> brief -> page
```

收益：明确 SEC/IR event-first pipeline，避免和 News Intel 混淆。

### Agent Lane

保留每个 domain 的 agent worker，但运行预算统一：

```text
agent-lane:
  narrative.mention_semantics
  narrative.discussion_digest
  news.item_brief
  equity_event.brief
  pulse.pipeline
  social.event_enrichment
```

收益：provider outage 时不会让不同业务 worker 各自空转、抢预算、烧 retry。

## 当前需要保持独立的 worker

这些 worker 不建议合并业务逻辑：

- `collector`: continuous WS 生命周期特殊。
- `market_tick_stream`: 长连接 provider 状态特殊。
- `market_tick_poll`: REST quote retry/rate-limit 模型不同。
- `token_radar_projection`: 大表 projection 和 ranking 主链路，必须单独观测。
- `pulse_candidate`: agent decision 风险高，必须保留独立 ledger 和预算。
- `notification_delivery`: 外部投递必须和 rule evaluation 分离。

## 推荐迁移顺序

### Phase 0: 文档和 manifest

不改 runtime 行为。

- 增加 `worker_manifest.py`。
- 把当前 `docs/WORKERS.md` 表格结构化进 manifest。
- 架构测试覆盖 manifest 完整性。

### Phase 1: Status 按 lane 展示

不改 worker loop。

- `/readyz` 和 `/api/status` 增加 `lanes` 聚合字段。
- 保留现有 `workers` 字段，前端/CLI 不破坏。

### Phase 2: Config lane defaults

不改业务逻辑。

- 读取 `workers.lanes.*` defaults。
- per-worker config 继续兼容。
- 增加配置校验，防止 lane budget 总和超过 Postgres 连接预算。

### Phase 3: Queue health 标准化

不改表语义。

- 为 dirty targets/job tables 增加统一只读 health adapter。
- 每个 worker status 暴露 due/pending/running/dead/oldest_due。
- 先读现有表，不新增业务写入。

### Phase 4: Backpressure 统一

行为仍等价，但运维面更清晰。

- Agent lane 统一 no-start/backoff/retry 语义。
- Projection lane 增加 DB query budget 和 slow-query labels。
- Ingest lane 增加 provider/source-health status 聚合。

### Phase 5: 可选的 lane supervisor

只在前几步稳定后做。

- supervisor 管状态聚合、预算、启动顺序。
- domain worker 仍拥有 `run_once()` 业务逻辑。
- 不把 news/equity/pulse 的业务步骤硬合并成一个大函数。

## 最终形态

理想运行视图：

```text
ingest-lane          healthy   5 workers   provider ok   backlog low
identity-lane        partial   7 workers   OKX 429       retry cooling
projection-lane      degraded  12 workers  slow radar    queue bounded
agent-lane           degraded  7 workers   provider 522  circuit open
notification-lane    disabled  2 workers   notifications disabled
support-lane         healthy   1 worker    cache fanout
```

理想代码心智：

```text
worker_registry.py   -> what class exists
worker_manifest.py   -> what each worker owns
workers.yaml         -> how each lane/worker runs
WorkerScheduler      -> starts/stops worker instances
LaneStatusView       -> operator-facing runtime map
domain services      -> business logic
repositories         -> DB access
provider adapters    -> external IO
```

这条路线的关键好处是：先提升可维护性和可观测性，再决定是否做代码合并。
不会破坏业务逻辑，也不会把已经正确分离的 domain worker 合成难以测试的大任务。
