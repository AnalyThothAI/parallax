# Parallax 后端 KISS Hard Cut 实施与复核

> 实施基线：`origin/main@1ecf679c`，2026-07-22。
> 前置审计：`backend-kiss-architecture-audit-zh-2026-07-21.md`。
> 范围：后端运行时、Kappa/CQRS 数据流、数据库迁移、HTTP/CLI/React 契约、测试与运维配置。
> 用户明确要求：不运行 build、typecheck、E2E、Docker rebuild/start；本报告不把这些门禁伪装成已完成证据。

## 结论先行

这次不是把原来的 25-worker 框架“重构得更漂亮”，而是删除了没有独立业务真相、失败边界或刷新节奏的控制面。最终运行时收敛为：

- 一个 Python service、一个 PostgreSQL；
- 17 个有真实独立生命周期的 worker；
- material facts、少量 stable current read models、必要的 durable targets；
- 一个最小 manifest、一个 typed `RuntimeSnapshot`、一个 composition root；
- provider/model/DB/subprocess 边界各自负责 timeout；
- HTTP status 热路径零 SQL，队列与领域诊断只在 authenticated ops 中按需查询；
- `market_ticks` 写入时同事务推进 `market_tick_current`，恢复时使用显式 bounded fact replay，不恢复常驻 projection worker；
- 模型执行只有一个直连 gateway、一次受 RPM 约束的 provider call 和一个 artifact identity 算法；
- 无 root settings forwarding aliases，无 repository `commit=True/False` 双模式，无 runtime/domain/surface 反向依赖。

旧审计给出的“20 workers”是删除前的保守目标，不是应被守护的新下限。进一步追踪真实数据流后，Market Current projection、Token Capture Tier 和 Live Price Gateway 都被证明是派生控制面，因此最终 17-worker 形态更接近第一性和 KISS，同时没有删除 material fact、side-effect ledger 或可恢复性。

## 1. 对旧审计的正式 supersession

旧审计保留为 2026-07-21 的证据快照；以下实施决策以本报告为准。

| 旧审计建议 | 最终实施 | 原因 |
|---|---|---|
| worker 25 -> 20 | worker 25 -> 17 | 3 个额外 worker 没有独立真相或失败边界 |
| `NOTIFY` 只作 wake hint | 删除 DB wake bus/waiter | 所有 worker 都有 bounded interval catch-up；低延迟收益不足以覆盖第二套连接/监听/重连状态机 |
| 保留 WorkerBase hard timeout | 删除通用 worker hard/soft timeout 与强制取消 | 多个 iteration 使用 `asyncio.to_thread`；取消 await task 不会终止线程或外部副作用，反而可能让下一轮与旧写入重叠 |
| 保留必要 worker advisory lock | 删除 lifecycle advisory locks | queue claim、CAS、unique key、monotonic upsert 和幂等事实已处理数据竞争；锁住整个 worker 生命周期是重复控制面 |
| Market Current 独立 projection | fact transaction 内推进 current | current 只依赖刚写入的规范化 tick，无需第二次排队 |
| persisted Token Capture Tier | 查询时选择 stream/poll target policy | tier 是调度策略，不是业务事实或产品 read model |
| Live Price Gateway | commit 后直接 WS fan-out，REST 读 DB current | gateway/cache/TTL 形成第二份 current truth |

### 1.1 为什么不恢复通用 hard timeout

保留的 timeout 是：

- provider HTTP/WebSocket connect/read timeout；
- model/agent execution timeout；
- PostgreSQL `statement_timeout` 与 connect timeout；
- subprocess/file/network 边界自己的 timeout。

删除的是 WorkerBase 对整个 `run_once()` 的 generic `wait_for + cancel`。Python task cancellation只取消协程等待，不保证终止 `to_thread`、驱动调用、网络端副作用或数据库端已经发出的工作。通用 hard timeout 因此不能证明“工作停止”，却可能让 scheduler 启动下一轮并制造重复写、重复 side effect 和更难解释的状态。

当前 kernel 保证同一 worker iteration 串行；shutdown 发 stop signal，并等待当前边界受控的 iteration 完成。若某个 provider 违反 bounded-I/O 合同，应在该 provider 边界修复 timeout，而不是用一个不能终止副作用的上层取消状态机掩盖。

### 1.2 删除了哪些锁，保留了哪些并发安全

删除：worker lifecycle advisory lock、lock pool、lock reason/status、acquire/release compatibility shape。

保留：

- `FOR UPDATE SKIP LOCKED` bounded claims；
- stable natural queue keys；
- lease owner + attempt + payload-hash completion identity；
- compare-and-set side-effect completion；
- unique constraints 与 deterministic fact identity；
- monotonic `(observed_at_ms, received_at_ms, tick_id)` current upsert；
- 领域内确有数据竞争含义的事务/锁。

这一区分删除的是“证明 worker 单例”的第二套控制面，不是删除数据库并发正确性。

## 2. 最终数据流

```mermaid
flowchart LR
  P["Provider inputs"] --> W["17 bounded workers"]
  W --> F["PostgreSQL material facts"]
  F --> Q["Durable target queues"]
  Q --> R["Stable current read models"]
  F --> C["Transactionally maintained current indexes"]
  R --> A["HTTP / CLI"]
  C --> A
  C -. "post-commit presentation event" .-> WS["WebSocket subscribers"]
  F -. "explicit bounded replay" .-> C
  A --> UI["React operator console"]
```

这条流保持 Kappa/CQRS 的关键边界：

1. provider raw frame 只是输入，不是业务事实；
2. PostgreSQL material facts 是唯一业务真相；
3. current read model 使用稳定 product/window key；
4. 每个 persisted read model 只有一个 runtime writer；
5. deterministic projection unchanged 时写 0 serving rows；
6. 外部 I/O 不跨数据库写事务；
7. notification/model side effects 保留 durable ledger；
8. derived current 可以从 material facts 显式、分批恢复。

## 3. 17-worker 最终模型

最终 inventory 由 `worker_manifest.py` 唯一维护：

```text
collector
market_tick_stream
market_tick_poll
event_anchor_backfill
resolution_refresh
asset_profile_refresh
token_radar_projection
macro_sync
token_image_mirror
token_profile_current
news_fetch
news_item_process
news_story_brief
news_page_projection
macro_view_projection
notification_rule
notification_delivery
```

Manifest 只保留 name、start priority、queue tables 和 current read-model identity。它不再动态导入 worker，不再承载 wake graph、timeout、lock、factory、provider 或第二套 settings schema。

`InactiveWorker` 是 disabled、operator-intent 和 unavailable composition 的单一表示实现；语义仍由 typed status 区分，未把“缺 provider”伪装为“用户关闭”。

## 4. Runtime 与 status hard cut

删除：

- DB `WakeBus` / `WakeWaiter` 与专用 wake pool；
- worker soft/hard timeout 状态机；
- lifecycle advisory-lock plane；
- scheduler sequential mode、force-cancel 与 iteration-task registry；
- 多套 Disabled/Unavailable/NotStarted worker 实现；
- readiness queue sampling 与重复 status composer。

保留后的职责：

- `WorkerBase`：串行 `run_once()`、duration telemetry、bounded backoff、interval catch-up；
- `WorkerScheduler`：按静态 priority 启停一次、聚合 typed status；
- `RuntimeSnapshot`：一次捕获 worker/collector/provider/news contract/agent execution 状态；
- `/healthz`：进程活性；
- `/readyz`：轻量 DB liveness + cached startup schema/composition；
- `/api/status`：纯内存 snapshot，零 SQL；
- `/api/ops/diagnostics`：同一 snapshot + authenticated on-demand SQL。

任何 `effective_status=degraded` 的 worker、异常 provider connection state 或 `news_provider_contract.ok=false` 都进入顶层稳定 degradation reason。readiness 不再因一个 provider 402、queue backlog 或业务 freshness 而错误拒绝 HTTP 流量。

### 4.1 Agent Execution 单策略 hard cut

产品当前只有 `news.story_brief` 一个真实模型执行阶段，因此删除了把未来可能性提前实现成运行时架构的 lane/default/global 多层配置：

- `llm` 配置只保留 credential/base URL，删除 provider、trace 与 passthrough config holder；
- 删除 `LLMGateway` 和 `WiredProviders.agent_execution_gateway`，composition root 直接构造唯一 `AgentExecutionGateway`；
- `workers.agent_runtime` 是一份 flat policy：model/provider family、token budget、capacity、RPM、timeout 与 circuit breaker；
- stage spec 固定且严格校验 `news.story_brief`，lane 只作为审计标签；
- gateway 只有一份并发容量、RPM、circuit 和 timeout 状态；
- 容量与 RPM 通过一次原子 `reserve_up_to` 预留，避免两阶段预留失败后泄漏 capacity；
- 一次 execution 只发一次模型请求并做一次 client validation；失败回到 durable worker retry，不再用未计 RPM/usage 的 client re-ask；
- freshness 与 request audit 共用一个 artifact hash，覆盖 model、provider family、request options、output schema、prompt 和 runtime version；
- `/api/status` 只返回 exact active payload、`{status: unavailable, error}` 或 `null`；
- ops 只返回 `{status, policy, counters, status_reason?, error?}`，没有兼容 alias、动态 lane map 或 fixed-null 字段。

这保留了有成本模型调用的审计 ledger 和 timeout，却删除了当前没有第二个消费者的通用调度框架。

## 5. Market path hard cut 与恢复性

### 5.1 正常写入

`MarketTickPersistenceService` 在一个 caller-owned transaction 中完成：

```text
INSERT market_ticks ... ON CONFLICT DO NOTHING RETURNING narrow rows
  -> choose newest inserted row per stable target
  -> monotonic upsert market_tick_current
  -> map product target
  -> enqueue token_radar_dirty_targets for changed current only
commit
  -> optional WebSocket live_market_update
```

被删除的链路：

- `market_tick_current_dirty_targets`；
- `MarketTickCurrentProjectionWorker`；
- `token_capture_tier` 与其 dirty queue/worker；
- `LivePriceGateway`、TTL cache 与 gateway worker；
- current row 的 `raw_payload_json` / `payload_hash` 重复字段。

### 5.2 显式 bounded rebuild

仅靠 forward transaction 不足以满足“derived read model 可重建”：如果 current 行被人工修复/删除，重复 fact 会在 fact insert 的 conflict 上 no-op。最终实现增加一个正式 application operation：

```text
parallax ops rebuild-market-current --execute --limit N
  -> scan distinct (target_type, target_id) after stable cursor
  -> lateral-select latest persisted market tick
  -> use the same MarketTickPersistenceService current primitive
  -> enqueue Radar dirty only for changed rows
  -> return next stable cursor
```

它是显式、分批、可恢复的 ops 操作，不是恢复常驻 worker、run ledger 或 dirty queue。集成测试会清空 current 和 Radar dirty row，再从既有 facts 恢复并验证 cursor exhaustion。

### 5.3 末端数据正确性复核

独立复核又修正了四个会在简化后放大成真实数据错误的边界：

- 只有 `repair=false` 且原因集合为纯 market 时才走 market-only Radar refresh；mixed/repair claim 必须重算 source edges；
- 60 秒 market freshness gate 不再丢弃唯一的新 tick，而是把同一 stable target 写回未来 `due_at_ms`；
- market target -> product target 映射统一调用 Registry 的 strict canonical rule：CEX 只接受 Binance canonical USDT swap，Asset 只接受 candidate/canonical，不再 lower-case 猜测；
- rebuild 从全表 `DISTINCT` 改为 stable recursive seek，每批最多定位 `limit` 个 target，避免修复操作先扫描全部历史 facts。

随后复核补齐了三个更底层的不变量：

- current upsert 在 source tuple 相等但派生 payload 漂移时允许 authoritative fact 修复；older tuple 仍禁止回退，完全相同仍写 0 行；
- identity 统一为 chain-aware exact key：EVM 地址规范化为小写，Solana/非 EVM 地址保留大小写，Registry、Search、poll/stream target 和 Radar join 不再用无条件 `lower()`；
- Radar 同一 `(window, scope)` 的 `all/sol/eth/base/bsc/cex` 六个 venue 只加载一次 cohort，再在内存中独立过滤排名；publication state 和失败事务仍按 venue 隔离。

0186 与运行时使用同一映射、identity 和 equal-key repair 语义，并覆盖已有 social dirty + market backlog 的 mixed 合并场景。

## 6. 领域与产品 hard cut

### News

- 删除 item brief lane、source-quality projection 和对应 worker/table；
- provider deterministic auth/payment/config failure 绑定 `config_payload_hash` terminal，不无限 retry；
- public story brief 只使用正式 nested contract；
- 删除 `agent_brief_status`、computed-time outer alias fallback 等前后端兼容路径；
- story model run ledger 作为有成本外部副作用审计保留并有 retention。

### Macro

- 删除独立 daily-brief worker/table；
- `assets.daily_brief` 只存在于 `module_views_json`；
- 删除双 run ledger、重复 raw series payload 与 request-time rebuild；
- 0186 在删除临时 `assets_brief_json` 前清空旧 snapshot，并强制 requeue current module projection，避免已消费 0185 rebuild 的数据库永久空。

### Notifications

- `notifications.dedup_key` unique constraint 是唯一 semantic dedup authority；
- 删除 JSON scan 与进程内 semantic seen；
- cooldown 仍是跨不同 notification identity 的外部推送策略；
- delivery ledger、network-outside-transaction 和 CAS complete/fail 保留；
- 删除独立 summary endpoint，list response 内嵌 summary。
- list item 后端与前端都使用 exact 23-field contract，不再把通知项退化为任意 JSON object。

### Token Radar / Watchlist / CEX / Narrative

- 删除 generic projection runs/offsets；
- Narrative admission 合入 Radar current payload；
- 删除 Account Quality 空置产品面和虚假 Watchlist signal scope；
- 删除无真实消费者的 CEX OI/detail product tables/API，保留通用 CEX identity/market facts；
- Radar rank source query 改读 compact route fields，避免拉取宽 JSON/current payload；
- read-model key、single writer、unchanged zero-write 与 publication state 保留。

## 7. Config、CLI 与 frontend 契约

### Settings

删除 43 个 root forwarding/compatibility properties。运行时代码直接读取 typed nested models：

```text
storage.postgres
api
llm
gmgn
providers.okx / providers.binance / providers.macrodata
upstream
```

只保留路径解析、SecretStr/env 解析和真正跨字段派生的 10 个属性。operator-owned `~/.parallax/config.yaml` 与 `~/.parallax/workers.yaml` 已按新 schema 验证；旧配置分别备份后 hard cut，不保留 runtime alias loader。当前 redacted `parallax config` 证明运行时读取的就是这两个 operator-owned 路径。

### CLI

CLI 只解析参数、调用 application/runtime operation、渲染结果。重复 News rebuild、重复 Radar audit 和 queue compatibility probes 被删除；Market Current repair 调用正式 application operation，不在 CLI 复制 SQL 或 current-write规则。

### Frontend

删除 fixed-null `raw_payload_hash`、News `agent_brief_status` 和 computed time alias fallback；同步 OpenAPI/types/fixtures。React 不重建后端 rank、brief、notification summary 或 current market truth。

公共 HTTP 成功响应契约同时完成 exact hard cut：Pydantic response schema 全局 `extra=forbid`，Search、Inspect、Token Case、Target Posts、Social Timeline、News、Macro、Watchlist、Notification、Status、Ready、Ops 的成功 payload 都在序列化边界 fail closed；本文不把 FastAPI/HTTP error envelope 误报为同一 exact schema。前端对 Macro、Notification、Ops、Status/Worker、Asset Flow、Watchlist 使用同样的 canonical required shape；Ops worker 删除无消费者的 `details`，status callback 统一只返回 dict；WebSocket notification 只触发失效重取，不再维护第二份 summary truth。

## 8. 数据库迁移安全

已发布 `20260721_0185` 保持 byte-identical；新增 irreversible `20260722_0186` 承担后续 runtime projection hard cut。

0186 在 drop 前执行：

1. 把本次被退休 queue 的 unresolved terminal evidence 标成 `archive/queue_retired_by_0186`；
2. 对账 active market-current dirty targets 与“本次迁移刚归档”的 terminal-only targets；
3. 明确跳过 operator 已 archive/quarantine 的历史 known-bad rows；
4. 对每个 target 用 `(observed_at_ms, received_at_ms, tick_id)` 选最新 fact；
5. 对相等 source tuple 的漂移 current 执行 authoritative repair，并以与生产 Registry 相同的 Asset/CEX route 过滤映射 Radar dirty；
6. 规范化已有 EVM registry/pricefeed address，改用 exact unique index 与 EVM-lowercase check，同时保留非 EVM case；
7. 删除 retired queue/tier tables；
8. reset Macro snapshot 并强制 enqueue module-only rebuild；
9. 删除 current/Macro 重复 columns。

验证场景包含：fresh empty DB、0184 -> head、已部署 0185 的 active backlog、terminal-only backlog、人工 quarantine 不重放、已消费 Macro rebuild 后重新入队。真实 operator PostgreSQL 在本轮不可连接，因此没有声称已完成 live migration、物理空间回收或 p95 改善。

## 9. 量化结果

| 指标 | 旧审计基线 | 实施后 |
|---|---:|---:|
| worker | 25 | 17 |
| schema tables | 79 live snapshot | 60 generated current schema |
| runtime Python（排除迁移） | 105,589 LOC | 80,192 LOC |
| architecture tests | 30,814 LOC | 241 LOC / 12 tests |
| 审计九类重复 helper | 193 | 8 |
| repository public `commit/auto_commit` 参数 | 172 functions 涉及双模式 | 0 |
| domain -> app forbidden imports | 存在 | 0 |
| runtime -> surfaces forbidden imports | 存在 | 0 |
| private source-string positive assertions | 大量 | 0 |
| root settings forwarding aliases | 43 | 0 |

这里的 60 是生成 schema，不是假装读取了不可用的 operator 数据库。自旧审计快照起 runtime 减少 25,397 行；只看本轮 `origin/main@1ecf679c` 到工作树，也从 83,287 降到 80,192 行（-3,095）。最终 staged commit 为 359 files、+22,817/-20,651，净增加 2,166 行；增量主要来自 exact OpenAPI/TypeScript 生成合同、0186、实施审计和新的正向行为测试，生产 runtime 本身仍净删除 3,095 行。

## 10. 验证边界

本轮采用与风险成比例的证据：

- Python 非 integration：3,466 passed / 1 skipped；skip 是显式 opt-in 的 GMGN provider drift，不是被忽略的失败；
- PostgreSQL integration：245 passed + 2 subtests（完整套件 17:55）；
- Worker/status/config/domain targeted unit tests；
- Testcontainers migration 和非空 backlog upgrade；
- current idempotency、transaction atomicity、read-model rebuild integration；
- API status/readiness/ops integration；
- frontend Vitest：105 files / 748 tests passed；
- frontend lint + architecture harness：14 files / 180 tests passed；
- Ruff 与 `git diff --check`；
- generated schema/OpenAPI/CLI docs clean-diff；
- `0185` blob immutable check。

明确未运行：build、frontend typecheck、E2E、Docker rebuild/start。原因是用户直接更改目标并要求不要编译；这四项不能出现在“通过”列表里。

## 11. 仍需真实环境完成的 Phase D

代码 hard cut 已完成，但以下物理数据工作不能靠本地测试伪造：

1. 建立并验证 raw frame -> event provenance coverage 后，才能删除 events 中重复完整 JSON；
2. 在真实数据库收集 7～30 天 index usage，再决定 drop 大索引；
3. 部署 0185/0186 后执行真实 relation-size、dead tuple、reindex/vacuum/reclaim 评估；
4. 用真实 `pg_stat_statements` 验证 Macro 与 News query p95/temp spill；
5. 验证 terminal/fetch/story retention job 在真实行量下的批次成本。

这些不是继续保留兼容代码的理由，而是必须由真实数据库证据驱动的物理治理。尤其 event JSON 在 provenance edge 达到完整覆盖前不能凭 KISS 口号删除。

## 最终判断

当前实现没有退回 CRUD，也没有拆微服务。它保留 Kappa/CQRS 的 material truth、stable read model、单写者、幂等 side-effect 和 replay 能力，同时删除了把这些原则重复实现成 wake、lock、timeout、ledger、cache、alias 和源码 tripwire 的控制面。

最关键的变化不是文件更少，而是每条业务事实现在只有一条可解释路径：

```text
provider input -> material fact -> stable current/dirty target -> public read
```

只有确实具有独立成本或外部副作用的阶段才保留 worker 和 ledger。这个边界比旧审计的保守 20-worker 目标更简单，也更符合第一性、KISS、Kappa 和 CQRS。

## 12. 继续审计：全链路 KISS 复核与第二轮硬切

> 继续审计基线：`main@c397affb`，2026-07-22。
> 目标：在前述 17-worker hard cut 之后，继续检查真实调用图、目录职责、provider/DB 边界和测试形态；不以文件大小或 McCabe 数值自动授权拆分。

### 12.1 更新后的判断

第一轮已经删除了主要控制面，但代码中仍残留四类“实现完成后没有退场”的复杂度：

1. 同一生命周期或状态在局部重复计算，例如 WorkerBase 的 one-shot/continuous iteration、ops queue health；
2. 已无消费者的 provider capability、client method、CLI branch 和 settings field；
3. application operation 仍放在 `app/runtime`，导致目录名表达错误的所有权；
4. 只证明旧代码形状不存在、伪造 PostgreSQL 细节或读取 private source text 的测试墓地。

本轮继续硬切这些残留，但没有改变 Kappa/CQRS 的业务拓扑：

```text
provider input
  -> normalized evidence / material facts in PostgreSQL
  -> durable target or transactionally maintained current row
  -> one owning worker/projection/read operation
  -> exact HTTP / CLI / WebSocket consumer
```

没有新增 service、table、worker、queue、ledger、feature flag、compatibility module 或第二写者。

### 12.2 当前职责图

| 层 | 唯一职责 | 本轮处理 |
|---|---|---|
| `integrations/**` | 外部协议、payload 解析、timeout/close、provider error | 删除零消费者 Candle 与 Binance 旁路接口；保留外部 alias、retry、unavailable 映射 |
| `domains/**` | material fact、identity、dirty/current 规则、side-effect ledger | 复用 ingest commit 返回值；删除 placeholder result、重复 Radar scheduling；保留 fact/target/current/ledger |
| `app/runtime/**` | composition、bootstrap、scheduler、provider wiring | 删除 operator query 与 dead descriptor；runtime Python 文件 28 -> 24 |
| `app/operations/**` | operator/application use case | 接收 diagnostics、News repair、Token Intel queries；不保留旧路径 re-export |
| `app/surfaces/**` | 参数解析、认证、exact payload | 删除伪造的 News `--domain` 分支；公共 payload 维持原结构 |
| `platform/**` | worker kernel、typed config、DB primitives | 合并 iteration body；settings field 下沉到真实消费者；terminal inspect 只表达 terminal evidence |

### 12.3 已实施的硬切

#### Worker 与 settings

- `WorkerBase.run()` 与 `run_one_iteration()` 共用一个 `_run_iteration()`；`running` 是唯一 re-entry 状态，不再维护同步的 `_active_run_loops`。
- `PerWorkerSettings` 只保留所有 worker 真正共享的 `enabled`、`interval_seconds` 和 `backoff`；batch、lease、attempt、statement timeout 等字段下沉到实际消费者。
- 删除从未产生第二种策略的 `BackoffPolicy.kind` 和无调用者的 `write_default_workers_config()`。
- strict mypy 暴露的 `Any` 传播通过 concrete worker settings annotation 和边界局部类型收窄解决，没有把 WorkerBase 泛型化，也没有新增 Protocol 层。

#### 数据流

- Collector 直接发布同一事务已提交的 `IngestedEvent.token_resolutions`，删除 commit 后第二次 repository session/read。
- token-intent rebuild 删除不驱动任何行为的 `projection_limit` 参数和 deferred projection placeholder；CLI 仍显式运行真正的 Radar worker，并返回其真实结果。
- Resolution empty result 删除 `anchor=None` 与虚构 projection 状态。
- Radar 删除与现有 hot/background due scheduler 重复的 `_missing_work_items()` pass；stable current identity、publication state 和失败事务隔离不变。
- News reprojection 直接调用 required repository capability，不把 repository 内部 `AttributeError` 改写成误导性的 capability error。

#### Provider 与 DB 私有面

- 原子删除 `MarketCandle`、DEX candle protocol/capability/wiring、GMGN/OKX candle client 和 Binance candle endpoint。当前 `/market/candles` read service 原本就显式返回 unsupported，不存在被删除的 runtime writer 或 provider consumer。
- 删除 Binance `premium_index`、`open_interest_hist`、simple ticker 三个零消费者接口；保留现行 `exchange_info` 与 `ticker_24hr`。
- OpenNews 只接受 typed `fetch_policy_json`；删除 URL query 的第二解析策略。operator config 只做了不含 secret 的结构检查。
- CryptoPanic 使用已有 RSS-like adapter；删除同构 wrapper、registry enumeration 和未使用的 context-manager methods。
- terminal history 删除伪造的 `active` 状态；active queue 仍由 queue-health 查询，terminal ledger、reason classifier 和 operator resolve action 保留。
- 删除 PostgreSQL audit 中没有任何 hot query placeholder 的 `token_factor_version` binding；不触碰 migration、CAS、JSON safety 或 transaction ownership。

#### 目录与 operations

- `ops_diagnostics.py`、`ops_cli_queries.py`、`projection_dirty_targets.py` 从 `app/runtime` 移到 `app/operations`，所有 import 直接切到新 authority，没有兼容 re-export。
- 删除只包装 queue metadata 的 `job_queue.py`，diagnostics 直接复用 `operations.queue_health`。
- News dirty-target operation 删除永远只有 News 的 `domain` 参数和嵌套结果分支。
- 删除无调用者 `repository_session(pool, ...)` 和 stale Make target `token-radar-cex-recover`。
- provider wiring 的 chain/address identity 统一使用 `domains.asset_market.chain_identity`；删除四套 EVM regex/chain alias helper。
- 删除只为测试伪造 malformed internal `OkxProviderBundle` 服务的字段级 cleanup 防御；真实 typed bundle 的 partial close、去重和 error note 保留。

#### 测试

- 删除两个完整测试文件及一批 retired CLI、source-text、private-field、fake-SQL shape assertions。
- Macro migration/schema 的真实 SQL contract 和 executable repository behavior 仍保留；没有把所有 source inspection 机械清零。
- News page 的低分/无 standalone filter 行为改由真实 repository integration 覆盖。
- provider、worker、ops、canonicalization 和 typed-config 使用正向行为测试守护。

### 12.4 对上一版量化表的纠正

上一版“private source-string positive assertions = 0”表述过强。全仓当前仍有 62 个 `inspect.getsource`/`read_text` 命中，分布在 17 个测试文件，主要是 migration 不可变性、architecture boundary 和 generated/static contract。正确结论不是“源码检查必须为零”，而是：

- 有 executable behavior/SQL integration 替代的 private shape assertion 应删除；
- 证明 migration blob、forbidden import、single writer 或 generated artifact 的静态 contract 可以保留；
- 不以“测试 LOC 更少”为由删除唯一的事务、迁移或 public-contract 证据。

本轮最终文件计数（含移动后的新文件）：

| 指标 | `main@c397affb` | 本轮实现后 | 变化 |
|---|---:|---:|---:|
| runtime Python，排除 migrations | 80,192 | 79,417 | -775 |
| Python tests | 85,871 | 84,744 | -1,127 |
| `app/runtime` Python files | 28 | 24 | -4 |
| `app/operations` Python files | 6 | 9 | +3（职责移动，不是新增 use case） |

### 12.5 明确保留的复杂度

以下复杂度经过调用图复核后保留，因为它们对应不同真相、失败边界或恢复责任，而不是“代码不够短”：

- fact、dirty target、stable current、publication state 的分层；
- provider `unavailable` 与 operator `disabled`/`intentionally_not_started` 的区分；
- model run、notification delivery、terminal queue evidence ledger；
- scheduler、worker manifest、typed RuntimeSnapshot、split DB pools；
- 大型但内聚的 News/Macro repositories，以及 migration/static architecture tests；
- MarketCandlesService 的 explicit unsupported public response；
- provider external payload aliases、provider-local retry 和 terminal reason classifier。

因此没有按 C90 或文件行数拆 repository/service，也没有引入 generic repository、event bus、DI framework 或新的抽象目录。

### 12.6 延后项及证据门槛

| 延后项 | 为什么不在本轮删除 | 下一步证据 |
|---|---|---|
| event `raw_json` / `event_json` 重复 | provenance coverage 尚未证明完整 | sealed raw-frame -> event coverage 与 replay test |
| OKX payload aliases / retry | 外部 provider 漂移边界 | sealed live frames、retry/idempotency receipt |
| News model pre-call ledger | 涉及 provider-start/cost audit语义 | failure injection 与 billing/audit requirement |
| token image completion atomicity | 需要独立状态机正确性设计 | crash/replay integration |
| PostgreSQL index/table/partition hard cut | 本轮没有当前物理证据 | operator `pg_stat*`、relation size、7-30 天 usage、EXPLAIN |

这些延后项不是兼容层豁免；它们需要比静态调用图更强的真实证据。

### 12.7 本轮验证边界

已通过：

- Worker/config targeted：93 passed；
- ingest/resolution/Radar/News flow：43 passed；
- provider/DB exact suite：101 passed；
- ops/canonicalization/root architecture：91 passed；
- resolution + News repository：30 passed；
- strict mypy：543 source files clean；
- mypy repair behavior suites：261 passed，复核子集 165 passed；
- Ruff、format、`git diff --check`、SDD/report validators。

`make check-all` 没有完成：Python Ruff/format/mypy 阶段已通过，随后 frontend typecheck 因当前 worktree 没有安装锁文件依赖而报 `vitest/globals` 缺失，并使用了不匹配的 TypeScript 6。用户随后明确要求停止完整 `check-all`，改为合并 `main` 后 build/start 验证真实链路。因此 integration、E2E、golden、coverage 和完整 frontend gate 都没有被写成已通过。`tests/integration/test_api_websocket.py` 的单独尝试又在首个 in-process `TestClient` shutdown 卡住，185.98 秒后中止，零测试完成。

合并到 `main@a7ad09df` 后，两轮 `make docker-up` 都成功构建 Python/Playwright/React production image、执行 migration 并启动健康容器；第二轮将真实数据库从 `0187` 升到新增的 `0188`。最终 `make docker-status` exit 0，app/PostgreSQL healthy，`/readyz` 为 true，当前与期望 revision 均为 `20260722_0188`。Docker 内的 React production build 已通过，但这不等价于完整 frontend lint/type/test gate。

### 12.8 继续审计最终判断

当前后端仍有真实业务复杂度，但没有发现需要再引入架构层的理由。第二轮最有效的简化不是拆大文件，而是删掉零消费者接口、重复读取/调度、伪状态、错误目录所有权和测试墓地。

Kappa/CQRS 的维护边界现在更清晰：事实只写一次，current 只有一个 owner，恢复通过 bounded fact/target replay，外部副作用保留 ledger，operator query 不再冒充 runtime composition。剩余高复杂度应由真实 provider/PostgreSQL 证据或新的产品责任触发，而不能由 LOC/C90 单独触发。

### 12.9 合并后真实链路暴露的两个缺口

静态测试全部通过并不等于真实 PostgreSQL 行量与历史状态正确。合并启动后的真实探针暴露了两个不属于本轮删减回归、但必须在交付前硬切的问题。

#### Recent / WebSocket replay 的 tick join 与 fallback

`EventTokenProjectionQuery` 对 event capture 的 immutable `market_ticks` join 少了分区主键中的 `observed_at_ms`；latest fallback 又扫描约 685 万行的 append-only fact tape，而不是已有的 `market_tick_current`。真实查询因此出现 timeout，影响 `/api/recent` 和 WebSocket replay。

修复没有添加 index、cache 或另一个 projection：

- captured tick 继续读 immutable fact，但按完整 composite key join；
- 没有 event capture 时，latest fallback 直接读现有 stable current model `market_tick_current`；
- 正向单测固定完整 key 与 current authority，不固定 SQL 私有排版。

修复后真实 `/api/recent?limit=20` 连续耗时 89/33/34/23/22 ms，WebSocket replay 20 条最终为 259 ms、100 条为 312 ms。

#### Radar private factor cache 的历史 contract 漂移

`0186` 已要求新 producer/validator 生成 `normalization.cohort_status`，但没有清理之前落盘的 private `token_radar_target_features`。真实库中发现 1,806 个无效 cache row、覆盖 1,025 个 target；material facts、rank-source edges 和 public current rows 都没有损坏。

新增不可逆 `0188`，只做 Kappa rebuild hard cut：

```text
feature/current/rank-source identities
  -> existing token_radar_dirty_targets(repair_dirty=true)
  -> truncate rebuildable token_radar_target_features
  -> existing bounded projection worker rebuilds from PostgreSQL facts
```

它不回填 malformed JSON、不放宽 validator、不改 `0185`-`0187`，也不删除 current/publication/first-seen/rank edge。`0187 -> 0188` 非空 PostgreSQL integration 通过；最终采样已有 1,360 个新 feature row，缺失 `cohort_status` 为 0，dirty/repair queue 均已排空，48 个 publication set 全部 `ready` 且 error 为 0。恢复完全由正常 worker 有界完成，这比 migration 内做第二套 projection/backfill 更符合 Kappa/KISS。

### 12.10 最终真实证据与未掩盖风险

最终 production image 上观察到一条非 synthetic GMGN direct-WebSocket event：

```text
gmgn direct_ws
  -> events(event_id=gmgn:twitter_monitor_basic:8fd4eb6d-d10f-47f6-80c8-b761a340a02a)
  -> authenticated /api/recent HTTP 200 (61 ms)
  -> authenticated /ws ready + replay 20 (259 ms)
```

HTTP、WebSocket 与 PostgreSQL 中的 event identity、provider、transport、channel 和 `received_at_ms=1784693966537` 一致。`/api/token-radar` 从 `token_radar_current_rows` 返回 HTTP 200、`fresh`、20 个 serving row、72 个 source row；GMGN runtime state 为 `streaming`。

真实运行也保留了三项明确 warning，而不是用 compatibility/default 修绿：

- `resolution_refresh` 和 `news_fetch` running but degraded，provider diagnostic 曾返回 HTTP 402；
- OKX DEX WebSocket 以 provider code `60029` 持续重连，采样时没有 ack subscription；
- `/api/news/sources/status` 在 5,208 ms 后 HTTP 500，日志确认 PostgreSQL statement timeout。

它们分别属于外部 entitlement/authorization 和 News 物理查询治理，不证明 KISS hard cut 回归，也不能由 `/readyz`、fallback payload 或 `disabled` 语义掩盖。最终结论因此是：本轮代码与目录简化可以交付，真实链路和 Radar hard cut 已验证；完整 `check-all`、正式 full integration/E2E/golden、coverage 与完整 frontend gate 仍明确未验证，News source-status 与 OKX/provider entitlement 是后续独立问题。
