# Spec — Worker Runtime 平台规范

**Status**: Approved for hard-cut plan
**Date**: 2026-05-15
**Owner**: Codex with Qinghuan
**Related**:

- `docs/ARCHITECTURE.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`
- `docs/superpowers/specs/active/2026-05-14-pulse-worker-architecture-cn.md`
- `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`
- 业界参考：[Tapoueh — PostgreSQL LISTEN/NOTIFY](https://tapoueh.org/blog/2018/07/postgresql-listen-notify/)，[psycopg pool 高级文档](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)，[Sidekiq Best Practices](https://sidekiq.org/wiki/Best-Practices)，[Inferable — Unreasonable Effectiveness of SKIP LOCKED](https://www.inferable.ai/blog/posts/postgres-skip-locked)，[OpenAI Cookbook — How to handle rate limits](https://cookbook.openai.com/examples/how_to_handle_rate_limits)，[Jeremy Miller — Postgres advisory locks for leader election](https://jeremydmiller.com/2020/05/05/using-postgresql-advisory-locks-for-leader-election/)，[Debezium — Materializing aggregate views](https://debezium.io/blog/2018/09/20/materializing-aggregate-views-with-hibernate-and-debezium/)，[OpenTelemetry — Messaging metrics conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-metrics/)，[Confluent — Kafka Streams Stateful Fault Tolerance](https://developer.confluent.io/courses/kafka-streams/stateful-fault-tolerance/)

---

## 一句话结论

把 12 个长期运行 worker（加上 1 个 per-frame `IngestService` 作为合规参照）的运行模型从「各自实现的 N 套 `run()`」一次性 hard cut 到 **「`WorkerBase` + helper（`JobQueue` / `WakeWaiter` / `LLMGateway` / `DBPoolBundle`）+ 进程级单点 `runtime.bootstrap()`」**；用 `workers.yaml` 集中配置、用架构测试守门，让「所有现有 worker 和未来 worker 满足规范」是可验证事实而不是 review 习惯。本规范要求现有 12 个长期 worker 在同一个 implementation plan 内完成全量迁移，删除旧 runtime 路径，不保留兼容性代码。

---

## Background

### 当前事实

`gmgn-twitter-intel` 是单 ASGI 进程的 Kappa/CQRS 服务，运行 12 个长期 asyncio worker 任务（含 GMGN WS collector）+ 1 个 per-frame transactional `IngestService`（不是后台任务但本 spec 也作为合规参照），共享三个 psycopg 连接池（`api_db_pool` / `worker_db_pool` / `wake_db_pool`，`app.py:241-269`）。worker 清单见 `docs/WORKERS.md:17-35`；`WORKERS.md:33-35` 明确 `IngestService` 是事务性、不是长期任务。

2026-05-15 的 worker 全审计（综合分 6.4/10）揭示以下系统级事实：

| 事实 | 证据 |
|---|---|
| 12 个长期 worker 各自实现 `run()`/`stop()`/`aclose()`，`IngestService` 也有单独事务路径，无公共运行时契约 | `domains/*/runtime/*_worker.py` 与 `domains/evidence/services/ingest_service.py` |
| 7/13 行合规对象至少有一项调参不在 `settings.yaml` 中可调 | `app.py:421-430`（asset_profile/resolution 硬编码），AnchorPrice/LivePriceGateway 类默认值 |
| 8 worker 在外部 IO 期间持有 worker_db_pool 连接 | `handle_summary_worker.py:135-144`（LLM 119s 持连）、`asset_profile_refresh.py:33-50`（50×HTTP 单 session）、`resolution_refresh_worker.py:85-95`、`anchor_price_observation.py:31-71`、`harness_ops_worker.py:50-70` |
| `set_tracing_export_api_key` 被 3 个 LLM client 各自调用 | `pulse_decision_agent_client.py:112`、`social_event_agent_client.py:56`、`watchlist_summary_agent_client.py:65` |
| 无 `application_name` 设定，`pg_stat_activity` 无法分辨 worker | `platform/db/postgres_client.py:43-61` `create_pool` 仅设 `autocommit/connect_timeout/row_factory` |
| 无 `statement_timeout`，卡死查询可永久持连接 | 同上 |
| `LivePriceGateway` 的 `provider_state_changed` 参数永远 `False`，重连第一帧不强制写库 | `live_price_gateway.py:374` |
| `token_resolution_refresh.rebuild_token_radar_windows` 旁路写 `token_radar_rows` | `token_resolution_refresh.py:103-116`（架构 #4 "one writer per read model" 的破坏点）|
| `PulseCandidateWorker.pulse_agent_run_steps.started_at_ms = finished_at_ms` | `pulse_candidate_worker.py:587-589` — 阶段耗时永久丢失；`usage_json={}` token 用量永久不可见 |
| `/readyz` 只暴露 `last_started/run/result/error` 五件套，无 `iteration_duration_ms`、`backlog`、`p99`、`pool_wait` | `app.py:588-723` |
| 3 LLM worker 无全局限速 | `enrichment_worker.py:40-49`（concurrency=4 独立 task）、`handle_summary_worker.py`（concurrency=1）、`pulse_candidate_worker.py:264`（batch_size=10 串行）三方各自 `asyncio.wait_for`，无共享 Semaphore/Limiter |

### 既有架构原则（不变）

- **ARCH #1**：facts-first；`events / token_evidence / token_intents / asset_identity_* / price_observations` 是业务真相，其余皆为可重建 read model（`docs/ARCHITECTURE.md:34-37`）。
- **ARCH #4**：one writer per read model（`docs/ARCHITECTURE.md:47-52`）。
- **ARCH #5**：wake is not truth；每个监听必须 bounded `interval_seconds` catch-up（`docs/ARCHITECTURE.md:53-57`）。
- **ARCH #7**：material write budget — LIVE 写库由 `should_persist_live_observation` 单点决定（`docs/ARCHITECTURE.md:62-67`）。
- **RELIABILITY**：单 ASGI worker（`docs/RELIABILITY.md:5-8`）。

本 spec 是这些原则的**实现强化**，不是替代。

---

## Problem

新增 worker 没有规范可依靠，所以每个新 worker 都重复了已知的 12 类反模式（外部 IO 期持连、无自报家门、配置散落、无 metrics、自建 LLM client、忽略 advisory lock）；运维定位卡顿仅有 `last_run_at_ms` 一种信号，看不到「谁在等连接 / 谁在等 LLM / 谁的 SQL 卡了」；3 个 LLM worker 共用 OpenAI 配额却各自重试，429 时三方 attempts 同时燃烧；进程级状态（`set_tracing_export_api_key`、OTel provider）由各 client 抢着初始化，行为不确定。

---

## First principles

### F1：Worker 是 fact-consumer 或 fact-producer，不是真理源

worker 的正确性永远是「重启就能从事实表重建出同样的状态」。这是 `ARCHITECTURE.md` 第 1 与第 4 条 invariant 的延伸。worker 内存里不持有任何无法从 PG 事实表 + provider 状态重建的业务结论；LIVE 缓存可以丢，重启重建。

### F2：DB 连接是稀缺资源，外部 IO 期不持连接

`worker_db_pool` 默认 `max_size=10`（`storage.postgres.pool_max_size`，`platform/config/settings.py:42`），由 12 个长期 worker 与 per-frame ingest 路径共用。一个 worker 持连跨 LLM 调用就把池子私有化了（参见 Background 中 5 个具体证据）。**所有 worker 的「外部 IO 调用」必须在连接释放之后才发生**。模式必须是「read → close → IO → reopen → write」或「IO → 开短事务写」。

### F3：NOTIFY 是 hint，不是 truth；catch-up 是真理

`ARCHITECTURE.md:53-57` 已写明；外部佐证见 Tapoueh 文章。任何监听 wake channel 的 worker 必须有 bounded `interval_seconds` catch-up，且 interval 紧到能在 NOTIFY 全失效 30 分钟内仍满足 SLO。

### F4：单进程 ≠ 进程级状态可以乱写

OpenAI Agents SDK 的 `set_tracing_export_api_key` 是模块全局态，3 个 client 各自调用 = 最后写者覆盖。所有进程级副作用（tracing key、OTel provider、structlog config、httpx default headers）只能从 `runtime.bootstrap()` 发起；唯一例外是 bootstrap 构造的 `LLMGateway` 在自身构造函数内设置 tracing export key 一次。worker 内的 client 构造**禁止**写进程级 setter。

### F5：worker 必须自报家门

`pg_stat_activity` 看不出哪条慢查询是哪个 worker，`/readyz` 看不出哪个 worker 在卡 — 这两个问题已被 worker 全审计直接证伪。每个 worker 在每条 PG 连接上设 `application_name=worker:<name>`；在 `/metrics`（或扩展 `/readyz`）上暴露 OTel messaging conventions 的最小指标集。

---

## Goals

| # | Goal | 通过条件 |
|---|---|---|
| **G1** | 所有 worker 模板化 | 现有 12 个长期 worker 全部继承 `WorkerBase`；新增 worker ≤ 100 行 Python（继承 `WorkerBase` + 实现 `run_once`）；架构测试守住公共字段集 |
| **G2** | 外部 IO 期零连接持有 | 架构测试 AST 扫描禁止 `await ...openai\|httpx\|gmgn\|okx\|requests...` 和同步 provider 调用在 `db.worker_session(...)` 块内 |
| **G3** | 进程级 PG 可观测 | `pg_stat_activity.application_name` 形如 `worker:pulse_candidate`；`SELECT pid, application_name, state, query_start FROM pg_stat_activity` 能定位「谁卡哪条 SQL」 |
| **G4** | 进程级指标可观测 | `/metrics` 暴露每个 worker 的 `_processing_seconds` Histogram、`_queue_depth` Gauge、`_jobs_total{status}` Counter、`_jobs_in_flight` Gauge、`_lag_seconds` Gauge；OTel messaging semantic conventions 合规 |
| **G5** | 全局 LLM 限速 | 3 个 LLM worker 共享 `LLMGateway` 单例（`asyncio.Semaphore` + `aiolimiter.AsyncLimiter`）；任一 worker 的 429 退避对所有共享者生效 |
| **G6** | YAML 集中配置 | `workers.yaml` 是 12 个长期 worker 全部 `enabled/interval/concurrency/timeout/batch_size/max_attempts` 的唯一可调整位置；Pydantic `extra="forbid"`，未知 key 启动报错 |
| **G7** | 单写者由数据库守 | 每个 read model writer worker 启动时 `pg_try_advisory_lock(SINGLE_WRITER_KEY)`；失败则 idle backoff，不竞争写 |
| **G8** | 合规对照表归零 | spec 附 13-row（12 worker + IngestService）× 8 项契约矩阵；本 hard-cut plan 结束时 12 个长期 worker 全部合规，`IngestService` 只保留事务参照项 |

---

## Non-goals

- **N1**：不替换 asyncio 单进程运行模型。Dramatiq/RQ/Temporal 是不同架构，引入需先改 `ARCHITECTURE.md` 与 `RELIABILITY.md`。
- **N2**：不重写任何 worker 的业务逻辑（评分公式、agent prompt、SQL 查询）。
- **N3**：不引入 Kafka / Redis / PG 之外的 broker。SKIP LOCKED 队列模式在 PG 上够用。
- **N4**：不做逐 worker 兼容迁移、双 runtime、adapter shim、旧配置 fallback 或旧 `/readyz` worker section 双写。实施是一次 hard cut。
- **N5**：不引入多副本部署。进程级 advisory lock 已足够保护 single-writer，但部署仍是单 ASGI 进程。

---

## Target architecture

### 三层结构

```text
runtime.bootstrap()        ← 进程级单点，ASGI lifespan startup 唯一调用者
  ├── DBPoolBundle         (api / worker / wake 三池 + per-worker session 注入 application_name)
  ├── LLMGateway           (单例限流/追踪门面 + 全局 Semaphore + aiolimiter.AsyncLimiter)
  ├── WakeBus              (现有 - emit-only 适配器)
  ├── WakeWaiter Factory   (基于 wake_db_pool 长连 LISTEN，返回每 worker 独立 WakeWaiter)
  ├── TelemetryRegistry    (Prometheus + OTel tracer provider，仅此处注册)
  └── WorkerScheduler      (12 个长期 Worker 实例的生命周期、watchdog、shutdown 协调)

WorkerBase                 ← 所有 worker 的根类
  └── 子类 (PulseCandidateWorker, TokenRadarProjectionWorker, ...)
       implements run_once(self) -> WorkerResult
```

**关键：「单点」不可让步**。任何 `set_tracing_export_api_key`、`logging.basicConfig`、`OTel.set_tracer_provider`、`set_global_handler`、`httpx.default_headers` 等进程级副作用，**只能从 `runtime.bootstrap()` 出发**；`set_tracing_export_api_key` 的实际调用可以封装在 bootstrap 构造的 `LLMGateway` 内。worker 内禁止任何 setter 类调用。

### WorkerBase（所有 worker 的根类）

| 成员 | 类型 | 语义 |
|---|---|---|
| `name` | `str` | 稳定标识符（如 `pulse_candidate`）— 用于 metric label、`application_name`、log context |
| `__init__(*, db, llm, telemetry, settings, wake_waiter=None, job_queue=None)` | constructor | **强制依赖注入** — worker 不允许 import 全局服务 |
| `async run()` | default impl | startup → 可选 advisory lock → loop(`run_once` + wait) → 自动 metrics → 异常 backoff 重试 |
| `async stop()` | default impl | 置 stop flag、唤醒等待 |
| `async aclose()` | default impl | 关闭子类独占资源（hook） |
| `async on_start(self)` | optional hook | 一次性启动副作用 |
| `async run_once(self) -> WorkerResult` | **must override** | 一次 iteration 的工作；返回值用于指标 |
| `async on_stop(self)` | optional hook | 优雅停机副作用 |
| `SINGLE_WRITER_KEY: int \| None` | class attr | 若声明，`run()` 启动前 `pg_try_advisory_lock(key)`；失败则 idle backoff |

**自动暴露指标**（基类负责，子类不需要写）：

- `worker_processing_seconds{worker=name}` Histogram
- `worker_jobs_in_flight{worker}` Gauge（iteration 进入 +1、退出 -1）
- `worker_jobs_total{worker,status}` Counter（status ∈ {success, failed, dead, skipped}）
- `worker_last_run_at_ms{worker}` Gauge
- `worker_lag_seconds{worker}` Gauge（catch-up 落后量，poll-job worker 是 queue depth）

**自动暴露 JSON status**（`/readyz`）：`last_started_at_ms / last_finished_at_ms / last_result / last_error`。

**WorkerResult**：dataclass `(processed: int, failed: int, dead: int, skipped: int, notes: dict[str, Any])`。基类只需要这五个字段就能算所有指标。

### DBPoolBundle

```text
db: DBPoolBundle
  .api_session()         -> ctxmgr[RepositorySession]   # 给 API 路由
  .worker_session(name)  -> ctxmgr[RepositorySession]   # 给 worker；自动 SET application_name='worker:<name>'
  .wake_emitter()        -> WakeBus                     # emit 用 wake pool
  .wake_listener(name, channels) -> WakeWaiter
  .api_pool / worker_pool / wake_pool: psycopg_pool.ConnectionPool  # 不让 worker 直接拿
```

池级 `kwargs.options`：

- `worker_pool`：`-c application_name=gmgn_worker -c statement_timeout=30s -c idle_in_transaction_session_timeout=60s`
- `api_pool`：`-c application_name=gmgn_api -c statement_timeout=5s`
- `wake_pool`：`-c application_name=gmgn_wake`（**不设 statement_timeout** — LISTEN 是长连）+ TCP keepalives

每次 `worker_session(name)` checkout 后立即 `SET application_name = 'worker:{name}'`，不能依赖 pool `setup=` 一次性设置。原因：同一个物理连接会在不同 worker 间复用，worker 级 `application_name` 必须随 checkout 覆盖；session 退出时可 reset 为 `gmgn_worker`，但下一次 checkout 仍必须重新设置。

### 连接持有契约（G2 执行点）

worker 代码中，`with db.worker_session(name) as repos:` 或 `async with db.worker_session(name) as repos:` 块内**禁止任何**外部 IO（OpenAI、HTTPX、GMGN、OKX、apprise、subprocess、provider protocol）。异步 IO 用 `await` 很容易被 AST 抓到；同步 provider IO 也必须通过重排代码释放连接后执行。模式必须是：

```python
# 模式 A：read → IO → write
with db.worker_session(name) as repos:
    inputs = repos.X.read(...)
result = await self.llm.run_with_limits(...) # 池外
with db.worker_session(name) as repos:
    repos.X.write(result)

# 模式 B：claim → IO → finalize（poll-job worker）
with db.worker_session(name) as repos:
    jobs = self.job_queue.claim_batch(limit, repos.conn)
results = await asyncio.gather(*[self.llm.run_with_limits(...) for j in jobs])
with db.worker_session(name) as repos:
    for j, r in zip(jobs, results):
        self.job_queue.finalize_success(j.id, repos.conn)
```

执行：架构测试 AST 扫描，禁止 worker 模块在 `db.worker_session(...)` 块内出现 `await ...openai|httpx|gmgn|okx|requests...`，并禁止块内调用命名为 `provider|client|market|adapter` 的对象方法，除非该对象来自 repository/session（AC1）。

### JobQueue helper（PollJob 模式）

`JobQueue(table, worker_name, *, lease_ms, max_attempts, backoff)`：

| 方法 | 语义 |
|---|---|
| `claim_batch(limit, conn)` | `WITH cte AS (SELECT id FROM {table} WHERE status IN ('pending','failed') AND visible_at_ms <= now_ms FOR UPDATE SKIP LOCKED LIMIT $1) UPDATE {table} SET status='running', lease_token=$2, lease_expires_at_ms=now+lease_ms, attempt_count=attempt_count+1` |
| `finalize_success(id, conn)` | `UPDATE … SET status='done'` |
| `finalize_failure(id, error, conn)` | `status = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END; visible_at_ms = now + backoff(attempt_count); last_error = $error` |
| `reclaim_stale(conn)` | `UPDATE … SET status='failed' WHERE status='running' AND lease_expires_at_ms < now`（启动时 + 每 catch-up） |

`backoff` 默认 `min(300_000, 5000 × attempt_count)`，YAML 可覆盖。表必须有 `(status, visible_at_ms)` 复合索引。

### WakeWaiter helper（NOTIFY + catch-up 双轨）

```text
waiter = db.wake_listener("token_radar", channels=("market_observation_written","resolution_updated"))
async def run_once(self):
    ...do work...
    await waiter.wait(timeout=self.settings.interval_seconds)
```

底层：长持 `wake_pool` 一条连接的 LISTEN；自动 reconnect（NAT/proxy timeout 后）；带 `tcp_keepalives_*`。Waiter 只通知「有事发生」，不传 payload（payload 是 hint，不是 truth — ARCH #5）。

### LLMGateway（全局共享）

```text
LLMGateway(api_key, *, max_concurrency=8, rpm_limit=3000)
  .run_with_limits(worker_name, stage, timeout_s, coro_factory) -> T
  .openai_client(model, base_url, timeout_s) -> AsyncOpenAI
```

- `asyncio.Semaphore(max_concurrency)` — 并发上限
- `aiolimiter.AsyncLimiter(rpm_limit, 60)` — RPM 上限
- 内部用 OpenAI SDK / Agents SDK 自身的 `max_retries` + `Retry-After` honoring
- `worker_name` / `stage` 作为 OTel `messaging.process` span attribute
- **`set_tracing_export_api_key` 在 LLMGateway 构造时调用一次，仅此一次**

注入：3 个 LLM provider adapter 在构造时拿同一个 `LLMGateway`，但继续实现各自 domain provider protocol。Pulse / Enrichment / Watchlist 的 prompt、schema、stage runner 不被塞进 Gateway；Gateway 只拥有限流、追踪导出 key、OpenAI client 构造和调用包裹。429 退避对所有共享者生效。

### Bootstrap 单点

```text
async def bootstrap(settings: Settings) -> Runtime:
    configure_structlog()
    setup_otel_tracer_provider()
    registry = TelemetryRegistry()
    db = DBPoolBundle.create(settings)
    llm = LLMGateway.create(settings) if settings.llm_configured else None
    workers = build_workers(db=db, llm=llm, telemetry=registry, settings=settings.workers)
    scheduler = WorkerScheduler(workers)
    return Runtime(db=db, llm=llm, workers=workers, scheduler=scheduler)
```

`bootstrap` 是唯一写进程级状态的地方。`app.py` 的 `lifespan` 调用它一次。

### WorkerScheduler

接管 `app.py._start_workers` / `_stop_runtime` 当前职责，增强：

- **启动顺序**：先 `bootstrap` → 启动监听类 worker（TokenRadar / Pulse）让 LISTEN 先就位 → 再启动 emitter 类 worker（Anchor / Live / Resolution）→ 最后启动 Collector
- **单 worker 异常**：默认 `os._exit(1)`（保留现行 watchdog 行为）；YAML 可声明 `restart_locally: true` — 此时重建 task 并 backoff，不退出进程
- **优雅停机**：`stop()` flag → 等 `run_once` 自然结束 → 超时 `cancel()` → `aclose()` → 关池

### 单写者保护

`WorkerBase.run()` 流程：

```text
if cls.SINGLE_WRITER_KEY is not None:
    lock_conn = db.acquire_advisory_lock_connection(worker=name, key=cls.SINGLE_WRITER_KEY)
    if lock_conn is None:
        log("another writer holds the lock, idling")
        await waiter_or_sleep(backoff)
        return WorkerResult(skipped=1, notes={"single_writer": "locked_by_other"})
try:
    await loop()
finally:
    if lock_conn is not None:
        lock_conn.close()
```

声明 `SINGLE_WRITER_KEY` 的 worker：`TokenRadarProjectionWorker`、`PulseCandidateWorker`、未来其他 projection。普通 poll-job worker 不需要（SKIP LOCKED 已经保证）。advisory lock 是 PostgreSQL session-level lock，因此 lock connection 必须由 `WorkerBase` 持有到 worker 停止，不能 checkout 后立即归还 pool。

---

## Conceptual data flow

```text
ASGI lifespan
  → runtime.bootstrap()            [single-point process-level setup]
     → DBPoolBundle, LLMGateway, TelemetryRegistry, WakeBus, WakeWaiter factory
     → build_workers()              [DI 构造 12 个 WorkerBase 子类]
     → WorkerScheduler.start()      [按依赖顺序启动 task]

per worker (in its run() loop):
  1. (optional) pg_try_advisory_lock(SINGLE_WRITER_KEY)
  2. run_once():
       with db.worker_session(name) as repos:          [短借连接]
           inputs = repos.X.read(...)
       result = await llm.run_with_limits(...) OR provider.http(...)    [外部 IO，无连接]
       with db.worker_session(name) as repos:          [短借连接]
           repos.Y.write(result)
       wake_bus.notify_*(...)                          [可选 emit hint]
  3. 自动更新 metrics + last_* JSON
  4. wake_waiter.wait(interval) OR asyncio.sleep(interval)

WakeWaiter (long-lived):
  wake_pool connection → LISTEN <channels>
  on NOTIFY: signal worker's asyncio.Event
  catch-up: worker's interval timeout 触发独立 wake → no payload trust
```

新箭头：`bootstrap → DBPoolBundle/LLMGateway/...`、`worker → LLMGateway`。原 `worker → repository_session → pool` 改为 `worker → db.worker_session(name)`。

---

## Core models

### `WorkerResult`

```text
@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    failed: int
    dead: int
    skipped: int
    notes: dict[str, Any]    # 子类放扩展字段，不进基类指标
```

`notes` 例子：`{"reason_breakdown": {"first_seen": 12, "heartbeat": 3}}`、`{"single_writer": "locked_by_other"}`。

### `WorkerSettings`（Pydantic schema）

```text
class BackoffPolicy(BaseModel):
    kind: Literal["exponential", "linear", "fixed"]
    base_ms: int
    max_ms: int

class WorkerDefaults(BaseModel):
    interval_seconds: float
    concurrency: int
    timeout_seconds: float
    max_attempts: int
    backoff: BackoffPolicy

class PerWorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 同 defaults + worker 自定义字段（advisory_lock_key, batch_size, wakes_on, ...）

class WorkersSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    defaults: WorkerDefaults
    # 每个 worker key 必须在 known set 中（IngestService 不在此 — 它是 per-frame 服务，不是长期 task）
    collector: PerWorkerSettings
    anchor_price: PerWorkerSettings
    live_price_gateway: PerWorkerSettings
    resolution_refresh: PerWorkerSettings
    asset_profile_refresh: PerWorkerSettings
    token_radar_projection: PerWorkerSettings
    pulse_candidate: PerWorkerSettings
    enrichment: PerWorkerSettings
    handle_summary: PerWorkerSettings
    harness_ops: PerWorkerSettings
    notification_rule: PerWorkerSettings
    notification_delivery: PerWorkerSettings
```

未知 key → ValidationError → 进程拒绝启动。旧 `config.yaml` 中的 worker runtime knobs 在 hard cut 后不再读取；实施同 PR 更新默认配置、文档和 contract tests。

`IngestService` 不获得独立 `WorkerBase` 实例；它由 `CollectorService` 在 frame 处理路径上同步调用。它的连接持有契约（不在 session 内做外部 IO）由调用方 `CollectorService` 落实，不通过 YAML 单独配置。

---

## Interface contracts

### 公共 HTTP 暴露

**`/metrics`**（新增）— Prometheus 文本格式，包含每 worker：

- `worker_processing_seconds_bucket{worker,le}` / `_sum` / `_count`
- `worker_jobs_in_flight{worker}`
- `worker_jobs_total{worker, status}`（status ∈ success|failed|dead|skipped）
- `worker_last_run_at_ms{worker}`
- `worker_lag_seconds{worker}`

OTel messaging semantic conventions：每 iteration 一个 process span，attribute `messaging.system="gmgn_worker"`、`messaging.destination.name=<channel>`、`messaging.consumer.group.name=<worker_name>`。

**`/readyz`**（hard cut）— 删除旧的顶层 worker section（如 `harness_ops`、`token_radar_projection`、`pulse_agent`、`watchlist_handle_summary`、`anchor_price`、`asset_profile_refresh`、`resolution_refresh`、`live_price_gateway`），改为统一：

```json
{
  "workers": {
    "token_radar_projection": {
      "enabled": true,
      "running": true,
      "last_started_at_ms": 0,
      "last_finished_at_ms": 0,
      "last_result": {"processed": 1, "failed": 0, "dead": 0, "skipped": 0, "notes": {}},
      "last_error": null,
      "iteration_duration_p99_ms": 0,
      "queue_depth": 0,
      "pool_wait_ms_p99": 0
    }
  }
}
```

每 worker 节包含：

- `iteration_duration_p99_ms`（从 Histogram 推）
- `queue_depth`（poll-job worker；SELECT COUNT(*) WHERE status IN pending,failed）
- `pool_wait_ms_p99`（DB 池等待时长，从 telemetry）

保留 `/readyz` 的全局 `ok/reasons/collector/snapshot_gate/db/provider_states/handles/store`，但 worker 状态只走 `workers` map。前端 mock、OpenAPI generated types、integration tests 同 PR 更新。

### CLI 暴露

`gmgn-twitter-intel ops worker status` — 一次性打印所有 worker 的健康度，离线运维工具。不替换 `/readyz`。

### 配置文件

`~/.gmgn-twitter-intel/workers.yaml`（新文件，与 `config.yaml` 并存）。**不在 `config.yaml` 内合并**，避免 schema 膨胀。`load_settings()` 合并 `config.yaml + workers.yaml + env override`。这会同步修改 `docs/RELIABILITY.md` 当前“`config.yaml` 是唯一应用配置源”的表述：hard cut 后 `config.yaml` 是应用/provider 配置源，`workers.yaml` 是 worker runtime 配置源。

---

## Acceptance criteria

- **AC1**. WHEN 任意 worker 模块的 `db.worker_session(...)` 块内出现 `await self.llm|client|provider|http...` 或同步 provider/client/market/adapter 外部 IO 调用，THEN 架构测试 `test_no_external_io_inside_db_session` SHALL fail。
- **AC2**. WHEN 任意 worker 进入 `db.worker_session("<name>")`，THEN 当前连接的 `current_setting('application_name')` 与 `pg_stat_activity.application_name` SHALL 等于 `worker:<name>`；对持有 advisory lock / LISTEN 长连的 worker，运维查询 `pg_stat_activity` SHALL 能定位对应 worker。
- **AC3**. WHEN 任一 worker `run_once()` 进入或完成 iteration，THEN `worker_processing_seconds_count{worker=...}` 与 `worker_processing_seconds_sum{worker=...}` Prometheus 指标 SHALL 增加；`worker_jobs_in_flight{worker=...}` SHALL 在 iteration 开始时 +1、结束时 -1。
- **AC4**. WHEN `LLMGateway.run_with_limits()` 被 3 个 LLM worker 同时调用 N+1 次（N=`max_concurrency`），THEN 第 N+1 次调用 SHALL 在 `asyncio.Semaphore.acquire()` 阻塞；**所有 worker** 的并发上限合计为 N。
- **AC5**. WHEN `workers.yaml` 出现 `WorkersSettings` schema 未声明的 key，THEN `load_settings()` SHALL 抛 ValidationError，进程拒绝启动。
- **AC6**. WHEN 声明 `SINGLE_WRITER_KEY` 的 worker 启动而另一进程已持有该 lock，THEN 该 worker SHALL 进入 idle backoff（`last_result.notes.single_writer="locked_by_other"`），不写任何 read model。
- **AC7**. WHEN `NotifyChannel` 在 30 分钟内 0 NOTIFY（手动模拟），THEN 所有声明 `wakes_on` 的 worker SHALL 在自身 `interval_seconds × 2` 内至少完成一次 `run_once()`。
- **AC8**. WHEN 任一 `worker_db_pool` 连接在 `application_name='worker:<name>'` 下运行查询超过 30s（默认 `statement_timeout`），THEN PostgreSQL SHALL 抛 `statement_timeout` 错误，连接归还池；worker 计入 `worker_jobs_total{status="failed"}`。
- **AC9**. WHEN 12 个长期 worker 被 `tests/test_worker_contract_compliance.py` 扫描，THEN 测试 SHALL 证明全部继承 `WorkerBase`、全部从 `workers.yaml` 读取 runtime knobs、全部通过 session/IO/metrics/status 合约；`IngestService` 仅以 per-frame 事务参照进入矩阵，不允许 skipped worker rows。
- **AC10**. WHEN 进程内任何模块尝试调用 `set_tracing_export_api_key` / `logging.basicConfig` / `OTel.set_tracer_provider` 等进程级 setter（白名单：`app/runtime/bootstrap.py` 与由 bootstrap 构造的 `app/runtime/llm_gateway.py`），THEN 架构测试 `test_process_global_setters_only_in_bootstrap` SHALL fail。

---

## 13-row 合规对照表

| Worker | DB Session 短借 | external IO 在外 | application_name | metrics | YAML 配置 | SINGLE_WRITER lock | wake catch-up | 全局 LLM gateway | 主要 gap |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| CollectorService | ⚠ 每帧 2 借 | ✓ | ✗ | ⚠ 仅 status | ✗ snapshot_timeout 硬编码 | N/A | N/A | N/A | 自报家门 + snapshot_timeout 上提 |
| IngestService | ⚠ 单事务 13 表 | ✓ | ✗ | ✗ | N/A | N/A | N/A | N/A | 事务拆分（架构允许） |
| AnchorPriceWorker | ✗ HTTP 在 session 内 | ✗ | ✗ | ✗ | ✗ 类默认 | N/A | N/A | N/A | 模式 A 重排 + YAML + metrics |
| LivePriceGateway | ⚠ 每帧 1 借 | ✓（WS） | ✗ | ⚠ | ✗ 类默认 | N/A | N/A | N/A | YAML + `provider_state_change` 触发器（修架构违规） + reason breakdown |
| ResolutionRefreshWorker | ✗ HTTP 在 session 内 | ✗ | ✗ | ⚠ result 字段丰富 | ✗ app.py 硬编码 | N/A | N/A | N/A | 模式 A 重排 + YAML |
| AssetProfileRefreshWorker | ✗ 50 HTTP 单 session | ✗ | ✗ | ⚠ `finished_at_ms` bug | ✗ app.py 硬编码 | N/A | N/A | N/A | 模式 A + YAML + bug fix |
| TokenRadarProjectionWorker | ✓ 每 work item 短借 | ✓ | ✗ | ⚠ per-window | ⚠ interval 硬编码 | **应声明** | ✓ 双轨实现 | N/A | `advisory_lock_key` + 删除 `token_resolution_refresh.rebuild_token_radar_windows` 旁路 |
| PulseCandidateWorker | ✓ scan+write 分开 | ✓ OpenAI 在 session 外 | ✗ | ✗ `usage_json={}` | ✓ 大部分在 settings | **应声明** | ✓ 双轨实现 | ✗ 自建 client | `advisory_lock_key` + LLMGateway 接入 + step 时间戳修复 + `usage_json` 接 OpenAI usage |
| EnrichmentWorker | ✓ 4-5 次短借 | ✓ | ✗ | ⚠ 无 `last_run_at_ms` | ✓ 大部分在 settings | N/A | N/A | ✗ 自建 client | LLMGateway + `last_run_at_ms` + 拆跨域事务（HandleSummary 入队解耦） |
| HandleSummaryWorker | **✗ LLM 在 session 内 119s** | ✗ | ✗ | ⚠ | ✓ | N/A | N/A | ✗ 自建 client | **P0**：模式 A 重排 + LLMGateway |
| HarnessOpsWorker | ✗ 整批 5 阶段单 session | ✓ | ✗ | ⚠ 无 `last_started_at_ms` | ✗ 全部硬编码 | N/A | N/A | N/A | JobQueue 模型 + YAML + 5 阶段拆事务 |
| NotificationWorker | ✓ `to_thread` | ✓ | ✗ | ✗ | ✓ | N/A | N/A | N/A | metrics + wake 触发 |
| NotificationDeliveryWorker | ⚠ DB SQL 在 event loop | ✓ HTTP 在外 | ✗ | ✗ | ✓ | N/A | N/A | N/A | DB SQL 移 `to_thread` + metrics + 进程内 Event 替代 5s poll |

**实施分组**（属同一个 hard-cut plan 内的任务排序，不是兼容迁移）：

- **P0**：HandleSummaryWorker 模式 A 重排（最高连接持有风险）+ 4 个 asset_market worker 短借重排。
- **P1**：3 LLM worker 接 LLMGateway（统一 set_tracing_export_api_key）。
- **P2**：全员 `application_name` + metrics 接入。
- **P3**：散落配置上提 `workers.yaml`。
- **P4**：advisory_lock_key 声明 + 删除 `token_resolution_refresh` 旁路 + `LivePriceGateway.provider_state_change` 触发器修复。

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| 抽基类引入新 bug、回归现有 worker | high | 单 plan 内先写 contract tests 与 WorkerBase 单测，再逐组迁移 worker；每组迁移后跑定向测试 |
| `LLMGateway` 单例成为新瓶颈（所有 worker 排队） | medium | `max_concurrency` / `rpm_limit` 默认值留宽，可经 YAML 调；workers 可分别配优先级 semaphore（在共享 RPM 之下） |
| 每次 worker checkout 都要 `SET application_name`，增加一次轻量 SQL | low | 这是 worker 级可观测性的必要成本；只在 `worker_session(name)` 执行，不影响 API pool 与 wake pool |
| `statement_timeout=30s` 杀掉 TokenRadar 长查询 | medium | TokenRadar 在 `run_once` 顶部 `SET LOCAL statement_timeout = 120s` 覆盖，作为 worker 内显式选择 |
| advisory_lock 持有连接被 wake_pool 占用 | low | 用 wake_pool（已留 3 槽）；lock 由 worker 在 `run()` 期间一直持有 |
| 测试 mock `LLMGateway` semaphore | low | Gateway 暴露 `with gateway.disable_limits():` 测试钩子 |
| hard cut 过大导致单 PR 难 review | medium | plan 拆成小任务小提交，但不引入运行时兼容层；每个任务结束时架构测试保持通过或明确处于红灯 TDD 步骤 |

---

## Evolution path

当前 spec 锁定「单 ASGI 进程 + asyncio worker」模型。未来若以下任一条件出现，应触发 spec 升级讨论：

1. **collector 帧速** > worker_pool 容量上限的 60% 持续 10 分钟 → 拆 collector 为独立进程（仍可共用本 spec 的 WorkerBase）。
2. **LLM 调用** RPM 触达 OpenAI tier 上限 → 跨进程 rate limiter（Redis token bucket 或 OpenAI dispatcher）。
3. **多副本部署**需求出现 → advisory_lock + SKIP LOCKED 模式天然支持多副本（leader election），WorkerBase 不变；但需引入 leader-elect 探测。
4. **超大 read model rebuild**（如 24h+ 全量重算）超过 10 分钟单 iteration → chunked iteration / checkpoint 模式（参考 Kafka Streams standby + changelog）。

不预设：Kafka/Redis/Temporal 引入路径。若那天到来，先改 `ARCHITECTURE.md`。

---

## Alternatives considered

- **Alternative A — 不抽基类，仅在文档里写约定** — 拒绝：约定靠 review 守护在 Python 异步代码里极易漂移；连接持有边界这种「不写测试无法察觉」的约束必须有架构测试，而架构测试要识别「是不是 worker」就需要有基类标识。
- **Alternative B — 引入 Dramatiq/Celery 队列中间件** — 拒绝：违反 `RELIABILITY.md` 单 ASGI worker；NOTIFY-as-hint 变成 queue-as-truth 是架构断点；多进程模型解决了单进程内 PG 池竞争，但同时引入跨进程 rate limit 同步、跨进程缓存（如 `LivePriceGateway._cache`）、跨进程配置中心化等新协调问题，得不偿失。
- **Alternative C — 逐 worker 兼容迁移** — 拒绝：这会长期保留两套生命周期、两套 `/readyz`、两套配置来源，正好违背 `ARCHITECTURE.md` 的 no runtime compatibility layer。采用单 plan、多任务、小提交的 hard cut。
- **Alternative D — 用 Faust / 自建 Python stream processor** — 拒绝：Faust 项目被 Robinhood 放弃（[The Tragedy of Faust](https://taogang.medium.com/the-past-and-present-of-stream-processing-17-the-tragedy-of-faust-pythons-stream-processing-3f4aaa2556c9)）；我们的 Kappa/CQRS 直接架在 PG 上，比 stream processor 中间件更简单可靠。
- **Alternative E — 抛弃 single ASGI worker、改为 worker-per-process（Dramatiq-style）** — 拒绝：collector 与 read model worker 共享内存缓存（如 `LivePriceGateway._cache`）；跨进程共享需要 Redis；本 spec 目标是统一进程内 worker 而非跨进程编排。

---

## Boundaries

| Class | Behaviour |
|---|---|
| **Always** | WorkerBase 自动维护 `last_*` 字段与 metrics；`application_name` 自动 SET；`workers.yaml` 是配置唯一来源；`runtime.bootstrap()` 是进程级 setter 唯一来源；LLMGateway 是 OpenAI 配额唯一来源 |
| **Ask first** | 是否给单个 worker 单独的 LLMGateway 优先级 semaphore；是否对某 worker 显式延长 `statement_timeout`；advisory lock key 的分配规则若要跨项目复用 |
| **Never** | worker 内 import 全局服务（必须依赖注入）；worker 在 `db.worker_session` 块内 `await` 外部 IO；worker 内调用 `set_tracing_export_api_key` 等进程级 setter；引入新的 PG 连接池绕过 `DBPoolBundle`；worker 内 `await asyncio.sleep` 替代 `wake_waiter.wait` |
