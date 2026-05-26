# Worker Contract Spec Review, 2026-05-26

## 结论

用户提出的原则应该继续深入，而且方向正确：

```text
Worker = 输入契约 + 状态所有权 + 幂等策略 + 事务边界 + 并发预算 + 可观测性
```

但在本项目里，不应该照搬 Kafka / Temporal / Celery 的完整模型，也不应该
马上做大平台式重构。`gmgn-twitter-intel` 当前是 PostgreSQL-first Kappa/CQRS，
事实表和 read model 已经是核心执行平面。最佳路线是：

```text
保留现有小 worker
  -> 增加只读 WorkerManifest
  -> 增加 lane-level status view
  -> 用架构测试校验 ownership/idempotency/ledger
  -> 再按真实瓶颈决定是否引入 lane budget / supervisor
```

不要把这次整理变成“新建一个万能 BaseWorker”或者“引入一个新调度平台”。

## 工业界共识核验

以下原则是成熟实践，可以采纳：

- 至少一次执行是默认现实，worker 必须幂等。Sidekiq 明确建议 job 要
  idempotent and transactional。
- Celery 把 late acknowledgement 与 task idempotency 绑定：幂等任务才适合
  执行后 ack。
- Temporal durable/retry 模型下 Activity 可能重复执行，因此外部副作用必须
  幂等或有稳定 idempotency key。
- Kafka consumer group 的顺序边界是 partition，不是全局；本项目如果用
  PostgreSQL queue 模拟顺序，应明确 target/window/source 这类 ordering key。
- PostgreSQL `FOR UPDATE SKIP LOCKED` 适合 queue-like 多消费者抢占，但官方
  提醒它不是普通一致性查询工具。
- PostgreSQL 观测应同时使用 `pg_stat_activity`、`pg_locks`、
  `pg_stat_statements`、`EXPLAIN (ANALYZE, BUFFERS)`、慢查询日志。

参考：

- Sidekiq Best Practices: https://github.com/sidekiq/sidekiq/wiki/Best-Practices
- Celery Tasks: https://docs.celeryq.dev/en/main/userguide/tasks.html
- Confluent Kafka consumer groups: https://docs.confluent.io/kafka/design/consumer-design.html
- PostgreSQL SELECT locking clause: https://www.postgresql.org/docs/current/sql-select.html
- PostgreSQL monitoring: https://www.postgresql.org/docs/current/monitoring.html
- PostgreSQL pg_stat_statements: https://www.postgresql.org/docs/current/pgstatstatements.html
- PostgreSQL EXPLAIN: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL auto_explain: https://www.postgresql.org/docs/current/auto-explain.html
- PostgreSQL VACUUM: https://www.postgresql.org/docs/current/sql-vacuum.html
- PoWA: https://powa.readthedocs.io/
- pgBadger: https://github.com/darold/pgbadger

## 当前项目已经做对的部分

### 运行时横切能力已经集中

`WorkerBase` 已统一：

- worker loop
- `run_once()` 业务边界
- soft/hard timeout
- backoff
- advisory lock
- wake wait
- telemetry hooks
- status payload
- cooperative close

这符合“统一 runtime/harness”的方向。

风险是：`WorkerBase` 已接近可接受上限，不应继续加入 lane budget、queue
health、agent execution、业务 cleanup 状态。

### DB pool 和 application_name 已有基础

`DBPoolBundle` 已分：

- `api_pool`
- `worker_pool`
- `lock_pool`
- `wake_pool`
- `tool_pool`

并且 worker session 会设置 `application_name=worker:<name>`，这对
pg_stat_activity、pgBadger、PoWA 归因很关键。

### Agent side effect 已有集中网关

`AgentExecutionGateway` 已承担：

- lane bulkhead
- RPM
- reservation
- circuit breaker
- timeout
- audit metadata

这符合“外部副作用不要散落在每个 worker 里”的方向。

### 幂等不是空白

当前系统大量使用更贴近业务语义的幂等机制：

- `raw_frames.payload_hash`
- `events.logical_dedup_key`
- `market_ticks` dedupe key
- `news_provider_items(source_id, source_item_key)`
- `news_items(provider_item_id)`
- `equity_provider_documents(source_id, provider_document_key)`
- `notifications.dedup_key`
- `notification_deliveries(notification_id, channel_id)`
- 各类 dirty target primary key / lease / attempt_count
- `pulse_agent_runs` / `pulse_agent_run_steps`
- `news_item_agent_runs`
- `equity_event_agent_runs`
- `narrative_model_runs`
- `watchlist_handle_summary_runs`

因此不建议新增一个全局 `worker_idempotency` 表作为通用答案。

## 需要修正用户 spec 的地方

### 1. Command Worker 这个名字要本项目化

用户 spec 里的 `Command Worker` 更适合订单/账户/支付这类命令系统。

本项目更准确的分类是：

```text
Fact Ingest Worker
Fact Lifecycle Worker
Projection Worker
Agent Side-effect Worker
Notification Delivery Worker
Cache Fanout Worker
Maintenance / Rebuild Worker
```

原因：本项目没有通用 command bus；业务真相主要来自 provider observations、
deterministic resolver、market facts、news/equity facts。

### 2. Outbox Relay Worker 暂时不是当前核心

当前系统没有外部 broker outbox relay。PostgreSQL `NOTIFY` 是 wake hint，
不是可靠事件流；事实和 dirty target 才是恢复来源。

KISS 结论：

- 不新增 outbox relay。
- 不把 NOTIFY 升级成“事件真相”。
- 未来如果要对外发布事件，再设计 outbox relay。

### 3. Rebuild / Replay Worker 应该是 ops path，不是常驻 worker 类别

当前 read models 应该可 rebuild，但不代表每个 read model 都需要一个常驻
`rebuild worker`。

KISS 结论：

- runtime worker 负责增量 bounded catch-up。
- rebuild/replay 走 explicit ops command。
- rebuild 必须拿相关 advisory lock，避免和 runtime writer 竞争。

### 4. 全局 worker_idempotency 表不适合现在

全局表会变成第二套真相：

```text
worker_idempotency says processed
but domain table says not terminal
```

这会让恢复语义更难审计。当前更好的做法是：

```text
manifest 声明 idempotency evidence
architecture test 静态检查 unique key / ON CONFLICT / ledger / dirty target lease
```

### 5. 每 worker 一个 DB role 暂缓

理论上 DB 权限隔离很好，但当前 Docker 生产只有一个 `gmgn_app` DSN，app、
migrate、workers 共用 operator config。直接拆成 34 个 worker DB role 会引入
大量部署复杂度。

KISS 替代：

- 先用 manifest + static SQL ownership tests。
- 继续依赖 `application_name=worker:<name>` 做观测归因。
- 保留 `tool_pool read_only`。
- 真要做 DB role，第一步只拆 `api_readonly` / `app_writer`，不要 per-worker。

## 建议的 WorkerKind

```python
class WorkerKind(StrEnum):
    FACT_INGEST = "fact_ingest"
    FACT_LIFECYCLE = "fact_lifecycle"
    PROJECTION = "projection"
    AGENT_SIDE_EFFECT = "agent_side_effect"
    NOTIFICATION_DELIVERY = "notification_delivery"
    CACHE_FANOUT = "cache_fanout"
    MAINTENANCE = "maintenance"
```

这些比 `command | projection | relay | side_effect | rebuild` 更贴近项目。

## WorkerManifest v1

第一版 manifest 必须只读，不驱动 runtime 行为。

```python
@dataclass(frozen=True)
class WorkerManifest:
    name: str
    domain: str
    lane: str
    kind: WorkerKind

    input_contract: tuple[str, ...]
    ordering_keys: tuple[str, ...]

    writes_facts: tuple[str, ...]
    writes_read_models: tuple[str, ...]
    writes_control_plane: tuple[str, ...]

    idempotency_evidence: tuple[str, ...]
    side_effect_ledgers: tuple[str, ...]

    dirty_target_tables: tuple[str, ...]
    advisory_lock_key: int | None
    wakes_on: tuple[str, ...]
    wakes_out: tuple[str, ...]
```

不要把所有 runtime knobs 都塞进 manifest。`interval_seconds`、`batch_size`、
`timeout`、`concurrency` 仍归 `workers.yaml` 管；manifest 只管 ownership 和
contract。

## KISS 落地顺序

### Phase 1: 只读 manifest

不改业务逻辑。

- 新增 `worker_manifest.py`。
- 从现有 `docs/WORKERS.md`、`worker_registry.py`、architecture tests 迁移事实。
- 纠正命名漂移，例如 `watchlist_handle_summary_*`。

验收：

- manifest 覆盖所有 canonical workers。
- manifest 和 `worker_registry.py` 名字一致。
- manifest 和 `WorkersSettings` 名字一致。
- manifest 和 `docs/WORKERS.md` 名字一致。

### Phase 2: 架构测试

不改 runtime 行为。

测试：

- 每个 read model 只能有一个 `writes_read_models` owner。
- 每个 side-effect worker 必须声明 ledger。
- 每个 dirty-target consumer 必须声明 dirty target table。
- dirty target repository 必须存在 lease/attempt/`FOR UPDATE SKIP LOCKED`。
- 多写 fact table 必须声明 `idempotency_evidence`。

### Phase 3: LaneStatusView

不改 worker loop。

在 `/readyz` 或 `/api/status` 增加：

```text
lanes:
  ingest:
    workers_total
    workers_running
    last_error
    provider_state
  projection:
    workers_total
    workers_running
    slowest_worker
    queue_due_count
  agent:
    workers_total
    circuit_open_count
    capacity_denied_total
```

保留原来的 `workers` flat map，避免破坏前端/CLI。

### Phase 4: Queue health adapters

统一只读 health，不改表语义：

- pending / due / leased / dead
- oldest due age
- max attempts
- retry cooling count

先覆盖 dirty target 和 job 表，不要求一次覆盖所有表。

### Phase 5: Budget validation

先做 config lint，不做强 runtime 调度：

- worker concurrency 总和不能明显超过 DB pool budget。
- agent workers 必须声明 agent lane。
- projection workers 默认 statement timeout 不超过某个上限，特例显式登记。

## 暂缓事项

这些现在做会过度设计：

- 引入 Kafka / Temporal / Celery 替换 PostgreSQL pipeline。
- 为每个 worker 建独立 DB role。
- 新增全局 `worker_idempotency` 表。
- 把 news/equity 多个 worker 合并成一个大 worker。
- 把 `WorkerManifest` 直接变成 runtime 调度器。
- 全天候开启全量 `auto_explain.log_analyze` 或 `log_min_duration_statement=0`。
- 追求端到端 exactly-once。

## 最终判断

当前 spec 合理，但需要三处优化：

1. 从通用 worker 分类改成本项目分类：fact ingest / fact lifecycle /
   projection / agent side-effect / notification / cache / maintenance。
2. 把幂等要求表达为“domain-specific idempotency evidence”，不要引入全局
   idempotency 表。
3. 把 manifest 定位成只读 contract 和测试输入，先不要让它驱动 runtime。

这样既吸收工业界最佳实践，又不破坏当前 Kappa/CQRS 架构，也不会过度设计。
