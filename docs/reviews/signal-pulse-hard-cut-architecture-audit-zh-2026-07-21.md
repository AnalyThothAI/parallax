# Signal Pulse 硬删除与整体架构审计（2026-07-21）

## 结论

Signal Pulse 应端到端硬删除，而不是继续 disabled、藏 UI、保留空接口或忽略旧配置。它不是 Kappa 物化事实，而是一条没有当前产品消费者的派生决策链；消费者被禁用后，上游仍持续写 dirty queue，前端也仍轮询，形成纯维护与资源成本。

本次硬切保留共享且仍有消费者的事实、读模型和 Agent 基础设施，删除 Pulse 专属 producer、worker、provider、API/CLI、通知、数据库、前端、测试、prototype 与兼容分支。同时处理审计中两个独立高置信问题：Macro 请求时伪回测，以及数据库 schema 生成器接受落后数据库。

## 审计边界与方法

审计区分四类证据，避免把设计、历史或运行时误当成当前实现：

1. 当前源码、worker manifest、路由、配置模型和前端依赖图；
2. Alembic 当前链与隔离 PostgreSQL 的实际 head schema；
3. operator 配置和本地数据库的只读运行证据；
4. 历史迁移、已完成 SDD 和历史审计，仅作为墓碑，不作为当前契约。

判断顺序采用第一性原则：先确认业务真相和真实消费者，再确认单写者、稳定键、幂等与 catch-up，最后评估代码量、数据库对象、请求、WAL、启动资源和测试维护成本。没有当前消费者的派生读模型、控制面和审计账本不因“以后可能用”而保留。

## 已核验基线

- 专属后端：51 个 Python 文件，13,298 行。
- Pulse 命名测试：42 个文件，19,206 行。
- 专属前端：8 个源码文件，1,055 行；加测试与 fixture 后约 1,741 行。
- 0182 实时本地库：14 张 `pulse_%` 表、52 个索引、35,561,472 bytes；0183 当前源码 head 剩 13 张目标表。
- 禁用消费者后仍有 21,172 条全部到期的 dirty targets。
- 当前统计窗口内，dirty-target producer 执行 570 次 upsert、触及 2,703 行并产生 6,193,803 WAL bytes。
- Live 页固定发起 3 个 Pulse 请求：12 秒一条、20 秒两条，约 11 req/min/client；隐藏队列同样轮询，即约 660 req/hour/client。
- 实时数据库在 0182，源码在 0183，原 `/readyz` 因迁移版本不匹配返回 503；本次没有修改实时数据库。

## Kappa/CQRS 真相边界

### 保留：物化事实与仍被消费的投影

- `events`、`token_intents`、`token_intent_resolutions`、`asset_identity_*`、`market_ticks`、`enriched_events` 等物化事实。
- Token Radar、Narrative Admission、News、Macro、token profile、Watchlist、notifications 等仍有真实消费者的单写者读模型。
- News item/story brief 仍使用的共享 `LLMGateway`、`AgentExecutionGateway`、执行策略、审计与遥测。
- PostgreSQL durable dirty targets、`NOTIFY` wake hint 与有界 `interval_seconds` catch-up 模式。
- API/CLI/WebSocket 的通用认证、错误封装和通知投递基础设施。

### 移除：无消费者的派生链

- candidates/playbooks 等 Pulse 派生读模型。
- dirty targets、jobs、edge、budget、runtime、eval 等控制面。
- runs、steps、evidence、eval 等 Pulse 专属审计账本。
- Token Radar producer fan-out、worker、lane、provider/client 与 Agent policy。
- 两个 HTTP 读端点、Pulse CLI/replay/eval 操作、通知规则与卡片、Token Case overlay。
- Signal Lab 前端、三个轮询 query、query keys、fixtures、MSW/E2E 场景、全局 Live selection 与 Zustand task store。
- 无引用的两份可导航 Signal Pulse/Signal Lab prototype。

删除后数据流收敛为：provider 输入先落 material facts；各领域单写者从事实或 durable dirty targets 重建自己的 current read model；HTTP/WebSocket/CLI 只读事实或投影；前端不重算 rank、admission 或历史决策。

## 数据库硬切

新 revision `20260721_0184` 在 `20260713_0183` 之后，以 FK 安全顺序精确删除 13 张表：

1. `pulse_agent_eval_results`
2. `pulse_agent_eval_cases`
3. `pulse_evidence_packets`
4. `pulse_agent_run_steps`
5. `pulse_playbook_snapshots`
6. `pulse_candidates`
7. `pulse_agent_runs`
8. `pulse_agent_jobs`
9. `pulse_agent_runtime_versions`
10. `pulse_candidate_edge_state`
11. `pulse_candidate_run_budget`
12. `pulse_target_run_budget`
13. `pulse_trigger_dirty_targets`

迁移不使用 `CASCADE`、`IF EXISTS` 或通配 DDL；任何未知依赖或 schema drift 会失败关闭。迁移先按精确 predicate 删除共享 `notifications` 与 `worker_queue_terminal_events` 中的 Pulse 行，保留通用表和非 Pulse 行。downgrade 明确不可逆，只允许恢复迁移前备份，不重建空兼容表。

## 复杂度与性能评估

合并前快照为 341 个文件变化、1,246 行新增、53,140 行删除，净减少 51,894 行。新增主要是不可逆迁移、负向架构守卫、SDD 和本审计；删除主要是业务实现、重复测试、生成报告与 prototype，而不是把代码转移到新的 wrapper。

直接收益：

- 少 1 个 worker、1 条 Agent lane、1 个 provider/client 构造链与对应 scheduler/status/queue health 分支。
- 少 13 张当前表和实时基线中的 52 个索引；不再维护 35,561,472 bytes 的无消费者关系对象。
- Token Radar 不再写 21,172 条全部到期的队列，也消除已观测的 570 次 producer upsert、2,703 行写放大和 6,193,803 WAL bytes。
- 每个打开 Live 页的客户端少约 11 req/min，隐藏面板不再产生请求、缓存 entry、解析和重渲染。
- 前端整体净减少 3,752 行；生产后端 `src/` 净减少 16,632 行；测试净减少 25,339 行。
- Ops diagnostics 改为无 query 参数的固定 cache key，删除后端已忽略的 `window/scope/since_hours` 与无意义缓存碎片。
- LLM/Agent gateway 只在 News domain、至少一个 News brief worker 和 LLM 配置同时有效时创建；删除两个同义 `*_configured` property，避免禁用 worker 时仍分配启动资源。

## KISS 与兼容性清理

本次没有添加 feature flag、deprecated alias、ignored setting、空 endpoint、redirect、shadow table 或双写。额外移除的高置信胶水包括：

- Notification rule config 只保留当前使用的 `enabled/channels/cooldown`，未知旧字段直接拒绝。
- Narrative read model 只接受正式嵌套 `target.target_type/target_id`，不再从顶层 `type/id` 修复身份。
- Search/Token Case/Token Radar 只使用 `narrative_admission`；删除 discussion digest、semantic backlog 和伪 Propagation/Bull/Bear UI 断言。
- frontend `NarrativeAdmission` 手工 facade 与 OpenAPI 对齐：正式三种 status、必需 `is_current`，unsupported 由 `currentness.display_status` 表达。
- Ops 页面删除永远为 0 的 semantics/digest 状态，不再展示后端根本没有返回的 domain。
- Worker manifest 的负向测试改用 synthetic manifest，不要求生产环境为了测试而保留一个 Agent queue。
- Identity evidence 事务守卫从“字符串出现次数”改为逐个验证两个真实 mutation 方法。

共享 `AgentExecutionGateway` 没有因 Pulse 删除而一并删除，因为 News item/story brief 是当前可验证消费者。这是保留通用模式、删除产品专属适配器，而不是按名称做机械清扫。

## 独立 P1：Macro 请求时伪回测

原 Macro module GET 把今天计算出的 trade-map expression 套到过去 60 天数据，生成 win rate、10K P&L、holding period 与 historical trust。它没有当时已发布的历史 decision snapshot，也没有稳定 projection identity，因此不是可审计回测，并且每个请求重复计算。

该表面已硬删除：生产后端删除 484 行、仅保留 7 行契约收口；生产前端模型/UI/CSS 删除 247 行、仅增加 5 行收口；连同失效测试和 fixture，Macro 相关净减少 1,675 行。未来若需要回测，必须消费当时实际发布且带稳定键的历史决策快照，不能缓存当前算法后伪装成历史预测。

## 独立 P1：数据库 schema 生成器

原生成器只 introspect 当前 DSN，可能把落后数据库写成 canonical schema。现在生成前必须证明 `alembic_version` 精确等于源码单一 head，并检查 0183/0184 已删除关系不存在；版本不匹配、multi-head 或同 revision schema drift 都失败关闭。`docs/generated/db-schema.md` 已从隔离 PostgreSQL 由空库迁到 0184 后重新生成，没有读取或修改 operator 数据库。

## 延期项

- Account Quality stats/snapshots 与公开 endpoint 当前没有前端消费者，但可能存在外部 API 使用者；缺少产品边界确认，记录为后续 re-underwrite，不在本次破坏性删除中猜测。
- 与 Signal Pulse 无直接证据关系的 Token Radar、News、Macro 业务重构不混入本次硬切。
- 历史 Alembic、已完成 SDD、日期化历史审计和 visual audit 保留为不可变工程证据；它们不属于当前运行契约。
- ignored `.pyc`、Vite cache 和空目录不是 Git 业务代码，不作为交付内容。

## 部署门禁与恢复

本次只交付代码和迁移，不修改 operator 配置或实时数据库。当前 `uv run parallax config` 会对三个旧键严格失败，这是预期硬切而不是兼容缺陷。部署必须原子执行：

1. 备份 PostgreSQL，并验证备份可恢复。
2. 从 `~/.parallax/config.yaml` 删除通知规则 `signal_pulse_candidate`。
3. 从 `~/.parallax/workers.yaml` 删除 lane `pulse.decision` 与 worker `pulse_candidate`。
4. 重新运行 `uv run parallax config`，必须通过且不得打印 secret。
5. 部署代码，再执行 0182 → 0183 → 0184；确认 `alembic_version=20260721_0184`。
6. 验证 13 张表不存在、共享非 Pulse 行保留、`/readyz` 返回 200，再启动常驻 worker。

迁移后若需回滚，必须恢复迁移前数据库备份并同时部署旧代码与旧配置；不得调用 0184 downgrade 或临时增加兼容 schema。

## 验证状态

- 当前运行时/公共契约 hard-delete guard：后端 3/3、前端 4/4 通过。
- SDD artifact validator 与生成索引 check 通过。
- Python architecture 聚焦修复与前端 40 项契约/组件回归通过。
- Search/Token Case 后端契约与集成回归 10 项通过。
- 完整 `make check-all`、非空 0183 → 0184 数据迁移、浏览器 desktop/mobile smoke 和独立实现验收在最终收口阶段记录到 feature verification；未通过前不宣称完成。
