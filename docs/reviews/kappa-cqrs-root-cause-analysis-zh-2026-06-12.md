# Kappa/CQRS 架构根因分析 - 2026-06-12

本文是 `Kappa/CQRS Worker and PostgreSQL Audit - 2026-06-12` 的中文根因总结和治理结果说明。它记录的是架构判断、已落地修复、仍未完成的验证边界，不替代 SDD 记录。

## 当前结论

这次问题的根不是某一个 worker 写法不好，也不是某一条 SQL 缺索引，而是 Kappa/CQRS 的边界被历史兼容路径逐步侵蚀：

- HTTP 读路径混入 provider IO。
- worker 存在绕过正式 runtime ownership 的 helper 入口。
- read model service 里混入 ops backfill 写路径。
- publish/claim 热路径夹带历史清理和 retention 维护。
- public read query 为兼容语义展开 JSONB event id 数组。
- 产品 read payload 暴露 worker/scheduler 进程瞬态。
- 诊断读面从 runtime provider object / private registry 推导契约能力。
- 测试和配置继续保护旧路径，让旧架构看起来“仍然可用”。

成熟 Kappa/CQRS 的核心要求是：PostgreSQL material facts 是唯一业务真相，provider raw frames 只是输入；read API 只读已投影 read model；每个 read model 只有一个 runtime writer；worker 通过 durable queue 和 bounded catch-up 处理工作；PostgreSQL 热路径必须可索引、可界定、可并发 claim。

本轮修复已把主要偏离点拉回这个模型，但最终 `make check-all` 未完成。用户明确要求停止集成测试，因此当前 SDD 状态保持 `In Progress`，不是 `Verified`。

## 根因一：读路径把 provider IO 当成 read model 补丁

典型表现是 `/api/stocks-radar` 在 HTTP request 内构造 `StocksRadarService`，并把 runtime quote provider 传进去。服务先从 PostgreSQL 读 social attention rows，再按 symbol 调 provider quote。

这违反了 CQRS 的第一原则：读模型应该是已经物化的查询视图，不应该在查询时补事实。否则同一个 API 响应同时依赖 DB 状态、外部 provider 可用性、provider rate limit 和 request-time 网络时延，既不可重放，也不可解释。

已修复：

- 删除 runtime stock quote provider lane。
- 删除 `MacrodataQuoteProvider` 及相关 config/health/test 兼容代码。
- `/api/stocks-radar` 只读 DB rows。
- quote block 保持 schema 形状，但明确返回 `quote.status = "unavailable"` 和 `quote.error = "quote_read_model_unavailable"`。

正确的后续方向不是把 provider 偷偷塞回 request path，而是单独设计一个持久化 US equity quote fact/current read model，由一个 worker 写入，并带 freshness/source 元数据。

## 根因二：worker ownership 被 helper 双入口削弱

`resolution_refresh` 的真实 runtime 行为已经是 dirty lookup queue consumer：claim `token_discovery_dirty_lookup_keys`，provider fetch 离开 DB session，随后重新打开 session 持久化。但修复前旧的 `run_resolution_refresh_once` helper 仍保留“拿着 repos 直接 claim、fetch、persist”的混合路径。

这种 helper 的风险不是现在一定会被生产调用，而是它会让测试、ops 或后续修复继续绕过 worker runtime 合约。只要第二入口存在，单 writer、session lifecycle、lease/retry 语义就不再是硬边界。

已修复：

- `resolution_refresh` manifest 改为 dirty lookup queue consumer。
- 删除 `run_resolution_refresh_once` 和旧 `_process_*` helper。
- 测试改为覆盖正式 `ResolutionRefreshWorker.run_once` 或纯 fetch/persist seam。

## 根因三：维护任务混进 serving/publish hot path

Token Radar publish 原先在 `refresh_rank_set` 内做 retention prune；notification claim 前会扫 stale running delivery 并做 terminalization。这些逻辑短期方便，但会让 hot path 成本随历史数据量增长。

成熟做法是区分：

- publish/claim hot path：只做当前投影或当前 claim 需要的最小 bounded 工作。
- retention/cleanup path：独立后台维护，必须有 batch limit、索引和可观测进度。

已修复：

- Token Radar publish 不再调用 `prune_target_features` / `prune_edges`。
- Token Radar private cache retention 记录为明确后续 debt，而不是塞回 publish。
- notification stale-running cleanup 改为 bounded CTE，使用 `LIMIT` 和 `FOR UPDATE SKIP LOCKED`。
- 新增 partial index：`idx_notification_deliveries_running_stale` on `(updated_at_ms, delivery_id) WHERE status = 'running'`。

## 根因四：read model 服务混入 backfill 写职责

`account_quality/read_models/account_quality_service.py` 同时承担公共读方法和 `backfill_account_token_call_stats` 写方法。后者会从 token/event/market 事实聚合账号调用统计，再 upsert `account_profiles`、`account_token_call_stats`、`account_quality_snapshots` 并直接 commit。

这不是请求时 provider IO，也不是第二个 runtime worker，但它破坏了目录和职责边界：一个名为 read model service 的对象既被 API/CLI 读路径构造，也暴露 ops 维护写入口。长期看，这会让公共 read service 逐步变成“顺手修投影”的地方，和 CQRS 的查询/命令分离方向相反。

已修复：

- `AccountQualityService` 只保留 `account_quality` 和 `account_quality_for_handles`。
- `AccountQualityBackfillService` 成为显式写侧服务，只由 `ops backfill-account-quality` 调用。
- API 与普通 read-model CLI 删除无用的 `signals` 依赖，通过 `AccountQualityService.from_conn(...)` 走读服务，不再直接 import `AccountQualityRepository`。
- `account_quality/interfaces.py` 只导出读侧服务，不再把 SQL repository 或 ops backfill service 暴露成跨域公共接口。
- 新增 `src/parallax/domains/account_quality/ARCHITECTURE.md`，声明 read-model 表、ops-only maintenance writer、稳定 key 和公共消费者。
- 新增 architecture guard，禁止 domain read-model 模块重新出现 backfill/repair/upsert/insert/commit 等写侧职责，并禁止 account-quality public read path 绕过读服务直连 repository。

这里保留了既有 repository SQL 和 commit 语义，没有把它过度设计成新 worker；这符合 KISS：先把读/写职责摆正，未来如果该 backfill 需要常态化，再单独设计 worker/manifest/dirty queue。

## 根因五：PostgreSQL hot path 依赖不可持续的 JSONB 展开

Pulse handle filter 原来通过 `jsonb_array_elements_text` 展开 candidate 的 `source_event_ids_json` / `evidence_event_ids_json`，再关联事件作者语义。这是典型的兼容型读路径：语义强，但查询形状会随历史 payload 增长变差，且难以稳定走窄索引。

已修复：

- Pulse public read path 不再展开 candidate event-id JSONB。
- handle filter 收窄为 direct `candidate.subject_key` / alias 语义。
- 合约文档更新为当前可索引语义。

如果未来产品确实需要“按 event author handle 找 candidate”，应新增 normalized edge read model，例如 `pulse_candidate_author_edges(candidate_id, author_handle, ...)`，由单 writer 投影维护，而不是在 public query 里临时展开 JSONB。

## 根因六：兼容测试和配置延长了旧架构寿命

这次不只是删代码，还必须删测试里的旧假设。否则旧测试会继续证明错误设计是“正确行为”：

- stocks radar 旧测试 fake quote provider。
- macrodata quote config/health 旧字段仍存在。
- resolution refresh tests 直接 import once helper。
- Token Radar tests 期待 publish 做 prune。
- Pulse tests 允许 JSONB expansion。
- `account_quality` 测试把 backfill 写路径挂在 read service 上，API/read CLI 也直接 import repository。

已修复后的测试方向改为 hard-cut guard：拒绝 provider IO、拒绝 helper、拒绝 unbounded cleanup、拒绝 publish prune、拒绝 public read JSONB event expansion、拒绝 read model service 暴露 backfill 写方法、拒绝 account-quality public read path 绕过读服务。停止集成测试后，又把 notification bounded stale-running SQL、Pulse JSONB event-id expansion、account-quality read/write split 这些边界补进 `tests/architecture`，确保 `make check` 这种非集成门禁也能阻止回退。

## 根因七：manifest 没完整表达 runtime IO 边界

补充 worker 矩阵审计时发现，`resolution_refresh` 已经是正确的 dirty lookup queue consumer，并且 provider fetch 已经离开 DB session，但 manifest 没有声明 `uses_provider_io=True`。这不是直接的数据错误，但会让 `WorkerManifest v1` 不能完整表达 runtime contract，削弱后续审计对“哪些 worker 会做外部 IO”的信任。

已修复：

- `resolution_refresh` manifest 保持 `DIRTY_TARGET_CONSUMER`，同时显式声明 `uses_provider_io=True`。
- architecture test 增加断言，要求 `resolution_refresh` 同时具备 dirty queue ownership、queue depth table 和 provider IO 标识。
- architecture test 增加 provider IO worker inventory 显式清单，防止后续新增 provider IO worker 未声明，或已声明 worker 被意外改回隐式状态。
- `docs/WORKERS.md` 增加 `provider-io-worker-keys` 机器可读 marker，并由 architecture test 绑定到 manifest 的 `uses_provider_io=True` 集合。
- `docs/WORKERS.md` 的新增/变更 worker 流程补充要求：只要 worker 获得或失去 upstream provider/subprocess/filesystem/network IO，就必须同步 `uses_provider_io=True` 和 `provider-io-worker-keys` marker。

这个修复的意义是让 manifest 重新成为架构真相：provider IO 不只是在代码里“看得出来”，也必须在 worker inventory 和文档里被机器可读地声明。

## 根因八：全局架构摘要会把退役 lane 重新合法化

补充审计时发现，`docs/ARCHITECTURE.md` 的顶层流程和 domain 表仍把 Narrative Intel 描述成 per-mention semantics / token discussion digest 职责。局部 `src/parallax/domains/narrative_intel/ARCHITECTURE.md` 和 `docs/WORKERS.md` 已经明确 hard-cut：当前 runtime 只写 `narrative_admissions`，历史 digest/semantic rows 只是 legacy read context。

这类文档残留不是小问题。新 agent 和后续 plan 会优先读全局架构，如果全局摘要继续描述退役 LLM lane，就等于把兼容路径重新合法化。

已修复：

- `docs/ARCHITECTURE.md` 的顶层流程改为 current source-set admissions 和 legacy narrative currentness reads。
- domain 表改为 current `narrative_admissions` source-set read model，并明确 former per-mention semantics / discussion-digest LLM lanes 没有当前 runtime writer。
- 新增 architecture guard，禁止全局架构重新把退役 Narrative LLM lane 写成当前职责。

## 根因九：产品读路径仍把退役 backlog 当作正在处理的状态

继续审计 Narrative Intel 时发现，虽然旧 `MentionSemanticsWorker` 和 `TokenDiscussionDigestWorker` 已经 hard-cut，Token Radar / Token Case 的产品读模型仍会从 `token_mention_semantics` 推导 `semantic_backlog_*`，并把缺少 ready digest 的当前 admission 显示成 `semantic_labeling_pending`。这等于告诉用户“后台还会继续标注”，但当前 runtime 已经没有这个 writer。

这类问题的根因是“legacy read context”和“current processing state”没有切开。历史 semantic/digest rows 可以作为已存在的上下文被读取，但不能再定义当前 source frontier、currentness reason 或 processing backlog。

已修复：

- `current_narrative_snapshots_for_targets` 不再查询 retired semantic backlog，也不再生成 `semantic_labeling_pending` currentness。
- `discussion_digest` public payload 不再暴露 `processing.backlog`。
- 删除未被路由使用的 `NarrativeBacklogHealthData` / `NarrativeSemanticBacklog` API schema 残留，以及不存在的 `/api/status/narrative-health` 合同描述。
- `src/parallax/domains/narrative_intel/ARCHITECTURE.md` 明确 selected post semantic hydration 只是 legacy read context，缺失语义不是 runtime queue state。
- 新增 architecture guard，防止产品读路径重新耦合 retired semantic backlog。

## 根因十：产品 health 混入 worker/scheduler 进程瞬态

继续审计 Signal Pulse 时发现，`/api/signal-lab/pulse` 会在公共读路径中调用 `_worker_running(runtime, "pulse_candidate")`，再把结果传给 `SignalPulseService.pulse(...)`，最终通过 `health.agent_worker_running` 暴露给前端和 OpenAPI 契约。

这个字段不是 material fact，也不是可重建 read model；它只是当前进程里 scheduler/task 是否看起来仍在跑。把它放入产品 read payload 会造成两个误导：

- 同一份 DB read model 在不同 API 进程、重启窗口或 scheduler 状态下可能返回不同 health。
- 用户会把“worker 此刻是否 running”误解为“Pulse read model 是否健康/新鲜”。

成熟 Kappa/CQRS 里，这类 runtime liveness 应归属 status/ops plane，例如 `/api/status`、worker inventory、queue health；产品读模型 health 应来自持久化 summary、freshness query、publish status 和事实时间戳。

已修复：

- `routes_pulse.py` 不再导入或调用 `_worker_running`。
- `SignalPulseService.pulse(...)` 不再接收 `agent_worker_running` 参数。
- `SignalPulseHealth`、`SignalPulseData`、OpenAPI、生成 TS 类型、前端手写契约和测试夹具删除 `agent_worker_running`。
- `docs/CONTRACTS.md` 明确 Signal Pulse public health 只来自 persisted summaries 和 bounded freshness queries；worker liveness 属于 `/api/status` 和 ops diagnostics。
- 新增源码与契约 guard，防止 public Signal Pulse payload 重新暴露 worker runtime state。

## 根因十一：诊断读面从 runtime provider object 推导静态契约

继续审计 News source status 时发现，`/api/news/sources/status` 虽然不直接发 provider 请求，但会从 `runtime.providers.news_intel.feed_client` 读取 `supported_provider_types()`，甚至 fallback 到 `feed_client._registry.supported_provider_types()`。这把一个本应静态、可测试的 provider-type contract 绑到了当前进程的 provider wiring 和私有 registry 形状。

这类问题比 request-time provider IO 轻，但根因相同：API read surface 不应该为了拼诊断 payload 去触碰 runtime provider object。支持哪些 provider type 是 runtime contract，不是某个 provider 实例的 product truth；配置源是否 unsupported 应由“持久化 source rows + 静态支持列表”判断。

已修复：

- 新增 `parallax.platform.config.news_provider_types.RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES` 作为纯静态 runtime 支持子集。
- `routes_news.py` 的 `/api/news/sources/status` 直接使用该静态契约，不再访问 `runtime.providers`、`feed_client` 或 `_registry`。
- `FakeRuntime` 测试不再伪造 `providers.news_intel.feed_client`，证明该 API 不依赖 runtime provider object。
- integration registry 不再导出自己的 `SUPPORTED_NEWS_PROVIDER_TYPES` 兼容常量；测试改为绑定 registry 输出和平台静态契约。
- 新增 architecture guard，禁止 News source status 重新从 runtime provider object / private registry 推导 supported types。

## 根因十二：News worker/status 仍从 provider object 反推 provider-type contract

继续沿着同一根因审计时发现，`NewsFetchWorker` 和 runtime `/api/status` 的 `news_provider_contract` payload 仍然通过 feed client 或 wrapper 的 `supported_provider_types()` 推导支持类型，并保留 private `_registry` fallback。虽然它们属于 worker/status 面，不是产品读 API，但问题本质仍然相同：静态 runtime provider-type contract 被当前 provider 实例形状反推。

这会带来两个长期风险：

- provider wrapper 变成“能力发现”入口，后续很容易被 API 或 worker 当作动态契约源。
- 测试可以通过 fake provider 暴露 `supported_provider_types()`，掩盖真实 runtime contract 应该由配置/平台常量和 DB schema 共同验证的事实。

已修复：

- `NewsFetchWorker` 直接向 `validate_news_provider_contract(...)` 传入 `RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES`。
- runtime `/api/status` 的 `news_provider_contract` 也使用同一个静态契约，只把 DB constraint 当 schema 校验源。
- `RegistryBackedNewsSourceProvider` 删除 `supported_provider_types()` wrapper 方法，provider object 只负责 `fetch/close`。
- `FakeCapabilityProbeProvider` 单元测试会在 worker 试图 probe provider capability 时直接失败。
- 新增 architecture guard，禁止 News fetch/status provider-contract validation 重新访问 feed-client capability method 或 private `_registry`。

## 根因十三：News provider-contract schema side 用代码枚举兜底 DB constraint

继续审计 `NewsFetchWorker` 的 provider-contract validation 时发现，supported provider types 已切到静态 runtime contract，但 schema provider types 仍通过 `_schema_provider_types(repository)` 做 fallback：当 repository 没有 `news_source_provider_constraint_values()` 时返回 `PROVIDER_TYPES`。这会把 PostgreSQL `news_sources.provider_type` CHECK constraint 的真实 schema contract 替换成 Python source-classification 枚举。

这不是正常容错，而是 schema 漂移的反向兼容层：如果 repository 接口缺失、schema introspection 失效，worker 仍会以代码枚举继续验证，掩盖 DB 约束和 runtime 支持集之间的不一致。成熟 Kappa/CQRS 里，schema contract 不能靠代码 enum 猜；schema side 必须来自 DB constraint，拿不到就失败并暴露诊断。

已修复：

- `NewsFetchWorker` provider-contract validation 直接调用 `repos.news.news_source_provider_constraint_values()`。
- 删除 `_schema_provider_types(...)` helper 和 `PROVIDER_TYPES` fallback。
- architecture guard 禁止 `news_fetch_worker.py` 重新导入 `PROVIDER_TYPES` 或保留 `_schema_provider_types` fallback。
- 单元测试用没有 schema introspection 方法的 fake repository 证明 worker 会 fail fast，并且不会 reconcile/claim sources。

## 根因十四：News item-process admission context 用 worker 内存兜底 repository readback

继续审计 News item-process worker 时发现，`NewsItemProcessWorker` 在同一事务内写入 `news_item_entities`、`news_token_mentions`、`news_fact_candidates`、content classification、market scope 和 story identity 后，会调用 `load_agent_admission_contexts(...)` 重新读取 PostgreSQL 上下文；但 `_agent_admission_context(...)` 仍带 `fallback_item`、`fallback_entities`、`fallback_token_mentions`、`fallback_fact_candidates` 参数，当 repository 没有返回完整 context 时用 worker 内存补齐。

这会把 agent admission 的输入从“已持久化事实 readback”退回到“本次 worker 计算的内存对象”，掩盖 repository 查询缺字段、事务可见性或 fake repository 未遵循真实契约的问题。成熟 Kappa/CQRS 里，item-process 可以在同一事务里先写事实再读回投影输入，但 admission context 必须来自 PostgreSQL repository contract；缺失 context 应 fail fast 并走 worker retry/terminal 状态，而不是继续生成 admission 和 brief dirty target。

已修复：

- `NewsItemProcessWorker` 删除 `_agent_admission_context(...)` 的内存 fallback 参数。
- `load_agent_admission_contexts(...)` 缺少 item/entities/token_mentions/fact_candidates/exact_duplicate_candidates/story_candidates 时 fail closed。
- 单元测试用缺失 agent-admission context 的 fake repository 证明 worker 不会继续写 agent admission。
- architecture guard 禁止 `fallback_item` / `fallback_entities` / `fallback_token_mentions` / `fallback_fact_candidates` 重新进入 `news_item_process_worker.py`。

## 根因十五：News fetch dirty target 用当前 item 兜底 repository affected set

继续审计 News fetch 写入链路时发现，`NewsRepository.upsert_canonical_news_item(...)` 已经返回 `affected_news_item_ids`，这个集合包含 canonical upsert、provider-article remap、material duplicate remap 和旧 item cleanup 后真正需要重投影的 item；但 `NewsFetchWorker` 又把这个集合交给 `_affected_news_item_ids(news, fallback_news_item_id=news_item_id)`，当 repository 没有返回 affected set 时用当前 `news_item_id` 兜底。

这会把“数据库没有给出权威影响集合”的契约失败伪装成正常写入：fetch run 会继续计入 `processed=1`，并向 page projection 发 dirty target。成熟 Kappa/CQRS 里，canonical merge/remap 后的受影响读模型集合必须由持久化写入边界给出；worker 不能从本次返回的代表 item 自造 affected set，否则会漏掉旧 item cleanup、隐藏 repository/fake 契约漂移，并让 read model 重建链路看起来健康。

已修复：

- `NewsFetchWorker` 对 `inserted/updated` canonical upsert 结果要求非空 `affected_news_item_ids`。
- 删除 `fallback_news_item_id` 和空 affected set 兜底。
- 缺失 affected set 时在同一 fetch run 中 fail closed，记录 failed fetch run，不发 `news_item_written` dirty target 或 wake。
- architecture/unit guard 证明该兼容兜底不能被恢复。

## 根因十六：News projection dirty enqueue 缺 servable repository filter 时直接放行

继续审计 News projection dirty enqueue helper 时发现，`enqueue_page_reprojection(...)` 和 `enqueue_item_brief_work(...)` 都通过 `_servable_news_item_ids(...)` 过滤 item；但 helper 使用 `getattr(repos, "news", None)` / `getattr(news_repo, "servable_news_item_ids", None)`，当 repository 没有该方法时直接 `return item_ids`。

这会把“缺少 PostgreSQL servable filter”变成“所有传入 ids 都可服务”。在 canonical merge/delete、source disable、zero-edge cleanup 之后，`servable_news_item_ids(...)` 是防止已经不可服务 item 进入 page/brief dirty queue 的权威 DB 过滤。成熟 Kappa/CQRS 里，dirty target helper 不能用测试 fake 或旧 repository 兼容路径绕过这个过滤；缺少 repository contract 应 fail closed，而不是继续写控制队列。

已修复：

- `_servable_news_item_ids(...)` 直接调用 `repos.news.servable_news_item_ids(item_ids)`。
- 缺少该 repository contract 时抛出 `ValueError`，不 enqueue page/brief dirty targets。
- architecture/unit guard 禁止 `getattr` / `return item_ids` fallback 回到 projection work helper。

## 根因十七：Token Radar source-dirty queue 被当成可选兼容 contract

继续审计 Token Radar 增量投影链路时发现，`IngestService`、`reprocess_recent_token_intents(...)`、`TokenRadarProjectionWorker` 和 `TokenRadarProjection.rebuild_dirty_targets(...)` 都把 `token_radar_source_dirty_events` 当成“可能不存在”的 repository：缺失时不 enqueue、不 claim，或者把 source claim 当成空队列。

这不是普通容错，而是 CQRS 链路的断边：事件/解析事实已经写入 PostgreSQL，但负责重建 `token_radar_rank_source_events` 的源事件 dirty queue 可以被静默跳过。结果是 current rows 可能继续依赖旧 source edges，除非后续全窗口刷新或人工 repair 偶然覆盖。成熟 Kappa/CQRS 里，事实写入和投影 dirty queue 必须是显式 contract；缺失 contract 应 fail closed，让 worker status/test 立刻暴露，而不是返回“没有工作”。

已修复：

- `IngestService` 默认构造并使用正式 `TokenRadarSourceDirtyEventRepository`，不再因未注入而跳过 source dirty enqueue。
- `resolution_refresh` reprocess 成功产生 resolved event edge 时，直接调用 `repos.token_radar_source_dirty_events.enqueue_events(...)`。
- `TokenRadarProjectionWorker` 和 projection service 直接 claim `token_radar_source_dirty_events`；缺 repo 时 worker 失败并记录错误，service 直接暴露 contract failure。
- architecture/unit guard 禁止 `getattr(...token_radar_source_dirty_events..., None)`、`else []` 和 `is not None` 可选路径回到 Token Radar 增量链路。

## 根因十八：Notification 外部投递 requeue 被 insert-only fallback 隐藏

继续审计 notification worker 时发现，`NotificationWorker._enqueue_external_deliveries_with_repository(...)` 在聚合后的 `news_high_signal` 需要重新激活外部 push delivery 时，会先用 `getattr(repository, "enqueue_or_requeue_delivery", None)` 探测 requeue 方法；如果方法不存在，则 fallback 到 `repository.enqueue_delivery`。

这会把“缺少 failed/dead delivery reactivation contract”伪装成正常处理。对于已经存在且失败的 `notification_deliveries(notification_id, channel_id)`，insert-only `enqueue_delivery` 只会 `ON CONFLICT DO NOTHING`，返回 `None`，失败投递保持 failed/dead；但 worker 不会暴露 repository contract 缺失。成熟 Kappa/CQRS 里，`notification_deliveries` 是 side-effect 控制面 ledger，重新激活 failed/dead delivery 是明确的 PostgreSQL 状态转换，不能用旧 insert-only 语义兼容。

已修复：

- 聚合 high-signal 外部 delivery reactivation 直接调用 `repository.enqueue_or_requeue_delivery`。
- 新通知行仍使用 `repository.enqueue_delivery`，两种语义不混用。
- 缺少 requeue repository contract 时 unit test 证明 worker fail closed，而不是静默跳过 failed/dead delivery reactivation。
- architecture guard 禁止 `getattr(repository, "enqueue_or_requeue_delivery", None)` 和 `if enqueue is None` fallback 回到 worker。

## 根因十九：Pulse low-information hide 被 optional no-op 隐藏

继续审计 Pulse worker 时发现，低信息 gate 会在不 hydrate source timeline 的情况下尝试隐藏已有 public candidate；但 `_hide_existing_public_candidate_for_low_information(...)` 通过 `getattr(repos.pulse_candidates, "hide_public_candidate_for_low_information", None)` 探测方法，缺失时直接 `return None`。随后 `scan_triggers_once(...)` 会把 dirty trigger 标记 done。

这会把“无法写入 hidden public row”伪装成“没有需要隐藏的 row”。如果旧 public candidate 仍是 `display_trade_candidate` / `display_token_watch`，低信息 gate 本应把它写成 `hidden_blocked_low_information`，否则 public read model 会继续展示过时状态。成熟 Kappa/CQRS 里，public visibility transition 是 read model writer 的正式职责；缺少 repository method 应让 dirty trigger fail/retry，而不是吞掉状态转换。

已修复：

- `PulseCandidateWorker` 低信息 gate 直接调用 `repos.pulse_candidates.hide_public_candidate_for_low_information(...)`。
- 缺少 hide repository contract 时 dirty trigger 走 `mark_error`，不会 `mark_done`。
- architecture/unit guard 禁止 optional low-information hide fallback 回到 worker。

## 根因二十：Macro assets daily brief 读路径把缺仓储契约当成空 read model

继续审计后端 public read path 时发现，`/api/macro/modules/assets` 的 daily brief 读取通过 `getattr(repos.macro_intel, "latest_macro_daily_brief", None)` 探测仓储方法；缺失时直接返回 `None`。这会把“API/read repository contract 不完整”伪装成“`assets_today` brief 暂无数据”。

这不是用户可见的正常 partial 状态，而是 CQRS 读模型边界断裂：`macro_daily_briefs` 是 `MacroDailyBriefProjectionWorker` 写入的稳定 read model，路由只应该读取这张持久化 read model。真正没有 brief row 可以返回空值；但 repository 方法不存在说明 runtime session 或测试 fake 没有实现当前 contract，应该立即暴露。成熟 Kappa/CQRS 里，public read path 不用 optional loader 兼容旧仓储形状。

已修复：

- `_daily_brief(...)` 直接调用 `repos.macro_intel.latest_macro_daily_brief(brief_key="assets_today")`。
- 正常 fake repository 补齐真实读契约；缺契约 fake 证明 API 会 fail closed，而不是返回正常 assets module。
- architecture guard 禁止 optional daily brief loader fallback 回到 Macro public read path。

## 根因二十一：Macro crypto-derivatives CEX board 把缺 repository 当成无 board

继续检查同一个 Macro module 路由时发现，`/api/macro/modules/assets/crypto-derivatives` 通过 `getattr(repos, "cex_oi_radar", None)` 探测 CEX board repository；缺失时返回 `None`，从而让模块正常返回但不带 board。

这会把 repository/session contract 缺失伪装成“没有 CEX board”。真实 PostgreSQL repository 已经能用 `latest_board(limit=20)` 返回 `publication/state/rows`，没有 publication state 时会返回 `publication=None, rows=[]`，模块层可以把它呈现为 `missing`。因此缺 repository 不是产品级缺数据，而是后端读路径 wiring 错误。成熟 Kappa/CQRS 里，跨域 read model consumer 可以读持久化 read model，但不能用 optional repo 兼容旧 session 形状。

已修复：

- `_cex_board(...)` 直接调用 `repos.cex_oi_radar.latest_board(limit=20)`。
- 缺 CEX board repository 的 fake 证明 API 会 fail closed，而不是成功返回一个少表的 crypto-derivatives module。
- architecture guard 禁止 optional `cex_oi_radar` repository fallback 回到 Macro public read path。

## 根因二十二：Token Case CEX detail 把缺 snapshot repository 当成无 detail

继续审计 Token Case / Search Inspect 的 CEX token dossier 时发现，`TokenCaseService._cex_detail(...)` 先判断 `self.cex_detail_snapshots is None`，再用 `getattr(..., "latest_snapshot", None)` 探测方法；缺 repository 或缺方法时直接返回 `None`。同时 `/api/search/inspect` 构造 `SearchInspectService` 时没有传入 `repos.cex_detail_snapshots`，导致 Search Inspect 的 `CexToken` token_result 和 `/api/token-case` 读契约不一致。

这会把 repository/session wiring 错误伪装成“这个 CEX token 没有 detail”。真实的产品缺数据应该是 `cex_detail_snapshots` 表里没有当前 snapshot 行，此时返回结构化 `status="missing"` detail；但 repository 方法不存在说明后端读路径没有接上正式 read model。成熟 Kappa/CQRS 里，`cex_detail_snapshots` 是 `CexOiRadarBoardWorker` 写出的 current read model，Token Case 和 Search Inspect 只能读取 PostgreSQL 投影，不能用 optional repository 兼容旧测试 fake 或旧 session 形状。

已修复：

- `TokenCaseService._cex_detail(...)` 对 `CexToken` 直接调用 `self.cex_detail_snapshots.latest_snapshot(...)`。
- Search Inspect 构造 Token Case dossier 时传递同一个 `cex_detail_snapshots` repository。
- `/api/search/inspect` 路由从 repository session 注入 `repos.cex_detail_snapshots`。
- architecture/unit guard 禁止 `getattr(self.cex_detail_snapshots, "latest_snapshot", None)`、`self.cex_detail_snapshots is None` 和缺 repository 兼容路径回到 CEX detail。

## 根因二十三：Token Case market_live 把缺 latest tick repository 当成无市场快照

继续检查同一个 Token Case dossier 时发现，`market_live` 虽然已经 hard-cut 到只读持久化 market tick，不再调用 `LivePriceGateway`，但 `_latest_market_tick(...)` 仍用 `getattr(targets, "latest_market_tick", None)` 探测方法；缺方法或不可调用时直接返回 `None`，上层再把它渲染成 `market_live.status="missing"`。

这会把 repository/session contract 缺失伪装成“这个 target 暂无市场快照”。真实产品缺数据应该是 `market_tick_current` 没有当前 tick 行；但 `latest_market_tick` 方法不存在说明 Token Case 没有接上正式 PostgreSQL 读契约。成熟 Kappa/CQRS 里，market-live 读块只能来自持久化 market tick/current read model，不能用 optional repository 兼容旧 fake 或旧 session 形状。

已修复：

- `_latest_market_tick(...)` 直接调用 `targets.latest_market_tick(...)`。
- 缺 `latest_market_tick` 的 fake target repository 证明 Token Case fail closed，而不是返回正常 dossier。
- architecture guard 禁止 `getattr(targets, "latest_market_tick", None)` 和 `if not callable(latest)` 回到 market-live 读路径。

## 根因二十四：Pulse dirty-trigger 把缺 job/edge/capacity repository 契约当成空控制面

继续扫描 Pulse worker 时发现，`PulseCandidateWorker._enqueue_if_due(...)` 仍通过 `_call_optional(repos.pulse_jobs, "job_for_candidate", ...)` 和 `_call_optional(repos.pulse_admission, "edge_state_by_candidate", ...)` 探测正式控制面读契约；缺方法时被当成“没有已有 job / 没有 edge state”。同一文件里 `recent_target_failure_count`、`pending_agent_job_count`、`pending_agent_job_count_for_window_scope` 和 `pulse_trigger_dirty_targets.queue_depth` 缺方法时也返回 `0`。

这不是 harmless fake 兼容：这些值决定 Pulse 是否重复 enqueue、是否进入 score-band pending、是否触发 recent-failure circuit、是否按全局/窗口 pending job 容量限流，以及 worker 是否看到 due dirty-target backlog。缺 repository 方法代表 Pulse worker 没有接上正式 PostgreSQL 控制面契约；成熟 Kappa/CQRS 里，控制面状态不是产品事实，但它仍是 worker 正确性的一部分，不能被 silent fallback 成空状态。

已修复：

- `_enqueue_if_due(...)` 直接调用 `repos.pulse_jobs.job_for_candidate(...)` 和 `repos.pulse_admission.edge_state_by_candidate(...)`。
- recent failure、pending job count、window/scope pending count、dirty-trigger queue depth 都直接调用正式 repository 方法。
- 缺 `job_for_candidate` 的 fake Pulse job repository 证明 dirty trigger fail/retry，而不是被标记 done。
- architecture guard 禁止 `_call_optional` 和这些 Pulse dirty-trigger state/capacity/queue-depth optional fallback 回到 runtime。

## 根因二十五：Token profile current worker 缺 source-query 契约时自建查询对象

继续扫描 Asset Market worker 时发现，`TokenProfileCurrentWorker` 在 claim `token_profile_current_dirty_targets` 后，通过 `getattr(repos, "source_query", None) or TokenProfileSourceQuery(repos.conn)` 读取 profile source exact-load 查询。也就是说，如果 `RepositorySession` 没有暴露正式 `source_query`，worker 会直接拿 `repos.conn` 自建 query 并继续执行。

这类代码看起来只是方便测试，但架构风险很具体：`token_profile_current` 是公共 profile/icon 当前读模型，输入必须来自同一个 worker session 上的正式 PostgreSQL repository/query contract。缺 `source_query` 代表 runtime session 没有接完整 source exact-load 契约；继续自建 query 会让 fake/session 漏字段、连接生命周期、事务可见性和注入边界问题被掩盖。

已修复：

- `RepositorySession` 显式暴露 `source_query: TokenProfileSourceQuery`。
- `TokenProfileCurrentWorker` 直接调用 `repos.source_query`，不再 import 或自建 `TokenProfileSourceQuery(repos.conn)`。
- 缺 `source_query` 的 fake repository 证明 dirty target 失败/重试，错误指向缺 repository-session 契约，而不是继续碰 `conn.execute`。
- architecture guard 禁止 worker 重新引入 `getattr(repos, "source_query", None)` 或 `TokenProfileSourceQuery(repos.conn)` fallback。

## 根因二十六：Notification worker 缺 unit_of_work 时回到 nullcontext 和手动 commit

继续扫描 Notifications worker 时发现，`NotificationWorker._process_once_sync(...)` 使用 `_unit_of_work_if_available(repos)` 包住写入；当 repository session 没有 `unit_of_work` 时，helper 返回 `nullcontext()`，worker 仍会写 `notifications` facts 和 `notification_deliveries` 控制行，最后再通过 `_commit_if_available(getattr(repos, "notifications", None))` 探测 repository 连接并手动 commit。

这类兼容路径把最关键的 PostgreSQL 事务边界变成了“如果 session 支持就用，不支持也能写”。在 Kappa/CQRS 里，notification rule 同时创建业务事实和外部 delivery 控制行，这两类写入必须属于同一个 worker-session Unit of Work；缺 UoW 是 runtime/session contract 错，不是测试 fake 或老 session shape 可以绕过的可选能力。否则一旦 fake/session 漏方法，测试会继续绿，生产代码也会保留第二套 commit 语义，审计时无法证明 notification fact 与 delivery control row 的原子性。

已修复：

- `NotificationWorker` 直接进入 `repos.unit_of_work()`，缺 session UoW 会在任何通知写入前 fail fast。
- 删除 `_unit_of_work_if_available`、`_has_unit_of_work`、`_commit_if_available` 和 `nullcontext` fallback。
- 单测 fake session 显式提供最小 `unit_of_work`，不再让测试依赖旧兼容形状。
- 缺 `unit_of_work` 的 fake repository 证明 worker 不写 `notifications` 和 `notification_deliveries`，而是暴露 session contract error。
- architecture guard 禁止重新引入 optional UoW、manual commit 或 `getattr(repos, "notifications", None)` fallback。

## 根因二十七：Macrodata bundle import 缺 session UoW 时回退到 conn.transaction

继续扫描 Macro offline replay/seed 路径时发现，`import_macrodata_bundle(...)` 不是直接进入 `RepositorySession.unit_of_work()`，而是通过 `_unit_of_work(repos)` 探测 `repos.unit_of_work`；缺失时继续探测 `repos.conn.transaction()` 并照常导入。`write_macrodata_bundle_import(...)` 也通过 `_require_transaction(repos, ...)` 探测 `repos.require_transaction`，缺方法时抛一个 helper 自己构造的运行时错误，而不是让 session contract 缺失在调用点 fail fast。

这条路径容易被误判为“只是 CLI/offline seed”，但它写入的是正式 Kappa material facts 和控制面：`macro_observations` 是事实，`macro_import_runs` 是导入审计，`macro_projection_dirty_targets` 会驱动后续 macro view projection。它们必须共享同一个 `RepositorySession` 事务契约；缺 `unit_of_work` 或 `require_transaction` 代表 runtime/test session 没接完整，不是可以降级到 raw connection transaction 的兼容能力。

根因和 Notification UoW 一样：第二套事务入口让测试 fake 和旧 session shape 保持绿灯，掩盖事实写、import-run 审计、dirty-target enqueue 是否真的在同一个正式 session 生命周期内。成熟 Kappa/CQRS 的 offline replay 也只是事实输入入口，不是绕过业务真相/投影控制面事务边界的后门。

已修复：

- `import_macrodata_bundle(...)` 直接 `with repos.unit_of_work():`，缺 UoW 会在任何 macro fact 写入前 fail fast。
- `write_macrodata_bundle_import(...)` 直接调用 `repos.require_transaction(operation="macrodata_bundle_import")`，不再通过 optional helper 探测。
- 删除 `_unit_of_work(...)`、`_require_transaction(...)`、`repos.conn.transaction()` fallback 和 helper 自造错误。
- 缺 `unit_of_work` 的 fake session 即使提供 `conn.transaction()`，也证明不会写 `macro_observations` 或 `macro_import_runs`。
- 缺 `require_transaction` 的 fake session 证明写函数必须暴露正式 session transaction contract，而不是落入 helper 兼容错误。
- architecture guard 禁止重新引入 optional UoW、raw `conn.transaction()` fallback 或 optional `require_transaction`。

## 根因二十八：Pulse candidate job service 缺 session transaction 时回到 nullcontext

继续审计 Pulse agent 写路径时发现，`PulseCandidateJobService.run_job(...)` 旧实现通过 `_transaction(repos.conn)` 包住多段写入；helper 会在连接对象有 `transaction()` 时打开 raw connection transaction，缺方法时返回 `nullcontext()`。这让 Pulse agent 的核心写入路径不再依赖正式 `RepositorySession.transaction()`。

这不是普通测试便利代码。`PulseCandidateJobService` 同一次 job 会写 `pulse_agent_runs`、`pulse_agent_run_steps`、`pulse_agent_eval_*`、`pulse_candidates`、`pulse_playbooks`、`pulse_candidate_edge_state` / admission state，以及 `pulse_agent_jobs` terminal state。它们共同构成 Pulse agent 的审计账本、候选 public/hidden 状态、deterministic eval 结果和控制面 job 终态；这些写入必须共享同一个 repository-session transaction contract。

根因和 Notification/Macrodata 的 session 兼容层相同：生产代码保留第二套事务入口，测试 fake 即使没实现 session transaction 也可以继续写，架构审计就无法证明 agent run ledger、eval、candidate row、playbook snapshot、admission edge state 和 job terminal state 是同一正式 Unit of Work 内的结果。成熟 Kappa/CQRS 不把“缺事务能力”解释成“无事务也可以写”；缺 session transaction 本身就是 runtime/session contract 错误，应在第一笔写入前暴露。

已修复：

- `PulseCandidateJobService` 四个写入块全部直接进入 `repos.transaction()`。
- 删除 `_transaction(conn)`、`nullcontext()`、`hasattr(conn, "transaction")` 和 raw `conn.transaction()` fallback。
- 正常 fake repository session 显式提供最小 `transaction()`，测试不再依赖旧连接 helper。
- 缺 `transaction` 的 fake session 证明 job service 在任何 `pulse_agent_runs`、run step、eval case、candidate upsert、job success/failure 写入前抛出 session contract error。
- architecture guard 禁止重新引入 `_transaction(repos.conn)`、`nullcontext`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()`。

## 根因二十九：News page/source-quality 投影 worker 缺 session transaction 时回到 nullcontext

继续审计 News 投影写路径时发现，`NewsPageProjectionWorker` 和 `NewsSourceQualityProjectionWorker` 都通过 `_transaction(repos.conn)` 包住 claim、投影、替换、mark done/error 和后续 dirty enqueue。helper 会在连接对象没有 `transaction()` 时返回 `nullcontext()`，也就是缺正式事务能力时仍继续写。

这不是 harmless projection 代码。page worker 写 `news_page_rows` 并标记 `news_projection_dirty_targets` 完成或错误；source-quality worker 写 `news_source_quality_rows`、更新 `news_sources.source_quality_status`，并在 compact source status 改变时 enqueue page dirty work。它们虽然写的是可重建 read model 和控制面队列，但仍然是 Kappa/CQRS serving 链路的一部分，必须由正式 `RepositorySession.transaction()` 约束。

根因和 Notification、Macrodata、PulseCandidateJobService 相同：第二套 raw connection 事务入口让测试 fake 和旧 session shape 在缺 session transaction 时继续绿灯，架构审计就无法证明 claim、projection write、dirty enqueue、mark done/error 处在同一个正式 worker-session transaction contract 内。成熟 Kappa/CQRS 里，缺事务能力是 runtime/session contract 错误，应在领取 dirty target 前暴露，而不是把 claim 后的写入落到 autocommit 或无事务路径。

已修复：

- `NewsPageProjectionWorker` 的外层 claim/mark 和内层 projection/replace 写块全部直接进入 `repos.transaction()`。
- `NewsSourceQualityProjectionWorker` 的 claim、source-quality rows/status 写、page dirty enqueue、mark done/reschedule 写块全部直接进入 `repos.transaction()`。
- 删除两个 worker 内的 `_transaction(conn)`、`nullcontext()`、`getattr(conn, "transaction", None)` 和 `_transaction(repos.conn)`。
- 正常 News 投影测试 fake 显式提供最小 `transaction()`，缺 transaction 的 fake session 证明 worker 在 dirty target claim 之前 fail fast，不写 page rows、source-quality rows、dirty enqueue、done/error 标记。
- architecture guard 禁止两个 News projection worker 重新引入 `_transaction(repos.conn)`、`nullcontext` 或 raw connection transaction fallback。

## 根因三十：PulseCandidateWorker 外层 dirty-trigger 写路径仍使用 raw connection transaction

继续审计 Pulse runtime worker 时发现，`PulseCandidateWorker.scan_triggers_once(...)` 和 `_enqueue_if_due(...)` 仍通过 `_transaction(repos.conn)` 包住 dirty target claim、mark done/error、admission claim、edge-state 写入、public row visibility transition 和 `pulse_agent_jobs` enqueue。当前 helper 已经不会再 `nullcontext` 静默通过，但它仍以 raw `conn.transaction()` 为正式入口，而不是要求 `RepositorySession.transaction()`。

这会留下一个比 job service 更外层的事务治理裂缝：即使 `PulseCandidateJobService` 的 agent ledger/eval/candidate/playbook/job terminal 写入已经收敛到 session transaction，PulseCandidateWorker 仍然可以在 repository session 没有 `transaction()` 的情况下，只要 `repos.conn.transaction()` 存在就继续 claim dirty trigger、写 admission/budget 控制行、隐藏低信息 public row、enqueue agent job 或标记 dirty done/error。

成熟 Kappa/CQRS 的 worker session contract 不应该有两套事务入口。`pulse_trigger_dirty_targets` 是控制面队列，`pulse_candidate_edge_state` 和 `pulse_candidates` 是 serving/read-model 状态，`pulse_agent_jobs` 是后续 agent job 的控制面；这些写入必须共享正式 `RepositorySession.transaction()`，缺 session transaction 应该在领取 dirty target 之前暴露，而不是被 raw connection 兼容层吸收。

已修复：

- `PulseCandidateWorker` 的外层 claim/queue-depth、每个 dirty trigger 处理块、error mark、admission claim/job enqueue 写块全部直接进入 `repos.transaction()`。
- 删除 worker 内 `_transaction(conn)` helper 和 `_transaction(repos.conn)` 调用。
- dirty-trigger 单测 fake 显式提供最小 `transaction()`；新增缺 session transaction 的 fake 证明 worker 在 dirty target claim 前 fail fast。
- architecture guard 禁止 `PulseCandidateWorker` 重新引入 `_transaction(repos.conn)`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()` fallback。

## 根因三十一：News fetch/process/brief runtime 写 worker 仍使用 raw connection transaction

继续审计 News runtime 写路径时发现，`NewsFetchWorker`、`NewsItemProcessWorker` 和 `NewsItemBriefWorker` 仍直接使用 `repos.conn.transaction()`。它们没有 `nullcontext` fallback，但仍然绕过了正式 `RepositorySession.transaction()`，让 repository session 缺少 `transaction()` 的 fake 或旧 session shape 继续通过，只要底层 `conn.transaction()` 存在即可。

这组三个 worker 是 News Intel 的事实和 agent/read-model 前置链路：fetch 写 `news_sources`、`news_fetch_runs`、`news_provider_items`、`news_items` 并 enqueue page/source-quality dirty work；item-process 写 entity/token mention/fact candidate、content classification、market scope、story identity、agent admission 和 page/brief dirty work；item-brief 写 `news_item_agent_runs` / current brief、agent admission update 和 page dirty work。它们不是普通 repository helper，而是 News material facts、agent audit ledger、current brief read model 和下游投影控制面的正式 writer。

根因仍是第二套事务入口。成熟 Kappa/CQRS 中，worker session 是事实写入和控制面状态转换的生命周期边界；缺 session transaction 是 runtime/session contract 错，应在 reconcile/claim/write 之前暴露。否则测试 fake 可以只实现 `conn.transaction()`，生产代码也会长期保留 raw connection 事务路径，审计时无法证明 News provider observation、canonical item fact、agent admission、brief ledger 和 projection dirty targets 都在正式 worker-session transaction contract 内。

已修复：

- `NewsFetchWorker` 的 source reconcile/claim、fetch-run start、not-modified finish、provider item/canonical item persist、fetch-run failure 写块全部直接进入 `repos.transaction()`。
- `NewsItemProcessWorker` 的 expired-processing release/claim、deterministic fact/admission write、failure terminal/retry 写块全部直接进入 `repos.transaction()`。
- `NewsItemBriefWorker` 的 policy-skip admission/page dirty/done 写块和 current brief upsert/page dirty 写块全部直接进入 `repos.transaction()`。
- 正常 News worker fake session 显式提供最小 `transaction()`；缺 session transaction 的 fake 证明 fetch 在 source reconcile 前 fail fast、item-process 在 release/claim 前 fail fast、item-brief 在 policy-skip write 前 fail fast。
- architecture guard 禁止三个 News runtime 写 worker 重新引入 `repos.conn.transaction()` 或 raw `conn.transaction()` fallback。

## 根因三十二：EventAnchorBackfillWorker stale cleanup 缺 UoW 时仍手动 commit

继续审计 Asset Market worker 时发现，`EventAnchorBackfillWorker._expire_stale_jobs(...)` 仍只打开普通 `_worker_session()`，调用 `repos.event_anchor_jobs.expire_stale(...)` 后再通过 `_commit_if_supported(repos)` 探测 `repos.conn.commit()` 或 `repos.commit()` 手动提交。也就是说，即使 repository session 没有正式 `unit_of_work()`，stale cleanup 仍会 terminalize `event_anchor_backfill_jobs`，并把对应 `enriched_events` 标记为 terminal。

这条路径写的是两类必须原子一致的 PostgreSQL 状态：`event_anchor_backfill_jobs` 是 event-anchor provider catch-up 的控制面，`enriched_events` 是公开事件 market context 的事实/投影生命周期。成熟 Kappa/CQRS 里，stale cleanup 不是“清理一下队列”的边角逻辑，它会决定事件是否永久进入 expired/failed anchor 状态；缺 worker-session UoW 应该在 cleanup 前 fail fast，而不是由 worker-local manual commit 兼容旧 session shape。

已修复：

- `_expire_stale_jobs(...)` 改为进入 `_transaction_session()`，即 `repos.unit_of_work()`。
- 删除 `_commit_if_supported(...)` 和对 `conn.commit()` / `repos.commit()` 的手动探测。
- 缺 `unit_of_work` 的 fake session 证明 stale cleanup 在任何 `event_anchor_backfill_jobs` 或 `enriched_events` terminal 写入前 fail fast。
- architecture guard 禁止 `EventAnchorBackfillWorker` stale cleanup 重新引入 `_commit_if_supported`、manual `commit()` 或普通 worker session。

## 根因三十三：TokenCaptureTierWorker projection 仍保留 manual commit / claim-before-transaction 兼容

继续审计 Asset Market capture lane 时发现，`TokenCaptureTierWorker._project_once(...)` 旧路径会先以 `commit=True` claim `token_capture_tier_dirty_targets`，然后才进入投影写入逻辑；同时 `project_once(..., commit: bool = True)` 会写 `token_capture_tier` 后通过 `_commit_if_supported(repos)` 探测 `repos.conn.commit()` 或 `repos.commit()` 手动提交。

这条路径看似只是 capture tier 控制面投影，但它决定后续 market tick stream/poll worker 订阅或轮询哪些标的。`token_capture_tier_dirty_targets` 的 claim/lease、`token_capture_tier` tier rows 和 demotion、以及 dirty target done 状态必须属于同一 session transaction。否则可能出现 dirty target 已被租约 claim、tier row 已写入或 demotion 已发生，但 done/error 状态与它们不在同一个原子边界内；缺失 session transaction 时，测试 fake 也会继续通过 manual commit 兼容路径掩盖真实 runtime contract 错误。

成熟 Kappa/CQRS 的判断是：`token_capture_tier` 是可重建 capture-control read model，单 runtime writer 是 `TokenCaptureTierWorker`。dirty target queue 是唤醒和 bounded catch-up 控制面，不是允许半事务 claim 的事实源；projection helper 不能自带 commit 开关，也不能在 worker session contract 缺失时替 runtime 做兼容提交。

已修复：

- `_project_once(...)` 现在先进入 `repos.transaction()`，再 claim `token_capture_tier_dirty_targets`，并在同一 transaction 内完成 `project_once(...)` 和 `mark_done(...)`。
- `project_once(...)` 删除 `commit` 参数，入口直接调用 `repos.require_transaction(operation="token_capture_tier_projection")`。
- 删除 `_commit_if_supported(...)` 和对 `conn.commit()` / `repos.commit()` 的手动探测。
- 缺 `transaction` 的 fake session 证明 worker 在 dirty target claim 前 fail fast；直接调用 `project_once(...)` 而无外部 transaction 也 fail fast，不会写 registry/tier/demotion。
- architecture guard 禁止 `TokenCaptureTierWorker` 重新引入 `_commit_if_supported`、`commit=True`、`commit: bool` 或 manual `commit()`，并要求 claim 发生在 `repos.transaction()` 之后。

## 根因三十四：EventAnchorBackfillJobRepository terminal paths 仍保留 nullcontext transaction fallback

继续向下审计 Event Anchor repository 时发现，worker stale cleanup 虽已要求 worker-session `unit_of_work`，但 `EventAnchorBackfillJobRepository.expire_stale(...)` 与 `mark_terminal(...)` 仍通过 `_transaction(self._conn)` 包裹 job terminalization 与 terminal ledger 写入；旧 `_transaction(conn)` 在缺 `conn.transaction()` 时返回 `nullcontext()`。

这会让直接 repository 调用或测试 fake 在缺正式 connection transaction 时仍更新 `event_anchor_backfill_jobs` 并写 `worker_queue_terminal_events`。也就是说，Root32 已经修掉的 worker UoW 边界，会在 repository 层被重新打穿：worker 表面上进入了正式 session，但 repository 自己仍允许“无事务也能 terminalize”的第二套兼容入口。

成熟 Kappa/CQRS 的判断是：Event Anchor repository terminal path owns atomic job state + terminal ledger transition。`event_anchor_backfill_jobs` 和 `worker_queue_terminal_events` 是同一次 job lifecycle transition 的两面，缺 connection transaction 是 repository/session contract 错误，应该在第一条 terminal SQL 前失败，而不是用 `nullcontext` 兼容旧 fake 或旧连接形状。

已修复：

- `_transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("event_anchor_repository_transaction_required")`。
- `expire_stale(...)` 和 `mark_terminal(...)` 继续共享 `_transaction(self._conn)`，但不再允许 `nullcontext` fallback。
- 缺 `transaction` 的 fake connection 证明 `expire_stale(...)` 在任何 SQL 前 fail fast。
- architecture guard 禁止 `EventAnchorBackfillJobRepository` 重新引入 `nullcontext`、`return nullcontext()` 或 `if callable(transaction):` fallback。

## 根因三十五：Queue Terminal operator resolve 缺事务时仍执行 FOR UPDATE

继续向下审计平台级 terminal ledger 时发现，`parallax.platform.db.queue_terminal.resolve_terminal_event(...)` 虽然用 `SELECT ... FOR UPDATE` 读取 `worker_queue_terminal_events`，但 `_transaction(conn)` 在连接没有 `transaction()` 时仍返回 `nullcontext()`，随后照常更新 `operator_action`、执行 retry transition，并保留了“没有 transaction 属性就手动 `conn.commit()`”的兼容分支。

这比普通 repository fallback 更危险：`FOR UPDATE` 的意义依赖事务边界。没有正式 transaction 时，operator 的 retry/archive/quarantine 决策就无法被证明与当前 terminal row snapshot、retry transition、operator audit update 处在同一个锁保护生命周期内。成熟 Kappa/CQRS 的 operator terminal ledger 不是可选增强日志，而是控制面状态机的一部分；operator action resolve 必须是一个原子状态转换。

根因仍是“为了兼容旧 fake/旧连接形状，平台 helper 把缺事务能力解释成可以无事务执行”。这会让测试继续绿灯，却掩盖 PostgreSQL 最基本的 row-locking contract：`FOR UPDATE` 需要事务，operator action update 需要和 retry transition 同生同死。成熟实现应把缺 `transaction()` 暴露为 session/connection contract failure，而不是在 platform db helper 里静默降级。

已修复：

- `_transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("queue_terminal_transaction_required")`。
- `resolve_terminal_event(...)` 删除 `nullcontext` fallback 和手动 `conn.commit()` 分支。
- 缺 `transaction` 的 fake connection 证明 operator resolve 在任何 SQL 前 fail fast。
- architecture guard 禁止 `queue_terminal` 重新引入 `nullcontext`、`hasattr(conn, "transaction")` 或 operator resolve 内的 manual commit。

## 根因三十六：Discovery terminalize lookup claims 仍保留 nullcontext transaction fallback

继续审计 Asset Market discovery queue 时发现，`DiscoveryRepository.terminalize_lookup_claims(...)` 会先删除已 claim 的 `token_discovery_dirty_lookup_keys`，再把同一 source row 写入 `worker_queue_terminal_events` terminal ledger；但它依赖的 `_transaction(self.conn)` 仍在缺 `conn.transaction()` 时返回 `nullcontext()`，并在 terminalize block 后保留 `self.conn.commit()`。

这条路径是 `resolution_refresh` 的 terminal state machine：provider retry budget 耗尽、hot not-found 或不可恢复错误都需要把 dirty lookup claim 从 active queue 转成 terminal evidence。如果无事务也能先 delete 再写 terminal ledger，就可能出现 claim 被删除但 terminal evidence 未写、或 terminal evidence 与删除动作不在同一个原子边界内。成熟 Kappa/CQRS 中，control queue terminalization 和 terminal ledger 是一次状态转换的两面，不能靠 helper 兼容旧 fake 的连接形状。

根因和 Event Anchor repository terminal path 相同：repository-level terminal helper 保留了第二套“无事务也可以 terminalize”的入口。它让测试 fake 不必实现正式 connection transaction，也让生产代码无法证明 queue delete 和 terminal ledger write 同生同死。PostgreSQL 最佳实践上，这类 delete-returning + audit insert 必须有明确事务边界。

已修复：

- `_transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("discovery_repository_transaction_required")`。
- `terminalize_lookup_claims(...)` 删除 terminal block 后的 `self.conn.commit()` 手动提交。
- 缺 `transaction` 的 fake connection 证明 terminalize 在任何 delete/ledger SQL 前 fail fast。
- architecture guard 禁止 `DiscoveryRepository` 重新引入 `nullcontext`、`return nullcontext()` 或 `if callable(transaction):` fallback，并要求 terminalize path 不手动 `self.conn.commit()`。

## 根因三十七：News projection dirty target terminalization 仍保留 nullcontext transaction fallback

继续审计 News projection dirty target repository 时发现，`NewsProjectionDirtyTargetRepository.terminalize_targets(...)` 会先删除已 claim 的 `news_projection_dirty_targets`，再把同一 source row 写入 `worker_queue_terminal_events` terminal ledger；但它仍通过 `transaction_factory = getattr(self.conn, "transaction", None)` 在缺 connection transaction 时进入 `nullcontext()`，并保留 terminal block 后的手动 `self.conn.commit()` 兼容分支。

这说明前面 Root26/Root28 修掉的 News worker/session 边界并没有完全闭合：worker 入口已经要求 `RepositorySession.transaction()`，但 repository terminal helper 仍然允许直接调用方或旧 fake 在没有正式 connection transaction 的情况下删除 dirty target 并写 terminal ledger。成熟 Kappa/CQRS 中，dirty target queue 是控制面状态，terminal ledger 是状态机审计证据；`DELETE ... RETURNING` 和 terminal ledger insert 必须是一个 PostgreSQL 原子状态转换，不能因为连接形状缺少 `transaction()` 就退化成无事务执行。

根因仍是“兼容旧连接/fake 形状”的第二套事务入口。它让测试可以不建模真实事务 contract，也让生产代码无法证明 claimed queue row delete 与 terminal evidence 同生同死。一旦中途失败，最坏情况是 dirty target 被删但 terminal evidence 丢失，或者 terminal evidence 与实际 queue state 不一致；这会直接污染 worker backlog、operator terminal ledger 和后续追责/重试判断。

已修复：

- `terminalize_targets(...)` 删除 `nullcontext` 和 terminal block 后的手动 `self.conn.commit()` 分支。
- 新增 `_transaction(conn)`，缺 callable `transaction` 时抛 `RuntimeError("news_projection_dirty_target_transaction_required")`。
- 缺 `transaction` 的 fake connection 证明 terminalize 在任何 delete/ledger SQL 前 fail fast。
- architecture guard 禁止 News projection dirty target repository 重新引入 `nullcontext`、`return nullcontext()` 或 terminalize path 内的 `transaction_factory`/manual commit fallback。

## 根因三十八：Ops projection dirty repair execute 模式缺事务时仍扫描并写队列

继续审计显式 ops repair path 时发现，`enqueue_projection_dirty_targets(..., execute=True)` 会先扫描 `news_items` / `news_sources`，再通过 News dirty enqueue helper 写 `news_projection_dirty_targets`；但 `projection_dirty_targets._transaction(conn)` 在连接缺 `transaction()` 时返回 `nullcontext()`。这意味着真正会写控制面 dirty queue 的 `--execute` 模式，会在缺事务能力时继续执行 broad repair scan 和 dirty target enqueue。

这条路径不是常驻 worker，但它仍然是 Kappa/CQRS 控制面写入口。成熟架构允许 ops repair 做 broad discovery，因为它是显式人工命令，不是 idle worker 热路径；但一旦进入 `execute=True`，它写的是后续 `news_page_projection` / `news_item_brief` / `news_source_quality_projection` 消费的 durable queue。扫描出的目标集合和 enqueue 写入必须处在明确事务边界内，否则测试 fake 可以绕过真实 session contract，生产 operator 也无法证明 repair scan 与 queue writes 是一次一致的状态推进。

根因是 dry-run 与 execute 的事务语义混在同一个 fallback helper 里。`execute=False` 只读统计，可以用 `nullcontext()`；`execute=True` 是写控制面，缺 connection transaction 应该在任何 SELECT 或 enqueue 前 fail fast，而不是把旧连接形状兼容成无事务 repair。

已修复：

- `_transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("projection_dirty_targets_transaction_required")`。
- `execute=False` dry-run 仍由上层显式 `nullcontext()` 保持只读统计语义。
- 缺 `transaction` 的 fake repos 证明 execute repair 在任何 SQL 或 dirty enqueue 前 fail fast。
- architecture guard 禁止 `_transaction(conn)` 重新返回 `nullcontext()` 或使用 optional `getattr(conn, "transaction", None)` fallback，同时要求上层保留 dry-run `nullcontext` 分支。

## 根因三十九：Pulse job terminal/dead paths 仍保留 nullcontext transaction fallback

继续审计 Pulse agent job repository 时发现，`PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`、`mark_job_failed(...)`、`mark_job_cancelled_by_worker_timeout(...)` 和 `terminalize_stale_jobs_by_window(...)` 都会把 `pulse_agent_jobs` 推到 `dead` 或 terminal-like 状态，并通过 `_terminalize_pulse_job(...)` 写 `worker_queue_terminal_events`；但它们共享的 `_transaction(conn)` 在连接缺 `transaction()` 时返回 `nullcontext()`，部分路径还在 block 后保留手动 `self.conn.commit()`。

这条路径是 Pulse 控制面状态机，不是普通日志。`pulse_agent_jobs` 不是产品真相，但它决定 agent work 的 retry、terminal、timeout 和 operator 追责；`worker_queue_terminal_events` 则是 terminal evidence。成熟 Kappa/CQRS 的要求是 job terminal/dead state 和 terminal ledger 同生同死：同一次 PostgreSQL 事务里要么一起完成，要么一起失败。否则可能出现 job 已经 `dead` 但 terminal evidence 没写，或者 terminal evidence 与 job snapshot 不一致，后续 operator retry/归档和 backlog 诊断都会失真。

根因仍是为了兼容旧 fake/旧 connection shape，把“缺事务能力”降级成“无事务也能执行”。这类兼容让单测容易绿，但抹掉了 PostgreSQL 最基本的原子状态转换 contract。正确做法不是在 repository 层猜测 commit，而是在第一条 job-state SQL 前要求 callable connection transaction，缺失时 fail fast。

已修复：

- `_transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("pulse_jobs_repository_transaction_required")`。
- 四个 Pulse job terminal/dead 路径删除 terminal block 后的手动 `self.conn.commit()` 分支。
- 缺 `transaction` 的 fake connection 证明 terminal/dead path 在任何 job-state 或 terminal-ledger SQL 前 fail fast。
- architecture guard 禁止 `PulseJobsRepository` 重新引入 `nullcontext`、`return nullcontext()` 或 `if callable(transaction):` fallback，并要求 terminal/dead path 不手动 `self.conn.commit()`。

## 根因四十：Pulse admission claim 仍通过 shared helper 兼容无事务写入

继续沿着 Pulse repository 层审计时发现，`PulseAdmissionRepository.claim_pulse_admission(...)` 会先写 `pulse_candidate_edge_state` edge observation，再在同一 claim 中 `SELECT ... FOR UPDATE` target/candidate budget rows，并根据结果写 suppression/admission 或 budget increment；但它依赖 `_pulse_repository_shared._transaction(conn)`，而 shared helper 仍在连接缺 `transaction` 时返回 `nullcontext()`。

这条路径决定 Pulse dirty trigger 能否进入 agent job，是 admission 控制面的一次原子状态转换。成熟 Kappa/CQRS 里，edge observation、budget lock/read、budget increment 或 suppression 必须共享同一个 PostgreSQL 事务；否则并发 worker 之间可能出现预算超发、edge state 已观测但 suppression/admission 未落账、或者 budget row 与 admission outcome 不一致。`FOR UPDATE` 在没有明确事务边界时尤其危险，因为 row lock 的生命周期退化成单语句或连接默认行为，无法表达“整次 admission claim”。

根因仍是旧 fake/旧 connection shape 兼容：shared helper 把“缺事务能力”解释成“无事务也可继续”。这会让 repository 单测绕过真实连接 contract，也会把控制面写路径的并发正确性建立在调用方偶然的 autocommit 行为上。正确做法是在第一条 edge/budget SQL 前要求 callable connection transaction，缺失时 fail fast。

已修复：

- `_pulse_repository_shared._transaction(conn)` 缺 callable `transaction` 时抛 `RuntimeError("pulse_repository_transaction_required")`。
- 删除 shared helper 的 `nullcontext` / `hasattr(conn, "transaction")` / raw `conn.transaction()` 兼容。
- 缺 `transaction` 或 `transaction = None` 的 fake connection 证明 `claim_pulse_admission(...)` 在任何 edge/budget SQL 前 fail fast。
- architecture guard 禁止 Pulse shared transaction helper 重新引入 `nullcontext`、`return nullcontext()`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()` fallback。

## 根因四十一：Macro observation series current refresh 缺事务时退化成无事务发布

继续扫描剩余 `nullcontext` 事务 helper 时发现，`MacroIntelRepository.refresh_observation_series_rows_for_concepts(...)` 在发现 changed concepts 后，会在一个 block 内删除退出的 `macro_observation_series_rows` current rows、插入/更新新的 current rows，并更新 `macro_observation_series_publication_state`；但 `_transaction_context(conn)` 在连接缺 `transaction` 时返回 `nullcontext()`。

这不是普通 repository convenience。`macro_observation_series_rows` 是 Macro API/module/series request path 直接读取的 current read model，`macro_observation_series_publication_state` 是投影当前性和 source signature 的控制状态。成熟 Kappa/CQRS 要求 current rows 与 publication state 原子发布：删旧、写新、标记 published 必须在同一 PostgreSQL 事务中完成。否则可能出现 current rows 已部分替换但 publication state 仍旧，或 publication state 标记 published 但 current rows 没完整落账，后续 `macro_view_snapshots` 和 `macro_daily_briefs` 会基于不一致的 projection frontier。

根因仍是旧 fake/旧 connection shape 兼容侵蚀了 read-model writer contract。`nullcontext()` 让测试可以不用实现真实 transaction 就覆盖 changed-refresh 路径，但代价是生产代码无法证明 current projection 发布是原子的。正确做法是在第一条 delete/insert/publication-state SQL 前要求 callable connection transaction，缺失时 fail fast。

已修复：

- `_transaction_context(conn)` 缺 callable `transaction` 时抛 `RuntimeError("macro_observation_series_refresh_transaction_required")`。
- 删除 Macro repository 的 `nullcontext` / `getattr(conn, "transaction", None)` 兼容分支。
- 缺 `transaction` 或 `transaction = None` 的 fake connection 证明 changed-refresh 在任何 delete/insert/publication-state SQL 前 fail fast。
- architecture guard 禁止 Macro observation series refresh 重新引入 `nullcontext`、`getattr(conn, "transaction", None)`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()` fallback。

## 根因四十二：Pulse job/run 普通状态写仍保留手动 commit 兼容分支

继续审计 Pulse job repository 时发现，Root39 只切掉了 terminal/dead + terminal ledger 路径；`enqueue_job(...)`、`mark_job_succeeded(...)`、`release_running_job_for_backpressure(...)`、`release_running_job_for_provider_cooldown(...)` 和 `mark_stale_agent_runs_failed(...)` 仍保留 `commit=True` 下的手动 `self.conn.commit()` 或 `getattr(self.conn, "transaction", None)` 探测分支。

这些路径虽然多数是单语句更新，但它们仍是 Pulse agent 控制面和审计账本：job enqueue 决定 agent work 入队，success/release 决定 running job 状态机，stale agent-run cleanup 终止 `pulse_agent_runs` 审计行。成熟 Kappa/CQRS 不是靠“单语句 autocommit 大概率安全”来定义 writer contract，而是要求 repository 拥有提交权时显式进入 PostgreSQL transaction；外层 worker/session 拥有事务时才用 `commit=False`。

根因是旧 repository API 的 `commit=True` 语义含混：有 transaction-capable connection 时不进入 transaction，缺 transaction 时反而手动 commit。这既保留了第二套提交语义，也让 fake connection 可以绕过正式 transaction contract。正确模型是 `commit=True -> connection transaction -> write`，`commit=False -> caller/session transaction already owns write`。

已修复：

- 新增 `_run_job_write(conn, commit, write)`，`commit=True` 时先进入 `_transaction(conn)`；缺 callable `transaction` 会在 SQL 前抛 `RuntimeError("pulse_jobs_repository_transaction_required")`。
- `enqueue_job(...)`、`mark_job_succeeded(...)`、两个 running-job release 路径和 `mark_stale_agent_runs_failed(...)` 删除手动 commit / `getattr(self.conn, "transaction", None)` 兼容。
- 缺 transaction 的 fake connection 证明这些 mutation 在任何 job/run SQL 前 fail fast。
- architecture guard 禁止 `PulseJobsRepository` 重新引入 `self.conn.commit()` 或 `getattr(self.conn, "transaction", None)`。

## 根因四十三：Pulse agent 写仓库仍残留 repository-owned manual commit 兼容

继续沿 Pulse agent 的 repository 层追踪后发现，Root42 只覆盖了 `PulseJobsRepository` 的 job/run 控制面 mutation；真正写 agent 审计和候选状态的多组 repository 仍有同一类旧语义：`commit=True` 时执行 SQL，然后调用 `self.conn.commit()`。

受影响路径包括 `PulseRunsRepository` 的 run/step ledger、`PulseAgentEvalRepository` 的 runtime version/eval case/result、`PulseEvidenceRepository` 的 evidence packet、`PulseCandidatesRepository` 的 candidate/public visibility mutation、`PulsePlaybooksRepository` 的 playbook snapshot/outcome，以及 `PulseAdmissionRepository` 的普通 edge/budget mutation 方法。

这些写入不是“普通表写入”。它们共同组成 Pulse agent 的可审计输出链：agent run 说明谁执行了任务，step/eval 说明模型和规则怎样决策，evidence packet 说明证据边界，candidate/playbook 决定 public serving 状态，admission edge/budget 决定后续是否允许继续生成。成熟 Kappa/CQRS 里，这些派生写入虽然是 read-model/control-plane 层，但仍必须有明确单 writer 和明确 PostgreSQL transaction 边界；不能让 repository 既支持 session transaction，又保留一条手动 commit 的第二提交语义。

根因仍是旧 `commit=True` 契约过宽：它把“repository 自己拥有提交权”误实现为“SQL 后手动 commit”，而不是“先进入 connection transaction 再写”。这会让缺少 transaction 的 fake/runtime connection 继续通过测试，也让未来维护者误以为这些写路径可以脱离外层 `RepositorySession.transaction` 单独落盘。

已修复：

- 新增共享 `_run_repository_write(conn, commit, write)`，统一 Pulse agent write repository 的 `commit=True -> connection transaction -> write` 语义；`commit=False` 明确留给外层 `RepositorySession.transaction`。
- `PulseRunsRepository`、`PulseAgentEvalRepository`、`PulseEvidenceRepository`、`PulseCandidatesRepository`、`PulsePlaybooksRepository` 和普通 `PulseAdmissionRepository` mutation 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明 run/step/eval/packet/candidate/playbook/edge/budget SQL 前会 fail fast。
- architecture guard 禁止 Pulse agent write repositories 重新引入 manual `self.conn.commit()` 或 optional connection-transaction fallback。

## 根因四十四：Pulse trigger dirty-target repository 仍保留 manual commit 兼容

继续收口 Pulse 控制面时发现，`PulseTriggerDirtyTargetRepository` 的 `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)`、`mark_error(...)` 和 `reschedule(...)` 仍在 `commit=True` 下先执行 `pulse_trigger_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条路径是 Pulse worker 的 bounded catch-up 队列，不是普通辅助表。enqueue 决定 Token Radar 变化是否进入 Pulse，claim 决定 worker 租约和 attempt，done/error/reschedule 决定同一 dirty target 后续是否被删除、重试或延迟。成熟 Kappa/CQRS 里，dirty queue 是控制面状态机，repository 拥有提交权时也必须先进入 PostgreSQL transaction；不能让 queue mutation 在缺 connection transaction 的 fake/runtime connection 上继续落 SQL。

根因仍是旧 `commit=True` 契约过宽：外层 `PulseCandidateWorker` 已经要求 `RepositorySession.transaction()`，但 repository 默认调用仍保留“SQL 后手动 commit”的第二提交语义。这样直接调用 repository、测试 fake 或未来维护代码会绕开正式 connection transaction，破坏 enqueue/claim/done/error/reschedule 的一致事务边界。

已修复：

- `PulseTriggerDirtyTargetRepository` 复用共享 `_run_repository_write(conn, commit, write)`，`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)`、`mark_error(...)` 和 `reschedule(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 dirty-target SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Pulse trigger dirty-target repository 重新引入 manual `self.conn.commit()` 或 optional connection-transaction fallback。

## 根因四十五：News projection dirty-target 普通 mutation 仍保留 manual commit 兼容

Root34 修掉了 `NewsProjectionDirtyTargetRepository.terminalize_targets(...)`
的 delete + terminal ledger 事务边界，但继续追踪普通队列状态机后发现，
`enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和
`mark_error(...)` 仍在 `commit=True` 下先执行
`news_projection_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条路径和 terminalize 一样不是普通辅助写入。enqueue 决定哪些 News item
或 source-window 进入投影，claim 决定 lease_owner / leased_until，done 决定
queue row 是否删除，error 决定 retry due_at 和 attempt 语义。成熟 Kappa/CQRS
里，dirty queue 是投影控制面状态机；repository 拥有提交权时应先进入
connection transaction，再执行 queue SQL。否则缺 transaction 的 fake/runtime
connection 仍可执行 `FOR UPDATE SKIP LOCKED` claim 或 delete/update 队列状态，
相当于保留了一条绕过正式 session transaction 的第二提交语义。

根因仍是旧 `commit=True` 契约过宽：外层 News projection workers 已经要求
`RepositorySession.transaction()`，但 repository 默认调用还保留“SQL 后手动
commit”的兼容入口。这样直接调用 repository、测试 fake 或未来维护代码可以
绕开正式 connection transaction，导致 enqueue/claim/done/error 的事务边界
和 terminalize 路径不一致。

已修复：

- `NewsProjectionDirtyTargetRepository` 新增 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `news_projection_dirty_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 News projection dirty-target repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因四十六：Token Radar source dirty event queue 仍保留 manual commit 兼容

继续沿 Token Radar 增量投影链路追踪后发现，Root14 只切掉了
`token_radar_source_dirty_events` repository 缺失时的 optional fallback；
真正的 source-edge dirty queue repository 仍保留同一类旧提交语义：
`enqueue_events(...)`、`claim_due(...)`、`mark_done(...)` 和
`mark_error(...)` 在 `commit=True` 下先执行
`token_radar_source_dirty_events` SQL，再调用 `self.conn.commit()`。

这条队列是 Token Radar 从 ingest/reprocess 到 projection 的正式增量输入。
enqueue 决定 resolved source-event edge 是否进入投影，claim 决定 worker lease
和 attempt，done/error 决定同一 source edge 是否删除或重试。成熟 Kappa/CQRS
里，source dirty queue 是投影控制面状态机：它不是 business truth，但它决定
哪些事实会被当前 read model 消费。repository 拥有提交权时必须先进入
connection transaction，再执行 enqueue/claim/delete/retry SQL。

根因仍是旧 `commit=True` 契约过宽：我们已经要求 Token Radar projection
worker 使用正式 repository contract，但 repository 默认调用还允许“SQL 后手动
commit”的第二提交语义。这样测试 fake 或未来维护代码可以在缺 connection
transaction 时绕过正式事务边界，尤其会让 `FOR UPDATE SKIP LOCKED` claim
和后续 done/error 状态转换看似可在无事务/自动提交语义下运行。

已修复：

- `TokenRadarSourceDirtyEventRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_events(...)`、`claim_due(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `token_radar_source_dirty_events` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Token Radar source dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因四十七：Token Radar target dirty queue 仍保留 manual commit 兼容

继续沿 Token Radar 主投影目标队列追踪后发现，Root46 只切掉了
source-edge dirty queue 的手动提交兼容；`TokenRadarDirtyTargetRepository`
仍保留同一类旧提交语义。`enqueue_targets(...)`、
`enqueue_market_targets(...)`、`claim_due(...)`、
`enqueue_recent_resolved_targets(...)`、`enqueue_market_current_targets(...)`、
`mark_done(...)` 和 `mark_error(...)` 在 `commit=True` 下先执行
`token_radar_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 Token Radar 当前 leaderboard 投影的目标级控制面：source dirty
edge、market current 变更、显式 repair 和 bounded catch-up 最终都落到这里。
enqueue 决定哪些目标进入投影，claim 决定 worker lease 和 attempt，done/error
决定同一目标是否删除或重试。成熟 Kappa/CQRS 里，target dirty queue 不是
business truth，但它是 read model 增量消费边界；repository 拥有提交权时
必须先进入 connection transaction，再执行 enqueue/claim/delete/retry SQL。

根因仍是旧 `commit=True` 契约过宽：外层 TokenRadarProjectionWorker 已经
通过正式 repository session 管理投影生命周期，但 repository 默认调用还允许
“SQL 后手动 commit”的第二提交语义。这样测试 fake 或未来维护代码可以在缺
connection transaction 时执行 `FOR UPDATE SKIP LOCKED` claim、market dirty
coalescing、catch-up enqueue 或 done/error 状态转换，掩盖真实 runtime/session
contract 缺失。

已修复：

- `TokenRadarDirtyTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`enqueue_market_targets(...)`、`claim_due(...)`、`enqueue_recent_resolved_targets(...)`、`enqueue_market_current_targets(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `token_radar_dirty_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Token Radar target dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因四十八：Market tick current dirty queue 仍保留 manual commit 兼容

继续沿 Asset Market 到 Token Radar 的市场链路往前追踪后发现，
`MarketTickCurrentDirtyTargetRepository` 仍保留同一类旧提交语义。
`enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和
`mark_error(...)` 在 `commit=True` 下先执行
`market_tick_current_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 append-only `market_ticks` 到 current read model
`market_tick_current` 的控制面。market tick writers 写事实后只发
`market_tick_written` wake hint；`MarketTickCurrentProjectionWorker`
必须靠这条 durable dirty queue 和 bounded `interval_seconds` catch-up
重建最新 current row，然后只在 visible current row 变化时 enqueue
`token_radar_dirty_targets`。如果 repository 拥有提交权时仍允许
“SQL 后手动 commit”，缺 connection transaction 的 fake/runtime connection
就可以执行 `FOR UPDATE SKIP LOCKED` claim、done delete 或 retry update，
相当于在 projection 控制面保留第二套事务边界。

根因仍是旧 `commit=True` 契约过宽：worker 处理 claim 结果时已经使用
`worker_transaction`，但 `_claim_due(...)` 默认仍直接调用 repository
自提交路径。成熟 Kappa/CQRS 中，dirty queue 不是 business truth，
但它决定事实变更进入哪个 current read model；enqueue/claim/done/error
必须先进入 PostgreSQL transaction，再执行队列 SQL。

已修复：

- `MarketTickCurrentDirtyTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `market_tick_current_dirty_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Market Tick Current dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因四十九：Token profile current dirty queue 仍保留 manual commit 兼容

沿 Asset Market 的 profile/icon read model 链路继续追踪后发现，
`TokenProfileCurrentDirtyTargetRepository` 也保留同一类旧提交语义。
`enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和
`mark_error(...)` 在 `commit=True` 下先执行
`token_profile_current_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 provider profile source cache、local image mirror 生命周期和
public `token_profile_current` read model 之间的增量控制面。
`TokenProfileCurrentWorker` 已经要求先 claim dirty targets，再通过
`RepositorySession.source_query` exact-load persisted GMGN OpenAPI、Binance
Web3、GMGN stream、OKX DEX、CEX profile 和本地 image state，然后只在
`token_profile_current` payload 变化时写 serving row。dirty queue 本身不是
business truth，但它决定哪些 profile/icon 事实进入当前读模型；如果 repository
拥有提交权时仍允许“SQL 后手动 commit”，缺 connection transaction 的
fake/runtime connection 就可以执行 `FOR UPDATE SKIP LOCKED` claim、done
delete 或 retry update，绕过正式 PostgreSQL 事务边界。

根因仍是旧 `commit=True` 契约过宽：worker 内部的 projection/done/error
阶段已经使用 `repos.transaction()`，但 dirty repository 对外默认路径仍允许
第二套手动提交语义。成熟 Kappa/CQRS 中，控制面队列状态必须与 claim lease、
attempt、payload_hash stale-completion token 和 retry state 一起纳入明确事务；
否则 queue correctness 依赖连接对象“有没有 commit 方法”这种兼容偶然性。

已修复：

- `TokenProfileCurrentDirtyTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `token_profile_current_dirty_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Token Profile Current dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因五十：Token image source dirty queue 仍保留 manual commit 兼容

沿 profile/icon 链路继续往上游追踪，`TokenImageSourceDirtyTargetRepository`
也保留同一类旧提交语义。`enqueue_targets(...)`、`claim_due(...)`、
`mark_done(...)` 和 `mark_error(...)` 在 `commit=True` 下先执行
`token_image_source_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 provider logo URL 到本地 `token_image_assets` 镜像状态的控制面。
`TokenImageMirrorWorker` 只读取 due `token_image_source_dirty_targets`，不扫描
source 表；镜像完成后再 enqueue `token_profile_current_dirty_targets`，让 public
`token_profile_current` 重新选择 ready local logo。也就是说，这条 queue 不代表
业务事实本身，但它决定哪些 provider URL 被 durable mirror、哪些 profile current
row 被唤醒重投影。若 repository 拥有提交权时还允许“SQL 后手动 commit”，缺
connection transaction 的连接仍可执行 `FOR UPDATE SKIP LOCKED` claim、
done delete 或 retry update，给 image mirror 控制面留下第二套事务边界。

根因仍是旧 `commit=True` 契约过宽：worker 的 terminal/pending/mirror 结果写入
已经把 mark_done/mark_error 放进 `repos.transaction()`，但 repository 对外默认
写路径仍兼容无 transaction 连接。成熟 Kappa/CQRS 中，local media mirror 是可重建
派生状态；其 dirty source queue 的 lease、attempt、payload_hash stale-completion
token 和 retry 状态必须由 PostgreSQL transaction 保护，不能靠连接对象的
manual `commit()` 方法兜底。

已修复：

- `TokenImageSourceDirtyTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`mark_done(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `token_image_source_dirty_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Token Image Source dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因五十一：Asset profile refresh target queue 仍保留 manual commit 兼容

沿 profile source cache 链路继续上游追踪，`AssetProfileRefreshTargetRepository`
同样保留旧提交语义。`enqueue_targets(...)`、`claim_due(...)`、
`reschedule(...)` 和 `mark_error(...)` 在 `commit=True` 下先执行
`asset_profile_refresh_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 provider-scoped DEX profile refresh 的控制面：worker 先 claim
`asset_profile_refresh_targets`，再调用 DEX profile source，写入 provider source
cache `asset_profiles`，随后唤醒 `token_profile_current_dirty_targets`。成熟
Kappa/CQRS 中，provider profile source cache 是 material/source fact cache，
public profile current 是 rebuildable read model；两者之间的 refresh queue
必须只表达“哪些 source cache 需要刷新”，不能保留第二套 transaction contract。

根因仍是旧 `commit=True` 契约过宽：worker 内部的 provider result 写入和
reschedule 已经使用 `repos.transaction()`，但 repository 对外默认路径仍允许
无 connection transaction 的连接先 claim/lease/reschedule queue row，再手动
commit。这样会让 `FOR UPDATE SKIP LOCKED`、lease、attempt_count、payload_hash
stale-completion token 和 retry state 处在统一 worker session 之外，削弱
PostgreSQL 队列的可预测性。

已修复：

- `AssetProfileRefreshTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_targets(...)`、`claim_due(...)`、`reschedule(...)` 和 `mark_error(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `asset_profile_refresh_targets` SQL 前 fail fast；空输入仍保持无 SQL 快速返回。
- architecture guard 禁止 Asset Profile Refresh target repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因五十二：Token capture tier dirty queue 仍保留 manual commit 兼容

最后一条 Asset Market dirty queue 扫描命中
`TokenCaptureTierDirtyTargetRepository`。`enqueue_rank_set(...)`、
`claim_due(...)` 和 `mark_done(...)` 在 `commit=True` 下先执行
`token_capture_tier_dirty_targets` SQL，再调用 `self.conn.commit()`。

这条队列是 Token Radar current rows 到 `token_capture_tier` rebuildable
control projection 的增量控制面。`TokenCaptureTierWorker` 已经被修成
claim、tier upsert/demotion 和 done state 共享 `RepositorySession.transaction`；
但 repository 自己的默认写路径仍保留旧 manual commit contract，会让 rank-set
dirty enqueue、claim lease、attempt_count 和 stale-completion token 脱离正式
connection transaction。

根因是 worker 层已经硬切，仓储层没有同步硬切。成熟 Kappa/CQRS 中，capture
tier 本身不是 market fact，而是可重建的 live-capture control read model；它的
dirty queue 也只是控制面，不能保留第二套“有 commit 方法就能写”的兼容入口。

已修复：

- `TokenCaptureTierDirtyTargetRepository` 增加本地 `_run_repository_write(conn, commit, write)`；`commit=True` 时先进入 connection transaction，`commit=False` 留给外层 session transaction。
- `enqueue_rank_set(...)`、`claim_due(...)` 和 `mark_done(...)` 删除 `self.conn.commit()` 手动提交兼容。
- 缺 transaction 的 fake connection 证明这些 queue mutation 在任何 `token_capture_tier_dirty_targets` SQL 前 fail fast；空输入 `mark_done([])` 仍保持无 SQL 快速返回。
- architecture guard 禁止 Token Capture Tier dirty repository 重新引入 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

## 根因五十三：Token Radar rank publication transaction helper 仍保留 optional probe 形状

`TokenRadarProjection.refresh_rank_set(...)` 已经把 stale-running cleanup、
projection offset advance、`token_radar_current_rows` publication 和 publication
run finish 包进 `_transaction_context(self.repos.conn)`。但 helper 本身仍使用
`getattr(conn, "transaction", None)`；缺失 transaction 会抛出 contract error，
non-callable transaction 却会继续到 `transaction()` 并抛 `TypeError`。这不是
manual commit fallback，但仍是旧兼容探测形状：错误边界不稳定，architecture guard
也无法证明 publish 写入前一定先校验正式 connection transaction contract。

成熟 Kappa/CQRS 中，Token Radar current rows 是核心 serving read model，
publication state 和 offset/run state 必须共享同一 PostgreSQL transaction。helper
应该只接受实现了 callable `transaction()` 的正式连接；缺失或形状错误都是 session
contract failure，而不是靠 Python 调用错误暴露。

已修复：

- `_transaction_context(conn)` 改为直接读取 `conn.transaction`，缺失或 non-callable 都抛 `token_radar_projection_requires_transactional_connection`。
- unit guard 证明 non-callable transaction 在 `publish_current_generation(...)` 前 fail fast，不写 current rows，也不 advance offset / finish run。
- architecture guard 禁止 Token Radar projection 重新引入 `getattr(conn, "transaction", None)`、`return nullcontext()` 或 `if transaction is None:` 的 optional probe 形状。

## 根因五十四：Event Anchor repository transaction helper 仍保留 optional probe 形状

Root39 已经把 Event Anchor terminal path 从 `nullcontext` fallback 拉回
connection transaction contract：`expire_stale(...)` 和 `mark_terminal(...)`
都必须进入 `_transaction(self._conn)`，缺 transaction 会在 SQL 前抛
`event_anchor_repository_transaction_required`。继续做全局 transaction-probe
扫描时发现，helper 虽然已经 fail closed，但实现仍是
`getattr(conn, "transaction", None)`。

这类形状的问题不是当前会漏写 SQL，而是它保留了“transaction 是可选属性”的阅读
语义。成熟 Kappa/CQRS 的 terminal state 写入要把 job terminal update 与
`worker_queue_terminal_events` ledger 写入绑定在同一个 PostgreSQL transaction 中；
helper 应该直接要求正式 connection contract，而不是用 optional probe 的写法再判断。

已修复：

- `_transaction(conn)` 改为直接读取 `conn.transaction`；缺失和 non-callable 都抛 `event_anchor_repository_transaction_required`。
- unit guard 证明 non-callable transaction 在 `mark_terminal(...)` 更新 job state 或写 terminal ledger 前 fail fast，`conn.sql` 为空。
- architecture guard 禁止 Event Anchor repository 重新引入 `getattr(conn, "transaction", None)`、`return nullcontext()`、`if callable(transaction):` 或 `if transaction is None:`。
- 全局源码扫描确认 `getattr(conn, "transaction", None)` / `return nullcontext()` / `if transaction is None:` 连接事务 optional-probe 形状已经清空。

## 根因五十五：WakeBus / WakeWaiter 把 PostgreSQL wake 事务接口当成可选能力

继续做 runtime 兼容性扫描时发现，`WakeBus._commit(conn)` 通过
`getattr(conn, "commit", None)` 探测提交方法，缺失时直接不提交；`WakeWaiter`
注册 `LISTEN` 后也用同样的 optional commit，并且缺少 `conn.notifies` 时退回
本地 `Event.wait(...)`。

这条链路看起来只是“hint”，但 PostgreSQL 的 `NOTIFY` 只有在事务提交后才会投递，
`LISTEN` 注册也依赖明确的连接语义。成熟 Kappa/CQRS 中，wake 确实不是事实来源，
worker 必须重新读 DB 并按 interval catch-up；但 wake hint 仍是降低延迟的正式 runtime
契约，不能把 malformed wake-pool connection 伪装成成功 no-op 或本地等待。否则测试 fake
和运行时连接形状漂移会被吞掉，表现为 worker 偶发靠 interval 追平，根因却不暴露。

已修复：

- `WakeBus` 发出 `pg_notify` 后直接要求 callable `conn.commit`，缺失或 non-callable 抛 `wake_bus_commit_required`。
- `WakeWaiter` 在 `LISTEN` 后直接要求 callable `conn.commit`，随后要求 callable `conn.notifies`；形状错误抛 `wake_waiter_commit_required` 或 `wake_waiter_notifies_required`，不再被普通 reconnect loop 吞掉。
- transient LISTEN 失败仍走原来的 reconnect 路径；只有 wake-pool connection contract 错误 fail closed。
- unit / architecture guard 禁止重新引入 `getattr(conn, "commit", None)` 或 missing-`notifies` local-wait fallback。

## 根因五十六：ResolutionRefreshWorker 仍在业务边界手动提交 worker session

Root1 已经把 `resolution_refresh` 拉回 dirty lookup queue consumer：claim
`token_discovery_dirty_lookup_keys`，provider IO 离开 DB session，随后重新进入
session 持久化。但继续做 transaction/commit 残留扫描时发现，worker 的
`start_lookup`、provider result persist + `finish_lookup`、`fail_lookup`、
claim completion/reschedule/terminalize 仍由 runtime 代码直接调用
`repos.conn.commit()`。

这类写法把事务边界从 `RepositorySession` contract 泄漏到 worker 业务代码里。
成熟 Kappa/CQRS 中，lookup claim 的 running/finished/error/terminal state 是控制
面状态机，必须由一个明确的 Unit of Work / session transaction 包住；worker 可以把
provider 网络调用放在事务外，但不能在每个业务分支上手工拼 commit。否则测试 fake
只要提供 `conn.commit` 就能绕过正式 session contract，后续代码很容易再次出现
claim state、result rows 和 terminal/retry ledger 半提交。

已修复：

- `ResolutionRefreshWorker` 新增 `_session_transaction(repos)`，直接要求
  `repos.transaction`，缺失或 non-callable 都抛
  `resolution_refresh_session_transaction_required`。
- `start_lookup` 在 provider IO 前的 running claim 标记进入
  `RepositorySession.transaction`；provider IO 仍在事务外，避免持有 DB transaction
  等网络。
- provider result persist + `finish_lookup`、error `fail_lookup` + retry/terminalize、
  `_finish_lookup_claims` 的 done/reschedule/terminalize 都进入 session transaction，
  不再调用 `repos.conn.commit()`。
- unit / architecture guard 禁止重新引入 `repos.conn.commit()`、raw
  `repos.conn.transaction()`、optional transaction probing 或 `_commit_if_supported`
  形状。

## 根因五十七：NotificationDeliveryWorker 仍把 delivery 状态机提交拆在 worker 和 repository 两层

继续扫描 notification 链路时发现，`notification_rule` 已经要求
worker-session `unit_of_work`，但实际发送侧 `NotificationDeliveryWorker` 仍在
claim 结束分支直接调用 `repos.notifications.conn.commit()`；同时
`NotificationRepository.complete_delivery(...)` 和 `fail_delivery(...)` 在 repository
内部无条件 `self.conn.commit()`。这使 delivery claim、pre-flight fail、log-provider
complete、外部推送后的 complete/fail 这些状态机写入没有统一的 session transaction
边界。

成熟 Kappa/CQRS 中，delivery row 是 side-effect/control ledger：它记录已 claim、
已发送、失败重试、dead 等控制事实，而外部 Apprise/PushDeer IO 只是副作用。正确边界
应该是：claim 与本地 pre-flight 状态转换在 DB transaction 内完成；外部 provider IO
不持有 DB transaction；IO 后的 delivered/failed terminal transition 再进入新的
session transaction。旧实现把 commit 散在 worker 和 repository 里，测试 fake 只要
暴露 `conn.commit` 就能绕过 `RepositorySession.transaction`，也容易在失败分支出现
半提交或不可审计的状态机边界。

已修复：

- `NotificationDeliveryWorker` 的 claim/pre-flight 分支、外部 IO 成功后的
  complete、外部 IO 异常后的 fail 都直接要求 `repos.transaction()`。
- `claim_next_delivery`、`complete_delivery`、`fail_delivery` 支持明确的
  `commit=False`，worker 路径由 session transaction 提交；repository 自己拥有提交权
  时则进入 `_run_delivery_write(...)` 的 connection transaction。
- Apprise/PushDeer 外部 IO 仍在 DB transaction 之外执行，避免网络等待期间持有行锁或
  session transaction。
- unit / architecture guard 禁止重新引入 worker 里的 `.conn.commit()`、
  `nullcontext`、optional transaction probing，并证明 missing session transaction
  会在 claim 前失败。

## 根因五十八：Token intent rebuild/reprocess 仍把事实重建提交权放在 raw conn 上

继续沿 token_intel 事实重建链路扫描后发现，`rebuild_recent_token_intents(...)`
和 `reprocess_recent_token_intents(...)` 仍在 runtime/service 层直接调用
`repos.conn.commit()`。这些路径会重写或追加 `token_evidence`、`token_intents`、
`token_intent_lookup_keys`、`token_intent_resolutions`、`asset_identity_evidence/current`、
`token_discovery_dirty_lookup_keys` 和 `token_radar_source_dirty_events`。它们不是普通
ops 脚本写法，而是事实层和投影控制面的重建入口。

成熟 Kappa/CQRS 中，rebuild/reprocess 只是重新消费 PostgreSQL material facts 的
一种命令入口；它仍必须遵守和在线 ingest/reprocess 一样的 Unit of Work 边界。旧实现
把“我有一个 `repos.conn` 可以 commit”当成成功条件，让测试 fake 不必实现正式
`RepositorySession.transaction`，也让多张事实表与 source-dirty 控制行的原子关系无法
被架构测试证明。一旦中途失败，最坏情况是 intent/resolution 已更新但 lookup/source-dirty
没有同步，后续 Token Radar 增量投影会漏消费或重复消费。

已修复：

- `rebuild_recent_token_intents(...)` 和 `rebuild_event_token_intents(...)` 的公开入口
  直接进入 `repos.transaction()`；内部 `_rebuild_event_token_intents(...)` 要求
  `repos.require_transaction(operation="token_intent_rebuild")`。
- `reprocess_recent_token_intents(...)` 进入 `repos.transaction()`；内部
  `_reprocess_recent_token_intents(...)` 要求
  `repos.require_transaction(operation="token_resolution_refresh")`。
- 删除 `rebuild_event_token_intents(..., commit=...)` 兼容参数和两处
  `repos.conn.commit()` 手动提交。
- unit / architecture guard 证明缺 session transaction 会在 lookup/rebuild 写入前
  失败，并禁止重新引入 direct commit、raw connection transaction probing 或
  `commit: bool` 兼容形状。

## 根因五十九：Macro view projection 把一次 read-model 发布拆成多段提交

继续沿 Macro read-model writer 扫描后发现，`MacroViewProjectionWorker` 在
`run_once_sync(...)` 中先用 `commit=True` claim `macro_projection_dirty_targets`，
再调用 observation-series refresh、写 `macro_view_snapshots`，最后又用
`commit=True` mark done/error。也就是说，一个逻辑上的 macro current projection
发布，被拆成 dirty-target claim、series current rows、snapshot row、dirty-target
terminal state 多个提交片段。

这违背了 Macro 域自己的 Kappa/CQRS contract：`macro_observation_series_rows`、
`macro_observation_series_publication_state` 和 `macro_view_snapshots` 是同一个
current read-model frontier。成熟实现里，claim 之后的投影发布应当是一个
RepositorySession Unit of Work；失败时不能留下半个 snapshot 或半套 current rows；
成功后才允许发 `macro_view_snapshot_updated`，而 wake 仍只是提示，不能先于提交让
下游 daily brief 读到未提交或部分提交状态。

根因不是某个 SQL 写慢，而是提交权分散：worker、repository、wake 三层都能“各自完成”
一段动作，测试 fake 也因此不需要表达正式 session transaction。这个形状在低并发下不
一定立刻坏，但在超时、异常、下游 wake、或多 worker 竞争时会制造不可重放的中间态。

已修复：

- `MacroViewProjectionWorker.run_once_sync(...)` 在 claim 前进入
  `repos.transaction()`，dirty-target claim 使用 `commit=False`。
- 成功路径在同一个 session transaction 内完成 observation-series refresh、
  snapshot insert 和 dirty-target done；内部 helper 调用
  `repos.require_transaction(operation="macro_view_projection")`。
- 失败路径用内层 savepoint 回滚 partial projection writes，再在外层 transaction 中
  mark dirty-target error，避免把半成品 read model 和 error state 一起提交。
- `macro_view_snapshot_updated` wake payload 从 `_run_claimed_once(...)` 带出，
  在 transaction block 退出之后发送；unchanged snapshot 不发 wake。
- unit / architecture guard 禁止 worker 恢复 `commit=True`、manual commit、
  optional transaction probing，并证明缺 `RepositorySession.transaction` 时 claim 前失败。

## PostgreSQL 最佳实践对照

本轮修复对齐的 PostgreSQL 原则：

- claim/cleanup 使用 bounded batch。
- 并发 worker 使用 `FOR UPDATE SKIP LOCKED`。
- stale-running cleanup 使用 partial index 对准谓词。
- public read path 避免 JSONB set-returning function 展开。
- read-model service 不暴露 upsert/insert/commit 写入口。
- public read path 通过 read service 读 account-quality，而不是直接构造 repository。
- public product health 不混入 process-local worker liveness。
- diagnostics read surface 不从 runtime provider object 推导静态 provider capability contract。
- item-process admission context 来自 PostgreSQL repository readback，不用 worker 内存对象兼容缺字段 context。
- News fetch dirty targets 来自 PostgreSQL repository affected set，不用当前 item id 兼容缺失 affected set。
- News projection dirty enqueue 必须经过 PostgreSQL servable filter，不在 helper 中兼容缺失 repository contract。
- Token Radar source-edge dirty queue 是正式 PostgreSQL 增量投影 contract，不用缺 repository 兼容路径把事实变更当成空队列。
- Notification failed/dead external delivery reactivation 是正式 PostgreSQL 控制面状态转换，不用 insert-only enqueue 兼容缺失 requeue contract。
- Notification fact 写入和 external delivery 控制行写入必须共享 worker-session `unit_of_work`，缺 UoW 不被兼容成 `nullcontext` 或手动 repository commit。
- Pulse public visibility transition 是正式 read-model 写 contract，低信息隐藏缺 repository support 时 fail/retry，不把 stale public row 当成已处理。
- Pulse dirty-trigger admission/capacity/edge-state 读取正式 PostgreSQL 控制面契约；缺 job/edge/count/queue-depth repository method 不被兼容成无 job、无 edge、失败数为 0 或空队列。
- Macro `assets_today` daily brief 是正式 PostgreSQL read-model 读契约，缺 repository method 不被 public route 兼容成空 brief。
- Macro CEX board 是正式 PostgreSQL read-model 读契约，缺 `cex_oi_radar` repository 不被 public route 兼容成无 board。
- Token Case / Search Inspect 的 CEX detail 是正式 PostgreSQL read-model 读契约，缺 `cex_detail_snapshots.latest_snapshot` repository method 不被兼容成无 detail。
- Token Case / Search Inspect 的 market-live 是正式 PostgreSQL current tick 读契约，缺 `latest_market_tick` repository method 不被兼容成 `market_live.status="missing"`。
- Token profile current 的 source exact-load 是正式 PostgreSQL session query contract，缺 `source_query` 不被 worker 兼容成临时自建 query。
- Macrodata bundle import 的 fact/import-run/dirty-target 写入必须共享 `RepositorySession.unit_of_work` 和 `require_transaction`；缺 session UoW 或 transaction guard 不被兼容成 raw `conn.transaction()` fallback。
- Macro observation series current refresh 的 current-row delete/insert 与 publication state update 必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext`。
- PulseCandidateJobService 的 agent run/step/eval/candidate/playbook/admission/job terminal 写入必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 `nullcontext` 或 raw `conn.transaction()`。
- PulseJobsRepository 的 `pulse_agent_jobs` terminal/dead state 和 `worker_queue_terminal_events` terminal ledger 写入必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext` 或 manual `commit()`。
- PulseJobsRepository 的 job enqueue、success marking、running-job release 和 stale `pulse_agent_runs` cleanup 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- Pulse agent write repositories 的 run/step/eval/packet/candidate/playbook/ordinary admission mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- PulseTriggerDirtyTargetRepository 的 enqueue/claim/done/error/reschedule mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- PulseAdmissionRepository 的 edge observation、suppression/admission state、target/candidate budget lock 与 increment 必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext`。
- News page/source-quality 投影的 claim、read-model write、dirty enqueue、mark done/error 必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 `nullcontext` 或 raw `conn.transaction()`。
- PulseCandidateWorker 的 dirty-trigger claim、admission/edge/public visibility/job enqueue、mark done/error 必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 raw `conn.transaction()`。
- News fetch/process/brief runtime 写 worker 的事实写、agent admission/brief ledger 写、projection dirty enqueue、claim/failure state 必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 raw `conn.transaction()`。
- EventAnchorBackfillWorker 的 stale cleanup 必须共享 worker-session `unit_of_work`，`event_anchor_backfill_jobs` terminalization 与 `enriched_events` terminal lifecycle 写入不能被兼容成 manual `commit()`。
- EventAnchorBackfillJobRepository 的 terminal paths 必须要求 connection transaction，`event_anchor_backfill_jobs` 与 `worker_queue_terminal_events` terminal ledger 写入不能被兼容成 `nullcontext`。
- Queue Terminal operator resolve 的 `SELECT ... FOR UPDATE`、operator action update 和 retry transition 必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext` 或 manual `commit()`。
- DiscoveryRepository 的 `token_discovery_dirty_lookup_keys` claimed-row delete 和 `worker_queue_terminal_events` terminal ledger 写入必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext` 或 manual `commit()`。
- NewsProjectionDirtyTargetRepository 的 `news_projection_dirty_targets` claimed-row delete 和 `worker_queue_terminal_events` terminal ledger 写入必须共享 connection transaction；缺 transaction 不被兼容成 `nullcontext` 或 manual `commit()`。
- NewsProjectionDirtyTargetRepository 的 enqueue/claim/done/error 普通队列 mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- TokenRadarSourceDirtyEventRepository 的 enqueue/claim/done/error source-edge queue mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- WakeBus / WakeWaiter 的 `NOTIFY` / `LISTEN` 连接必须具备 callable `commit`，listener 还必须具备 callable `notifies`；缺连接契约不被兼容成 no-op 或本地等待。
- ResolutionRefreshWorker 的 lookup running/finish/fail/claim completion 状态转换必须共享 `RepositorySession.transaction`；provider IO 保持在事务外，缺 session transaction 不被兼容成手动 `repos.conn.commit()`。
- NotificationDeliveryWorker 的 delivery claim、pre-flight fail、log complete、外部 IO 后 complete/fail 状态转换必须共享 `RepositorySession.transaction`；Apprise/PushDeer IO 保持在事务外，缺 session transaction 不被兼容成 worker/repository 手动 commit。
- Token intent rebuild/reprocess 的 token facts、lookup keys、resolution rows、discovery dirty lookup 和 Token Radar source-dirty 写入必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 direct `repos.conn.commit()`。
- Macro view projection 的 dirty-target claim、observation-series current refresh、current snapshot upsert 和 dirty-target done/error 必须由 `RepositorySession.transaction` 管理；`macro_view_snapshot_updated` 只能在事务退出后作为 wake hint 发送。
- TokenRadarDirtyTargetRepository 的 target enqueue、market enqueue、claim、recent-resolved catch-up enqueue、market-current enqueue、done/error mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- TokenProfileCurrentDirtyTargetRepository 的 enqueue/claim/done/error profile-current queue mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- TokenImageSourceDirtyTargetRepository 的 enqueue/claim/done/error image-source queue mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- AssetProfileRefreshTargetRepository 的 enqueue/claim/reschedule/error provider-profile refresh queue mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- TokenCaptureTierDirtyTargetRepository 的 rank-set enqueue/claim/done mutation 在 repository 拥有提交权时必须进入 connection transaction；缺 transaction 不被兼容成 manual `commit()`。
- Token Radar rank publication 的 current rows、publication state、offset advance 和 run finish 必须共享 connection transaction；缺失或 non-callable transaction 都是正式 contract failure，不保留 optional probe 形状。
- Event Anchor terminal job update 与 terminal ledger 写入必须共享 connection transaction；缺失或 non-callable transaction 都是正式 contract failure，不保留 optional probe 形状。
- Ops projection dirty repair 的 execute 模式写 `news_projection_dirty_targets` 前必须要求 connection transaction；dry-run 只读统计可以无事务，但 execute 不能兼容成 `nullcontext`。
- TokenCaptureTierWorker 的 dirty target claim、tier row write/demotion 和 dirty target done state 必须共享 `RepositorySession.transaction`；缺 session transaction 不被兼容成 claim-before-transaction 或 manual `commit()`。
- projection hot path 避免历史 retention delete。
- unchanged read model publication 继续依赖 payload hash / `IS DISTINCT FROM` 语义，避免无变化时写 serving rows。

仍需后续验证的部分：

- 没有连接 operator-owned production-sized PostgreSQL。
- 没有跑 `EXPLAIN (ANALYZE, BUFFERS)`。
- 没有检查 `pg_stat_statements`、表膨胀、autovacuum、真实 queue cardinality。

因此 SQL 性能结论是代码/模式层面的风险治理，不是生产负载上的最终性能证明。

## 停止集成测试后的补充静态扫描

按用户要求，后续不再运行 integration suite。为避免验证证据断层，额外做了窄口径源码扫描：

- 直接从 `WorkerManifest v1` 导出 worker 矩阵，确认当前 worker inventory 以 manifest 为准；补齐 `resolution_refresh` 的 provider IO 标识。
- Stocks quote 旧 provider 标识在生产代码中不再出现；唯一保留的是 `quote_read_model_unavailable` 响应状态。
- `run_resolution_refresh_once` 和旧 `_process_*` helper 只出现在架构测试的禁止名单中，生产 worker 已无第二入口。
- `pulse_read_repository.py` 不再引用 `candidate.source_event_ids_json`、`candidate.evidence_event_ids_json` 或 `jsonb_array_elements_text`。
- `account_quality/read_models/account_quality_service.py` 不再包含 `backfill_`、`upsert_`、`insert_quality_snapshot` 或直接 commit；写路径迁移到 `services/account_quality_backfill_service.py` 并只由 ops 调用。
- `routes_events.py`、`routes_notifications.py`、CLI read-model command 不再直接 import `AccountQualityRepository`，统一通过 `AccountQualityService.from_conn(...)`。
- `account_quality/interfaces.py` 不再导出 `AccountQualityRepository` 或 `AccountQualityBackfillService`。
- API/read-model provider/network 扫描没有发现新的 request-time provider IO；命中项主要是 provider metadata 字段、WebSocket 类型、schema 字段和 DB payload 字段。
- 已新增 architecture guard：后端 public read path（API/read_models/queries）不得导入 `httpx`、`requests`、`aiohttp` 等网络客户端库。
- 已新增 architecture guard：后端 public read path（API/read_models/queries）不得导入 `parallax.integrations`、`provider_wiring`、`wire_providers` 或访问 `runtime.providers`。
- 已新增 architecture guard：Macrodata quote runtime lane 的旧文件、runtime 字段、config alias 和 provider export 不得恢复。
- 已新增 architecture guard：notification claim 的 stale-running terminalization 必须保持 bounded CTE、`LIMIT` 和 `FOR UPDATE SKIP LOCKED`。
- 已新增 architecture guard：notification worker 必须使用 worker-session `unit_of_work`，不得恢复 `nullcontext`、optional UoW 或手动 commit fallback。
- 已新增 architecture guard：Token Radar `refresh_rank_set` 不得重新调用 retention prune，也不得恢复 `pruned_*` publish counters。
- 已新增 architecture guard：Pulse read repository 不得重新引入 `jsonb_array_elements_text`、candidate event-id JSONB expansion 或 event author join。
- 已新增 architecture guard：domain read-model modules 不得重新引入 backfill/repair/upsert/insert/commit 写路径。
- 已新增 architecture guard：account-quality public read paths 不得直接 import repository 或绕过读服务。
- 已新增 architecture guard：account-quality cross-domain interface 不得导出 repository 或 backfill 写侧服务。
- 已新增 architecture guard：account-quality domain architecture 必须声明 read/write 边界和 ops-only maintenance writer。
- 已新增 architecture guard：全局架构不得把退役 Narrative LLM lane 描述成当前 runtime 职责。
- 已新增 architecture guard：Narrative 产品读路径不得重新暴露 retired semantic backlog/currentness coupling。
- 已新增 architecture/contract guard：Signal Pulse public read path、OpenAPI 和前端契约不得重新暴露 `agent_worker_running`，也不得从该产品路径调用 `_worker_running`。
- 已新增 architecture guard：News source status 不得访问 `runtime.providers`、`feed_client` 或 `_registry` 来生成 provider capability payload。
- 已新增 architecture guard：News fetch/status provider-contract validation 不得通过 feed client、provider wrapper 或 private `_registry` 反推 supported provider types。
- 已新增 architecture guard：News provider-contract schema side 不得用 `PROVIDER_TYPES` 兜底 DB constraint introspection。
- 已新增 architecture guard：News item-process agent-admission context 不得用 worker 内存对象兜底 repository readback。
- 已新增 architecture guard：Token Radar source dirty queue 不得被 ingest、resolution reprocess、projection worker 或 projection service 当成可选 repository contract。
- 已新增 architecture guard：notification aggregated external delivery reactivation 不得探测 `enqueue_or_requeue_delivery` 后 fallback 到 insert-only enqueue。
- 已新增 architecture guard：Pulse low-information hide 不得把缺失 `hide_public_candidate_for_low_information` 当成 no-op。
- 已新增 architecture guard：Pulse dirty-trigger job/edge/capacity/queue-depth 状态不得用 optional repository fallback 当成空控制面状态。
- 已新增 architecture guard：Macro assets daily brief public read path 不得用 optional loader 把缺 `latest_macro_daily_brief` 仓储契约当成空 read model。
- 已新增 architecture guard：Macro crypto-derivatives CEX board public read path 不得用 optional repo 把缺 `cex_oi_radar` 仓储契约当成无 board。
- 已新增 architecture guard：Token Case CEX detail 不得用 optional snapshot repository 把缺 `cex_detail_snapshots.latest_snapshot` 仓储契约当成无 detail。
- 已新增 architecture guard：Token Case market-live 不得用 optional latest tick repository 把缺 `latest_market_tick` 仓储契约当成缺市场数据。
- 已新增 architecture guard：Macrodata bundle import 必须使用正式 `RepositorySession.unit_of_work` / `require_transaction`，不得恢复 raw `conn.transaction()` fallback。
- 已新增 architecture guard：PulseCandidateJobService 必须使用正式 `RepositorySession.transaction`，不得恢复 `_transaction(repos.conn)`、`nullcontext`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()`。
- 已新增 architecture guard：PulseJobsRepository terminal/dead paths 必须要求 connection transaction，不得恢复 `nullcontext`、optional transaction fallback 或 terminal path manual commit。
- 已新增 architecture guard：PulseAdmissionRepository claim path 必须要求 connection transaction，不得通过 shared helper 恢复 `nullcontext`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()` fallback。
- 已新增 architecture guard：News page/source-quality projection workers 必须使用正式 `RepositorySession.transaction`，不得恢复 `_transaction(repos.conn)`、`nullcontext` 或 raw `conn.transaction()` fallback。
- 已新增 architecture guard：PulseCandidateWorker 必须使用正式 `RepositorySession.transaction`，不得恢复 `_transaction(repos.conn)`、`hasattr(conn, "transaction")` 或 raw `conn.transaction()` fallback。
- 已新增 architecture guard：News fetch/process/brief runtime 写 worker 必须使用正式 `RepositorySession.transaction`，不得恢复 `repos.conn.transaction()` 或 raw `conn.transaction()` fallback。
- 已新增 architecture guard：EventAnchorBackfillWorker stale cleanup 必须使用 worker-session `unit_of_work`，不得恢复 `_commit_if_supported` 或 manual `commit()` fallback。
- 已新增 architecture guard：EventAnchorBackfillJobRepository terminal paths 必须要求 connection transaction，不得恢复 `nullcontext` 或 optional transaction fallback。
- 已新增 architecture guard：ResolutionRefreshWorker 的 lookup running/finish/fail/claim completion 状态转换必须使用 `RepositorySession.transaction`，不得恢复 `repos.conn.commit()`、raw `repos.conn.transaction()` 或 optional transaction probing。
- 已新增 architecture guard：NotificationDeliveryWorker 的 delivery claim/pre-flight/complete/fail 状态转换必须使用 `RepositorySession.transaction` 和 repository `commit=False`，不得恢复 worker `.conn.commit()`、`nullcontext` 或 optional transaction probing。
- 已新增 architecture guard：Token intent rebuild/reprocess 必须使用 `RepositorySession.transaction`，不得恢复 direct `repos.conn.commit()`、raw connection transaction probing、optional session transaction probing 或 `commit: bool` 兼容参数。
- 已新增 architecture guard：MacroViewProjectionWorker 必须使用 `RepositorySession.transaction`，不得恢复 worker `commit=True`、manual commit、optional transaction probing，也不得在 `_run_claimed_once(...)` 中直接发送 `macro_view_snapshot_updated`。
- 已新增 architecture guard：NewsProjectionDirtyTargetRepository terminalize path 必须要求 connection transaction，不得恢复 `nullcontext`、`transaction_factory` 或 manual commit fallback。
- 已新增 architecture guard：NewsProjectionDirtyTargetRepository enqueue/claim/done/error mutation 必须要求 connection transaction，不得恢复 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。
- 已新增 architecture guard：TokenRadarSourceDirtyEventRepository enqueue/claim/done/error mutation 必须要求 connection transaction，不得恢复 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。
- 已新增 architecture guard：TokenRadarDirtyTargetRepository target enqueue/market enqueue/claim/catch-up enqueue/done/error mutation 必须要求 connection transaction，不得恢复 manual `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。
- 已新增 architecture guard：Ops projection dirty repair 的 execute 模式必须要求 connection transaction，不得让 `_transaction(conn)` 返回 `nullcontext()`；dry-run 的只读 `nullcontext` 分支保留。
- 已新增 architecture guard：TokenCaptureTierWorker projection 必须使用正式 `RepositorySession.transaction`，claim 必须发生在 transaction 内，且不得恢复 `_commit_if_supported`、`commit=True`、`commit: bool` 或 manual `commit()` fallback。
- `jsonb_array_elements_text` 仍在 News 等其他域出现；这些是本次 Pulse public read path 和 Narrative 产品 currentness 路径之外的既有查询形状，不能被本次修复声明为已治理。

这个扫描只能证明目标残留被清掉，不能替代 PostgreSQL 真实负载下的 `EXPLAIN (ANALYZE, BUFFERS)`。

## 已完成修复清单

- Stocks Radar 读路径 DB-only，删除 request-time quote provider。
- Macrodata quote runtime lane 删除。
- `resolution_refresh` manifest/runtime/tests 对齐 dirty lookup queue。
- `resolution_refresh` manifest 显式声明 provider IO，避免 worker inventory 漂移。
- `account_quality` 读服务和 backfill 写服务拆分，API/read CLI 不再持有 backfill 方法，也不直接 import repository，跨域 interface 也不再导出 repository/backfill。
- `account_quality` 增加 domain-local `ARCHITECTURE.md` 并链接到全局架构。
- 全局 Narrative 架构摘要对齐 hard-cut：当前职责是 `narrative_admissions` source-set read model，不再把退役 LLM semantics/digest lane 当成 active ownership。
- Narrative 产品读模型删除 retired semantic backlog/processing 暗示，保留 selected post legacy semantic 只读上下文。
- Signal Pulse public health 删除 worker/scheduler liveness 字段，契约和前端类型同步 hard-cut。
- News source status 改为静态 provider-type contract + persisted source rows，不再读取 runtime provider object。
- News fetch 和 `/api/status.news_provider_contract` 也改为静态 provider-type contract + DB schema constraint，不再读取 provider object capability。
- News fetch 删除 provider-contract schema enum fallback，缺失 DB schema introspection 会 fail fast。
- News item-process admission context 内存 fallback 删除，缺失 repository readback 会 fail fast 并走 retry/terminal 处理。
- News fetch dirty target current-item fallback 删除，canonical upsert 缺失 repository affected set 会 fail closed。
- News projection dirty enqueue 删除 servable filter 缺失时的放行 fallback。
- Token Radar source dirty queue 可选兼容删除，ingest/reprocess/projection worker/service 都要求正式 repository contract。
- Token Radar target dirty queue 手动 commit 兼容删除，target enqueue、market enqueue、claim、bounded catch-up enqueue、done/error 在 repository 拥有提交权时要求正式 connection transaction。
- Market Tick Current dirty queue 手动 commit 兼容删除，market-current enqueue、claim、done/error 在 repository 拥有提交权时要求正式 connection transaction。
- Notification aggregated external delivery requeue 可选兼容删除，failed/dead reactivation 要求正式 repository contract。
- Pulse low-information hide 可选 no-op 删除，低信息 public-row 隐藏要求正式 repository contract。
- Pulse dirty-trigger state/capacity/queue-depth optional fallback 删除，缺 job/edge/count repository contract 会让 dirty trigger fail/retry。
- Macro assets daily brief optional loader 删除，`/api/macro/modules/assets` 要求正式 repository read contract。
- Macro crypto-derivatives CEX board optional repo 删除，`/api/macro/modules/assets/crypto-derivatives` 要求正式 repository read contract。
- Token Case CEX detail optional snapshot repo 删除，`/api/token-case` 和 `/api/search/inspect` 的 `CexToken` dossier 要求正式 repository read contract。
- Token Case market-live optional latest tick repo 删除，`/api/token-case` 和 `/api/search/inspect` 的 dossier 要求正式 repository read contract。
- Notification worker session optional UoW 删除，`notification_rule` 写 `notifications` 和 `notification_deliveries` 时要求正式 `repos.unit_of_work()`。
- Macrodata bundle import optional session UoW/raw connection transaction fallback 删除，offline replay/seed 写 `macro_observations`、`macro_import_runs`、`macro_projection_dirty_targets` 时要求正式 `repos.unit_of_work()` 和 `repos.require_transaction(...)`。
- PulseCandidateJobService optional session transaction/raw connection transaction fallback 删除，Pulse agent run/step/eval/candidate/playbook/admission/job terminal 写入要求正式 `repos.transaction()`。
- PulseJobsRepository terminal/dead paths 的 `nullcontext` / manual commit fallback 删除，`pulse_agent_jobs` terminal/dead state 与 `worker_queue_terminal_events` terminal ledger 写入要求正式 connection transaction。
- PulseAdmissionRepository claim path 的 shared `nullcontext` fallback 删除，`pulse_candidate_edge_state`、`pulse_target_run_budget`、`pulse_candidate_run_budget` admission 控制面写入要求正式 connection transaction。
- Macro observation series current refresh 的 `nullcontext` transaction fallback 删除，`macro_observation_series_rows` current-row delete/insert 与 `macro_observation_series_publication_state` update 要求正式 connection transaction。
- PulseJobsRepository 普通 job/run mutation 的手动 commit / transaction 探测兼容删除，job enqueue、success marking、running-job release、stale agent-run cleanup 在 repository 拥有提交权时要求正式 connection transaction。
- Pulse agent write repositories 普通 run/eval/evidence/candidate/playbook/admission mutation 的手动 commit 兼容删除，repository 拥有提交权时要求正式 connection transaction。
- PulseTriggerDirtyTargetRepository queue mutation 的手动 commit 兼容删除，enqueue/claim/done/error/reschedule 在 repository 拥有提交权时要求正式 connection transaction。
- News page/source-quality projection workers optional session transaction/raw connection transaction fallback 删除，`news_page_rows`、`news_source_quality_rows`、`news_sources.source_quality_status`、page dirty enqueue 和 dirty target done/error 状态写入要求正式 `repos.transaction()`。
- PulseCandidateWorker raw connection transaction fallback 删除，dirty-trigger claim、admission/edge/public visibility/job enqueue、dirty target done/error 状态写入要求正式 `repos.transaction()`。
- News fetch/process/brief runtime worker raw connection transaction fallback 删除，News facts、agent admission/brief ledger、projection dirty enqueue 和 claim/failure 状态写入要求正式 `repos.transaction()`。
- EventAnchorBackfillWorker stale cleanup manual commit fallback 删除，stale `event_anchor_backfill_jobs` terminalization 和 `enriched_events` terminal lifecycle 写入要求正式 `repos.unit_of_work()`。
- EventAnchorBackfillJobRepository terminal paths 的 `nullcontext` transaction fallback 删除，`event_anchor_backfill_jobs` terminalization 与 `worker_queue_terminal_events` terminal ledger 写入要求正式 connection transaction。
- EventAnchorBackfillJobRepository transaction helper optional probe 形状删除，缺失或 non-callable `transaction` 都在 terminal SQL 前抛 contract error。
- WakeBus / WakeWaiter optional commit/notifies fallback 删除，wake-pool connection 缺 callable `commit` 或 listener 缺 callable `notifies` 会直接暴露 runtime contract error。
- ResolutionRefreshWorker 手动 `repos.conn.commit()` 删除，lookup running/finish/fail/claim completion 状态转换要求正式 `repos.transaction()`，provider IO 继续在事务外执行。
- NotificationDeliveryWorker 手动 `repos.notifications.conn.commit()` 删除，delivery claim/pre-flight fail/log complete 和外部 IO 后 complete/fail 状态转换要求正式 `repos.transaction()`；`NotificationRepository` delivery 状态机方法支持 caller-owned `commit=False`，repository-owned commit 进入 connection transaction。
- Token intent rebuild/reprocess 手动 `repos.conn.commit()` 删除，token evidence/intents/lookup/resolution/discovery/source-dirty 写入要求正式 `repos.transaction()`，内部 helper 使用 `require_transaction` 防止绕过 session contract。
- MacroViewProjectionWorker 的 `commit=True` 提交碎片删除，dirty-target claim、series refresh、snapshot write、dirty-target done/error 进入正式 `repos.transaction()`；snapshot wake 改为事务退出后发送。
- TokenCaptureTierWorker projection manual commit / claim-before-transaction 兼容删除，`token_capture_tier_dirty_targets` claim、`token_capture_tier` write/demotion 和 dirty target done 状态写入要求正式 `repos.transaction()`。
- Queue Terminal operator resolve 的 `nullcontext` / manual commit fallback 删除，`worker_queue_terminal_events` operator action 与 retry transition 要求正式 connection transaction。
- DiscoveryRepository terminal lookup claims 的 `nullcontext` / manual commit fallback 删除，`token_discovery_dirty_lookup_keys` claim 删除与 terminal ledger 写入要求正式 connection transaction。
- NewsProjectionDirtyTargetRepository terminalize path 的 `nullcontext` / manual commit fallback 删除，`news_projection_dirty_targets` claim 删除与 terminal ledger 写入要求正式 connection transaction。
- NewsProjectionDirtyTargetRepository 普通 queue mutation 的手动 commit 兼容删除，enqueue/claim/done/error 在 repository 拥有提交权时要求正式 connection transaction。
- TokenRadarSourceDirtyEventRepository 普通 source-edge queue mutation 的手动 commit 兼容删除，enqueue/claim/done/error 在 repository 拥有提交权时要求正式 connection transaction。
- TokenRadarDirtyTargetRepository 普通 target queue mutation 的手动 commit 兼容删除，target enqueue、market enqueue、claim、recent-resolved catch-up enqueue、market-current enqueue、done/error 在 repository 拥有提交权时要求正式 connection transaction。
- Ops projection dirty repair execute 模式的 `nullcontext` fallback 删除，写 `news_projection_dirty_targets` 前要求 connection transaction；dry-run 保持只读统计。
- notification stale-running cleanup bounded + partial index。
- Token Radar publish path 删除 retention prune。
- Pulse handle filter 删除 JSONB event-array expansion。
- SDD 记录、generated DB schema、OpenAPI/types、SDD work index 更新。

## 验证状态

已通过：

- `uv run python scripts/validate_sdd_artifacts.py`
- `uv run python scripts/check_sdd_gate.py --feature 2026-06-12-kappa-cqrs-governance-root-fix --gate implement`
- `uv run python scripts/regen_sdd_work_index.py --check`
- `uv run pytest tests/architecture/test_api_read_paths_provider_free.py -q`
- `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_resolution_refresh_manifest_is_dirty_lookup_queue_consumer -q`
- `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_provider_io_manifest_inventory_is_explicit tests/architecture/test_worker_manifest_static_contracts.py::test_resolution_refresh_manifest_is_dirty_lookup_queue_consumer tests/architecture/test_worker_manifest_static_contracts.py::test_provider_io_manifest_workers_are_bounded_and_not_projection_claim_loaders -q`
- `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_provider_io_worker_marker_matches_manifest_inventory tests/architecture/test_worker_manifest_static_contracts.py::test_provider_io_manifest_inventory_is_explicit -q`
- `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_provider_io_worker_marker_matches_manifest_inventory tests/architecture/test_worker_inventory_contract.py::test_worker_inventory_keys_match_runtime_registry_and_settings -q`
- `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_stale_running_terminalization_is_bounded_and_skip_locked tests/architecture/test_pulse_no_compat.py::test_pulse_read_handle_filter_does_not_expand_event_id_jsonb -q`
- `uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_backend_public_read_paths_do_not_import_provider_wiring -q`
- `uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_read_model_service_has_no_backfill_write_path -q`
- `uv run pytest tests/architecture/test_api_read_paths_provider_free.py -q`
- `uv run pytest tests/architecture/test_src_domain_architecture.py -q`
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_quote_runtime_lane_is_removed -q`
- `uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py::test_token_radar_rank_publication_does_not_run_retention_prune -q`
- `make regen-contract`
- `uv run pytest tests/unit/test_signal_pulse_service.py tests/unit/test_api_signal_pulse_contract.py tests/architecture/test_api_read_paths_provider_free.py tests/contract/test_openapi_drift.py -q`
- `uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_news_source_status_uses_static_provider_contract_not_runtime_provider_object tests/unit/test_api_news_contract.py::test_news_api_source_status_includes_provider_diagnostics_without_postgres tests/unit/integrations/news_feeds/test_provider_registry.py::test_registry_routes_rss_atom_json_feed_and_cryptopanic_to_expected_wrappers -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_contract_validation_uses_static_contract_not_provider_object tests/unit/domains/news_intel/test_news_provider_contract.py::test_news_fetch_worker_returns_contract_error_without_provider_capability_probe tests/unit/domains/news_intel/test_news_provider_contract.py::test_runtime_status_news_provider_contract_uses_static_provider_types_without_provider_probe -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_contract_schema_uses_db_constraint_without_enum_fallback tests/unit/domains/news_intel/test_news_provider_contract.py::test_news_fetch_worker_fails_fast_when_schema_introspection_missing -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/test_providers_wiring.py::test_news_feed_client_returns_registry_backed_provider_and_closes_underlying_clients tests/unit/test_api_news_contract.py::test_news_api_source_status_includes_provider_diagnostics_without_postgres -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_agent_admission_context_uses_repository_readback_without_memory_fallback tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_fails_when_agent_admission_context_missing -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_fetch_dirty_targets_use_repository_affected_items_without_fallback tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_fails_when_canonical_upsert_omits_affected_news_item_ids -q`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_work_requires_repository_servable_filter_without_fallback tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_news_item_work_requires_repository_servable_filter -q`
- `uv run pytest tests/architecture/test_token_radar_source_width_contract.py::test_source_dirty_queue_is_required_without_optional_runtime_fallback tests/unit/test_token_radar_projection_worker.py::test_projection_worker_requires_source_dirty_event_repository tests/unit/domains/token_intel/test_token_radar_market_only_projection.py::test_rebuild_dirty_targets_requires_source_dirty_event_repository tests/unit/test_token_resolution_refresh.py::test_reprocess_requires_token_radar_source_dirty_repository -q`
- `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_worker_requires_delivery_requeue_contract_without_insert_only_fallback tests/unit/test_notification_worker_runtime.py::test_worker_requires_requeue_contract_for_aggregated_external_delivery -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_low_information_hide_requires_repository_contract_without_optional_fallback tests/unit/test_pulse_candidate_worker.py::test_low_information_hide_requires_repository_contract -q`
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py::test_macro_assets_daily_brief_requires_repository_contract_without_optional_loader tests/unit/test_api_macro_contract.py::test_macro_assets_module_requires_daily_brief_repository_contract tests/unit/test_api_macro_contract.py::test_macro_module_api_serves_assets_landing_module -q`
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py::test_macro_crypto_derivatives_cex_board_requires_repository_contract_without_optional_repo tests/unit/test_api_macro_contract.py::test_macro_crypto_derivatives_requires_cex_board_repository_contract tests/unit/test_api_macro_contract.py::test_macro_module_api_compacts_crypto_derivatives_cex_rows -q`
- `uv run pytest tests/architecture/test_runtime_lifecycle_hard_cut.py::test_token_case_cex_detail_requires_snapshot_repository_contract tests/unit/test_token_case_service.py::test_token_case_requires_cex_detail_snapshot_repository_for_cex_tokens -q`
- `uv run pytest tests/architecture/test_runtime_lifecycle_hard_cut.py::test_token_case_market_live_uses_durable_ticks_only tests/architecture/test_runtime_lifecycle_hard_cut.py::test_token_case_cex_detail_requires_snapshot_repository_contract tests/unit/test_token_case_service.py tests/unit/test_search_inspect_service.py -q`
- `uv run pytest tests/architecture/test_runtime_lifecycle_hard_cut.py::test_token_case_market_live_uses_durable_ticks_only tests/unit/test_token_case_service.py::test_token_case_requires_latest_market_tick_repository_contract -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_dirty_trigger_state_contracts_are_not_optional_fallbacks tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_missing_pulse_job_state_contract_fails_dirty_trigger_instead_of_marking_done -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py -q`
- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_requires_repository_session_source_query_contract tests/unit/test_token_profile_current_worker.py::test_rebuild_token_profile_current_once_requires_session_source_query_contract -q`
- `uv run pytest tests/unit/test_token_profile_current_worker.py tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_source_query.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_requires_repository_session_source_query_contract -q`
- `uv run pytest tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_radar_projection.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/architecture/test_token_radar_source_width_contract.py -q`
- `uv run pytest tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_token_radar_source_width_contract.py::test_source_dirty_event_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_radar_projection.py tests/unit/test_ingest_service_token_radar_dirty_targets.py -q`
- `uv run ruff format src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py && uv run ruff check src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py`
- `uv run mypy src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`
- `uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_target_dirty_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_token_radar_source_width_contract.py::test_target_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_radar_projection.py tests/unit/test_ingest_service_token_radar_dirty_targets.py -q`
- `uv run ruff format src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py tests/unit/test_token_radar_dirty_target_repository.py tests/architecture/test_token_radar_source_width_contract.py && uv run ruff check src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py tests/unit/test_token_radar_dirty_target_repository.py tests/architecture/test_token_radar_source_width_contract.py`
- `uv run mypy src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- `uv run pytest tests/unit/test_market_tick_current_repository.py::test_market_tick_current_dirty_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_market_tick_current_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/test_market_tick_current_repository.py tests/unit/test_market_tick_current_projection_worker.py tests/unit/test_market_tick_stream_worker.py tests/unit/test_market_tick_poll_worker.py tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff format src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py tests/unit/test_market_tick_current_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py && uv run ruff check src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py tests/unit/test_market_tick_current_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`
- `uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py -q`
- `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_worker_requires_worker_session_unit_of_work_without_manual_commit_fallback tests/unit/test_notification_worker_runtime.py::test_worker_requires_unit_of_work_session_contract -q`
- `uv run pytest tests/architecture/test_notifications_hard_cut.py tests/unit/test_notification_worker_runtime.py tests/unit/test_notification_rules.py -q`
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_bundle_import_requires_session_unit_of_work_without_conn_transaction_fallback tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_requires_repository_session_unit_of_work tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_write_macrodata_bundle_import_requires_session_transaction_contract -q`
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_fact_import_change_semantics.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_job_service_requires_session_transaction_without_nullcontext_fallback tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_repository_session_transaction_contract -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py -q`
- `uv run ruff check src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py tests/architecture/test_pulse_no_compat.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py`
- `uv run mypy src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_workers_require_session_transaction_without_nullcontext_fallback tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_requires_repository_session_transaction_before_claiming tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_requires_repository_session_transaction_before_claiming -q`
- `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_news_intel_kiss_simplification.py -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_worker_requires_session_transaction_without_conn_fallback tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_worker_requires_repository_session_transaction_before_claiming_dirty_targets -q`
- `uv run pytest tests/architecture/test_pulse_no_compat.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py -q`
- `uv run ruff check src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py tests/architecture/test_pulse_no_compat.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py`
- `uv run mypy src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_runtime_write_workers_require_session_transaction_without_conn_fallback tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_requires_repository_session_transaction_before_reconciling_sources tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_requires_repository_session_transaction_before_claiming_items tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_requires_repository_session_transaction_for_policy_skip_completion -q`
- `uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q`
- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_stale_cleanup_requires_worker_session_unit_of_work_without_manual_commit tests/unit/test_event_anchor_backfill_worker.py::test_run_once_requires_worker_session_unit_of_work_before_expiring_stale_jobs -q`
- `uv run pytest tests/unit/test_event_anchor_backfill_worker.py tests/unit/test_event_anchor_backfill_job_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_event_anchor_backfill_worker.py`
- `uv run mypy src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_repository_terminal_paths_require_connection_transaction_without_nullcontext tests/unit/test_event_anchor_backfill_job_repository.py::test_expire_stale_requires_connection_transaction_before_terminal_writes -q`
- `uv run pytest tests/unit/test_event_anchor_backfill_job_repository.py tests/unit/test_event_anchor_backfill_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_event_anchor_backfill_job_repository.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_projection_requires_session_transaction_without_manual_commit tests/unit/test_token_capture_tier_worker.py::test_project_once_requires_external_session_transaction tests/unit/test_token_capture_tier_worker.py::test_worker_requires_session_transaction_before_claiming_dirty_target -q`
- `uv run pytest tests/unit/test_token_capture_tier_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_token_capture_tier_worker.py`
- `uv run mypy src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py`
- `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_terminalize_requires_connection_transaction_before_delete_or_ledger_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_terminal_paths_require_connection_transaction_without_nullcontext -q`
- `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_target_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_mutations_use_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py -q`
- `uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py`
- `uv run mypy src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- `uv run pytest tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_execute_requires_transaction_before_reads_or_writes tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_execute_requires_transaction_without_nullcontext_fallback -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py::test_pulse_job_terminal_paths_require_connection_transaction_before_job_or_ledger_sql tests/architecture/test_pulse_no_compat.py::test_pulse_jobs_repository_terminal_paths_require_connection_transaction_without_nullcontext -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_admission_repository.py::test_claim_pulse_admission_requires_connection_transaction_before_edge_or_budget_sql tests/architecture/test_pulse_no_compat.py::test_pulse_admission_repository_requires_connection_transaction_without_nullcontext -q`
- `uv run pytest tests/unit/domains/macro_intel/test_macro_generation_swap.py::test_refresh_observation_series_rows_requires_connection_transaction_before_current_publication_writes tests/architecture/test_macro_no_compatibility_contract.py::test_macro_observation_series_refresh_requires_connection_transaction_without_nullcontext -q`
- `uv run pytest tests/unit/domains/macro_intel/test_macro_generation_swap.py tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/architecture/test_macro_no_compatibility_contract.py tests/architecture/test_macro_kappa_contract.py -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py::test_pulse_job_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_pulse_no_compat.py::test_pulse_jobs_repository_mutations_use_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/domains/pulse_lab/test_pulse_admission_repository.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py tests/architecture/test_pulse_no_compat.py -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_repository_transactions.py::test_pulse_agent_write_repositories_require_connection_transaction_before_sql_when_committing tests/architecture/test_pulse_no_compat.py::test_pulse_agent_write_repositories_use_shared_transaction_helper_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_repository_transactions.py tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/domains/pulse_lab/test_pulse_admission_repository.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/architecture/test_pulse_no_compat.py -q`
- `uv run ruff check src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py src/parallax/domains/pulse_lab/repositories/pulse_runs_repository.py src/parallax/domains/pulse_lab/repositories/pulse_agent_eval_repository.py src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py src/parallax/domains/pulse_lab/repositories/pulse_candidates_repository.py src/parallax/domains/pulse_lab/repositories/pulse_playbooks_repository.py src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py tests/unit/domains/pulse_lab/test_pulse_agent_repository_transactions.py tests/architecture/test_pulse_no_compat.py`
- `uv run mypy src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py src/parallax/domains/pulse_lab/repositories/pulse_runs_repository.py src/parallax/domains/pulse_lab/repositories/pulse_agent_eval_repository.py src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py src/parallax/domains/pulse_lab/repositories/pulse_candidates_repository.py src/parallax/domains/pulse_lab/repositories/pulse_playbooks_repository.py src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_pulse_trigger_dirty_target_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_target_repository_uses_shared_transaction_helper_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/domains/pulse_lab/test_pulse_admission_repository.py tests/unit/domains/pulse_lab/test_pulse_agent_repository_transactions.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/architecture/test_pulse_no_compat.py -q`
- `uv run ruff check src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/architecture/test_pulse_no_compat.py`
- `uv run mypy src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`
- `uv run pytest tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py::test_profile_current_dirty_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/test_token_profile_current_worker.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_projection.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py`
- `uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py::test_token_image_source_dirty_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/test_token_image_mirror_worker.py tests/unit/test_token_image_mirror.py tests/unit/test_token_image_source_admission.py tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`
- `uv run pytest tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py::test_asset_profile_refresh_target_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_refresh_target_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_asset_profile_refresh_worker.py tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py`
- `uv run pytest tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py::test_token_capture_tier_dirty_mutations_require_connection_transaction_before_sql_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`
- `uv run pytest tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/unit/test_token_capture_tier_worker.py tests/unit/test_token_capture_tier_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py`
- `uv run pytest tests/unit/test_token_radar_projection.py::test_refresh_rank_set_requires_callable_connection_transaction_before_publish tests/architecture/test_token_radar_publication_state_hard_cut.py::test_token_radar_rank_publication_requires_connection_transaction_without_optional_probe -q`
- `uv run pytest tests/unit/test_event_anchor_backfill_job_repository.py::test_mark_terminal_requires_callable_connection_transaction_before_terminal_writes tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_repository_terminal_paths_require_connection_transaction_without_nullcontext -q`
- `uv run pytest tests/unit/test_event_anchor_backfill_job_repository.py tests/unit/test_event_anchor_backfill_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py tests/unit/test_event_anchor_backfill_job_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- `uv run pytest tests/unit/test_db_pool_bundle.py::test_wake_emitter_requires_callable_commit_before_notify_completion tests/unit/test_wake_waiter.py::test_wait_requires_callable_commit_after_listen tests/unit/test_wake_waiter.py::test_wait_requires_callable_notifies_source tests/architecture/test_worker_runtime_contracts.py::test_wake_bus_is_emit_only -q`
- `uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_wake_waiter.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py -q`
- `uv run ruff check src/parallax/app/runtime/wake_bus.py src/parallax/app/runtime/wake_waiter.py tests/unit/test_db_pool_bundle.py tests/unit/test_wake_waiter.py tests/architecture/test_worker_runtime_contracts.py`
- `uv run mypy src/parallax/app/runtime/wake_bus.py src/parallax/app/runtime/wake_waiter.py`
- `uv run pytest tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_requires_session_transaction_before_start_lookup tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_resolution_refresh_worker_requires_session_transaction_without_manual_commit -q`
- `uv run pytest tests/unit/test_resolution_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q`
- `uv run ruff check src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py tests/unit/test_resolution_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `uv run mypy src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- `rg -n "repos\.conn\.commit\(|repos\.conn\.transaction\(|getattr\(repos, \"transaction\", None\)|getattr\(repos\.conn, \"transaction\", None\)|getattr\(repos\.conn, \"commit\", None\)" src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- `uv run pytest tests/unit/test_notification_worker_runtime.py::test_delivery_worker_requires_session_transaction_before_claim tests/unit/test_notification_worker_runtime.py::test_delivery_worker_keeps_external_io_outside_session_transaction tests/architecture/test_notifications_hard_cut.py::test_notification_delivery_worker_requires_session_transaction_without_manual_commit_fallback tests/architecture/test_notifications_hard_cut.py::test_notification_delivery_repository_exposes_worker_owned_commit_boundary -q`
- `uv run pytest tests/unit/test_notification_worker_runtime.py tests/architecture/test_notifications_hard_cut.py -q`
- `make check`

`make check` 覆盖 lint、format、mypy、web typecheck/lint/format、unit、architecture、contract；最新结果为 `3401 passed, 2 skipped in 32.80s`。

未完成：

- `make check-all` 最终完成证据。
- integration/e2e/golden/coverage full completion gate。

原因：

- 用户明确要求停止集成测试，因为当前 integration suite 耗时过高。
- 第二次 full run 在用户停止前已经通过非集成段，并在 integration 内达到 `205 passed`，但该结果不是最终完成证据。

## 根因六十：Token Radar dirty projection 把 `commit=False` 误当成延迟提交

现象：

- `TokenRadarProjectionWorker` 会先 claim `token_radar_dirty_targets` 和 `token_radar_source_dirty_events`，然后把 claims 传给 `TokenRadarProjection.rebuild_dirty_targets(...)`。
- service 内部的 source-edge populate、target-feature upsert/delete 多数传 `commit=False`，但整个 `rebuild_dirty_targets` 之前没有显式连接事务。
- `refresh_rank_set(...)` 自己开启发布事务，随后 dirty target done/error 又用 `commit=True` 单独终结。

根因：

- Parallax PostgreSQL 连接使用 `autocommit=True`。在这种连接上，如果没有显式 `conn.transaction()`，一次 `commit=False` repository call 并不会形成“稍后统一提交”的事务边界；每条 SQL 仍会独立落地。
- 这把一次 Token Radar read-model 发布链拆成了几段不同提交：source edge / target feature 私有投影、current row/publication state 发布、dirty queue terminal state。任何中途失败都会留下难以推理的中间状态。
- 这也弱化了 Kappa/CQRS 的 rebuildable read-model 原则：`token_radar_rank_source_events`、`token_radar_target_features`、`token_radar_current_rows`、`token_radar_publication_state` 和 dirty queue 终态应该是同一次处理尝试的可解释结果，而不是自动提交拼出来的副作用集合。

修复：

- `TokenRadarProjection.rebuild_dirty_targets(...)` 现在先进入 `_transaction_context(self.repos.conn)`，缺少 callable `transaction` 会在 dirty claim SQL 之前失败。
- claim 之后的 source edge populate、target feature upsert/delete、rank publication attempt、dirty target done/error 都通过 caller-owned `commit=False` 落在同一个显式连接事务里。
- `refresh_rank_set` 失败路径的 publication failed 标记也不再强行 `commit=True`，避免在外层 dirty projection 事务中打穿提交边界。
- 删除 `TokenRadarProjectionWorker` 未使用的 `_mark_publication_failed` 侧路，避免保留 worker-owned `commit=True` 诊断残留。

验证：

- RED：`uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py::test_token_radar_dirty_projection_processing_uses_one_explicit_transaction -q`
- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_processes_claims_inside_explicit_transaction tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_transaction_before_claiming -q`
- GREEN：`uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_token_radar_source_width_contract.py -q`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py tests/unit/test_token_radar_projection.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/architecture/test_token_radar_publication_state_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`

## 根因六十一：TokenIntentResolver 保留了未使用的直接提交兼容参数

现象：

- `TokenIntentResolver.resolve(...)` 仍然暴露 `commit: bool = False`。
- 当 `persist=True` 且 `commit=True` 时，它会调用 `self.resolutions.conn.commit()`。
- 真实 ingest、rebuild、resolution reprocess 调用都已经传 `commit=False`，并由外层 `IngestService.unit_of_work` 或 `RepositorySession.transaction` 管理提交。

根因：

- resolver 混合了两个职责：确定性身份解析，以及可选的仓储提交控制。
- 在 Kappa/CQRS 事实写入链路中，resolver 应该只产生确定性 resolution decision；是否写入、何时提交属于调用者的事实事务。
- 保留 `commit=True` 参数会给测试或未来调用者提供第二提交边界，绕开已经治理过的 token evidence / intent / lookup / resolution / discovery / source-dirty 原子写入。

修复：

- 删除 `TokenIntentResolver.resolve(...)` 的 `commit` 参数。
- 删除 `self.resolutions.conn.commit()` 分支。
- 调整 ingest、token intent rebuild、resolution reprocess 调用点，不再传 `commit=False` 兼容实参。
- 架构 guard 扩展到 `token_intent_resolver.py`，禁止 `commit: bool` 和 `self.resolutions.conn.commit()` 回归。

验证：

- RED：`uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit -q`
- GREEN：`uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit tests/unit/test_token_intent_resolver.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_intent_rebuild_runtime.py -q`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/services/token_intent_resolver.py src/parallax/domains/evidence/services/ingest_service.py src/parallax/domains/token_intel/services/token_resolution_refresh.py src/parallax/domains/token_intel/runtime/token_intent_rebuild.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_token_intent_rebuild_runtime.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/services/token_intent_resolver.py src/parallax/domains/evidence/services/ingest_service.py src/parallax/domains/token_intel/services/token_resolution_refresh.py src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`

## 根因六十二：Account Quality ops backfill 用裸 commit 假装批事务

现象：

- `AccountQualityBackfillService.backfill_account_token_call_stats(...)` 从上游事实读取账号/Token mention 和市场结果，写入 `account_profiles`、`account_token_call_stats`、`account_quality_snapshots`。
- repository 调用都传了 `commit=False`，但 service 最后直接调用 `self.repository.conn.commit()`。
- 这个路径虽然是 ops-only，不是长跑 worker，但它写的是产品 read model，会被 `/api/account-quality`、account alerts、事件作者 watched 装饰和通知规则读取。

根因：

- “ops 命令”被误当成可以弱化事务边界的脚本层；但在 Kappa/CQRS 里，只要它写 read model，就必须服从同一套单 writer、可重放、可解释提交边界。
- Parallax PostgreSQL 连接使用 `autocommit=True`。没有显式 `conn.transaction()` 时，`commit=False` 不会把 profile/stat/snapshot 多次写入变成一个延迟提交批次。
- 因此一次账号质量重建可能被拆成 profile 已写、stat 已写、snapshot 未写的中间状态，公共读路径会看到半成品派生状态。

修复：

- `AccountQualityBackfillService` 现在在读取上游事实和写入账号 read model 前进入 `_transaction(self.repository.conn)`。
- 缺少 callable `transaction` 会抛 `account_quality_backfill_transaction_required`，并且在任何 backfill 读写前失败。
- 删除裸 `self.repository.conn.commit()`，保留 repository 调用上的 caller-owned `commit=False`。
- 架构 guard 禁止 `self.repository.conn.commit()`、`nullcontext` 和 optional transaction probing 回归。

验证：

- GREEN：`uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_backfill_uses_connection_transaction_without_manual_commit_fallback tests/unit/test_account_quality_service.py::test_account_quality_backfill_runs_inside_one_connection_transaction tests/unit/test_account_quality_service.py::test_account_quality_backfill_requires_connection_transaction_before_reads_or_writes -q`
- GREEN：`uv run pytest tests/unit/test_account_quality_repository.py tests/unit/test_account_quality_service.py tests/architecture/test_api_read_paths_provider_free.py -q`
- GREEN：`uv run ruff check src/parallax/domains/account_quality/services/account_quality_backfill_service.py tests/unit/test_account_quality_service.py tests/architecture/test_api_read_paths_provider_free.py`
- GREEN：`uv run mypy src/parallax/domains/account_quality/services/account_quality_backfill_service.py`

## 根因六十三：Asset Market sync service 把 provider 读取和 DB 批写事务混成裸提交

现象：

- `sync_binance_usdt_perp_routes(...)`、`sync_cex_token_profiles(...)`、`sync_us_equity_symbols(...)` 都先执行多次 repository `commit=False` 写入，再直接调用 `*.conn.commit()`。
- 这些路径写入 `cex_tokens`、`price_feeds`、`cex_token_profiles` 和 US equity registry rows，都会影响 deterministic resolver、Token Profile Current、Token Case/Search Inspect 等下游读模型。
- CEX profile sync 还可能把 `profile_source.token_profiles()` 的 provider 迭代和 DB 写入交织在同一个函数循环里。

根因：

- service 层把“这是同步/维护命令”理解成可以直接管理连接提交，而没有区分 provider IO 和 DB materialization。
- 对 PostgreSQL autocommit 连接而言，裸 `conn.commit()` 不是多行 `commit=False` 写入的可靠批事务边界。
- 如果 provider 迭代、DB 写入、最终提交混在一起，会同时违反两条规则：外部 IO 不应持有 DB 事务，DB 批写又必须有明确事务。

修复：

- 三个 sync service 都新增直接 callable connection transaction helper，缺少或 malformed `transaction` 时分别抛出 `asset_market_sync_transaction_required`、`cex_token_profile_sync_transaction_required`、`us_equity_symbol_sync_transaction_required`。
- Binance route 拉取、CEX profile 拉取、Nasdaq Trader symbol 拉取/解析保留在事务外。
- route/feed/profile/symbol/deactivation DB 写入全部进入显式 connection transaction，并继续以 caller-owned `commit=False` 调用 repository。
- 删除 service 层裸 `*.conn.commit()`。
- 架构 guard 锁住三条 service 的 `_transaction(...)` 形状，禁止 `.conn.commit()`、`nullcontext` 和 optional transaction probing 回归。

验证：

- GREEN：`uv run pytest tests/unit/test_asset_market_sync.py tests/unit/test_cex_token_profile_sync.py tests/unit/test_us_equity_symbol_sync.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_market_sync_services_require_connection_transaction_without_manual_commit -q`
- GREEN：`uv run ruff check src/parallax/domains/asset_market/services/asset_market_sync.py src/parallax/domains/asset_market/services/cex_token_profile_sync.py src/parallax/domains/asset_market/services/us_equity_symbol_sync.py tests/unit/test_asset_market_sync.py tests/unit/test_cex_token_profile_sync.py tests/unit/test_us_equity_symbol_sync.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/asset_market/services/asset_market_sync.py src/parallax/domains/asset_market/services/cex_token_profile_sync.py src/parallax/domains/asset_market/services/us_equity_symbol_sync.py`

## 根因六十四：CLI ops execute 路径保留了 worker/service 之外的裸提交孤岛

现象：

- `ops.py` 中 token radar dirty repair、token capture tier rank-set repair、News canonical rebuild、GMGN directory sync 仍有 `commit=True` 或 `repos.conn.commit()` / `repository.conn.commit()`。
- 这些命令不是常驻 worker，但它们会写 dirty queues、删除/重建 News projection rows、更新 GMGN directory account profile columns。

根因：

- CLI ops 被当成“人工维护脚本”，没有完全套用 Kappa/CQRS 的事务边界和 PostgreSQL autocommit 规则。
- dry-run 可以只读，但 execute-mode 一旦写 control/read-model state，就必须有明确 connection transaction。
- GMGN directory sync 还存在 provider iteration 和 DB 写入交织的风险；外部 IO/分页不应该发生在 DB transaction 内。

修复：

- `ops.py` 新增 `_transaction(conn)`，缺少 callable `transaction` 时抛 `ops_command_transaction_required`。
- token radar dirty enqueue、token capture tier rank-set enqueue、News canonical rebuild delete/enqueue 都在 execute transaction 内读取本次修复集合并用 caller-owned `commit=False` 写入。
- GMGN directory entries 先从 client materialize，再进入 repository connection transaction 写 `upsert_directory_entry(commit=False)`。
- 架构 guard 禁止 `ops.py` 重新出现 `commit=True`、`.conn.commit()`、`nullcontext` 和 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_execute_commands_require_transaction_without_manual_commit_fallback -q`，`16 passed`
- GREEN：`uv run ruff check src/parallax/app/surfaces/cli/commands/ops.py tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/app/surfaces/cli/commands/ops.py`
- GREEN：`make check`，`3274 passed, 2 skipped in 34.08s`；两个 skip 分别是本地 PostgreSQL `127.0.0.1:55432` 不可用与 `GMGN_PROVIDER_DRIFT=1` 未启用。

剩余 `commit=True` 分类：

- 收窄扫描只剩 `token_radar_projection_worker.py`、`market_tick_current_projection_worker.py`、`asset_profile_refresh_worker.py`、`token_image_mirror_worker.py`、`token_profile_current_worker.py` 中的 dirty-target `claim_due(..., commit=True)`。
- 这些位置的语义是短 claim/lease 提交：先持久化租约，释放会话/锁，再进入有界 projection transaction 或外部 provider/file IO 边界。
- 它们不是服务层/CLI 的裸提交，也不是兼容 fallback。当前 hard-cut 重点仍是禁止 worker/service/ops 在业务写入中绕过 caller-owned transaction。

## 根因六十五：domain worker 对注入 wake emitter 的方法契约做了静默兼容

现象：

- `NotificationWorker`、`NewsFetchWorker`、`NewsSourceQualityProjectionWorker`、`MarketTickCurrentProjectionWorker`、`EventAnchorBackfillWorker` 在 wake object 被注入后仍用 `getattr(..., None)` 或 optional branch 探测 `notify_*` / `wake()`。
- 当 DB state 已提交且应该发 wake hint 时，malformed wake object 会被当成“无 wake”静默吞掉。

根因：

- 把“wake 不是事实来源”误解成“wake runtime contract 可以是 optional shape”。
- 成熟 Kappa/CQRS 中 missed wake 可由 bounded interval catch-up 修正，但 malformed injected wake object 是 wiring/config/runtime contract 错误，应显式暴露。

修复：

- 缺 wake object 仍允许表示没有低延迟 hint。
- 已注入 wake object 时，Notification delivery wake、News page dirty wake、Market Tick Current -> Token Radar wake、Event Anchor -> market tick wake 都直接调用 required method。
- 架构 guard 禁止 optional wake-emitter probing token 回归。

验证：

- GREEN：`uv run pytest tests/unit/test_notification_worker_runtime.py::test_worker_requires_delivery_wake_contract_when_external_deliveries_are_enqueued tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_fetch_worker_requires_news_page_dirty_wake_contract_after_metadata_dirty_enqueue tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_requires_news_page_dirty_wake_contract_after_page_dirty_enqueue tests/unit/test_market_tick_current_projection_worker.py::test_worker_requires_wake_emitter_contract_after_token_radar_dirty_enqueue tests/unit/test_event_anchor_backfill_worker.py::test_event_anchor_wake_emitter_contract_is_required_when_emitter_is_injected tests/architecture/test_worker_runtime_contracts.py::test_runtime_wake_emitters_do_not_swallow_missing_notify_contracts -q`，`6 passed`
- GREEN：`uv run pytest tests/unit/test_notification_worker_runtime.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/test_market_tick_current_projection_worker.py tests/unit/test_event_anchor_backfill_worker.py tests/architecture/test_worker_runtime_contracts.py::test_runtime_wake_emitters_do_not_swallow_missing_notify_contracts -q`，`57 passed`
- GREEN：targeted ruff / mypy passed

## 根因六十六：WorkerBase 把注入 wake_waiter 当成 optional shape

现象：

- `WorkerBase.stop()` 用 `getattr(self.wake_waiter, "wake", None)`，缺少 `wake()` 时静默不唤醒。
- `_wait_for_next_iteration()` 用 `hasattr(self.wake_waiter, "async_wait")`，缺少 `async_wait(...)` 时退回本地 `stop_event.wait()`。
- `_close_wake_waiter()` 用 optional `getattr(..., "close", None)`，缺少 `close()` 时静默跳过关闭。

根因：

- Root65 治理的是 domain worker 的 wake emitter；这里是更靠根部的通用 worker loop。
- 成熟 Kappa/CQRS 允许 missed wake 由 interval catch-up 修正，但前提是 runtime wiring 错误可见。注入了 malformed waiter 却静默退回 sleep/skip close，会掩盖 LISTEN wake 失效、资源泄漏和 shutdown latency 问题。

修复：

- `wake_waiter is None` 仍表示没有低延迟 wake，使用本地 interval sleep。
- 只要注入了 `wake_waiter`，`WorkerBase` 就直接调用 `wake()`、`async_wait(...)`、`close()`。
- 架构 guard 禁止 `WorkerBase` 重新出现 optional wake-waiter probing token。

验证：

- GREEN：`uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_stop_requires_injected_wake_waiter_wake_contract tests/unit/test_worker_base_runtime.py::test_worker_base_wait_requires_injected_wake_waiter_async_wait_contract tests/unit/test_worker_base_runtime.py::test_worker_base_aclose_requires_injected_wake_waiter_close_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_base_wake_waiter_contract_is_direct_when_injected -q`，`4 passed`
- GREEN：`uv run pytest tests/unit/test_worker_base_runtime.py tests/architecture/test_worker_runtime_contracts.py::test_worker_base_wake_waiter_contract_is_direct_when_injected tests/architecture/test_worker_runtime_contracts.py::test_wake_bus_is_emit_only -q`，`24 passed`
- GREEN：targeted ruff / mypy passed

## 根因六十七：CEX Market Intel read-model 写入仍保留裸提交和失败路径事务漂移

现象：

- `CexOiRadarBoardWorker` 的成功发布路径已经通过 `repos.transaction()` 写 `cex_oi_radar_rows`、`cex_oi_radar_publication_state` 和 `cex_detail_snapshots`。
- 但 empty universe、all symbols failed、exception attempt-state 这些路径仍直接调用 `publish_board(...)` / `record_attempt_failure(...)`，依赖 repository 默认 `commit=True`。
- CEX OI board、detail snapshot、derivative series repositories 仍保留 repository-owned `self.conn.commit()`，导致同一 read-model writer 有两种提交语义。

根因：

- 之前只把“成功写 serving rows”看成 read-model publication，低估了 skipped/failed attempt state 也是 publication state 的一部分。
- 在 Kappa/CQRS 里，publication state 是 current read model 的控制面，不是日志旁路。失败尝试虽然不改 serving rows，也会更新 `latest_attempt_*`，必须和 worker session transaction / repository connection transaction 使用同一个边界。
- 裸 `self.conn.commit()` 在 psycopg/autocommit、测试 fake、RepositorySession 组合下语义不稳定：它既不能证明 SQL 已在事务里，也容易把失败状态写成成功路径之外的旁路。

修复：

- `CexOiRadarBoardWorker` 的 empty universe、all symbols failed、exception attempt-state 路径全部进入 `RepositorySession.transaction()`，并向 repository 传 `commit=False`。
- `CexOiRadarRepository`、`CexDetailSnapshotRepository`、`CexDerivativeSeriesRepository` 在 repository-owned commit 下先要求 callable connection `transaction()`，再递归执行 caller-owned `commit=False` 写入。
- 删除 CEX read-model repository 的裸 `self.conn.commit()` 语义；缺失或 malformed transaction contract 会在任何 SQL 前失败。
- 架构 guard 禁止这些 repository 重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_publish_board_requires_connection_transaction_before_sql_when_committing tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_record_attempt_failure_requires_connection_transaction_before_sql_when_committing tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_upsert_many_requires_connection_transaction_before_sql_when_committing tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_upsert_snapshot_requires_connection_transaction_before_sql_when_committing tests/unit/domains/cex_market_intel/test_cex_derivative_series_repository.py tests/architecture/test_cex_oi_kappa_contract.py::test_cex_read_model_repositories_require_explicit_transactions -q`，`8 passed`
- GREEN：`uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py tests/unit/domains/cex_market_intel/test_cex_derivative_series_repository.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py tests/architecture/test_cex_oi_kappa_contract.py -q`，`40 passed`
- GREEN：targeted ruff / mypy passed

## 根因六十八：Narrative Admission dirty-target repository 仍把控制面 queue 当成本地裸提交

现象：

- `NarrativeAdmissionWorker` 已经是当前 Narrative runtime 的唯一 writer，消费 `narrative_admission_dirty_targets` 并写 `narrative_admissions`。
- worker 路径已经在 `RepositorySession.transaction` 内用 `commit=False` claim/done/error dirty targets。
- 但 `NarrativeAdmissionDirtyTargetRepository` 的 repository-owned enqueue、claim、done、error、reschedule 仍使用 `self.conn.commit()`，导致同一控制面 queue 有 worker-session transaction 和 standalone naked commit 两套边界。

根因：

- 旧代码把 dirty-target queue 当成“只是调度表”，低估了它对现役 read-model writer 的控制面意义。
- 对 Kappa/CQRS 来说，dirty target 是 read-model catch-up 的 durable control plane：它决定哪些 target 会被重放、重试、释放或完成。它不是 public truth，但它是 worker correctness 的事实边界。
- 裸 `self.conn.commit()` 无法证明 enqueue/claim/delete/update 已在 PostgreSQL transaction 内执行，也会让测试 fake 和 autocommit 连接把 commit 误认为边界。

修复：

- `NarrativeAdmissionDirtyTargetRepository` 的 repository-owned mutation 统一先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- 空输入仍保持零 SQL、零事务。
- 缺失或 malformed transaction contract 会在任何 queue SQL 前失败。
- 架构 guard 禁止重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_dirty_target_mutations_require_connection_transaction_before_sql_when_committing tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_enqueue_targets_commit_owned_write_uses_connection_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_admission_dirty_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`7 passed`
- GREEN：`uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_admission_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_worker_runtime_contracts.py::test_public_narrative_reads_do_not_expose_retired_semantic_backlog tests/architecture/test_worker_runtime_contracts.py::test_global_architecture_does_not_describe_retired_narrative_llm_lanes_as_current tests/architecture/test_worker_runtime_contracts.py::test_narrative_hard_cut_contracts_are_documented -q`，`24 passed`
- GREEN：targeted ruff / mypy passed

## 根因六十九：NarrativeRepository 仍把 `narrative_admissions` serving row 写成可选 commit

现象：

- Root68 已经把 `narrative_admission_dirty_targets` queue 的 repository-owned mutation 切到显式 connection transaction。
- 但真正的 active serving read model `narrative_admissions` 仍由 `NarrativeRepository.upsert_admissions` 和 `stale_admission_target` 通过 `_commit_if_available(conn)` 完成 repository-owned commit。
- worker 正常路径虽然在 `RepositorySession.transaction` 内传 `commit=False`，但 repository 自己被调用时仍允许“有 commit 就调，没有就当作成功”的兼容语义。

根因：

- 旧实现把 `narrative_admissions` 的 upsert/stale 当成普通 repository 写入，而没有按 current read model publication 边界审计。
- 对 Kappa/CQRS 来说，`narrative_admissions` 是当前 Narrative source frontier 的 serving truth；它的 upsert 和 stale delete 不是附属日志，必须有可证明的 PostgreSQL transaction 边界。
- `_commit_if_available` 是典型兼容 shim：它让 fake/autocommit/缺失 commit 的连接都可能绕过显式事务，从而掩盖“不在 transaction 中写 current read model”的架构错误。

修复：

- `NarrativeRepository` repository-owned `upsert_admissions` 和 `stale_admission_target` 统一先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- 空 admissions 输入保持零 SQL、零事务。
- 删除 `_commit_if_available`；缺失或 malformed transaction contract 会在任何 `narrative_admissions` SQL 前失败。
- 架构 guard 禁止重新出现 `_commit_if_available`、`self.conn.commit()`、`getattr(conn, "commit", None)` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_narrative_admission_mutations_require_connection_transaction_before_sql_when_committing tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_narrative_admission_commit_owned_writes_use_connection_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_repository_admission_writes_require_connection_transaction_without_manual_commit_fallback -q`，`5 passed`

## 根因七十：TokenProfileCurrentRepository 仍把 `token_profile_current` serving row 写成裸 commit

现象：

- Root58 已经把 `token_profile_current_dirty_targets` 的 repository-owned enqueue/claim/done/error 切到显式 connection transaction。
- 但真正的 public profile current read model `token_profile_current` 仍由 `TokenProfileCurrentRepository.upsert_current(..., commit=True)` 在 SQL 后直接 `self.conn.commit()`。
- worker 正常路径在 `RepositorySession.transaction` 内传 `commit=False`，所以运行时主路径看起来正确；但 repository 自己的默认路径仍允许 current serving row 脱离显式事务边界。

根因：

- 之前审计优先治理了 dirty-target control plane，却没有把同一 worker 拥有的 serving row repository 纳入同一事务治理面。
- 对 Kappa/CQRS 来说，`token_profile_current` 是 rebuildable serving truth；它的身份由 `(target_type, target_id)` 稳定决定，且通过 `payload_hash` 保证 unchanged projection 写零 serving rows。这个 upsert 不是普通缓存写，必须有可证明的 PostgreSQL transaction 边界。
- 裸 `self.conn.commit()` 让 fake/autocommit/缺事务连接也能执行 SQL，掩盖了“repository-owned current row publication 没有显式 transaction contract”的根问题。

修复：

- `TokenProfileCurrentRepository.upsert_current` 在 `commit=True` 时先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- 缺失或 malformed transaction contract 会在任何 `token_profile_current` SQL 前失败。
- worker 路径保持不变：`TokenProfileCurrentWorker` 仍在 `RepositorySession.transaction` 内调用 `repos.token_profiles.upsert_current(row, commit=False)`。
- 架构 guard 禁止重新出现 `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

验证：

- GREEN：`uv run pytest tests/unit/test_token_profile_current_repository.py::test_upsert_current_requires_connection_transaction_before_sql_when_committing tests/unit/test_token_profile_current_repository.py::test_upsert_current_commit_owned_write_uses_connection_transaction_without_manual_commit tests/unit/test_token_profile_current_repository.py::test_upsert_current_sanitizes_text_and_json_payloads tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`4 passed`
- GREEN：`uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_repository.py tests/unit/test_token_profile_current_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_requires_repository_session_source_query_contract -q`，`18 passed`
- GREEN：targeted ruff / mypy passed
- GREEN：latest non-integration `make check` passed with `3257 passed, 2 skipped in 33.62s`

## 根因七十一：TokenImageAssetRepository 仍把 `token_image_assets` lifecycle row 写成裸 commit

现象：

- Root58 已经把 `token_image_source_dirty_targets` 的 repository-owned enqueue/claim/done/error 切到显式 connection transaction。
- Root70 又把 `token_profile_current` serving row 切到显式 connection transaction。
- 但位于两者之间、会决定 public logo 是否可用的 `token_image_assets` 仍由 `TokenImageAssetRepository.upsert_pending_sources` / `mark_ready` / `mark_error` / `mark_unsupported` 在 SQL 后直接 `self.conn.commit()`。
- `TokenImageMirrorWorker` 的 pending 写在 `RepositorySession.transaction` 内 `commit=False`，但 mirror terminal ready/error/unsupported 写通过 session adapter 默认 `commit=True`，最终仍走 repository-owned 裸 commit。

根因：

- 之前审计把 token image dirty-source queue 和 profile current serving row 分别治理了，但漏掉了中间的 local media lifecycle 表。
- `token_image_assets` 不是 provider raw frame；它是 provider logo URL 经本地镜像、magic-byte 校验、文件落盘后的可服务状态。`token_profile_current` 只允许 ready local row 成为 public `logo_url`，所以这张表直接影响 public read model。
- 裸 `self.conn.commit()` 让 image lifecycle publication 没有可证明的 transaction boundary，也让 worker adapter 可以绕过 `RepositorySession.transaction`，违背单 writer worker 的事务所有权。

修复：

- `TokenImageAssetRepository` repository-owned pending/ready/error/unsupported lifecycle mutations 统一先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- `TokenImageMirrorWorker` 的 `_TokenImageAssetSessionRepository` 终态写入改为进入 `RepositorySession.transaction`，并对底层 repository 传 `commit=False`。
- 缺失或 malformed transaction contract 会在任何 `token_image_assets` SQL 前失败。
- 架构 guard 禁止重新出现 `self.conn.commit()`、optional transaction probing 或 `nullcontext` fallback。

验证：

- GREEN：`uv run pytest tests/unit/domains/asset_market/test_token_image_asset_repository.py tests/unit/test_token_image_mirror_worker.py::test_token_image_asset_session_repository_uses_session_transaction_with_caller_owned_writes tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_asset_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`10 passed`
- GREEN：`uv run pytest tests/unit/domains/asset_market/test_token_image_asset_repository.py tests/unit/test_token_image_mirror.py tests/unit/test_token_image_mirror_worker.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/test_token_image_source_admission.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_asset_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_worker_runtime_contracts.py::test_token_image_mirror_is_only_token_image_assets_writer -q`，`42 passed`
- GREEN：targeted ruff / mypy passed
- GREEN：latest non-integration `make check` passed with `3274 passed, 2 skipped in 34.08s`

## 根因七十二：IdentityEvidenceRepository 仍把 `asset_identity_*` 事实/当前身份写成裸 commit

现象：

- `IngestService`、`ResolutionRefreshWorker` 和 token intent rebuild/reprocess 主路径都已经在外层事务里传 `commit=False` 写 `registry_assets`、`asset_identity_evidence` 和 `asset_identity_current`。
- 但 `IdentityEvidenceRepository.ensure_asset`、`upsert_identity_evidence`、`recompute_current_identity` 的默认 repository-owned 路径仍在 SQL 后直接 `self.conn.commit()`。
- 这意味着直接使用仓储默认入口时，资产 registry row、identity evidence ledger row、current identity row 可以在缺少显式 PostgreSQL transaction contract 的连接上写入。

根因：

- 前几轮治理优先处理了 worker queue、read-model current row 和 local image lifecycle，却漏掉了更上游的身份事实仓储默认路径。
- `asset_identity_evidence/current` 不是缓存；它们是 Kappa/CQRS 事实链路里决定 token 身份、Token Radar source edge、Search Inspect、Token Case 和 Pulse evidence packet 的业务真相之一。
- 裸 `self.conn.commit()` 让 fake/autocommit/缺事务连接也能执行身份事实 SQL，掩盖了“事实 ledger + current identity selection 必须有显式 transaction boundary”的根问题。

修复：

- `IdentityEvidenceRepository.ensure_asset`、`upsert_identity_evidence`、`recompute_current_identity` 在 `commit=True` 时先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- 缺失或 malformed transaction contract 会在任何 registry/identity SQL 前失败，错误标记为 `identity_evidence_repository_transaction_required`。
- 正常 ingest、resolution refresh、token intent rebuild/reprocess 路径保持外层 `RepositorySession.transaction` / ingest `unit_of_work`，继续用 `commit=False`。
- 架构 guard 禁止重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/test_asset_identity_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_identity_evidence_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`9 passed`
- GREEN：`uv run pytest tests/unit/test_asset_identity_repository.py tests/unit/test_resolution_refresh_worker.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_intent_rebuild_runtime.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_identity_evidence_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_resolution_refresh_worker_requires_session_transaction_without_manual_commit -q`，`25 passed`
- GREEN：targeted ruff / mypy passed
- GREEN：production residual scan had no matches
- GREEN：SDD validator / work-index check / analyze gate / `git diff --check` passed
- GREEN：latest non-integration `make check` passed with `3274 passed, 2 skipped in 34.08s`

## 根因七十三：RegistryRepository 仍把资产 registry、CEX route 和 US equity symbol 写成裸 commit

现象：

- Root72 已经治理了 `IdentityEvidenceRepository` 的 registry asset / identity evidence/current 默认写路径。
- 但 `RegistryRepository` 本身仍保留 `upsert_chain_asset`、`upsert_cex_token`、`upsert_pricefeed`、`upsert_us_equity_symbol`、`deactivate_missing_us_equity_symbols` 的 `self.conn.commit()`。
- 这些默认入口覆盖 `registry_assets`、`cex_tokens`、`price_feeds`、`us_equity_symbols`，是 resolution refresh、CEX route sync、US equity resolver 的基础写链路；服务层虽然多已在外层事务里传 `commit=False`，仓储默认路径仍允许缺少显式 PostgreSQL transaction contract 的写入。

根因：

- 前序治理先把 service/worker 的外层事务边界收紧，却没有把同一基础仓储的 repository-owned 默认提交路径纳入同一不变量。
- `RegistryRepository` 写的不是 UI 缓存：`registry_assets` 影响链上资产身份，`cex_tokens`/`price_feeds` 影响 CEX market target 选择，`us_equity_symbols` 影响 deterministic resolver 的跨资产消歧。
- 裸 `self.conn.commit()` 让 fake/autocommit/缺事务连接也能先执行 registry/route/symbol SQL，再用 commit 伪装成边界，掩盖了“基础 registry 事实必须在可证明事务内写入”的根问题。

修复：

- `RegistryRepository` 五个 repository-owned mutation 默认入口统一先要求 callable `conn.transaction()`，再递归走 caller-owned `commit=False` 写入。
- 缺失或 malformed transaction contract 会在任何 registry/route/feed/symbol SQL 前失败，错误标记为 `registry_repository_transaction_required`。
- Resolution refresh、ingest、Asset Market route sync、US equity symbol sync 等外层事务路径保持 `commit=False`，继续由 caller/session 拥有事务边界。
- 架构 guard 禁止重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/test_registry_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_registry_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`11 passed`
- GREEN：`uv run pytest tests/unit/test_registry_repository.py tests/unit/test_asset_market_sync.py tests/unit/test_us_equity_symbol_sync.py tests/unit/test_cex_binance_read_path_filters.py tests/unit/test_asset_identity_repository.py tests/unit/test_resolution_refresh_worker.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_intent_rebuild_runtime.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_registry_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_market_sync_services_require_connection_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_identity_evidence_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_resolution_refresh_worker_requires_session_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit -q`，`50 passed`
- GREEN：targeted ruff / mypy passed
- GREEN：production residual scan had no matches
- GREEN：SDD validator / work-index check / analyze gate / `git diff --check` passed
- GREEN：latest non-integration `make check` passed with `3285 passed, 2 skipped in 33.39s`

## 根因七十四：DiscoveryRepository 普通 lookup queue/result 状态转换仍把控制面写成裸 commit

现象：

- Root36 已经把 `DiscoveryRepository.terminalize_lookup_claims(...)` 的 claimed-row delete + terminal ledger 写入切到正式 connection transaction。
- Root39 又把 `ResolutionRefreshWorker` 的 lookup running/finish/fail/claim completion 主路径切到 `RepositorySession.transaction`，provider IO 保持在事务外。
- 但 `DiscoveryRepository` 自己默认拥有 commit 的普通 mutation 仍在 SQL 后直接 `self.conn.commit()`：`enqueue_lookup_keys`、`claim_due_lookup_keys`、`mark_lookup_done`、`reschedule_lookup_claims`、`start_lookup`、`finish_lookup`、`fail_lookup`。
- 这些方法覆盖 `token_discovery_dirty_lookup_keys` 和 `token_discovery_results`，是 `resolution_refresh` 的 lookup state machine；缺少 connection transaction 的 fake/autocommit 连接仍可先执行 SQL，再用裸 commit 伪装边界。

根因：

- 前序治理把 worker 外层 session 和 terminal delete+ledger 边界修好了，但没有把同一个仓储的普通 repository-owned 默认写路径纳入同一不变量。
- `token_discovery_dirty_lookup_keys` 不是临时缓存，它决定 unresolved lookup 的 wake/catch-up、lease、retry、done/reschedule；`token_discovery_results` 决定后续 reprocess 是否继续、何时刷新、是否 not_found/error。
- 成熟 Kappa/CQRS 中，control-plane queue 和 result state 是可恢复状态机。它可以被重放、catch up、terminalize，但每一次 state transition 都必须有清晰的事务边界；不能一部分靠 `RepositorySession.transaction`，另一部分靠仓储裸 `commit()`。
- 裸 `self.conn.commit()` 让“缺少正式 PostgreSQL transaction contract”被测试 fake 隐藏，实际风险是 claim/result/done/reschedule 在失败时和上层 reprocess、terminal ledger、wake hint 的可观察顺序产生漂移。

修复：

- `DiscoveryRepository` 七个普通 repository-owned mutation 统一走 `_run_repository_write(self.conn, commit, _write)`。
- `commit=True` 时先要求 callable `conn.transaction()`；缺失或 malformed transaction contract 会在任何 queue/result SQL 前失败，错误标记为 `discovery_repository_transaction_required`。
- `commit=False` caller-owned 路径保持不变，worker/reprocess 仍可在外层 `RepositorySession.transaction` 内组合写入。
- `terminalize_lookup_claims(...)` 保持 delete-returning + terminal-ledger 的显式 `with _transaction(self.conn):` 形态，避免把 terminal transition 和普通 mutation wrapper 混成一个含糊入口。
- 架构 guard 要求 `_run_repository_write` 存在且 7 个普通 mutation 全部使用它，并禁止 `self.conn.commit()`、`nullcontext` 或 optional transaction probing 回流。

验证：

- GREEN：`uv run pytest tests/unit/test_discovery_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_terminal_paths_require_connection_transaction_without_nullcontext -q`，`16 passed`
- GREEN：`uv run pytest tests/unit/test_discovery_repository.py tests/unit/test_resolution_refresh_worker.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_intent_rebuild_runtime.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_terminal_paths_require_connection_transaction_without_nullcontext tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_resolution_refresh_worker_requires_session_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit -q`，`32 passed`
- GREEN：`uv run ruff check src/parallax/domains/asset_market/repositories/discovery_repository.py tests/unit/test_discovery_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/asset_market/repositories/discovery_repository.py`
- GREEN：production residual scan had no matches
- GREEN：SDD validator / work-index check / analyze gate / `git diff --check` passed
- GREEN：latest non-integration `make check` passed with `3299 passed, 2 skipped in 33.63s`

## 根因七十五：AssetProfileRepository 仍把 DEX profile source cache 写成裸 commit

现象：

- Root48 已经把 `AssetProfileRefreshTargetRepository` 的 provider refresh target enqueue/claim/reschedule/error 切到正式 connection transaction。
- Root70/Root71 又把 public `token_profile_current` serving row 和 `token_image_assets` lifecycle row 切到正式事务边界。
- 但 `asset_profile_refresh` 链路中间真正写 provider source cache 的 `AssetProfileRepository` 仍在 `upsert_ready_profile(...)` 和 `upsert_status(...)` SQL 后直接 `self.conn.commit()`。
- 这会让 worker 表面上用 `RepositorySession.transaction` 写 `asset_profiles`、reschedule refresh target、enqueue `token_profile_current_dirty_targets`，但仓储默认路径仍允许缺事务 fake/autocommit 连接先写 source cache 再裸提交。

根因：

- 前序治理按 dirty queue 和 public read model 边界向两端推进，但漏掉了 provider source cache 这一层。
- `asset_profiles` 不是 public read model，也不是 provider raw frame；它是 DEX profile provider 的持久 source cache，后续 `TokenProfileCurrentWorker` 通过 `RepositorySession.source_query` exact-load 它，再投影到 public `token_profile_current`。
- 成熟 Kappa/CQRS 中，source cache 也是可重放链路里的持久输入。它可以不是最终 serving truth，但一旦会唤醒下游 read model，就必须和 refresh target reschedule、dirty enqueue 保持可证明的事务边界。
- 裸 `self.conn.commit()` 把“缺少正式 PostgreSQL transaction contract”伪装成可工作的 repository-owned 写入，容易让 source cache、refresh target 状态和下游 dirty enqueue 的失败顺序漂移。

修复：

- `AssetProfileRepository.upsert_ready_profile(...)` 和 `upsert_status(...)` 统一走 `_run_repository_write(self.conn, commit, _write)`。
- `commit=True` 时先要求 callable `conn.transaction()`；缺失或 malformed transaction contract 会在任何 `asset_profiles` SQL 前失败，错误标记为 `asset_profile_repository_transaction_required`。
- `commit=False` caller-owned 路径保持不变；`asset_profile_refresh` service 写 ready/missing/error source cache 时显式传 `commit=False`，继续由 worker 外层 `RepositorySession.transaction` 覆盖 profile write、refresh-target reschedule/error、profile-current dirty enqueue。
- 架构 guard 要求两个 repository-owned mutation 全部使用 `_run_repository_write`，并禁止 `self.conn.commit()`、`nullcontext` 或 optional transaction probing 回流。

验证：

- GREEN：`uv run pytest tests/unit/domains/asset_market/test_asset_profile_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`6 passed`
- GREEN：`uv run pytest tests/unit/domains/asset_market/test_asset_profile_repository.py tests/unit/test_asset_profile_refresh_worker.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_token_profile_current_worker.py tests/unit/test_token_profile_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_refresh_target_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_requires_repository_session_source_query_contract -q`，`33 passed`
- GREEN：`uv run ruff check src/parallax/domains/asset_market/repositories/asset_profile_repository.py src/parallax/domains/asset_market/services/asset_profile_refresh.py tests/unit/domains/asset_market/test_asset_profile_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/asset_market/repositories/asset_profile_repository.py src/parallax/domains/asset_market/services/asset_profile_refresh.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3305 passed, 2 skipped in 33.51s`

## 根因七十六：CexTokenProfileRepository 仍把 CEX profile source cache 写成裸 commit

现象：

- Root63 已经把 `sync_cex_token_profiles(...)` 的 provider 读取和 DB 批写拆开：provider/client 读取在事务外，`cex_token_profiles` 写入在 callable connection transaction 内，并传 `commit=False`。
- 但仓储默认路径 `CexTokenProfileRepository.upsert_ready_profile_if_token_exists(...)` 仍在 `INSERT INTO cex_token_profiles ... RETURNING *` 后直接 `self.conn.commit()`。
- 这意味着正常 sync service 路径已经安全，但任何 repository-owned 调用、测试 fake 或未来维护命令仍可以绕过正式 connection transaction，先写 source cache，再用裸 commit 伪装事务边界。

根因：

- Root63 治理的是 service 层批写边界，没有把同一 source cache 的 repository-owned 默认写入纳入同一不变量。
- `cex_token_profiles` 与 `asset_profiles` 一样，不是 public serving row，却是 `TokenProfileCurrentWorker` exact-load 的持久 source cache；它会影响 public `token_profile_current` 的 profile/icon 选择。
- 成熟 Kappa/CQRS 中，source cache 只要被下游 current read model 消费，就必须有可证明的 PostgreSQL transaction contract。否则 service 层看似 KISS，仓储层却保留了第二套兼容提交语义。

修复：

- `CexTokenProfileRepository.upsert_ready_profile_if_token_exists(...)` 统一走 `_run_repository_write(self.conn, commit, _write)`。
- `commit=True` 时先要求 callable `conn.transaction()`；缺失或 malformed transaction contract 会在任何 `cex_token_profiles` SQL 前失败，错误标记为 `cex_token_profile_repository_transaction_required`。
- `commit=False` caller-owned 路径保持不变；`sync_cex_token_profiles(...)` 继续在自己的 service-level connection transaction 内批量写入。
- 架构 guard 要求 CEX profile source-cache repository 使用 `_run_repository_write`，并禁止 `self.conn.commit()`、`nullcontext` 或 optional transaction probing 回流。

验证：

- RED：`uv run pytest tests/unit/domains/asset_market/test_cex_token_profile_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_cex_token_profile_repository_uses_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露缺 transaction 仍先 SQL、正常 fake 仍走 `self.conn.commit()`、architecture guard 找不到 `_run_repository_write`。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/domains/asset_market/test_cex_token_profile_repository.py tests/unit/test_cex_token_profile_sync.py tests/unit/test_asset_market_sync.py tests/unit/test_token_profile_current_worker.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_cex_token_profile_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_market_sync_services_require_connection_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_requires_repository_session_source_query_contract -q`，`21 passed`
- GREEN：`uv run ruff check src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py tests/unit/domains/asset_market/test_cex_token_profile_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3308 passed, 2 skipped in 33.54s`

## 根因七十七：Token fact 基础仓储仍把 evidence/intent/lookup/resolution 写成裸 commit

现象：

- Root41/Root55 已经把 token intent rebuild 和 resolution reprocess 的服务入口切到 `RepositorySession.transaction`，并确认 `TokenIntentResolver` 不再暴露 commit flag。
- 但底层 `TokenEvidenceRepository.insert_many/insert`、`TokenIntentRepository.insert_many/insert`、`TokenIntentLookupRepository.replace_lookup_keys`、`IntentResolutionRepository.insert_resolution` 仍保留 `self.conn.commit()`。
- 其中 `IntentResolutionRepository.insert_resolution` 还会先执行 `pg_advisory_xact_lock(hashtextextended(...))`，如果没有真实 transaction，测试 fake/autocommit 路径会把“事务级序列化锁”伪装成有效边界。

根因：

- 前序治理修的是 ingest/rebuild/reprocess 的外层 session 事务，没有继续下探到 token facts 的 repository-owned 默认提交路径。
- `token_evidence`、`token_intents`、`token_intent_lookup_keys`、`token_intent_resolutions` 是 Token Radar、Search、Event token projection、Pulse evidence 的事实根；它们不是普通缓存，也不是可随意裸提交的 convenience rows。
- 成熟 Kappa/CQRS 中，事实写入可以由外层 Unit of Work 拥有，也可以由仓储默认入口拥有；但两者都必须进入同一种可证明的 PostgreSQL transaction contract。否则同一事实链会同时存在“正式 UoW”和“裸 commit 兼容路径”两套语义。
- `pg_advisory_xact_lock` 尤其暴露了这个根因：锁的正确性依赖 transaction 生命周期，而裸 `commit()` 不能证明调用前已经有事务。

修复：

- 四个 token fact 仓储默认写入口统一走 `_run_repository_write(self.conn, commit, _write)`。
- `commit=True` 时先要求 callable `conn.transaction()`；缺失或 malformed transaction contract 会在任何 token fact SQL 前失败，错误标记分别为 `token_evidence_repository_transaction_required`、`token_intent_repository_transaction_required`、`token_intent_lookup_repository_transaction_required`、`intent_resolution_repository_transaction_required`。
- `commit=False` caller-owned 路径保持不变；ingest、token intent rebuild、resolution reprocess 继续在 `unit_of_work` / `RepositorySession.transaction` 内组合写 token evidence、intent、lookup、resolution、discovery/source-dirty 状态。
- `IntentResolutionRepository.insert_resolution` 现在先进入 connection transaction，再执行 `pg_advisory_xact_lock` 和 current resolution supersede/upsert。
- 架构 guard 禁止四个仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露缺 transaction 仍先 SQL/manual commit、正常 fake 仍走 `self.conn.commit()`、architecture guard 找不到 `_run_repository_write`。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py tests/unit/test_intent_resolution_repository.py tests/unit/test_token_intent_rebuild_runtime.py tests/unit/test_token_resolution_refresh.py tests/unit/test_ingest_event_market_capture.py tests/unit/test_token_intent_resolver.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit -q`，`18 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py src/parallax/domains/token_intel/repositories/intent_resolution_repository.py tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py src/parallax/domains/token_intel/repositories/intent_resolution_repository.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因七十八：Queue Ops terminal retry 仍用 optional repository probe 判断能否重排队

现象：

- Queue Terminal 本体已经要求 `resolve_terminal_event(...)` 在 connection transaction 中 `SELECT ... FOR UPDATE` 并写 operator action。
- 但 `ops queue-resolve --action retry --execute` 绑定 retry transition 时，`queue_ops.py` 仍用 `getattr(repos, "discovery", None)`、`getattr(discovery, "enqueue_lookup_keys", None)`、`getattr(repos, "event_anchor_jobs", None)`、`getattr(repo, "retry_terminal_job_from_snapshot", None)`、`getattr(repos, "pulse_jobs", None)` 探测仓储形状。
- 缺仓储最终也会失败，但代码语义仍像“这个 terminal queue 的 retry capability 是可选能力”，而不是正式 repository/session contract。

根因：

- 前序治理把 terminal ledger 的 row lock / operator action 原子性修好了，但 retry transition 的目标队列仓储仍沿用旧 CLI/fake 兼容风格。
- 对 Kappa/CQRS 来说，terminal retry 不是普通 CLI 分支：它把已 terminalized 的控制面 row 重新投回 `token_discovery_dirty_lookup_keys`、`event_anchor_backfill_jobs` 或 `pulse_agent_jobs`，必须和 operator action 处在同一个 transaction 的状态推进里。
- 如果 retry 仓储被 optional probing 处理，测试 fake 可以少实现正式 session contract，代码阅读上也会保留“缺仓储是可兼容形状”的错误暗示。

修复：

- `_conn(repos)` 直接要求 `repos.signals.conn`，缺失时保留 `signals_connection_required` 错误。
- discovery/event-anchor/Pulse retry transition 直接访问正式仓储方法；缺 repository 或方法时抛已有 operator 错误码，并由 terminal transaction rollback。
- 新增 architecture guard 禁止 `queue_ops.py` 重新出现这些 retry 仓储/方法的 optional `getattr(..., None)` probe。
- 新增 unit 覆盖缺 discovery retry repository 时 terminal action rollback，不会留下半写 operator action。

验证：

- RED：`uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes -q` 初始失败，暴露 `queue_ops.py` 仍保留 optional repository/method probe。
- GREEN：`uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes tests/unit/test_cli_queue_ops.py -q`，`9 passed`
- GREEN：`uv run pytest tests/unit/test_cli_queue_ops.py tests/unit/test_queue_terminal.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_terminal_operator_resolution_requires_transaction_without_nullcontext tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes -q`，`22 passed`
- GREEN：`uv run ruff check src/parallax/app/surfaces/cli/commands/queue_ops.py tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/app/surfaces/cli/commands/queue_ops.py`
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因七十九：TokenRadarRepository 默认 publication/current-row 写入仍可裸 commit

现象：

- Root43/Root60 已经把 `TokenRadarProjection` dirty processing 改成一个显式 connection transaction，worker 路径用 `commit=False` 组合 source-edge、target-feature、rank publication、dirty done/error。
- 但底层 `TokenRadarRepository.publish_current_generation(...)`、`upsert_target_feature(...)`、`delete_target_feature(...)`、`prune_target_features(...)`、`upsert_first_seen_batch(...)`、`mark_publication_failed(...)` 默认 `commit=True` 路径仍直接 `self.conn.commit()`。
- 更危险的是 `publish_current_generation(...)` 一进来就执行 `pg_advisory_xact_lock(...)`；如果没有真实 transaction，fake/autocommit 路径会让“事务级 publication serialization”看起来存在。

根因：

- 前序治理保证了 worker/service 正常投影路径的 outer transaction，但没有把 `TokenRadarRepository` 这个 serving read-model 仓储的 repository-owned 默认入口一起治理掉。
- `token_radar_current_rows` 和 `token_radar_publication_state` 是 Token Radar 在线读模型；`token_radar_target_features` 与 `token_radar_target_first_seen` 虽然是 projection-private/cache，但决定后续 rank-set 的输入和 first-seen 语义。它们不是可以裸提交的普通缓存。
- 成熟 Kappa/CQRS 里，current rows、publication state、last-failure state、projection-private cache 必须共享可证明的 PostgreSQL transaction boundary；否则同一 read model 既有正式 projection transaction，又保留 repository-owned 裸 commit 第二入口。

修复：

- `TokenRadarRepository` 新增 `_transaction(conn)`，缺 callable `conn.transaction` 时抛 `token_radar_repository_transaction_required`。
- 默认 `commit=True` 的 publication、target-feature、first-seen、failed-publication 写入先进入 `_transaction(self.conn)`，再调用同一方法的 `commit=False` 路径。
- `publish_current_generation(...)` 因而会先进入 connection transaction，再执行 `pg_advisory_xact_lock`、current rows diff/delete/upsert、first-seen upsert、publication state upsert 和 callback。
- worker projection 路径保持 `commit=False`，继续由外层 dirty-processing transaction 拥有提交。
- architecture guard 禁止仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_repository.py::test_token_radar_repository_mutations_require_connection_transaction_before_sql_when_committing tests/unit/test_token_radar_repository.py::test_token_radar_repository_commit_owned_publication_uses_connection_transaction_without_manual_commit tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_repository_uses_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露缺 transaction 先跑 advisory-lock SQL、正常 fake 走 `self.conn.commit()`、architecture guard 找不到 `token_radar_repository_transaction_required`。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/test_token_radar_repository.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_token_radar_publication_state_hard_cut.py -q`，`137 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/repositories/token_radar_repository.py tests/unit/test_token_radar_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十：raw_frames / event_entities 入口仓储仍保留裸提交旁路

现象：

- `IngestService.commit_prepared_event(...)` 已经把 `events`、`event_entities`、token evidence / intent / resolution、registry / identity evidence、dirty queue 等写入放进同一个 `EvidenceRepository.unit_of_work`。
- 但 `EvidenceRepository.insert_raw_frame(...)` 仍直接写 `raw_frames` 后 `self.conn.commit()`；`EntityRepository.insert_event_entities(..., commit=True)` 也保留裸 `self.conn.commit()` 默认路径。
- collector 的 `_PooledIngestStore.insert_raw_frame(...)` 本身已经打开 `worker_session("collector")`，但仓储仍绕过正式 transaction helper，这让输入观察和事件实体事实边有第二套提交语义。

根因：

- 历史上 raw frame 被当作“只是 provider 输入缓存”，event entity 被当作 ingest 的附属明细，因此默认仓储写入没有和后续 token fact / identity fact 仓储一起纳入 connection-transaction hard cut。
- 在 Kappa/CQRS 里，`raw_frames` 虽然不是业务真相，但它是输入观察审计链；`event_entities` 是从事件事实派生出的可查询事实边。两者都不能通过 fake/autocommit 裸提交绕开 PostgreSQL 事务边界。
- 只治理 token evidence / intent / resolution 会留下不对称入口：完整 ingest 是单 UoW，但 raw-frame 入口和 event-entity 默认仓储仍可自己提交，测试 fake 也能继续少实现正式事务合同。

修复：

- `EvidenceRepository.insert_raw_frame(..., commit=True)` 改为先进入 `_run_repository_write(self.conn, commit, ...)`，缺 callable `conn.transaction` 时抛 `evidence_repository_transaction_required`，且在 transaction 进入前不执行 `raw_frames` SQL。
- `EntityRepository.insert_event_entities(..., commit=True)` 同样改为 connection transaction helper，缺事务合同抛 `entity_repository_transaction_required`。
- `commit=False` 路径保持 caller-owned，供 `IngestService.commit_prepared_event(...)` 在 `EvidenceRepository.unit_of_work` 内组合完整事件事实链。
- architecture guard 禁止这两个仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/domains/evidence/test_evidence_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_evidence_ingest_repositories_use_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露 raw-frame 路径裸 `self.conn.commit()`、正常 fake 走 manual commit、architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/domains/evidence/test_evidence_repositories.py tests/unit/test_collector_service.py tests/unit/test_ingest_event_market_capture.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/unit/test_token_intent_rebuild_runtime.py tests/unit/test_event_token_projection.py -q`，`18 passed`
- GREEN：`uv run ruff check src/parallax/domains/evidence/repositories/evidence_repository.py src/parallax/domains/evidence/repositories/entity_repository.py tests/unit/domains/evidence/test_evidence_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/evidence/repositories/evidence_repository.py src/parallax/domains/evidence/repositories/entity_repository.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十一：ProjectionRepository 投影控制面仍保留裸提交路径

现象：

- `TokenRadarProjection.refresh_rank_set(...)` 已经把 stale-run cleanup、run start、publication、offset advance、run finish 放进一个显式 connection transaction，并以 `commit=False` 调用 `ProjectionRepository`。
- 但 `ProjectionRepository` 默认 `commit=True` 的 `advance_offset(...)`、`start_run(...)`、`mark_stale_running_runs(...)`、`finish_run(...)`、`enqueue_dirty_range(...)`、`claim_dirty_ranges(...)` 仍直接 `self.conn.commit()`。
- 这些表不是普通日志：`projection_offsets` 决定投影 frontier，`projection_runs` 是投影审计/运行状态，`projection_dirty_ranges` 是控制面队列。裸提交会保留第二套投影控制面写入语义。

根因：

- 前序治理关注了 Token Radar rank publication 和 dirty target processing，但 `ProjectionRepository` 作为通用投影控制面仓储被留在旧仓储模式里。
- 成熟 Kappa/CQRS 里，投影控制面和 serving read model 一样需要可证明的事务边界：claim / run ledger / offset 必须要么共同处于外层投影 transaction，要么在 repository-owned 写入时自己先进入真实 PostgreSQL transaction。
- 保留 `self.conn.commit()` 会让 fake/autocommit 环境继续掩盖“claim_dirty_ranges 或 offset advance 没有事务”的事实，也让 ops/CLI 入口可以绕过 projection worker 的正式边界。

修复：

- `ProjectionRepository` 新增 connection transaction helper，缺 callable `conn.transaction` 时抛 `projection_repository_transaction_required`。
- 六个 repository-owned 写入口统一走 `_run_repository_write(self.conn, commit, ...)`；`commit=True` 先进入 transaction 再执行 SQL。
- `commit=False` 路径保持不变，供 Token Radar rank publication 的显式 projection transaction 组合 stale cleanup、run ledger、offset 和 dirty range 状态。
- architecture guard 禁止该仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/domains/token_intel/test_projection_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_projection_repository_uses_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露 offset 写入裸 `self.conn.commit()`、正常 fake 走 manual commit、architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/domains/token_intel/test_projection_repository.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_ops_diagnostics.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_projection_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_token_radar_publication_state_hard_cut.py -q`，`119 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/repositories/projection_repository.py tests/unit/domains/token_intel/test_projection_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/repositories/projection_repository.py`
- GREEN：production residual scan had no matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十二：Token Radar rank-source 边写入把提交能力藏在 Query 层

现象：

- `TokenRadarProjection.rebuild_dirty_targets(...)` 已经把 source dirty claim、rank-source edge population、target feature 写入、rank publication、dirty done/error terminalization 放进一个显式 connection transaction，并以 `commit=False` 调用 rank-source 仓储。
- 但 `TokenRadarRankSourceRepository.populate_edges_for_event_ids(...)` / `populate_edges_for_targets(...)` / `prune_edges(...)` 只是薄代理，默认 `commit=True` 会继续委托 `TokenRadarRankSourceQuery` 执行写 SQL 后 `self.conn.commit()`。
- 这让 `queries/token_radar_rank_source_query.py` 同时承担 read query、projection-private edge mutation、commit owner 三个角色；缺少 connection transaction 的 fake/autocommit 连接仍能到达 `token_radar_rank_source_events` SQL。

根因：

- 前序治理把 Token Radar dirty projection 的外层事务补齐了，但没有切断 rank-source query 对提交的所有权，导致“运行时路径安全、默认仓储路径仍旧裸提交”的双语义继续存在。
- 成熟 CQRS 分层里，query 可以封装复杂 SQL shape，但提交边界必须由 repository / session / worker 这类写所有者控制。否则 review 时看到 `commit=False` 会误以为调用者拥有事务，但默认路径仍可绕过正式事务 helper。
- `token_radar_rank_source_events` 虽然是 projection-private edge 表，不是在线 leaderboard 表，但它直接决定后续 `token_radar_target_features` 和 current rows 的输入集合；edge population / prune 不能通过 query 层裸提交形成第二套投影写入协议。

修复：

- `TokenRadarRankSourceRepository` 新增 connection transaction helper，缺 callable `conn.transaction` 时抛 `token_radar_rank_source_repository_transaction_required`，且在事务进入前不执行 edge SQL。
- 三个 repository-owned 写入口统一走 `_run_repository_write(self.conn, commit, ...)`；`commit=True` 先进入 transaction 再调用 query SQL，`commit=False` 保持 caller-owned 供 Token Radar dirty projection 的显式事务使用。
- `TokenRadarRankSourceQuery` 移除写方法的 `commit` 参数和 `self.conn.commit()`，变成 SQL execution helper，不再拥有提交语义。
- architecture guard 禁止 query 层重新出现 `commit: bool`、`commit=True`、`if commit:` 或 `self.conn.commit()`，并禁止 repository 回退到 `self.conn.commit()` / `nullcontext` / optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/domains/token_intel/test_token_radar_rank_source_query.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_rank_source_repository_owns_write_transactions_without_query_commit_fallback -q` 初始 `7 failed`，暴露 repository 默认路径仍委托 query 裸 `self.conn.commit()`，缺事务 fake 可到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `13 passed`
- GREEN：`uv run pytest tests/unit/domains/token_intel/test_token_radar_rank_source_query.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_rank_source_repository_owns_write_transactions_without_query_commit_fallback tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_token_radar_sql_surface_inventory_contract.py -q`，`122 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py tests/unit/domains/token_intel/test_token_radar_rank_source_query.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- GREEN：query residual scan had no query-owned commit matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十三：TokenFactorEvaluationRepository 的评分评估读模型仍有单条裸提交旁路

现象：

- `token_score_evaluations` 是 Token Radar 的派生诊断读模型，manifest 里按 `(horizon, window, scope, score_version, bucket_label)` 定义当前身份。
- 批量 `upsert_score_evaluations(...)` 已经使用 `with self.conn.transaction()` 包住多条写入，但单条 `upsert_score_evaluation(...)` 默认 `commit=True` 仍然在 SQL 后直接 `self.conn.commit()`。
- 这导致同一张读模型表存在两套写入语义：批量路径有显式 connection transaction，单条默认路径可以在 fake/autocommit 连接上无事务执行 SQL 后裸提交。

根因：

- 前序治理集中在 Token Radar serving rows、rank-source edges 和 projection control-plane，没有把评分评估表当成同等需要治理的 read model writer。
- 成熟 Kappa/CQRS 里，即便是 diagnostics/evaluation read model，也必须具备可重放、单 writer、可审计的写入边界。它不能因为“不直接服务 leaderboard”就保留旧仓储模式。
- 单条 upsert 和批量 upsert 事务语义分裂，会在后续调用点增加隐性风险：reviewer 看到批量路径安全，容易忽略默认单条路径仍可绕过 repository transaction helper。

修复：

- `TokenFactorEvaluationRepository` 新增 connection transaction helper，缺 callable `conn.transaction` 时抛 `token_factor_evaluation_repository_transaction_required`。
- 单条和批量 `token_score_evaluations` upsert 都统一走 `_run_repository_write(self.conn, commit, ...)`；`commit=True` 先进入 transaction 再执行 SQL。
- 批量 upsert 内部逐条调用 `upsert_score_evaluation(..., commit=False)`，保持 per-row 写入 caller-owned，避免嵌套提交。
- architecture guard 禁止该仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- GREEN：`uv run pytest tests/unit/test_token_factor_evaluation.py::test_evaluation_repository_upsert_requires_connection_transaction_before_sql_when_committing tests/unit/test_token_factor_evaluation.py::test_evaluation_repository_commit_owned_upsert_uses_connection_transaction_without_manual_commit tests/unit/test_token_factor_evaluation.py::test_evaluation_repository_batch_upsert_uses_transaction_once tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_factor_evaluation_repository_uses_connection_transaction_without_manual_commit_fallback -q`，`4 passed`
- GREEN：`uv run pytest tests/unit/test_token_factor_evaluation.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_factor_evaluation_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_token_radar_publication_state_hard_cut.py -q`，`113 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/repositories/token_factor_evaluation_repository.py tests/unit/test_token_factor_evaluation.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/repositories/token_factor_evaluation_repository.py`
- GREEN：production residual scan had no naked commit or optional transaction fallback matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十四：SignalRepository 的 watched-account alert 表被读路径消费，却保留默认裸提交

现象：

- `account_token_alerts` 仍被 `/api/account-alerts`、recent event alerts、WebSocket replay/live payload、notification rules 和 CLI read-model 命令消费。
- 写入来自 evidence ingest：`IngestService._insert_token_alerts(...)` 在 deterministic token resolution 和 first-seen 检查之后，以 `commit=False` 调用 `SignalRepository.insert_account_token_alert(...)`。
- 但 `SignalRepository.insert_account_token_alert(...)` 的默认 `commit=True` 路径会在 SQL 后直接 `self.conn.commit()`，缺事务能力的连接仍可先到达 `account_token_alerts` 写 SQL。

根因：

- 这张表不是 worker manifest 中的 current read model，所以前序 worker/read-model 治理没有把它纳入同等的事务边界审计。
- 但从产品链路看，它是持久化 alert/read path 输入：notification rules 和 account-alert API 都依赖它。只要它仍是 PostgreSQL truth/read input，就不能用“不是 worker current row”来保留旧裸提交模式。
- 成熟 Kappa/CQRS 中，ingest 派生出的辅助 alert 表也必须遵守同一原则：外层 ingest unit of work 可以 caller-owned，仓储默认写入则必须自己先进入真实 connection transaction。

修复：

- `SignalRepository` 新增 connection transaction helper，缺 callable `conn.transaction` 时抛 `signal_repository_transaction_required`。
- `insert_account_token_alert(...)` 的 repository-owned 默认路径统一走 `_run_repository_write(self.conn, commit, ...)`，先进入 transaction 再执行 `account_token_alerts` SQL。
- `commit=False` 路径保持 caller-owned，供 evidence ingest 在 `EvidenceRepository.unit_of_work` 内组合事件、实体、token facts、resolution、alert 和 downstream dirty enqueue。
- architecture guard 禁止该仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing。

验证：

- RED：`uv run pytest tests/unit/domains/token_intel/test_signal_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_signal_repository_alert_writes_use_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed`，暴露 watched-account alert 插入仍在缺事务 fake 上到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/domains/token_intel/test_signal_repository.py tests/unit/test_ingest_event_market_capture.py tests/unit/test_public_event_token_payloads.py tests/unit/test_notification_rules.py tests/unit/test_account_quality_service.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_signal_repository_alert_writes_use_connection_transaction_without_manual_commit_fallback -q`，`53 passed, 1 skipped`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/repositories/signal_repository.py tests/unit/domains/token_intel/test_signal_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/repositories/signal_repository.py`
- GREEN：production residual scan had no naked commit or optional transaction fallback matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十五：AccountQualityRepository 默认写入仍保留裸提交，弱化 ops-only 读模型边界

现象：

- Account Quality 已经拆成明确读写边界：`AccountQualityService` 只读，`AccountQualityBackfillService` 负责 ops backfill，并在外层 connection transaction 里以 `commit=False` 写 `account_profiles`、`account_token_call_stats`、`account_quality_snapshots`。
- 但底层 `AccountQualityRepository.upsert_profile(...)`、`upsert_directory_entry(...)`、`upsert_token_call_stat(...)`、`insert_quality_snapshot(...)` 默认 `commit=True` 仍直接 `self.conn.commit()`。
- 这意味着同一批 account-quality 读模型表存在两套提交语义：正式 backfill / directory sync 是 caller-owned transaction，默认仓储入口却仍能在 fake/autocommit 连接上先写 SQL 再裸提交。

根因：

- 前序 Root58 只治理了 `AccountQualityBackfillService` 的外层事务，没有同步切断仓储默认入口的旧兼容模式。
- ops-only 不等于低一致性。`account_profiles` 会装饰 `/api/recent`、`/events/by-ids`，也支撑 `/api/account-quality`、`/api/account-alerts` 和 notification 规则读取；它们是产品读路径状态，不是可以随意裸提交的临时缓存。
- 成熟 Kappa/CQRS 架构里，读模型是否由常驻 worker 维护不是关键，关键是每个 derived state writer 都必须有单一、可审计、可回放的事务边界。保留仓储默认裸提交会让后续 ops 命令或测试 fake 绕过正式边界。

修复：

- `AccountQualityRepository` 新增 connection transaction helper，缺 callable `conn.transaction` 时抛 `account_quality_repository_transaction_required`，且在事务进入前不执行 account-quality 写 SQL。
- profile、directory entry、token call stat、quality snapshot 四类 repository-owned 写入口统一走 `_run_repository_write(self.conn, commit, ...)`；`commit=True` 先进入 transaction，`commit=False` 保留给 backfill/directory sync 的外层事务。
- architecture guard 禁止该仓储重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing，并要求四个写入口都走 transaction helper。

验证：

- RED：`uv run pytest tests/unit/test_account_quality_repository.py::test_account_quality_repository_writes_require_connection_transaction_before_sql_when_committing tests/unit/test_account_quality_repository.py::test_account_quality_repository_commit_owned_writes_use_connection_transaction_without_manual_commit tests/unit/test_account_quality_repository.py::test_account_quality_repository_caller_owned_writes_do_not_open_inner_transaction tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_repository_writes_use_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed, 1 passed`，暴露缺事务 fake 仍可到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/test_account_quality_repository.py tests/unit/test_account_quality_service.py tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_read_model_service_has_no_backfill_write_path tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_public_read_paths_use_read_service_not_repository tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_interface_exposes_read_services_only tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_architecture_declares_read_write_boundary tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_backfill_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_repository_writes_use_connection_transaction_without_manual_commit_fallback -q`，`12 passed, 1 skipped`
- GREEN：`uv run ruff check src/parallax/domains/account_quality/repositories/account_quality_repository.py tests/unit/test_account_quality_repository.py tests/architecture/test_api_read_paths_provider_free.py`
- GREEN：`uv run mypy src/parallax/domains/account_quality/repositories/account_quality_repository.py`
- GREEN：production residual scan had no naked commit or optional transaction fallback matches
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十六：NotificationRepository 默认通知事实/已读标记/投递 enqueue 仍有裸提交旁路

现象：

- `NotificationWorker` 已经被治理为在 worker-session `unit_of_work` 内写 `notifications` 和 `notification_deliveries`，并且聚合高信号通知必须用 `enqueue_or_requeue_delivery` 重新激活 failed/dead external delivery。
- 但 `NotificationRepository.insert_notification_with_outcome(...)`、`mark_read(...)`、`mark_author_read(...)`、`enqueue_delivery(...)`、`enqueue_or_requeue_delivery(...)` 的 repository-owned 默认路径仍可在 SQL 后直接 `self.conn.commit()`，或只在 delivery 子路径上有不完整的事务 helper。
- 这让通知域存在两套提交协议：worker 路径看起来已经符合 UoW，API 已读标记和直接仓储默认入口却仍能在 fake/autocommit 连接上先写 `notifications`、`notification_reads` 或 `notification_deliveries` 后裸提交。

根因：

- 前序治理把焦点放在常驻 worker 的 `unit_of_work` 和 delivery worker 的 session transaction，遗漏了同一仓储对 API/read-marker/direct caller 暴露的默认写入口。
- 成熟 Kappa/CQRS 中，`notifications` 是事实/产品通知 ledger，`notification_reads` 是用户读状态，`notification_deliveries` 是外部 side-effect 控制面；三者虽然用途不同，但只要 repository owns commit，就必须先进入可审计的 PostgreSQL transaction。
- 如果 worker 路径使用 `commit=False` 安全，而默认仓储路径继续裸提交，后续 ops、API 或测试 fake 会绕过正式边界，导致 review 时误判“通知域已经事务化”。

修复：

- `NotificationRepository` 新增 notification 和 delivery 两类 connection transaction helper：缺 callable `conn.transaction` 时分别抛 `notification_repository_transaction_required` 或 `notification_delivery_repository_transaction_required`。
- 通知插入/聚合、已读标记、作者已读标记统一走 `_run_repository_write(self.conn, commit, ...)`；repository-owned 路径先进入 transaction 再执行 SQL，`commit=False` 保留给 worker-session UoW。
- delivery enqueue/requeue 统一走 `_run_delivery_write(self.conn, commit, ...)`，确保 `notification_deliveries` 插入、requeue 和返回行读取在 repository-owned transaction 内完成。
- architecture guard 禁止 `notification_repository.py` 重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing，并要求插入、已读、enqueue/requeue 入口都走 transaction helper。

验证：

- RED：`uv run pytest tests/unit/test_notification_worker_runtime.py::test_notification_repository_writes_require_connection_transaction_before_sql_when_committing tests/unit/test_notification_worker_runtime.py::test_notification_repository_commit_owned_writes_use_connection_transaction_without_manual_commit tests/unit/test_notification_worker_runtime.py::test_notification_repository_caller_owned_writes_do_not_open_inner_transaction tests/architecture/test_notifications_hard_cut.py::test_notification_repository_writes_use_connection_transactions_without_manual_commit_fallback -q` 初始 `3 failed, 1 passed`，暴露缺事务 fake 仍可到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/test_notification_worker_runtime.py tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py -q`，`66 passed`
- GREEN：`uv run ruff check src/parallax/domains/notifications/repositories/notification_repository.py tests/unit/test_notification_worker_runtime.py tests/architecture/test_notifications_hard_cut.py`
- GREEN：`uv run mypy src/parallax/domains/notifications/repositories/notification_repository.py`
- GREEN：production residual scan had no naked commit, optional transaction fallback, or `nullcontext` matches in `notification_repository.py`
- GREEN：latest non-integration `make check` passed with `3359 passed, 2 skipped in 33.03s`

## 根因八十七：NewsRepository 默认事实/投影写入口仍保留裸提交，绕过 News worker session 事务边界

现象：

- `news_fetch`、`news_item_process`、`news_item_brief`、`news_page_projection` 和 `news_source_quality_projection` 已经被治理为使用 `RepositorySession.transaction`，worker 路径也会以 `commit=False` 调用仓储。
- 但 `NewsRepository` 的默认 `commit=True` 路径仍在大量写入口末尾直接 `self.conn.commit()`：source reconcile/claim、fetch run 状态、provider item、canonical item、实体/mention/fact、processed/retry state、agent run/current brief、source-quality rows、page rows 等都存在第二套提交协议。
- `upsert_canonical_news_item(...)` 还保留了方法内部 autocommit 分支：当连接处于 autocommit 时单独开 `self.conn.transaction()` 并递归调用自身。这让事务策略同时存在于外层 worker session、仓储方法尾部和单方法特例里。

根因：

- 前序治理修好了 runtime worker 的外层事务边界，但没有同步审计 repository-owned 默认入口。结果是 worker 路径看起来符合 Kappa/CQRS，API、ops、直接仓储调用或测试 fake 仍可能绕过正式 session contract。
- 成熟 Kappa/CQRS 不是只要求“常驻 worker 有事务”，而是要求每一个 material fact、control-plane row 和 rebuildable read model 的写所有者都只有一个可审计事务协议。`NewsRepository` 同时写事实层和读模型层，如果默认入口裸提交，就等于保留了 News 域的第二 writer protocol。
- 这种问题还会误导测试：fake connection 只要提供 `execute()` 和 `commit()` 就能通过旧测试，掩盖真实 PostgreSQL 事务、锁、claim 和 dirty-target 状态应该一起成功或一起失败的约束。

修复：

- `NewsRepository` 新增统一 `_news_repository_transaction(...)` 和 `_news_repository_write(...)`。
- repository-owned 默认 `commit=True` 先要求 callable `conn.transaction`，缺失时抛 `news_repository_transaction_required`，并且在进入事务前不执行 SQL。
- 32 个默认写入口统一加 decorator；`commit=False` 保持 caller-owned，供 News workers 的 `RepositorySession.transaction` 组合多表写入。
- 删除 `news_repository.py` 中所有裸 `self.conn.commit()`，并删除 `upsert_canonical_news_item(...)` 的方法内 autocommit 特例。
- architecture guard 禁止 `self.conn.commit()`、`nullcontext`、optional transaction probing 回到 `NewsRepository`，并要求 source/fetch/provider/canonical/fact/agent/source-quality/page-row 写入口都有统一 decorator。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_writes_require_connection_transaction_before_sql_when_committing tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_commit_owned_writes_use_connection_transaction_without_manual_commit tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_caller_owned_writes_do_not_open_inner_transaction tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_writes_use_connection_transaction_without_manual_commit_fallback -q` 初始 `3 failed, 1 passed`，暴露缺事务 fake 仍可到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q`，`132 passed`
- GREEN：`uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py`
- GREEN：`uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py`
- GREEN：production residual scan had no naked commit, optional transaction fallback, or `nullcontext` matches in `news_repository.py`

## 根因八十八：Macro projection dirty-target 默认 claim/done/error 仍保留裸提交

现象：

- `MacroViewProjectionWorker` 已经被治理为在 `RepositorySession.transaction` 内 claim `macro_projection_dirty_targets`、刷新 `macro_observation_series_rows`、写 `macro_view_snapshots`，并在同一事务内 mark done/error。
- 但 `MacroIntelRepository.claim_macro_projection_dirty_targets(...)`、`mark_macro_projection_dirty_targets_done(...)`、`mark_macro_projection_dirty_targets_error(...)` 的 repository-owned 默认路径仍在执行 `macro_projection_dirty_targets` SQL 后直接 `self.conn.commit()`。
- 这让 Macro projection 控制面存在两套提交协议：worker 路径看起来已经遵循 session transaction，直接仓储调用或测试 fake 仍能用 `execute()+commit()` 通过旧路径完成 claim/delete/retry。

根因：

- 前序 Root42/Root56 重点修了 Macro projection worker 的外层事务和 post-commit wake，Root38 修了 observation-series current rows 的 connection transaction，但没有同步审计同一仓储里的 dirty-target 默认入口。
- `macro_projection_dirty_targets` 不是普通临时队列，而是 Kappa/CQRS 的投影控制面：claim 租约、attempt count、done 删除和 error retry 决定投影是否会重放。如果这些状态转换可以绕过正式事务，就无法证明“claim + projection write + done/error”是一个可审计状态机。
- PostgreSQL 层面，`FOR UPDATE SKIP LOCKED` 的 claim 语义依赖事务边界。裸提交/无事务 fake 会让测试误以为 queue claim 安全，但实际锁生命周期、attempt 递增和 terminal state 不能被统一证明。

修复：

- `MacroIntelRepository` 新增 `_macro_projection_dirty_target_transaction_context(...)`，缺 callable `conn.transaction` 时抛 `macro_projection_dirty_target_transaction_required`，并在事务进入前不执行 dirty-target SQL。
- claim/done/error 默认 `commit=True` 先进入连接事务，再以 `commit=False` 复用同一 SQL 路径；空输入仍直接返回 0，不打开无意义事务。
- `MacroViewProjectionWorker` 保持 caller-owned `commit=False`，由外层 `RepositorySession.transaction` 统一提交。
- architecture guard 禁止 dirty-target claim/done/error 段落重新出现 `self.conn.commit()`、`nullcontext` 或 optional transaction probing，并要求显式 transaction helper。

验证：

- RED：`uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_target_default_writes_require_connection_transaction_before_sql tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_target_default_writes_use_connection_transaction_without_manual_commit tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_target_caller_owned_writes_do_not_open_inner_transaction tests/architecture/test_macro_no_compatibility_contract.py::test_macro_projection_dirty_target_writes_require_connection_transaction_without_manual_commit -q` 初始 `3 failed, 1 passed`，暴露缺事务 fake 仍可到达 SQL/manual commit，architecture guard 找不到 transaction helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_generation_swap.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/architecture/test_macro_no_compatibility_contract.py -q`，`70 passed`
- GREEN：`uv run ruff check src/parallax/domains/macro_intel/repositories/macro_intel_repository.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/architecture/test_macro_no_compatibility_contract.py`
- GREEN：`uv run mypy src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- GREEN：business-domain production residual scan had no naked commit, optional transaction fallback, or `nullcontext` matches.

## 根因八十九：TokenRadarProjection 下游 dirty-target fan-out 仍保留 optional repository probe

现象：

- Token Radar rank-set current rows 变化后，会继续向 Pulse trigger、Narrative Admission、Token Profile Current、Token Capture Tier 四条下游 dirty-target/control-plane 队列 enqueue。
- 前序治理已经把 Token Radar 的 source dirty、target dirty、rank publication、serving publication、projection control-plane 和 score-evaluation 写路径都收紧为事务合同，但这个下游 fan-out 仍使用 `getattr(self.repos, "...", None)` 先探测仓库，再用自定义 `RuntimeError` 报 missing repo。
- 这虽然不是静默跳过，但仍然保留了第二套 repository shape 兼容协议：测试 fake 可以只缺属性却得到业务层 RuntimeError，而不是暴露为 `RepositorySession` wiring 不完整。

根因：

- 修复焦点长期放在“写 SQL 是否裸 commit”和“worker 外层是否有事务”上，遗漏了投影事务尾部的跨读模型 dirty-target fan-out。
- 成熟 Kappa/CQRS 里，下游 dirty-target enqueue 是当前 projection transaction 的一部分：rank-set 发布、目标特征刷新、下游脏队列和 dirty done/error 必须被视为同一个可重放状态机。
- 如果下游仓库可以被 optional probe 包住，即使最后抛错，也会让架构表达变成“这个下游也许不存在”。这和单 writer、固定 runtime wiring、fail-closed 的设计思想冲突。

修复：

- `TokenRadarProjection` 改为直接访问 `self.repos.pulse_trigger_dirty_targets`、`self.repos.narrative_admission_dirty_targets`、`self.repos.token_profile_current_dirty_targets`、`self.repos.token_capture_tier_dirty_targets`。
- 删除四个 `getattr(self.repos, "...", None)` probe 和对应 `if repo is None` 自定义分支。
- architecture guard 明确禁止这些 optional probe 回来，并要求四个直接 session 属性。
- 单元测试要求缺少正式 repository 属性时抛 `AttributeError`，把问题定位为 session wiring 失败，而不是领域层可选功能。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_runtime_dirty_target_enqueues_require_formal_repository_contracts tests/architecture/test_token_radar_source_width_contract.py::test_token_radar_downstream_dirty_target_repositories_are_required_without_optional_probes -q` 初始 `5 failed`，四个单元 case 得到旧的自定义 RuntimeError，architecture guard 捕获 optional probe。
- GREEN：同一命令修复后 `5 passed`
- GREEN：`uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/architecture/test_token_radar_source_width_contract.py tests/architecture/test_token_radar_publication_state_hard_cut.py -q`，`117 passed`
- GREEN：`uv run ruff check src/parallax/domains/token_intel/services/token_radar_projection.py tests/unit/test_token_radar_projection.py tests/architecture/test_token_radar_source_width_contract.py`
- GREEN：`uv run mypy src/parallax/domains/token_intel/services/token_radar_projection.py`
- GREEN：residual scan 只在 architecture guard 的 forbidden-token 列表里保留旧 optional probe 字符串。

## 根因九十：PulseEvidenceBuilder sealed packet source repository 仍把缺仓库方法当空证据

现象：

- `PulseEvidenceBuilder` 在 LLM 调用前构造 sealed `PulseEvidencePacket`，它读取 source events、enriched events、market facts、identity facts 和 current discussion digest，并把这些事实压成 `allowed_evidence_refs`、quality metrics、data gaps 和 source fingerprints。
- 旧实现把 `list_source_events` / `list_enriched_events` 包在 `_list_repo(..., default=())` 里；如果 source repository 没有这个方法，就返回空列表。
- `list_market_facts` 和 `get_current_discussion_digest` 也通过 `getattr(self._sources, "...", None)` optional probe；方法缺失时分别返回空 market facts 或 `None` digest。
- 这会把 repository/session wiring 错误伪装成“没有证据”或“没有 digest”。LLM 看到的是一个合法但贫血的 sealed packet，审计上却无法区分真实数据缺口和仓库合约缺失。

根因：

- 前序 Pulse 治理集中在 candidate job service 的 session transaction、worker dirty-trigger transaction、Pulse write repositories 的 connection transaction，以及 public read/visibility 合约，没有把 evidence packet builder 当成 agent 输入事实边界来审计。
- 成熟 Kappa/CQRS 里，LLM 不直接取事实；agent 只能消费由 PostgreSQL 持久事实组装出的 sealed packet。因此 packet builder 的 source repository 方法是正式读侧合约，缺方法是接线失败，不是业务数据为空。
- 空 rows 可以表达“事实不存在或过期”，但只能发生在正式仓库方法被调用以后。用 optional method probe 直接吞掉缺方法，会削弱单 writer、固定 runtime wiring 和 fail-closed 的设计思想。

修复：

- `PulseEvidenceBuilder.build(...)` 直接调用 `self._sources.list_source_events(...)`、`list_enriched_events(...)`、`list_identity_facts(...)`。
- `_list_market_facts(...)` 直接调用 `self._sources.list_market_facts(...)`，缺方法立即暴露为 `AttributeError`。
- `_current_discussion_digest(...)` 在 context target/window/scope 字段齐备时直接调用 `self._sources.get_current_discussion_digest(...)`；返回 `None` 仅表示正式仓库查询后没有 current digest。
- 删除 `_list_repo` 和 source repository optional probes；测试 fake 也必须实现完整 evidence source repository 合约，默认 `None` digest 只代表数据缺口。
- architecture guard 禁止 `_list_repo`、`getattr(self._sources, "...", None)` 和 `return list(default)` 兼容路径回归，并要求五个正式 source repository 调用存在。

验证：

- RED：`uv run pytest tests/unit/test_pulse_evidence_packet_builder.py::test_builder_requires_formal_evidence_source_repository_contracts tests/architecture/test_pulse_no_compat.py::test_pulse_evidence_builder_requires_source_repository_contracts_without_optional_probes -q` 初始 `6 failed`，五个缺方法 case 未抛 `AttributeError`，architecture guard 捕获 optional probe。
- GREEN：同一命令修复后 `6 passed`
- GREEN：`uv run pytest tests/unit/test_pulse_evidence_packet_builder.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_candidate_worker.py tests/architecture/test_pulse_no_compat.py -q --tb=short`，`104 passed`
- GREEN：`uv run ruff check src/parallax/domains/pulse_lab/services/evidence_packet_builder.py tests/unit/test_pulse_evidence_packet_builder.py tests/unit/test_pulse_candidate_worker.py tests/architecture/test_pulse_no_compat.py`
- GREEN：`uv run mypy src/parallax/domains/pulse_lab/services/evidence_packet_builder.py`
- GREEN：residual scan 只在 architecture guard 的 forbidden-token 列表里保留旧 optional probe 字符串。

## 根因九十一：Signal Pulse public health 绕过正式读仓库合约探测 repository.conn

现象：

- `SignalPulseService.pulse(...)` 是 `/api/signal-lab/pulse` 的公共读模型服务，主体数据来自 `PulseReadRepository.list_candidates(...)` 和 `pulse_summary(...)`。
- 但 freshness health 旧实现没有调用正式仓库方法，而是在服务层执行 `getattr(repository, "conn", None)`，再直接实例化 `PulseFreshnessHealthService(conn)`。
- 如果测试 fake、未来代理仓库或 route/session wiring 缺少 `conn`，公共 health 会静默变成 `{}`；如果正式 freshness 读能力缺失，系统表现成“健康信息为空”，而不是暴露读仓库合约破裂。

根因：

- 前序 Root8 已经移除了 public health 中的 worker liveness，Root90 又把 LLM sealed packet 输入收紧为正式 repository 方法，但 Signal Pulse health 仍残留一条“服务层自己拿连接做查询”的旁路。
- 成熟 CQRS/Kappa 中，读服务不应该知道仓库私有连接形状。公共读模型的健康状态也是 read model contract 的一部分：缺行可以是业务状态，SQL 查询失败可以降级，缺 repository 方法则是 route/session wiring 错误。
- 旧代码把三种情况混在一起：缺方法、缺连接、无健康数据都可能表现为 `{}`。这会让测试夹具和运行时 wiring 在不完整时仍然通过，削弱“固定读仓库接口、单一读路径、fail-closed”的边界。

修复：

- `SignalPulseService._freshness_health(...)` 改为先直接读取 `repository.freshness_health`；该读取发生在 degraded-query `try` 外，缺方法会以 `AttributeError` 暴露为 wiring/契约错误。
- `PulseReadRepository` 新增正式 `freshness_health(window, scope, now_ms, since_hours)`，直接调用持久化 freshness SQL query functions，返回 public health payload。
- 将 freshness 分类阈值和状态判断抽为 `types/pulse_freshness_health.py` 纯规则模块，供 `PulseReadRepository` 和 CLI `PulseFreshnessHealthService` 共享，避免 repository 反向 import service。
- API/unit fakes 必须实现 `freshness_health(...)`；architecture guard 禁止 `SignalPulseService` 重新探测 `repository.conn` 或直接实例化 `PulseFreshnessHealthService`。

验证：

- RED：`uv run pytest tests/unit/test_signal_pulse_service.py::test_signal_pulse_uses_formal_freshness_health_repository_contract tests/unit/test_signal_pulse_service.py::test_signal_pulse_requires_formal_freshness_health_repository_contract -q` 初始 `2 failed`，证明服务没有调用正式方法，缺方法也不会失败。
- RED：`uv run pytest tests/architecture/test_pulse_no_compat.py::test_signal_pulse_health_uses_formal_repository_contract_without_conn_probe -q` 初始 `1 failed`，architecture guard 捕获 `repository.conn` 探测和服务层 freshness 实例化。
- GREEN：上述目标守卫修复后全部通过，合计 `3 passed`。
- GREEN：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py tests/unit/test_signal_pulse_service.py tests/unit/test_api_signal_pulse_contract.py tests/unit/domains/pulse_lab/test_write_gate_health.py -q`，`34 passed`
- GREEN：targeted ruff 和 mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十二：MacroSyncService queue summary 把缺仓库方法当空队列状态

现象：

- `MacroSyncWorker.run_once_sync(...)` 每轮先调用 `MacroSyncService.enqueue_due_windows(...)`，该方法会根据 `macro_sync_state` enqueue bootstrap/gap/steady sync windows，然后把 queue summary 合并进 worker notes。
- `uv run parallax macro status` 也把 sync queue state 当成运维可观测性合同，来源是持久化 `macro_sync_windows`。
- 旧实现却通过 `_call_queue_summary(...)` 执行 `getattr(repos.macro_intel, "macro_sync_queue_summary", None)`；缺方法或不可调用时直接返回 `{}`。
- 这会把 repository/session wiring 错误伪装成“没有 queue state”，worker idle notes 和 status 面都可能少掉 `open_count` / `due_count` / running/exhausted 计数，而测试 fake 仍能通过。

根因：

- 前序 Macro 治理把 `macro_sync_windows` 的 claim/done/error 事务、Macrodata bundle import 的 session UoW、Macro view projection 的 dirty-target 事务都收紧了，但遗漏了 enqueue 后的 queue summary 读合约。
- 成熟 Kappa/CQRS 中，控制面状态不是产品事实，但它仍是正式 ops/read signal。队列 summary 不是可选装饰；它是判断 backlog、retry、running lease 和 exhausted windows 的唯一持久化视图。
- 缺 queue-summary 方法只能说明 repository/session 形状不完整，不能被解释成空队列。否则会削弱 worker backlog 排障、`macro status` 和 `WorkerResult.notes` 的可信度。

修复：

- `MacroSyncService.enqueue_due_windows(...)` 删除 `_call_queue_summary(...)` helper，直接调用 `repos.macro_intel.macro_sync_queue_summary(now_ms=now)`。
- 缺方法现在以 `AttributeError` 暴露为 repository/session wiring failure。
- architecture guard 禁止 `_call_queue_summary`、`getattr(..., None)`、`if not callable(queue_summary)` 和 `return {}` 空 summary 兼容路径回归。
- 单元测试覆盖正常 queue summary 合并和缺方法 fail-closed 两种情况。

验证：

- RED：`uv run pytest tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_uses_formal_queue_summary_repository_contract tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_requires_formal_queue_summary_repository_contract tests/architecture/test_macro_no_compatibility_contract.py::test_macro_sync_queue_summary_requires_repository_contract_without_optional_probe -q` 初始 `2 failed`，暴露缺方法被吞掉、架构 guard 找到 optional helper。
- GREEN：同一命令修复后 `3 passed`
- GREEN：`uv run pytest tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/architecture/test_macro_no_compatibility_contract.py -q`，`59 passed`
- GREEN：targeted ruff 和 mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十三：Asset Market Binance route sync 用输入数量伪造计划差异

现象：

- `sync_binance_usdt_perp_routes(...)` 是 CEX route/feed ops 维护入口。它先读取 Binance provider route 列表，再返回 dry-run/execute 计划计数，execute 时写 `cex_tokens` 与 `price_feeds`。
- 旧实现通过 `_sync_plan_counts(...)` 执行 `getattr(registry, "binance_usdt_perp_sync_plan_counts", None)`；缺方法时用 `len(set(base_symbols))` 和 `len(set(native_market_ids))` 估算待插入数，删除数固定为 0。
- 这会把“RegistryRepository 没接上 plan-count SQL”伪装成一个看似合理的 dry-run 结果。操作者可能看到错误的 insert/delete 计划，execute 结果也会携带不可信的计划摘要。

根因：

- 前序 Root63/Root73 已把 Asset Market sync 的写事务和 `RegistryRepository` 写事务硬切成正式 connection transaction，但遗漏了“计划读”这条合同。
- CEX route sync 虽是 ops-only maintenance，不是 runtime worker，也不写 read model；但 dry-run 计划是 PostgreSQL 当前状态和 provider 输入之间的差异读。成熟 Kappa/CQRS 中，这类 ops/read signal 不能由输入大小猜测，因为它回答的是“当前持久化事实/路由状态和新 provider universe 的差异”。
- 缺 plan-count 仓库方法只能说明 repository/session wiring 不完整，不能被解释成“所有 provider 输入都是待插入，且没有待删除”。这种兼容估算会降低 dry-run 的可信度，也让 fake registry 在不实现正式 SQL 读合约时继续通过。

修复：

- `sync_binance_usdt_perp_routes(...)` 删除 `_sync_plan_counts(...)` helper，直接调用 `registry.binance_usdt_perp_sync_plan_counts(base_symbols=..., native_market_ids=...)`。
- 缺方法现在以 `AttributeError` 暴露为仓库合约错误；只有正式仓库方法返回的持久化差异计数会进入 dry-run/execute 摘要。
- architecture guard 禁止 optional `getattr(registry, "binance_usdt_perp_sync_plan_counts", None)`、输入长度 insert 估算和 `_sync_plan_counts` 回归。
- 单元测试覆盖 dry-run 缺 plan-count 方法 fail-closed，确保不会再生成伪计划。

验证：

- RED：`uv run pytest tests/unit/test_asset_market_sync.py::test_sync_binance_usdt_perp_routes_requires_formal_plan_count_repository_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_market_sync_services_require_connection_transaction_without_manual_commit -q` 初始 `2 failed`，暴露缺方法未失败、架构 guard 捕获 optional probe 和输入长度 fallback。
- GREEN：同一命令修复后 `2 passed`
- GREEN：`uv run pytest tests/unit/test_asset_market_sync.py tests/unit/test_registry_repository.py tests/unit/test_cex_token_profile_sync.py tests/unit/test_us_equity_symbol_sync.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_market_sync_services_require_connection_transaction_without_manual_commit -q`，`20 passed`
- GREEN：targeted ruff 和 mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十四：WorkerScheduler 把坏 status_payload 合约吞成 stopped/空状态

现象：

- `WorkerScheduler.status_payload()` 已经直接汇总每个 worker 的 `status_payload()`，但调度器用于 startability、unhealthy reasons 和 unavailable reason 的私有 `_worker_status_payload(...)` 仍通过 `getattr(worker, "status_payload", None)` 探测。
- 缺方法、方法抛错、或返回非 `dict` 时，旧 helper 都返回 `{}`。随后 `worker_effective_status(...)` 再根据 `settings.enabled`、`last_error`、`running` 等零散属性猜测状态。
- 这会让一个不满足 runtime worker 合约的对象被判成 `stopped` 或继续进入启动判断，而不是在 `/readyz`、`ops worker-status`、scheduler start/health 面暴露 wiring 错误。

根因：

- 前序 Root65/Root66 已把 wake emitter 和 wake waiter 的注入对象从 optional-shape 改成直接契约，但 status hook 还保留“诊断信息可缺省”的旧思维。
- 成熟 Kappa/CQRS 中，worker status 属于控制面读模型，不是可有可无的日志。它不写业务事实，但它决定 worker 是否 startable、是否 unhealthy、ops 是否能定位 backlog 和 unavailable 原因。
- 把坏 status contract 转成 `{}` 会混淆三类状态：worker 真的 stopped、worker 业务状态缺数据、运行时对象根本没实现正式合约。结果是控制面比业务读模型更宽松，反而掩盖 runtime bootstrap/fake/session wiring 错误。

修复：

- `WorkerScheduler.status_payload()`、`worker_effective_status(...)` 和 unavailable reason 读取统一走 `_worker_status_payload(...)`。
- `_worker_status_payload(...)` 直接调用 `worker.status_payload()`；缺方法自然抛 `AttributeError`，方法内部异常原样冒泡，非 mapping payload 抛 `TypeError("worker_status_payload_must_be_dict")`。
- 删除旧的 `_worker_enabled(...)` 属性猜测路径；disabled/unavailable/intentionally-not-started 由 `WorkerBase.status_payload()` 暴露，而不是 scheduler 自己猜。
- architecture guard 禁止 `_worker_status_payload(...)` 重新出现 `getattr(worker, "status_payload", None)`、`if not callable(...)`、吞异常和 `return {}`。

验证：

- RED：`uv run pytest tests/unit/test_worker_scheduler.py::test_scheduler_liveness_requires_formal_status_payload_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed -q` 初始 `4 failed`，三个单测证明缺方法/抛错/非 dict payload 都被吞掉，架构 guard 捕获 optional helper。
- GREEN：同一命令修复后 `4 passed`
- GREEN：`uv run pytest tests/unit/test_worker_scheduler.py tests/unit/test_worker_status.py tests/unit/test_worker_base_runtime.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q`，`219 passed`
- GREEN：targeted ruff 和 mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十五：API dependency helper 把坏 worker status wiring 伪装成 unsupported/false

现象：

- `src/parallax/app/surfaces/api/dependencies.py` 的 `_worker_running(...)` 和 `_worker_object(...)` 仍保留 Root94 同源的 optional status 探测。
- `_worker_running(...)` 通过 `getattr(runtime, "scheduler", None)`、`getattr(scheduler, "status_payload", None)` 探测，缺 scheduler 或 status hook 异常时返回 `False`。
- `_worker_object(...)` 从 `runtime.workers` 读取对象，再用 `getattr(worker, "status_payload", None)` 探测；status hook 抛错时返回 `None`，`/api/live-market` 于是会表现成 `unsupported`。
- 这会让坏 scheduler wiring、坏 worker payload、缺 canonical worker key、测试 fake 未实现正式 hook 等问题被公共 API helper 压成“worker 未运行”或“该 route 不支持 live gateway”。

根因：

- Root94 修掉了 `WorkerScheduler` 内部的 status 合约吞错，但 API dependency layer 仍把 worker status 当成 route 装饰信息，而不是控制面生产契约。
- 成熟 Kappa/CQRS 中，公共 route 可以诚实表达业务数据 unavailable，但不能把运行时控制面合约错误伪装成业务 unavailable。`live_price_gateway` 是 cache/fan-out worker，不是业务事实；但是 route 访问它时仍必须经过 canonical scheduler worker map 和 formal `status_payload()`。
- 旧代码还保留了 `getattr(worker, "worker", worker)` 这种 ad-hoc unwrap，允许测试或兼容包装绕过正式 worker 对象。结果是 API helper 比 scheduler 更宽松，削弱了“一份 canonical worker map + 一份 status contract”的治理边界。

修复：

- `_worker_running(...)` 现在直接读取 `runtime.scheduler`、`scheduler.tasks` 和 `scheduler.status_payload()`；scheduler payload 必须是 mapping，目标 worker key 必须存在，单 worker payload 也必须是 mapping。
- `_worker_object(...)` 现在直接读取 `runtime.scheduler.workers[worker_name]`，调用 worker 自身 `status_payload()`，并只在正式 `effective_status` 为 disabled/intentionally-not-started/unavailable 时返回 `None`。
- 删除 API helper 内部的 status hook `getattr(..., None)`、`except Exception` 吞错、`runtime.workers` 旁路和 ad-hoc `.worker` unwrap。
- architecture guard 禁止 API dependency helper 重新引入 optional scheduler/status/worker probes、吞异常和 `status_payload is None` 分支。

验证：

- RED：`uv run pytest tests/unit/test_api_dependencies.py tests/architecture/test_worker_runtime_contracts.py::test_api_worker_dependencies_use_formal_status_payload_contracts -q` 初始 `8 failed, 2 passed`，证明旧 helper 吞掉 scheduler/worker status 异常、把缺 worker key 变成 false、并从 `runtime.workers` 走旁路。
- GREEN：同一命令修复后 `10 passed`
- GREEN：`uv run pytest tests/unit/test_api_dependencies.py tests/unit/test_api_ops_contract.py tests/unit/test_worker_scheduler.py tests/unit/test_worker_status.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_api_worker_dependencies_use_formal_status_payload_contracts tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed -q`，`50 passed`
- GREEN：targeted mypy 通过；targeted ruff 初始发现新测试两行超长，格式修复后通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十六：Collector ingest service 用构造器 fallback 掩盖 RepositorySession wiring 缺口

现象：

- `app/runtime/bootstrap.py` 的 `_ingest_service_for_repos(...)` 虽然接收 `RepositorySession`，但对 `token_evidence`、`token_intents`、`intent_resolutions`、`market_ticks`、`enriched_events`、`event_anchor_jobs` 等核心仓库使用 `getattr(repos, "...", None)`。
- `IngestService.__init__(...)` 又把这些 `None` 静默转换成 `Repo(evidence.conn)`。`discovery` 甚至没有从 bootstrap 显式传入，而是在构造器里重新创建。
- `token_radar_dirty_targets` 作为历史参数出现在 ingest 构造链路里，但真正的 ingest fan-out 是 source-event 维度的 `token_radar_source_dirty_events`；目标 dirty queue 属于 Token Radar projection 控制面，不是事实 ingest 输入。

根因：

- 这里残留的是“服务自己修 runtime wiring”的旧兼容思想。它让测试 fake 或 runtime session 少建几个仓库也能跑，于是 wiring 缺口不会在 collector 边界暴露。
- 成熟 Kappa/CQRS 中，collector/ingest 是事实入口：它必须把 `events`、token facts、registry identity、market/enriched facts 和 source-dirty 控制行写在同一事务语义内。事实入口不能在服务内部临时重建仓库，因为那会绕过 `RepositorySession` 的单一生命周期、事务约束和可审计依赖图。
- 这种 fallback 不是 SQL 性能优化，而是性能和可靠性风险：它制造第二套连接/仓库来源，弱化事务边界，让缺少 source dirty queue、discovery queue 或 enriched-event writer 的错误变成“看起来能写一部分事实”。

修复：

- `IngestService` 构造器现在要求所有核心仓库显式传入，并直接赋值；不再用 `RegistryRepository(evidence.conn)`、`DiscoveryRepository(evidence.conn)`、`TokenRadarSourceDirtyEventRepository(evidence.conn)` 等 fallback。
- `_ingest_service_for_repos(...)` 现在直接读取 `repos.token_evidence`、`repos.token_intents`、`repos.intent_resolutions`、`repos.discovery`、`repos.market_ticks`、`repos.enriched_events`、`repos.event_anchor_jobs`、`repos.token_radar_source_dirty_events`。
- 删除 ingest 构造器里的 `token_radar_dirty_targets` 参数，保留 source-dirty queue 作为 ingest 到 Token Radar projection 的正式控制面边界。
- architecture guard 禁止 bootstrap 重新引入 optional repository probing，也禁止 `IngestService` 重新引入构造器仓库 fallback。

验证：

- RED：`uv run pytest tests/unit/test_ingest_event_market_capture.py::test_ingest_service_wiring_requires_formal_repository_session_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ingest_service_requires_formal_repository_session_contracts_without_constructor_fallbacks -q` 初始 `8 failed`，证明旧 bootstrap/constructor 吞掉缺仓库字段。
- GREEN：同一命令修复后 `8 passed`
- GREEN：`uv run pytest tests/unit/test_ingest_event_market_capture.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ingest_service_requires_formal_repository_session_contracts_without_constructor_fallbacks tests/architecture/test_token_radar_source_width_contract.py::test_source_dirty_queue_is_required_without_optional_runtime_fallback -q`，`13 passed`
- GREEN：targeted ruff 通过；targeted mypy 通过。
- GREEN：Root96-era non-integration `make check` passed with `3389 passed, 2 skipped in 32.93s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十七：WorkerScheduler unhealthy reason 仍绕过 status_payload 读取旧属性

现象：

- Root94 已经让 `WorkerScheduler` 的 startability、liveness 和 status payload 入口直接调用 `worker.status_payload()`，但 `unhealthy_reasons()` 的细节仍通过 `getattr(worker, "last_error", None)`、`getattr(worker, "unavailable_reason", None)` 和 `getattr(worker, "active_run_once_hard_timed_out_at_ms", None)` 读取 worker 实例属性。
- 当 `status_payload()` 暴露的 `last_error` 和实例旧属性不一致时，scheduler 会报告旧属性错误。
- 当 `status_payload()` 暴露 hard-timeout marker 但实例属性缺失时，scheduler 会把 worker 报成 `stopped`，而不是 `hard_timeout`。
- 当 `status_payload()` 暴露正式 `unavailable_reason` 但实例属性残留旧值时，scheduler 会报告旧 unavailable 原因。

根因：

- Root94 修掉了 status hook 的 optional probing，但 unhealthy reason 还保留“从对象属性补细节”的兼容思路。
- 成熟 Kappa/CQRS 中，worker status 是控制面读模型。`last_error`、hard-timeout marker、unavailable reason 都是这个读模型的一部分；如果 reason 细节绕过 payload 直接读对象属性，就会出现两个状态来源。
- 这不会直接破坏业务事实表，但会破坏操作面判断：`/readyz`、ops status、scheduler health 可能把真实 hard timeout 显示成 stopped，或把新 payload 错误替换成旧属性错误，降低 backlog/超时定位可信度。

修复：

- `WorkerScheduler.unhealthy_reasons()` 现在每个 worker 先读取一次 `_worker_status_payload(worker)`，后续 effective status、unavailable reason、last_error 和 hard-timeout 判断都从这份 payload 派生。
- `_worker_unavailable_reason(...)`、`_worker_failure_reason(...)`、`_worker_hard_timed_out(...)` 改为接收 payload，不再接收 worker 对象。
- architecture guard 禁止 unhealthy reason 路径重新出现 `getattr(worker, "last_error", None)`、`getattr(worker, "unavailable_reason", None)` 和 `getattr(worker, "active_run_once_hard_timed_out_at_ms", None)`。

验证：

- RED：`uv run pytest tests/unit/test_worker_scheduler.py::test_scheduler_unhealthy_reasons_use_formal_status_payload_for_reason_details tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_unhealthy_reasons_use_status_payload_not_worker_attributes -q` 初始 `2 failed`，证明旧实现使用 stale worker attributes 并漏报 payload hard timeout。
- GREEN：同一命令修复后 `2 passed`
- GREEN：`uv run pytest tests/unit/test_worker_scheduler.py tests/unit/test_worker_status.py tests/unit/test_worker_base_runtime.py tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_unhealthy_reasons_use_status_payload_not_worker_attributes tests/architecture/test_worker_inventory_contract.py -q`，`105 passed`
- GREEN：targeted ruff 和 mypy 通过。
- GREEN：latest non-integration `make check` passed with `3391 passed, 2 skipped in 33.12s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十八：stream provider connection_state_payload 仍被当作可选诊断 hook

现象：

- `DexMarketStreamProvider` 和 `UpstreamClientProtocol` 没有把 `connection_state_payload()` 声明为正式运行契约。
- `market_tick_stream_worker` 在 stream 失败时用 `getattr(provider, "connection_state_payload", None)` 探测 hook；hook 不存在或返回非 dict 时吞成 `{}`，导致 `provider_state` 变成 `None`，失败分类退回异常类型。
- readiness、ops diagnostics、OKX DEX WS adapter 也用可选探测或兼容 fallback：已配置 provider 缺少状态 hook 时会被显示成 `disconnected`、`configured` 或 adapter 自造的 disconnected，而不是 runtime wiring failure。

根因：

- 这里残留的是“provider 状态只是诊断增强信息”的旧思路。但在当前 Kappa/CQRS 架构里，stream provider 状态属于控制面读模型：它解释为什么新事实没有进入 `market_ticks`，并支撑 `/readyz`、ops diagnostics、worker degraded notes 和排障判断。
- 成熟 Kappa/CQRS 不要求 provider raw frames 成为事实，但要求 IO 边界的健康状态可审计、单语义、可复现。如果状态 hook 是可选的，系统会把 wiring 缺口伪装成普通未连接或配置正常，造成“事实缺失原因”不可判定。
- 这类 fallback 不会改善 SQL 性能，反而会污染运维链路：worker 已经降级时，控制面却没有准确 provider state，排查只能回到日志和异常类型，削弱了 DB truth 与 runtime status 之间的闭环。

修复：

- `DexMarketStreamProvider` 和 `UpstreamClientProtocol` 现在声明 `connection_state_payload() -> dict[str, Any]`。
- `market_tick_stream_worker`、readiness、ops diagnostics 和 OKX DEX WS adapter 现在直接调用 provider 状态契约，不再用 optional `getattr(..., None)` 探测。
- 已配置 provider 缺少 hook 会以 `provider_connection_state_contract_missing` 显示为 `failed` provider state；hook 返回非 dict 会显示为 `provider_connection_state_payload_not_dict`，而不是被吞成空状态。
- 正常 fake stream provider 测试桩补齐状态 hook；唯一刻意缺失 hook 的 fake 只用于证明契约缺失会变成显式失败。

验证：

- RED：`uv run pytest tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_provider_state_hook_is_required_for_stream_failures tests/architecture/test_worker_runtime_contracts.py::test_stream_provider_connection_state_is_formal_runtime_contract -q` 初始 `2 failed`，证明旧实现把缺失 hook 吞成空 provider state，且 Protocol 未声明正式契约。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_market_tick_stream_worker.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_diagnostics.py tests/architecture/test_worker_runtime_contracts.py::test_stream_provider_connection_state_is_formal_runtime_contract -q`，`30 passed`。
- GREEN：`uv run pytest tests/unit/test_okx_dex_ws_client.py tests/unit/test_gmgn_token_payload.py -q`，`22 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- GREEN：latest non-integration `make check` passed with `3393 passed, 2 skipped in 33.23s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因九十九：agent_execution status 仍从 provider bundle alias 兜底读取

现象：

- `Runtime` 已经有正式字段 `agent_execution_gateway`，bootstrap 也把 gateway 作为独立 runtime root 创建和清理。
- `/api/status` 的 `_agent_execution_status(...)` 和 ops diagnostics 的 `_agent_execution_payload(...)` 仍先 `getattr(runtime, "agent_execution_gateway", None)`，再回退到 `runtime.providers.agent_execution_gateway`。
- 如果正式 runtime 字段为 `None`，但旧 provider alias 上挂了 gateway，ops diagnostics 会显示 `agent_execution.status = ok`，掩盖正式 Runtime wiring 缺口。
- 如果正式字段是一个非空对象但没有 `status_snapshot()`，旧实现把它当成 disabled，而不是 runtime contract failure。

根因：

- 这里残留的是“provider bundle 可以临时承载 agent execution gateway”的兼容路径。它让运行状态有两个来源：正式 runtime root 和 provider alias。
- 在当前架构里，`AgentExecutionGateway` 是 LLM provider 执行控制面：并发、RPM、circuit、timeout、usage audit 由它统一管理；它不是业务事实，也不是 provider raw frame，但它是 `/api/status` 和 ops diagnostics 的生产状态契约。
- 成熟 Kappa/CQRS 的控制面读法应当和事实/读模型一样单源。状态面如果从 alias 兜底，会让 disabled、unavailable、ok 三种状态被错误折叠，影响 agent backpressure、circuit open、provider-started failure 的排障判断。

修复：

- `_agent_execution_status(runtime)` 现在直接读取 `runtime.agent_execution_gateway`；`None` 返回 disabled/absent status，非空 gateway 直接调用 `gateway.status_snapshot()`。
- `_agent_execution_payload(runtime, ...)` 同样只读取正式 runtime 字段；`runtime.providers.agent_execution_gateway` 不再参与状态判断。
- 非空 gateway 缺少 `status_snapshot()` 会显示 `agent_execution_status_contract_missing` / unavailable，而不是 disabled。
- 架构守卫禁止重新引入 provider alias fallback 和 optional `status_snapshot` probing。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_agent_execution_ignores_provider_alias_without_runtime_gateway tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_agent_execution_gateway_requires_status_snapshot_contract tests/architecture/test_worker_runtime_contracts.py::test_agent_execution_status_uses_runtime_gateway_contract_without_provider_alias -q` 初始 `3 failed`，证明旧实现从 provider alias 兜底并把坏 hook 当 disabled。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/architecture/test_worker_runtime_contracts.py::test_agent_execution_status_uses_runtime_gateway_contract_without_provider_alias -q`，`19 passed`。
- GREEN：`uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/integrations/model_execution/test_agent_execution_gateway.py tests/architecture/test_agent_execution_plane_contracts.py -q`，`56 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- GREEN：latest non-integration `make check` passed with `3396 passed, 2 skipped in 33.66s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百：WorkerScheduler 关闭 DB pools 仍保留逐池 fallback

现象：

- `WorkerScheduler._close_pools(...)` 先尝试 `getattr(self.db, "aclose", None)`，如果没有正式 close root，就继续探测并关闭 `api_pool`、`worker_pool`、`lock_pool`、`tool_pool`、`wake_pool`。
- 正式的 `DBPoolBundle` 反而没有 `aclose()`，所以调度器复制了 bundle 内部的 pool 生命周期知识。
- 测试中的 partial DB object 只要暴露几个 pool attribute 就可以通过 shutdown，掩盖了 runtime DB bundle contract 缺失。

根因：

- 这里不是业务 SQL 性能问题，而是运行时资源生命周期的单一所有权问题。成熟 Kappa/CQRS 系统里，worker scheduler 负责 worker 生命周期，DB pool bundle 负责 DB pool 生命周期；调度器不应该知道有多少个 pool role，也不应该通过 attribute probing 兼容半成品 DB object。
- 旧实现把“为了测试方便的 partial object”变成了生产兼容路径，导致关闭顺序、异常聚合和缺失资源的失败语义分散在 scheduler 里。
- 这种 fallback 会让 runtime wiring 问题在停机路径被延迟暴露：缺少正式 `db.aclose()` 本应是启动/停机契约错误，而不是让 scheduler 逐个猜测可关闭资源。

修复：

- `DBPoolBundle.aclose()` 成为唯一正式 pool 生命周期入口，按 `api_pool`、`worker_pool`、`lock_pool`、`tool_pool`、`wake_pool` 顺序关闭非空 pool，并用 `ExceptionGroup("db_pool_bundle_close_failed", ...)` 聚合关闭错误。
- `WorkerScheduler.stop()` 直接调用 `self.db.aclose()`，不再 `getattr` 探测、不再逐池 fallback，也删除了 `_close_pools(...)` / `_close_resource(...)`。
- 架构守卫禁止重新引入 `getattr(self.db, "aclose", None)`、逐池 attribute fallback 和 scheduler 资源关闭 helper。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_db_pool_bundle_aclose_closes_all_pool_roles_once tests/unit/test_worker_scheduler.py::test_scheduler_stop_requires_db_bundle_aclose_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback -q` 初始 `3 failed`，分别证明 `DBPoolBundle` 没有 `aclose()`、scheduler 会逐池 fallback、架构守卫能发现旧 token。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_worker_scheduler.py tests/unit/test_db_pool_bundle.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed -q`，`51 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过；latest non-integration `make check` passed with `3399 passed, 2 skipped in 33.03s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零一：bootstrap 失败清理仍绕过 DBPoolBundle close root

现象：

- `bootstrap(...)` 在 provider wiring 或 runtime assembly 失败时，仍调用 `_close_db_pools(db.api_pool, db.worker_pool, getattr(db, "lock_pool", None), db.tool_pool, db.wake_pool)`。
- 这条路径和 Root100 修掉的 `WorkerScheduler._close_pools(...)` 是同一个问题：运行时 composition root 知道每个 pool role，并且继续用逐池 fallback 关闭。
- 单元测试中的 fake DB 即使没有正式 `aclose()`，只要暴露各个 pool attribute，也能被 startup unwind 当作可关闭 DB bundle。

根因：

- bootstrap 失败清理是 runtime lifecycle 的另一半。正常停机由 `Runtime.aclose()` / `WorkerScheduler.stop()` 覆盖，异常启动回滚由 `bootstrap(...) except` 覆盖；两边必须共享同一个 DBPoolBundle 生命周期契约。
- 旧代码把“初始化失败时尽量清理”实现成逐池探测，短期看容错，长期看会让 `DBPoolBundle` 的 close 顺序、错误聚合和缺失 contract 语义继续分裂。
- KISS 的修法不是再做一个更聪明的 fallback helper，而是让 bootstrap 在 DB bundle 已创建后只调用正式 `db.aclose()`。如果 cleanup 失败，保留原始启动错误并把 cleanup failure 加为 note，避免清理失败掩盖真正的启动根因。

修复：

- `bootstrap(...) except` 现在调用 `_close_db_bundle_sync(db)`，该 helper 只执行 `_await_sync(db.aclose())`。
- 删除 `_close_db_pools(...)` 和 `contextlib.suppress` 逐池静默关闭路径。
- 架构守卫禁止 bootstrap failure path 重新出现 `_close_db_pools(...)`、`getattr(db, "lock_pool", None)`、`db.api_pool/db.worker_pool/db.tool_pool/db.wake_pool` 逐池关闭 token。

验证：

- RED：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_bootstrap_failure_closes_db_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback -q` 初始 `2 failed`，证明 bootstrap 失败路径没有调用 `db.aclose()`，且架构守卫抓到逐池 fallback。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_db_pool_bundle.py tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback -q`，`36 passed`。
- GREEN：targeted mypy 通过；targeted ruff 在整理新增 import 后通过；latest non-integration `make check` passed with `3401 passed, 2 skipped in 32.80s`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零二：WakeBus 仍接受裸连接工厂作为兼容 fallback

现象：

- `WakeBus._notify(...)` 先调用 `self._conn_factory()`，再用 `hasattr(conn_or_context, "__enter__")` 判断是否是 connection context。
- 如果工厂返回裸 connection，旧代码会直接在裸 connection 上执行 `pg_notify` 并 `commit()`。
- 正式 runtime 路径是 `DBPoolBundle.wake_emitter()` 注入 `wake_pool.connection`，也就是专用 wake pool 的 connection context；裸 connection 分支并不是一个需要保留的生产入口。

根因：

- Root55 已经把 wake-pool 的 `commit` / `notifies` 从可选能力改成正式 contract，但 `_notify(...)` 仍保留了更外层的形状兼容：connection factory 既可以返回 context，也可以返回 raw connection。
- 这会让 malformed wake-pool wiring 被伪装成“仍然能发通知”。成熟 Kappa/CQRS 里，`NOTIFY` 虽然不是 truth，但 wake emit 的资源边界仍然必须由 `DBPoolBundle` 的 wake pool 管理；裸连接 fallback 会绕开 checkout/return lifecycle，使测试 fake 或旧调用点继续绕过正式 runtime root。
- KISS 修法不是继续识别更多连接形状，而是只接受正式 context：缺 context protocol 在 `pg_notify` 前失败。

修复：

- `WakeBus._notify(...)` 现在只走 `context = self._conn_factory(); _require_connection_context(context); with context as conn: ...`。
- `_require_connection_context(...)` 要求 callable `__enter__` 和 `__exit__`，缺失时抛 `wake_bus_connection_context_required`。
- 删除 `_execute_notify(conn_or_context, ...)` / `_commit(conn_or_context)` raw connection fallback。
- 架构守卫禁止 `hasattr(conn_or_context, "__enter__")`、`conn_or_context = self._conn_factory()`、raw-connection notify/commit token 回到 `wake_bus.py`。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_wake_bus_requires_connection_context_without_raw_connection_fallback tests/architecture/test_worker_runtime_contracts.py::test_wake_bus_requires_connection_context_without_raw_connection_fallback -q` 初始 `2 failed`，证明旧 WakeBus 接受裸连接且架构守卫能抓到 raw fallback token。
- GREEN：同一命令修复后 `2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零三：WorkerBase advisory lock 释放仍保留 close fallback

现象：

- `WorkerBase._release_advisory_lock()` 通过 `getattr(self._advisory_lock_connection, "release", None)` 探测释放方法。
- 如果没有 `release()`，旧代码继续探测 `close()`，并把 `release or close` 当作等价释放入口。
- 正式 runtime 路径里，single-writer advisory lock 来自 `DBPoolBundle.acquire_advisory_lock_connection()`，该对象的生命周期 contract 是 `release()`；`close()` 只是具体实现内部的别名，不应成为 WorkerBase 接受 malformed lock object 的外部兼容入口。

根因：

- 这是 worker lifecycle root ownership 不清晰的同类问题。成熟 Kappa/CQRS 的 single-writer 约束不是“尽量释放某个看起来像连接的对象”，而是由 DBPoolBundle 提供正式 advisory-lock handle，WorkerBase 只按该 handle 的 contract 释放。
- `close()` fallback 让旧 fake、partial DB object 或错误注入的连接对象在关闭阶段看起来成功，掩盖了真正的 runtime wiring 错误。最坏情况下，测试覆盖的是“有个 close 方法被调用”，而不是 advisory lock 是否按 `pg_advisory_unlock` 和 pool return 语义完成。
- advisory lock 是控制 single writer 的运行时闸门。释放路径如果兼容多种形状，就会让单 writer 的可证明性下降：谁持有锁、谁释放锁、释放失败如何暴露，都被 fallback 稀释。

修复：

- `WorkerBase._release_advisory_lock()` 现在先保存正式 lock handle，然后直接读取 `lock_connection.release`。
- 缺少 `release` 或 `release` 不可调用时，抛 `worker_advisory_lock_release_required`，不再调用 `close()`。
- 释放尝试结束后仍清空 `_advisory_lock_connection`，避免失败路径重复释放同一 handle。
- 架构守卫禁止 `getattr(..., "release", None)`、`getattr(..., "close", None)`、`release or close` 和 `releaser is not None` 回到 `_release_advisory_lock()`。

验证：

- RED：`uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_requires_advisory_lock_release_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_base_advisory_lock_release_contract_is_direct -q` 初始 `2 failed`，证明旧实现没有抛 `worker_advisory_lock_release_required`，并且架构守卫能抓到 `release/getattr + close fallback`。
- GREEN：同一命令修复后 `2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零四：CLI ops one-shot worker 仍复制 DB/lock 生命周期 fallback

现象：

- `ops.py` 的一次性 worker 命令使用 `_close_db_bundle(db)`，但该 helper 逐个探测并关闭 `api_pool`、`worker_pool`、`lock_pool`、`tool_pool`、`wake_pool`。
- `_release_advisory_lock_connection(...)` 仍通过 `getattr(connection, "release", None)` 和 `getattr(connection, "close", None)` 选择 `release or close`。
- `_close_runtime_resource(...)` 作为未使用 helper 也保留了 `close/aclose` 形状探测，形成另一个潜在兼容入口。

根因：

- CLI ops one-shot worker 不是另一个 runtime。它临时创建 `DBPoolBundle`、构造正式 worker、获取 advisory lock，然后跑一次 projection/repair。既然它使用的是同一个 DB bundle 和同一个 advisory-lock 语义，就不应该复制一套“逐池关闭”和“close 也算释放”的脚本级生命周期。
- 旧实现把 Root100/Root103 已经修掉的 runtime root 问题留在 ops surface：正常服务停机要求 `DBPoolBundle.aclose()`，但 ops 命令仍可通过 partial fake DB 或旧 pool attributes 通过；WorkerBase 要求 advisory lock `release()`，但 ops 命令手工拿锁后仍接受 `close()`。
- 这会让 ops repair 路径成为兼容性逃生门。成熟 Kappa/CQRS 中，ops repair 可以是显式例外的写入口，但不能是资源生命周期、single-writer lock、事务边界的例外。

修复：

- `_close_db_bundle(db)` 现在直接读取并调用 `db.aclose()`，缺失或不可调用时抛 `ops_db_bundle_aclose_required`。
- `_release_advisory_lock_connection(connection)` 现在直接读取并调用 `connection.release()`，缺失或不可调用时抛 `ops_advisory_lock_release_required`。
- 删除未使用的 `_close_runtime_resource(...)` 形状探测 helper。
- 架构守卫禁止 ops one-shot worker lifecycle helper 重新出现逐池 close fallback、`release/close` fallback、`release or close` 和 `releaser is not None`。

验证：

- RED：`uv run pytest tests/unit/test_ops_backfill_commands.py::test_ops_one_shot_worker_close_requires_db_bundle_aclose_contract tests/unit/test_ops_backfill_commands.py::test_ops_advisory_lock_release_requires_release_contract_without_close_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts -q` 初始 `3 failed`，分别证明逐池 close、`close()` advisory fallback、架构 token 都还在。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_execute_commands_require_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts -q`，`19 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零五：Collector upstream client 关闭仍接受 close-only 兼容形状

现象：

- `CollectorService.on_close()` 通过 `getattr(self.upstream_client, "aclose", None) or getattr(self.upstream_client, "close", None)` 选择关闭方法。
- `UpstreamClientProtocol` 只声明 `run()` 和 `connection_state_payload()`，没有声明生命周期 `aclose()`。
- close-only fake 或错误注入的 upstream client 可以在 Collector 关闭阶段被静默接受，测试也只能证明“某个 close 被调用”，不能证明 runtime 真的遵循统一 worker/provider lifecycle。

根因：

- Collector 是事实入口 worker，它接收 GMGN stream frame 并把 raw frame / event / token fact 写入 PostgreSQL。这个 worker 的 provider IO 生命周期必须是显式 contract，而不是按对象形状猜测。
- 成熟 Kappa/CQRS 中，provider raw frames 只是输入，不是事实；事实边界在 DB。为了让这个边界可停机、可重启、可诊断，上游 stream client 的启动、状态、关闭必须都是协议的一部分：`run()`、`connection_state_payload()`、`aclose()`。
- 旧 `close()` fallback 把运行时错误变成兼容路径。它允许旧 fake、partial adapter、甚至错误 provider wrapper 混入 collector，而停机时不会暴露 wiring 缺口。这和 DB bundle / advisory lock / WakeBus 几个根因同源：生命周期 owner 不清，调用方用 reflection 兜底。

修复：

- `UpstreamClientProtocol` 现在声明 `async def aclose(self) -> None`。
- `CollectorService.on_close()` 直接读取并调用 `self.upstream_client.aclose()`；缺失或不可调用时抛 `collector_upstream_client_aclose_required`。
- `DirectGmgnWebSocketClient` 实现 `aclose()`，将连接状态收敛到 `disconnected`；活跃 websocket 的实际关闭仍由 run task cancellation 里的 `finally` 负责。
- 架构守卫禁止 Collector 关闭路径重新出现 `getattr(..., "aclose", None)`、`getattr(..., "close", None)`、`inspect.isawaitable` 和 `close()` fallback。

验证：

- RED：`uv run pytest tests/unit/test_collector_service.py::CollectorServiceTests::test_collector_close_requires_upstream_client_aclose_contract_without_close_fallback tests/architecture/test_worker_runtime_contracts.py::test_collector_upstream_client_close_contract_is_direct -q` 初始 `2 failed`，证明旧 Collector 接受 close-only client，协议/实现仍有 optional close fallback。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_collector_service.py tests/unit/test_direct_ws.py tests/unit/test_gmgn_token_payload.py tests/architecture/test_worker_runtime_contracts.py::test_collector_upstream_client_close_contract_is_direct tests/architecture/test_worker_runtime_contracts.py::test_stream_provider_connection_state_is_formal_runtime_contract -q`，`21 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零六：Bootstrap provider cleanup 仍递归扫描对象图和 close/aclose 形状

现象：

- `Runtime.aclose()` 调用 `_cleanup_runtime_providers(self)`，该 helper 通过 `_provider_cleanup_targets(...)` 递归遍历 `runtime.providers`、`runtime.agent_execution_gateway`、`runtime.llm_gateway`。
- `_provider_cleanup_targets(...)` 会扫描 dataclass fields、mapping、sequence、`__dict__`、`__slots__`，并把任何拥有 `close()` 或 `aclose()` 的对象当成 cleanup target。
- bootstrap 失败清理 `_cleanup_provider_roots_sync(...)` 使用同一套递归扫描。结果是 `WiredProviders.agent_execution_gateway` 这种旧 provider-bundle alias 也会被当成 provider root 关闭，哪怕正式 runtime root 已经是 `runtime.agent_execution_gateway`。

根因：

- 这不是“清理够不够彻底”的问题，而是生命周期所有权再次被 reflection 稀释。成熟 Kappa/CQRS 的 runtime root 应该知道自己拥有哪些可关闭资源：provider bundle、agent execution gateway、LLM gateway。它不应该在对象图里搜索任何名字像 close 的东西。
- 递归扫描会让 provider wiring 的内部结构变成隐式 contract。只要某个 wrapper、fake、adapter 或 alias 暴露 `close()`，bootstrap 就可能关闭它；这会掩盖正式 root 缺失，也可能让旧 alias 继续有实际语义。
- 对事实入口和 worker 架构而言，这类“全局兜底清理”会把责任从 owning bundle/worker/gateway 移到 bootstrap，导致 provider IO 所有权难以审计：到底是 worker `on_close()` 关，还是 provider bundle 关，还是递归扫描碰巧关，都变得模糊。

修复：

- `WiredProviders` 现在暴露正式 `aclose()` root；它按 `ingestion`、`asset_market`、`cex_market_intel`、`news_intel`、`pulse_lab` 显式关闭 provider bundle，并收集错误为 `wired_provider_cleanup_failed`。
- `AssetMarketProviders`、`CexMarketIntelProviders`、`NewsIntelProviders`、`PulseLabProviders` 各自拥有自己的显式 close/aclose 顺序；`WiredProviders.agent_execution_gateway` 旧 alias 不参与 provider bundle cleanup。
- `Runtime.aclose()` 的 provider cleanup 直接调用 `runtime.providers.aclose()`、`runtime.agent_execution_gateway.aclose()`、`runtime.llm_gateway.aclose()`。
- bootstrap failure cleanup 同样直接调用 `providers.aclose()`、`agent_execution_gateway.aclose()`、`llm_gateway.aclose()`，并删除 `_provider_cleanup_targets(...)`、`_object_values_for_cleanup(...)`、`_has_close_method(...)` 和 dataclass/object graph traversal。

验证：

- RED：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_provider_cleanup_uses_formal_roots_without_provider_graph_fallback tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_provider_cleanup_uses_formal_roots_without_object_graph_scan -q` 初始 `2 failed`，证明旧 cleanup 会关闭 provider-bundle alias，且架构守卫能抓到递归扫描 helper。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_providers_wiring.py tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_llm_gateway.py tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_provider_cleanup_uses_formal_roots_without_object_graph_scan tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback -q`，`51 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零七：Worker-owned provider cleanup 仍在各 worker 内部做 close/aclose 形状兼容

现象：

- `PulseCandidateWorker.on_close()` 先探测 `decision_client.aclose`，找不到时继续探测 `decision_client.close`，把 async decision provider 和 sync close-only object 当成兼容生命周期。
- `NewsFetchWorker.on_close()` 探测 `feed_client.close`，然后如果返回 awaitable 就继续 await，把 `NewsSourceProvider.close() -> None` 的同步协议扩展成“同步/异步都可以”。
- Root106 已经把 bootstrap 的全局 provider cleanup 反射层切掉，但 worker 自己还保留了局部 provider close fallback，形成新的兼容入口。

根因：

- 这仍然是 lifecycle owner 不清晰。Pulse candidate worker 拥有的是 `PulseDecisionProvider`，该协议的 provider-side cleanup 是 `aclose()`；News fetch worker 拥有的是 `NewsSourceProvider`，该协议的 cleanup 是同步 `close()`。
- 如果 worker 接受另一种 shape，测试 fake 或错误 provider wrapper 可以绕过协议，导致 wiring 错误在 shutdown 阶段变成“也能关”。成熟 Kappa/CQRS 里，worker 可以拥有 provider IO，但它必须按 provider 协议关闭，而不是把 worker 变成又一个通用 cleanup dispatcher。
- News fetch 是事实入口之一，Pulse candidate 是 agent-driven read-model/control-plane writer。二者的 provider IO 边界必须可审计：谁 owns provider、用哪个 close contract、错误如何暴露，都不能靠 `getattr` fallback 推断。

修复：

- `PulseCandidateWorker.on_close()` 现在直接读取并调用 `self.decision_client.aclose()`；缺失或不可调用时抛 `pulse_candidate_decision_client_aclose_required`，不再调用 `close()`。
- `NewsFetchWorker.on_close()` 现在调用同步 `feed_client.close()`，并要求返回 `None`；返回 awaitable 或其他值时抛 `news_fetch_feed_client_close_must_be_sync`。
- 架构守卫禁止两个 worker 的 provider cleanup 重新出现 `getattr(...close/aclose...)`、`close_sync`、`isawaitable(...)` 和 awaitable close fallback。

验证：

- RED：`uv run pytest tests/unit/test_pulse_candidate_worker.py::test_pulse_worker_aclose_requires_decision_client_aclose_contract_without_close_fallback tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_on_close_requires_sync_feed_client_close_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_owned_provider_cleanup_uses_formal_lifecycle_contracts -q` 初始 `3 failed`，证明 Pulse 接受 close-only client、News await 了 malformed close result，架构守卫抓到 fallback token。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_worker_runtime_contracts.py::test_worker_owned_provider_cleanup_uses_formal_lifecycle_contracts -q`，`88 passed`。
- GREEN：targeted ruff 和 targeted mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零八：Provider wiring wrapper 和 partial cleanup 仍在跳过 missing close contract

现象：

- `FallbackDexQuoteProvider.close()` 对 primary/fallback provider 使用 `getattr(provider, "close", None)`，如果 provider 没有 `close()` 就直接跳过。
- `SerializedDiscoveryProvider.close()` 对内部 discovery provider 使用 `getattr(self._provider, "close", None)`，缺失时直接 return。
- asset-market 和 OKX wiring 的 `_close_partial_providers(...)` 在启动失败回滚时也使用 optional `close` 探测；已经构造出来但协议错误的 provider 会被静默忽略，不会在原始异常 notes 中留下清理失败证据。

根因：

- Root106 切掉了 bootstrap 的对象图扫描，Root107 切掉了 worker-owned provider fallback，但 provider wiring 层仍保留“如果有 close 就关”的兼容思路。这样生命周期 contract 还没有贯穿到最靠近构造失败的位置。
- provider wiring 是事实入口和 read-model worker 的上游装配边界。这里如果跳过 missing `close()`，测试 fake、错误 adapter 或半初始化 provider 都可能在失败路径中看起来“清理成功”，导致 wiring 错误晚暴露或不暴露。
- 成熟 Kappa/CQRS 的 provider 边界不应该通过形状猜测来推断资源所有权。wrapper 拥有什么 provider、该 provider 用同步 `close()` 还是异步 `aclose()`，应该由协议和 root owner 决定；partial cleanup 只能按正式 contract 清理，并把 contract 缺失作为失败证据。

修复：

- `FallbackDexQuoteProvider.close()` 现在对 primary/fallback provider 直接调用 `provider.close()`，仍保留去重，缺失 `close()` 会按 contract 错误暴露。
- `SerializedDiscoveryProvider.close()` 现在在 lock 内直接调用 `self._provider.close()`，保持幂等，但不再接受 close-less inner provider。
- asset-market 和 OKX `_close_partial_providers(...)` 通过 `_SyncCloseProvider` contract 直接调用 `close()`；缺失或执行失败都作为 `partial provider cleanup failed: ...` note 附加到原始启动异常。
- 架构守卫禁止这几个 provider wiring cleanup 切口重新出现 optional `close` 探测和 `if close` / `if close is None` 分支。

验证：

- RED：`uv run pytest tests/unit/test_providers_wiring.py::test_fallback_quote_provider_close_requires_primary_close_contract tests/unit/test_providers_wiring.py::test_serialized_discovery_provider_close_requires_inner_close_contract tests/unit/test_providers_wiring.py::test_asset_market_partial_cleanup_records_missing_close_contract tests/architecture/test_worker_runtime_contracts.py::test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes -q` 初始 `4 failed`，证明 wrapper 和 partial cleanup 都会静默跳过 missing close。
- GREEN：同一命令修复后 `4 passed`。
- GREEN：`uv run pytest tests/unit/test_providers_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_provider_cleanup_uses_formal_roots_without_object_graph_scan -q`，`26 passed`。
- GREEN：targeted ruff、targeted mypy 通过；残留扫描未找到 provider wiring optional close 探测。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百零九：DBPoolBundle.create partial pool cleanup 仍用 optional close 探测并可能遮蔽原始建池错误

现象：

- `DBPoolBundle.create(...)` 在创建 `api_pool`、`worker_pool`、`lock_pool`、`tool_pool`、`wake_pool` 的过程中如果失败，会遍历 `locals().get(...)` 得到已经创建的 pool。
- 旧代码对每个 partial pool 执行 `getattr(pool, "close", None)`，没有 `close()` 就静默跳过。
- 如果 partial pool 的 `close()` 自身抛异常，该 cleanup 异常会遮蔽原始建池错误，例如 `worker pool failed` 被替换成 `close failed`。

根因：

- Root100/101 已经把 DB bundle 完整生命周期收敛到 `DBPoolBundle.aclose()`，但 `DBPoolBundle.create()` 内部的“bundle 尚未构造完成”失败路径仍保留旧的 shape-probe cleanup。
- 这条路径属于 runtime composition root 的最早阶段。它不是业务事实链路，但它决定了进程能否可靠启动、失败时能否保留真正的根因。optional close 探测会让错误 fake、半初始化 pool 或错误 adapter 看起来“没有可清理资源”，而 cleanup 失败遮蔽原始错误会让排障指向错误方向。
- KISS 的边界是：建池函数知道 `create_pool(...)` 返回的是有同步 `close()` 的 pool；partial cleanup 只能按这个正式 contract 调用，并把 contract 缺失/关闭失败记录为原始异常的附加证据。

修复：

- `DBPoolBundle.create(...)` 的 `except` 现在调用 `_close_partial_pools(exc, ...)`。
- `_close_partial_pools(...)` 通过 `_SyncClosePool` protocol 和 `cast(_SyncClosePool, pool).close()` 直接调用同步 close contract。
- missing `close()` 或 close 执行失败都写入 `partial db pool cleanup failed: ...` note，不会静默跳过，也不会遮蔽原始建池异常。
- 架构守卫禁止 `DBPoolBundle.create()` partial cleanup 重新出现 `getattr(pool, "close", None)`、`close = getattr`、`if close` 等 optional close 探测。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_create_failure_records_missing_close_contract_for_partial_pool tests/unit/test_db_pool_bundle.py::test_create_failure_preserves_original_error_when_partial_pool_close_fails tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_create_partial_cleanup_uses_formal_pool_close_contract -q` 初始 `3 failed`，证明 missing close 被跳过、close 失败会遮蔽原始建池错误、架构 helper 还不存在。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_bootstrap_failure_closes_db_bundle_contract_without_pool_fallback tests/unit/test_worker_scheduler.py::test_scheduler_stop_requires_db_bundle_aclose_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_create_partial_cleanup_uses_formal_pool_close_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback -q`，`23 passed`。
- GREEN：targeted ruff、targeted mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。广义生命周期扫描仍显示 `_discard_connection()` 的连接 discard fallback，这是另一个独立切口，不在本根因的 AC105 范围内。

## 根因一百一十：DBPoolBundle discard connection 仍保留 pool.close_returns 和 optional conn.close fallback

现象：

- `_discard_connection(pool, conn)` 先探测 `getattr(pool, "close_returns", None)`；如果 fake pool 或旧 pool shape 暴露该方法，就调用 `pool.close_returns(conn)`。
- 如果没有 `close_returns`，旧代码再探测 `getattr(conn, "close", None)`，有就关闭，缺失也继续 `pool.putconn(conn)`。
- 真实 `psycopg_pool.ConnectionPool` 没有 `close_returns`；这是测试 fake 里的私有兼容 hook。生产正式路径是关闭 connection 后通过 `putconn` 交还 pool，让 pool 处理 closed connection。

根因：

- Root100/109 已经把 DB pool root close 和 create partial cleanup 收敛到正式 contract，但 checked-out connection discard 仍保留了“pool 如果有某个私有 hook 就用”的测试兼容思路。
- 这个路径影响 worker session reset failure、advisory lock unlock/reset failure。它不写业务事实，但决定坏连接是否离开 worker pool，以及单 writer 锁连接失败时是否按统一 pool 生命周期回收。
- 成熟 Kappa/CQRS 的 worker runtime 不应该依赖 fake pool 私有方法来表达资源生命周期。DBPoolBundle 已经知道自己使用的是 psycopg pool contract：`conn.close()` + `pool.putconn(conn)`。缺少 `conn.close()` 是 malformed connection，不应该被 optional probe 吞掉。

修复：

- `_discard_connection(pool, conn)` 现在直接调用 `conn.close()`，然后 `pool.putconn(conn)`。
- 删除 `pool.close_returns` 探测和 optional `conn.close` 探测。
- 单元测试要求 worker session reset failure 与 advisory-lock discard 走同一条 closed-connection return path；架构守卫禁止 `close_returns` 和 optional close probe 回流。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_discard_connection_uses_connection_close_then_pool_putconn_without_pool_close_returns tests/unit/test_db_pool_bundle.py::test_worker_session_preserves_body_error_and_discards_when_reset_fails tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_discard_connection_uses_formal_connection_close_without_pool_fallback -q` 初始 `3 failed`，证明旧实现调用了 `pool.close_returns`，且架构守卫抓到 `close_returns/getattr`。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_worker_scheduler.py::test_scheduler_stop_requires_db_bundle_aclose_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_discard_connection_uses_formal_connection_close_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_create_partial_cleanup_uses_formal_pool_close_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback -q`，`24 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`db_pool_bundle.py` 残留扫描未找到 `close_returns` 或 optional close probe。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十一：MarketTickStreamWorker 对 stream iterator aclose 仍做 optional probing

现象：

- `MarketTickStreamWorker._stream_and_persist_ticks(...)` 在每个 bounded stream cycle 里创建 `iterator = stream_dex_market.iter_price_info().__aiter__()`。
- finally cleanup 使用 `getattr(iterator, "aclose", None)`，有就 await，没有就跳过。
- 当 provider 返回一个实现 `__aiter__/__anext__` 但缺少 `aclose()` 的自定义 async iterator 时，worker 会把本轮 stream 当作成功完成，而不是 degraded contract failure。

根因：

- Root98 已经把 stream provider `connection_state_payload()` 收敛为正式状态 contract，但单次 stream iterator 生命周期仍停留在“能关就关”的兼容思路。
- `market_tick_stream` 是 Tier 1 market fact ingest worker。provider 对象本身由 provider bundle/runtime root 关闭，但每次 `iter_price_info()` 返回的 async iterator 是 worker 本轮消费的资源；它必须有可取消、可关闭的 lifecycle，否则 bounded cycle timeout 后可能留下 provider-side stream task 或订阅状态。
- 成熟 Kappa/CQRS 的事实入口不能把 malformed provider iterator 当成功 no-op cleanup。缺 iterator `aclose()` 应该暴露为 degraded stream evidence，同时保留已经持久化的有效 ticks，而不是静默通过。

修复：

- 新增 `_AsyncCloseIterator` protocol。
- `MarketTickStreamWorker._stream_and_persist_ticks(...)` 的 finally 现在直接 `await cast(_AsyncCloseIterator, iterator).aclose()`。
- 缺失 `aclose()` 会通过既有外层 degraded path 记录为 `AttributeError`，已收集 ticks 仍会持久化一次。
- 架构守卫禁止 `getattr(iterator, "aclose", None)`、`if close is not None` 等 optional async-close probing 回流。

验证：

- RED：`uv run pytest tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_requires_iterator_aclose_contract tests/architecture/test_worker_runtime_contracts.py::test_market_tick_stream_worker_iterator_cleanup_uses_formal_aclose_contract -q` 初始 `2 failed`，证明缺 `aclose()` iterator 被旧实现当成正常成功，且架构守卫抓到 optional probe。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_market_tick_stream_worker.py tests/architecture/test_worker_runtime_contracts.py::test_market_tick_stream_worker_iterator_cleanup_uses_formal_aclose_contract tests/architecture/test_worker_runtime_contracts.py::test_stream_provider_connection_state_is_formal_runtime_contract tests/architecture/test_worker_manifest_static_contracts.py::test_provider_io_manifest_inventory_is_explicit -q`，`17 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`market_tick_stream_worker.py` 残留扫描未找到 optional iterator `aclose` probe。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十二：DBPoolBundle runtime pool close 仍接受 awaitable close 兼容形状

现象：

- `DBPoolBundle.aclose()` 已经成为 scheduler、bootstrap 和 CLI ops 共享的 DB 生命周期入口。
- 但内部 `_close_pool(pool)` 仍执行 `result = pool.close()` 后用 `inspect.isawaitable(result)` 判断，并在返回 awaitable 时 `await result`。
- 真实 `psycopg_pool.ConnectionPool.close()` 是同步 close 契约；awaitable 返回值只可能来自 fake、旧 adapter 或错误接线。

根因：

- Root100/101 把“谁拥有 pool shutdown”收敛到了 `DBPoolBundle.aclose()`，Root109/110 又把 create partial cleanup 和 discarded connection cleanup 收敛成正式同步契约；但 runtime shutdown 的单池 close 仍保留“async shape 也可以”的兼容尾巴。
- 这会让 DB lifecycle root 表面统一，底层仍接受第二种 pool 生命周期协议。成熟 Kappa/CQRS 的 runtime root 应该让错误接线快速暴露，因为 pool close 顺序、错误聚合和 worker stop 语义都依赖同一个 PostgreSQL 客户端契约。
- `DBPoolBundle.aclose()` 可以是 async owner boundary，但这不等于底层 pool 允许 async close。async 边界只是为了被 scheduler/bootstrap await；pool contract 仍应是 `close() -> None`。

修复：

- 删除 `db_pool_bundle.py` 的 `inspect` import 和 `_close_pool(...)` 中的 awaitable fallback。
- `_close_pool(pool)` 现在直接调用 `pool.close()`；返回值非 `None` 时抛 `RuntimeError("db_pool_close_must_be_sync")`。
- 架构守卫禁止 `import inspect`、`inspect.isawaitable`、`await result`、`await pool.close()` 回流到 `DBPoolBundle` pool shutdown。
- 文档明确 `DBPoolBundle.aclose()` 是 async owner boundary，底层 psycopg pool close 仍是同步 `close() -> None`。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_db_pool_bundle_aclose_requires_sync_pool_close_contract_without_awaitable_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_pool_close_is_sync_contract_without_awaitable_fallback -q` 初始 `2 failed`，证明旧实现等待了 awaitable close result，且架构守卫抓到 `import inspect`、`inspect.isawaitable`、`await result`。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_worker_scheduler.py::test_scheduler_stop_requires_db_bundle_aclose_without_pool_fallback tests/unit/test_bootstrap_worker_runtime_wiring.py::test_bootstrap_failure_closes_db_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_pool_close_is_sync_contract_without_awaitable_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_discard_connection_uses_formal_connection_close_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_create_partial_cleanup_uses_formal_pool_close_contract tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback -q`，`27 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`db_pool_bundle.py` 残留扫描未找到 awaitable close fallback 或 optional close probe。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十三：CLI ops asset-market one-shot provider cleanup 仍复制 provider 字段并 optional close

现象：

- `ops.py` 中 `asset_profile_refresh` 和 `resolution_refresh` 的 one-shot 命令会临时调用 `wire_asset_market_providers(...)`。
- finally 中 `_close_asset_market_providers(asset_market)` 手工枚举 `cex_market`、`dex_discovery_market`、`dex_quote_market`、`dex_candle_market`、`stream_dex_market`，再遍历 `dex_profile_sources`。
- 每个 provider 都通过 `getattr(provider, "close", None)` 选择性关闭；缺失 `close()` 时静默跳过。

根因：

- Root106/108 已经把 provider cleanup 收敛到正式 root：runtime/bootstrap 通过 `WiredProviders.aclose()`，asset-market provider bundle 通过 `AssetMarketProviders.aclose()`，wrapper/partial cleanup 使用各自正式 close contract。
- CLI ops one-shot 仍保留了一份 provider graph 知识，相当于第二套 asset-market provider lifecycle：它知道字段名、去重逻辑和 close 方法形状，却绕过了 `AssetMarketProviders.aclose()` 内部的同步/异步 provider 清理区分。
- 这会让 malformed provider bundle 在服务 runtime 中失败，却在 ops 命令中被“能关就关、不能关就跳过”吞掉。成熟 Kappa/CQRS 里，ops one-shot 不是另一个 runtime；它可以临时 wire provider bundle，但清理必须交回同一个 bundle root。

修复：

- `_close_asset_market_providers(asset_market)` 不再枚举 provider 字段。
- CLI ops 现在要求 `asset_market.aclose()` 是正式 bundle cleanup contract；缺失或非 callable 时抛 `ops_asset_market_providers_aclose_required`。
- 单元测试覆盖 close-only fake bundle 不再触发 provider.close，并覆盖正式 bundle `aclose()` 被调用一次。
- 架构守卫禁止 `_close_asset_market_providers(...)` 中重新出现 provider 字段枚举、`dex_profile_sources` 遍历和 optional `provider.close` probing。

验证：

- RED：`uv run pytest tests/unit/test_ops_backfill_commands.py::test_ops_asset_market_provider_cleanup_requires_bundle_aclose_without_provider_close_probe tests/unit/test_ops_backfill_commands.py::test_ops_asset_market_provider_cleanup_calls_bundle_aclose_once tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_asset_market_provider_cleanup_uses_bundle_aclose_without_provider_field_probe -q` 初始 `3 failed`，证明旧实现调用了 provider.close、没有调用 bundle `aclose()`，且架构守卫抓到 provider 字段枚举和 optional close probe。
- GREEN：同一命令修复后 `3 passed`。
- GREEN：`uv run pytest tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_asset_market_provider_cleanup_uses_bundle_aclose_without_provider_field_probe -q`，`21 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`_close_asset_market_providers(...)` 函数体残留扫描未找到 provider 字段枚举或 optional close probe。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十四：WorkerBase wake_waiter.close 仍接受 awaitable close 兼容形状

现象：

- `WakeWaiter.async_wait(...)` 是正式异步等待合同，但 `WakeWaiter.close()` 是同步关闭方法。
- `WorkerBase._close_wake_waiter()` 直接调用 `result = self.wake_waiter.close()` 后仍用 `inspect.isawaitable(result)` 判断，并在 awaitable 时 `await result`。
- 这让一个 `close()` 返回 awaitable 的 malformed wake waiter 被当成合法 close path，而不是 runtime wiring failure。

根因：

- Root62 已经把 injected wake waiter 的 `wake()`、`async_wait(...)`、`close()` 从 optional `getattr/hasattr` 收敛成直接方法合同，但当时只切掉了“方法是否存在”的兼容，没有切掉“close 返回值形状”的兼容。
- `WakeWaiter` 的生命周期不是“任意 async close shape”：等待需要 async 是因为要把阻塞 `LISTEN` 放到专用 executor；关闭只设置本地事件并 shutdown executor，是同步 `close() -> None`。
- 成熟 Kappa/CQRS worker runtime 不应该让 injected lifecycle fake 随意选择 close 协议。否则 worker stop/aclose 的资源边界会同时支持同步 close 和异步 close 两套合同，后续测试 fake 或旧 adapter 容易继续绕过正式 WakeWaiter 语义。

修复：

- 删除 `worker_base.py` 的 `inspect` import。
- `WorkerBase._close_wake_waiter()` 现在直接调用 `self.wake_waiter.close()`；返回值非 `None` 时抛 `RuntimeError("worker_wake_waiter_close_must_be_sync")`。
- 单元测试覆盖 `close()` 返回 awaitable object 时不再 await，并暴露同步 close contract failure。
- 架构守卫禁止 `WorkerBase` wake-waiter close path 重新出现 `inspect.isawaitable`、`await result` 和 optional wake-waiter probe。

验证：

- RED：`uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_aclose_requires_sync_wake_waiter_close_contract_without_awaitable_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_base_wake_waiter_contract_is_direct_when_injected -q` 初始 `2 failed`，证明旧实现等待了 awaitable close result，且架构守卫抓到 `import inspect`、`inspect.isawaitable`、`await result`。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_worker_base_runtime.py tests/architecture/test_worker_runtime_contracts.py::test_worker_base_wake_waiter_contract_is_direct_when_injected tests/architecture/test_worker_runtime_contracts.py::test_worker_base_advisory_lock_release_contract_is_direct -q`，`26 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`worker_base.py` 残留扫描未找到 `inspect.isawaitable` 或 `await result`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十五：WorkerScheduler.stop 仍通过 _maybe_await 接受同步 lifecycle hook

现象：

- `WorkerScheduler.stop()` 是 runtime worker shutdown 的控制面根。
- 它已经不再枚举 DB pool 字段，但 `worker.stop()`、`worker.aclose()` 和 `self.db.aclose()` 仍统一包在 `_maybe_await(...)` 里。
- `_maybe_await(...)` 使用 `inspect.isawaitable(...)`，导致同步 `stop()` / `aclose()` / `db.aclose()` 返回 `None` 时被当成合法关闭，而不是 malformed runtime wiring。

根因：

- Root100/112 把 DB shutdown 统一到了 `DBPoolBundle.aclose()`，Root114 又把 WorkerBase wake-waiter close 收敛成同步合同；但 scheduler 这个更外层 lifecycle root 仍保留“同步也可以、异步也可以”的兼容入口。
- 这等价于在 worker runtime 边界同时允许两套协议：正式的 `WorkerBase.stop/aclose` async contract，以及测试 fake 或旧 adapter 的同步 shape。
- 成熟 Kappa/CQRS 的 worker supervisor 不应该替错误接线补协议转换。它应该只编排正式 runtime 对象，并让错误 lifecycle hook 在 shutdown 时暴露到同一个 `worker_scheduler_stop_failed` 错误聚合里。

修复：

- 删除 `worker_scheduler.py` 的 `inspect` import 和 `_maybe_await(...)` helper。
- `WorkerScheduler.stop()` 现在直接 `await worker.stop()`、`await worker.aclose()`、`await self.db.aclose()`。
- 单元测试覆盖同步 lifecycle fake 会被聚合为 `TypeError`，证明旧兼容路径不再吞掉 malformed hook。
- 架构守卫禁止 `_maybe_await(...)`、`inspect.isawaitable(...)`、`await _maybe_await(...)` 回流，并要求源码保留三处直接 `await`。

验证：

- RED：`uv run pytest tests/unit/test_worker_scheduler.py::test_scheduler_stop_requires_async_lifecycle_hooks_without_maybe_await_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback -q` 初始 `2 failed`，证明旧实现没有抛出 `worker_scheduler_stop_failed`，且架构守卫抓到 `_maybe_await` / `inspect`。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_worker_scheduler.py tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed tests/architecture/test_worker_runtime_contracts.py::test_worker_scheduler_unhealthy_reasons_use_status_payload_not_worker_attributes -q`，`20 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`worker_scheduler.py` 残留扫描未找到 `_maybe_await`、`inspect.isawaitable` 或 `await _maybe_await`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

## 根因一百一十六：LivePriceGateway fan-out publish 仍接受同步 callback 兼容形状

现象：

- `LivePriceGateway` 已经 hard-cut 成 cache/fan-out worker：它只读 `token_capture_tier` 和最新 `market_ticks`，不再拥有上游 price provider，也不写事实。
- 生产 wiring 中 `worker_factories/asset_market.py` 传入的是 `ctx.hub.publish`，即 `PublicWebSocketHub.publish(payload)` 的 async 合同。
- 但 `_publish(payload)` 仍执行 `result = self.on_live_market_update(payload)`，再用 `inspect.isawaitable(result)` 决定是否 await。同步 `list.append` 风格 callback 会被当作合法 fan-out callback。

根因：

- Live fan-out 是展示层便利状态，不是业务事实；这更要求其 runtime 边界单一、可验证。否则测试 fake 的同步 callback 会继续塑造生产代码的协议。
- `on_live_market_update` 实际上不是“任意 callback”，而是 WebSocket hub 的 async publish root。让它同时接受 sync/async 结果，会把 cache-only worker 变成一个带协议适配逻辑的小型 dispatcher。
- 成熟 Kappa/CQRS 中，fan-out 失败可以是运行时 wiring failure，但不应该通过兼容判断被静默降级。同步 callback 返回 `None` 应暴露为 malformed wiring，而不是被视为“发布完成”。

修复：

- 删除 `live_price_gateway.py` 的 `inspect` import。
- `on_live_market_update` 类型收敛为 `Callable[[dict[str, Any]], Awaitable[None]] | None`。
- `_publish(payload)` 现在直接 `await self.on_live_market_update(payload)`。
- 单元测试把正常 publisher fake 改成 async `RecordingLivePublisher.publish(...)`；新增同步 callback 用例证明旧兼容路径不再被接受。
- 架构守卫禁止 `inspect.isawaitable(...)`、`await result` 和 `result = self.on_live_market_update(payload)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_live_price_gateway.py::test_live_price_gateway_requires_async_publish_contract_without_sync_callback_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_live_price_gateway_publish_uses_async_hub_contract_without_isawaitable_fallback -q` 初始 `2 failed`，证明同步 callback 旧实现不抛错，且架构守卫抓到 `inspect.isawaitable`。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_live_price_gateway.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_live_price_gateway_publish_uses_async_hub_contract_without_isawaitable_fallback tests/architecture/test_runtime_lifecycle_hard_cut.py::test_manifest_classifies_cache_and_delivery_without_product_fact_drift -q`，`7 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`live_price_gateway.py` 生产残留扫描未找到 `inspect.isawaitable`、`await result` 或 callback result 兼容分支。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 117：GMGN DirectWS 上游帧投递仍把 collector handler 当成 sync/async callback

现象：

- `bootstrap(...)` 在启用 collector 时把 `collector.handle_frame` 注入 GMGN upstream factory。
- `CollectorService.handle_frame(...)` 是 async 热路径：解析 GMGN frame、写 raw frame、进入 ingest 事实链路。
- 但 `DirectGmgnWebSocketClient._receive_frames(...)` 仍执行 `result = self.on_frame(frame)`，再用 `inspect.isawaitable(result)` 决定是否 await。同步测试 fake 返回 `None` 时会被视为投递完成。
- `UpstreamClientFactory` 类型仍是 `Callable[..., Any]`，把真实 async collector 合同退化成了“任意 callback”。

根因：

- GMGN DirectWS 是 provider adapter，不应该在 worker 热路径里承载 callback 形状适配。它的唯一生产下游是 collector 的 async `handle_frame(...)`。
- 同步 callback 兼容让单测便利反过来定义了生产协议：测试里 `lambda _: None` 能跑，生产代码就必须保留 `inspect.isawaitable(...)`。
- 成熟 Kappa/CQRS 的 ingest 边界应当让 malformed wiring 立即失败；否则 raw frame 是否真正进入事实链路会被 callback 返回值形状影响，破坏“事实写入链路单一、可审计”的约束。

修复：

- 删除 `direct_ws.py` 的 `inspect` import 和 conditional await 分支。
- `DirectGmgnWebSocketClient.on_frame` 收敛为 `Callable[[str], Awaitable[None]]`。
- `_receive_frames(...)` 现在直接 `await self.on_frame(frame)`，同步 callback 返回 `None` 会作为 malformed runtime wiring 暴露。
- `UpstreamClientFactory` 和 GMGN provider wiring 同步收敛为 async frame handler 类型。
- 正常单元测试 fake 改为 async handler；新增同步 handler 用例证明旧兼容路径不再被接受。
- 架构守卫禁止 `inspect.isawaitable(...)`、`await result`、`result = self.on_frame(frame)` 和旧 `Callable[[str], Any | Awaitable[Any]]` 类型回流。

验证：

- RED：`uv run pytest tests/unit/test_direct_ws.py::DirectWebSocketProtocolTests::test_direct_client_requires_async_frame_handler_without_isawaitable_fallback tests/architecture/test_worker_runtime_contracts.py::test_direct_gmgn_ws_frame_handler_uses_async_collector_contract_without_isawaitable_fallback -q` 初始 `2 failed`，证明同步 frame handler 被旧实现接受，且架构守卫抓到 conditional await fallback。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/test_direct_ws.py tests/unit/test_gmgn_token_payload.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_bootstrap_runtime_preserves_enabled_collector_injection_and_attaches_upstream_client tests/architecture/test_worker_runtime_contracts.py::test_direct_gmgn_ws_frame_handler_uses_async_collector_contract_without_isawaitable_fallback tests/architecture/test_worker_runtime_contracts.py::test_collector_upstream_client_close_contract_is_direct -q`，`16 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`direct_ws.py` / GMGN provider wiring 生产残留扫描未找到 `inspect.isawaitable`、`await result` 或旧 sync-callback result 分支。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 118：AgentExecution capacity reservation release 仍接受 awaitable 释放结果

现象：

- `AgentExecutionGateway.try_reserve(...)` 创建的 release callback 实际只做同步资源归还：释放 lane semaphore、global semaphore，并更新 in-flight 计数。
- 但 `AgentCapacityReservation.ReleaseCallback` 类型是 `Callable[[], None | Awaitable[None]]`。
- `AgentCapacityReservation.release()` 执行 `result = release()` 后，如果 `result is not None` 就 `await result`。这让 async release fake 或未来 async cleanup 被当成合法执行平面生命周期。

根因：

- Agent execution 的 capacity reservation 是资源 accounting，不是 provider IO，也不是 domain cleanup。其 release 必须是一个确定的同步临界区，否则 lane/global/RPM 资源归还会变成双形态生命周期。
- 当前 async `release()` 方法是外部调用 API 形状：worker/gateway 可以统一 `await reservation.release()`。但内部 `_release` callback 不应该因此变成 async hook。
- 成熟的执行平面应区分“public async method for caller ergonomics”和“internal sync resource release contract”。旧实现把这两层混在一起，和 DB pool / wake waiter / provider cleanup 的兼容根因一致。

修复：

- `ReleaseCallback` 收敛为 `Callable[[], None]`。
- `AgentCapacityReservation.release()` 仍保持 async public method，但 `_release()` 返回非 `None` 时直接抛 `RuntimeError("agent_capacity_release_must_be_sync")`。
- 新增单元测试证明 awaitable release result 不再被 await。
- 新增 agent execution 架构守卫禁止 `ReleaseCallback = Callable[[], None | Awaitable[None]]`、`Awaitable[None]]` 和 `await result` 回流。

验证：

- RED：`uv run pytest tests/unit/integrations/model_execution/test_agent_execution_audit.py::test_capacity_reservation_release_requires_sync_callback_without_awaitable_fallback tests/architecture/test_agent_execution_plane_contracts.py::test_agent_capacity_reservation_release_is_sync_contract_without_awaitable_fallback -q` 初始 `2 failed`，证明旧实现没有抛错且架构守卫抓到 awaitable release fallback。
- GREEN：同一命令修复后 `2 passed`。
- GREEN：`uv run pytest tests/unit/integrations/model_execution/test_agent_execution_audit.py tests/unit/integrations/model_execution/test_agent_execution_gateway.py tests/architecture/test_agent_execution_plane_contracts.py::test_agent_capacity_reservation_release_is_sync_contract_without_awaitable_fallback -q`，`45 passed`。
- GREEN：targeted ruff、targeted mypy 通过；`agent_execution.py` 生产残留扫描未找到 awaitable release fallback token。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 119：OpenNews REST poster 仍接受同步返回值兼容形状

现象：

- OpenNews 已经 hard-cut 为 `news_fetch` 内的 REST-only provider fact source，生产默认 HTTP client 是 async `httpx.AsyncClient`。
- 但 `OpenNewsFeedClient._fetch_rest_entries(...)` 仍执行 `payload_result = self._post_json(...)`，再用 `inspect.isawaitable(payload_result)` 决定是否 await。
- 这让同步测试 fake 返回 `dict` 也被当成合法 transport，使 OpenNews 的 runtime 合同变成“同步或异步都可”的双形态 callback。

根因：

- REST-only 解决的是 WebSocket/hybrid fetch mode 的入口问题，但旧代码没有继续收紧 transport 层的调用合同。
- 成熟 Kappa/CQRS 的 provider adapter 应当只把上游观察转成事实输入；它不应该在热路径里承担测试便利造成的协议适配。
- 同步 poster 兼容会让“是否真的完成 HTTP provider fetch”取决于返回值形状探测，而不是明确的 async HTTP contract。这类兼容会沿着测试 fake、worker wiring、错误处理继续扩散，最终削弱 provider fact ingestion 的可审计性。

修复：

- 删除 OpenNews client 中的 `inspect.isawaitable(...)` fallback。
- 新增 `_OpenNewsPostJson` Protocol，表达真实合同：`post_json(url, *, token, body)` 必须返回 `Awaitable[Mapping[str, Any]]`。
- `_fetch_rest_entries(...)` 现在直接 `await self._post_json(...)`；同步返回值会以 malformed runtime wiring 暴露。
- 单元测试覆盖同步 poster 不再被接受；架构守卫禁止 `isawaitable`、二次 `await payload_result` 和旧 `Callable[..., Any]` 类型回流。

验证：

- RED：`uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_client_requires_async_rest_poster_without_isawaitable_fallback tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_poster_uses_async_http_contract_without_isawaitable_fallback -q` 初始 `2 failed`，证明旧实现接受同步 poster 且架构守卫抓到 conditional await fallback。
- GREEN：同一命令修复后 `2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 120：PostgreSQL health check 仍跳过缺失 commit/rollback 的 fake connection

现象：

- `postgres_health_check(...)` 执行 liveness SQL 和 migration version SQL 后，只在 `hasattr(conn, "commit")` 为真时提交。
- 异常路径也只在 `hasattr(conn, "rollback")` 为真时回滚。
- 因此只实现 `execute(...)` 的测试 fake 可以返回健康状态，失败探测也可以在没有 rollback cleanup 的情况下返回原始错误，掩盖连接合同不完整。

根因：

- health check 看起来只是状态探针，但它是 `/readyz`、启动检查、ops diagnostics、CLI DB health 共同使用的 PostgreSQL runtime contract。
- 前面 Root100/112 已经把 DB pool lifecycle 收敛到正式 psycopg contract；但 health check 仍把连接 cleanup 当成可选能力，留下了一条 fake connection 兼容入口。
- 成熟 Kappa/CQRS 中，health/status 面虽然不写业务事实，但它决定系统是否可服务、是否迁移就绪、ops 是否可信。跳过 commit/rollback 会让测试 fake 和 malformed runtime connection 看起来可用，削弱 PostgreSQL 可预测性。

修复：

- `postgres_health_check(...)` 成功探测后直接调用 `conn.commit()`。
- 探测失败后直接调用 `conn.rollback()`；如果 rollback 本身缺失或失败，则返回 failed liveness payload，并记录 `original_error` / `original_detail`。
- 正常 fake connection 显式实现 `commit()` / `rollback()`；新增缺 commit 和缺 rollback 用例证明旧兼容路径不再被接受。
- 架构守卫禁止 `hasattr(conn, "commit")` / `hasattr(conn, "rollback")` 和对应 `getattr(...)` probe 回流。

验证：

- RED：`uv run pytest tests/unit/test_postgres_client.py::test_postgres_health_check_requires_commit_contract_without_optional_probe tests/unit/test_postgres_client.py::test_postgres_health_check_reports_missing_rollback_contract_without_optional_probe tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_postgres_health_check_uses_formal_commit_rollback_contract_without_optional_probe -q` 初始 `3 failed`，证明旧实现跳过缺失 cleanup contract。
- GREEN：同一命令修复后 `3 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 121：OpenNews sync-worker bridge 仍用 optional coroutine close probe

现象：

- OpenNews `fetch()` 是同步 worker 入口，但内部 REST fetch 是 async coroutine，由 `_run_rest_fetch(...)` 用 `asyncio.run(...)` 桥接。
- 当 `fetch()` 被误用于已有 event loop 时，旧实现执行 `close = getattr(coro, "close", None)`，如果 callable 才关闭 coroutine，然后抛同步 worker 误用错误。
- 这让 `_run_rest_fetch(coro: Any)` 接受任意 awaitable 形状；一个没有 `close()` 的 awaitable 会被当成可兼容输入，跳过 cleanup contract。

根因：

- Root119 已经把 OpenNews poster 收紧成 async-only，但 sync/async bridge 还保留了“像 coroutine 就试着 close”的测试便利思路。
- `_run_rest_fetch` 的生产调用点只传入 `_fetch_rest_entries(...)` 创建的真实 coroutine；因此 private bridge 的合同应该是 formal coroutine，而不是任意 awaitable。
- 成熟 Kappa/CQRS 的 worker adapter 边界应尽早暴露 malformed wiring。否则 provider fetch 路径虽然 REST-only，却仍保留一条按对象形状猜 lifecycle 的兼容入口。

修复：

- `_run_rest_fetch` 参数从 `Any` 收敛为 `Coroutine[Any, Any, _T]`，返回 `_T`。
- 在 active event loop 误用路径直接调用 `coro.close()`，不再通过 `getattr(coro, "close", None)` / `callable(close)` 探测。
- 单元测试覆盖无 `close()` 的 awaitable 不再被吞成 worker misuse RuntimeError；架构守卫禁止 `coro: Any`、`getattr(coro, "close", None)` 和 `if callable(close)` 回流。

验证：

- RED：`uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_run_rest_fetch_requires_formal_coroutine_close_contract_without_optional_probe tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_fetch_bridge_uses_formal_coroutine_close_contract_without_optional_probe -q` 初始 `2 failed`，证明旧实现接受无 close 的 awaitable 并保留 optional close probe。
- GREEN：同一命令修复后 `2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 122：`require_transaction(...)` 仍允许缺失 psycopg transaction status 的 fake connection

现象：

- `parallax.platform.db.postgres_client.require_transaction(conn, operation=...)` 通过 `getattr(conn, "info", None)` 探测连接信息。
- 如果 `conn.info` 缺失，或读取 `info.transaction_status` 抛异常，旧实现直接 `return`。
- 因此 `require_transaction(object(), operation="fake_write")` 会通过，无法证明内层写入真的处在 PostgreSQL transaction 中。

根因：

- 前面大量 repository/worker 根修都把内层写入口收敛到 `repos.require_transaction(...)`，让写入必须发生在外层 `RepositorySession.transaction()` / `unit_of_work()` 内。
- 但最底层 transaction guard 仍保留 fake connection 兼容：没有 psycopg `conn.info.transaction_status` 时视为“无法判断，所以通过”。
- 这会削弱所有依赖 `require_transaction(...)` 的根修证据。成熟 Kappa/CQRS 中，transaction guard 不是测试便利函数，而是 PostgreSQL 原子写边界的证明；缺失 transaction-status evidence 必须 fail fast。

修复：

- `require_transaction(...)` 现在直接读取 `conn.info.transaction_status`。
- 缺失 `conn.info` 或 `transaction_status` 时抛 `RuntimeError("{operation}_requires_transaction_status_contract")`。
- 真实 `IDLE` 状态仍保留原来的 `RuntimeError("{operation}_requires_explicit_transaction")`。
- 单元测试覆盖 missing contract、IDLE、INTRANS 三种状态；旧 integration 测试的 fake-object 期望同步改为拒绝；架构守卫禁止 `getattr(conn, "info", None)`、`if info is None`、`except Exception` 和静默 `return` 回流。

验证：

- RED：`uv run pytest tests/unit/test_postgres_client.py::test_require_transaction_rejects_fake_connection_without_transaction_status_contract tests/unit/test_postgres_client.py::test_require_transaction_rejects_idle_transaction_status tests/unit/test_postgres_client.py::test_require_transaction_accepts_active_transaction_status tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_postgres_require_transaction_uses_formal_transaction_status_without_optional_info_fallback -q` 初始 `2 failed, 2 passed`，证明 fake connection 仍通过且架构守卫抓到 optional info fallback。
- GREEN：同一命令修复后 `4 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 123：enabled 的 Asset Market provider worker 缺 provider 时被伪装成 disabled

现象：

- `construct_asset_market_workers(...)` 中，`asset_profile_refresh` 和
  `resolution_refresh` 明明由 `workers.yaml` 设置为 enabled。
- 但当 DEX profile provider / discovery provider 缺失时，旧实现构造
  `disabled_worker(...)`。
- 结果是 worker status 里的 `enabled` 变成 `False`，`effective_status`
  变成 `disabled`，`WorkerScheduler.unhealthy_reasons()` 不会把这条缺失
  provider 的事实刷新链路报为异常。

根因：

- `disabled` 和 `unavailable` 的语义被混用。
- `disabled` 应该只表示 operator 明确关闭；而 enabled worker 缺少运行时
  provider 依赖，是 runtime wiring / provider 配置不可用，必须影响
  readiness。
- 对 Kappa/CQRS 来说，这不是普通状态文案问题：`asset_profile_refresh`
  写 `asset_profiles` source cache，`resolution_refresh` 刷新
  `token_intent_resolutions`、`registry_assets` 和 identity facts。把缺失
  provider 隐藏成 disabled，会让上游事实链路断裂但状态面显示“用户关了”，
  后续 Token Radar / Profile / Pulse 只能看到陈旧或缺失事实。

修复：

- `asset_profile_refresh` enabled 但缺少 profile provider 时，构造
  `unavailable_worker(ctx, "asset_profile_refresh", "missing_asset_profile_provider")`。
- `resolution_refresh` enabled 但缺少 discovery provider 时，构造
  `unavailable_worker(ctx, "resolution_refresh", "missing_asset_discovery_provider")`。
- 单元测试验证 status 保持 `enabled=True`、`effective_status=unavailable`，
  且 unhealthy reasons 包含对应缺 provider reason。
- 架构守卫禁止这两个 enabled provider-worker 分支回退到 `disabled_worker(...)`。

验证：

- RED：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_enabled_asset_profile_refresh_without_profile_provider_surfaces_unavailable tests/unit/test_bootstrap_worker_runtime_wiring.py::test_enabled_resolution_refresh_without_discovery_provider_surfaces_unavailable tests/architecture/test_worker_runtime_contracts.py::test_enabled_asset_market_provider_workers_missing_provider_surface_unavailable -q`
  初始 `3 failed`，证明旧实现把 enabled worker 缺 provider 降级成 disabled。
- GREEN：同一命令修复后 `3 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 124：CEX/News worker factory 把缺失 WiredProviders domain root 当成空 provider set

现象：

- `construct_cex_market_intel_workers(...)` 通过
  `getattr(ctx.providers, "cex_market_intel", None)` 读取 provider bundle。
- `construct_news_intel_workers(...)` 通过
  `getattr(ctx.providers, "news_intel", None)` 读取 provider bundle。
- 如果整个 domain bundle root 缺失，旧实现不会暴露 malformed runtime
  wiring，而是继续构造 `unavailable_worker(...)`，把组合根缺失伪装成
  普通具体 provider 缺失。

根因：

- 代码混淆了两层合同：`WiredProviders` 的 domain bundle 字段是 runtime
  composition root；bundle 内部的具体 provider handle 才允许因配置或凭证
  不存在而 unavailable。
- 成熟 Kappa/CQRS 里，worker ownership、manifest status 和事实链路启动
  必须依赖显式组合根。缺失 `ctx.providers.news_intel` 或
  `ctx.providers.cex_market_intel` 说明 runtime wiring 形状错误，不是 provider
  健康状态。
- optional `getattr(..., None)` 会让 malformed root wiring 进入正常状态面，
  削弱启动期 fail-fast，也让 operator 很难区分“系统装配错了”和“某个上游
  provider 暂不可用”。

修复：

- CEX factory 直接读取 `ctx.providers.cex_market_intel`。
- News factory 直接读取 `ctx.providers.news_intel`。
- 缺失整个 domain bundle root 时抛出 `AttributeError`，作为 malformed
  runtime wiring 暴露。
- 已存在 bundle 内缺少具体 `oi_market`、`feed_client`、`brief_provider` 等
  provider 时，仍按 worker 合同返回 redacted `unavailable_worker(...)`。
- 架构守卫禁止 `getattr(ctx.providers, "cex_market_intel", None)` 和
  `getattr(ctx.providers, "news_intel", None)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py::test_worker_factory_requires_cex_market_intel_provider_bundle_root tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_requires_news_intel_provider_bundle_root tests/architecture/test_worker_runtime_contracts.py::test_worker_factories_use_formal_wired_provider_domain_roots_without_optional_probe -q`
  初始 `3 failed`，证明旧实现把缺失 domain root 转换成普通 unavailable
  worker。
- GREEN：同一命令修复后 `3 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 125：status/diagnostics 把缺失 Runtime provider domain root 当成 disabled provider

现象：

- `/readyz` 的 `_stream_dex_market(...)` 通过
  `getattr(runtime, "providers", None)` 和
  `getattr(providers, "asset_market", None)` 读取 provider root。
- ops diagnostics 的 provider inventory 也通过
  `getattr(getattr(runtime, "providers", None), "asset_market", None)` 读取
  Asset Market bundle。
- 如果 `runtime.providers.asset_market` 整个组合根缺失，旧实现不会暴露
  malformed runtime wiring，而是把 OKX provider 状态显示成 disconnected /
  disabled，或把 provider health 列表显示成空。

根因：

- Root124 已经把 worker factory 的 `WiredProviders` domain root 收紧成
  formal composition contract，但 status surface 还保留了同一类 optional
  runtime-root 探测。
- `/readyz`、`/api/status` 和 ops diagnostics 不是“尽量展示一点”的旁路；
  它们是 operator 判断 runtime wiring 是否成立的合同面。
- 缺失 `runtime.providers.asset_market` 表示 bootstrap/Runtime 装配形状
  已经坏了，不能被解释为“Asset Market provider 未配置”。只有 bundle
  已经存在时，里面的 `stream_dex_market=None` 或其他具体 provider handle
  才能被解释成 disabled/disconnected IO state。

修复：

- `/readyz` 直接读取 `runtime.collector.upstream_client` 和
  `runtime.providers.asset_market.stream_dex_market`。
- ops diagnostics 直接读取 `runtime.providers.asset_market` 和
  `runtime.collector.upstream_client`。
- bundle 内 concrete provider handle 仍允许为 `None`，并继续显示
  disabled/disconnected；缺 bundle root 则 fail fast。
- 架构守卫禁止 status/diagnostics provider-root helper 回退到
  `getattr(runtime, "providers", None)`、嵌套 `getattr(..., "asset_market",
  None)` 或 collector upstream optional probe。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_requires_asset_market_provider_bundle_root tests/architecture/test_worker_runtime_contracts.py::test_status_provider_roots_use_formal_runtime_provider_bundle_contract -q`
  初始 `2 failed`，证明旧实现把缺失 provider bundle 转换成 empty/disabled
  状态。
- GREEN：同一命令修复后 `2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 126：ops diagnostics collector section 把缺失 collector status 合同藏成空 details

现象：

- `_collector_payload(...)` 通过 `getattr(runtime, "collector", None)`、
  `getattr(collector, "status", None)`、`getattr(status_object, "to_dict",
  None)` 和 `callable(to_dict)` 读取 collector 状态。
- 如果 collector 存在但缺少 `status.to_dict()`，旧实现返回
  `details={}`，并可能继续把 collector section 标成 `ok`。
- 这会让 operator 看到“collector 没细节但状态正常”，而不是看到 runtime
  装配/状态合同已经坏掉。

根因：

- Root125 已经证明 status/diagnostics 是 runtime contract surface；collector
  section 也属于同一层，而不是随意容错的展示层。
- `CollectorService.status` 是 worker/ingest 入口的正式状态合同，包含
  snapshot gate counters、frame/event counters 和时间戳。缺这个合同会直接影响
  ops 对 provider frame、ingest 活性和 snapshot gate 的判断。
- optional probe 把“没有状态合同”降级成“没有细节”，等于把 runtime wiring
  错误变成了健康但信息少的状态。

修复：

- `_collector_payload(...)` 直接调用 `runtime.collector.status.to_dict()`。
- `to_dict()` 返回值必须是 mapping；非 mapping 抛
  `collector_status_payload_must_be_dict`。
- `_collector_payload(...)` 直接读取 `runtime.collector.upstream_client`。
- 架构守卫禁止 collector/status/to_dict/upstream 的 optional `getattr(...)`
  probe 和 empty-details fallback 回流。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_collector_status_contract_failure_is_unknown_section tests/architecture/test_worker_runtime_contracts.py::test_ops_diagnostics_collector_section_uses_formal_collector_status_contract -q`
  初始 `2 failed`，证明旧 helper 把缺失 collector status 合同藏成空
  details。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`140 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 127：ops diagnostics provider health 把缺失 bundle 字段藏成空 inventory

现象：

- `_asset_market_provider_health(...)` 已经直接读取
  `runtime.providers.asset_market`，但随后又通过
  `getattr(asset_market, "provider_health", ()) or ()` 读取 provider health。
- 如果 `AssetMarketProviders` bundle 存在但缺少 `provider_health` 字段，旧实现
  返回空 provider 列表。
- operator 会看到“Asset Market provider inventory 为空”，而不是看到
  provider-bundle 状态合同已经损坏。

根因：

- Root125 收紧的是 provider domain root；Root127 继续收紧 bundle 内的正式
  status 字段。
- `provider_health` 是 `AssetMarketProviders` dataclass 的正式字段，用于表达
  OKX、GMGN、Binance 等 provider 的 configured/capability/error 证据。
- 缺这个字段不是“没有配置 provider”，而是 wiring shape 与 runtime contract
  不一致。把它降级成空列表，会让 diagnostics 低估 provider 层损坏范围。

修复：

- `_asset_market_provider_health(...)` 直接读取
  `runtime.providers.asset_market.provider_health`。
- 架构守卫禁止 `getattr(asset_market, "provider_health", ())` 这类 optional
  fallback 回流。
- 单测用畸形 asset-market bundle 证明缺失 `provider_health` 必须暴露为
  `AttributeError`，而不是空 provider inventory。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_requires_asset_market_provider_health_contract tests/architecture/test_worker_runtime_contracts.py::test_status_provider_roots_use_formal_runtime_provider_bundle_contract -q`
  初始 `2 failed`，证明旧 helper 把缺失 provider-health 合同藏成空 provider
  list。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`141 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 128：Asset Market worker factory 把缺失 bundle 字段误判成缺 provider

现象：

- `construct_asset_market_workers(...)` 已经直接读取
  `ctx.providers.asset_market`，但随后对 bundle 内字段仍使用
  `getattr(asset_market, "...", None)` 或
  `getattr(asset_market, "dex_profile_sources", ())`。
- 如果 `AssetMarketProviders` bundle 存在但缺少 `cex_market`、
  `dex_quote_market`、`dex_profile_sources`、`dex_discovery_market` 或
  `stream_dex_market` 字段，旧实现不会暴露 malformed bundle shape。
- 这些缺字段会被解释成具体 provider 为 `None` 或空 tuple，于是 worker 被构造成
  `unavailable_worker(...)`，operator 会误以为是 provider 未配置，而不是 runtime
  wiring 合同损坏。

根因：

- Root123 明确了“enabled worker 缺具体 provider”应显示 unavailable；Root128
  区分的是更上一层：bundle 字段是否存在。
- 成熟 Kappa/CQRS 的 composition root 应该让 wiring shape fail fast。只有
  字段存在且值为 `None`，才表示具体 provider IO 不可用。
- optional field probe 把“bundle 合同缺字段”降级成“业务 provider 缺失”，会让
  readiness/unhealthy reason 低估 bootstrap/provider wiring 的真实故障。

修复：

- `construct_asset_market_workers(...)` 直接读取
  `asset_market.cex_market`、`asset_market.dex_quote_market`、
  `asset_market.dex_profile_sources`、`asset_market.dex_discovery_market` 和
  `asset_market.stream_dex_market`。
- `dex_profile_sources` 仍允许字段值为空，空值继续让 enabled
  `asset_profile_refresh` 显示 `missing_asset_profile_provider`。
- 架构守卫禁止这些 bundle 字段的 optional `getattr(...)` probe 回流。

验证：

- RED：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_asset_market_worker_factory_requires_formal_provider_bundle_fields tests/architecture/test_worker_runtime_contracts.py::test_asset_market_worker_factory_uses_formal_provider_bundle_fields_without_optional_probe -q`
  初始 `2 failed`，证明旧 factory 把缺失 bundle 字段藏成普通 unavailable
  provider。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`145 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 129：CEX/News worker factory 把缺失 bundle 字段误判成缺 provider

现象：

- `construct_cex_market_intel_workers(...)` 已经直接读取
  `ctx.providers.cex_market_intel`，但随后仍通过
  `getattr(cex_providers, "oi_market", None)` 和
  `getattr(cex_providers, "coinglass_derivatives", None)` 读取 bundle 字段。
- `construct_news_intel_workers(...)` 同样直接读取
  `ctx.providers.news_intel` 后，又通过
  `getattr(news_providers, "feed_client", None)` 和
  `getattr(news_providers, "brief_provider", None)` 读取 bundle 字段。
- 如果 bundle 存在但缺字段，旧实现会构造普通 unavailable worker，而不是暴露
  malformed provider-bundle wiring。

根因：

- Root124 只切掉了 provider domain root 的 optional probe；Root129 继续切掉
  domain bundle 内字段的 optional probe。
- CEX/News provider bundle 是 runtime composition contract。字段存在但值为
  `None` 表示具体 provider 不可用；字段不存在表示 provider wiring shape
  已经坏了。
- 把缺字段解释成 `None` 会污染 worker status：operator 看到的是
  `missing_cex_oi_market_provider` 或 `missing_news_intel_feed_client`，但真实问题
  是 bootstrap/provider bundle 没有按合同装配。

修复：

- CEX factory 直接读取 `cex_providers.oi_market` 和
  `cex_providers.coinglass_derivatives`。
- News factory 直接读取 `news_providers.feed_client` 和
  `news_providers.brief_provider`。
- 架构守卫禁止这些字段的 optional `getattr(...)` probe 回流。

验证：

- RED：`uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py::test_worker_factory_requires_cex_market_intel_provider_bundle_fields tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_requires_news_intel_provider_bundle_fields tests/architecture/test_worker_runtime_contracts.py::test_cex_and_news_worker_factories_use_formal_provider_bundle_fields_without_optional_probe -q`
  初始 `3 failed`，证明旧 factory 把缺失 CEX/News bundle 字段藏成普通
  unavailable provider。
- GREEN：同一命令修复后 `3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`155 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 130：News provider-contract status 把缺失 settings 合同藏成空配置源

现象：

- `/api/status` 的 `_news_provider_contract_payload(...)` 通过
  `getattr(getattr(runtime.settings, "news_intel", None), "sources", ())`
  读取 News 配置源。
- 如果 `runtime.settings` 缺少 `news_intel`，旧实现不会暴露 malformed runtime
  settings shape，而是把 `configured_sources` 设为空 tuple。
- operator 会看到 News provider contract 没有配置源，或者只看到后续 DB/schema
  诊断，而不是看到 runtime settings 合同已经缺字段。

根因：

- News provider contract 是 status surface，不是 best-effort 展示层。它用于判断
  configured provider types、runtime supported types 和 PostgreSQL schema
  constraint 是否一致。
- `Settings.news_intel.sources` 是正式 runtime configuration contract。缺
  `news_intel` 表示配置对象装配 shape 坏了，不等价于“没有配置 News source”。
- optional nested `getattr(...)` 把配置合同错误降级成空源列表，会让
  provider-contract status 低估配置装配问题。

修复：

- `_news_provider_contract_payload(...)` 直接读取
  `runtime.settings.news_intel.sources`。
- 架构守卫禁止 nested `getattr(..., "news_intel", None)` / empty-source fallback
  回流。
- 单测用缺 `news_intel` 的 runtime settings fake 证明必须抛 `AttributeError`，
  而不是生成空配置源 payload。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py::test_runtime_status_news_provider_contract_requires_news_intel_settings_contract tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_contract_validation_uses_static_contract_not_provider_object -q`
  初始 `2 failed`，证明旧 status helper 把缺失 News settings 合同藏成空
  configured source set。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py tests/architecture/test_news_intel_kiss_simplification.py -q`
  通过，`45 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 131：ops diagnostics config/watchlist 把缺失 runtime settings 藏成空配置/idle

现象：

- ops diagnostics 的 `_config_payload(...)` 先
  `getattr(runtime, "settings", None)`，再对 `app_home`、`handles`、
  `upstream_channels`、provider configured flags、News enabled、notification
  rules 逐个做默认值 fallback。
- `_watchlist_domain(...)` 通过
  `getattr(getattr(runtime, "settings", None), "handles", ())` 读取 handles。
- 如果 `runtime.settings` 缺失或 shape 不完整，operator 看到的是
  `config_path=None`、provider flags 全 false、`handles_count=0`、
  watchlist `status=idle`，而不是 runtime configuration contract 已经坏了。

根因：

- ops diagnostics 是控制面 read model，不是“尽量拼一个页面”的展示 helper。
  它解释 worker 为什么没有写入事实、为什么 provider/配置没有驱动下游投影。
- 在 Kappa/CQRS 里，业务事实仍然只在 PostgreSQL；但控制面状态必须诚实说明
  runtime composition/configuration 是否有效。把缺 settings 降级成空配置，会让
  排障方向从“runtime settings 装配坏了”偏到“用户没有配置 handles/provider/news”。
- 这类 optional `getattr(..., default)` 是兼容性残留：它让测试 fake 和旧
  runtime shape 继续通过，同时削弱了正式 `Settings` 契约。

修复：

- `_config_payload(...)` 直接读取 `runtime.settings`，并直接读取
  `settings.app_home`、`settings.handles`、`settings.upstream_channels`、
  `settings.gmgn_configured`、`settings.okx_dex_configured`、
  `settings.llm_configured`、`settings.news_intel_enabled` 和
  `settings.notification_rules`。
- `_watchlist_domain(...)` 直接读取 `runtime.settings.handles`。
- 架构守卫禁止 `getattr(runtime, "settings", None)` 和 settings 字段 fallback
  回流；单测证明缺 `runtime.settings` 必须抛 `AttributeError`。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_config_requires_runtime_settings_contract tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_watchlist_requires_runtime_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_ops_diagnostics_config_uses_formal_runtime_settings_contract_without_optional_probe -q`
  初始 `3 failed`，证明旧 diagnostics 把缺失 settings 合同藏成空
  config/idle watchlist。
- GREEN：同一命令修复后 `3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`146 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 132：ops diagnostics queues 把缺失 DB/API pool 合同藏成空队列

现象：

- ops diagnostics 的 `_queues_payload(...)` 先
  `getattr(runtime, "db", None)`，再 `getattr(db, "api_pool", None)`，
  最后 `getattr(api_pool, "connection", None)`。
- 如果 runtime 缺 `db.api_pool.connection`，旧实现直接返回 `[]`。
- operator 会看到没有 queue summary，而不是看到 diagnostics 无法读取
  manifest-owned queue/control-plane state。

根因：

- queue summaries 是控制面诊断，不是可选装饰字段。它们解释 dirty target、
  job、delivery、terminal ledger 等队列是否 blocked/due/running。
- 在 Kappa/CQRS 里，worker 的事实写入和 read-model 投影都依赖 PostgreSQL；
  如果 diagnostics 不能打开正式 API pool，就应该暴露 runtime DB wiring 错误。
- 把缺 DB pool 降级成 `queues=[]` 会让“观测系统坏了”看起来像“所有队列都没有
  状态”，这会误导 worker backlog、wake/catch-up 和 SQL queue 性能排查。

修复：

- `_queues_payload(...)` 直接使用 `runtime.db.api_pool.connection()`。
- 架构守卫禁止 `_queues_payload(...)` 内的 `getattr(runtime, "db", None)`、
  `getattr(db, "api_pool", None)`、`getattr(api_pool, "connection", None)`、
  `if not callable(connection)` 和 `return []` fallback 回流。
- 单测用缺 `api_pool` 的 runtime fake 证明必须抛 `AttributeError`，而不是返回
  空 queue list。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_queues_require_api_pool_connection_contract tests/architecture/test_worker_runtime_contracts.py::test_ops_diagnostics_queues_use_formal_api_pool_connection_contract -q`
  初始 `2 failed`，证明旧 diagnostics 把缺失 DB/API pool 合同藏成空队列。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`148 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 133：worker queue_health 把缺失 API pool connection 合同藏成 unavailable queue

现象：

- `fill_worker_queue_healths(...)` 通过 `getattr(runtime, "db", None)`、
  `getattr(db, "api_pool", None)`、`getattr(api_pool, "connection", None)`
  读取 queue-health DB 入口。
- 如果 runtime 缺 `db.api_pool.connection`，旧实现会把每个 manifest queue
  填成 unavailable，并使用 legacy `missing_connection` error code。
- `/readyz` / `/api/status` 会看到 queue health unavailable，而不是看到
  runtime DB contract 本身缺失。

根因：

- queue health 是 worker 控制面状态：它解释 dirty target、job、delivery、
  terminal evidence 是否 due/running/blocked。它不是 product truth，但它是
  worker 排障的正式读模型。
- 缺 `runtime.db.api_pool.connection` 是 runtime wiring/configuration 错误；
  这和“DB 存在但连接 context enter 失败”或“queue SQL 查询失败”不是一类问题。
- 保留 `missing_connection` 兼容码会让测试 fake 和不完整 runtime shape 继续通过，
  并把 wiring contract 缺失伪装成普通 queue unavailable。

修复：

- `fill_worker_queue_healths(...)` 先直接构造
  `runtime.db.api_pool.connection()` connection context；缺 DB/API pool/connection
  会直接失败。
- 只在正式 connection context 已构造后捕获 context enter/query failure，并继续
  作为 queue-health unavailable state 展示。
- 移除 `missing_connection` error code 和 `/readyz` 的对应 reason 映射。

验证：

- RED：`uv run pytest tests/unit/test_queue_health.py::test_fill_worker_queue_healths_requires_api_pool_connection_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_health_uses_formal_api_pool_connection_contract_without_missing_connection_fallback -q`
  初始 `2 failed`，证明旧 queue health 把缺 API pool connection 合同藏成
  unavailable queue。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_queue_health.py tests/unit/test_worker_status.py tests/unit/test_api_ops_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`214 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 134：runtime readiness 保留未使用 notification summary 空 fallback helper

现象：

- `src/parallax/app/runtime/app.py` 中保留了 `_notification_summary(...)`。
- 这个 helper 不在 `_readiness_payload(...)` 中使用，但它会调用
  `repos.notifications.summary(subscriber_key="local")`，并把任意异常吞成 `{}`。
- 它实际上是一个 dead compatibility surface：当前不影响 payload，但后续很容易被
  重新接回 `/readyz` 或其他 status surface。

根因：

- KISS 的硬切不仅是删除运行中的 fallback，也包括删除未使用但可复活的 fallback
  helper。否则代码库会留下“看起来有现成方法”的旧入口。
- notification summary 属于 notification route/worker 的拥有边界；runtime
  readiness 不应保留一个无 owner、无调用方、无契约校验的 best-effort summary。
- `except Exception: return {}` 会把 repository contract failure、DB read failure
  和真实空 summary 混成同一个结果。

修复：

- 删除 `_notification_summary(...)`。
- 架构守卫禁止 `def _notification_summary`、
  `repos.notifications.summary(subscriber_key="local")` readiness helper 和
  catch-all `except Exception: return {}` 回流。
- 调整 provider-state 架构测试的源码分隔点，不再依赖这个 dead helper 作为 delimiter。

验证：

- RED：`uv run pytest tests/architecture/test_worker_runtime_contracts.py::test_readyz_does_not_keep_dead_notification_summary_fallback -q`
  初始 `1 failed`，证明 dead helper 仍存在。
- GREEN：同一命令修复后 `1 passed`；配套 provider-state guard `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_api_ops_contract.py tests/unit/test_postgres_api_health.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`129 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 135：worker factory sentinel 把缺失 worker settings block 默认成 enabled/placeholder

现象：

- `worker_factories.__init__` 的 `_worker_config_enabled(...)` 使用
  `getattr(settings.workers, name, None)`，再用
  `getattr(config, "enabled", True)`。
- `_worker_settings(...)` 在 `config is None` 时返回
  `SimpleNamespace(enabled=enabled)`。
- 当某个 manifest worker 的 settings block 缺失时，旧实现不会暴露 runtime
  configuration shape 错误，而是把它当成 enabled unavailable worker，或构造一个
  placeholder sentinel settings 对象。

根因：

- Worker manifest、factory ownership 和 `workers.yaml`/`Settings.workers` 必须是同一套
  runtime contract。manifest 里有 worker，但 settings 缺 block，表示配置装配坏了。
- default-enabled 和 synthetic settings 会让测试 fake 或半截 runtime shape 继续通过，
  并把“配置缺字段”误导成“factory 没构造 worker”或“worker disabled”。
- 这会削弱 worker status、readiness、scheduler unhealthy reasons 对真实 runtime
  wiring/configuration 的诊断能力。

修复：

- `_worker_config_enabled(...)` 直接读取 `getattr(settings.workers, name)` 和
  `config.enabled`。
- `_worker_settings(...)` 直接读取同一个 formal worker settings block；缺 block
  直接抛 `AttributeError`。
- 架构守卫禁止 `getattr(settings.workers, name, None)`、
  `getattr(config, "enabled", True)`、`if config is None` 和
  `SimpleNamespace(enabled=enabled)` placeholder 回流。

验证：

- RED：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_missing_worker_sentinel_requires_worker_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_missing_worker_sentinel_uses_formal_worker_settings_contract_without_default_config -q`
  初始 `2 failed`，证明旧 sentinel helper 把缺 worker settings 合同默认化。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q`
  通过，`214 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 136：DBPoolBundle wake sizing 把缺失 worker settings 误判成零 listener

现象：

- `enabled_wake_listener_concurrency(...)` 用
  `getattr(settings, "workers", None)`，缺失 `settings.workers` 时直接返回 `0`。
- 对每个 worker settings 又用
  `getattr(worker_settings, "enabled", True)`、
  `getattr(worker_settings, "wakes_on", ())` 和
  `getattr(worker_settings, "concurrency", 1)`。
- 结果是 malformed runtime settings shape 会被伪装成“没有 wake listener”，
  `wake_pool` 可能被压到最小 size，而 readiness/worker diagnostics 不会暴露配置错误。

根因：

- `wake_pool` sizing 是 runtime composition root 的容量规划，不是 best-effort
  diagnostics。成熟 Kappa/CQRS 里，wake 只是 hint，但 wake listener 的资源边界仍然必须
  与 manifest 和正式 worker settings 一致。
- 旧实现把“wake 不是 truth”误解成“wake 配置可以缺省”。这会掩盖 `workers.yaml` /
  `Settings.workers` 与 `worker_manifest.py` 脱节的问题，让测试 fake 或半截 settings
  继续通过。
- 更深层问题仍是 optional-shape 思维：把 composition contract 错误翻译成一个看似正常的
  空状态，导致后续排查 backlog、missed wake、pool starvation 时方向错误。

修复：

- `DBPoolBundle` 导入 `all_worker_manifests()`，只遍历 manifest 声明了 `wakes_on` 的
  wake listener worker。
- sizing 直接读取 `settings.workers`，再读取对应
  `settings.workers.<manifest.name>.enabled`、`.wakes_on`、`.concurrency`。
- 缺失 `settings.workers` 或缺失 manifest wake worker settings block 直接暴露
  `AttributeError`；不再把配置错误收敛为 0 listener。
- 架构守卫禁止 `getattr(settings, "workers", None)`、
  `getattr(worker_settings, "enabled"/"wakes_on"/"concurrency", default)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_db_pool_bundle.py::test_enabled_wake_listener_concurrency_requires_workers_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_wake_listener_sizing_uses_manifest_worker_settings_contract -q`
  初始 `2 failed`，证明旧 sizing 把缺失 worker settings 合同默认化。
- GREEN：`uv run pytest tests/unit/test_db_pool_bundle.py::test_enabled_wake_listener_concurrency_requires_workers_settings_contract tests/unit/test_db_pool_bundle.py::test_enabled_wake_listener_concurrency_requires_manifest_worker_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_db_pool_bundle_wake_listener_sizing_uses_manifest_worker_settings_contract -q`
  通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_db_pool_bundle.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`175 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 137：CLI ops market-current rebuild 合成缺失 worker settings

现象：

- `ops rebuild-market-tick-current` 的 `_run_market_tick_current_rebuild(...)`
  使用 `getattr(getattr(settings, "workers", SimpleNamespace()), worker_name, SimpleNamespace())`。
- `worker_session(...)` 的 statement timeout 又用
  `getattr(worker_settings, "statement_timeout_seconds", None)`。
- `_market_tick_current_projection_lock_key(...)` 在缺
  `settings.workers.market_tick_current_projection` 时构造 `_LockProbe(SimpleNamespace())`，
  再退回 `SINGLE_WRITER_KEY`。
- 结果是 CLI one-shot 命令会在缺 `workers.yaml` / 缺 worker settings block 时继续创建
  `DBPoolBundle`，把 malformed runtime configuration 伪装成默认 timeout/default lock key。

根因：

- ops one-shot 不是第二套 runtime。它临时创建 DB bundle、拿 advisory lock、跑一次
  projection/rebuild，但 worker-specific knobs 仍然来自同一个
  `settings.workers.<name>` 合同。
- Root104/113 已把 ops one-shot 的 DB/lock/provider 生命周期收回正式 root；这里是同一个
  问题在配置读取上的残留：CLI 表面自己合成 settings，使 runtime settings 形态错误不可见。
- 成熟 Kappa/CQRS 中，operator repair command 可以是手动入口，但不能有一套与 worker
  runtime 不同的默认配置语义，否则排查 projection lock、statement timeout、pool 使用和
  worker status 时会出现两套事实。

修复：

- `_run_market_tick_current_rebuild(...)` 直接读取
  `settings.workers.market_tick_current_projection`，并直接传
  `worker_settings.statement_timeout_seconds`。
- `_market_tick_current_projection_lock_key(...)` 直接返回
  `settings.workers.market_tick_current_projection.advisory_lock_key`。
- 删除 `_LockProbe` 和 `SimpleNamespace()` fallback 路径。
- 架构守卫禁止 nested `getattr(..., SimpleNamespace())`、statement-timeout fallback、
  `_LockProbe` 和 `worker_settings or SimpleNamespace()` 回流。

验证：

- RED：`uv run pytest tests/unit/test_ops_backfill_commands.py::test_rebuild_market_tick_current_requires_worker_settings_contract_before_db_create tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_market_tick_current_rebuild_uses_formal_worker_settings_contract -q`
  初始 `2 failed`，证明旧 one-shot 命令在缺 worker settings 时仍进入 DB bundle 创建。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_market_tick_current_rebuild_uses_formal_worker_settings_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_asset_market_provider_cleanup_uses_bundle_aclose_without_provider_field_probe -q`
  通过，`23 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 138：CLI ops advisory-lock key helper 接受 SINGLE_WRITER_KEY 属性 fallback

现象：

- `_effective_worker_advisory_lock_key(...)` 先 optional-probe
  `getattr(worker, "_advisory_lock_key", None)`，如果不可调用就退回
  `getattr(worker, "SINGLE_WRITER_KEY", None)`。
- 这意味着一个没有正式 `_advisory_lock_key()` 方法、但恰好有 `SINGLE_WRITER_KEY`
  属性的 fake/旧 worker shape，会被 CLI ops one-shot 当作合法单 writer lock 配置。
- 错误信息还用 `worker.__class__.__name__` 做 fallback，继续把 malformed worker object
  包装成可诊断但可兼容的形状。

根因：

- runtime worker 的正式 advisory-lock 合同是 `WorkerBase._advisory_lock_key()`：它内部可以
  把 settings override 和 class-level default 合并，但外部调用者不应该绕过这个方法。
- ops one-shot 再次保留了第二套 lock-key 语义：服务 runtime 走 worker 方法，CLI 走
  方法或裸属性都行。这样测试 fake 可能绕过真实 worker 的 settings override、single-writer
  policy 或未来校验。
- 成熟 Kappa/CQRS 的单 writer 不是“有个数字就可以”，而是 worker runtime contract 的一部分；
  CLI repair command 必须复用同一合同，不能接受更宽的旧形状。

修复：

- `_effective_worker_advisory_lock_key(...)` 直接读取 `worker._advisory_lock_key`。
- 缺方法、non-callable 方法、或方法返回 `None` 都抛
  `ops_worker_advisory_lock_key_required`。
- 删除 `SINGLE_WRITER_KEY` 属性 fallback 和 class-name fallback 错误路径。
- 架构守卫禁止 optional `_advisory_lock_key` probe、`SINGLE_WRITER_KEY` fallback、
  `if callable(resolve)` 分支和 `worker.__class__.__name__` 回流。

验证：

- RED：`uv run pytest tests/unit/test_ops_backfill_commands.py::test_ops_advisory_lock_key_requires_worker_method_without_single_writer_attr_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts -q`
  初始 `2 failed`，证明旧 helper 接受了只有 `SINGLE_WRITER_KEY` 的 fake worker。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_ops_backfill_commands.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_market_tick_current_rebuild_uses_formal_worker_settings_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_asset_market_provider_cleanup_uses_bundle_aclose_without_provider_field_probe -q`
  通过，`24 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 139：配置后的 GMGN provider 被当成 optional capability bag

现象：

- `wire_asset_market(...)` 在 `settings.gmgn_configured` 后拿到 `gmgn_dex_market`，但
  `_dex_quote_market(...)` 仍用 `_has_token_quotes(...)` /
  `getattr(value, "token_quotes", None)` 判断是否有 quote 能力。
- `_dex_profile_sources(...)` 同样用 `_has_token_profile(...)` /
  `getattr(value, "token_profile", None)` 决定是否加入 GMGN profile source。
- 结果是：如果 GMGN adapter/fake/runtime wiring 返回了一个非空但缺
  `token_quotes` 或 `token_profile` 的 malformed provider，对外不会暴露 wiring 错误；
  quote 路径会静默落到 OKX fallback，profile refresh 会静默缺少 GMGN source。

根因：

- “provider 未配置”和“配置后对象形状错误”是两类状态。前者可以是 `None`；
  后者必须 fail fast。旧实现把两者混成 optional capability discovery。
- GMGN OpenAPI 在当前架构中不是一个插件式能力袋，而是 Asset Market 的 concrete DEX
  provider adapter。它的正式合同包括 quote/profile/candle 方法，worker 和 service
  通过 domain protocol 注入使用。
- 成熟 Kappa/CQRS 允许 provider IO 失败并由 worker 记录缺失/退避，但不能让
  composition root 把 malformed provider shape 伪装成“上游没数据”。否则事实链路会变得不诚实：
  PostgreSQL 里缺少 GMGN profile source/cache 不是 provider observation，而是 wiring bug
  被 fallback 吞掉了。

修复：

- `_dex_quote_market(...)` 只在 `primary is None` 时使用 OKX fallback 表示 GMGN 未配置；
  非空 primary 必须通过 `_require_token_quote_provider(...)`。
- `_dex_profile_sources(...)` 只在 `gmgn_dex_market is not None` 时加入 GMGN source，并通过
  `_require_token_profile_source(...)` 直接校验 `token_profile`。
- 缺失或非 callable 方法分别抛
  `asset_market_token_quotes_required` /
  `asset_market_token_profile_required`，并复用既有 partial cleanup 关闭已创建 provider。
- 架构守卫禁止 `_has_token_quotes`、`_has_token_profile` 和相关 `getattr(..., None)` 能力探测回流。

验证：

- RED：`uv run pytest tests/unit/test_providers_wiring.py::test_asset_market_configured_gmgn_requires_token_quote_contract tests/unit/test_providers_wiring.py::test_asset_market_configured_gmgn_requires_token_profile_contract tests/architecture/test_worker_runtime_contracts.py::test_configured_asset_market_gmgn_provider_uses_formal_quote_and_profile_contracts -q`
  初始 `3 failed`，证明旧 wiring 接受 malformed GMGN provider 并保留 optional capability probes。
- GREEN：同一命令修复后 `3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_providers_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes tests/architecture/test_worker_runtime_contracts.py::test_configured_asset_market_gmgn_provider_uses_formal_quote_and_profile_contracts -q`
  通过，`28 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 140：CEX CoinGlass provider wiring 合成缺失 worker settings 字段

现象：

- `_coinglass_derivatives(...)` 已经直接读取
  `settings.workers.cex_oi_radar_board`，但内部仍用
  `getattr(worker_settings, "enabled", True)`。
- `coinglass_enrichment_limit` 同样用
  `getattr(worker_settings, "coinglass_enrichment_limit", 0)`。
- 结果是 malformed worker settings block 会被误解释成“worker enabled”或“enrichment
  limit 为 0，所以不构造 CoinGlass”，而不是暴露配置装配错误。

根因：

- CoinGlass enrichment 虽然是可选 provider enrichment，但它的开关和上限仍属于正式
  `workers.yaml` / `Settings.workers.cex_oi_radar_board` 合同。
- 旧实现把“业务上可以配置为 0 表示关闭”混成“字段缺失时也当作 0”。这会让不完整
  runtime settings、测试 fake 或 workers schema 漂移绕过 diagnostics。
- 成熟 Kappa/CQRS 中，provider enrichment 可以缺数据、失败或配置关闭，但配置平面的形状不能
  best-effort。否则 CEX read-model 新鲜度、partial status 和 provider availability 的根因会被
  混淆。

修复：

- `_coinglass_derivatives(...)` 直接读取 `worker_settings.enabled`。
- CoinGlass 上限直接读取 `worker_settings.coinglass_enrichment_limit`。
- 缺字段直接 `AttributeError` 暴露 malformed runtime configuration；保留显式
  `enabled=False` 和 `coinglass_enrichment_limit <= 0` 作为合法关闭路径。
- 架构守卫禁止这两个 `getattr(..., default)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py::test_wire_cex_market_intel_requires_worker_enabled_setting tests/unit/test_cex_market_intel_provider_wiring.py::test_wire_cex_market_intel_requires_worker_coinglass_limit_setting tests/architecture/test_worker_runtime_contracts.py::test_cex_market_intel_provider_wiring_uses_formal_worker_settings_fields_without_defaults -q`
  初始 `3 failed`，证明旧 wiring 合成缺失 `enabled` 和 `coinglass_enrichment_limit` 字段。
- GREEN：同一命令修复后 `3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_cex_market_intel_provider_wiring_uses_formal_worker_settings_fields_without_defaults tests/architecture/test_worker_runtime_contracts.py::test_cex_and_news_worker_factories_use_formal_provider_bundle_fields_without_optional_probe tests/architecture/test_worker_runtime_contracts.py::test_provider_io_worker_factories_do_not_import_raw_third_party_clients -q`
  通过，`13 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 141：Asset Market 启动失败清理路径 optional-probe OKX bundle 字段

现象：

- `wire_asset_market(...)` 正常构造 `AssetMarketProviders` 时直接读取
  `okx_bundle.dex_discovery_market`、`.dex_quote_market`、`.stream_dex_market`。
- 但异常清理路径却用
  `getattr(okx_bundle, "dex_discovery_market", None)`、
  `getattr(okx_bundle, "dex_quote_market", None)`、
  `getattr(okx_bundle, "stream_dex_market", None)`。
- 如果 `okx.wire_okx_provider_bundle(...)` 返回了一个非空但缺字段的 malformed bundle，
  后续 GMGN 或 Binance wiring 失败时，cleanup 会把字段缺失当成普通缺 provider，
  原始错误 notes 里没有留下 bundle shape 证据。

根因：

- 启动失败 cleanup 不是一条更宽的兼容执行路径。它应该保留原始 startup error，同时把
  cleanup 期间发现的 malformed runtime shape 作为 evidence 记录下来。
- `OkxProviderBundle` 已经是 `dataclass(frozen=True, slots=True)` 的 formal composition
  contract。正常路径直读字段，异常路径却 optional-probe 字段，等于同一个 bundle 有两套合同。
- 成熟 Kappa/CQRS 的 composition root 要能解释 provider 启动失败的真实层级：是 GMGN
  上游失败、OKX provider close 失败，还是 OKX bundle shape 本身坏了。optional cleanup
  会抹掉这个诊断维度。

修复：

- 新增 `_okx_bundle_cleanup_providers(...)`：`okx_bundle is None` 仍表示 bundle 未创建；
  非空 bundle 则逐个直接读取正式字段。
- 缺字段通过 `_record_okx_bundle_cleanup_field_error(...)` 写入原始异常 note，例如
  `okx_bundle.dex_quote_market` / `okx_bundle.stream_dex_market`。
- 可读取到的 provider 仍交给 `_close_partial_providers(...)` 关闭，避免 malformed 字段阻断
  已创建资源的清理。
- 架构守卫禁止 `getattr(okx_bundle, ..., None)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_providers_wiring.py::test_asset_market_wiring_records_malformed_okx_bundle_fields_during_partial_cleanup tests/architecture/test_worker_runtime_contracts.py::test_asset_market_wiring_cleanup_uses_formal_okx_bundle_fields_without_optional_probe -q`
  初始 `2 failed`，证明旧 cleanup 没有记录 malformed OKX bundle 字段并保留 optional probes。
- GREEN：同一命令修复后 `2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_providers_wiring.py tests/architecture/test_worker_runtime_contracts.py::test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes tests/architecture/test_worker_runtime_contracts.py::test_configured_asset_market_gmgn_provider_uses_formal_quote_and_profile_contracts tests/architecture/test_worker_runtime_contracts.py::test_asset_market_wiring_cleanup_uses_formal_okx_bundle_fields_without_optional_probe -q`
  通过，`30 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 142：Pulse provider timeout 保留 provider-local 120 秒 fallback

现象：

- `_agent_runtime_lane_timeout_seconds(...)` 用
  `getattr(settings.workers.agent_runtime, "lanes", {}) or {}`。
- 如果 `pulse.decision` lane 缺失，会返回 `120.0`。
- 如果 lane object 缺 `timeout_seconds`，会用
  `getattr(lane_policy, "timeout_seconds", 120.0)`。
- 这绕过了 `Settings` / `WorkersSettings` 对 `agent_runtime.lanes` 的正式合并和校验；
  malformed runtime settings 会被包装成一个 provider-local 120 秒 timeout。

根因：

- `AgentRuntimePolicy` 对未知 lane 有默认策略，这是 gateway 内部对通用 lane 查询的语义；
  但 Pulse provider wiring 使用的是已知产品 lane `pulse.decision`。
- 对已知 lane，`Settings` 已经通过 `_default_agent_lanes()` 保证 `pulse.decision` 存在，
  默认 timeout 是 240 秒。运行时缺 lane 或缺 timeout 字段说明 settings shape 坏了。
- 旧实现把 provider wiring 做成第二套 timeout policy：真实 gateway lane policy 一套，
  Pulse provider wrapper 又有一套 120 秒 fallback。这会让超时诊断、worker hard timeout 和
  agent execution status 出现不一致。

修复：

- `_agent_runtime_lane_timeout_seconds(...)` 直接读取
  `settings.workers.agent_runtime.lanes[lane].timeout_seconds`。
- 缺 `lanes` 抛 `AttributeError`；缺 `pulse.decision` 抛 `KeyError`；缺
  `timeout_seconds` 抛 `AttributeError`。
- 保留 `AgentRuntimePolicy.lane_for("missing")` 的默认行为，不改变 gateway 对未知 lane
  的通用策略；只收紧已知 Pulse provider wiring。
- 架构守卫禁止 `getattr(settings.workers.agent_runtime, "lanes", {})`、
  `lanes.get(lane)`、`getattr(lane_policy, "timeout_seconds", 120.0)` 和
  `return 120.0` 回流。

验证：

- RED：`uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py::test_pulse_provider_timeout_requires_agent_runtime_lanes_contract tests/unit/test_provider_wiring_agent_execution_gateway.py::test_pulse_provider_timeout_requires_configured_pulse_decision_lane tests/architecture/test_agent_execution_plane_contracts.py::test_model_execution_provider_wiring_uses_formal_agent_lane_timeout_contract -q`
  初始 `3 failed`，证明旧 provider wiring 对缺 lane settings 使用 120 秒 fallback。
- GREEN：同一命令修复后 `3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/integrations/model_execution/test_agent_execution_audit.py::test_runtime_policy_uses_default_lane_when_missing tests/architecture/test_agent_execution_plane_contracts.py::test_model_execution_provider_wiring_uses_formal_agent_lane_timeout_contract -q`
  通过，`9 passed`；targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 143：worker factory sentinel 用对象 dump 合成 settings，绕过正式 worker settings model

现象：

- Root135 已经删除了缺失 `settings.workers.<name>` 时默认 enabled 或合成
  `SimpleNamespace(enabled=...)` 的路径。
- 但 `_worker_settings(...)` 在需要把 sentinel worker 的 `enabled` 翻转为
  disabled/intentionally-not-started 状态时，仍然调用 `_object_values(config)`。
- `_object_values(...)` 会先尝试 `model_dump`，再接受任意对象的 `__dict__`，
  最后甚至用 `getattr(value, "enabled", True)` 合成最小 settings。
- 结果是：只要测试 fake 或 malformed runtime object 有一个 `enabled` 字段，sentinel
  就可以继续生成一个 `SimpleNamespace(**values)`，而不是证明这是正式
  Pydantic worker settings model。

根因：

- Worker sentinel 不是业务 worker 的另一套配置系统。它只是为了让 canonical worker map
  在 disabled/unavailable/intentionally-not-started 状态下仍有一个 `WorkerBase` 实例。
- sentinel settings 必须和真实 worker 使用同一个 `PerWorkerSettings` / Pydantic contract；
  否则 status payload、timeout、interval、advisory/wake 配置会出现“真实 worker 一套，
  sentinel 另一套”的分叉。
- 成熟 Kappa/CQRS 里，控制面状态可以有 placeholder worker，但 placeholder 不能带
  placeholder config。否则 operator 看到的 disabled/unavailable 状态不是来自
  `workers.yaml` 的真实 runtime knobs，而是来自 composition root 的反射兼容层。

修复：

- `_worker_settings(...)` 继续直接读取 `settings.workers.<name>` 和 `config.enabled`。
- 如果 `config.enabled` 已经等于目标状态，直接复用正式 settings object。
- 如果需要翻转 `enabled`，只允许调用
  `config.model_copy(update={"enabled": enabled})` 克隆正式 Pydantic settings。
- 非 model settings 会抛 `worker_settings_model_copy_required:<worker>`，不再通过
  `model_dump`、`__dict__`、`vars(...)` 或 `SimpleNamespace(**...)` 合成。
- 架构守卫禁止 `_object_values` 和对象 dump 兼容路径回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_sentinel_requires_model_copy_for_enabled_state_changes tests/architecture/test_worker_runtime_contracts.py::test_missing_worker_sentinel_uses_formal_worker_settings_contract_without_default_config -q`
  通过，`2 passed`。
- Targeted ruff 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 144：Collector snapshot gate timeout 保留 service-local 0.5 秒默认

现象：

- `CollectorService.__init__(...)` 用
  `getattr(settings, "snapshot_timeout_seconds", 0.5)` 设置 snapshot gate timeout。
- `snapshot_timeout_seconds` 已经是 `CollectorWorkerSettings` 的正式字段，默认值由
  `workers.yaml` / `Settings` 合并和校验提供。
- 如果 collector settings fake 或 runtime wiring 缺这个字段，旧实现会静默使用 0.5 秒，
  让缺配置看起来像正常运行。

根因：

- snapshot gate timeout 是 ingestion worker 的控制面参数，不是 collector service 的私有
  fallback policy。
- 成熟 Kappa/CQRS 的 wake/catch-up 和 provider-frame admission 行为必须能从
  runtime settings 解释。超时值如果来自 service-local fallback，operator 看到的
  snapshot gate 行为就不能从 `workers.yaml` 复现。
- 这类默认值尤其危险，因为 collector 是事实链路入口：它不直接写 read model，但它决定
  provider frame 何时进入 ingest。入口控制面的默认漂移会污染后续所有事实/投影诊断。

修复：

- `CollectorService` 直接读取 `settings.snapshot_timeout_seconds`。
- 缺字段直接暴露 `AttributeError`，表示 malformed collector worker settings。
- 架构守卫禁止
  `getattr(settings, "snapshot_timeout_seconds", 0.5)` 或同类本地 timeout fallback 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_collector_service.py::CollectorServiceTests::test_collector_requires_snapshot_timeout_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_collector_snapshot_gate_timeout_uses_formal_worker_settings_contract -q`
  通过，`2 passed`。
- Targeted ruff 通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 145：MarketTickPollWorker 构造器保留测试/旧调用兼容入口

现象：

- `MarketTickPollWorker.__init__(...)` 接受 `settings=None`，并通过 `_settings(...)`
  合成 `SimpleNamespace(enabled=True, interval_seconds=..., batch_size=...)`。
- 构造器还接受 `dex_quote_market`、`cex_market`、`batch_size`、`interval_seconds`、
  `wake_bus`、`db` 等并非当前 worker factory 使用的旧注入形态。
- `self.providers = providers or SimpleNamespace(...)` 允许绕过 Asset Market provider
  bundle，把单个 provider handle 拼成临时 bundle。
- `self.batch_size` / `self.concurrency` 通过 `getattr(..., default)` 读取，使
  malformed settings fake 可以继续运行。

根因：

- Tier 2 market poll 是事实写入 worker：它从 `token_capture_tier(tier=2)` 读取目标，
  调 DEX/CEX quote provider，写入 `market_ticks(source_tier='tier2_poll')`，再发
  `market_tick_written` wake hint。
- 成熟 Kappa/CQRS 的 fact-writer 入口必须由 composition root 明确装配：正式
  worker settings、provider bundle、DB bundle、wake emitter。构造器里合成 settings
  或 provider bundle 等于给事实链路留了第二个 composition root。
- 这个兼容入口短期方便单测，但长期会让测试 fake、CLI 手动调用和生产 factory 分裂：
  operator 以为 batch/concurrency 来自 `workers.yaml`，实际可能来自构造器默认值或
  测试残留参数。Root144 同类问题发生在 collector timeout，这里发生在 market fact
  capture lane。

修复：

- `MarketTickPollWorker` 只接受正式 `settings`、`providers`、`pool_bundle` 和
  `wake_emitter` 入口；缺 settings/provider/DB bundle 分别 fail fast 为
  `market_tick_poll_settings_required`、`market_tick_poll_providers_required`、
  `market_tick_poll_db_required`。
- 删除 `_settings(...)`、`SimpleNamespace` 合成、单项 quote-provider 注入、
  `batch_size` / `interval_seconds` 构造器覆盖、`wake_bus` / `db` alias。
- `batch_size` 和 `concurrency` 改为直接读取 `settings.batch_size` /
  `settings.concurrency`；缺字段暴露 malformed worker settings。
- `construct_asset_market_workers(...)` 不再给 `MarketTickPollWorker` 传
  `batch_size=workers.market_tick_poll.batch_size` 旁路。
- 单测改为显式传正式 settings helper，architecture guard 禁止旧兼容入口回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_market_tick_poll_worker.py::test_market_tick_poll_worker_requires_formal_settings_provider_and_db_contracts tests/unit/test_market_tick_poll_worker.py::test_market_tick_poll_worker_reads_formal_settings_fields_directly tests/architecture/test_worker_runtime_contracts.py::test_market_tick_poll_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults -q`
  通过，`3 passed`。
- worker 单元全量：`uv run pytest tests/unit/test_market_tick_poll_worker.py -q`
  通过，`17 passed`。
- factory/architecture：`uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py -q`
  通过，`27 passed`；`uv run pytest tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`132 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 146：CLI ops one-shot worker override 继续 dump 任意 settings 对象

现象：

- `src/parallax/app/surfaces/cli/commands/ops.py` 的
  `_worker_settings_with_overrides(...)` 先尝试 `getattr(config, "model_dump", None)`，
  再退回 `vars(config)`，最后 `return SimpleNamespace(**values)`。
- 这个 helper 被 `refresh-asset-profiles`、`rebuild-token-profiles`、
  `run-token-image-mirror`、`run-resolution-refresh`、`run-token-radar-projection` 等
  one-shot ops worker 使用，用来覆盖 `batch_size` 或 `reprocess_limit`。
- 因此 CLI ops 虽然构造的是正式 worker，却给 settings 创建了第三种来源：
  `workers.yaml` 正式 Pydantic settings、worker factory sentinel 的 settings clone、
  以及 ops 自己 dump 出来的 `SimpleNamespace` settings。

根因：

- operator one-shot command 不是测试 helper，也不是脱离运行时的脚本。它会创建 DB pool、
  provider bundle 和真实 worker，并可能写 dirty queues、facts 或 read models。
- 成熟 Kappa/CQRS 里，运维入口可以改变运行窗口参数，但必须保持同一个配置模型；
  否则同一个 worker 在 daemon 和 CLI 下会看到不同 settings 类型、默认值、timeout 字段和
  validation 行为。
- Root143 已经证明 sentinel settings 不能 dump arbitrary object；Root146 是同一根因在
  ops one-shot 路径的残留：为了方便覆盖 `batch_size`，引入了第二套 settings 复制机制。

修复：

- `_worker_settings_with_overrides(...)` 只读取 `config.model_copy`，并调用
  `model_copy(update=overrides)`。
- 缺少或非 callable `model_copy` 直接抛
  `ops_worker_settings_model_copy_required`。
- 删除 `ops.py` 对 `SimpleNamespace` 的生产导入、`model_dump`、`vars(config)` 和
  `SimpleNamespace(**values)` 合成路径。
- 单元测试覆盖正式 model-copy 调用和 malformed settings fail-fast；架构守卫禁止旧
  dump/synthesis 令牌回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_ops_backfill_commands.py::test_ops_worker_settings_overrides_require_formal_model_copy_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ops_one_shot_worker_settings_overrides_use_formal_model_copy_contract -q`
  通过，`2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 147：WorkerBase 对核心 worker settings 保留本地默认值

现象：

- `WorkerBase.enabled` 用 `getattr(self.settings, "enabled", True)`，缺字段默认 enabled。
- `WorkerBase.interval_seconds` 用
  `getattr(self.settings, "interval_seconds", _DEFAULT_INTERVAL_SECONDS)`，缺字段默认 5 秒。
- `_backoff_seconds(...)` 用
  `getattr(self.settings, "backoff", None)`，再把缺 `base_ms/max_ms` 默认成 1000/60000。
- 这些字段已经由 `PerWorkerSettings` 正式定义：`enabled`、`interval_seconds`、
  `soft_timeout_seconds`、`hard_timeout_seconds`、`backoff`。

根因：

- `WorkerBase` 是所有 worker 的运行时底座。它如果自己保留默认值，就等于在
  `Settings` / `workers.yaml` 之外再维护一套 runtime policy。
- 成熟 Kappa/CQRS 要求 worker cadence、enabled state、retry/backoff 都能从控制面配置
  解释。缺字段是 malformed runtime settings，不应该变成“看似正常”的 enabled worker、
  5 秒 catch-up 或 1s/60s retry backoff。
- Root135/143/146 修掉了 composition root 和 ops helper 的 settings 合成；Root147 修掉
  base class 的最后一层核心 settings 兜底，否则所有 worker 仍可绕过正式配置合同。

修复：

- `WorkerBase.enabled` 直接读取 `self.settings.enabled`。
- `WorkerBase.interval_seconds` 直接读取 `self.settings.interval_seconds`。
- `_backoff_seconds(...)` 直接读取 `self.settings.backoff.base_ms` 和 `.max_ms`。
- 删除 `_DEFAULT_INTERVAL_SECONDS`、`_DEFAULT_BACKOFF_BASE_MS`、
  `_DEFAULT_BACKOFF_MAX_MS` 运行时 fallback 常量。
- 保留 `_advisory_lock_key()` 对 optional `advisory_lock_key` 的语义：不是所有 worker 都是
  single-writer worker，因此锁 key 仍是可选锁配置/类默认，不属于本次核心 settings hard cut。

验证：

- 目标验证：`uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_requires_formal_settings_fields_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_worker_base_core_settings_use_formal_worker_settings_without_runtime_defaults -q`
  通过，`2 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 148：TokenCaptureTierWorker 构造器仍保留测试式 settings 合成和限额覆盖

现象：

- `TokenCaptureTierWorker.__init__(...)` 接受 `settings=None`，并通过 `_settings(...)`
  合成 `SimpleNamespace(enabled=True, interval_seconds=..., batch_size=...)`。
- 构造器还接受 `db`、`interval_seconds`、`batch_size`、`ws_limit`、`poll_limit` 等
  旧调用形态；production factory 虽然已经有 `workers.token_capture_tier`，仍把
  `batch_size/ws_limit/poll_limit` 重复作为构造参数传入。
- worker 内部通过 `getattr(self.settings, "lease_ms", DEFAULT_LEASE_MS)` 读取租约，
  缺字段时静默回到 60 秒 lease，而不是暴露 malformed worker settings。
- `project_once(...)` 自身保留 batch/ws/poll 默认值，使纯投影函数也有一套隐藏运行
  策略。

根因：

- `token_capture_tier` 是 rebuildable control projection，不是 market fact，但它决定哪些
  target 进入 Tier 1 stream、Tier 2 poll、Tier 3 inline-only。它的限额和租约属于
  worker control-plane policy，必须由 `workers.yaml` 的正式
  `settings.workers.token_capture_tier` 解释。
- 成熟 Kappa/CQRS 的 projection worker 入口应只有一个 composition root：factory 注入
  正式 settings 和 DB bundle，worker 在 bounded dirty-target transaction 内执行投影。
  构造器默认值和 `SimpleNamespace` 合成让测试或 CLI 可以绕过 worker settings 合同，
  等于给 capture-tier 控制面保留了第二套 runtime policy。
- 这类兼容代码的危险不在于当前默认值是否正确，而在于它模糊了根因定位：当 stream/poll
  目标数量异常时，operator 看到的是 `workers.yaml`，代码实际可能用的是构造器覆盖或
  本地 fallback。

修复：

- `TokenCaptureTierWorker` 只接受正式 `settings` 和 `pool_bundle`；缺 settings/DB bundle
  分别 fail fast 为 `token_capture_tier_settings_required`、
  `token_capture_tier_db_required`。
- 删除 `_settings(...)`、生产 `SimpleNamespace` 导入、`db` alias、`interval_seconds` /
  `batch_size` / `ws_limit` / `poll_limit` 构造覆盖，以及 `DEFAULT_*` 本地默认值。
- `batch_size`、`ws_limit`、`poll_limit` 和 `lease_ms` 均直接读取正式 settings 字段；
  缺字段暴露 malformed worker settings。
- `construct_asset_market_workers(...)` 不再重复传限额参数，只传
  `settings=workers.token_capture_tier` 和 `pool_bundle=ctx.db`。
- 单测改为显式 settings helper，architecture guard 限定在 constructor/factory block，
  禁止旧兼容入口回流，同时保留 `project_once(...)` 作为必须显式传参的纯投影函数。

验证：

- 目标验证：`uv run pytest tests/unit/test_token_capture_tier_worker.py::test_worker_requires_formal_settings_and_db_contracts tests/unit/test_token_capture_tier_worker.py::test_worker_reads_formal_settings_fields_directly tests/architecture/test_worker_runtime_contracts.py::test_token_capture_tier_worker_constructor_uses_formal_settings_contract_without_synthetic_defaults -q`
  通过，`3 passed`。
- worker 单元全量：`uv run pytest tests/unit/test_token_capture_tier_worker.py -q`
  通过，`16 passed`。
- architecture：`uv run pytest tests/architecture/test_worker_runtime_contracts.py -q`
  通过，`134 passed`。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root 149：EventAnchorBackfillWorker 构造器仍保留 provider/settings 兼容入口

现象：

- `EventAnchorBackfillWorker.__init__(...)` 接受 `settings=None`，并通过
  `_settings(...)` 合成 `SimpleNamespace` worker settings。
- 构造器还接受 `db`、`wake_bus`、`dex_quote_market`、`cex_market`、
  `interval_seconds`、`batch_size`、`concurrency`、`min_age_ms`、
  `active_window_ms`、`max_anchor_lag_ms` 等旧调用形态；production factory
  已有 `workers.event_anchor_backfill` 和 `asset_market` provider bundle，但仍重复传
  batch/concurrency/window 参数。
- `_worker_session(...)` 通过
  `getattr(self.settings, "statement_timeout_seconds", None)` 探测 SQL timeout，
  缺字段时静默回到无 statement timeout，而不是暴露 malformed worker settings。

根因：

- `event_anchor_backfill` 不是普通“补一下数据”的后台脚本。它消费
  `event_anchor_backfill_jobs` 控制面，可能写入 `market_ticks`，并推进
  `enriched_events` 的 event-anchor lifecycle。它的 batch、lease、重试次数、窗口和 SQL
  timeout 都是 worker control-plane policy，必须由
  `settings.workers.event_anchor_backfill` 统一解释。
- 成熟 Kappa/CQRS 的 event-anchor catch-up 只有一个 composition root：worker factory
  注入正式 settings、DB bundle、provider bundle 和 wake emitter。构造器本地默认值、单独
  provider handles、`db/wake_bus` alias 会让测试/CLI/未来调用者绕过正式 runtime
  配置，形成第二套执行策略。
- 这类兼容代码的危险在于根因定位会失真：当 event anchor backlog、provider quote
  失败、lease 过短或 SQL timeout 异常时，operator 会检查 `workers.yaml`，但实际 worker
  可能由构造器覆盖值或本地 fallback 驱动。

修复：

- `EventAnchorBackfillWorker` 只接受正式 `settings` 和 `pool_bundle`；缺失时分别
  fail fast 为 `event_anchor_backfill_settings_required` 和
  `event_anchor_backfill_db_required`。
- 无显式 `capture_service` 时必须提供 Asset Market provider bundle；缺失 provider bundle
  fail fast 为 `event_anchor_backfill_providers_required`。
- 删除 `_settings(...)`、生产 `SimpleNamespace` 导入、`DEFAULT_*` 本地默认值、
  `db` / `wake_bus` alias、`dex_quote_market` / `cex_market` 单独 provider handles，以及
  batch/concurrency/window/interval 构造覆盖。
- `batch_size`、`concurrency`、`max_attempts`、`lease_ms`、`min_age_ms`、
  `active_window_ms`、`max_anchor_lag_ms` 和 `statement_timeout_seconds` 均直接读取
  正式 settings 字段；缺字段暴露 malformed worker settings。
- `construct_asset_market_workers(...)` 不再重复传 event-anchor 限额参数，只传
  `settings=workers.event_anchor_backfill`、`pool_bundle=ctx.db`、
  `providers=asset_market` 和 `wake_emitter=ctx.wake_bus`。
- 单测改为显式 settings helper，architecture guard 限定 constructor/factory block，
  禁止旧兼容入口回流，同时保留 `capture_service` 作为明确的单元测试/组合注入点。
- e2e 源码中的直接 worker 调用也改为 `model_copy(update=...)` 的正式 settings override
  和 `AssetMarketProviders` bundle；本轮按用户指令不运行 e2e。

验证：

- 目标验证：`uv run pytest tests/unit/test_event_anchor_backfill_worker.py::test_event_anchor_worker_requires_formal_settings_contract tests/unit/test_event_anchor_backfill_worker.py::test_event_anchor_worker_requires_formal_db_bundle_contract tests/unit/test_event_anchor_backfill_worker.py::test_event_anchor_worker_requires_provider_bundle_without_injected_capture_service tests/architecture/test_worker_runtime_contracts.py::test_event_anchor_backfill_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults -q`
  通过，`4 passed`。
- 相关源码 lint：`uv run ruff check tests/e2e/test_backend_hot_path.py src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py src/parallax/app/runtime/worker_factories/asset_market.py tests/unit/test_event_anchor_backfill_worker.py tests/architecture/test_worker_runtime_contracts.py`
  通过。
- 注意：按照当前用户指令，本轮没有运行 integration-heavy gate。

### Root150 - TokenProfileCurrentWorker 保留 worker/helper 层默认执行策略

发现：

- `TokenProfileCurrentWorker._rebuild_once(...)` 仍通过
  `getattr(self.settings, "statement_timeout_seconds", None)`、
  `getattr(self.settings, "batch_size", 500)`、`DEFAULT_LEASE_MS` 和
  `DEFAULT_RETRY_MS` 在 runtime 层补默认值。
- `rebuild_token_profile_current_once(...)` 仍为 `limit`、`lease_owner`、
  `lease_ms` 和 `retry_ms` 提供 helper 默认参数，意味着测试、CLI 或未来调用者可以不经过
  `settings.workers.token_profile_current` 直接运行一套隐式执行策略。
- `TokenProfileCurrentWorkerSettings` 没有正式 `retry_ms` 字段，实际 retry cadence
  完全来自 worker-local fallback。这会让 operator 检查 `workers.yaml` 时看不到真实重试策略来源。
- 同时审计确认 `claim_due(commit=True)` 本身不是兼容代码：dirty-target
  `mark_error(...)` 用已持久化的 `lease_owner` 和 `attempt_count` 做保护，claim
  事务是队列租约状态边界，不应在本 Root 里误删。

修复：

- `TokenProfileCurrentWorkerSettings` 新增正式 `retry_ms` 字段，并同步默认 workers YAML。
- `TokenProfileCurrentWorker._rebuild_once(...)` 直接读取
  `statement_timeout_seconds`、`batch_size`、`lease_ms` 和 `retry_ms`。
- 删除 worker-local `DEFAULT_LEASE_MS` / `DEFAULT_RETRY_MS`；helper
  `rebuild_token_profile_current_once(...)` 不再提供执行策略默认参数。
- 单测覆盖 settings 直接透传和缺少正式 `statement_timeout_seconds` 字段时 fail fast；
  architecture guard 禁止 runtime 默认常量、settings `getattr(..., default)` 和 helper
  参数默认值回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_token_profile_current_worker.py::test_token_profile_current_worker_run_once_records_result_and_uses_one_db_session tests/unit/test_token_profile_current_worker.py::test_token_profile_current_worker_requires_formal_statement_timeout_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_token_profile_current_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- Token Profile Current 单测通过，`10 passed`；worker runtime architecture suite 通过，`136 passed`；settings suite 通过，`61 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 TokenProfileCurrentWorker runtime 默认值、settings fallback 或 helper 默认参数 token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root151 - MarketTickCurrentProjectionWorker 保留 current projection 默认执行策略

发现：

- `MarketTickCurrentProjectionWorker` 是 `market_tick_current` 的单 writer，但 claim、
  projection session 和 error retry 仍通过 `getattr(self.settings, ..., default)`
  读取 `statement_timeout_seconds`、`batch_size`、`lease_ms` 和 `retry_ms`。
- `MarketTickCurrentProjectionWorkerSettings` 已经定义 `batch_size`、`retry_ms`，
  并继承 `lease_ms` / `statement_timeout_seconds`，因此 runtime fallback 是第二套执行策略，
  不是配置缺口。
- `DEFAULT_RETRY_MS` 和硬编码的 `batch_size=100` / `lease_ms=120_000` 会让队列吞吐、
  租约和错误重试行为在正式 `workers.yaml` 之外继续存在。

修复：

- 删除 `DEFAULT_RETRY_MS`。
- `_claim_due(...)`、`_process_claim(...)`、`_mark_error(...)` 全部直接读取
  `self.settings.statement_timeout_seconds`；claim 直接读取 `batch_size` / `lease_ms`，
  error retry 直接读取 `retry_ms`。
- 单测覆盖 settings 直接透传到 claim/session/retry，并覆盖缺少正式
  `statement_timeout_seconds` 时 fail fast。
- architecture guard 禁止 `DEFAULT_RETRY_MS`、settings fallback probe、硬编码 batch/lease
  fallback token 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_market_tick_current_projection_worker.py::test_worker_reads_formal_settings_fields_directly_for_claim_sessions_and_retry tests/unit/test_market_tick_current_projection_worker.py::test_worker_requires_formal_statement_timeout_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_market_tick_current_projection_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- MarketTickCurrentProjectionWorker 单测通过，`10 passed`；worker runtime architecture suite 通过，`137 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 MarketTickCurrentProjectionWorker runtime 默认值或 settings fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root152 - TokenImageMirrorWorker 的图片重试/租约策略仍在 runtime 默认值里

发现：

- `TokenImageMirrorWorker` 处在 provider logo URL 到本地 `token_image_assets`、再到
  `token_profile_current` 的公共 profile/icon 链路中，但 claim、terminal image write
  session 和 dirty-source error retry 仍通过 `getattr(self.settings, ..., default)` 读取
  settings。
- worker-local `DEFAULT_LEASE_MS` / `DEFAULT_RETRY_MS` 让图片镜像租约和错误重试 cadence
  在正式 `workers.yaml` 之外继续存在。尤其 `retry_ms` 此前没有进入
  `TokenImageMirrorWorkerSettings`，operator 无法从正式配置面看到这条链路的重试策略。
- 内部 `_TokenImageAssetSessionRepository` 也重复使用硬编码
  `statement_timeout_seconds=120.0` fallback，形成同一 worker 内多处隐式 SQL timeout
  策略。

修复：

- `TokenImageMirrorWorkerSettings` 新增正式 `retry_ms` 字段，并同步默认 workers YAML。
- 删除 worker-local `DEFAULT_LEASE_MS` / `DEFAULT_RETRY_MS`。
- dirty-source claim、terminal done/error session、内部 image asset session repository
  全部直接读取 `statement_timeout_seconds`；claim 直接读取 `batch_size` / `lease_ms`，
  dirty-source error retry 直接读取 `retry_ms`。
- 单测覆盖正式 settings 直接透传、缺少 `statement_timeout_seconds` 时 fail fast，以及
  error retry 使用正式 `retry_ms`；architecture guard 禁止默认常量、settings fallback
  和硬编码 timeout/batch fallback 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_token_image_mirror_worker.py::test_token_image_mirror_worker_mirrors_claimed_rows_outside_db_sessions tests/unit/test_token_image_mirror_worker.py::test_token_image_mirror_worker_requires_formal_statement_timeout_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_token_image_mirror_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- TokenImageMirrorWorker 单测通过，`3 passed`；settings suite 通过，`61 passed`；worker runtime architecture suite 通过，`138 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 TokenImageMirrorWorker runtime 默认值或 settings fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root153 - AssetProfileRefreshWorker 的 provider-block retry 仍在 runtime 默认值里

发现：

- `AssetProfileRefreshWorker` 是 DEX/profile source cache 到 `token_profile_current_dirty_targets`
  的上游写手，但 provider-scoped claim、profile write/reschedule session 和 provider-block
  retry 仍通过 `getattr(self.settings, ..., default)` 读取 settings。
- worker-local `DEFAULT_LEASE_MS` / `DEFAULT_PROVIDER_RETRY_MS` 让 profile refresh 租约和
  provider-block retry cadence 在正式 `workers.yaml` 之外继续存在。
- `provider_retry_ms` 此前没有进入 `AssetProfileRefreshWorkerSettings`，operator 无法从正式
  config 看到 provider 被 Cloudflare/上游限流时的重试策略。

修复：

- `AssetProfileRefreshWorkerSettings` 新增正式 `provider_retry_ms` 字段，并同步默认
  workers YAML。
- 删除 worker-local `DEFAULT_LEASE_MS` / `DEFAULT_PROVIDER_RETRY_MS`。
- provider-scoped claim、error/ready/missing profile write session、provider-block reschedule
  session 全部直接读取 `statement_timeout_seconds`；claim 直接读取 `batch_size` / `lease_ms`，
  provider-block retry 直接读取 `provider_retry_ms`。
- 单测覆盖正式 settings 直接透传、provider-block retry 使用正式 `provider_retry_ms`，
  以及缺少 `statement_timeout_seconds` 时 fail fast；architecture guard 禁止默认常量、
  settings fallback 和硬编码 batch fallback 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_asset_profile_refresh_worker.py::test_asset_profile_refresh_worker_run_once_records_result_and_uses_session_and_provider tests/unit/test_asset_profile_refresh_worker.py::test_asset_profile_refresh_worker_reports_provider_block_without_writing_token_error tests/unit/test_asset_profile_refresh_worker.py::test_asset_profile_refresh_worker_requires_formal_statement_timeout_settings_contract tests/architecture/test_worker_runtime_contracts.py::test_asset_profile_refresh_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`4 passed`。
- AssetProfileRefreshWorker 单测通过，`5 passed`；settings suite 通过，`61 passed`；worker runtime architecture suite 通过，`139 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 AssetProfileRefreshWorker runtime 默认值或 settings fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root154 - MarketTickStreamWorker 仍保留第二套构造/composition root

发现：

- `MarketTickStreamWorker` 是 Tier 1 WebSocket 市场事实写手，但构造器仍接受
  `db` / `wake_bus` alias、`subscription_limit` / `interval_seconds` /
  `stream_cycle_seconds` 覆盖，并在缺少 settings 时用 `SimpleNamespace` 合成一套本地
  worker settings。
- helper `_settings(...)` 还会读取 `settings.__dict__` 并复制字段，这是典型兼容旧测试或
  旧调用者的逃生门；正式 `settings.workers.market_tick_stream` 不再是唯一执行策略来源。
- `DEFAULT_SUBSCRIPTION_LIMIT` / `DEFAULT_STREAM_CYCLE_SECONDS` 让订阅规模和 stream cycle
  时间在正式 `workers.yaml` 之外继续存在。`stream_cycle_seconds` 此前也没有正式 schema 字段。

修复：

- `MarketTickStreamWorkerSettings` 新增正式 `stream_cycle_seconds` 字段，并同步默认 workers YAML。
- `MarketTickStreamWorker` 构造器现在要求正式 settings、DB pool bundle、stream provider 和
  telemetry；缺失 settings/DB/provider 分别 fail fast。
- 删除 `_settings(...)`、`_stream_cycle_seconds(...)`、`SimpleNamespace` 合成、`db` /
  `wake_bus` alias、constructor limit/interval/cycle overrides，以及本地 stream 默认常量。
- worker 直接读取 `settings.subscription_limit` 和 `settings.stream_cycle_seconds`；factory
  不再重复传 subscription limit。
- 单测改为用显式 `_stream_settings(...)` helper 表达测试配置，并覆盖 settings/DB/provider
  构造契约失败；architecture guard 禁止旧兼容入口回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_is_not_single_writer_locked tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_reads_tier1_streams_outside_session_inserts_and_notifies tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_requires_formal_settings_contract tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_requires_db_pool_bundle_contract tests/unit/test_market_tick_stream_worker.py::test_market_tick_stream_worker_requires_stream_provider_contract tests/architecture/test_worker_runtime_contracts.py::test_market_tick_stream_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults -q`
- 目标验证通过，`6 passed`。
- MarketTickStreamWorker 单测通过，`16 passed`；bootstrap worker wiring 通过，`27 passed`；settings suite 通过，`61 passed`；worker runtime architecture suite 通过，`140 passed`。
- targeted ruff/mypy 通过；constructor/fallback 残留扫描未发现 `SimpleNamespace` settings 合成、`db` / `wake_bus` alias、constructor interval/limit/cycle override、本地 stream 默认值、settings `__dict__` 或重复 factory subscription-limit token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root155 - ResolutionRefreshWorker 仍保留构造覆盖和 settings fallback

发现：

- `ResolutionRefreshWorker` 是 discovery/control-plane worker，但构造器仍接受 `chain_ids`
  覆盖、未使用的 `dex_quote_market` 参数和 `wake_bus` alias。
- `settings.chain_ids`、`settings.max_attempts`、`settings.batch_size`、
  `settings.reprocess_limit` 没有作为唯一执行策略来源；runtime 仍有
  `getattr(..., default)` 和 `DEFAULT_DISCOVERY_LIMIT` /
  `DEFAULT_REPROCESS_LIMIT` fallback。
- 这会让 discovery queue claim 批量、retry budget、affected-intent reprocess 上限和
  wake emitter shape 不完全由 `settings.workers.resolution_refresh` 与 worker factory 决定。

修复：

- `ResolutionRefreshWorker` 构造器要求正式 settings 和配置好的 discovery provider；缺失时
  fail fast。
- 删除构造 `chain_ids` 覆盖、未使用 `dex_quote_market`、`wake_bus` alias，以及 discovery
  claim/reprocess limit 的 runtime fallback。
- worker 直接读取 `settings.chain_ids`、`settings.max_attempts`、`settings.batch_size` 和
  `settings.reprocess_limit`；factory 改为传 `wake_emitter=ctx.wake_bus`。
- 单测覆盖 settings 直接读取、缺 `chain_ids` fail fast、缺 provider fail fast、claim limit 和
  reprocess limit 透传；architecture guard 禁止旧构造/fallback 入口回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_worker_notifies_from_workerbase_path tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_worker_reads_formal_settings_contract tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_worker_requires_formal_chain_settings_contract tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_worker_requires_discovery_provider_contract tests/architecture/test_worker_runtime_contracts.py::test_resolution_refresh_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`5 passed`。
- ResolutionRefreshWorker 单测通过，`10 passed`；bootstrap worker wiring 通过，`27 passed`；worker runtime architecture suite 通过，`141 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 ResolutionRefreshWorker 旧构造/settings fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root156 - LivePriceGateway 仍把 fan-out 执行策略藏在构造器和 runtime 常量里

发现：

- `LivePriceGateway` 已经是 DB-backed presentation fan-out，不再拥有上游价格 provider；但构造器仍接受
  未使用的 `providers` bundle，这会让 composition root 看起来仍有第二条 provider 生命周期入口。
- worker 仍通过 constructor `interval_seconds` 合成 `SimpleNamespace` settings，绕过正式
  `settings.workers.live_price_gateway`。这和 WorkerBase 直接读取 formal settings 的治理方向冲突。
- `DEFAULT_LIVE_TARGET_LIMIT` 和 `DEFAULT_LIVE_TARGET_TTL_SECONDS` 让 live target 查询规模和
  latest tick freshness 预算留在 runtime 代码里，而不是 `workers.yaml`。结果是 SQL 扫描上限、
  freshness 语义和运维配置可以分裂。

修复：

- `LivePriceGatewayWorkerSettings` 新增正式 `target_limit` 和 `target_ttl_seconds` 字段，并同步默认
  workers YAML。
- `LivePriceGateway` 构造器现在要求正式 settings 和 DB pool bundle；缺失时分别 fail fast。
- 删除 constructor `providers` / `interval_seconds` 兼容路径、`SimpleNamespace` 合成，以及
  `DEFAULT_LIVE_TARGET_LIMIT` / `DEFAULT_LIVE_TARGET_TTL_SECONDS`。
- worker 直接用 `settings.target_limit` 限定 `token_capture_tier` live target rows，用
  `settings.target_ttl_seconds` 限定 `market_ticks.latest_for_targets(...)` 的 `max_age_ms`。
- factory 只传 formal settings、DB bundle、telemetry、projection version 和 async hub publish。
  单测覆盖 settings 直接读取、缺 settings/DB fail fast；architecture guard 禁止旧构造/fallback
  入口回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_live_price_gateway.py::test_live_price_gateway_uses_market_ticks_without_upstream_price_providers tests/unit/test_live_price_gateway.py::test_live_price_gateway_reads_formal_settings_for_target_limit_and_tick_ttl tests/unit/test_live_price_gateway.py::test_live_price_gateway_requires_formal_settings_contract tests/unit/test_live_price_gateway.py::test_live_price_gateway_requires_db_pool_bundle_contract tests/architecture/test_worker_runtime_contracts.py::test_live_price_gateway_constructor_uses_formal_settings_contract_without_synthetic_defaults -q`
- 目标验证通过，`5 passed`。
- targeted ruff/mypy 通过；后续 broader 非集成验证记录在 SDD verification。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root157 - NewsPageProjectionWorker 仍用 runtime fallback 控制 SQL/claim/retry 预算

发现：

- `NewsPageProjectionWorker` 是 News 页面读模型的 dirty-target consumer，但 worker session
  的 `statement_timeout_seconds`、dirty-target claim 的 `batch_size` / `lease_ms`、以及
  `mark_error(...)` 的 `retry_ms` 仍通过 `getattr(self.settings, ..., default)` 读取。
- `NewsPageProjectionWorkerSettings` 只显式定义了 advisory lock 和 wakes_on，导致实际 SQL
  timeout、claim 批量、lease 和 retry budget 的来源分裂：一部分在 `workers.yaml`，一部分在
  worker 代码默认值。
- 这不是简单风格问题。页面投影是公共 News read path 的上游，claim batch 与 statement timeout
  直接影响 PostgreSQL 热路径成本；这些预算必须可配置、可审计、可在 ops 中统一查看。

修复：

- `NewsPageProjectionWorkerSettings` 新增正式 `batch_size`、`lease_ms`、`retry_ms` 和
  `statement_timeout_seconds` 字段，并同步默认 workers YAML。
- `NewsPageProjectionWorker` 直接读取 `self.settings.statement_timeout_seconds`、
  `self.settings.batch_size`、`self.settings.lease_ms` 和 `self.settings.retry_ms`；删除
  `getattr(..., default)` fallback。
- 单测改用 formal `NewsPageProjectionWorkerSettings` helper；新增 focused 单测覆盖
  statement timeout、claim limit/lease 和 error retry 全部来自正式 settings。
- architecture guard 禁止 runtime default/fallback token 回流，并检查 schema 字段存在。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_reads_formal_settings_for_claim_session_and_retry tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_requires_repository_session_transaction_before_claiming tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_replaces_rows_without_emitting_wake tests/architecture/test_worker_runtime_contracts.py::test_news_page_projection_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`4 passed`。
- News projection dirty-target 单测通过，`27 passed`；News workers 单测通过，`33 passed`；
  settings suite 通过，`88 passed`；bootstrap worker wiring 通过，`27 passed`；worker runtime
  architecture suite 通过，`143 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 settings fallback 或硬编码
  batch/lease/retry default token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root158 - MacroViewProjectionWorker 仍把投影预算拆在 settings/schema 与 worker fallback 之间

发现：

- `MacroViewProjectionWorker` 是 Macro current read model 的唯一 writer，但 worker session
  的 statement timeout、dirty-target claim limit/lease、error retry、history lookback 和
  per-series history cap 仍有 runtime `getattr(..., default)` 或常量兜底痕迹。
- claim limit 此前硬编码为 `1`，而不是读取正式 `batch_size`。这让 `workers.yaml` 中的批量参数
  对最关键的 dirty-target consumer 没有真实控制力。
- 构造器仍暴露 `wake_bus` 命名和 `**kwargs` 风格的旧 composition root 入口。对 CQRS read-model
  writer 来说，wake 只应是事务提交后的 emit contract，而不应继续保留旧 bus 生命周期别名。
- 历史窗口下限此前靠 worker 常量保护，说明配置校验和运行执行边界混在一起。成熟 Kappa/CQRS
  系统里，运行时 worker 应执行已经验证的配置，而不是一边运行一边修补配置缺口。

修复：

- `MacroViewProjectionWorkerSettings` 显式定义 `lease_ms` 和新增正式 `retry_ms`，并把 `lookback_days >= 1095`、
  `limit_per_series >= 800` 的质量约束移到 settings schema；默认 workers YAML 同步记录。
- `MacroViewProjectionWorker` 构造器显式要求 formal settings 和 DB bundle；缺失时 fail fast。
- worker 直接读取 `statement_timeout_seconds`、`batch_size`、`lease_ms`、`retry_ms`、
  `lookback_days` 和 `limit_per_series`；删除 runtime fallback 常量/默认值。
- dirty-target claim limit 改为 `self._batch_size()`；factory 改为注入 `wake_emitter=ctx.wake_bus`，
  worker 仅在事务退出后调用 `notify_macro_view_snapshot_updated(...)`。
- 单测改用正式 `MacroViewProjectionWorkerSettings` helper，并新增 focused 单测覆盖 session
  timeout、claim batch/lease、history bounds 与 retry 全部来自同一个 formal settings 对象。
- architecture guard 禁止旧 `wake_bus` 构造、`**kwargs`、history fallback 常量、`getattr(settings, ...)`
  默认值和 `limit=1` 回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_reads_formal_settings_for_claim_history_session_and_retry tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_requires_session_transaction_before_claiming_dirty_target tests/architecture/test_worker_runtime_contracts.py::test_macro_view_projection_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- Macro view projection 单测通过，`9 passed`；settings suite 通过，`88 passed`；bootstrap worker wiring 通过，`27 passed`；worker runtime architecture suite 通过，`144 passed`；Macro no-compatibility architecture suite 通过，`11 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 history fallback 常量、settings `getattr(..., default)`、旧 `wake_bus`/`**kwargs` 构造入口、硬编码 `limit=1` 或 lease/retry 默认 token。
- SDD/static 通过；按照当前用户指令，本轮不运行 integration-heavy gate。

### Root159 - NewsSourceQualityProjectionWorker 仍把 source-quality 投影预算留在 runtime fallback

发现：

- `NewsSourceQualityProjectionWorker` 是 `news_source_quality_rows` 的单 writer，同时会在 compact source
  quality 状态变化时 enqueue `news_page_dirty`，属于 News CQRS operational projection 的关键链路。
- worker session 的 statement timeout、dirty-target claim 的 batch/lease、失败 retry 以及 source-quality
  windows 仍通过 `getattr(self.settings, ..., default)` 读取；`retry_ms` 甚至没有正式 schema 字段。
- 构造器仍接受旧 `wake_bus` 和 `**kwargs`，让 source-quality writer 和其它已治理的 read-model worker
  在 composition root 上不一致。
- 根因仍是“worker 自己修补配置缺口”：配置 schema、默认 YAML、factory 和 runtime worker 不是一个唯一执行合同，
  导致 SQL 预算和 wake 语义不能从 `workers.yaml` 一眼审计。

修复：

- `NewsSourceQualityProjectionWorkerSettings` 显式定义 `lease_ms`、`retry_ms`、
  `statement_timeout_seconds`，并同步默认 workers YAML。
- `NewsSourceQualityProjectionWorker` 构造器显式要求 formal settings 和 DB bundle；缺失时 fail fast。
- worker 直接读取 `statement_timeout_seconds`、`batch_size`、`lease_ms`、`retry_ms` 和 `windows`；
  删除 runtime fallback 默认值。
- factory 改为注入 `wake_emitter=ctx.wake_bus`，worker 只在 page-dirty enqueue 后调用
  `notify_news_page_dirty(...)`。
- 单测改用正式 `NewsSourceQualityProjectionWorkerSettings` helper，并新增 focused 单测覆盖 session timeout、
  claim batch/lease、configured windows 和 retry 全部来自同一个 formal settings 对象。
- architecture guard 禁止旧 `wake_bus`/`**kwargs` 构造、settings fallback、hard-coded batch/lease/retry/window
  默认值回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py::test_source_quality_worker_reads_formal_settings_for_claim_session_windows_and_retry tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_enqueues_page_dirty_when_source_quality_status_changes tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_requires_repository_session_transaction_before_claiming tests/architecture/test_worker_runtime_contracts.py::test_news_source_quality_projection_worker_uses_formal_settings_and_wake_contract -q`
- 目标验证通过，`4 passed`。
- Source-quality dirty-target 单测通过，`3 passed`；News projection dirty-target 单测通过，`27 passed`；settings/bootstrap suite 通过，`115 passed`；worker runtime architecture suite 通过，`145 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 source-quality settings fallback、旧 `wake_bus`/`**kwargs` 构造入口或 hard-coded batch/lease/retry/window 默认值。
- SDD/static 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root160 - NewsItemProcessWorker 仍把 item 处理预算留在 runtime fallback

发现：

- `NewsItemProcessWorker` 是 News item-level material facts 的关键 writer，负责 deterministic entities、token mentions、
  fact candidates、content classification、market scope、story identity、agent admission、下游 page/brief dirty work。
- worker session 的 statement timeout、item claim 的 batch/lease、失败 retry delay 和 max attempts 仍通过
  `getattr(self.settings, ..., default)` 读取；这些预算应该是 `settings.workers.news_item_process`
  的正式合同，而不是 worker 内部的隐藏默认值。
- 构造器仍接受旧 `wake_bus` 和 `**kwargs`，导致 News writer worker 在 composition root 上继续保留旧入口。
- 根因仍是配置合同没有完全收口：schema/default YAML、factory wiring、runtime worker 和测试 fake
  各自携带一部分默认值，导致 SQL 预算和 wake 语义无法从配置层完整审计。

修复：

- `NewsItemProcessWorkerSettings` 显式定义 `batch_size`、`lease_ms`、`max_attempts` 和
  `statement_timeout_seconds`，并同步默认 workers YAML；保留既有 `retry_delay_ms` 正式字段。
- `NewsItemProcessWorker` 构造器显式要求 formal settings 和 DB bundle；缺失时 fail fast。
- worker 直接读取 `statement_timeout_seconds`、`batch_size`、`lease_ms`、`max_attempts` 和
  `retry_delay_ms`；删除 runtime fallback 默认值。
- factory 改为注入 `wake_emitter=ctx.wake_bus`，worker 只在成功处理 item 后调用
  `notify_news_item_processed(...)`。
- 单测改用正式 `NewsItemProcessWorkerSettings` helper，并新增 focused 单测覆盖 session timeout、
  claim batch/lease、max attempts 和 retry delay 全部来自同一个 formal settings 对象。
- architecture guard 禁止旧 `wake_bus`/`**kwargs` 构造、settings fallback、hard-coded batch/lease/max-attempt/retry
  默认值回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_reads_formal_settings_for_claim_session_and_retry tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_requires_repository_session_transaction_before_claiming_items tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_extracts_mentions_candidates_and_wakes tests/architecture/test_worker_runtime_contracts.py::test_news_item_process_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`4 passed`。
- News worker 单测通过，`34 passed`；News projection dirty-target 单测通过，`27 passed`；
  settings/bootstrap suite 通过，`115 passed`；worker runtime architecture suite 通过，`146 passed`；
  News KISS architecture suite 通过，`37 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 item-process settings fallback、旧 `wake_bus`/`**kwargs`
  构造入口或 hard-coded batch/lease/max-attempt/retry 默认值。
- SDD/static 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root161 - NewsItemBriefWorker 仍把 LLM brief 预算和 wake 合同留在 runtime fallback

发现：

- `NewsItemBriefWorker` 是 `news_item_agent_runs` / `news_item_agent_briefs` 的单 writer，并且会刷新
  `agent_admission_*`、enqueue page work、发出 `news_item_brief_updated` wake，是 News semantic read path 的关键 writer。
- worker session 的 statement timeout、item-brief claim batch/lease、dirty-target retry、backpressure cooldown
  仍通过 `getattr(self.settings, ..., default)` 读取；这些预算必须从
  `settings.workers.news_item_brief` 正式合同可审计。
- 构造器仍接受旧 `wake_bus` 和 `**kwargs`，且 provider 可选后在 `run_once` 内返回 `missing_provider`。
  这会让 composition root 和 worker runtime 共同保留第二套“可启动但无 provider”的兼容路径。
- 根因仍是 settings schema、默认 YAML、factory wiring、worker 和测试 fake 没有同一个运行合同。

修复：

- `NewsItemBriefWorkerSettings` 显式定义 `lease_ms`、`retry_ms` 和 `statement_timeout_seconds`，
  并同步默认 workers YAML；保留既有 `backpressure_cooldown_ms` 正式字段。
- `NewsItemBriefWorker` 构造器显式要求 formal settings、DB bundle 和 provider；缺失时 fail fast。
- worker 直接读取 `statement_timeout_seconds`、`batch_size`、`lease_ms`、`retry_ms` 和
  `backpressure_cooldown_ms`；删除 runtime fallback 默认值。
- factory 改为注入 `wake_emitter=ctx.wake_bus`，worker 只在 current brief 更新后调用
  `notify_news_item_brief_updated(...)`。
- 单测改用正式 `NewsItemBriefWorkerSettings` helper，并新增 focused 单测覆盖 session timeout、
  claim batch/lease、retry 和 backpressure cooldown 全部来自同一个 formal settings 对象。
- architecture guard 禁止旧 `wake_bus`/`**kwargs`/optional-provider 构造、settings fallback、
  hard-coded batch/lease/retry/backpressure 默认值回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_reads_formal_settings_for_claim_session_retry_and_backpressure tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_requires_repository_session_transaction_for_policy_skip_completion tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_writes_ready_brief_and_emits_wake tests/architecture/test_worker_runtime_contracts.py::test_news_item_brief_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`4 passed`。
- News item-brief 单测通过，`25 passed`；settings/bootstrap suite 通过，`115 passed`；
  worker runtime architecture suite 通过，`147 passed`；News KISS architecture suite 通过，`37 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 brief settings fallback、旧 `wake_bus`/`**kwargs`
  构造入口、optional-provider runtime skip 或 hard-coded batch/lease/retry/backpressure 默认值。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root162 - NewsPageProjectionWorker settings 已收口但仍保留无用 wake_bus 构造入口

发现：

- `NewsPageProjectionWorker` 已经在 Root157 中改为直接读取 formal `news_page_projection` settings，
  但构造器仍接受 `wake_bus` 和 `**kwargs`，factory 仍传入 `wake_bus=ctx.wake_bus`。
- 这个 projection 本身不发下游 wake；保留 `wake_bus` 只是在 composition root 里留下旧生命周期别名，
  与“一个 worker 一个明确运行合同”的治理目标不一致。

修复：

- `NewsPageProjectionWorker` 构造器显式要求 formal settings 和 DB bundle；缺失时 fail fast。
- 删除 `wake_bus` 和 `**kwargs` 构造入口；factory 不再传无用 wake。
- 单测删除 page projection 的 wake fake；bootstrap 断言 page projection 没有 `wake_bus` 属性。
- 现有 architecture guard 扩展为同时禁止 page projection constructor/factory 的旧 wake 入口。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_reads_formal_settings_for_claim_session_and_retry tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_requires_repository_session_transaction_before_claiming tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_replaces_rows_without_emitting_wake tests/architecture/test_worker_runtime_contracts.py::test_news_page_projection_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`4 passed`。
- News projection/news worker 单测通过，`61 passed`；settings/bootstrap suite 通过，`115 passed`；
  worker runtime + News KISS architecture suite 通过，`184 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 page projection settings fallback、旧 `wake_bus`/`**kwargs`
  构造入口或 factory page block 的 `wake_bus=ctx.wake_bus` 注入。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root163 - NewsFetchWorker 事实入口仍保留 settings/wake/news_settings fallback

发现：

- `NewsFetchWorker` 是 News Kappa 事实入口，负责把 configured sources、provider observations 和 canonical news
  item 写入 PostgreSQL，并发出 `news_item_written` / `news_page_dirty` wake。
- worker session 的 statement timeout 和 due-source claim / provider fetch limit 仍通过
  `getattr(self.settings, ..., default)` 读取；configured sources 也通过
  `getattr(self.news_settings, "sources", ())` 读取。
- 构造器仍接受旧 `wake_bus` 和 `**kwargs`，feed client 缺失仍可被旧构造形状掩盖。
- 根因仍是事实入口没有把 `settings.workers.news_fetch`、`settings.news_intel`、feed client 和 wake
  emitter 统一为单一 composition root 合同。

修复：

- `NewsFetchWorkerSettings` 显式定义 `statement_timeout_seconds`，并同步默认 workers YAML。
- `NewsFetchWorker` 构造器显式要求 formal settings、DB bundle、News Intel settings 和 feed client；缺失时 fail fast。
- worker 直接读取 `settings.statement_timeout_seconds`、`settings.batch_size` 和 `news_settings.sources`；
  删除 runtime fallback 默认值。
- factory 改为注入 `wake_emitter=ctx.wake_bus`；worker 通过 emitter 发出 `news_item_written` 和
  source metadata page-dirty wake。
- 单测改用正式 `NewsFetchWorkerSettings` helper，并新增 focused 单测覆盖 session timeout、due-source
  claim limit 和 provider fetch limit 全部来自同一个 formal settings 对象。
- architecture guard 禁止旧 `wake_bus`/`**kwargs` 构造、settings/news_settings fallback、
  hard-coded batch fallback 和 factory `wake_bus=ctx.wake_bus` 回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_reads_formal_settings_for_session_claim_and_fetch_limit tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_requires_repository_session_transaction_before_reconciling_sources tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_fetches_outside_db_session_and_writes_items tests/architecture/test_worker_runtime_contracts.py::test_news_fetch_worker_uses_formal_settings_news_settings_and_wake_contract -q`
- 目标验证通过，`4 passed`。
- News worker/projection dirty-target 单测通过，`62 passed`；settings/bootstrap suite 通过，`115 passed`；
  worker runtime + News KISS architecture suite 通过，`185 passed`。
- targeted ruff/mypy 通过；生产 worker 残留扫描未发现 fetch settings/news_settings fallback、旧
  `wake_bus`/`**kwargs` 构造入口或 factory fetch block 的 `wake_bus=ctx.wake_bus` 注入。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root164 - MacroSyncWorker/Service 事实导入入口仍保留 settings/wake fallback

发现：

- `macro_sync` 是 Macro Kappa 事实入口，负责 claim `macro_sync_windows`，调用 `macrodata`
  history bundle，写 `macro_observations` / `macro_import_runs` / `macro_sync_runs`，并以
  `macro_observations_imported` 唤醒 Macro View projection。
- formal `MacroSyncWorkerSettings` 已经有 source、bundle、lease、retry、timeout 等字段，但
  `MacroSyncService` 仍通过 `_sync_settings(...)` 支持裸 settings 形状，并对 source/bundle/
  enqueue cadence/lease/retry/statement timeout 逐字段 `getattr(..., default)`。
- `MacroSyncWorker` 构造器仍通过 `**kwargs` 透传 `WorkerBase`，并把 wake emitter 命名成旧
  `wake_bus`；batch 也通过 `getattr(self.settings, "batch_size", 1)` 默认。
- 根因是 Macro 事实入口把正式 worker settings schema、root Settings、provider runner、DB session
  和 wake emitter 混在旧兼容 composition 形状里，导致“配置合同”和“运行时默认值”并存。

修复：

- `MacroSyncWorkerSettings` 显式定义 `batch_size=1`，并同步默认 workers YAML。
- `MacroSyncWorker` 构造器显式要求 formal settings、DB bundle、telemetry、root settings；删除
  `**kwargs` 和旧 `wake_bus` 构造入口，factory 改为 `wake_emitter=ctx.wake_bus`。
- `MacroSyncService` 初始化时一次性解析 `settings.workers.macro_sync`；缺失 formal worker settings
  或 repository session 合同直接 fail fast。
- service 直接读取 source、bundle、bootstrap lookback、window size、steady overlap、interval、
  max bootstrap windows、max attempts、lease、retry delay 和 statement timeout；删除 per-field
  runtime fallback。
- 单测新增 focused case，证明 worker batch cap、service worker session timeout、claim lease、retry
  delay 均来自 formal settings；architecture guard 禁止旧 `_sync_settings` helper、`wake_bus`、
  `**kwargs` 和 hard-coded defaults 回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py::test_worker_caps_formal_batch_size_to_max_windows_per_cycle tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_reads_formal_settings_for_session_claim_and_retry tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- Macro sync worker/service/repository 单测通过，`50 passed`；settings/bootstrap suite 通过，`115 passed`；
  worker runtime + Macro no-compat architecture suite 通过，`160 passed`。
- targeted ruff/mypy 通过；生产残留扫描未发现 Macro Sync 旧 `wake_bus=` 注入、`**kwargs` 构造、
  `_sync_settings` helper、settings batch fallback 或 source/bundle/retry/timeout hard-coded 默认值。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root165 - CexOiRadarBoardWorker read-model writer 仍保留可空 provider 和 settings 默认值

发现：

- `CexOiRadarBoardWorker` 是 CEX OI board/detail current read model 的唯一 runtime writer，负责从
  Binance OI/ticker/premium 输入和可选 CoinGlass enrichment 生成 `cex_oi_radar_rows`、
  `cex_oi_radar_publication_state`、`cex_detail_snapshots`。
- formal `CexOiRadarBoardWorkerSettings` 已有 period、batch、universe、statement timeout、
  CoinGlass limits，但 worker 仍对这些字段使用 `getattr(self.settings, ..., default)`。
- worker 构造器仍接受 `**kwargs`，`oi_market` 仍是可空 provider，并在 run path 里以
  `cex_market_unavailable` skip；这和 factory 已经负责 unavailable sentinel 的边界重复。
- 根因是 CEX read-model writer 没有把 provider availability 放在 composition root，仍在 worker 内保留
  “可运行但无 provider”的兼容状态，同时把 formal settings schema 旁路成 runtime 默认值。

修复：

- `CexOiRadarBoardWorker` 构造器显式要求 formal settings、DB bundle、telemetry 和 OI market provider；
  缺失时 fail fast。
- 删除 `**kwargs` 构造和 worker 内 `oi_market is None` skip 分支；provider 缺失继续由 factory 返回
  unavailable worker。
- worker 直接读取 `settings.period`、`settings.universe_limit`、`settings.batch_size`、
  `settings.statement_timeout_seconds`、`settings.coinglass_enrichment_limit`、
  `settings.coinglass_level_limit`。
- 单测改为正式 `CexOiRadarBoardWorkerSettings` helper，并新增 focused 单测覆盖 session timeout、
  universe limit、period、CoinGlass limits 和 provider required 合同。
- architecture guard 禁止 `**kwargs`、可空 OI provider、worker 内 provider skip、settings fallback、
  hard-coded period/universe/CoinGlass/batch/timeout 默认值回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py::test_cex_oi_radar_board_worker_reads_formal_settings_for_session_universe_and_enrichment tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py::test_cex_oi_radar_board_worker_requires_oi_market_provider_contract tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_board_worker_uses_formal_settings_and_provider_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- CEX worker/repository 单测通过，`37 passed`；settings/bootstrap suite 通过，`116 passed`；
  worker runtime + CEX Kappa architecture suite 通过，`152 passed`；manifest/lifecycle architecture suite
  通过，`56 passed`。
- targeted ruff/mypy 通过；生产残留扫描未发现 CEX OI worker 旧 `**kwargs` 构造、可空 provider、
  provider skip、settings fallback 或 hard-coded runtime defaults。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root166 - Notification workers 仍以 runtime fallback 决定批量和 DB timeout

发现：

- `NotificationWorker` 写 `notifications` 事实和 `notification_deliveries` 控制行；
  `NotificationDeliveryWorker` 负责投递 claim/complete/fail side-effect ledger。
- 两个 worker 已经有 formal worker settings block，但 batch limit 仍通过
  `getattr(settings, "batch_size", default)` 初始化，worker session timeout 仍通过
  `getattr(self.settings, "statement_timeout_seconds", None)` 读取。
- 根因是 notifications 的事务/side-effect 边界已经被收紧，但执行预算仍停留在“settings 可以缺字段”的旧模型，
  让批量和 PostgreSQL statement timeout 同时存在 schema 默认和 runtime 默认两套来源。

修复：

- `NotificationRuleWorkerSettings` 和 `NotificationDeliveryWorkerSettings` 显式定义
  `statement_timeout_seconds=30.0`，并同步默认 workers YAML。
- 两个 worker 构造时要求 formal settings 和 DB bundle；batch limit 直接读取
  `settings.batch_size`。
- `_repository_session()` 直接传入 `self.settings.statement_timeout_seconds`。
- 单测改用正式 `NotificationRuleWorkerSettings` / `NotificationDeliveryWorkerSettings` helper，并新增
  focused 单测覆盖 notification rule batch limit、rule session timeout、delivery session timeout。
- notifications architecture guard 禁止 batch/statement-timeout fallback token 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_notification_worker_runtime.py::test_notification_workers_read_formal_settings_for_batch_and_statement_timeout tests/architecture/test_notifications_hard_cut.py::test_notification_workers_read_formal_settings_without_runtime_defaults -q`
- 目标验证通过，`2 passed`。
- Notification runtime 单测通过，`15 passed`；settings/bootstrap suite 通过，`116 passed`；
  notifications + worker runtime architecture suite 通过，`161 passed`。
- targeted ruff/mypy 通过；生产残留扫描未发现 notification batch 或 statement-timeout fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root167 - MacroDailyBriefProjectionWorker 纯 projection 仍保留构造和 timeout fallback

发现：

- `MacroDailyBriefProjectionWorker` 只读当前 Macro View snapshot，写稳定 `assets_today`
  `macro_daily_briefs` read model；没有 provider IO，也没有下游 wake。
- 但构造器仍用 `**kwargs` 透传 `WorkerBase`，session timeout 仍通过
  `getattr(self.settings, "statement_timeout_seconds", None)` 读取。
- 根因是 Macro View projection 已经完成 formal settings/wake hard cut，但同域 daily brief projection
  仍保留旧 WorkerBase constructor shortcut，导致纯 projection writer 还有第二种运行入口。

修复：

- `MacroDailyBriefProjectionWorker` 构造器显式要求 formal settings、DB bundle、telemetry 和 wake waiter；
  缺失 settings/DB 时 fail fast。
- `_repository_session()` 直接读取 `self.settings.statement_timeout_seconds`。
- 新增 runtime 单测覆盖 formal statement timeout、missing snapshot 下 zero serving write 行为；
  bootstrap/settings 增加默认断言。
- architecture guard 禁止 `**kwargs`、`super().__init__(**kwargs)`、statement-timeout fallback 和
  `wake_bus` 回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/macro_intel/test_macro_daily_brief.py::test_macro_daily_brief_worker_reads_formal_settings_for_session_timeout_and_zero_write tests/architecture/test_worker_runtime_contracts.py::test_macro_daily_brief_projection_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`2 passed`。
- Macro daily/module/repository targeted 单测通过，`27 passed`；settings/bootstrap suite 通过，`116 passed`；
  worker runtime + Macro Kappa/no-compat architecture suite 通过，`164 passed`。
- targeted ruff/mypy 通过；生产残留扫描未发现 daily brief `**kwargs`、statement-timeout fallback 或
  old wake alias token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root168 - TokenRadarProjectionWorker 仍把产品窗口和 wake 入口留在 runtime fallback

发现：

- `TokenRadarProjectionWorker` 是 `token_radar_current_rows`、`token_radar_publication_state`
  和相关投影控制面的核心 runtime writer，也是 Market Tick / Resolution 更新后唤醒 Narrative、
  Pulse 等下游读模型的关键节点。
- formal `TokenRadarProjectionWorkerSettings` 已经定义 windows、scopes、venues、hot windows、
  batch size、cold interval、statement timeout 和 wakes_on，但 worker 构造器仍用
  `getattr(settings, ..., default)` 保留本地默认值。
- 构造器仍接受旧 `wake_bus` alias，factory 和 CLI one-shot 路径也继续使用旧参数名；这让
  composition root 的正式 wake emitter 契约和 worker 内部兼容入口并存。
- 根因是 Token Radar 的数据/事务链路已经被收紧到 CQRS 投影模型，但运行契约还停留在“缺配置也能
  按旧默认跑”的阶段。成熟 Kappa/CQRS 中，窗口集合、冷热节奏、批量和 DB timeout 是投影拓扑的一部分，
  必须由配置 schema 和 worker factory 单一来源控制，不能在 worker 内另藏一份产品默认值。

修复：

- `TokenRadarProjectionWorker` 构造时显式要求 settings 和 DB bundle；缺失直接
  `token_radar_projection_settings_required` / `token_radar_projection_db_required`。
- worker 直接读取 formal settings 的 windows、scopes、venues、hot_windows、batch_size、
  cold_interval_seconds、statement_timeout_seconds；删除 runtime 默认 tuple、batch/cold fallback。
- downstream wake 输出改为 `wake_emitter`，factory 与 CLI one-shot 路径同步使用
  `wake_emitter=...`，删除旧 `wake_bus` 构造 alias。
- Token Radar worker 单测补齐 formal settings shape，并覆盖 settings 字段进入 worker 状态、
  missing settings/DB fail-fast、无旧 `wake_bus` 属性。
- architecture guard 禁止 `DEFAULT_WINDOWS` / `DEFAULT_SCOPES` / `DEFAULT_HOT_WINDOWS`、
  `getattr(settings, ..., default)`、`getattr(self.settings, "statement_timeout_seconds", ...)`、
  `wake_bus` alias 和 factory/CLI 旧注入路径回流。
- mypy 同步暴露并顺手修正 `ops.py` 中既有 ResolutionRefreshWorker one-shot 旧构造参数
  `dex_quote_market` / `chain_ids`，让该 CLI 路径也继续遵守 AC151 的 formal settings/wake contract。

验证：

- 目标验证：`uv run pytest tests/unit/test_token_radar_projection_worker.py::test_projection_worker_calls_dirty_incremental_projection_not_window_rebuild tests/unit/test_token_radar_projection_worker.py::test_projection_worker_requires_formal_settings_and_db_contract tests/architecture/test_worker_runtime_contracts.py::test_token_radar_projection_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- Token Radar worker 单测通过，`22 passed`；settings/bootstrap/token-radar architecture targeted 通过，
  `51 passed`；ResolutionRefreshWorker formal settings/wake guard 与 Token Radar guard 通过，`2 passed`。
- Token Radar projection/service/source-width/publication-state 非集成套件通过，`119 passed`；
  worker runtime architecture suite 通过，`152 passed`；settings/bootstrap suite 通过，`116 passed`。
- targeted ruff/mypy 通过；残留扫描未发现 Token Radar worker 本体旧 settings fallback、product default
  tuple、statement-timeout fallback 或旧 `wake_bus` alias token。
- SDD validate、SDD generated index check、`git diff --check` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root169 - NarrativeAdmissionWorker 仍保留旧秒级 lease/retry 和无用 wake 输出入口

发现：

- `NarrativeAdmissionWorker` 是 `narrative_admissions` 的唯一 runtime writer，消费
  `narrative_admission_dirty_targets`，读取 Token Radar 当前行和物化事实后写当前 source-set admission。
- formal `NarrativeAdmissionWorkerSettings` 已有 admission/source limits 和 rank thresholds，但 worker
  仍通过 `getattr(..., default)` 读取这些字段，并额外读取 settings schema 中不存在的
  `lease_seconds`、`error_retry_seconds`。
- worker 构造器还接受 `wake_bus` 并保存为 `self.wake_bus`，但 Narrative Admission 没有 downstream
  wake-out；factory 仍把 `ctx.wake_bus` 注入进来，形成无效兼容入口。
- 根因是 Narrative LLM lane 删除后，`narrative_admission` 被保留下来作为确定性 read-model writer，
  但它的 runtime execution budget 没有同步硬切到 formal worker settings，旧秒级字段和 wake 输出入口
  继续给未来调用者制造第二套运行契约。

修复：

- `NarrativeAdmissionWorkerSettings` 显式定义 `lease_ms=60_000`、`retry_ms=60_000`、
  `statement_timeout_seconds=30.0`，并同步默认 workers YAML。
- `NarrativeAdmissionWorker` 构造时要求 settings 和 DB bundle；缺失直接
  `narrative_admission_settings_required` / `narrative_admission_db_required`。
- worker 直接读取 `admission_limit`、`source_limit`、`lease_ms`、`retry_ms`、
  `statement_timeout_seconds`、`hot_rank_limit`、`min_rank_score`；删除 `lease_seconds` /
  `error_retry_seconds` 和 `getattr(..., default)` fallback。
- factory 不再传 `wake_bus`；Narrative Admission 明确为 wake-in only，有 `wake_waiter` 但没有
  `wake_bus` / `wake_emitter` 构造路径。
- 单测补齐 formal settings shape，覆盖 fail-fast 构造、claim lease/retry/session-timeout/rank threshold
  都来自 settings；bootstrap/settings 和 architecture guard 防止旧字段和 wake alias 回流。

验证：

- 目标验证：`uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_narrative_admission_worker_requires_formal_settings_and_db_contract tests/unit/domains/narrative_intel/test_narrative_workers.py::test_narrative_admission_worker_marks_claim_error_with_completion_token tests/architecture/test_worker_runtime_contracts.py::test_narrative_admission_worker_uses_formal_settings_contract_without_runtime_defaults -q`
- 目标验证通过，`3 passed`。
- Narrative worker 单测通过，`7 passed`；settings/bootstrap/narrative architecture targeted 通过，
  `29 passed`；Narrative unit/architecture hard-cut suite 通过，`45 passed`；worker runtime architecture
  suite 通过，`153 passed`。
- settings/bootstrap suite 通过，`116 passed`；SDD validate、SDD generated index check、
  `git diff --check` 均通过。
- targeted ruff/mypy 通过；残留扫描未发现 NarrativeAdmissionWorker 旧 `getattr` settings fallback、
  `lease_seconds` / `error_retry_seconds`、statement-timeout fallback、`wake_bus` 或 `wake_emitter` token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root170 - Pulse Candidate 的 worker/job service 仍保留产品拓扑和 DB timeout runtime fallback

发现：

- `PulseCandidateWorker` 是 `pulse_trigger_dirty_targets` 的消费者，也是 `pulse_candidates` public
  visibility、`pulse_candidate_edge_state`、`pulse_agent_jobs` 和 agent 审计写入链路的入口。
- formal `PulseCandidateWorkerSettings` 已经承载 windows、scopes、batch/queue budget、agent attempt
  budget、trigger/gate thresholds 和 wakes_on，但 worker 构造仍曾把 `SIGNAL_PULSE_WINDOWS`、本地
  `DEFAULT_WINDOWS` / `DEFAULT_SCOPES`、`getattr(settings, ..., default)` 和 statement-timeout fallback
  留在 runtime 内。
- `PulseCandidateJobService` 作为同一 writer 链路的一部分，写 run/step/eval/candidate/playbook/admission/job
  terminal state，但 `_repository_session()` 也曾允许 `statement_timeout_seconds` 缺省兼容。
- 根因是 Pulse 之前集中治理了 repository contract 和 transaction boundary，但没有把 execution topology
  同步收敛到 settings schema。成熟 Kappa/CQRS 里，窗口/scope、触发阈值、agent budget 和 DB timeout
  都是 worker 拓扑，不应由 writer 本体另外保留一份“能跑就行”的产品默认值。

修复：

- `PulseCandidateWorkerSettings` 显式定义 `statement_timeout_seconds=30.0`，默认 workers YAML 同步。
- `PulseCandidateWorker` 构造时要求 settings、DB bundle 和 decision client；缺失直接 fail fast。
- worker 直接读取 `windows`、`scopes`、`batch_size`、`max_agent_jobs_per_cycle`、`max_attempts`、
  `max_enqueues_per_cycle`、pending job budgets、trigger thresholds、gate thresholds 和
  `statement_timeout_seconds`；删除本地 windows/scope/default settings fallback。
- `PulseCandidateJobService` 构造时要求 settings、DB bundle 和 decision client，并直接用
  `self.settings.statement_timeout_seconds` 打开 worker session。
- 单测覆盖 worker/job service fail-fast、formal settings 字段进入 worker 状态、非默认 statement timeout
  进入 worker/job service session；architecture guard 禁止 `SIGNAL_PULSE_WINDOWS`、`DEFAULT_WINDOWS` /
  `DEFAULT_SCOPES`、settings `getattr(..., default)`、statement-timeout fallback 和 job-service fallback 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_pulse_candidate_worker.py::test_pulse_worker_requires_formal_settings_db_and_client_contract tests/unit/test_pulse_candidate_worker.py::test_pulse_worker_uses_formal_settings_fields_and_session_timeout tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_job_service_requires_formal_settings_db_and_client_contract tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_job_service_uses_formal_settings_statement_timeout tests/architecture/test_worker_runtime_contracts.py::test_pulse_candidate_worker_and_job_service_use_formal_settings_without_runtime_defaults -q`
- 目标验证通过，`5 passed`。
- Pulse Candidate worker/job/dirty-trigger unit suite 通过，`80 passed`；settings/architecture target 通过，
  `2 passed`。
- targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root171 - WorkerBase advisory lock key 仍把 SINGLE_WRITER_KEY 当运行时 fallback

发现：

- 前面 Root103/Root138 已经把 advisory lock 的释放和 CLI one-shot 取锁入口切到正式 contract，但
  `WorkerBase._advisory_lock_key()` 本身仍保留 `getattr(self.settings, "advisory_lock_key", None)`，
  缺 settings 字段时回退到 worker 类上的 `SINGLE_WRITER_KEY`。
- 这让 runtime worker 和 CLI one-shot 出现微妙分叉：CLI 已经不接受裸 `SINGLE_WRITER_KEY` 属性，
  但真正的 WorkerBase loop 仍可在 formal worker settings 缺失时靠类常量拿锁并运行。
- 根因是 `SINGLE_WRITER_KEY` 一开始同时承担了“代码侧单 writer 标记”和“运行时锁 key 默认值”两个角色。
  在成熟 Kappa/CQRS runtime 中，锁 key 是 worker execution contract，必须由 manifest/settings/composition
  root 证明；类常量可以辅助声明，但不能替代 operator-owned workers settings。

修复：

- `WorkerBase._advisory_lock_key()` 对非 single-writer worker 仍返回 `None`。
- 对声明 `SINGLE_WRITER_KEY` 的 worker，直接读取 `self.settings.advisory_lock_key`；缺字段或值为 `None`
  抛 `worker_advisory_lock_key_required`。
- 删除 `return int(self.SINGLE_WRITER_KEY)` 运行时 fallback。
- 单测反转旧行为：settings 中配置的 lock key 优先于类常量；缺 formal lock key 的 single writer 不能开始运行。
- architecture guard 禁止 `getattr(self.settings, "advisory_lock_key", None)` 和
  `return int(self.SINGLE_WRITER_KEY)` 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_worker_base_runtime.py::test_worker_base_uses_formal_advisory_lock_key_instead_of_single_writer_fallback tests/unit/test_worker_base_runtime.py::test_worker_base_requires_formal_advisory_lock_key_for_single_writer tests/architecture/test_worker_runtime_contracts.py::test_worker_base_advisory_lock_key_uses_formal_settings_without_class_attr_fallback -q`
- 目标验证通过，`3 passed`。
- targeted ruff 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root172 - Macrodata FRED env/secret/timeout 仍回探旧 provider settings shape

发现：

- `MacroSyncService` 已经把 `workers.macro_sync` 作为正式执行预算来源，但 `_configured_fred_env_name(...)`
  仍先读 `settings.macrodata_fred_api_key_env`，缺失后回探 `settings.providers.macrodata.fred_api_key_env`，
  最后落到硬编码默认。
- `MacrodataBundleRunner` 同样回探 nested provider shape 来找 FRED env 和 config secret，并且
  `_macrodata_timeout_seconds(...)` 还接受 root-level `macrodata_timeout_seconds` 或缺失后 `240.0`
  默认。
- 根因是 Macrodata quote/provider runtime lane 删除后，配置读取没有完全收敛到 formal `Settings`
  facade 和 `workers.macro_sync`。这会让测试 fake 或旧配置形状继续通过，使真实运行时到底用哪个
  FRED env、是否注入 config secret、child process timeout 来自哪里变得不可审计。

修复：

- `MacroSyncService` 直接读取 `settings.macrodata_fred_api_key_env`；缺 formal 属性时抛
  `macrodata_fred_api_key_env_settings_required`。
- `MacrodataBundleRunner` 直接读取 `settings.macrodata_fred_api_key_env`、
  `settings.macrodata_fred_api_key` 和 `settings.workers.macro_sync.macrodata_timeout_seconds`。
- 删除 nested `providers.macrodata.*` 回探、root-level timeout fallback 和 `240.0` runtime
  timeout fallback；保留 env 字段为空时使用 `FINANCE_FRED_API_KEY` 的现有配置语义。
- 单测 fake 更新为 formal settings shape，并补缺字段 fail-fast 测试；Macro no-compat guard
  禁止旧 provider-shape fallback 回流。

验证：

- 目标验证：`uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runner_requires_formal_fred_and_timeout_settings_contracts tests/unit/test_cli_macro_commands.py::test_macrodata_runner_injects_fred_env_without_exposing_secret tests/unit/test_cli_macro_commands.py::test_macrodata_runner_passes_configured_timeout_to_child_process tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_requires_formal_fred_env_settings_contract tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_redacts_secret_from_run_payload_and_diagnostics tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback -q`
- 目标验证通过，`6 passed`。
- CLI Macro、Macro Sync Service、Macro no-compat 文件通过，`67 passed`。
- targeted ruff/mypy 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root173 - MarketTickPollWorker 仍把 provider bundle 缺字段当成 provider unavailable

发现：

- `MarketTickPollWorker` 已经要求正式 Asset Market provider bundle，并且 factory 已经直接读取
  `asset_market.cex_market` 和 `asset_market.dex_quote_market` 来决定 worker 是否 unavailable。
- 但 worker 轮询阶段仍用 `getattr(self.providers, "dex_quote_market", None)` 和
  `getattr(self.providers, "cex_market", None)`，这会把“provider bundle 字段缺失”吞成
  `dex_provider_unavailable` / `cex_provider_unavailable`。
- 根因是 Root145/AC141 只硬切了构造入口和 settings/provider bundle 参数形状，没有把 worker
  内部对 bundle 字段的读取也收敛到同一个 formal contract。成熟 Kappa/CQRS 里，组合根对象的字段本身
  是运行时契约；字段值为 `None` 才能表示具体 provider 未配置，字段缺失必须暴露为 malformed wiring。

修复：

- `MarketTickPollWorker.__init__` 直接读取 `providers.dex_quote_market` 和
  `providers.cex_market`；缺字段时构造失败。
- DEX/CEX poll path 改为使用 `self.dex_quote_market` / `self.cex_market`，删除
  `getattr(self.providers, ..., None)` optional probe。
- 单测新增缺 provider-bundle 字段 fail-fast 覆盖；architecture guard 禁止 optional provider probe 回流。
- Asset Market 架构、`docs/WORKERS.md` 和 `docs/WORKER_FLOW.md` 明确“字段缺失是 malformed wiring；
  present `None` 才是 unavailable provider state”。

验证：

- RED 目标验证先失败：`uv run pytest tests/unit/test_market_tick_poll_worker.py::test_market_tick_poll_worker_requires_formal_provider_bundle_fields tests/architecture/test_worker_runtime_contracts.py::test_market_tick_poll_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults -q`
- 修复后同一目标验证通过，`2 passed`。
- MarketTickPollWorker 单测全量加目标架构通过，`19 passed`；完整 worker runtime architecture suite 通过，
  `155 passed`；bootstrap worker wiring 目标通过，`3 passed`。
- targeted ruff/mypy、SDD validate、SDD generated index check 和 `git diff --check` 均通过。
- 残留扫描只在 architecture guard forbidden-token 字符串中看到旧 optional provider probe token，生产 worker
  已改为直接字段读取。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root174 - Token resolution reprocess helper 仍保留服务层默认 window/limit

发现：

- Root151 已经让 `ResolutionRefreshWorker` 直接读取 formal `settings.workers.resolution_refresh.reprocess_limit`，
  但 `token_resolution_refresh.py` 仍导出 `DEFAULT_REPROCESS_LIMIT=500`、
  `DEFAULT_REPROCESS_WINDOW="24h"`，并让 `refresh_recent_token_state(...)` /
  `reprocess_recent_token_intents(...)` 在缺参数时自行补默认。
- `token_intent_rebuild.rebuild_recent_token_intents(...)` 也保留 `window="24h"`、`limit=500`、
  `projection_limit=100` 参数默认，并用 `WINDOW_MS.get(window, fallback)` 静默把未知 window 映射到默认窗口。
- 根因是前序治理先修了 transaction boundary，却没有把“重放窗口和预算来自调用者/worker settings”的原则下沉到
  service helper。结果 helper 本身又变成第二套执行预算来源。

修复：

- `DEFAULT_REPROCESS_LIMIT` 删除；`DEFAULT_REPROCESS_WINDOW` 改为非默认语义的
  `TOKEN_REPROCESS_WINDOW = "24h"`，只表达 ResolutionRefreshWorker 当前 reprocess policy。
- `refresh_recent_token_state(...)`、`reprocess_recent_token_intents(...)` 和
  `rebuild_recent_token_intents(...)` 要求调用者显式传入 window、limit、projection limit。
- `WINDOW_MS.get(window, fallback)` 改为 `WINDOW_MS[window]`，非法 window 不再静默回退。
- `interfaces.py` 不再导出 `DEFAULT_REPROCESS_*`；architecture guard 禁止旧默认常量和默认参数回流。

验证：

- RED 目标验证先失败：`uv run pytest tests/unit/test_token_resolution_refresh.py::test_reprocess_requires_explicit_window_and_limit_contract tests/unit/test_token_resolution_refresh.py::test_refresh_recent_token_state_defers_projection_to_worker tests/architecture/test_worker_runtime_contracts.py::test_token_resolution_reprocess_helpers_require_explicit_window_and_limits_without_defaults -q`
- 修复后同一目标验证通过，`3 passed`。
- Token resolution/rebuild/resolution worker 相关非集成套件通过，`20 passed`。
- 完整 worker runtime architecture suite 通过，`156 passed`。
- targeted ruff 初次提示 `interfaces.py` `__all__` 排序，排序后通过；targeted mypy、SDD validate、
  SDD generated index check 和 `git diff --check` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root175 - Pulse decision client 仍暴露 provider-local 120 秒 timeout

发现：

- Root142/AC138 已经让 model-execution provider wiring 直接读取
  `settings.workers.agent_runtime.lanes["pulse.decision"].timeout_seconds`，缺 lane 或缺
  `timeout_seconds` 会作为 malformed runtime configuration 暴露。
- 但 `LiteLLMPulseDecisionClient` 仍保留 `_DEFAULT_TIMEOUT_SECONDS = 120.0` 和
  `timeout_seconds` property。虽然当前组合根会用 `LiteLLMPulseDecisionProvider` 包住 client，
  但这个底层 client 仍“长得像” `PulseDecisionProvider`，未来任何直接注入都会绕过正式 lane
  settings，重新启用 provider-local 预算。
- 根因是前序治理把焦点放在 provider wiring helper，没有把 timeout policy ownership 收敛到
  provider adapter 的公开 surface。成熟 Kappa/CQRS/worker 控制面里，执行预算属于统一 runtime lane
  policy，不能由低层 transport/client 自带第二套默认值。

修复：

- 删除 `LiteLLMPulseDecisionClient` 的 `_DEFAULT_TIMEOUT_SECONDS` 和 `timeout_seconds` property。
- `LiteLLMPulseDecisionProvider.timeout_seconds` 继续从构造时传入的 formal lane timeout 暴露给
  `PulseCandidateJobService` 和 runtime manifest。
- 单测证明底层 client 不再暴露 provider timeout budget；agent execution architecture guard 禁止
  `_DEFAULT_TIMEOUT_SECONDS`、`def timeout_seconds` 和 `return 120.0` 回流。
- `docs/WORKERS.md`、`docs/WORKER_FLOW.md` 和 Pulse domain architecture 明确 timeout 只能由
  provider adapter 映射 formal `pulse.decision` lane。

验证：

- RED 目标验证先失败：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_client_does_not_expose_provider_timeout_budget tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_decision_client_does_not_keep_provider_timeout_fallback -q`
- 修复后同一目标验证通过，`2 passed`。
- Pulse decision client/provider wiring/agent execution architecture 相关非集成套件通过，`51 passed`。
- targeted ruff/mypy、SDD validate、SDD generated index check 和 `git diff --check` 均通过。
- client-only 残留扫描未发现 `_DEFAULT_TIMEOUT_SECONDS`、`def timeout_seconds` 或 `return 120.0`；
  剩余 timeout property 只在 provider adapter 中，且来源是 formal lane settings。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root176 - IngestService 仍保留 event-anchor pending job 的本地 active-window 默认

发现：

- `_assemble_runtime(...)` 已经把 `settings.workers.event_anchor_backfill.active_window_ms`
  传给 `_PooledIngestStore`，但 `_PooledIngestStore.__init__`、`_ingest_service_for_repos(...)`
  和 `IngestService.__init__` 仍保留 `300_000` ms 默认。
- 这个默认直接影响 `event_anchor_backfill_jobs.active_until_ms`，也就是 pending event anchor 的可追赶窗口。
  如果 ingest/helper 层保留本地默认，同一个控制面队列就有两套生命周期政策：worker settings 一套，
  ingest service fallback 一套。
- 根因是前序治理聚焦在 `EventAnchorBackfillWorker` 的构造/settings hard cut，却没有把 job enqueue 端的
  lifetime ownership 同步收敛。成熟 Kappa/CQRS 里，控制面 job 的生命周期必须由单一 runtime policy
  决定；事实写入 service 不能自带 worker catch-up 窗口默认。

修复：

- 删除 `DEFAULT_EVENT_ANCHOR_ACTIVE_WINDOW_MS`。
- `IngestService`、`_PooledIngestStore` 和 `_ingest_service_for_repos` 均要求显式
  `event_anchor_active_window_ms`。
- `_assemble_runtime(...)` 继续从 `settings.workers.event_anchor_backfill.active_window_ms`
  传入；测试工厂和 integration fixture 显式传入 fixture policy。
- 单测证明缺 active-window 参数会 fail fast，bootstrap 单测证明 runtime ingest store 使用 formal
  worker setting，architecture guard 禁止默认常量和默认参数回流。

验证：

- RED 目标验证先失败：`uv run pytest tests/unit/test_ingest_event_market_capture.py::test_pooled_ingest_store_requires_event_anchor_window_contract tests/unit/test_ingest_event_market_capture.py::test_ingest_service_for_repos_requires_event_anchor_window_contract tests/architecture/test_worker_runtime_contracts.py::test_ingest_event_anchor_window_uses_formal_settings_without_service_defaults -q`
- 修复后目标验证加 bootstrap formal-setting 断言通过，`4 passed`。
- Ingest/bootstrap/worker-runtime architecture 相关非集成套件通过，`196 passed`。
- targeted ruff 初次修正 `ingest_service.py` import 排序后通过；targeted mypy、SDD validate、
  SDD generated index check 和 `git diff --check` 均通过。
- 生产残留扫描未发现 `DEFAULT_EVENT_ANCHOR_ACTIVE_WINDOW_MS`、
  `event_anchor_active_window_ms: int =` 或 `event_anchor_active_window_ms=300_000`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root177 - News source claim 仍保留 repository-local 60 秒 lease 默认

发现：

- `NewsFetchWorker` 已经直接读取 formal `settings.workers.news_fetch.batch_size` 和
  `statement_timeout_seconds`，但 claim due `news_sources` 时只传 `limit`，没有传 source claim lease。
- `NewsRepository.claim_due_sources(...)` 因此保留 `_DEFAULT_SOURCE_CLAIM_LEASE_MS = 60_000` 和
  `claim_lease_ms` 默认参数。这个值决定 `news_sources.next_fetch_after_ms` 的临时 claim 延后时间，
  属于 worker 执行预算/租约策略，不应由 repository 自行补默认。
- 根因是 Root159/AC159 治理了 NewsFetchWorker 的构造、session timeout、batch 和 provider/wake
  contract，但没有把 source-claim lease 纳入 formal worker settings，导致 repository 层仍是第二套
  runtime policy。

修复：

- `NewsFetchWorkerSettings` 增加 `lease_ms=60_000`，默认 workers YAML 同步。
- `NewsFetchWorker` 调用 `repos.news.claim_due_sources(...)` 时显式传
  `claim_lease_ms=max(1, int(self.settings.lease_ms))`。
- 删除 `NewsRepository` 的 `_DEFAULT_SOURCE_CLAIM_LEASE_MS` 和 `claim_lease_ms` 默认参数。
- 单测 fake repository 改成必填 `claim_lease_ms`；architecture guard 禁止 repository 默认常量/默认参数回流，
  并要求 settings schema 包含 `news_fetch.lease_ms`。

验证：

- RED 目标验证先失败：`uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_reads_formal_settings_for_session_claim_and_fetch_limit tests/architecture/test_worker_runtime_contracts.py::test_news_fetch_worker_uses_formal_settings_news_settings_and_wake_contract -q`
- 修复后目标验证加 worker settings YAML guard 通过，`3 passed`。
- News worker/provider/projection/settings/worker-runtime architecture 相关非集成套件通过，`254 passed`。
- targeted ruff 初次修正测试 import 排序后通过；targeted mypy、SDD validate、SDD generated index check
  和 `git diff --check` 均通过。
- 生产残留扫描未发现 `_DEFAULT_SOURCE_CLAIM_LEASE_MS` 或 `claim_lease_ms: int =`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root178 - Pulse stale running job timeout 仍散落在 worker 探测和 repository 默认里

发现：

- `PulseCandidateWorker._terminalize_exhausted_stale_running_jobs(...)` 通过
  `getattr(pulse_jobs, "running_timeout_ms", 300_000) or 300_000` 决定 stale running
  job 的 terminalize 窗口。
- `PulseJobsRepository.__init__` 同时保留 `running_timeout_ms=300_000` 默认；多个
  不使用该值的 Pulse repository 也复制了同名构造参数和实例字段。
- `DBPoolBundle` / `repositories_for_connection(conn)` 过去没有 Pulse worker settings
  输入，所以即使 worker settings 已经治理过 windows、queue budget 和 statement timeout，
  `pulse_agent_jobs` running timeout 仍由 repository 层的隐性默认决定。

根因：

- 前序 Root170/AC166 只把 Pulse worker/job-service 的构造、窗口、预算、阈值和 session
  timeout 收敛到 `settings.workers.pulse_candidate`，但没有把 `pulse_agent_jobs` 状态机里的
  “running 多久算 stale/dead”纳入同一个 formal runtime policy。
- 成熟 Kappa/CQRS 中，控制面 job 的 lease/timeout 是 worker 状态机策略，而不是 repository
  的私有默认值。repository 可以执行 SQL 和记录 terminal ledger，但不能决定产品运行预算。
- 未使用 timeout 字段散落在其他 Pulse repository，会制造伪契约：读代码的人会误以为所有
  Pulse 写仓储共享 running timeout，实际只有 `PulseJobsRepository` 使用它。

修复：

- `PulseCandidateWorkerSettings` 增加 `job_running_timeout_ms=300_000`，默认 workers YAML 同步。
- `DBPoolBundle.create(settings)` 从 `settings.workers.pulse_candidate.job_running_timeout_ms`
  读取正式值，并在 `api_session` / `worker_session` 中传给
  `repositories_for_connection(..., pulse_job_running_timeout_ms=...)`。
- `repositories_for_connection` 和 `repository_session` 要求显式
  `pulse_job_running_timeout_ms`，并只把它传给 `PulseJobsRepository`。
- `PulseCandidateWorker` 直接读取 `settings.job_running_timeout_ms`，不再探测 repository
  属性或使用 `300_000` fallback。
- `PulseJobsRepository` 删除构造默认值；其他 Pulse repository 删除无用 `running_timeout_ms`
  参数和实例字段。
- architecture guard 禁止 Pulse repo 构造默认值、无用 timeout state、worker `getattr`
  fallback 和 DBPoolBundle/repository session 漏传 formal timeout。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_worker_runtime_contracts.py::test_pulse_candidate_worker_and_job_service_use_formal_settings_without_runtime_defaults tests/architecture/test_pulse_no_compat.py::test_pulse_job_running_timeout_is_formal_setting_without_repository_defaults -q`
- 修复后同一目标验证通过，`2 passed`。
- Pulse worker / dirty-trigger / PulseJobsRepository / DBPoolBundle / settings 相关非集成套件通过，
  `96 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root179 - Notification delivery stale-running 策略仍是 repository-local 默认

发现：

- `NotificationRepository.__init__` 保留 `running_timeout_ms=300_000` 和
  `stale_running_terminalization_batch_size=100` 默认。
- `claim_next_delivery(...)` 用这两个值决定 running `notification_deliveries` 何时被 terminalize 为
  `dead`，以及每轮 bounded cleanup 的批大小。
- `NotificationDeliveryWorkerSettings` 只包含 `batch_size`、`max_attempts` 和
  `statement_timeout_seconds`，没有承载 delivery running timeout 或 stale-running cleanup batch。
- `DBPoolBundle` / `repositories_for_connection(...)` 过去构造 `NotificationRepository(conn)`，
  因此 delivery 状态机策略由 repository 默认决定，而不是由 worker runtime settings 决定。

根因：

- 前序治理已经把 notification rule/delivery 的 session transaction、statement timeout 和 delivery
  enqueue/requeue 边界收敛到正式契约，但把 `notification_deliveries` running 状态的生命周期预算留在
  repository 层。
- 成熟 Kappa/CQRS 中，repository 负责执行确定的 SQL；“running 多久算 stale/dead”和“一轮清理多少”
  是 worker catch-up/state-machine 策略，应由 `settings.workers.notification_delivery` 统一配置。
- 继续保留 repository-local 默认会造成两套策略入口：运维以为调的是 worker，实际 stale-running
  cleanup 仍按 repository 的 5 分钟/100 行默认运行。

修复：

- `NotificationDeliveryWorkerSettings` 增加 `running_timeout_ms=300_000` 和
  `stale_running_terminalization_batch_size=100`，默认 workers YAML 同步。
- `DBPoolBundle.create(settings)` 从 `settings.workers.notification_delivery` 读取两个正式值，
  并在 `api_session` / `worker_session` 中传给
  `repositories_for_connection(...)`。
- `repositories_for_connection` 和 `repository_session` 要求显式 notification delivery
  stale-running 策略，并把它们传给 `NotificationRepository`。
- `NotificationRepository` 删除构造默认值和旧常量；repository 只使用显式注入的 timeout/batch。
- `bootstrap` 中 `PooledRepository(..., NotificationRepository)` 同步传入 DBPoolBundle 上的正式值。
- architecture guard 禁止 repository 默认值回流，并要求 settings/schema/session 装配存在正式字段。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_workers_read_formal_settings_without_runtime_defaults tests/architecture/test_notifications_hard_cut.py::test_notification_delivery_stale_running_policy_uses_formal_settings_without_repository_defaults -q`
- 修复后同一目标验证通过，`2 passed`。
- Notification worker/repository architecture、DBPoolBundle、settings 相关非集成套件通过，`58 passed`；
  notification + worker-runtime + Pulse/session 横向非集成守卫通过，`305 passed`。
- targeted ruff 和 mypy 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root180 - AccountQuality backfill 批大小仍保留 service-local 默认

发现：

- `AccountQualityBackfillService.backfill_account_token_call_stats(...)` 保留 `limit: int = 1000`。
- CLI `ops backfill-account-quality --limit` 已经有 `default=1000`，且运行路径会显式传
  `limit=args.limit`；service 层再保留默认值形成第二个预算入口。

根因：

- 前序治理把 `AccountQualityBackfillService` 从 public read service 中拆出，并要求 backfill 在一个
  callable connection transaction 中读上游事实、写 `account_profiles`、`account_token_call_stats` 和
  `account_quality_snapshots`。
- 但 ops backfill 的 bounded budget 没有同步从 service 默认里拿掉。Kappa/CQRS 的写侧维护任务即使
  是 ops-only，也应由调用方/CLI 显式给出批大小；service 只执行给定批量，不自行决定 1000 行。

修复：

- `backfill_account_token_call_stats` 改为必填 `limit: int`。
- 现有 CLI 和测试调用均已显式传 `limit`；architecture guard 禁止 `limit: int =` 回流到
  backfill service。
- Account Quality domain architecture、`docs/WORKERS.md` 和 `docs/WORKER_FLOW.md` 说明 backfill
  `limit` 是 CLI/caller budget，不是 service-local default。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_backfill_uses_connection_transaction_without_manual_commit_fallback -q`
- 修复后 AccountQuality backfill 相关非集成目标通过：
  `uv run pytest tests/architecture/test_api_read_paths_provider_free.py::test_account_quality_backfill_uses_connection_transaction_without_manual_commit_fallback tests/unit/test_account_quality_service.py -q`，
  `3 passed, 1 skipped`；skip 原因是本地 PostgreSQL 测试库不可用。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root181 - Signal Pulse 通知查询维度在 settings 和规则引擎里保留两套默认

发现：

- `settings.notifications.rules.signal_pulse_candidate` 的默认 payload 已经定义
  `window="1h"`、`scopes=("all", "matched")` 和
  `statuses=("trade_candidate", "token_watch", "risk_rejected_high_info")`。
- `NotificationRuleEngine._signal_pulse_candidates(...)` 仍保留
  `DEFAULT_SIGNAL_PULSE_WINDOW`、`DEFAULT_SIGNAL_PULSE_SCOPES` 和
  `DEFAULT_SIGNAL_PULSE_STATUSES`，并用 `rule.window or DEFAULT...`、
  `rule.scopes or DEFAULT...`、`rule.statuses or DEFAULT...` 恢复查询面。
- `NotificationsConfig` 过去允许用户或测试 fake 把这些字段显式置空；服务层会静默补回默认，
  所以配置审计无法证明通知 worker 实际查询窗口、scope 和 status 完全来自正式配置。

根因：

- 前序 notification 治理把 worker session、delivery requeue、statement timeout 和 stale-running
  policy 收敛到了正式契约，但遗漏了 notification rule 自身的产品查询维度。
- 在成熟 Kappa/CQRS 中，worker rule 查询面属于 composition/config policy；规则引擎只执行已验证的
  policy，不应该拥有第二套默认。否则同一个通知事实的产生条件同时散落在 settings 和服务层，
  审计时无法判断“为什么这个 candidate 被查询/通知”。
- `or DEFAULT` 对空值的容忍也是兼容性代码：它让 malformed config 或老测试 fake 继续工作，却把
  错误配置伪装成正常默认行为。

修复：

- `settings.py` 将 Signal Pulse notification scope/status 默认提升为命名常量，并让
  `_default_notification_rule_payloads()` 使用这些正式常量。
- `NotificationsConfig` 增加配置校验：`signal_pulse_candidate.window/scopes/statuses` 为空会失败，
  window/status/scope 不在允许集合内也会失败。
- `NotificationRuleEngine` 删除服务层 Signal Pulse 默认常量和 `or DEFAULT` 兜底；规则引擎直接读取
  已验证 rule，缺字段时抛 `signal_pulse_notification_rule_config_required`。
- architecture guard 禁止 `DEFAULT_SIGNAL_PULSE_*` 和 `rule.window/scopes/statuses or` 回流到规则引擎。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_signal_pulse_notification_rule_uses_formal_config_without_service_defaults tests/unit/test_settings.py::test_signal_pulse_notification_rule_rejects_empty_query_dimensions -q`，
  `7 failed`。
- 修复后同一目标验证通过，`7 passed`。
- Notification rules / settings / architecture 非集成套件通过：
  `uv run pytest tests/unit/test_notification_rules.py tests/unit/test_settings.py tests/architecture/test_notifications_hard_cut.py -q`，
  `122 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root182 - notification candidate_limit 配置会被服务层 50 行地板值覆盖

发现：

- `NotificationsConfig.candidate_limit` 默认是 50，并且测试已经覆盖用户可以把它配置成 40。
- 但 `NotificationRuleEngine._limit()` 返回 `max(DEFAULT_LIMIT, int(settings.notifications.candidate_limit))`，
  所以低于 50 的正式配置不会真正进入 watched-account、account-token-alert 和 Signal Pulse
  candidate 查询。
- 这让配置表面上生效，运行时又被服务层硬地板覆盖；`candidate_limit=0` 也能加载，只是后续被
  `max(50, 0)` 遮住。

根因：

- 前序 Root181 收敛了 Signal Pulse rule 的查询维度，但同一个 notification rule engine 仍把
  candidate 查询预算当成服务层“保护性默认”处理。
- Kappa/CQRS 的 worker/read-model 查询预算必须从配置或 worker settings 明确进入执行路径；
  如果服务层偷偷加地板，运维无法通过配置缩小每轮扫描，也无法从代码审计中确认真实 SQL limit。
- `max(DEFAULT_LIMIT, config)` 是兼容性兜底而不是策略表达。真正的最小合法值应在 settings schema
  里失败，而不是在运行时恢复成另一个值。

修复：

- `NotificationsConfig.candidate_limit` 改为 `Field(default=50, ge=1)`，非法 0/负数在配置加载阶段失败。
- `NotificationRuleEngine` 删除 `DEFAULT_LIMIT`，`_limit()` 直接返回
  `settings.notifications.candidate_limit`。
- 新增行为测试证明 `candidate_limit=12` 会原样传给 Signal Pulse `list_candidates(...)`。
- architecture guard 禁止 `DEFAULT_LIMIT`、`max(DEFAULT_LIMIT, ...)` 或服务层 50 行地板回流。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_rule_candidate_limit_uses_formal_config_without_service_floor tests/unit/test_notification_rules.py::test_signal_pulse_candidate_limit_uses_configured_notification_limit_without_service_floor tests/unit/test_settings.py::test_notification_candidate_limit_rejects_zero -q`，
  `3 failed`。
- 修复后同一目标验证通过，`3 passed`。
- Notification rules / settings / architecture 非集成套件通过：
  `uv run pytest tests/unit/test_notification_rules.py tests/unit/test_settings.py tests/architecture/test_notifications_hard_cut.py -q`，
  `125 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root183 - 非 Signal notification rule 接受未使用的 window/scopes/statuses 字段

发现：

- `NotificationRuleConfig` 是共享模型，包含 `window`、`scopes`、`statuses` 字段。
- 这些字段实际只被 `signal_pulse_candidate` 消费；`watched_account_activity` 使用固定
  `WATCHED_ACTIVITY_WINDOW_MS`，`watched_account_token_alert` 调用 `account_alerts(window="1h")`，
  `news_high_signal` 走自己的 high-signal story 查询。
- 过去 settings 只禁止了 `news_high_signal.statuses` 和旧 score thresholds，没有禁止
  watched/news 规则上的 `window` 或 `scopes`，也没有禁止 watched 规则上的 `statuses`。
  结果是配置可以加载成功，但运行时完全忽略这些字段。

根因：

- 前序治理聚焦于运行时默认值和 repository/session 边界，但 notification rule config 仍用一个宽模型表达
  多种规则。宽模型没有配套 rule-specific validation 时，就会形成“看似支持”的假配置面。
- CQRS worker 的查询输入必须可审计：每个配置字段要么进入确定 SQL/query contract，要么在配置层失败。
  允许未使用字段加载成功，会让 operator 以为改变了查询窗口或过滤范围，实际 notification facts 的生成条件
  没有变化。
- 这不是向后兼容，而是沉默忽略；它比显式失败更难排查，因为最终事实表里看不到“配置被忽略”的证据。

修复：

- `NotificationsConfig.parse_rules(...)` 对 `watched_account_activity` 和
  `watched_account_token_alert` 明确禁止 `window/scopes/statuses`，只允许 delivery settings。
- `news_high_signal` 的 forbidden set 扩展为禁止 `window/scopes/statuses` 以及旧 score thresholds。
- 新增 settings 单测覆盖 watched/news 非 Signal rule 的未使用 query 字段会失败。
- architecture guard 检查非 Signal 规则的 rule-specific validation 不被移除。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_settings_reject_unused_query_fields_for_non_signal_rules tests/unit/test_settings.py::test_notification_settings_reject_unused_query_fields_for_non_signal_rules -q`，
  `9 failed`。
- 修复后同一目标验证通过，`9 passed`。
- Notification rules / settings / architecture 非集成套件通过：
  `uv run pytest tests/unit/test_notification_rules.py tests/unit/test_settings.py tests/architecture/test_notifications_hard_cut.py -q`，
  `134 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root184 - NotificationWorker 仍兼容 insert outcome 的旧 row-dict 形态

发现：

- `NotificationRepository.insert_notification_with_outcome(...)` 已经定义正式返回类型
  `NotificationInsertOutcome(row, created, aggregated)`。
- `NotificationWorker._process_once_sync(...)` 却用
  `getattr(outcome, "row", outcome)`、`getattr(outcome, "created", True)` 和
  `getattr(outcome, "aggregated", False)` 兼容旧形态：repository 可以直接返回 row dict，worker
  会默认当成 created row。
- 单测 fake 也用 `SimpleNamespace(row=..., created=..., aggregated=...)`，没有强制使用正式 outcome。

根因：

- 前序 notification 治理把 insert-only fallback、requeue contract、session UoW 和 repository transaction
  都收紧了，但留下了返回值形态兼容。这个兼容会把“仓储没有实现正式 outcome 合约”伪装成新建通知成功。
- 对 notification rule worker 来说，`created` 和 `aggregated` 不是 UI 信息，而是决定是否 enqueue external
  delivery、是否 requeue aggregated high-signal delivery、是否计入 batch limit 的控制面分支。默认
  `created=True` 会错误打开外部 delivery 路径。
- 成熟 CQRS worker 应该让写仓储返回一个明确的命令结果类型；worker 不应该从裸 row 或缺字段对象推断状态机结果。

修复：

- `NotificationWorker` 直接读取 `outcome.row`、`outcome.created`、`outcome.aggregated`，删除
  `getattr(outcome, ..., default)` 形态兼容。
- `_insert_candidate_with_repository(...)` 返回类型标注为 `NotificationInsertOutcome`。
- 单测 fake 改用正式 `NotificationInsertOutcome`，并新增坏仓储返回 row dict 时 worker 失败的测试。
- architecture guard 禁止 `getattr(outcome, ...)` 回流。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_worker_uses_formal_insert_outcome_without_shape_fallback tests/unit/test_notification_worker_runtime.py::test_worker_requires_formal_insert_outcome_contract_without_row_fallback -q`，
  `2 failed`。
- 修复后同一目标验证通过，`2 passed`。
- Notification worker / rules / architecture 非集成套件通过：
  `uv run pytest tests/unit/test_notification_worker_runtime.py tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py -q`，
  `75 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root185 - PulseEvidenceBuilder 仍兼容非正式 PulseCandidateContext 形态

发现：

- `PulseEvidenceBuilder.build(...)` 的签名已经声明 `context: PulseCandidateContext`，但实现仍大量使用
  `getattr(context, "...", default)`。
- `PulseEvidenceSourceRepository.list_market_facts(...)` / `list_identity_facts(...)` 继续通过
  `_context_value(...)` 和 `_context_raw(...)` 支持 `dict` context 与任意对象 context。
- 单测夹具使用 `SimpleNamespace` 构造 context，导致缺少 `candidate_type`、`subject_key`、`trigger_signature`
  等正式字段时，builder 仍能产出 sealed packet，并把缺失字段转成 `unknown`、空字符串或空证据上下文。

根因：

- Root90 已经把 evidence source repository 方法收紧成正式调用，但只治理了“仓库方法是否存在”，没有治理
  “传入证据包构建器的 candidate context 是否是正式域对象”。
- 在成熟 Kappa/CQRS 里，sealed evidence packet 是 LLM 之前的事实边界；它不能从半结构 payload、旧 job JSON
  或测试便利对象推断关键身份。否则 `candidate_id/target/window/scope/factor_snapshot/source_event_ids`
  的缺失会被静默降级，后续 `pulse_evidence_packets`、gate、run/eval audit 仍看起来完整。
- PostgreSQL 最佳实践角度，builder 和 source repository 的查询键必须来自一个明确的 typed command/context，
  不能让 dict/object duck typing 决定 SQL lookup key。否则查询可能退化成空 lookup、错误 market route 或缺
  pricefeed 补查，表现为“没有证据”，根因却是调用形态错误。
- 这类兼容不是 KISS，而是第二套输入协议；它让 worker/repository 边界的错误延迟到 read-model 质量下降之后才暴露。

修复：

- `PulseEvidenceBuilder` 直接读取 `context.factor_snapshot`、`source_event_ids`、`evidence_event_ids`、
  `candidate_id`、`target_type`、`target_id`、`symbol`、`window`、`scope`、`gate_result` 和
  `selected_posts`。
- `_current_discussion_digest(...)`、`_list_market_facts(...)`、`_market_contract(...)` 改为正式
  `PulseCandidateContext` 输入，不再接受 `Any` context 或 `PulseCandidateContext | Any`。
- `PulseEvidenceSourceRepository` 删除 `_context_value(...)` / `_context_raw(...)`，market/identity lookup
  直接读取 `PulseCandidateContext` 字段和 `factor_snapshot`。
- `test_pulse_evidence_packet_builder.py` 的夹具改用真实 `PulseCandidateContext`，并新增 malformed
  `SimpleNamespace` context 会在入口失败的单测。
- architecture guard 禁止 `getattr(context, ...)`、`context.get(...)`、`context: Any` 和 context helper
  回流到 evidence packet builder/source repository。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_evidence_builder_requires_formal_candidate_context_without_shape_fallback tests/unit/test_pulse_evidence_packet_builder.py::test_builder_requires_formal_candidate_context_without_shape_fallback -q`，
  `2 failed`。
- 修复后同一目标验证通过，`2 passed`。
- Pulse evidence builder / Pulse architecture 非集成套件通过：
  `uv run pytest tests/unit/test_pulse_evidence_packet_builder.py tests/architecture/test_pulse_no_compat.py -q`，
  `39 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root186 - Queue Terminal source-row 写入仍保留裸 conn.commit

发现：

- Root35 已经把 `resolve_terminal_event(...)` 收紧到 connection transaction，用于保护
  `SELECT ... FOR UPDATE`、operator action update 和 retry transition。
- 但同一个平台模块里的 `terminalize_source_row(..., commit=True)` 仍在写入
  `worker_queue_terminal_events` 后直接调用 `conn.commit()`。
- 这意味着直接调用平台 terminal ledger helper 的路径，只要传 `commit=True`，仍可以绕过正式
  `conn.transaction()` contract；缺少 transaction 的测试 fake 也能写 terminal ledger。

根因：

- 前序治理把“operator resolve”当成独立控制面状态机处理，但平台 terminal ledger 的“source-row
  terminalization”仍保留了旧 repository 风格的 `commit=True` 裸提交协议。
- `worker_queue_terminal_events` 不是普通日志表；它是 worker queue terminal state 的可审计证据。
  成熟 Kappa/CQRS 里，terminal ledger 写入必须与上游 queue delete/job terminal state 在同一事务中完成，
  或者在 helper 自己拥有提交时显式打开 connection transaction。
- PostgreSQL 最佳实践上，`ON CONFLICT ... RETURNING` 写 terminal ledger 后裸 `conn.commit()` 会把事务边界
  伪装成连接能力；一旦 future caller 在 `commit=True` 下叠加 retry/delete/update，就会重新出现部分提交风险。
- 这不是为了兼容旧调用方应该保留的 convenience，而是第二套提交协议；根修应该让 `commit=True`
  也走同一个 `_transaction(conn)`。

修复：

- `terminalize_source_row(..., commit=True)` 现在先进入 `_transaction(conn)`，再递归调用
  `commit=False` 的同一写逻辑，避免复制 SQL 和裸提交。
- 缺少 callable transaction 时，在任何 terminal generation 查询或 ledger insert 前抛
  `RuntimeError("queue_terminal_transaction_required")`。
- architecture guard 扩展为要求 `terminalize_source_row` 与 `resolve_terminal_event` 一样使用
  `with _transaction(conn):`，并禁止整个 queue_terminal 模块重新出现 `conn.commit()`。
- 新增单测证明缺 transaction 的连接在 `commit=True` 下 `conn.sql == []` 且没有写入 terminal row。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/unit/test_queue_terminal.py::test_terminalize_source_row_requires_connection_transaction_when_committing tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_terminal_operator_resolution_requires_transaction_without_nullcontext -q`，
  `2 failed`。
- 修复后同一目标验证通过，`2 passed`。
- Queue terminal / CLI queue ops 非集成套件通过：
  `uv run pytest tests/unit/test_queue_terminal.py tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_terminal_operator_resolution_requires_transaction_without_nullcontext -q`，
  `22 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root187 - OpenNews REST scan policy 仍保留 integration-local 默认值

发现：

- 默认 `news_intel.sources` 已经给 `opennews-news`、`opennews-listing`、`opennews-onchain`
  写入 `rest_limit=100`、`max_rest_pages=5`、`rest_overlap_ms=900_000`。
- `NewsFetchWorker` 同时会把正式 `settings.workers.news_fetch.batch_size` 作为 provider fetch
  `limit`，并用 source policy / durable cursor 计算 OpenNews `since_ms`。
- 但 `OpenNewsFeedClient` 内部仍保留 `DEFAULT_REST_LIMIT=100`、`DEFAULT_MAX_REST_PAGES=5`、
  `DEFAULT_REST_OVERLAP_MS=900_000`、`MIN_REST_OVERLAP_MS=600_000` 和 `DEFAULT_REST_PAGE=1`。
  这让缺失 source policy 的测试或运行时来源仍能“成功抓取”，实际行为由 integration client
  悄悄决定。
- worker 侧还接受 source policy 里的旧 `overlap_ms` 别名，虽然文档和默认配置只承认
  `rest_overlap_ms`；这会让 operator 以为自己配置的是新 REST policy，运行时却仍保留第二个名字。

根因：

- OpenNews 从短生命周期 WebSocket hard-cut 到 REST-only 后，只删除了 transport 兼容路径；
  REST scan 的预算/窗口策略没有同步完成边界迁移。
- 成熟 Kappa/CQRS 的 provider adapter 应该只实现外部协议和 payload normalization；“扫多少页、每页多少条、
  回看多久”是 worker/source policy，属于可审计运行时策略，不应该藏在 integration client。
- PostgreSQL/worker 最佳实践角度，cursor high watermark 和 overlap window 是 catch-up 边界的一部分。
  如果 worker 用 source policy 算 `since_ms`，client 又用自己的默认 overlap/floor 决定停止页，就会形成
  两套 catch-up 语义：数据库里看到的是一个策略，实际 provider scan 执行的是另一个策略。
- 这类默认值不是 KISS，而是兼容兜底；它降低了配置缺失的可见性，让生产问题表现为“OpenNews 数据断层、
  重复或过度拉取”，而不是在 source policy 缺失处直接失败。

修复：

- 删除 `OpenNewsFeedClient` 的 REST page/limit/max-pages/overlap 默认常量和 overlap floor，只保留
  `MAX_REST_LIMIT` 这个 provider 协议上限。
- `_rest_limit(...)` 现在要求 source policy `rest_limit` 或 worker 传入的 formal `limit`；两者都缺失时
  直接报 `OpenNews REST fetch policy missing rest_limit`。
- `_max_rest_pages(...)` 要求 `max_rest_pages`；`_rest_overlap_ms(...)` 要求 source policy
  `rest_overlap_ms` 或 durable cursor `overlap_ms`，不再从 client 默认值生成游标策略。
- `_rest_search_body(...)` 的 page 只来自内部扫描循环，不再读取 policy/default page。
- `NewsFetchWorker._fetch_policy_overlap_ms(...)` 删除 source policy 的 `overlap_ms` 兼容别名；`overlap_ms`
  只作为 durable cursor 字段保留。
- 单元测试补齐 OpenNews REST policy 缺失直接失败的 RED/GREEN；架构测试禁止
  `DEFAULT_REST_*` / `MIN_REST_OVERLAP_MS` 回流，并禁止 worker 重新读取 source policy
  `overlap_ms`。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_client_requires_formal_rest_fetch_policy_without_defaults tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_fetch_policy_has_no_integration_local_defaults -q`，
  `4 failed`。
- 修复后同一目标验证通过，`4 passed`。
- OpenNews client / provider registry / News worker OpenNews since-ms / OpenNews architecture 非集成小套件通过：
  `uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_news_workers.py::test_opennews_fetch_since_uses_cursor_overlap_not_agent_brief_age tests/unit/domains/news_intel/test_news_workers.py::test_opennews_first_fetch_since_uses_optional_fetch_policy_catchup_only tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_client_runtime_reports_rest_transport_without_fetch_mode_surface tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_poster_uses_async_http_contract_without_isawaitable_fallback tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_fetch_bridge_uses_formal_coroutine_close_contract_without_optional_probe tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_opennews_rest_fetch_policy_has_no_integration_local_defaults tests/architecture/test_news_intel_boundaries.py::test_opennews_runtime_has_no_short_lived_websocket_fetch_path -q`，
  `32 passed`。
- targeted ruff / mypy 通过；生产残留扫描没有发现 `DEFAULT_REST_*`、`MIN_REST_OVERLAP_MS`
  或 source policy `overlap_ms` alias；SDD 校验、work index check 和 `git diff --check` 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root188 - Macrodata FRED env 在 runner/service 中仍保留本地默认

发现：

- `MacrodataProviderConfig` 已经把 `macrodata_fred_api_key_env` 作为正式 root setting，并且默认值在
  settings/schema 层声明为 `FINANCE_FRED_API_KEY`。
- 但 `MacrodataBundleRunner` 仍保留 `DEFAULT_FRED_API_KEY_ENV = "FINANCE_FRED_API_KEY"`，
  `MacroSyncService` 也保留 `_DEFAULT_FRED_API_KEY_ENV = "FINANCE_FRED_API_KEY"`。
- 当 operator 显式把 `macrodata_fred_api_key_env` 配成 `null`，运行时仍会把 env 名恢复为
  `FINANCE_FRED_API_KEY`，诊断里显示该 env 名，并继续允许从进程环境读取 FRED key。

根因：

- Root172/AC168 已经删除旧 `settings.providers.macrodata.*` 和 root timeout fallback，但只收紧了
  “从哪里读设置”，没有继续审计“谁拥有默认值”。结果是默认值同时存在于 settings 和两个运行时代码点。
- 在成熟 Kappa/CQRS 中，默认策略属于配置 schema / composition root；worker service 和 integration runner
  只消费已经解析后的正式设置。否则 `null` 这种 operator 意图会被下游恢复成“默认启用”，配置就不再是事实。
- 这不是纯粹的 secret ergonomics 问题。FRED key 是否可用会影响 macrodata child process 的 provider 行为、
  `macro_sync_runs` source health、diagnostics，以及后续 macro observations 的完整性。运行时第二套默认值会让
  DB audit 显示“使用正式配置”，实际 provider IO 却受进程环境隐式影响。
- PostgreSQL/worker 最佳实践角度，source-health 和 import audit 必须可由持久配置解释；不能让同一个 worker 在
  相同 settings row/config 下，因为宿主环境残留变量而走不同的事实摄取路径。

修复：

- 删除 runner/service 的 `DEFAULT_FRED_API_KEY_ENV` / `_DEFAULT_FRED_API_KEY_ENV`。
- `_configured_fred_env_name(...)` 现在直接读取 `macrodata_fred_api_key_env`；缺字段报正式 contract error，
  `None` 或空字符串表示关闭 env lookup。
- `fred_api_key_state(...)` 和 `_fred_api_key_state(...)` 只在 env 名存在时检查进程环境。
- `MacrodataBundleRunner.history_bundle(...)` 只在显式 secret 缺失且 env 名存在时注入 `FRED_API_KEY`。
- architecture guard 禁止本地默认常量回流；单测覆盖 disabled env 不被恢复为 `FINANCE_FRED_API_KEY`。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runner_honors_disabled_fred_env_without_defaulting tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_honors_disabled_fred_env_without_defaulting tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback -q`，
  `3 failed`。
- 修复后同一目标验证通过，`3 passed`。
- Macrodata FRED policy 非集成小套件通过：
  `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runner_injects_fred_env_without_exposing_secret tests/unit/test_cli_macro_commands.py::test_macrodata_runner_injects_configured_fred_key_without_exposing_secret tests/unit/test_cli_macro_commands.py::test_macrodata_runner_honors_disabled_fred_env_without_defaulting tests/unit/test_cli_macro_commands.py::test_macrodata_runner_passes_configured_timeout_to_child_process tests/unit/test_cli_macro_commands.py::test_macrodata_runner_timeout_raises_redacted_runner_error tests/unit/test_cli_macro_commands.py::test_macrodata_runner_removes_stale_parent_fred_key_when_configured_env_missing tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_requires_formal_fred_env_settings_contract tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_honors_disabled_fred_env_without_defaulting tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback -q`，
  `9 passed`。
- targeted ruff / mypy 通过；生产残留扫描没有发现 `DEFAULT_FRED_API_KEY_ENV` 或
  `_DEFAULT_FRED_API_KEY_ENV`；注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root189 - News 当前状态写入仍接受 dict/alias/default payload

发现：

- `NewsItemProcessWorker` 已经在处理阶段计算正式的 `NewsMarketScope`、`NewsStoryIdentity` 和
  `NewsItemAgentAdmission` 对象。
- 但 `NewsRepository.update_item_market_scope_and_story_identity(...)`、
  `update_item_market_scope_and_agent_admission(...)`、`update_item_agent_admission(...)`
  仍允许 `Mapping` / `Any` payload 进入写侧。
- `_strict_current_dataclass_or_mapping_payload(...)` 会接受 dict，也会探测对象是否有 `to_payload()`；
  `_agent_admission_payload(...)` 还会接受 `agent_representative_news_item_id`、
  `representative_item_id` 等别名，并在缺字段时恢复 `needs_review` / 默认 version / eligible 推导。
- 这些字段最终写入 `news_items.market_scope_json`、`story_identity_json`、`story_key` 和
  `agent_admission_*`。它们不是展示层临时字段，而是 News page projection 和 item brief work 的当前事实输入。

根因：

- 前序修复把 worker 的计算结果收敛成领域对象，但没有同步收紧 repository command boundary；
  写侧仍保留了“为了旧测试/旧调用方也能写”的第二套协议。
- 成熟 CQRS 中 command side 的写入应该由明确命令对象表达业务含义，read/projection side 才可以把数据库行或
  JSON payload 组装成公开展示结构。这里把两者混在同一个 helper 里，导致读侧归一化能力反向污染写侧。
- agent admission 的别名和默认值尤其危险：一个缺少 `version`、`eligible` 或正式 representative 字段的旧 dict
  也能被写入当前状态，看起来像新的正式决策。这会让后续 page projection、brief gating、dirty enqueue
  基于“补出来”的状态运行，而不是基于真实处理阶段产物运行。
- PostgreSQL 最佳实践角度，JSONB/current columns 应该存储已经验证过的业务对象；如果 repository 在 SQL 前
  静默补 shape/default，数据库里的 current state 就无法从上游事实链路完全解释，审计时也分不清是 worker
  做出的决策，还是写 helper 做出的兼容修正。

修复：

- `NewsRepository` 当前状态写入口签名收窄为正式 `NewsMarketScope`、`NewsStoryIdentity`、
  `NewsItemAgentAdmission`。
- 删除 `_strict_current_dataclass_or_mapping_payload(...)`；市场范围和故事身份写 payload 直接从 dataclass
  原字段构造并校验 required/list/mapping/text，不再接受 dict 或可选 `to_payload()` 探测。
- `_agent_admission_payload(...)` 现在只接受 `NewsItemAgentAdmission`，并显式校验
  `status`、`reason`、`representative_news_item_id`、`basis`、`version`；写侧不再补 `needs_review`
  或默认 version，也不再接受别名。
- 页面投影/公开读取需要的 row normalization 拆到 `_agent_admission_mapping_payload(...)` 和
  `_agent_admission_public_payload(...)`，保留读侧列到展示 payload 的转换，但不作为写命令协议。
- `NewsItemProcessWorker._strict_current_payload(...)` 也删除 `Mapping` 分支和 `to_payload` 探测，只接受正式
  `NewsMarketScope` / `NewsStoryIdentity`。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_update_item_market_scope_and_story_identity_requires_formal_current_objects_without_mapping_fallback tests/unit/domains/news_intel/test_news_repository_queries.py::test_update_item_agent_admission_requires_formal_admission_without_alias_or_default_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_item_payload_writes_require_domain_objects_without_mapping_or_alias_defaults -q`，
  `3 failed`。
- 修复后同一目标验证通过，`3 passed`。
- News current-payload 非集成小套件通过：
  `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_fails_when_agent_admission_context_missing tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_market_scope_shape_before_persistence tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_story_identity_shape_before_persistence tests/architecture/test_news_intel_kiss_simplification.py -q`，
  `60 passed`。
- targeted ruff / mypy 通过；函数级残留扫描确认当前写 helper 中没有 `Mapping`、`admission: Any`、
  `isinstance(value, Mapping)`、可选 `to_payload` 探测、agent admission 别名、`needs_review` 或 version 默认值。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root190 - Pulse dirty-trigger 策略仍一半藏在 worker 本地常量

发现：

- `PulseCandidateWorkerSettings` 已经承载 windows/scopes、batch/queue budget、agent attempts、
  `job_running_timeout_ms`、trigger/gate thresholds 和 statement timeout。
- 但同一条 dirty-trigger/admission 链路里，trigger claim lease、capacity retry、error retry、
  target/candidate edge budget、failure-circuit 阈值和 failure reason 集合仍分散在
  `pulse_candidate_worker.py` 本地常量或 `PulseAdmissionPolicy` 的硬编码 `3`。
- 这些值直接决定 `pulse_trigger_dirty_targets.claim_due(...)` 的租约、capacity backpressure 的
  reschedule 时间、dirty-target error retry 时间、`pulse_target_run_budget` /
  `pulse_candidate_run_budget` 的 admission 限额，以及 recent schema failure 是否打开 circuit。

根因：

- Root170/AC166 把 Pulse Candidate 的主要执行拓扑和 session timeout 迁入正式 worker settings，
  但没有继续把 dirty-trigger 控制面策略一起迁走，导致一个 worker 内出现两套策略来源：
  operator-visible settings 和 operator 不可见的模块常量。
- 成熟 Kappa/CQRS 中，worker 的重放、限流、retry 和 admission gate 必须能从配置与数据库 ledger
  解释。这里 edge budget 和 retry 间隔会改变哪些 dirty target 进入 agent job、哪些 target 被延后或抑制；
  如果它们藏在代码常量中，DB 里的 queue/admission 状态只能解释“发生了什么”，不能解释“为什么按这个预算发生”。
- PostgreSQL 最佳实践角度，`SELECT ... FOR UPDATE` / run-budget 表一类控制面写入应由显式 policy 参数驱动；
  repository SQL 不应被 worker-local magic number 隐式约束。否则调参只能改代码，生产排障也无法对照
  `~/.parallax/workers.yaml` 复现实例行为。
- 未使用的 `PULSE_FAILURE_CIRCUIT_PER_HOUR` 还制造了额外误导：代码看起来有一个阈值常量，实际生效的是
  policy 内部硬编码。这样的“假配置”比缺配置更危险，因为审计时会读错事实来源。

修复：

- `PulseCandidateWorkerSettings` 增加 `trigger_lease_ms`、`trigger_capacity_retry_ms`、
  `trigger_error_retry_ms`、`target_edge_budget_per_hour`、`candidate_edge_budget_per_hour`、
  `failure_circuit_per_hour` 和非空 `failure_circuit_reasons`，默认 workers YAML 同步暴露。
- `PulseCandidateWorker` 构造时直接读取这些 settings 字段；dirty-trigger claim、capacity reschedule、
  error retry、low-information hide、exited-target suppression、normal admission budget claim 全部使用
  worker settings 注入的值。
- `_is_asset_trigger(...)` 和 `_asset_trigger_signature(...)` 不再隐式构造默认
  `PulseTriggerThresholds()`；trigger threshold 必须由 worker/settings 显式传入。
- `_recent_target_failure_count(...)` 接收正式 `failure_circuit_reasons`；`PulseAdmissionPolicy.classify(...)`
  接收 `failure_circuit_per_hour` 并由 worker 显式传入，删除 runtime 生效路径中的硬编码阈值。
- architecture guard 禁止旧 `PULSE_*` 策略常量、`PulseTriggerThresholds()` 默认和
  `recent_failure_count >= 3` 魔法阈值回流；单测证明配置的 candidate budget、retry/lease 和 failure circuit
  阈值会真正到达 repository/policy 边界。

验证：

- 目标非集成验证通过：
  `uv run pytest tests/unit/test_pulse_candidate_worker.py::test_edge_budget_uses_formal_candidate_limit_setting tests/unit/test_pulse_candidate_worker.py::test_low_information_hide_requires_repository_contract tests/unit/test_pulse_candidate_worker.py::test_scan_global_pending_cap_bounds_enqueues_across_windows_and_scopes tests/unit/test_pulse_candidate_worker.py::test_recent_schema_failure_circuit_uses_formal_threshold_and_reason_settings tests/unit/test_pulse_candidate_worker.py::test_pulse_worker_uses_formal_settings_fields_and_session_timeout tests/unit/test_worker_settings.py::test_default_workers_yaml_contains_canonical_worker_defaults tests/unit/test_worker_settings.py::test_worker_settings_reject_zero_pulse_candidate_trigger_policies tests/unit/test_worker_settings.py::test_worker_settings_reject_empty_pulse_failure_circuit_reasons tests/unit/test_settings.py::test_load_settings_accepts_yaml_handle_list_as_public_subscription tests/unit/test_settings.py::test_default_workers_yaml_keys_match_manifest_worker_names tests/architecture/test_worker_runtime_contracts.py::test_pulse_candidate_worker_and_job_service_use_formal_settings_without_runtime_defaults -q`，
  `11 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root191 - Pulse admission policy 对 malformed failed job row 补默认 max_attempts

发现：

- `PulseCandidateWorker._enqueue_if_due(...)` 会读取 `repos.pulse_jobs.job_for_candidate(...)`，把现有
  `pulse_agent_jobs` 行交给 `PulseAdmissionPolicy.classify(...)` 判断是否 suppress 新 admission。
- 当 existing job 的 `status == "failed"` 时，policy 通过 `job.get("attempt_count")` 和
  `job.get("max_attempts")` 判断是否还有 retry 空间。
- 旧代码在 `max_attempts` 缺失或无法解析时执行 `_int(job.get("max_attempts")) or 3`，把 malformed
  persisted job row 补成“最多 3 次尝试”的 retryable failed job。

根因：

- 前序 Pulse 治理把 repository 方法、dirty-trigger transaction、job enqueue 的 formal settings 都收紧了，
  但 admission policy 仍保留了面向旧 row/test fake 的宽松 shape 解释。
- `pulse_agent_jobs.max_attempts` 是入队时由 worker settings 写入的控制面事实；它不是 policy 可以自行恢复的展示字段。
  如果 row 缺失该字段，正确行为是让 dirty trigger fail/retry 并暴露 malformed repository/DB row，而不是静默
  suppress 新 admission。
- 这个默认尤其隐蔽：它不写新 SQL，却改变了是否 enqueue agent job。最终表现是 `pulse_candidate_edge_state`
  看起来因为 `retryable_failed_job` 被抑制，但根因其实是 job row shape 不完整。
- PostgreSQL 最佳实践角度，状态机 ledger row 必须以完整列契约驱动状态转移；不能把缺列/坏值在纯 policy
  层改写成可用默认值，否则 DB audit 无法区分真实 failed job 与损坏/旧 shape job。

修复：

- `PulseAdmissionPolicy` 新增 `_failed_job_attempt_contract(...)`，对 failed existing job 直接读取
  `job["attempt_count"]` 和 `job["max_attempts"]`。
- 缺字段、不可解析、负 `attempt_count` 或非正 `max_attempts` 统一抛
  `pulse_existing_failed_job_attempt_contract_required`，由 worker dirty-trigger error path 记录并 retry。
- 删除 `_int(...)` helper 以及 `max_attempts or 3` 默认；architecture guard 禁止该 fallback 回流。
- 单测覆盖纯 policy contract 和 worker dirty-trigger 行为：malformed failed job 不会 mark dirty target done。

验证：

- RED 目标验证先失败：
  `uv run pytest tests/unit/test_pulse_admission_policy.py::test_policy_rejects_failed_job_missing_attempt_contract_without_default tests/unit/test_pulse_candidate_worker.py::test_malformed_failed_existing_job_fails_dirty_trigger_instead_of_defaulting_attempts tests/architecture/test_worker_runtime_contracts.py::test_pulse_candidate_worker_and_job_service_use_formal_settings_without_runtime_defaults -q`，
  `3 failed`。
- 修复后同一目标验证通过，`3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root192 - Notification delivery 对 malformed attempt contract 补默认值

发现：

- `NotificationDeliveryWorker` claim 到 `notification_deliveries` 后，失败路径通过 `_failure_outcome(...)`
  判断本次失败是 retryable 还是 dead。
- `NotificationRepository.fail_delivery(...)` 也用同一组字段决定写回 `failed` 还是 `dead`，并计算下一次 retry
  延迟。
- 两处旧代码都把缺失/坏形状的 delivery row 当成可解释状态：worker 使用
  `delivery.get("attempt_count") or 0` 和 `delivery.get("max_attempts") or 1`，repository 使用
  `delivery.get("max_attempts") or 5`。

根因：

- 前序 notification 治理已经把 delivery claim、session transaction、stale-running policy 和
  enqueue/requeue 边界收紧到正式契约，但 delivery 失败状态转移仍保留了面向旧 fake/旧 row shape 的宽松解释。
- `notification_deliveries.attempt_count` 和 `max_attempts` 是 PostgreSQL 控制面 ledger 的必需字段；
  claim SQL 也用 `attempt_count < max_attempts` 选择可运行 row。状态机失败路径不能在 SQL 之外为这些字段补默认值。
- 这个 fallback 会把 corrupted row 伪装成真实 retry/dead 决策：缺 `max_attempts` 时，worker 可能把 row 算成 dead，
  repository 可能按 5 次上限重试。两处默认值甚至不一致，DB audit 无法解释为什么同一个 delivery 在不同边界有不同生命周期语义。
- 成熟 Kappa/CQRS 中，side-effect control ledger 必须以完整持久化字段驱动状态转移；缺列/坏值应暴露为 runtime contract
  错误，而不是被业务层修补成另一个事实。

修复：

- `NotificationDeliveryWorker._failure_outcome(...)` 改为通过 `_delivery_attempt_contract(...)` 直接读取
  `delivery["attempt_count"]` 和 `delivery["max_attempts"]`。
- `NotificationRepository.fail_delivery(...)` 使用同一契约要求；缺字段、不可解析、负 attempt 或非正 max attempts 统一抛
  `notification_delivery_attempt_contract_required`，并在 SQL 前失败。
- 单元测试覆盖 worker fake malformed row 和 repository direct `fail_delivery(...)`；architecture guard 禁止
  `delivery.get("attempt_count")` / `delivery.get("max_attempts")` 默认 fallback 回流。

验证：

- RED：`uv run pytest tests/unit/test_notification_worker_runtime.py::test_delivery_worker_rejects_malformed_delivery_attempt_contract_without_default tests/unit/test_notification_worker_runtime.py::test_notification_repository_fail_delivery_requires_attempt_contract_before_sql -q`
  初始 `2 failed`，证明旧代码没有抛错。
- GREEN：同一目标加 architecture guard
  `uv run pytest tests/unit/test_notification_worker_runtime.py::test_delivery_worker_rejects_malformed_delivery_attempt_contract_without_default tests/unit/test_notification_worker_runtime.py::test_notification_repository_fail_delivery_requires_attempt_contract_before_sql tests/architecture/test_notifications_hard_cut.py::test_notification_delivery_attempt_contract_has_no_default_fallback -q`，
  `3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root193 - Queue Terminal terminal evidence 为缺失 attempt/generation 补默认

发现：

- `terminalize_source_row(...)` 是平台层写入 `worker_queue_terminal_events` 的共享入口，供多个 worker/repository
  把 terminal source row 固化成可审计证据。
- 旧实现会在未显式传入 `attempt_count` 且 `source_row` 缺该字段时，把 terminal event 的 attempt 补成 `0`。
- `_next_terminal_generation(...)` 读取已有 unresolved terminal row 或 max generation 时，会把缺失/空
  `terminal_generation` 补成 `1`；`_terminal_id(...)` 也用 `max(1, int(...))` 再兜一次。

根因：

- 前序 AC182 修掉的是 Queue Terminal 的 connection transaction 边界，但没有继续收紧 terminal evidence 的 row
  契约。于是平台 helper 已经不会裸提交，却仍能把 malformed source/ledger state 写成看似完整的 terminal evidence。
- `worker_queue_terminal_events.attempt_count` 不是展示字段，它回答“这个 source row 经过多少次尝试后 terminal”；
  缺失时写 `0` 会制造假审计证据。
- `terminal_generation` 决定 unresolved snapshot 复用和 operator retry 后的新 terminal attempt identity；缺失时补 `1`
  会把损坏 ledger row 伪装成第一代 terminal event，可能导致 terminal_id、operator action 和后续 retry 归档含义错位。
- 成熟 Kappa/CQRS 中，terminal ledger 是控制面事实的审计投影。平台层不能替源队列表或 ledger 行编造 attempt/generation；
  应该在 SQL 前或读到 malformed generation 时 fail fast，让损坏状态进入可诊断路径。

修复：

- `terminalize_source_row(...)` 在任何 terminal-generation SQL 前解析 attempt contract：显式 `attempt_count` 是正式 override；
  否则 `source_row["attempt_count"]` 必须存在、可转 int 且非负。
- `_next_terminal_generation(...)` 对 unresolved row 和 aggregate row 都要求 `terminal_generation` 存在、可转 int 且为正；
  不再从缺字段/空 row 恢复为 `1`。
- `_terminal_id(...)` 使用同一 positive generation contract，不再 `max(1, int(...))`。
- architecture guard 禁止 attempt/generation fallback token 回流，并要求两个新错误码存在。

验证：

- RED：`uv run pytest tests/unit/test_queue_terminal.py::test_terminalize_source_row_requires_attempt_contract_before_sql tests/unit/test_queue_terminal.py::test_terminalize_source_row_requires_existing_terminal_generation_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_terminal_operator_resolution_requires_transaction_without_nullcontext -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root194 - terminal ledger 调用方用默认 attempt 绕过 Queue Terminal 契约

发现：

- Root193 已把 `terminalize_source_row(...)` 收紧为：显式 `attempt_count` 是正式 override，否则必须从
  `source_row["attempt_count"]` 读取。
- 但三个上游 terminal ledger 调用方仍在传参前执行 `attempt_count=int(row.get("attempt_count") or 0)`：
  `EventAnchorBackfillJobRepository`、`DiscoveryRepository.terminalize_lookup_claims(...)` 和
  `PulseJobsRepository._terminalize_pulse_job(...)`。
- 这会把 malformed source row 转成显式 override `0`，使平台 helper 无法再区分“调用方明确知道 attempt 为 0”和
  “source row 缺 attempt 字段”。

根因：

- 这是典型的分层契约绕过：平台层已经 fail-fast，但调用方在进入平台层前先做兼容恢复，等于把坏事实清洗成合法命令。
- 在 Kappa/CQRS 控制面里，terminal ledger 是 operator 追责和 retry/archive 的证据；上游 repository 不应该替 deleted
  queue row 编造 attempt 数。否则 terminal evidence 仍会显示“0 次尝试后 terminal”，而不是暴露队列表 row contract
  损坏。
- PostgreSQL 最佳实践角度，delete-returning 的 queue row 已经是本次 terminal transition 的 source-of-record snapshot；
  传入 `terminalize_source_row(...)` 时应保留原始 row 契约，而不是在 Python 层把缺字段改写成默认值。

修复：

- 删除 Event Anchor、Discovery、Pulse job terminal ledger callsite 中的
  `attempt_count=int(row.get("attempt_count") or 0)`。
- 让 `terminalize_source_row(...)` 直接从传入的 `source_row` 验证 `attempt_count`，缺失或非法时抛
  `queue_terminal_attempt_contract_required`。
- 新增 architecture guard 覆盖三个 callsite，禁止调用方在平台 contract 前恢复默认 attempt。

验证：

- RED：`uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_terminal_ledger_callers_do_not_default_attempt_count_before_platform_contract -q`
  初始 `1 failed`，列出三个违规文件。
- GREEN：同一 guard 修复后通过，`1 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root195 - Token Radar dirty claim completion key 默认为 attempt_count=0

发现：

- `TokenRadarProjection._claim_key(...)` 和 `_source_claim_key(...)` 会把 target/source dirty claim 转成
  `mark_done(...)` / `mark_error(...)` 使用的 completion key。
- 旧代码用 `int(claim.get("attempt_count") or 0)` 生成 completion key。也就是说，claim row 缺
  `attempt_count` 时，projection 不会立即失败，而是把 malformed claim 转成 `attempt_count=0`。
- 下游 repository 的 `_key_records(...)` 虽然会拒绝 `attempt_count <= 0`，但这个错误发生在 completion
  边界，可能已经执行了 rank-source populate、source request projection 或其它中间 work，也可能掩盖原始处理异常。

根因：

- 前序治理已经把 Token Radar dirty-target claim/done/error 收进显式 transaction，但 completion token 的字段契约仍在
  projection service 层被宽松解释。
- `attempt_count` 是 dirty claim 的乐观完成保护字段：它确保 worker 只完成自己 claim 的那一代 row。缺失时正确行为是
  在 claim 进入任何投影工作前暴露 malformed repository/DB row，而不是让业务投影跑完后再由 repository completion
  报“attempt_count required”。
- 成熟 Kappa/CQRS 的判断是：dirty queue row 是控制面事实，不是可以在 service 层补默认的 DTO。completion key
  必须忠实反映 PostgreSQL claim row。

修复：

- `TokenRadarProjection._rebuild_dirty_targets_in_transaction(...)` 在 claim 后立即构造 target/source completion keys，
  也就立即验证 `attempt_count`。
- `_claim_key(...)` / `_source_claim_key(...)` 改为通过 `_claim_attempt_count(...)` 读取
  `claim["attempt_count"]`；缺字段、不可解析或 `< 1` 统一抛
  `token_radar_dirty_claim_attempt_contract_required`。
- 后续 source dirty done/error 复用已验证的 `source_claim_keys`，target dirty processing 复用
  `target_claim_keys`，避免重新从 claim dict 推导默认值。
- architecture guard 禁止 `claim.get("attempt_count") or 0` 回流。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_target_claim_attempt_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_attempt_contract_before_work tests/architecture/test_token_radar_source_width_contract.py::test_projection_claim_completion_keys_require_attempt_contract_without_defaults -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root196 - News projection dirty completion key 默认为 attempt_count=0

发现：

- `NewsProjectionDirtyTargetRepository._key_records(...)` 是 `mark_done(...)`、`mark_error(...)`、
  `delete_claimed_targets(...)` 和 `terminalize_targets(...)` 的统一 completion-token 入口。
- 旧代码使用 `int(key.get("attempt_count") or 0)`。也就是说，claimed dirty target token 缺
  `attempt_count` 时，repository 不会认为 token malformed，而是生成 `attempt_count=0` 去匹配
  `news_projection_dirty_targets`。
- 这会影响 page/source-quality projection 的 done/error、terminal delete，以及 terminal ledger source row。
  缺失 attempt 本应说明 completion token 没有保留 claim row contract，却被转成了一个合法的零次尝试 claim。

根因：

- 前序修复已经要求 News projection worker 使用 `RepositorySession.transaction`，也要求 dirty-target repository
  自有 commit 进入 connection transaction；但 completion token 的字段契约仍然保留了旧 fake 兼容。
- `attempt_count` 是 dirty queue optimistic completion 的匹配条件。它不是展示字段，也不是可推导默认；缺失时应该在
  任何事务进入或 SQL 执行前暴露 malformed claim/completion token。
- 从 PostgreSQL 最佳实践看，`DELETE ... USING` / `UPDATE ... FROM` 这类队列完成 SQL 应只匹配 worker 实际 claim
  到的 row snapshot。Python 层把缺失字段改成 0，会扩大误匹配空间，也会污染后续 terminal evidence。

修复：

- 新增 `_completion_attempt_count(key)`，直接读取 `key["attempt_count"]`；缺失、不可解析或 `< 0` 时抛
  `ValueError("news projection dirty target completion requires attempt_count from claim_due")`。
- `_key_records(...)` 改为通过该 helper 取 attempt，删除 `key.get("attempt_count") or 0` 兼容。
- 单元测试覆盖 `mark_done(...)`、`mark_error(...)`、`terminalize_targets(...)` 缺 attempt 时在事务和 SQL 前失败。
- architecture guard 禁止 `_key_records` 重新引入 `key.get("attempt_count") or 0`。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_target_completion_requires_claim_attempt_contract_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_completion_keys_require_claim_attempt_contract -q`
  初始 `4 failed`。
- GREEN：同一目标修复后通过，`4 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root197 - Token Radar repository completion helper 仍用默认 attempt 后再失败

发现：

- Root195 已经让 `TokenRadarProjection` 在 service 层提前验证 target/source dirty claim 的 `attempt_count`。
- 但下层两个 repository 仍保留同形兼容恢复：`TokenRadarDirtyTargetRepository._key_records(...)` 和
  `TokenRadarSourceDirtyEventRepository._key_records(...)` 都先执行 `int(key.get("attempt_count") or 0)`，再通过
  `attempt_count <= 0` 抛 completion 错误。
- 行为上缺 attempt 已经不会执行 SQL，但代码语义仍然是“缺字段先恢复成 0”，这保留了旧 fake/旧 DTO 兼容入口，也让错误原因从
  “缺字段”变成“字段值非法”。

根因：

- 这是 Root195 的下沉残留：service 层已经 hard cut，repository 层还没有把 completion token 当作正式 claim row
  contract，而是保留了宽松 dict 读取。
- `token_radar_dirty_targets` 与 `token_radar_source_dirty_events` 的 `claim_due(...)` 都在 SQL 里把
  `attempt_count = queue.attempt_count + 1`，因此 done/error completion key 必须携带正数 attempt。
- 成熟 Kappa/CQRS 中，repository 是控制面边界，不应该依赖“补 0 后再失败”来表达 schema/claim token 损坏；这种
  兼容路径会继续鼓励测试或工具绕开正式 claim row 形状。

修复：

- 两个 repository 都新增 `_completion_attempt_count(key)`，直接读取 `key["attempt_count"]`。
- 缺字段、不可解析或 `<= 0` 时分别抛原有 completion error，并保留缺字段的 `KeyError` cause，便于证明不是默认化。
- architecture guard 覆盖两个 repository，禁止 `key.get("attempt_count") or 0` 和
  `int(key.get("attempt_count") or 0)` 回流。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_target_dirty_completion_requires_claim_attempt_field_without_default tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_completion_requires_claim_attempt_field_without_default tests/architecture/test_token_radar_source_width_contract.py::test_token_radar_dirty_repositories_require_attempt_contract_without_default_completion_keys -q`
  初始 `5 failed`。
- GREEN：同一目标修复后通过，`5 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root198 - Market Tick Current dirty completion helper 仍把缺 attempt 还原成 0

发现：

- `MarketTickCurrentDirtyTargetRepository._claim_records(...)` 会把 `mark_done(...)` / `mark_error(...)`
  的 completion claim 转成 SQL 参数。
- 旧代码先执行 `int(claim.get("attempt_count") or 0)`，再用 `attempt_count <= 0` 抛
  `market tick current dirty target completion requires attempt_count from claim_due`。
- 这意味着 malformed completion claim 缺 `attempt_count` 时不会被识别为字段缺失，而是被恢复成 0 后再失败。

根因：

- Market Tick Current 是市场事实到 Token Radar 的关键 current projection 控制面。它的 dirty queue completion key
  和 Token Radar dirty queue 一样，依赖 claimed row 的 `payload_hash`、`lease_owner`、`attempt_count`
  做乐观完成匹配。
- 前序治理已经要求 repository-owned enqueue/claim/done/error 进入 connection transaction，但 completion key 字段
  仍保留旧 dict 兼容恢复。
- PostgreSQL 层面，`queue.attempt_count = done.attempt_count` 是防止完成新一代 claim 的条件。Python 层不应把缺字段转成
  0，因为这会继续给 fake/工具一个非正式 token shape。

修复：

- 新增 `_completion_attempt_count(claim)`，直接读取 `claim["attempt_count"]`。
- 缺字段、不可解析或 `<= 0` 抛原有 completion error；缺字段保留 `KeyError` cause，证明没有默认化。
- 新增 unit test 覆盖 `mark_done(...)` 和 `mark_error(...)` 缺 attempt 时在 SQL 前失败。
- architecture guard 禁止 `claim.get("attempt_count") or 0` 回流。

验证：

- RED：`uv run pytest tests/unit/test_market_tick_current_repository.py::test_market_tick_current_dirty_completion_requires_claim_attempt_field_without_default tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_market_tick_current_dirty_completion_keys_require_claim_attempt_contract -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root199 - Asset Market 三条 profile/image/refresh dirty queue completion 仍把缺 attempt 还原成 0

发现：

- `TokenProfileCurrentDirtyTargetRepository._claim_records(...)`、`TokenImageSourceDirtyTargetRepository._claim_records(...)`
  和 `AssetProfileRefreshTargetRepository._claim_records(...)` 仍通过
  `int(claim.get("attempt_count") or 0)` 生成 done/error 或 reschedule/error completion key。
- 这三条队列的 SQL completion 都会用 `payload_hash`、`lease_owner`、`attempt_count`
  匹配 claimed row，防止过期 worker 完成新一代 lease。
- 旧 Python 层先把缺失 `attempt_count` 恢复成 0，再报 invalid attempt，使 malformed
  completion token 看起来像“有 attempt 但值非法”，而不是“claim_due contract 损坏”。

根因：

- Root58/Root70/Root71/Root80 已经把 Asset Market profile/icon 链路的事务边界切到显式
  connection transaction，但 completion token 的字段契约还停留在旧 dict 兼容习惯。
- Kappa/CQRS 里这些 dirty rows 是控制面，不是事实；它们的正确性来自“claim 返回什么，complete
  就必须带回什么”的严格 token。缺 `attempt_count` 代表 worker/session/fake 没有遵守 claim
  contract，不能由 repository 私自补成 0。
- PostgreSQL 最佳实践角度，SQL 的 `queue.attempt_count = done.attempt_count` 是乐观并发保护条件；
  应用层把缺字段合成为 0 会削弱这个保护条件的可审计性，也让测试 fake 可以继续绕过真实 row shape。

修复：

- 三个 repository 都新增 `_completion_attempt_count(claim)`，直接读取 `claim["attempt_count"]`。
- 缺字段、不可解析或 `<= 0` 均在 SQL 前失败；缺字段保留 `KeyError` cause，证明没有零值默认。
- 单测分别覆盖 `token_profile_current_dirty_targets` done/error、`token_image_source_dirty_targets`
  done/error、`asset_profile_refresh_targets` reschedule/error 的缺 attempt completion。
- architecture guard 同时禁止三处 `claim.get("attempt_count") or 0` 回流，并要求 direct
  `claim["attempt_count"]`。

验证：

- RED：`uv run pytest tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py::test_profile_current_dirty_completion_requires_claim_attempt_field_without_default tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py::test_token_image_source_dirty_completion_requires_claim_attempt_field_without_default tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py::test_asset_profile_refresh_completion_requires_claim_attempt_field_without_default tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_image_refresh_dirty_completion_keys_require_claim_attempt_contract -q`
  初始 `7 failed`。
- GREEN：同一目标修复后通过，`7 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_refresh_target_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_image_refresh_dirty_completion_keys_require_claim_attempt_contract -q`
  通过，`29 passed`。
- `uv run ruff check ...` 覆盖三个 repository、三组 unit test 和架构守卫，通过。
- `uv run mypy ...` 覆盖三个 repository，通过。
- 生产残留扫描确认三个 repository 中没有 `claim.get("attempt_count") or 0` / `int(claim.get("attempt_count") or 0)`。
- SDD/static：`uv run python scripts/validate_sdd_artifacts.py`、`uv run python scripts/regen_sdd_work_index.py --check`、`git diff --check` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root200 - Discovery / Narrative / Pulse dirty completion 仍允许缺 attempt 通过兼容路径

发现：

- `DiscoveryRepository._claim_records(...)` 对 lookup claim completion 使用
  `int(claim.get("attempt_count") or 0)`，并在字段不完整时返回空 records。缺 `attempt_count`
  的 done/reschedule/terminalize 会变成静默 no-op，而不是暴露 malformed claim。
- `NarrativeAdmissionDirtyTargetRepository._claim_records(...)` 和
  `PulseTriggerDirtyTargetRepository._claim_records(...)` 也使用
  `int(claim.get("attempt_count") or 0)`。它们会报 completion requires attempt，但根因已经被
  0 默认值覆盖，不能证明 claim token shape 损坏。
- 三者都是 worker 从 `claim_due` 取得控制行后，用相同 claim token 做 done/error/reschedule/terminal
  匹配；SQL 都依赖 `queue.attempt_count = done.attempt_count` 防止过期 lease 完成新 claim。

根因：

- 前序修复把事务边界、terminal ledger、Token Radar/News/Asset Market profile completion 逐步收紧，
  但 Discovery、Narrative、Pulse 三个跨域控制面还保留了旧的“dict 兼容输入”习惯。
- Discovery 的静默过滤尤其危险：它会让 malformed completion token 看起来像“没有要完成的行”，从而
  掩盖 worker/session/fake 没有把 claimed-row `attempt_count` 带回来的事实。
- 在成熟 Kappa/CQRS 设计里，dirty queue 不是事实源，而是可重建 projection 的调度控制面。控制面
  不应替损坏 token 做修复；否则重放、审计和 lease 并发保护都会变成“SQL 看起来有条件，Python
  已经先把坏输入洗干净”的状态。

修复：

- 三个 repository completion helper 都改为直接读取 `claim["attempt_count"]`。
- 缺字段、不可解析或 `<= 0` 在 SQL 前失败；缺字段保留 `KeyError` cause。
- Discovery 同时从静默过滤改为显式校验 provider/lookup key/payload hash/lease owner。
- 新增单测覆盖 Discovery done/reschedule/terminalize、Narrative done/error/reschedule、Pulse
  done/error/reschedule 缺 attempt 的路径。
- 新增 architecture guard 禁止三处 `claim.get("attempt_count") or 0` 回流。

验证：

- RED：`uv run pytest tests/unit/test_discovery_repository.py::test_lookup_claim_completion_requires_claim_attempt_field_without_default tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_completion_requires_claim_attempt_field_without_default tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_completion_requires_claim_attempt_field_without_default tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_and_narrative_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract -q`
  初始 `11 failed`。
- GREEN：同一目标修复后通过，`11 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_discovery_repository.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_terminal_paths_require_connection_transaction_without_nullcontext tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_admission_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_and_narrative_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_target_repository_uses_shared_transaction_helper_without_manual_commit_fallback tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract -q`
  通过，`56 passed`。
- `uv run ruff check ...` 覆盖三处 repository、三组 unit test 和两个架构守卫文件，通过。
- `uv run mypy ...` 覆盖三处 repository，通过。
- 生产残留扫描确认三处 repository 中没有 `claim.get("attempt_count") or 0` / `int(claim.get("attempt_count") or 0)`。
- SDD/static：`uv run python scripts/validate_sdd_artifacts.py`、`uv run python scripts/regen_sdd_work_index.py --check`、`git diff --check` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root201 - Event Anchor / Resolution Refresh worker retry 判断仍把缺 attempt 当成 0

发现：

- `EventAnchorBackfillWorker._should_reschedule(...)` 用 `int(row.get("attempt_count") or 0)`
  判断临时 provider/rate-limit 失败是否还能 reschedule。
- 同一 worker 的 `_attempt_count(row)` 也用 `row.get("attempt_count") or 0`，随后把这个值传给
  `event_anchor_backfill_jobs` 的 done/terminal/reschedule guard。
- `ResolutionRefreshWorker._claim_retry_budget_exhausted(...)` 用
  `int(claim.get("attempt_count") or 0)` 判断 lookup claim 是否耗尽 retry budget。

根因：

- Root195-Root200 已经把多个 dirty repository completion key 收紧为 claimed-row attempt contract；
  但 worker 自身的 retry-budget / terminal guard 判断还保留了“缺字段就是第 0 次尝试”的状态机默认。
- 这比 repository SQL completion 更隐蔽：即使下游 repository 现在会校验 completion token，worker
  仍可能先用错误的 retry 判断决定走 reschedule 还是 terminalize。
- Kappa/CQRS 的控制面语义应当是：claim 行的 `attempt_count` 是调度事实的一部分；worker 不能根据
  缺失字段推导业务状态。缺 attempt 代表 claim row shape 损坏或 fake/session 不符合 contract，应当在
  状态机分支前失败。

修复：

- `EventAnchorBackfillWorker._should_reschedule(...)` 改为调用 `_attempt_count(row)`。
- `_attempt_count(row)` 改为直接读取 `row["attempt_count"]`，缺字段、不可解析或 `<= 0` 抛
  `event_anchor_backfill_claim_attempt_count_required`，缺字段保留 `KeyError` cause。
- `ResolutionRefreshWorker._claim_retry_budget_exhausted(...)` 改为调用 `_claim_attempt_count(claim)`；
  helper 直接读取 `claim["attempt_count"]`，缺字段、不可解析或 `<= 0` 抛
  `resolution_refresh_claim_attempt_count_required`。
- 新增单测覆盖 Event Anchor helper、临时 reschedule 分支、Resolution retry-budget 分支的缺 attempt
  情况。
- 新增 architecture guard 禁止两个 worker 文件恢复 `row.get("attempt_count") or 0` /
  `claim.get("attempt_count") or 0`。

验证：

- RED：`uv run pytest tests/unit/test_event_anchor_backfill_worker.py::test_event_anchor_claim_attempt_helpers_require_claim_attempt_field_without_default tests/unit/test_event_anchor_backfill_worker.py::test_temporary_reschedule_requires_claim_attempt_field_without_default tests/unit/test_resolution_refresh_worker.py::test_resolution_refresh_retry_budget_requires_claim_attempt_field_without_default tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_and_resolution_refresh_workers_require_claim_attempt_contract_without_defaults -q`
  初始 `4 failed`。
- GREEN：同一目标修复后通过，`4 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_event_anchor_backfill_worker.py tests/unit/test_resolution_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_repository_terminal_paths_require_connection_transaction_without_nullcontext tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_event_anchor_and_resolution_refresh_workers_require_claim_attempt_contract_without_defaults -q`
  通过，`32 passed`。
- `uv run ruff check ...` 覆盖两个 worker、两个 unit test 和架构守卫文件，通过。
- `uv run mypy ...` 覆盖两个 worker，通过。
- 生产残留扫描确认这两个 worker 中没有 `row.get("attempt_count") or 0` / `claim.get("attempt_count") or 0`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root202 - Pulse job / Macro Sync retry 仍把坏 claim 推断成第一次尝试

发现：

- `PulseCandidateJobService.run_job(...)` 用 `job.get("attempt_count") or 0`
  参与 agent run id 构造。缺 attempt 的 claimed job 会得到稳定但错误的 `...:0:...` 运行身份。
- `PulseDecisionRuntimeService.request_audit(...)` 用同样的默认写入 trace metadata，使审计看起来像真实第 0 次尝试。
- `PulseJobsRepository.mark_job_failed(...)`、`mark_job_cancelled_by_worker_timeout(...)`、
  `release_running_job_for_backpressure(...)`、`release_running_job_for_provider_cooldown(...)`
  用默认 attempt 做 retry/dead 分类和 CAS 条件；`mark_job_failed(...)` 还用 `max_attempts or 3`
  推断预算。
- `MacroSyncService._attempt_budget_exhausted(...)` 用 `attempt_count or 0` 和
  `max_attempts or 1` 判断 provider failure 是 retryable 还是 failed。

根因：

- Root191-Root201 已经把大量 dirty completion key 收紧为 claimed-row attempt contract，但
  “运行身份 / 审计 / retry budget / release CAS” 这些状态机入口还在用 Python 默认值恢复缺字段。
- 这类 fallback 会绕过 SQL 层的乐观并发保护：SQL 里看似有 `attempt_count` 条件，进入 SQL 前
  Python 已把 malformed claim 转成了合法但错误的 0 或默认 max。
- 成熟 Kappa/CQRS 中，`pulse_agent_jobs` 和 `macro_sync_windows` 都是控制面状态；worker
  可以重放和重试，但不能替损坏的 claim row 猜测它处在第几次尝试或预算上限。

修复：

- Pulse job service 在进入 `try` / repository 状态机之前直接读取 `job["attempt_count"]`；
  缺字段、不可解析或 `<= 0` 抛 `pulse_agent_job_claim_attempt_count_required`。
- Pulse decision runtime 的 audit metadata 使用同一正数 attempt contract，不再写入默认 0。
- Pulse jobs repository 的失败、超时取消、backpressure release、provider cooldown release 都要求
  claimed job 的正数 `attempt_count`；失败 retry/dead 分类还要求正数 `max_attempts`。
- Macro Sync retry-budget helper 要求 claimed window 的正数 `attempt_count` 和 `max_attempts`。
- 新增单测覆盖 Pulse job service、Pulse jobs repository、Pulse decision audit、Macro Sync budget
  的 malformed claim；新增 architecture guard 防止 attempt/max fallback 回流。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_claim_attempt_count_before_pipeline_state tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py::test_pulse_job_claim_mutations_require_attempt_count_from_claim_before_sql tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py::test_pulse_job_failure_requires_max_attempts_from_claim_before_sql tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_claim_attempt_count tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_attempt_budget_requires_claim_attempt_fields_without_defaults tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_pulse_job_and_macro_sync_attempt_contracts_require_claim_fields_without_defaults -q`
  初始 `9 failed`。
- GREEN：同一目标修复后通过，`9 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/test_pulse_decision_agent_client.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_pulse_job_and_macro_sync_attempt_contracts_require_claim_fields_without_defaults -q`
  通过，`81 passed`。
- `uv run ruff check ...` 覆盖四个生产文件、四组 unit test 和架构守卫文件，通过。
- `uv run mypy ...` 覆盖四个生产文件，通过。
- 生产残留扫描确认 `src/parallax/domains`、`src/parallax/app`、`src/parallax/platform`
  中没有 `attempt_count` / `max_attempts` 默认兜底 token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root203 - News item-process claim attempt / lease owner 仍可被恢复成默认值

发现：

- `NewsItemProcessWorker` 已通过 repository claim `news_items`，但 `_processing_attempts(...)`
  仍把缺失或不可用的 `processing_attempts` 转成 `0`。
- `_processing_lease_owner(...)` 仍把缺失的 `processing_lease_owner` 转成空字符串。
- 这两个值随后参与确定性 item fact 写入、retryable/terminal failure 写入、page dirty enqueue、
  item brief dirty enqueue 以及完成/失败 CAS 条件。

根因：

- 前几轮已把 dirty completion key 和 job/window retry budget 收紧为 claimed-row attempt contract，
  但 News item-process 的“处理 claim 本身”还保留了早期宽容 helper。
- 这类 fallback 看似只是 Python 层容错，实质上会改变状态机语义：一个损坏的 claimed row
  会被伪装成“第 0 次尝试 / 无 lease owner”，然后进入后续事实写、失败分支或 dirty enqueue。
- 在成熟 Kappa/CQRS 中，claim row 是控制面事实的一部分。worker 可以拒绝 malformed claim，
  但不能替数据库猜测 attempt 或 lease owner；否则 SQL 层的乐观并发和可审计失败语义会被削弱。

修复：

- `_processing_attempts(...)` 改为直接读取 `item["processing_attempts"]`，缺字段、不可解析或
  `<= 0` 抛 `news_item_process_claim_attempt_required`。
- `_processing_lease_owner(...)` 改为直接读取 `item["processing_lease_owner"]`，缺字段或空值抛
  `news_item_process_claim_lease_owner_required`。
- `NewsItemProcessWorker` 在进入 entity extraction、deterministic writes、failure writes 或 dirty
  enqueue 前先校验 claim attempt / lease owner。
- 新增单测覆盖缺 attempt、零 attempt、缺 lease owner 三类 malformed claim；新增 architecture guard
  禁止恢复 `item.get("processing_attempts", 0)`、`item.get("processing_attempts") or 0`、
  `item.get("processing_lease_owner") or ""` 等 fallback。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_requires_claim_attempt_and_lease_owner_before_processing_state tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_claim_attempt_and_lease_owner_require_claim_fields_without_defaults -q`
  初始 `4 failed`。
- GREEN：同一目标修复后通过，`4 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_agent_admission_context_uses_repository_readback_without_memory_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_claim_attempt_and_lease_owner_require_claim_fields_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_runtime_write_workers_require_session_transaction_without_conn_fallback -q`
  通过，`41 passed`。
- `uv run ruff check ...` 覆盖 worker、unit test 和 architecture guard，通过。
- `uv run mypy ...` 覆盖 `news_item_process_worker.py`，通过。
- 生产残留扫描确认 `news_item_process_worker.py` 中没有 `processing_attempts` /
  `processing_lease_owner` claim fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root204 - Dirty completion key 仍把缺失 lease owner 变成空字符串

发现：

- Root195-Root203 已把大量 dirty/job claim 的 `attempt_count` 收紧为 claimed-row contract，
  但多个 done/error/reschedule/terminal completion helper 仍用
  `claim.get("lease_owner") or ""`、`key.get("lease_owner") or ""` 或
  `row.get("lease_owner") or ""` 恢复缺失 owner。
- 影响面覆盖 Token Radar target/source dirty、News projection dirty、Market Tick Current dirty、
  Token Profile Current dirty、Token Image Source dirty、Asset Profile Refresh、Discovery lookup、
  Narrative Admission、Pulse Trigger，以及 Event Anchor Backfill 的 lease owner helper。
- Token Radar projection service 更进一步：target/source claim key 会把空 lease owner 传入
  rank-source/source projection 和后续 dirty completion，而不是在 work 前失败。

根因：

- 前几轮关注了 `attempt_count`，但 dirty queue 的 CAS key 实际上是“目标 key + payload_hash +
  lease_owner + attempt_count”的组合。只校验 attempt 不校验 owner，仍然允许坏 claimed row
  进入后续状态机。
- 空 lease owner 不只是展示缺省值；它会改变 completion SQL 的匹配条件，造成“看似有 CAS，
  但 CAS 字段来自 Python 兜底”的假安全。
- 成熟 Kappa/CQRS 中，dirty queue claim row 是控制面事实；completion token 必须继承 claim
  row 的 owner 和 attempt，worker/repository 不能替损坏行合成 owner。

修复：

- Token Radar projection 的 target/source claim key 改为 `_claim_lease_owner(claim)`，直接读取
  `claim["lease_owner"]`；缺字段、`None` 或空字符串抛
  `token_radar_dirty_claim_lease_owner_contract_required`。
- Token Radar、News、Asset Market、Discovery、Narrative、Pulse 的 dirty completion helpers 改为
  直接读取 `key["lease_owner"]` 或 `claim["lease_owner"]`，并保留原有领域错误消息。
- Event Anchor Backfill `_lease_owner(row)` 改为直接读取 `row["lease_owner"]`，缺字段保留
  `KeyError` cause。
- 新增 Token Radar projection 单测证明缺 lease owner 不会进入 rank-source/source work；新增
  architecture guard 覆盖所有生产端 dirty completion lease owner fallback token。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_target_claim_lease_owner_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_lease_owner_contract_before_work tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_lease_owner_contract_without_defaults -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/test_market_tick_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_discovery_repository.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/test_event_anchor_backfill_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_lease_owner_contract_without_defaults tests/architecture/test_token_radar_source_width_contract.py::test_projection_claim_completion_keys_require_attempt_contract_without_defaults tests/architecture/test_token_radar_source_width_contract.py::test_token_radar_dirty_repositories_require_attempt_contract_without_default_completion_keys tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_completion_keys_require_claim_attempt_contract tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract -q`
  通过，`260 passed`。
- `uv run ruff check ...` 覆盖 12 个生产文件、Root204 单测和 architecture guard，通过。
- `uv run mypy ...` 覆盖 12 个生产文件，通过。
- 生产残留扫描确认 `src/parallax/domains`、`src/parallax/app`、`src/parallax/platform`
  中没有 dirty completion `lease_owner` 空字符串 fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root205 - Dirty completion key 仍把缺失 payload_hash 变成空字符串

发现：

- Root204 收紧了 dirty completion 的 `lease_owner`，但同一 completion/CAS key 中的
  `payload_hash` 仍通过 `claim.get("payload_hash") or ""` 或
  `key.get("payload_hash") or ""` 被恢复成空字符串。
- 影响面覆盖 Token Radar target/source dirty、News projection dirty、Market Tick Current dirty、
  Token Profile Current dirty、Token Image Source dirty、Asset Profile Refresh、Discovery lookup、
  Narrative Admission 和 Pulse Trigger。
- Token Radar projection service 会在 target/source claim 缺 `payload_hash` 时继续进入
  rank-source/source projection，而不是在 work 前失败。

根因：

- Dirty completion 的 CAS 语义不是单字段；它依赖目标 key、`payload_hash`、`lease_owner` 和
  `attempt_count` 一起证明“我完成的是刚刚 claim 到的那一版 work”。
- 前几轮已经消除了 attempt 和 owner 的默认恢复，但 payload 版本仍可被 Python 合成为空字符串，
  使 completion SQL 看起来有 payload 条件，实质上条件来自兼容兜底。
- 成熟 Kappa/CQRS 中，payload hash 是 dirty work 内容签名。缺失 hash 代表 control-plane
  row 损坏，应失败并暴露，而不是退化成空 payload 版本。

修复：

- Token Radar projection 的 target/source claim key 改为 `_claim_payload_hash(claim)`，直接读取
  `claim["payload_hash"]`；缺字段、`None` 或空字符串抛
  `token_radar_dirty_claim_payload_hash_contract_required`。
- Token Radar、News、Asset Market、Discovery、Narrative、Pulse 的 dirty completion helpers 改为
  直接读取 `key["payload_hash"]` 或 `claim["payload_hash"]`，并保留原有 full-key 优先错误语义。
- 新增 Token Radar projection 单测证明缺 payload hash 不会进入 rank-source/source work；新增
  architecture guard 覆盖生产端 dirty completion payload fallback token。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_target_claim_payload_hash_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_payload_hash_contract_before_work tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/test_market_tick_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_discovery_repository.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_lease_owner_contract_without_defaults tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults tests/architecture/test_token_radar_source_width_contract.py::test_projection_claim_completion_keys_require_attempt_contract_without_defaults tests/architecture/test_token_radar_source_width_contract.py::test_token_radar_dirty_repositories_require_attempt_contract_without_default_completion_keys tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_completion_keys_require_claim_attempt_contract tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract -q`
  通过，`244 passed`。
- `uv run ruff check ...` 覆盖 11 个生产文件、Root205 单测和 architecture guard，通过。
- `uv run mypy ...` 覆盖 11 个生产文件，通过。
- 生产残留扫描确认 `src/parallax/domains`、`src/parallax/app`、`src/parallax/platform`
  中没有 dirty completion `payload_hash` 空字符串 fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root206 - Token Image Source dirty completion 仍从 source_url 重建 source_url_hash

发现：

- Root205 收紧了 `payload_hash` 后，Token Image Source dirty queue 的 completion target key
  仍有一个更隐蔽的兼容路径：缺 `source_url_hash` 时，通过
  `claim.get("source_url") or ""` 重新计算 `_source_url_hash(...)`。
- `mark_done(...)` 和 `mark_error(...)` 因此可以在 claim row 缺少 target key 的情况下继续生成
  completion SQL 参数，而不是在 SQL 前暴露 malformed claim。
- 这个问题只存在于 completion 端；enqueue 和 existing lookup 从 source URL 计算 hash 是合法输入规范化。

根因：

- Token Image Source dirty queue 的稳定身份是 `(source_url_hash, target_type, target_id)`。
  Completion CAS 需要证明“我完成的是刚 claim 到的同一条 dirty row”，所以 target key 必须来自
  claimed row 本身。
- 从 `source_url` 回算 hash 看似等价，实质上把事实表上的 target identity 变成了可选衍生字段：
  一旦 claim row 损坏、字段缺失或未来 URL 规范化规则变化，completion 端可能用本地推导值去匹配
  PostgreSQL 队列状态。
- 成熟 Kappa/CQRS 中，claim 返回的是控制面事实快照；completion 不能修复或猜测这个快照，
  只能用它做 CAS 或失败。

修复：

- `TokenImageSourceDirtyTargetRepository._claim_records(...)` 改为调用
  `_completion_source_url_hash(claim)`，并直接读取 `claim["source_url_hash"]`。
- 缺字段、`None` 或空白 `source_url_hash` 会在 SQL 前抛
  `token image source dirty target completion requires full target key from claim_due`。
- 新增单测覆盖 done/error 两条路径，证明缺 `source_url_hash` 时没有 SQL；新增 architecture guard 禁止
  `claim.get("source_url_hash") or _source_url_hash` 和 `claim.get("source_url") or ""` 回归。

验证：

- RED：`uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py::test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback -q`
  初始 `3 failed`。
- GREEN：同一目标修复后通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_lease_owner_contract_without_defaults -q`
  通过，`12 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit test 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`
  通过。
- 生产残留扫描确认 Token Image Source dirty repository 中没有 completion `source_url_hash`
  URL 回算 fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root207 - Pulse exit suppression 仍把缺失 payload_hash 写成空 trigger_signature

发现：

- Root205/Root206 已经收紧 dirty completion 的 payload 和 target key，但 Pulse Candidate 的
  token-radar-exited suppression 分支仍用 `str(claim.get("payload_hash") or "")` 构造
  `pulse_candidate_edge_state.trigger_signature`。
- 当 exit dirty claim 缺 `payload_hash` 且当前 Radar row 已缺失时，worker 会先写 admission/edge
  状态，把 `trigger_signature` 记成空字符串，然后才进入 dirty completion。
- 这不是 SQL completion 条件本身，而是同一个 claim payload contract 在审计/read-model
  分支被绕松。

根因：

- `payload_hash` 在 dirty trigger 中不是展示字段，它是触发内容签名。Pulse exit suppression
  把它写入 edge state，是为了让之后的 admission/audit 判断知道这次 “not_active/exited”
  是由哪一版 dirty trigger 触发。
- 空字符串 trigger signature 会制造一个看似合法但不可追溯的 edge state：队列 CAS 也许会失败，
  但 admission side effect 已经带着兼容默认值进入状态机。
- 成熟 Kappa/CQRS 要求 claim row 是控制面事实快照；读模型/审计写入不能为损坏 claim
  发明签名。

修复：

- `PulseCandidateWorker` 新增 `_claim_payload_hash(claim)`，直接读取 `claim["payload_hash"]`。
- 缺字段、`None` 或空白 payload 会抛 `pulse_trigger_dirty_claim_payload_hash_required`，
  在 `claim_pulse_admission(...)` 前失败。
- 新增单测证明缺 payload 的 exit trigger 不写 admission、不 mark done，而进入 dirty-trigger
  failure 处理；新增 architecture guard 禁止 `str(claim.get("payload_hash") or "")` 回归。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_exit_trigger_requires_claim_payload_hash_before_suppression_admission tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_pulse_candidate_exit_suppression_requires_claim_payload_hash_without_default -q`
  初始在刷新 focused test fixture settings 后 `2 failed`。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_pulse_candidate_exit_suppression_requires_claim_payload_hash_without_default tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract -q`
  通过，`10 passed`。
- `uv run ruff check ...` 覆盖 touched source、Pulse dirty trigger 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py` 通过。
- 生产残留扫描确认 `pulse_candidate_worker.py` 中没有 `payload_hash` 空字符串 fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root208 - Token Radar 下游 fan-out 用空 payload_hash 判断“未变化”

发现：

- Token Radar current row 发布后，会向 Pulse Trigger、Narrative Admission、Token Profile Current
  三条下游 dirty 队列 fan-out。
- 这三条 fan-out 的 skip 判断仍使用
  `str(previous.get("payload_hash") or "") == str(row.get("payload_hash") or "")`。
  如果 previous/current row 都缺 `payload_hash`，系统会把两个损坏 row 当成相同签名并静默跳过 dirty enqueue。
- `_row_from_target_feature(...)` 从 target feature hydrate current row 时也把缺 `payload_hash`
  恢复成空字符串，给后续 read-model/fan-out 留下同样的空签名。

根因：

- `payload_hash` 是 Token Radar current row 的内容签名，也是 downstream dirty fan-out 的变化判断依据。
  缺失 hash 不是“没有变化”，而是 current read model 或 feature cache 的契约损坏。
- 用空字符串比较把两类状态混在一起：真正 unchanged row 与 malformed row。成熟 CQRS 投影必须让
  malformed read-model state 显性失败，否则 downstream projection 会漏掉 Pulse/Narrative/Profile 的重算。
- 这类 bug 特别隐蔽，因为它不会直接写错 SQL，而是少写 dirty target，表现为读模型长期 stale。

修复：

- 新增 `_rank_change_payload_hash(row)`，直接读取 `row["payload_hash"]`；缺字段、`None` 或空白值抛
  `token_radar_rank_change_payload_hash_required`。
- Pulse、Narrative Admission、Token Profile Current fan-out 的 previous/current 比较统一使用
  `_rank_change_payload_hash(previous)` 和 `_rank_change_payload_hash(row)`。
- `_row_from_target_feature(...)` hydrate current row 时也要求 target feature row 的 payload hash，
  不再写空 hash。
- 新增单测覆盖三条 fan-out 缺 payload 时不能 silent skip；新增 architecture guard 禁止
  previous/current payload 空字符串比较回归。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_projection.py::test_projection_downstream_rank_change_requires_payload_hash_before_skip tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_downstream_rank_change_payload_hash_requires_row_contract_without_defaults -q`
  初始 `4 failed`。
- GREEN：同一目标修复后通过，`4 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_token_radar_projection.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_radar_downstream_rank_change_payload_hash_requires_row_contract_without_defaults tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults tests/architecture/test_token_radar_source_width_contract.py::test_token_radar_downstream_dirty_target_repositories_are_required_without_optional_probes -q`
  通过，`88 passed`。
- `uv run ruff check ...` 覆盖 touched source、Token Radar projection 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/token_intel/services/token_radar_projection.py` 通过。
- 生产残留扫描确认 `token_radar_projection.py` 中没有 previous/current `payload_hash`
  空字符串比较 fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root209 - Discovery terminal ledger 把缺失 source payload_hash 记录成空签名

发现：

- `DiscoveryRepository.terminalize_lookup_claims(...)` 已经在 claim completion key 上要求
  `payload_hash`、`lease_owner` 和 `attempt_count`，但删除 claimed
  `token_discovery_dirty_lookup_keys` 后写 terminal ledger 时仍使用
  `str(row.get("payload_hash") or "")`。
- 如果被删除的 queue source row 缺 `payload_hash`，`worker_queue_terminal_events`
  会收到空 payload 签名，而不是暴露 terminal evidence 的 source snapshot 损坏。
- 这不会表现为 SQL 错误；它会污染 operator 看到的 terminal evidence，使 retry/archive/quarantine
  面对的是“合法 terminal 事件”，但事件签名已经丢失。

根因：

- Completion CAS key 和 terminal ledger source row 是两层契约：前者证明“删哪一条 claim”，后者证明“为什么这条
  source row 被 terminalize”。
- 前序 Root205 收紧了 completion key，但 terminal evidence 写入点还保留了独立的空字符串兼容默认。
  这说明治理不能只扫 claim helper；所有进入 read/ops ledger 的 payload signature 都必须保持 required contract。
- 在成熟 Kappa/CQRS 中，terminal ledger 是控制面事实的审计投影。source row 缺 payload hash
  应该让 terminalization 失败并保留可调查状态，而不是写出一个空签名事件。

修复：

- 新增 `_terminal_source_payload_hash(row)`，直接读取 `row["payload_hash"]`。
- 缺字段、`None` 或空白值抛
  `token discovery lookup terminalization requires source payload_hash`。
- `terminalize_lookup_claims(...)` 写 `terminalize_source_row(...)` 前必须通过该 helper；
  malformed source row 在 `worker_queue_terminal_events` SQL 前失败。
- 新增单元测试证明缺 source payload hash 不写 terminal ledger；新增 architecture guard 禁止
  `payload_hash=str(row.get("payload_hash") or "")` 回归。

验证：

- RED：`uv run pytest tests/unit/test_discovery_repository.py::test_terminalize_lookup_claims_requires_deleted_source_payload_hash_before_ledger_write tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_terminalization_requires_deleted_source_payload_hash_without_default -q`
  初始 `2 failed`。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_discovery_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_and_narrative_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_terminalization_requires_deleted_source_payload_hash_without_default -q`
  通过，`22 passed`。
- `uv run ruff check ...` 覆盖 touched source、Discovery 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/asset_market/repositories/discovery_repository.py` 通过。
- 生产残留扫描确认 `discovery_repository.py` 中没有 terminalization
  `payload_hash=str(row.get("payload_hash") or "")` fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root210 - Macro current-series 变更检测把缺失 payload_hash 当成空签名

发现：

- `MacroIntelRepository.refresh_observation_series_rows_for_concepts(...)` 会把 selected
  observation rows 与 existing `macro_observation_series_rows` current rows 做 per-concept
  payload hash 比较，决定是否 delete/insert current rows。
- selected rows 通过 `macro_series_current_row_payload_hash(row)` 计算稳定签名，但 existing rows
  仍用 `str(row.get("payload_hash") or "")` 读取。
- 如果 existing current row 缺 `payload_hash`，系统不会暴露 read-model state 损坏，而是把它放进空签名比较。
  这类错误可能触发不必要重写，也可能掩盖 schema/迁移不完整导致的 current row contract 破坏。

根因：

- `macro_observation_series_rows.payload_hash` 不是缓存优化字段；它是 current read model 的内容签名，
  也是 unchanged projection 写零 serving rows 的依据。
- 成熟 CQRS 投影的比较逻辑必须区分“内容真的变化”和“existing read model malformed”。把缺 hash 压成
  空字符串，会把后者伪装成普通 diff 输入，降低了对坏 read model 的可观测性。
- 这和 Token Radar downstream fan-out 的根因相同：payload signature 一旦进入 read-model comparison，
  就必须是 required contract，而不是 Python 层的兼容默认。

修复：

- `_series_payload_hashes_by_concept(...)` 对 existing rows 改为调用 `_existing_series_payload_hash(row)`。
- `_existing_series_payload_hash(row)` 直接读取 `row["payload_hash"]`；缺字段、`None` 或空白值抛
  `macro_series_current_existing_payload_hash_required`。
- 新增单测证明 malformed existing current row 在 delete/insert 前失败；新增 architecture guard 禁止
  `str(row.get("payload_hash") or "")` 回归。

验证：

- RED：`uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py::test_partition_refresh_requires_existing_current_payload_hash_before_change_detection tests/architecture/test_macro_kappa_contract.py::test_macro_series_existing_payload_hash_is_required_without_empty_fallback -q`
  初始 `2 failed`。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/unit/domains/macro_intel/test_macro_generation_swap.py tests/architecture/test_macro_kappa_contract.py -q`
  通过，`19 passed`。
- `uv run ruff check ...` 覆盖 touched source、Macro partition refresh 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` 通过。
- 生产残留扫描确认 `macro_intel_repository.py` 中没有 Macro current-series
  `str(row.get("payload_hash") or "")` fallback token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root211 - Stocks Radar public read query 聚合无界 source_event_ids

发现：

- `/api/stocks-radar` 已经移除了 request-time provider IO，但
  `StocksRadarQuery.stock_rows(...)` 仍在 public read query 中为每个股票
  target 聚合窗口内全部 `event_id` 到 `source_event_ids`。
- mentions、unique authors、watched mentions、latest evidence 需要完整窗口统计；
  但 public provenance 不需要把窗口内所有 source event id 都返回给前端。
- 热门股票在 1h/4h 窗口内可能产生很大的 per-group array，增加 PostgreSQL
  sort/memory pressure，也扩大 HTTP 响应负载。

根因：

- 前序治理优先删除了 provider IO，但保留了“把所有 source ids 都带给前端”的兼容心态。
- 在成熟 Kappa/CQRS 中，完整事实应该保留在 PostgreSQL material facts 和可 drilldown
  查询里；公共读模型响应只应该携带有界、可解释的 provenance。
- 这个问题不是业务统计错，而是读模型 payload 边界错：把事实表的完整事件集合泄漏成了
  API row 的默认 shape。

修复：

- 新增 `STOCKS_RADAR_SOURCE_EVENT_LIMIT = 25`。
- 新增 `ranked_mentions AS MATERIALIZED`，按 target 内
  `received_at_ms DESC, event_id DESC` 计算 `event_rank`。
- `source_event_ids` 改为
  `ARRAY_AGG(event_id ORDER BY event_rank) FILTER (WHERE event_rank <= %s)`；
  mentions、unique authors、watched mentions、latest evidence 仍按完整窗口聚合。
- 新增单测和 architecture guard，禁止旧的无界
  `ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids`
  回归。

验证：

- RED：`uv run pytest tests/unit/test_stocks_radar_query.py::test_stock_rows_bounds_source_event_id_aggregation_per_symbol tests/architecture/test_api_read_paths_provider_free.py::test_stocks_radar_source_event_ids_are_bounded_in_sql_read_path -q`
  初始 `2 failed`。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_stocks_radar_query.py tests/unit/test_stocks_radar_service.py tests/architecture/test_api_read_paths_provider_free.py::test_stocks_radar_api_is_provider_free tests/architecture/test_api_read_paths_provider_free.py::test_stocks_radar_source_event_ids_are_bounded_in_sql_read_path tests/architecture/test_api_read_paths_provider_free.py::test_stocks_radar_docs_do_not_describe_request_time_quote_provider -q`
  通过，`7 passed`。
- `uv run ruff check ...` 覆盖 touched source、Stocks Radar 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/token_intel/queries/stocks_radar_query.py` 通过。
- 生产残留扫描确认 `stocks_radar_query.py` 中没有旧的无界
  `ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids`
  token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root212 - News agent admission duplicate lookup 仍展开 provider_article_keys_json

发现：

- News 已经有规范化 `news_item_observation_edges(provider_article_key)`，并且迁移里为
  非空 `provider_article_key` 建了 partial index。
- 但 agent admission duplicate lookup 仍有两处使用 `jsonb_array_elements_text(...)`
  展开 `provider_article_keys_json`：一个在 `_agent_exact_duplicate_context(...)`，
  一个在 `load_agent_admission_contexts(...)` 的 duplicate candidate 子查询。
- 这条路径不是公共 API read path，但它是 News item-process/brief admission 的 worker
  readback 热路径；JSONB summary 越大，duplicate 判断越难稳定走窄索引。

根因：

- `provider_article_keys_json` 本来是 compact evidence payload，便于 prompt、页面和审计读取；
  它不是 provider-article identity 的查询索引。
- 前序 canonical/dedup hard cut 已经建立了 observation edge 表，但部分 readback SQL
  仍保留“从 JSONB payload 里反推 identity edge”的兼容路径。
- 成熟 CQRS 里，identity/edge lookup 应走规范化事实边；JSONB payload 只保留为可重建投影的展示/审计字段。

修复：

- `_agent_exact_duplicate_context(...)` 新增 `item_provider_article_keys AS MATERIALIZED`，
  直接从 `news_item_observation_edges` 读取 target item 的 provider article key，再与 candidate edges join。
- `load_agent_admission_contexts(...)` 的 duplicate candidate provider-article 分支改为
  `target_provider_edges` 与 `duplicate_edges` 的 self-join，并保持 enabled source 过滤。
- 新增单测和 architecture guard，要求 `target_provider_edges` / edge join 存在，并禁止
  agent-admission duplicate lookup 函数中出现 `jsonb_array_elements_text`。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_context_provider_duplicate_lookup_uses_observation_edges tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_provider_article_duplicate_lookup_uses_edges_not_jsonb_expansion -q`
  初始 `2 failed`。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_fails_when_agent_admission_context_missing tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_market_scope_shape_before_persistence tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_story_identity_shape_before_persistence tests/architecture/test_news_intel_kiss_simplification.py -q`
  通过，`64 passed`。
- `uv run ruff check ...` 覆盖 touched source、News repository 单测和 architecture guard，通过。
- `uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py` 通过。
- 生产残留扫描确认 `news_repository.py` 中没有 `jsonb_array_elements_text`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root213 - Signal Pulse public q search 仍靠未索引 `%...%` 过滤

发现：

- `PulseReadRepository.list_candidates(...)` 和 `pulse_summary(...)` 对 public `q`
  使用三列 substring filter：
  `candidate.symbol ILIKE %s OR candidate.subject_key ILIKE %s OR candidate.target_id ILIKE %s`。
- `pulse_summary(...)` 还用同一个 `q` 过滤候选汇总、abstain reason 汇总和 dead job count；
  这些都是 count/group 形状，不能靠列表页的 `LIMIT` 保护。
- 旧迁移只有 B-tree `idx_pulse_candidates_latest`、`idx_pulse_candidates_target`、
  `idx_pulse_candidates_subject` 和 `idx_pulse_agent_jobs_scope_status`；它们不适合
  `ILIKE '%term%'`。
- 另外，空白 `q` 会被 `q.strip()` 变成空字符串后拼成 `ILIKE '%%'`，等价于主动要求
  PostgreSQL 匹配整个窗口。

根因：

- Pulse 已经把决策结果物化成 `pulse_candidates`，但 public 搜索仍停留在“对物化表临时扫字符串”
  的读端思维，没有给这个 public contract 配套索引。
- 成熟 CQRS 的读模型不仅要“数据已经物化”，还要让常用读取维度成为可索引的读取合同。
  否则读模型会退化成一张越来越大的临时筛选表。
- 空白搜索进入 `ILIKE '%%'` 是输入归一缺口：它不会改变业务结果，却会把一个普通页面刷新变成
  明确的全匹配模式过滤。

修复：

- 新增 `20260612_0179_pulse_public_search_trgm_indexes.py`，创建 `pg_trgm` 并为
  `pulse_candidates.symbol`、`pulse_candidates.subject_key`、`pulse_candidates.target_id`、
  `pulse_agent_jobs.subject_key`、`pulse_agent_jobs.target_id` 添加并发 GIN trigram 索引。
- `PulseReadRepository` 新增 `_normalize_public_search_q(...)`，空白 `q` 视为无搜索；
  非空搜索统一 strip 后再生成 `%term%`。
- Pulse domain architecture 明确 public `q` 搜索必须由 trigram GIN 支撑，禁止回到
  `ILIKE '%%'` 或 JSONB event-array expansion。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py::test_pulse_read_repository_treats_blank_q_as_no_search_filter tests/unit/test_postgres_schema.py::test_signal_pulse_public_search_migration_adds_trigram_indexes -q`
  初始 `2 failed`。
- GREEN：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py::test_pulse_read_repository_treats_blank_q_as_no_search_filter tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py::test_pulse_read_repository_strips_q_before_ilike_filter tests/unit/test_postgres_schema.py::test_signal_pulse_public_search_migration_adds_trigram_indexes -q`
  通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py tests/unit/test_postgres_schema.py::test_signal_pulse_agent_hard_cut_migration_defines_pulse_tables tests/unit/test_postgres_schema.py::test_signal_pulse_public_search_migration_adds_trigram_indexes -q`
  通过，`5 passed`。
- `uv run pytest tests/architecture/test_pulse_no_compat.py::test_pulse_read_handle_filter_does_not_expand_event_id_jsonb -q`
  通过，确认 public search 没有回到 JSONB event-id expansion。
- `uv run ruff check ...` 覆盖 touched source、migration 和 tests，通过。
- `uv run mypy src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py` 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root214 - Ops diagnostics provider health item 仍走反射兼容

发现：

- `ops_diagnostics._asset_market_provider_health(...)` 已经要求
  `runtime.providers.asset_market.provider_health` 这个根字段存在，但对每个 health item
  仍调用泛化 `_object_payload(...)`。
- `_object_payload(...)` 接受 mapping、dataclass，并最终用 `vars(value)` 展开任意对象。
  这意味着 `SimpleNamespace(provider="gmgn", configured=True, capabilities=())`
  这类非正式 provider-health 对象会被诊断层接受。
- 失败表现不是 contract error，而是可能被渲染成 `provider=unknown`、
  `configured=false` 或其它“看起来只是 provider 没配好”的行。

根因：

- 前序 hard cut 已经把运行时 provider root 从 optional probe 收紧为正式 contract，
  但 item 级别仍保留了“对象有什么字段就展开什么字段”的兼容层。
- 对成熟 Kappa/CQRS 系统来说，ops diagnostics 是发现链路断裂的观测面；
  它可以汇总健康状态，但不应该把 malformed runtime object 转译成正常健康行。
- 这类反射兼容会把 wiring 错误从“系统契约断裂”降级成“业务 provider 未配置”，
  导致排查方向偏到数据源/配置，而不是 composition root。

修复：

- 删除 provider-health item 的泛化 `_object_payload(...)` 路径。
- 新增 `_provider_health_payload(...)`，只接受正式 `ProviderHealth` 或显式 mapping；
  mapping 必须包含 `provider`、`capabilities`、`configured`。
- 架构测试禁止 `ops_diagnostics.py` 重新引入 `_object_payload`、`vars()`、
  `__dict__` 或 dataclass-reflection 兼容路径。

验证：

- RED：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_rejects_reflective_asset_market_provider_health_items -q`
  初始 `1 failed`。
- GREEN：`uv run pytest tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_rejects_reflective_asset_market_provider_health_items tests/unit/test_ops_diagnostics.py::test_ops_diagnostics_requires_asset_market_provider_health_contract tests/architecture/test_worker_runtime_contracts.py::test_ops_diagnostics_asset_market_provider_health_items_use_explicit_contract_without_reflection -q`
  通过，`3 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/app/runtime/ops_diagnostics.py` 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root215 - Pulse evidence gate 仍接受任意对象反射输入

发现：

- `EvidenceCompletenessGate.evaluate(...)` 的类型签名是
  `PulseEvidencePacket | Any`，但实际通过 `getattr(packet, ...)`
  读取 `social_evidence`、`market_evidence`、`identity_evidence`、
  `allowed_evidence_refs` 和 `data_gaps`。
- `_model_mapping(...)` 会接受 dict、任意 `model_dump(...)` 对象，
  以及带 `__dict__` 的对象，并用 `vars(value)` 展开。
- 单元测试自身使用 `SimpleNamespace` 构造 packet，这把测试 fake 的形状固定成了
  生产 runtime contract，导致 malformed sealed-packet wiring 会变成普通
  insufficient/partial/complete gate 结果。

根因：

- 前序治理已经把 `PulseEvidenceBuilder` 收紧为正式 `PulseCandidateContext`
  和 `PulseEvidencePacket`，但下游 gate 仍保留了旧测试夹具驱动的“对象形状兼容”。
- Evidence completeness gate 是 Pulse LLM 前的业务决策门。它应该判断正式证据包
  是否足够，而不是帮 composition/root/test fake 把任意对象翻译成证据包。
- 成熟 Kappa/CQRS 里，sealed evidence packet 是 worker 与 agent plane 之间的
  replay contract；如果这里接受任意对象反射，错误会从“证据包边界断裂”
  被降级成“证据不足/可展示状态”，排查方向会被带偏。

修复：

- `EvidenceCompletenessGate.evaluate(...)` 只接受正式 `PulseEvidencePacket`，
  并对非正式对象抛出 `pulse_evidence_packet_contract_required`。
- gate 内部直接读取 Pydantic 字段，并只对正式 packet 子模型调用
  `model_dump(mode="json")`；删除 `_model_items(...)`、`_model_mapping(...)`、
  `getattr(packet, ...)`、任意 `model_dump` 探测、`__dict__` 和 `vars(...)` 路径。
- 单元测试 helper 改为构造真实 `PulseEvidencePacket`，并新增拒绝
  `SimpleNamespace` packet 的 RED/GREEN 测试。
- Pulse domain architecture、worker flow 和 worker inventory 明确 evidence gate
  的输入边界是 sealed packet，不是 dict/object reflection。

验证：

- RED：`uv run pytest tests/unit/test_pulse_evidence_completeness_gate.py::test_evidence_gate_requires_formal_pulse_evidence_packet_without_reflection tests/architecture/test_pulse_no_compat.py::test_pulse_evidence_completeness_gate_requires_formal_packet_without_reflection -q`
  初始 `2 failed`，因为 `SimpleNamespace` packet 被接受，且架构 guard 找到反射兼容。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_pulse_evidence_completeness_gate.py tests/unit/test_pulse_evidence_packet_builder.py::test_builds_cex_snapshot_packet_with_derivatives_and_level_refs tests/unit/test_pulse_evidence_packet_builder.py::test_stale_digest_prose_without_current_sources_blocks_non_abstain_packet tests/unit/test_pulse_evidence_packet_builder.py::test_current_source_refs_remain_primary_when_digest_is_stale_context tests/architecture/test_pulse_no_compat.py::test_pulse_evidence_completeness_gate_requires_formal_packet_without_reflection -q`
  通过，`11 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/evidence_completeness_gate.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root216 - Pulse claim verifier 仍用测试对象形状验证 LLM 输出引用

发现：

- `ClaimEvidenceVerifier.verify(...)` 的输入签名仍是
  `PulseEvidencePacket | Any` 和 `FinalDecision | Any`。
- verifier 通过 `getattr(final_decision, ...)` 读取 recommendation、supporting refs、
  risk refs、data gap refs 和 event ids；同时 `_allowed_ref_ids(...)` 用
  `getattr(packet, "allowed_evidence_refs", ())` 并兼容 dict ref。
- 单元测试使用 `SimpleNamespace` packet/decision 夹具，使“任意对象只要长得像”
  成为 claim validation 的事实 contract。

根因：

- Root215 已经把 evidence completeness gate 收紧到 sealed `PulseEvidencePacket`，
  但下游 claim verifier 仍把 agent 输出验证当成 duck-typing 工具函数。
- Claim verifier 是 LLM 输出进入 write gate 之前的安全门。它应该在严格
  `FinalDecision` schema 之后判断引用是否都来自 sealed packet，而不是替
  未验证对象解释字段。
- 这类兼容层会把 agent-output schema 断裂、测试 fake 漂移或 packet 边界断裂
  混成 unknown-ref/unsupported-claim 业务结果，降低根因定位精度。

修复：

- `ClaimEvidenceVerifier.verify(...)` 和 `verify_claim_evidence(...)` 只接受
  正式 `PulseEvidencePacket` 与 `FinalDecision`。
- 非正式 packet 抛出 `pulse_claim_verifier_packet_contract_required`；
  非正式 decision 抛出 `pulse_claim_verifier_final_decision_contract_required`。
- 允许引用集合直接从 `packet.allowed_evidence_refs` 的 Pydantic ref 字段读取；
  final refs 直接从 `FinalDecision` 字段读取；删除 `_sequence(...)`、packet
  `getattr(...)` 和 dict-ref 兼容。
- verifier 单测改成正式 packet/decision 夹具；event-id-only 非 abstain 输出
  改由 `FinalDecision` schema 在 verifier 前失败。

验证：

- RED：`uv run pytest tests/unit/test_pulse_claim_evidence_verifier.py::test_verifier_requires_formal_packet_and_final_decision_without_reflection tests/architecture/test_pulse_no_compat.py::test_pulse_claim_evidence_verifier_requires_formal_models_without_reflection -q`
  初始 `2 failed`，因为 loose packet 被接受，且架构 guard 找不到 formal
  model 检查。
- GREEN：同一目标修复后通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_pulse_claim_evidence_verifier.py tests/unit/domains/pulse_lab/test_agent_output_normalization.py tests/architecture/test_pulse_no_compat.py::test_pulse_claim_evidence_verifier_requires_formal_models_without_reflection -q`
  通过，`15 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit、normalization 单测和
  architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/claim_evidence_verifier.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root217 - Pulse decision stage builder 仍接受 dict packet/gate

发现：

- `PulseDecisionRuntimeService.pulse_decision_stage_spec(...)` 的协议声明是
  `PulseEvidencePacket` 与 `EvidenceCompletenessGateResult`，但实现通过
  `_model_payload(...)` 接受 dict 或任意 `model_dump(...)` 对象。
- 单元测试直接把 dict packet 和 `{"status": "complete"}` gate 传入 stage builder。
- `LiteLLMPulseDecisionClient` 从 JSON context 中取 `evidence_packet` 后返回 dict，
  并把 `completeness` dict 直接传给 domain runtime。异常 abstain helper 还保留
  `PulseEvidencePacket | dict` packet 兼容。

根因：

- Root215/Root216 已经把 gate 和 claim verifier 收紧成正式模型，但 agent stage
  prompt 构造仍保留“JSON/dict 可以直接进入 domain runtime”的旧测试便利路径。
- JSON context 是 integration adapter 边界，不是 domain runtime 的内部合同。
  成熟 agent execution plane 应该在 adapter 入口重新校验成正式领域模型，再交给
  prompt/stage builder。
- 如果 stage builder 接受 dict packet/gate，malformed packet 或 gate payload 会在
  prompt 输入阶段被降级为空 payload、缺少 allowed refs 或缺少 gate status，而不是
  作为 runtime contract 断裂暴露。

修复：

- `pulse_decision_stage_spec(...)` 显式要求 `PulseEvidencePacket` 与
  `EvidenceCompletenessGateResult`；非正式 packet/gate 分别抛出
  `pulse_decision_stage_packet_contract_required` 和
  `pulse_decision_stage_gate_contract_required`。
- 删除 `_model_payload(...)` 和任意 `model_dump` 探测；packet prompt payload 只从
  正式 `PulseEvidencePacket.model_dump(...)` 导出，并继续排除 `summary_json` 与
  `admission_context`。
- `LiteLLMPulseDecisionClient` 在进入 stage builder 前用
  `PulseEvidencePacket.model_validate(...)` 校验 context JSON，并把 full completeness
  JSON 转成 `EvidenceCompletenessGateResult`。
- 异常 abstain helper 只接受正式 packet，gate ref 直接从
  `packet.allowed_evidence_refs` 读取。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_stage_spec_requires_formal_packet_and_gate_without_dict_compatibility tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_decision_stage_spec_requires_formal_packet_and_gate_without_payload_fallback -q`
  初始 `2 failed`，因为 dict packet 被接受且 stage builder 缺少 formal model 检查。
- GREEN：同一目标修复后通过，并连同 stage input 测试一起通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_decision_stage_spec_requires_formal_packet_and_gate_without_payload_fallback -q`
  通过，`20 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py src/parallax/integrations/model_execution/pulse_decision_agent_client.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root218 - News deterministic fact writes 仍接受任意对象反射

发现：

- `NewsRepository.replace_item_entities(...)`、`replace_token_mentions(...)`、
  `replace_fact_candidates(...)` 的写入 helper 共用 `_object_payload(...)`。
- 该 helper 会接受 Mapping、任意 `model_dump(...)` 对象、`vars(...)` /
  `__dict__` 对象，以及 `__slots__` 对象。
- `NewsItemProcessWorker._object_payload(...)` 也保留 `model_dump` 与
  `__dict__` 兜底，使 `SimpleNamespace` 这类测试对象能进入 deterministic
  classification/story 输入。

根因：

- News item process 已经是 facts -> current state -> projection 的确定性 worker，
  entity、token mention、fact candidate 是 PostgreSQL material facts，不是
  public read row，也不是 provider/raw adapter payload。
- 成熟 Kappa/CQRS 写侧边界应该只接受正式领域结果：
  `NewsEntity`、`NewsTokenMention`、`NewsFactCandidate`。如果写入层还替任意对象
  解释字段，测试 fixture 漂移或旧对象形状会被降级成部分 INSERT、KeyError 或
  静默 payload 差异，而不是“worker/domain contract 断裂”。
- 这类反射兼容也削弱 PostgreSQL 最佳实践：表列写入应该来自清晰字段映射，而不是
  从对象形状推断 SQL 参数。

修复：

- `NewsRepository` deterministic fact writes 只接受正式
  `NewsEntity`、`NewsTokenMention`、`NewsFactCandidate`。
- `_entity_payload(...)`、`_mention_payload(...)`、`_fact_payload(...)` 直接读取正式
  dataclass 字段并显式构造 SQL 参数；非正式对象分别抛出
  `unsupported news entity payload shape`、
  `unsupported news token mention payload shape`、
  `unsupported news fact candidate payload shape`。
- 删除 repository 旧 `_object_payload(...)`，不保留 `model_dump`、`vars`、
  `__dict__`、`__slots__` fallback。
- `NewsItemProcessWorker._object_payload(...)` 仅允许 Mapping 与正式 dataclass；
  未知对象抛出 `unsupported news item process payload shape`。
- News domain architecture、worker flow、worker inventory 明确 deterministic fact
  writes 不接受 object reflection compatibility。

验证：

- RED：`uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_current_fact_writes_reject_reflective_payload_objects_before_insert tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_payload_helper_rejects_reflective_objects tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_fact_payload_helpers_have_no_reflective_object_fallbacks -q`
  初始 `3 failed`，因为反射 payload 被接受，且架构 guard 找不到 formal fact object
  检查。
- GREEN：同一目标修复后通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_extracts_mentions_candidates_and_wakes tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_market_scope_shape_before_persistence tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_rejects_unsupported_story_identity_shape_before_persistence tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_payload_helper_rejects_reflective_objects tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_fact_payload_helpers_have_no_reflective_object_fallbacks -q`
  通过，`26 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root219 - Pulse post-decision gates 仍把 malformed gate 输入恢复成默认状态

发现：

- `recommendation_clipper.clip_recommendation(...)` 的 `gate` 与 `evidence_gate`
  参数仍是 `Any` / optional，并通过 `getattr(...)` 读取 `pulse_status`、
  `max_recommendation`、`max_decision_status`、`public_allowed`、`blocked_reason`
  和 `required_ref_ids`。
- `PulseWriteGate.evaluate(...)` 的 `gate`、`evidence_gate`、`claim_verification`
  和 `source_quality` 仍是 `Any` / optional，并把缺失 evidence 默认为
  `complete`，缺失 claim 默认为 `valid=True`，缺失 public_allowed 默认为 true。
- `decide_pulse_agent_cost(...)` 虽然类型签名已经是正式
  `EvidenceCompletenessGateResult`，但仍通过 `getattr(evidence_gate, "hard_blocked", False)`
  读取 hard block。

根因：

- Root215/216/217 已经把 evidence gate、claim verifier 和 decision stage builder
  收紧到正式模型，但后段 recommendation/write gate 仍保留 duck-typing。
- 这会把前段已经应该暴露的 contract failure 再次降级成业务默认值：
  malformed evidence gate 变成 complete/public，malformed claim result 变成 valid，
  malformed Pulse gate 变成无 gate 限制。
- 对成熟 Kappa/CQRS/agent execution plane 来说，post-decision gate 是写入前最后一道
  deterministic boundary，不能替坏对象补默认值。

修复：

- `clip_recommendation(...)` 只接受正式 `PulseGateResult` 和
  `EvidenceCompletenessGateResult`，非正式输入分别抛出
  `pulse_recommendation_clipper_gate_contract_required` 与
  `pulse_recommendation_clipper_evidence_gate_contract_required`。
- `PulseWriteGate.evaluate(...)` 只接受正式 `PulseGateResult`、
  `EvidenceCompletenessGateResult`、`ClaimEvidenceVerificationResult` 和
  `PulseSourceQualityDecision`，非正式输入分别抛出对应
  `pulse_write_gate_*_contract_required`。
- `recommendation_clipper`、`write_gate`、`pulse_agent_cost_guard` 改为直接读取
  dataclass/model 字段；删除 `Any` gate 签名、optional evidence/claim/source-quality
  默认，以及 `getattr(...)` 兼容。
- Pulse domain architecture、worker flow 和 worker inventory 明确 post-decision gate
  contract 是正式 gate/result 模型，不是 duck-typed object。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_write_gate_health.py::test_write_gate_requires_formal_gate_inputs_without_reflection tests/unit/test_pulse_recommendation_clipper.py::test_recommendation_clipper_requires_formal_gate_inputs_without_reflection tests/architecture/test_pulse_no_compat.py::test_pulse_write_and_clip_gates_require_formal_models_without_reflection -q`
  初始 `7 failed`，因为 loose gate 对象被接受，且架构 guard 找到 `Any/getattr`
  兼容。
- GREEN：同一目标修复后通过，`7 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_write_gate_health.py tests/unit/test_pulse_recommendation_clipper.py tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py tests/architecture/test_pulse_no_compat.py::test_pulse_write_and_clip_gates_require_formal_models_without_reflection -q`
  通过，`18 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/write_gate.py src/parallax/domains/pulse_lab/services/recommendation_clipper.py src/parallax/domains/pulse_lab/services/pulse_agent_cost_guard.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root220 - Pulse run outcome 仍把 verifier 结果拆成 bool + optional object

发现：

- `PulseCandidateJobService._run_outcome(...)` 在 claim verifier 已经 formalized 后，
  仍接收 `claim_verification_valid: bool` 和 `claim_verification: Any | None`。
- unknown-ref 分类通过 `getattr(claim_verification, "unknown_ref_ids", ())`
  读取。如果 caller 传错 verifier 对象或漏传对象，失败会被降级成
  `invalid_unsupported_claim`。

根因：

- `ClaimEvidenceVerificationResult` 是 claim verifier 的正式输出合同；把它拆成
  bool + optional object 等于重新引入第二套 shape。
- Run outcome 会决定 agent run/job 的终态分类和后续可观察审计。如果这里允许 optional
  object fallback，claim verifier contract 断裂会被写成普通 unsupported-claim 业务结果，
  破坏故障定位。

修复：

- `_run_outcome(...)` 只接受正式 `ClaimEvidenceVerificationResult`。
- 非正式 verifier 输入抛出 `pulse_run_outcome_claim_verification_contract_required`。
- unknown-ref outcome 直接从 `claim_verification.unknown_ref_ids` 判断；删除
  `claim_verification_valid` 参数和 `getattr(...)` fallback。
- Pulse architecture、worker flow、worker inventory 明确 run-outcome classification
  使用同一个正式 claim verification result。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_outcome_requires_formal_claim_verification_result_without_reflection tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_outcome_classifies_unknown_refs_from_formal_claim_verification tests/architecture/test_pulse_no_compat.py::test_pulse_run_outcome_requires_formal_claim_verification_without_reflection -q`
  初始 `3 failed`，因为 `_run_outcome(...)` 仍要求 `claim_verification_valid`，
  架构 guard 也找到 `Any/getattr` 兼容。
- GREEN：同一目标修复后通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/architecture/test_pulse_no_compat.py::test_pulse_run_outcome_requires_formal_claim_verification_without_reflection -q`
  通过，`28 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root221 - Pulse 输出归一化仍把 sealed packet 当成 dict/duck object

发现：

- `agent_output_normalization.normalize_pulse_stage_output(...)` 的
  `evidence_packet` 参数仍是 `Any`。
- `_allowed_event_ids(...)` 从 dict packet 读取 `source_event_ids`，再通过
  `_allowed_refs(...)` 支持 dict packet 或 `getattr(packet, "allowed_evidence_refs", ())`。
- `_ref_value(...)` 同时支持 dict ref 和 object ref，意味着模型输出归一化可以绕过
  `PulseEvidencePacket` / `EvidenceRef` 的正式字段合同。
- `LiteLLMPulseDecisionClient._run_stage(...)` 已经在上游拿到了 re-validated
  `PulseEvidencePacket`，但仍把 `spec.input_payload["evidence_packet"]` 的 JSON dict
  传入归一化。

根因：

- Root215/216/217/219/220 已经把 evidence gate、claim verifier、stage builder、
  post-decision gate、run-outcome 全部收紧到 formal model，但模型输出归一化层还保留
  旧测试/旧 JSON payload 入口。
- 这会让 adapter/runtime 边界断裂被写成“正常 event-id repair”：如果 packet 或 ref
  形状坏了，系统不会在 agent boundary 失败，而是继续从 dict/object 里尽力找字段。
- 对 Pulse 来说，event-id normalization 是 FinalDecision schema validation 之前的最后
  输入修正层；它只能基于 sealed packet 的正式 allowed refs 修正非关键显示字段，不能替
  malformed packet 兜底。

修复：

- `normalize_pulse_stage_output(...)` 只接受正式 `PulseEvidencePacket`，非正式输入抛出
  `pulse_stage_output_normalization_packet_contract_required`。
- `_allowed_event_ids(...)` 直接读取 `evidence_packet.source_event_ids` 和
  `evidence_packet.allowed_evidence_refs`，直接使用 `ref.ref_id`、`ref.source_id`、
  `ref.ref_type`。
- 删除 `_allowed_refs(...)` 和 `_ref_value(...)` dict/object 反射兼容。
- `PulseDecisionRuntime` 协议和实现签名改为 formal packet；`LiteLLMPulseDecisionClient`
  从 `_run_pulse_decision(...)` 把已验证的 packet 显式传入 `_run_stage(...)`，不再从
  prompt JSON 里回捞 packet。
- Pulse domain architecture、global architecture、worker flow 和 worker inventory
  明确 stage-output normalization 也是 formal sealed packet boundary。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_agent_output_normalization.py::test_normalization_requires_formal_evidence_packet_without_dict_compatibility tests/architecture/test_pulse_no_compat.py::test_pulse_stage_output_normalization_requires_formal_packet_without_reflection -q`
  初始 `2 failed`，因为 dict packet 仍被接受，架构 guard 找到 `Any/getattr` 和
  dict-ref 兼容。
- GREEN：`uv run pytest tests/unit/domains/pulse_lab/test_agent_output_normalization.py tests/architecture/test_pulse_no_compat.py::test_pulse_stage_output_normalization_requires_formal_packet_without_reflection -q`
  通过，`10 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_agent_output_normalization.py tests/unit/test_pulse_decision_agent_client.py tests/architecture/test_pulse_no_compat.py::test_pulse_stage_output_normalization_requires_formal_packet_without_reflection -q`
  通过，`29 passed`。
- `uv run ruff check ...` 覆盖 touched source、unit 和 architecture guard，通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/agent_output_normalization.py src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py src/parallax/domains/pulse_lab/providers.py src/parallax/integrations/model_execution/pulse_decision_agent_client.py`
  通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root222 - Pulse deterministic eval 仍允许最小 dict packet 通过证据评分

发现：

- `agent_eval.grade_pulse_deterministic_eval_case(...)` 从 eval-case JSON 里读取
  `context.evidence_packet` 后，直接用 `_mapping(...)` 把非 dict 恢复成 `{}`。
- `_allowed_ref_ids(...)` 从 `packet.get("allowed_evidence_refs")` 的 list/dict
  形状里抽取 `ref_id`，不要求 eval case 中的 packet 能验证为正式
  `PulseEvidencePacket`。
- 单元测试 helper 只提供 `evidence_packet_hash` 和 `allowed_evidence_refs` 就能构造
  passing eval case，和真实 sealed packet 合同脱节。

根因：

- Eval case 是落库 JSON audit artefact，这一点没错；问题在于 JSON 里的
  `evidence_packet` 仍代表 Pulse 的 sealed packet 事实边界。
- 如果 deterministic eval 允许最小 dict packet 通过，测试和历史 artefact 就会形成第二套
  allowed-ref 语义：runtime/normalization/verifier 都要求 formal packet，但 eval 可以只看
  hash/ref list。
- 成熟 agent execution plane 的 eval ledger 应该复核同一合同，而不是替合同降级。否则 eval
  可能把缺失 source ids、schema version、candidate/window/scope、quality metrics 的 packet
  当成完整证据，误报 pass。

修复：

- `grade_pulse_deterministic_eval_case(...)` 对
  `input_json.context.evidence_packet` 调用 `PulseEvidencePacket.model_validate(...)`。
- malformed 或 partial packet JSON 归入 `evidence_packet_exists` 违规，不再进入 allowed-ref
  评分。
- `_allowed_ref_ids(...)` 改为消费 `PulseEvidencePacket`，直接读取
  `packet.allowed_evidence_refs` / `ref.ref_id`。
- 单元测试 helper 改为生成完整 `PulseEvidencePacket.model_dump(mode="json")`，新增 partial
  dict packet 失败测试。
- Pulse architecture、worker flow、worker inventory 明确 deterministic eval case 是 JSON
  audit container，但其中 packet 必须 re-validate 为 formal sealed packet。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_agent_eval_v2.py::test_evidence_first_eval_requires_formal_packet_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_deterministic_eval_requires_formal_packet_without_partial_dict_refs -q`
  初始 `2 failed`，因为 partial dict packet 被当成普通 evidence，架构 guard 找到
  `_mapping(context.get("evidence_packet"))` 和 dict ref 抽取。
- GREEN：`uv run pytest tests/unit/domains/pulse_lab/test_agent_eval_v2.py::test_evidence_first_eval_passes_complete_packet_run tests/unit/domains/pulse_lab/test_agent_eval_v2.py::test_evidence_first_eval_requires_formal_packet_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_deterministic_eval_requires_formal_packet_without_partial_dict_refs -q`
  通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/domains/pulse_lab/test_agent_eval_v2.py tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_deterministic_eval_requires_formal_packet_without_partial_dict_refs -q`
  通过，`10 passed`。
- `uv run ruff check src/parallax/domains/pulse_lab/services/agent_eval.py tests/unit/domains/pulse_lab/test_agent_eval_v2.py tests/architecture/test_agent_execution_plane_contracts.py`
  通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/agent_eval.py` 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root223 - Pulse request-audit 仍从 top-level evidence_packet_hash 构造 replay hash

发现：

- `PulseDecisionRuntimeService.request_audit(...)` 调用 `_context_packet_payload(...)`
  获取 packet payload。
- `_context_packet_payload(...)` 支持两种形状：`context["evidence_packet"]` dict，或者
  当 context 自己带 `evidence_packet_hash` 时直接 `return dict(context)`。
- `input_hash` 使用 `{"evidence_packet": packet_payload or context, ...}`，继续把 malformed
  context 当 audit 输入兜底。

根因：

- Request audit 是 replay ledger 的入口：它决定 `input_hash`、trace metadata 中的
  `evidence_packet_hash` 和 schema version。如果这里允许 top-level hash fallback，audit
  ledger 可以记录一个看似有 packet hash 的运行，但没有证明该 hash 来自正式 sealed packet。
- Root217 已经要求 prompt construction 从 formal packet/gate 构造；Root221/222 又把
  normalization/eval 收紧。request-audit 若保留旧 fallback，会成为同一链路里的最后一条
  parallel packet contract。
- 成熟 agent execution plane 要求 audit metadata 是可重放证据，而不是“尽力从 context
  里找 hash”。否则排查时 input hash 可能绑定到一个不完整 context，而不是 sealed packet。

修复：

- `request_audit(...)` 新增 `_context_evidence_packet(...)`，只从
  `context["evidence_packet"]` 读取 dict 并 `PulseEvidencePacket.model_validate(...)`。
- 缺失或 malformed context packet 抛出
  `pulse_decision_request_audit_packet_contract_required`。
- `packet_payload` 统一通过 `_agent_packet_payload(evidence_packet)` 生成；`input_hash`
  不再使用 `packet_payload or context`。
- 删除 `_context_packet_payload(...)` 和 top-level `evidence_packet_hash` fallback。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_context_evidence_packet_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_context_packet_without_top_level_hash_fallback -q`
  初始 `2 failed`，因为 top-level packet-hash context 被接受，架构 guard 找到
  `_context_packet_payload(...)` fallback。
- GREEN：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_context_evidence_packet_contract tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_claim_attempt_count tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_context_packet_without_top_level_hash_fallback -q`
  通过，`3 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_decision_stage_spec_requires_formal_packet_and_gate_without_payload_fallback tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_context_packet_without_top_level_hash_fallback -q`
  通过，`22 passed`。
- `uv run ruff check src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py tests/unit/test_pulse_decision_agent_client.py tests/architecture/test_agent_execution_plane_contracts.py`
  通过。
- `uv run mypy src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py` 通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root224 - Pulse stage audit 仍从 loose agent execution audit 反射拼字段

发现：

- `LiteLLMPulseDecisionClient` 的 `_stage_audit_from_execution(...)` 接收
  `execution_audit` 后，用 `getattr(audit, "input_hash", ...)`、
  `getattr(audit, "usage", {})`、`getattr(audit, "latency_ms", None)`、
  `getattr(audit, "parse_mode", None)`、`getattr(audit, "trace_metadata", {})`
  等反射路径拼出 `StageRunAudit`。
- `_stage_audit_from_execution_error(...)` 同样通过
  `getattr(audit, "error_message", None)` 读取错误审计；`_is_no_start_agent_backpressure(...)`
  用 `getattr(exc, "execution_started", True)` 判断错误是否已开始执行。
- 这意味着一个 `AgentExecutionError.audit=SimpleNamespace(...)` 或其他 loose
  gateway object 可以被写成看似正常的 timeout/failed stage audit。

根因：

- 平台层已经定义了正式 `AgentExecutionResult`、
  `AgentExecutionRequestAudit`、`AgentExecutionResultAudit` 和
  `AgentExecutionError`。Pulse adapter 继续通过 duck typing 读字段，本质上保留了第二套
  execution-plane 合同。
- 对 Kappa/CQRS 来说，`pulse_agent_run_steps` 是 replay ledger，不是 UI 错误摘要。
  它的 input/output hash、usage、latency、trace metadata 必须来自正式执行平面的审计模型；
  如果 adapter 可以补字段，后续排查会无法区分真实 provider timeout、模型输出不合规、
  gateway wiring 损坏和测试 fake 漂移。
- 这类错误不应该降级成 Pulse abstain。`abstain` 是模型输出/业务约束的可审计结果；
  agent execution audit contract 破裂是基础设施契约错误，必须在 run-step audit row
  合成前失败。

修复：

- `_run_stage(...)` 在读取 `execution.audit` 和 `execution.final_output` 前要求 gateway
  返回正式 `AgentExecutionResult`，否则抛出
  `pulse_decision_execution_result_contract_required`。
- `_stage_audit_from_execution(...)` 和 `_stage_audit_from_execution_error(...)`
  统一调用 `_require_execution_audit(...)`，只接受
  `AgentExecutionRequestAudit` / `AgentExecutionResultAudit`。
- stage audit 字段改为直接读取正式模型字段，不再对 audit/exception 使用
  `getattr(...)` 反射兜底。
- malformed execution result/audit 不再被 broad exception path 包成 failed stage audit；
  它会作为执行平面合同错误向外暴露。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_gateway_execution_error_requires_formal_audit_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_stage_audit_requires_formal_agent_execution_audit_without_reflection -q`
  初始 `2 failed`，因为 loose error audit 被接受，架构 guard 找到
  `getattr(audit, ...)` / `getattr(exc, ...)`。
- GREEN：同一命令通过，`2 passed`。
- 扩展轻量验证：`uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_stage_audit_requires_formal_agent_execution_audit_without_reflection tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_stage_audit_no_longer_dual_writes_safety_net_trace_metadata -q`
  通过，`23 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root225 - Pulse request-audit 仍用 raw completeness dict 写 gate replay hash

发现：

- Root223 之后，`PulseDecisionRuntimeService.request_audit(...)` 已经会重新校验
  `context["evidence_packet"]`，但 `completeness` 仍是 `dict[str, Any]`。
- `input_hash` 直接包含 `"evidence_gate": completeness`，trace metadata 也直接写
  `"evidence_gate": completeness`。
- 同一条链路稍后才在 `LiteLLMPulseDecisionClient.run_decision_pipeline(...)` 中调用
  `_evidence_gate_from_completeness(...)`，把 dict 转成 `EvidenceCompletenessGateResult`
  供 stage builder 使用。

根因：

- Request-audit 是 replay ledger 的第一入口，不能比真正 prompt/stage 输入更宽。
  如果 audit hash 接受 raw gate dict，而 stage builder 要求 formal gate，就会出现“审计记录
  说这次 gate 输入可 hash/replay，但真正执行合同并没有接受该 gate”的不一致。
- 这和 top-level packet hash fallback 是同一类问题：为了兼容 JSON payload，audit 层先把
  未验证 shape 固化进 trace metadata，随后才由执行层发现合同问题。成熟 Kappa/CQRS 的
  agent execution ledger 应该只记录已经通过领域合同的输入。

修复：

- `PulseDecisionRuntimeService.request_audit(...)` 改为要求
  `EvidenceCompletenessGateResult`，非正式 gate 抛出
  `pulse_decision_request_audit_gate_contract_required`。
- `LiteLLMPulseDecisionClient.request_audit(...)` 在进入 runtime 前调用
  `_evidence_gate_from_completeness(...)`，把外层 JSON completeness 重新校验为正式模型。
- `input_hash` 和 trace metadata 的 `evidence_gate` 都使用
  `completeness.to_json()` 产生的 gate payload。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_formal_gate_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_formal_gate_without_dict_payload -q`
  初始 `2 failed`，因为 raw completeness dict 被接受，架构 guard 找到 raw gate dict
  hash/trace payload。
- GREEN：同一命令通过，`2 passed`。
- 扩展轻量验证：request-audit packet/gate/attempt 集合通过，`5 passed`；
  Pulse decision client/request-audit architecture 集合通过，`26 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root226 - Pulse request-audit 仍把缺失 runtime_version 记录成空字符串

发现：

- `PulseDecisionRuntimeService.request_audit(...)` 用
  `str(runtime_manifest.get("runtime_version") or "")` 写 trace metadata 和 run audit metadata。
- 当 runtime manifest 缺失 `runtime_version` 时，audit 仍能生成 `runtime_hash`，但
  `runtime_version` 变成空字符串。

根因：

- Runtime manifest 是 Pulse agent execution 的 replay 合同：它描述单阶段 runner、
  timeout、model、prompt/schema、validator 和 failure taxonomy。如果 audit 允许空
  runtime version，就无法把 `runtime_hash` 和人类可读 runtime lineage 对齐。
- 成熟的 agent execution ledger 不应该把“缺 runtime version”当成一个合法默认版本。
  这会让后续 deterministic eval、成本报表和运行时变更排查变成只看 hash、看不到版本语义。

修复：

- 新增 `_runtime_manifest_version(...)`，要求
  `runtime_manifest["runtime_version"]` 存在且非空。
- 缺失或 blank runtime version 抛出
  `pulse_decision_runtime_manifest_version_required`。
- trace metadata 和 run audit metadata 统一写入验证后的 `runtime_version`。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_runtime_version_contract tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_runtime_manifest_version_without_empty_default -q`
  初始 `2 failed`，因为缺失 runtime version 被接受，架构 guard 找到空默认。
- GREEN：同一命令通过，`2 passed`。
- 扩展轻量验证：request-audit packet/gate/attempt/runtime-version 集合通过，`7 passed`；
  Pulse decision client/request-audit architecture 集合通过，`28 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root227 - Pulse request-audit 仍把空执行身份写进 agent run lineage

发现：

- `PulseDecisionRuntimeService.request_audit(...)` 仍用 `str(run_id or "")`、
  `str(job.get("job_id") or "")`、`str(model or "")`、`str(workflow_name or "")`
  和 `str(agent_name or "")` 生成 trace metadata / agent run audit metadata。
- `artifact_version_hash` 也直接透传，没有要求非空。
- 结果是 malformed caller 可以生成带空 run id、job id、model、artifact hash、workflow 或
  agent name 的 replay audit。

根因：

- 这些字段不是展示字段，而是 `pulse_agent_runs` 的执行 lineage：它们把 claimed job、
  runtime/model artifact、workflow/agent 名称、execution trace 关联在一起。
- 如果为空字符串可以进入 audit ledger，后续成本报表、eval case、provider failure
  分析和 replay 对账都会失去 join 语义；这和 Kappa/CQRS 的“事实可追溯”相冲突。
- KISS 的做法不是再加一个“unknown model / unknown workflow”兼容标签，而是在
  request-audit 边界直接拒绝 malformed execution identity。

修复：

- 新增 `_required_request_audit_text(...)`，对 `run_id`、`job["job_id"]`、`model`、
  `artifact_version_hash`、`workflow_name`、`agent_name` 做非空校验。
- 缺失字段分别抛出
  `pulse_decision_request_audit_run_id_required`、
  `pulse_decision_request_audit_job_id_required`、
  `pulse_decision_request_audit_model_required`、
  `pulse_decision_request_audit_artifact_version_hash_required`、
  `pulse_decision_request_audit_workflow_name_required`、
  `pulse_decision_request_audit_agent_name_required`。
- trace metadata、execution trace id 和 run audit metadata 统一使用校验后的身份值。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_execution_identity_fields tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_execution_identity_without_empty_defaults -q`
  初始 `7 failed`，因为空身份字段被接受，架构 guard 找到空字符串默认。
- GREEN：同一命令通过，`7 passed`。
- 扩展轻量验证：request-audit identity/packet/gate/runtime/attempt 集合通过，`14 passed`；
  Pulse decision client/request-audit architecture 集合通过，`35 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root228 - Pulse request-audit 未证明 runtime manifest 和 run audit 指向同一模型 artifact

发现：

- Root227 之后，`request_audit(...)` 已经要求传入的 `model` 和
  `artifact_version_hash` 非空。
- 但 `runtime_manifest` 自身也包含 `model.model` 和 `model.artifact_version_hash`，旧代码没有
  校验两者是否一致。
- 这意味着同一个 agent run audit 可以写入 `model=gpt-test`，但 `runtime_hash`
  实际来自另一个 model/artifact 的 manifest。

根因：

- `runtime_hash` 是对完整 manifest 的 hash；`pulse_agent_runs.model` 和
  `artifact_version_hash` 是 run ledger 的索引字段。二者必须描述同一个可执行 artifact。
- 如果不校验一致性，后续 deterministic eval、runtime version table、成本报表和 replay
  排查会出现同一个 run 同时指向两个模型 artifact 的情况。
- 成熟 agent execution plane 的 manifest 不是附加说明，而是运行合同；request-audit
  不能让合同和审计 identity 分叉。

修复：

- 新增 `_runtime_manifest_model_identity(...)`，从
  `runtime_manifest["model"]["model"]` 和
  `runtime_manifest["model"]["artifact_version_hash"]` 读取正式 runtime model identity。
- request-audit 比较 runtime manifest model/artifact 与传入 model/artifact。
- 不一致分别抛出 `pulse_decision_runtime_manifest_model_mismatch` 和
  `pulse_decision_runtime_manifest_artifact_version_hash_mismatch`。
- 单测 fixture 从最小 `{"runtime_version": "test"}` 改成真实
  `build_pulse_runtime_manifest(...)`，client pipeline tests 使用
  `_client_runtime_manifest(client)` 保证测试走生产形状。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_decision_request_audit_requires_runtime_manifest_execution_identity_match tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_request_audit_requires_runtime_manifest_model_artifact_match -q`
  初始 `3 failed`，因为 model/artifact mismatch 被接受。
- GREEN：同一命令通过，`3 passed`。
- 扩展轻量验证：runtime manifest identity 集合通过，`4 passed`；
  Pulse decision client/request-audit architecture 集合通过，`38 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root229 - Pulse agent-run 落库边界仍把 request-audit 当 loose dict 补默认值

发现：

- Root223-Root228 已经把 request-audit 入口收紧为 sealed packet、formal gate、非空 runtime
  version、非空执行 identity，以及 manifest model/artifact 一致性。
- 但 `PulseCandidateJobService` 在写 `pulse_agent_runs` 和 run-step prompt/schema 时仍然使用
  `audit.get(...) or 常量/默认值`。
- provider 结果缺 `output_hash` 时，旧代码还会用最终 decision 的 `_stable_hash(...)`
  现场补一个输出 hash。

根因：

- request-audit 入口是“生成审计包”的合同，`pulse_agent_runs` 写入是“审计 ledger sink”
  的合同；两者必须同样严格。
- 旧 job service 把下游落库边界做成了第二个事实源：backend、workflow、agent、artifact、
  prompt/schema、input hash、trace metadata、runtime identity、output hash 都可以在 sink
  处重新合成。
- 这会让同一次 run 的 replay lineage 被分叉：上游 audit 可能缺字段或错字段，但落库行看起来
  仍然完整，从而掩盖 provider adapter 或 runtime manifest 的真实合同漂移。

修复：

- 新增 `_AgentRunRequestAudit` 和 `_agent_run_request_audit(...)`，在插入
  `pulse_agent_runs` 前校验 request-audit payload。
- backend、execution trace id、workflow、agent、artifact hash、prompt/schema、runtime
  version/hash、input hash、trace metadata 全部改为必填。
- artifact hash、runtime version、runtime hash 必须与当前 runtime manifest / runtime hash
  一致。
- provider pipeline result audit 必须携带 `output_hash` 才能完成 done finalization；deterministic
  finalize 由 job service 明确计算自身输出 hash。
- run-level `usage_json` 改为从 stage audit rows 汇总，不再从 result audit 缺省回落。
- 单元测试里的旧 `claim_verification_valid` 调用也改为正式
  `ClaimEvidenceVerificationResult` fixture，避免测试层继续使用已删除兼容入口。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_complete_request_audit_before_agent_run_insert tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_request_audit_identity_to_match_runtime_manifest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_result_audit_output_hash_before_finish tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_job_service_requires_agent_run_audit_contract_without_defaults -q`
  初始 `15 failed` + `1 failed`，因为缺字段、identity mismatch 和缺 output hash 都被接受。
- GREEN：focused 单元通过，`15 passed`；架构 guard 通过，`1 passed`。
- 扩展轻量验证：Pulse job service / worker / architecture 组合通过，`96 passed`。
- targeted `ruff` 和 `mypy` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root230 - Pulse no-start backpressure 可由 loose exception audit dict 驱动

发现：

- `PulseCandidateJobService` 的 no-start backpressure 判断会从 `exc.audit`、
  `exc.agent_audit`、`agent_error_class`、`agent_execution_started` 等兼容字段里反射
  `error_class` 和 `execution_started`。
- 这意味着一个普通异常只要携带 dict audit：
  `{"error_class": "capacity_denied", "execution_started": False}`，就会被当成正式
  provider cooldown release。
- 结果是 job attempt 被回退、job 被释放到 cooldown，原始 provider/adapter 合同错误被隐藏成
  正常 backpressure。

根因：

- backpressure/release 是 worker 控制流，不是只影响 audit 展示的附属字段。
- 成熟 agent execution plane 里，控制流只能由正式 `AgentExecutionError` 驱动；
  loose audit metadata 只能作为记录材料，不能决定 job 是否释放、是否扣减 attempt、是否进入
  cooldown。
- 旧代码把错误记录形状和控制流合同混在一起，导致 malformed provider adapter 可以改变队列状态。

修复：

- `_agent_no_start_backpressure_reason(...)` 现在只接受正式 `AgentExecutionError`。
- 仅当 `exc.error_class` 属于 no-start backpressure 集合且 `exc.execution_started is False`
  时才释放到 provider cooldown。
- 删除 `_agent_error_class(...)` 兼容 helper，不再从 loose audit dict、`agent_audit`、
  `agent_error_class` 或 `agent_execution_started` 读取控制流信号。
- hard-timeout cancellation 的 execution-started 判断暂不纳入本根；其剩余 audit 读取只用于
  worker timeout cleanup，不参与 provider cooldown 分类。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_no_start_backpressure_requires_formal_agent_execution_error_without_audit_reflection tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_job_service_backpressure_requires_formal_agent_execution_error -q`
  初始 `1 failed` + `1 failed`，因为 loose audit dict 驱动 provider cooldown release。
- GREEN：加入正式 circuit-open 控制样例后 focused 命令通过，`3 passed`。
- 扩展轻量验证：Pulse job service / worker / architecture 组合通过，`97 passed`。
- targeted `ruff` 和 `mypy` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root231 - Pulse worker hard-timeout cleanup 可由 loose cancellation audit dict 改写执行状态

发现：

- `_cancelled_execution_started(...)` 会从 `exc.execution_started`、`exc.audit`、
  `exc.agent_audit` 和 audit 对象属性里反射执行状态。
- 一个普通 `CancelledError` 只要携带 `audit={"execution_started": False}`，就能把已经创建
  agent run 的 worker timeout 伪装成 before-execution timeout。
- 这会影响 `PulseJobsRepository.mark_job_cancelled_by_worker_timeout(...)` 的 retry/dead
  分类：before-execution 会回退 attempt 并 pending，after-execution 会失败或 dead。

根因：

- worker hard timeout 是队列生命周期控制流，不是展示用 audit metadata。
- 正式 agent execution plane 已经有 `AgentExecutionCancelled.execution_started`；
  worker-level cancellation 没有 agent-plane execution state 时，最可靠的本地事实是 job
  service 是否已经写入 run ledger，即 `run_started`。
- 旧代码把 loose audit dict 当控制信号，导致 malformed cancellation metadata 可以改写 job
  retry/dead 结果。

修复：

- `_cancelled_execution_started(...)` 现在只在 `isinstance(exc, AgentExecutionCancelled)`
  时读取 `exc.execution_started`。
- 其他 worker hard-timeout cancellation 统一回落到 `bool(run_started)`。
- 删除 cancellation cleanup 的 `exc.audit` / `agent_audit` / reflective
  `execution_started` 兼容读取。
- 原 before/after timeout 单测改用正式 `AgentExecutionCancelled` fixture。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_before_execution_releases_job_and_finishes_run tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_after_execution_marks_job_failed_or_dead_and_finishes_run tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_worker_timeout_ignores_loose_audit_execution_started_for_cleanup tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_job_service_timeout_cleanup_uses_formal_agent_cancellation_without_audit_reflection -q`
  初始 `1 failed` + `1 failed`，因为 loose cancellation audit dict 覆盖了 `run_started=True`。
- GREEN：focused 单元通过，`3 passed`；架构 guard 通过，`1 passed`。
- 扩展轻量验证：Pulse job service / worker / architecture 组合通过，`99 passed`。
- targeted `ruff` 和 `mypy` 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root232 - Pulse run_id 仍由空 claimed job identity 兼容拼接

发现：

- `PulseCandidateJobService.run_job(...)` 在进入 gate/evidence/request-audit 前构造
  `run_id`，但仍使用：
  `job.get("job_id") or ""`、`job.get("trigger_signature") or ""`、
  `job.get("timeline_signature") or ""`。
- 缺失或空白 claimed job 身份不会在 queue claim 边界失败，而是继续进入 evidence packet、
  runtime manifest、request audit 和 run ledger 写入路径。
- `job_id` 缺失时甚至会在后面的 `insert_agent_run(...)` 或失败处理里才炸；trigger/timeline
  缺失时则可能生成看似稳定但语义空洞的 `pulse-run` id。

根因：

- 成熟 Kappa/CQRS worker 里，claim row 是队列状态机的控制合同，不是任意 dict。
  `job_id`、`trigger_signature`、`timeline_signature`、`attempt_count` 共同定义本次 agent run
  的可重放 lineage 和 CAS/retry 语义。
- 旧代码把 run identity 当成字符串拼接材料，用空字符串维持“函数能继续跑”，等于把 malformed
  queue state 推迟到更深的 evidence/audit/SQL 层才暴露。
- 这和前面 request-audit/agent-run sink 的根因一致：入口合同缺失时不应该在下游重建或补洞。

修复：

- 新增 `_PulseJobRunIdentity` 和 `_pulse_job_run_identity(...)`。
- 在 `try` 块和 repository session 之前要求 claimed row 提供非空 `job_id`、
  `trigger_signature`、`timeline_signature` 以及正数 `attempt_count`。
- `run_id`、`pulse_agent_runs.job_id` 和 `mark_job_succeeded(...)` 都使用已验证的
  job run identity。
- 架构 guard 禁止 `str(job.get("job_id") or "")`、
  `str(job.get("trigger_signature") or "")`、`str(job.get("timeline_signature") or "")`
  回到 job service。

验证：

- RED：`uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_requires_claimed_job_identity_before_pipeline_state tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_job_service_run_identity_requires_formal_claimed_job_fields_without_empty_segments -q`
  初始 `6 failed` + `1 failed`，因为缺失或空白 claimed identity 仍能进入 pipeline。
- GREEN：focused 单元通过，`6 passed`；架构 guard 通过，`1 passed`。
- 扩展轻量验证：Pulse job service / worker / architecture 组合通过，`104 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root233 - Pulse AgentStageSpec 仍用 run_id 回填缺失的 audit/group identity

发现：

- `LiteLLMPulseDecisionClient._agent_stage_spec(...)` 在构造 `AgentStageSpec` 时仍使用：
  `audit.get("trace_metadata") or {}`、`_group_id(...) or str(run_id or "")`、
  `str(run_id or "")`。
- 如果 runtime request-audit 返回缺失 `trace_metadata` 的 dict，adapter 会继续组装
  gateway stage spec，并把 pipeline-local `run_id` 写进 trace。
- 如果 runtime stage spec 的 input packet 缺少可分组的 candidate/subject identity，
  adapter 会把 `run_id` 当 group id 替代，模型执行仍会继续。

根因：

- Root223-Root228 已经把 request-audit 生成边界收紧，但 `AgentStageSpec` 是进入
  `AgentExecutionGateway` 前的下一道合同边界。
- 成熟 agent execution plane 里，`trace_metadata.run_id` 和 stage group id 不是展示字段；
  它们决定 gateway request audit、执行 trace、后续 result audit 与领域 run ledger 是否能对齐。
- 旧代码把 malformed runtime/audit output 降级成“用本地 run_id 补一下”，导致 adapter
  还能发起模型执行，掩盖 runtime contract drift。

修复：

- 新增 `_PulseStageRequestAudit` 与 `_stage_request_audit(...)`。
- `AgentStageSpec` 构造前要求 request-audit trace metadata 存在且包含与 pipeline `run_id`
  一致的非空 `run_id`。
- 新增 `_stage_group_id(...)`，从 formal stage input evidence packet 中读取 group identity；
  缺失则抛 `pulse_decision_stage_group_id_required`。
- 删除 `_agent_stage_spec(...)` 内的 `audit.get("trace_metadata") or {}`、
  `_group_id(...) or run_id`、`str(run_id or "")` fallback。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_client_stage_spec_requires_request_audit_trace_run_identity tests/unit/test_pulse_decision_agent_client.py::test_pulse_client_stage_spec_requires_packet_group_identity_without_run_id_fallback tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_agent_stage_spec_requires_request_audit_identity_without_empty_defaults -q`
  初始 `3 failed` + `1 failed`，因为缺失/不匹配 audit trace 和缺失 group identity 都被接受或回填。
- GREEN：focused 单元通过，`3 passed`；架构 guard 通过，`1 passed`。
- 扩展轻量验证：Pulse decision client / agent-execution architecture 组合通过，`37 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root234 - Pulse workflow_name 构造期仍把显式空值恢复成默认 workflow

发现：

- `LiteLLMPulseDecisionClient.__init__(...)` 使用
  `str(workflow_name or "").strip() or WORKFLOW_NAME`。
- 这意味着调用方显式传入 `""`、`" "` 或 `None` 时，adapter 会静默恢复为
  `parallax.pulse_decision`。
- 后续 request-audit 虽然要求 workflow 非空，但它看到的已经是被 constructor 修补过的值，
  无法暴露上游 wiring 错误。

根因：

- workflow name 是 agent execution lineage 的一部分，参与 request audit、stage audit、
  trace metadata 和 replay 归因。
- 默认参数只应该代表“调用方未提供，所以使用 canonical workflow”；显式空值代表 malformed
  composition/wiring。
- 旧代码把这两种情况混在一起，保留了一个小但真实的兼容入口：构造期把错误身份修成默认身份。

修复：

- 新增 `_workflow_name(...)`，复用 `_required_identity_text(...)` 对 constructor
  workflow identity 做非空校验。
- 省略 constructor 参数仍使用默认常量；显式传空/空白/`None` 抛
  `pulse_decision_workflow_name_required`。
- 架构 guard 禁止 `str(workflow_name or "").strip() or WORKFLOW_NAME` 或
  `or WORKFLOW_NAME` 回到 constructor。

验证：

- RED：`uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_pulse_client_requires_non_empty_workflow_name_without_defaulting_blank tests/architecture/test_agent_execution_plane_contracts.py::test_pulse_decision_client_requires_constructor_workflow_identity_without_blank_default -q`
  初始 `3 failed` + `1 failed`，因为显式空 workflow 被恢复为默认。
- GREEN：focused 单元通过，`3 passed`；架构 guard 通过，`1 passed`。
- 扩展轻量验证：Pulse decision client / agent-execution architecture 组合通过，`40 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root235 - Token Radar current identity 仍从 target/intent 字段兜底

发现：

- `TokenRadarRepository._current_key(...)`、`_identity_key(...)` 和
  `stable_generation_id(...)` 仍会用
  `row.get("target_type_key") or row.get("target_type")` 以及
  `row.get("identity_id") or row.get("target_id") or row.get("intent_id")`
  生成 current row key 和 generation hash。
- `TokenRadarProjection._current_key(...)` 在 downstream previous/current row 比较时也保留同类 fallback。
- `_project_group(...)` 对 unresolved/attention 行也可能用 `intent_id` 参与 row identity。
- 这意味着 malformed projection row 可以绕过正式 serving identity，继续写入
  `token_radar_target_features` 或 `token_radar_current_rows`，并生成看似稳定的 payload/generation hash。

根因：

- `token_radar_current_rows` 是在线 leaderboard read model，`token_radar_target_features`
  虽然是 projection-private cache，但也是后续 rank-set 的正式输入。
- 成熟 Kappa/CQRS 里，serving row identity 必须由 projection 明确产出；repository
  只能验证和写入，不能从旧 target/intention 字段猜测 key。
- `intent_id` 是事件/意图事实身份，不是产品/window serving identity；把它当 fallback 会让
  attention lane 的行随事件漂移，破坏 current row 的可重建语义。

修复：

- 新增 `_current_row_identity_key(...)`，要求 `target_type_key` 与 `identity_id`
  非空后才允许 current-key comparison、first-seen lookup、payload/generation hash 或 SQL upsert。
- projection downstream `_current_key(...)` 也直接要求 formal current identity，避免 fan-out
  previous/current comparison 重新补回 target/intent 字段。
- `_project_group(...)` 显式写出 formal `target_type_key` / `identity_id`。
- unresolved attention 行使用稳定 lookup-key identity，例如 `LookupKey/symbol:UPEG`，
  不再使用 `intent_id`。
- 架构 guard 禁止 repository 重新从 `target_type`、`target_id` 或 `intent_id`
  恢复 serving identity，也禁止 projection 回到 intent fallback。

验证：

- RED：`uv run pytest tests/unit/test_token_radar_repository.py::test_token_radar_serving_identity_requires_formal_current_key_without_target_or_intent_fallback tests/architecture/test_token_radar_publication_state_hard_cut.py::test_token_radar_repository_requires_formal_current_identity_without_target_or_intent_fallback -q`
  初始 `1 failed` + `1 failed`，因为仓储仍从 target/intent 字段补 serving identity。
- GREEN：focused Root235 命令通过，`5 passed`。
- 扩展轻量验证：Token Radar repository/projection/worker + architecture 组合通过，`164 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root236 - Token Radar dirty completion identity 仍从 alias 字段兜底

发现：

- Root235 切掉了 serving current identity 的 target/intent fallback，但
  `TokenRadarProjection._claim_key(...)`、`_claim_identity_key(...)` 和
  `_source_claim_key(...)` 仍会从 `target_type`、`target_id`、`event_id`
  或默认 projection version 重建 dirty completion key。
- `TokenRadarDirtyTargetRepository._key_records(...)` 复用了入队用的 `_target_key(...)`，
  因而 target dirty done/error 可以在缺 `target_type_key` 或 `identity_id` 时继续用
  `target_type`、`target_id` 或 `intent_id` 拼 CAS key。
- `TokenRadarSourceDirtyEventRepository._key_records(...)` 也会把缺失的
  `projection_version`、`source_event_id`、`target_type_key`、`identity_id`
  从默认值或 alias 字段中补回来。

根因：

- 这里混淆了两个边界：enqueue 前可以把事实输入列映射成队列身份；claim 后的
  done/error completion key 则必须是 `claim_due` 返回的正式队列表 identity。
- Postgres CAS 删除/更新依赖完整 queue key + `payload_hash` + `lease_owner` +
  `attempt_count`。如果 identity 也能被 alias 修复，malformed claim row 会绕过
  “claimed row is the completion token”的状态机约束。

修复：

- projection 的 target dirty claim helper 直接要求 `target_type_key` 与
  `identity_id`，缺失时报 `token_radar_dirty_claim_identity_contract_required`。
- projection 的 source dirty claim helper 直接要求 `projection_version`、
  `source_event_id`、`target_type_key`、`identity_id`，缺失时报
  `token_radar_source_dirty_claim_identity_contract_required`。
- dirty target repository 新增 `_completion_target_key(...)`，source dirty repository
  新增 `_source_completion_key(...)`，completion parser 不再复用 enqueue mapping helper。
- 架构 guard 禁止 dirty completion 回到 `claim.get(...)` / `key.get(...)` alias fallback。

验证：

- RED：focused Root236 命令初始 `19 failed`，因为 target/source dirty completion identity
  仍接受 alias 字段或默认 projection version。
- GREEN：focused Root236 命令通过，`19 passed`。
- 扩展轻量验证：Token Radar dirty/projection/architecture 组合通过，`186 passed`。
- Targeted ruff、targeted mypy 通过；残留扫描只在 architecture guard forbidden list 命中旧 token。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root237 - NewsRepository 仍向上依赖 deterministic services 的 value objects

发现：

- 轻量 architecture harness `test_repositories_and_queries_do_not_import_services_or_runtime`
  发现 `news_repository.py` 从 `news_intel.services.news_entity_extraction`、
  `news_intel.services.news_fact_candidates`、`news_intel.services.news_token_mentions`
  import `NewsEntity`、`NewsFactCandidate`、`NewsTokenMention`。
- 这些对象本身是 repository 持久化 deterministic facts 的 formal payload 类型，但它们定义在
  services 层会迫使 repository/query 向上 import service module。

根因：

- AC214 已要求 News deterministic fact writes 只接受 formal result objects，避免
  dict/object reflection compatibility；但当 formal type 仍放在 services 层时，repository
  为了校验类型就违反了 Clean Architecture dependency rule。
- 正确边界应是：worker 调用 service 生成 formal result；repository 只依赖 domain types 并负责持久化。

修复：

- 新增 `news_intel.types.news_extraction`，下沉 `NewsEntity`、`NewsTokenMention`、
  `NewsFactCandidate` 三个 frozen dataclass。
- `news_entity_extraction.py`、`news_token_mentions.py`、`news_fact_candidates.py`
  从 types 层 import 并继续负责 deterministic build 逻辑。
- `news_repository.py` 改为从 types 层 import formal result objects，不再依赖 deterministic services。
- News domain architecture 明确：这些 result types 属于 `news_intel.types`，repository/query
  不得 import services/runtime/read_models。

验证：

- RED：focused architecture 命令初始 `1 failed`，列出 `news_repository.py` 的三处 service import。
- GREEN：focused architecture + service unit 命令通过，`19 passed`。
- 扩展轻量验证：`tests/architecture/test_src_domain_architecture.py` 通过，`25 passed`。
- Targeted ruff、targeted mypy 通过；残留扫描确认 repository/query 中没有这组三个 service dataclass import。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root238 - repository upward-import allowlist 掩盖了 leaf primitive 放错层

发现：

- 删除 `test_src_domain_architecture.py` 中的 repository upward-import allowlist 后，
  `test_repositories_and_queries_do_not_import_services_or_runtime` 立刻打红。
- 失败列出三处 repository -> services 依赖：
  `news_repository.py` -> `news_intel.services.news_canonical_identity`，
  `narrative_repository.py` -> `narrative_intel.services.fingerprints`，
  `token_radar_repository.py` -> `token_intel.services.token_radar_payload_hash`。
- 这些模块不是运行服务，而是 canonical identity、fingerprint、payload hash 这类
  deterministic leaf primitives；放在 services 目录会迫使 SQL/persistence 层向上依赖。

根因：

- 架构守卫的 allowlist 把分层错误“制度化”了：repository/query 仍然可以为了纯值对象或
  hash 函数 import services。
- Kappa/CQRS 的写侧边界要求 repository 拥有 SQL 和事务，依赖方向只能朝向
  `types` / interfaces / platform primitives。否则服务层可以悄悄变成 persistence
  的隐式前置依赖，后续又会产生兼容 re-export、反射 payload、默认值补齐等二阶问题。

修复：

- 新增 `news_intel.types.news_canonical_identity`，下沉 `CanonicalIdentity`、
  canonical item key、provider-global article key 和 stable news item id policy。
- 新增 `narrative_intel.types.fingerprints`，下沉 text/source/label fingerprint primitives。
- 新增 `token_intel.types.token_radar_payload_hash`，下沉 Token Radar payload canonicalization
  和 stable payload hash。
- 删除旧 `services/news_canonical_identity.py`、`services/fingerprints.py`、
  `services/token_radar_payload_hash.py`，不保留 re-export shim。
- 删除 architecture guard allowlist；repository/query 现在统一拒绝 `.services.`、
  `.runtime.`、`.read_models.` imports。

验证：

- RED：删除 allowlist 后 focused architecture 命令初始 `1 failed`，列出三处旧 service import。
- GREEN：focused architecture + 三个 primitive 单元测试通过，`38 passed`。
- 扩展轻量验证：全量 `tests/architecture -q` 通过，`924 passed`。
- Targeted ruff、targeted mypy 通过；残留扫描确认旧 service import/module 路径不再出现在
  active production/tests/docs 中。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root239 - Token Radar dirty queue lease/retry 策略所有权分裂

发现：

- `TokenRadarProjectionWorkerSettings` 已继承正式 `lease_ms`，但 worker claim 阶段仍通过
  `_dirty_target_lease_ms()` 从 projection service 读取 `DIRTY_TARGET_LEASE_MS`。
- `TokenRadarProjection.rebuild_dirty_targets(...)` 的错误重试路径也使用
  `DIRTY_TARGET_RETRY_MS`，而不是 operator-owned worker settings。
- 当测试把 `settings.lease_ms` 配成 `45000` 时，实际 dirty claim 仍使用 `120000`；
  说明运行行为没有服从配置契约。

根因：

- Token Radar dirty queue 的时间策略有两个主人：worker settings 和 service-local constants。
- 在 Kappa/CQRS worker 架构里，lease/retry 是运行时 policy，应该由 worker runtime settings
  单点拥有；projection service 只执行已声明的处理逻辑和事务边界。
- 隐藏常量会让 operator 调参失效，也会让 claim lease、error retry、backlog 恢复节奏在不同路径
  悄悄分叉，最终表现为“看似配置了 worker，实际队列行为没变”的运维错觉。

修复：

- `TokenRadarProjectionWorker` 直接读取 `settings.lease_ms` 和新增的
  `settings.retry_ms`。
- `TokenRadarProjection.rebuild_dirty_targets(...)` 和内部 transaction helper 要求显式
  `lease_ms` / `retry_ms` 参数。
- dirty target/source claim lease、source-edge failure、target-edge failure、projection failure、
  publish failure 后的 dirty error retry 全部使用传入的 runtime policy。
- 删除 `DIRTY_TARGET_LEASE_MS`、`DIRTY_TARGET_RETRY_MS` 和 `_dirty_target_lease_ms()`。
- 文档和架构守卫明确：Token Radar dirty queue timing 属于
  `settings.workers.token_radar_projection`，service 不能保留本地策略默认值。

验证：

- RED：focused unit + architecture 命令初始 `2 failed`，证明 claim 使用旧 `120000`
  且架构守卫抓到 service-local dirty policy 常量。
- GREEN：focused worker/settings/architecture 命令通过，`3 passed`。
- 扩展轻量验证：Token Radar projection/worker/market-only suite 通过，`119 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root240 - Token Radar private cache retention 没有明确 owner lane

发现：

- Root6/AC6 正确地把 `refresh_rank_set` 中的 private cache prune 删除了，避免 rank
  publication hot path 同时承担 retention cleanup。
- 但删除之后只剩 `docs/TECH_DEBT.md` 里的 open debt：`token_radar_target_features`
  和 `token_radar_rank_source_events` 旧行没有正式 worker owner。
- `prune_target_features(...)` / `prune_edges(...)` 已存在，但 SQL 没有 `LIMIT`，
  不适合作为 runtime worker 的有界维护动作。

根因：

- 这是典型的“从 hot path 拿掉副作用，但没有给副作用重新找 owner”的治理半步。
- 成熟 Kappa/CQRS 里，projection-private cache 不是 public read model，但仍然是物理
  PostgreSQL 存储；它的生命周期必须归属于单 writer 或显式 ops lane，不能靠开放 tech debt
  或 future cleanup。
- 如果 retention 继续无 owner，系统短期读路径是干净的，但存储会随历史 source/rank edge
  增长，最终把 SQL 性能问题推迟到 autovacuum、index bloat 或手工运维阶段。

修复：

- `TokenRadarProjectionWorkerSettings` 新增正式
  `private_cache_retention_enabled=true` 和 `private_cache_retention_ms=172800000`。
- `TokenRadarProjectionWorker` 在正式 settings 控制下调用
  `TokenRadarProjection.prune_private_cache(...)`；该维护路径不进入 `refresh_rank_set`。
- `TokenRadarProjection.prune_private_cache(...)` 在单个 transaction 中按 worker `batch_size`
  预算先 prune target features，再用剩余预算 prune rank-source edges。
- `TokenRadarRepository.prune_target_features(...)` 和
  `TokenRadarRankSourceQuery.prune_edges(...)` 改为 `ctid IN (SELECT ... LIMIT %s)`，
  删除动作有明确上界。
- `docs/TECH_DEBT.md` 中对应 open debt 已移除，架构文档改为描述已落地 owner lane。

验证：

- RED：focused worker/service/repository/architecture/settings 命令初始 `7 failed`，
  证明 worker 没有 retention lane、service 无 `prune_private_cache`、prune API 无
  `limit`、settings 无正式字段。
- GREEN：同一 focused 命令通过，`7 passed`。
- 扩展轻量验证：Token Radar retention 非集成套件通过，`174 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root241 - TECH_DEBT 仍把已删除 legacy asset schema 当作 open debt

发现：

- `docs/TECH_DEBT.md` 的 Open 区仍有两条 storage debt：legacy
  `assets` / `asset_aliases` / `asset_venues` / `asset_market_snapshots`
  等表“仍在 schema”，以及 duplicate-token audit 的 `idx_tir_*` /
  `idx_tirc_*` / `idx_asssnap_*` FK-index follow-up。
- 但当前 migration 已经提供两个证据：
  `20260516_0050_drop_legacy_asset_stack.py` 删除 legacy/orphan 表和
  `token_intent_resolutions.{asset_id,primary_venue_id}` 列；
  `20260517_0053_reconcile_legacy_asset_stack_drop.py` 又为错过 0050 的本地库做
  idempotent reconcile。
- `docs/generated/db-schema.md` 当前也没有这些已删除表的 current schema 条目。

根因：

- 这是治理台账和当前 schema 状态脱节，不是生产代码缺少 migration。
- 成熟 Kappa/CQRS 的审计不仅要删 runtime 兼容路径，也要让“开放债务”只描述当前真实缺口；
  否则后续 agent 会把已完成 hard cut 当作待办，浪费优先级，甚至重新围绕已删除表设计兼容修复。
- duplicate-token FK-index debt 的原始性能问题来自旧 `assets` bulk delete 触发级联
  `SET NULL`，但 hard cut 已经删除 affected columns/tables；继续把它列为 open 会误导 PostgreSQL
  性能治理方向。

修复：

- 将两条 storage row 从 `docs/TECH_DEBT.md` Open 移入 Closed，记录 resolved by
  `20260516_0050` / `20260517_0053`。
- 新增 `test_open_tech_debt_does_not_keep_resolved_legacy_asset_schema_debt`，
  要求这类已由 drop/reconcile migration 证明解决的 legacy asset schema debt 不能回到 Open。
- SDD 增加 AC237，明确 open TECH_DEBT 只能记录 unresolved current-state work。

验证：

- RED：focused harness 测试初始 `1 failed`，因为 Open TECH_DEBT 仍含 legacy asset-stack
  和 duplicate-token FK-index rows。
- GREEN：同一 focused 命令通过，`1 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root242 - resolution_refresh lookup queue timing 仍有第二套本地策略

发现：

- `ResolutionRefreshWorker` 已经把 chain ids、batch size、retry budget、reprocess limit
  拉回 `settings.workers.resolution_refresh`，但 lookup claim lease 仍从
  `DiscoveryRepository.RUNNING_LOOKUP_TIMEOUT_MS` 读取。
- 同一常量还在 `DiscoveryRepository._due_params(...)` 中决定 running lookup 何时过期，
  并在 `start_lookup(...)` 中决定 `token_discovery_results.next_refresh_at_ms` 的 running TTL。
- hot not-found retry cadence 也保留在 worker-local `HOT_NOT_FOUND_RETRY_MS`，用于 claim
  选择和 reschedule due time。
- 因此把测试 settings 配成 `lease_ms=45000`、`hot_not_found_retry_ms=7000` 时，实际 claim
  lease 仍是 `300000`，热 not-found cadence 也不是正式 settings 契约的一部分。

根因：

- `resolution_refresh` 的 dirty lookup queue 有两个运行策略 owner：worker settings 和
  worker/repository 模块常量。
- 在成熟 Kappa/CQRS worker 中，queue lease、running TTL、retry cadence 是运行时 policy，
  应由 operator-owned `workers.yaml` 单点拥有；repository 只执行显式传入的 SQL 状态转换。
- 把 TTL 写在 repository 常量里，会让 claim lease、running-state expiry、hot not-found 重试节奏
  在不同路径悄悄分叉。最终运维看到的是“调了 worker 配置，但 lookup queue 行为没变”。

修复：

- `ResolutionRefreshWorkerSettings` 显式声明 `lease_ms=300000` 和
  `hot_not_found_retry_ms=60000`，默认值保持旧行为语义。
- `ResolutionRefreshWorker` 在构造时读取正式 settings，并把 `lease_ms` 同时作为 claim
  lease 和 lookup running timeout 显式传入 `DiscoveryRepository`。
- `DiscoveryRepository.due_lookup_keys(...)`、`claim_due_lookup_keys(...)`、`start_lookup(...)`
  要求调用者显式传入 `running_timeout_ms`，不再保留 `RUNNING_LOOKUP_TIMEOUT_MS`。
- 删除 worker-local `HOT_NOT_FOUND_RETRY_MS`，hot not-found due/reschedule 全部使用
  `settings.workers.resolution_refresh.hot_not_found_retry_ms`。
- 架构文档和 worker inventory 明确：discovery lookup queue timing 属于
  `settings.workers.resolution_refresh`，repository 不能保留本地 policy constants。

验证：

- RED：focused worker/settings/architecture 命令初始 `3 failed`，证明 claim lease
  仍用 `300000` 常量、架构 guard 抓到两个本地常量、settings 默认仍继承 `120000`。
- GREEN：同一 focused 命令通过，`3 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root243 - DiscoveryRepository 仍暴露只读 due lookup peek helper

发现：

- Root242 已把 discovery lookup queue 的 lease/running/hot retry timing 拉回正式 worker
  settings，但 `DiscoveryRepository.due_lookup_keys(...)` 仍保留在生产 repository。
- 当前生产 runtime 没有任何调用者；架构 guard 也已经禁止 `resolution_refresh_worker`
  使用 `.due_lookup_keys(...)` 或 broad catch-up。
- 这个 helper 主要剩下集成测试用来观察 due ordering，并且还带着已无意义的
  `since_ms` 参数。

根因：

- 这是 hard-cut 后典型的“旧调试/测试便利 API 没有被删干净”。
- 成熟 Kappa/CQRS queue consumer 不应该同时暴露 read-only due peek 和 leasing claim
  两个消费入口。真正的 runtime 消费必须进入 `claim_due_lookup_keys(...)`，因为那里同时建立
  lease、attempt_count、CAS completion token 和 `SKIP LOCKED` 并发语义。
- read-only due helper 即使当前无人使用，也会给后续测试、ops 或修复代码一个绕过 lease/CAS
  的诱惑，重新制造“看到了 due work 但没有进入正式状态机”的第二路径。

修复：

- 删除生产 `DiscoveryRepository.due_lookup_keys(...)`。
- 删除测试 fake 中的同名“不要调用”方法，让旧入口真正不存在，而不是靠 fake 报错提醒。
- 集成测试中需要验证 due ordering / error_count 的场景改为测试文件本地
  `_due_lookup_keys_for_test(...)` SQL，不再要求 production repository 保留 peek API。
- 新增架构 guard，禁止 `DiscoveryRepository` 重新出现 `def due_lookup_keys(...)` 或
  `since_ms` 兼容参数。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 repository 仍定义
  `due_lookup_keys(...)` 和 `since_ms`。
- GREEN：同一 focused 命令通过，`1 passed`。
- 扩展非集成验证：resolution/discovery worker/repository/architecture suite 通过，`34 passed`。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root244 - Token image mirror service 仍保留隐藏 retry policy

发现：

- Root152 已把 `token_image_mirror.retry_ms` 纳入正式 worker settings，dirty source
  queue 的 error retry 使用 `settings.workers.token_image_mirror.retry_ms=300000`。
- 但 `TokenImageMirrorService` 仍保留 `TOKEN_IMAGE_MIRROR_RETRY_MS=900000`，并把
  `retry_ms` 构造参数默认到这个 15 分钟常量。
- `TokenImageMirrorWorker` 构造 service 时没有传 `retry_ms`，所以同一个镜像链路中，
  dirty-source claim error 用正式 worker settings，而 `token_image_assets.mark_error(...)`
  用隐藏 service default。

根因：

- 这是“worker settings 形式上收敛，但下游 service 仍拥有第二套运行策略”的残余。
- 在成熟 Kappa/CQRS worker 中，retry cadence 是 operator-visible runtime policy，应该由
  `workers.yaml` / worker settings 单点拥有；service 只执行明确传入的状态转换参数。
- 如果 service 保留默认值，运维调小或调大 `token_image_mirror.retry_ms` 时，只会改变
  dirty-source queue 的重试节奏，image asset lifecycle row 仍按 15 分钟重试，造成 backlog
  和 `token_image_assets` 状态看似“自己有节奏”的漂移。

修复：

- 删除 `TOKEN_IMAGE_MIRROR_RETRY_MS`。
- `TokenImageMirrorService` 构造函数要求显式 `retry_ms`，不再提供默认值。
- `TokenImageMirrorWorker` 使用 `max(1, int(self.settings.retry_ms))` 构造 service，让
  dirty-source retry 和 image asset retry 共享同一个正式 worker setting。
- 单测改为显式注入 `RETRY_MS`，worker 单测断言 service 收到正式 settings retry。
- 架构 guard 扩展到 service 文件，禁止 `TOKEN_IMAGE_MIRROR_RETRY_MS` 和
  `retry_ms: int =` 回归。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 service 仍定义
  `TOKEN_IMAGE_MIRROR_RETRY_MS` 和 `retry_ms: int = TOKEN_IMAGE_MIRROR_RETRY_MS`。
- GREEN：focused architecture 命令通过，`1 passed`；image mirror service/worker
  unit suite 通过，`16 passed`。
- 扩展非集成验证：image-source dirty / service / worker / architecture suite 通过，`27 passed`。
- targeted ruff、mypy、生产残留扫描、SDD validation / generated index / diff whitespace 检查均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root245 - NarrativeAdmissionService 仍保留本地 admission 默认和旧 carry TTL

发现：

- `NarrativeAdmissionWorker` 已经从 `settings.workers.narrative_admission` 读取
  `hot_rank_limit` 和 `min_rank_score`，并显式传入 `NarrativeAdmissionService`。
- 但 `NarrativeAdmissionService` 构造函数仍保留 `hot_rank_limit=50`、
  `min_rank_score=30` 默认值。
- 同一个 service 还保留 `carry_ttl_ms=3_600_000` 并赋给 `self.carry_ttl_ms`，
  但当前 source-frontier 算法完全不使用它；`existing_admissions` 也不会被 carry。

根因：

- 这是旧 carry-forward admission 语义 hard-cut 后留下的配置影子。
- 当前 Narrative runtime 的第一性边界是：`narrative_admissions` 只表示从当前
  Token Radar / material facts 重新计算出的 source-set frontier；不再靠历史 admission
  TTL 延续当前性。
- 如果 service 保留 threshold 默认和 carry TTL 字段，后续直接构造 service 的测试、ops
  或修复代码会绕过正式 worker settings，并误以为 admission 仍有“旧结果可 TTL carry”的
  第二策略。

修复：

- `NarrativeAdmissionService` 构造函数改为必须显式接收 `hot_rank_limit` 和
  `min_rank_score`。
- 删除未使用的 `carry_ttl_ms` 参数和 `self.carry_ttl_ms`。
- 单元测试全部显式传入 thresholds，不再传 carry TTL。
- 架构 guard 扩展到 service 文件，禁止 `hot_rank_limit: int =`、
  `min_rank_score: int =` 和 `carry_ttl_ms` 回归。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 service 仍定义本地 threshold
  默认和 `carry_ttl_ms`。
- GREEN：focused architecture 命令通过，`1 passed`；narrative admission service/worker
  unit suite 通过，`10 passed`。
- 扩展非集成验证：narrative repository / dirty-target / service / worker / architecture
  suite 通过，`36 passed`。
- targeted ruff、mypy、生产残留扫描、SDD validation 均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root246 - Pulse evidence packet 市场 freshness 仍藏在 builder/repository 默认里

发现：

- `PulseCandidateJobService` 在构建 sealed `PulseEvidencePacket` 时直接调用
  `PulseEvidenceBuilder(repos.pulse_evidence_sources).build(...)`，没有把正式
  `settings.workers.pulse_candidate` 中的 freshness policy 传入 packet 构造链路。
- `PulseEvidenceBuilder` 构造函数保留 `market_freshness_ms=3_600_000` 默认值。
- `PulseEvidenceSourceRepository.list_market_facts(...)` 也保留
  `max_age_ms=3_600_000` 和 `now_ms=None`，并在 repository 内部用当前时钟兜底。
- 结果是同一个 Pulse job 的 replay policy 分散在 job service、builder 和 repository
  三层：operator 看不到 builder/repository 的默认窗口，回放时也无法从 claimed job 的
  `now_ms` 完整解释市场证据边界。

根因：

- 这是“sealed evidence packet 形式上建立，但 packet 输入策略没有完全上移到 worker
  runtime settings”的残留。
- 成熟 Kappa/CQRS 里，read-model/agent worker 的 freshness 窗口属于 runtime policy：
  它必须由 `workers.yaml` / formal settings 单点拥有，并且每次 run 要用同一个
  `now_ms` 解释“哪些 material facts 足够新”。
- Repository 的职责是执行明确传入的查询条件，不应该决定“1 小时算新”或“未传 now 就用
  当前时钟”。否则 replay/audit 会出现同一个 `pulse_agent_jobs` claim 在不同时间重新读取
  出不同 market evidence 的风险。

修复：

- 在 `PulseCandidateWorkerSettings` / 默认 `workers.yaml` 中新增
  `evidence_market_freshness_ms=3600000`，作为正式 Pulse candidate worker policy。
- `PulseCandidateJobService` 用 `max(1, int(self.settings.evidence_market_freshness_ms))`
  构造 `PulseEvidenceBuilder`，并继续把 job run 的显式 `now_ms` 传入 packet build。
- `PulseEvidenceBuilder` 构造函数要求显式 `market_freshness_ms`，不再提供默认值。
- `PulseEvidenceSourceRepository.list_market_facts(...)` 要求显式 `max_age_ms` 和
  `now_ms`，删除 repository-local default-current-clock fallback。
- 单测 helper 改为显式构造 builder freshness；Pulse job service fake settings 也补齐
  `evidence_market_freshness_ms`，让测试对象对齐正式 settings contract。
- 架构 guard 扩展到 job service、builder 和 source repository，禁止
  `PulseEvidenceBuilder(repos.pulse_evidence_sources).build`、`market_freshness_ms: int =`、
  `max_age_ms: int =`、`now_ms: int | None =`、以及 `_now_ms() if now_ms is None`
  回归。

验证：

- RED：focused architecture 命令初始失败，先抓到 job service 直连 builder 和 builder
  本地 `3_600_000` 默认；扩展 repository guard 后再次失败，抓到 repository 仍保留
  `max_age_ms` / `now_ms` 默认与 default-current-clock fallback。
- GREEN：focused architecture 命令通过，`1 passed`；Pulse evidence packet builder、
  Pulse job service、worker settings focused suite 通过，`66 passed`。
- 扩展非集成验证：Pulse worker / evidence builder / job service / settings /
  architecture suite 通过，`120 passed`。
- targeted ruff、mypy、生产残留扫描、SDD validation / generated index / diff whitespace
  检查均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root247 - CEX CoinGlass enrichment service 仍保留 level-band 默认

发现：

- Root165 已把 `CexOiRadarBoardWorker` 收紧到正式
  `settings.workers.cex_oi_radar_board`，worker 会读取
  `coinglass_enrichment_limit` 和 `coinglass_level_limit` 并传给
  `enrich_rows_with_coinglass(...)`。
- 但 `coinglass_detail_enricher.py` 仍在 `enrich_rows_with_coinglass(...)` 和
  `enrich_row_with_coinglass(...)` 上保留 `level_limit=6` 默认。
- 单元测试也可以直接调用 service 而不传 `level_limit`，这让 CEX enrichment level-band
  budget 在 worker settings 之外还有第二套入口。

根因：

- 这是“worker 已经 formalized，但下游 enrichment service 还保留产品默认”的残留。
- CoinGlass enrichment 是可选 provider 输入，但一旦运行，它写入的是
  `cex_detail_snapshots.level_bands`，会影响 Token Case、CEX detail rail 和 Signal Pulse
  CEX evidence packet 的证据密度。
- 成熟 Kappa/CQRS worker 中，provider enrichment 的 top-K / level-band budget 都是
  operator-visible runtime policy；service 只执行 worker 明确给出的预算，不应该替 operator
  决定默认 level 数。

修复：

- `enrich_rows_with_coinglass(...)` 和 `enrich_row_with_coinglass(...)` 改为必须显式接收
  `level_limit`，删除 `=6` 默认。
- `CexOiRadarBoardWorker` 继续把正式 `settings.coinglass_level_limit` 传入 service。
- 直接 service 单测显式传入 `level_limit=6`。
- 架构 guard 扩展到 `coinglass_detail_enricher.py`，禁止 `level_limit: int =` 回归。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 enricher 仍包含
  `level_limit: int =` / `level_limit: int = 6`。
- GREEN：focused architecture 命令通过，`1 passed`；CEX CoinGlass enricher / board worker
  unit suite 通过，`14 passed`。
- 扩展非集成验证：CEX CoinGlass / board worker / repository / CEX Kappa architecture
  suite 通过，`41 passed`。
- targeted ruff、mypy 和生产残留扫描均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root248 - CEX Binance OI row builder 仍保留 period / limit 默认

发现：

- `CexOiRadarBoardWorker` 已经从正式 `settings.workers.cex_oi_radar_board` 读取
  `period`、`universe_limit` 和 `batch_size`，并计算出本轮 Binance OI board build limit。
- 但 `build_binance_oi_radar_rows(...)` 仍保留 `period="5m"` 和 `limit=500` 默认。
- 直接调用 builder 时可以绕过 worker 的 formal settings，让 CEX board 的时间粒度和
  构建预算又回到 service-local 默认。

根因：

- 这是 Root247 同一类问题：worker budget 形式上收敛，但下游 builder 还保留产品默认。
- CEX OI board 是 current read model；`period` 决定 provider OI history 的时间桶，
  `limit` 决定本轮 provider 读取和 board candidate 宽度。它们都是 worker runtime policy，
  不应该由 builder 在缺参时自行决定。
- 如果 builder 保留默认，测试、ops 或未来修复代码可以直接调用 service 并生成看似正常的
  `5m/500` board rows，绕过 `workers.yaml` 中的 period/batch/universe 配置。

修复：

- `build_binance_oi_radar_rows(...)` 改为必须显式接收 `period` 和 `limit`。
- `CexOiRadarBoardWorker` 继续从 formal settings 派生 `period` 和 bounded `limit` 后传入。
- 架构 guard 扩展到 `binance_oi_radar_builder.py`，禁止 `period: str =` 和
  `limit: int =` 回归。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 builder 仍包含
  `period: str = "5m"` / `limit: int = 500`。
- GREEN：focused architecture 命令通过，`1 passed`；CEX Binance builder / CoinGlass
  enricher / board worker unit suite 通过，`17 passed`。
- 扩展非集成验证：CEX Binance builder / CoinGlass enricher / board worker / repository /
  CEX Kappa architecture suite 通过，`44 passed`。
- targeted ruff、mypy 和生产残留扫描均通过。
- 注意：按照当前用户指令，本轮不运行 integration-heavy gate。

### Root249 - Asset Profile Refresh ready/missing/error 刷新 TTL 仍藏在 repository/service 常量

发现：

- `AssetProfileRefreshWorker` 已经从正式 `settings.workers.asset_profile_refresh`
  读取 batch、lease、statement timeout 和 provider-block retry。
- 但 `asset_profile_repository.py` 仍定义 `READY_REFRESH_MS`、`MISSING_REFRESH_MS`
  和 `ERROR_REFRESH_MS`。
- `asset_profile_refresh.py` service 写 ready/missing/error profile source cache 时，
  仍在 service 内部做 `next_refresh_at_ms = now_ms + 常量`。
- worker 重排 `asset_profile_refresh_targets.due_at_ms` 时也直接引用同一组常量。

根因：

- 这是“控制面策略所有权只迁了一半”的残留：provider-block retry 已经属于
  worker settings，但 source-cache 生命周期 TTL 仍由 repository/service 模块常量决定。
- 对成熟 Kappa/CQRS 来说，`asset_profiles` 虽然是 provider source cache，不是最终
  public read model，但它仍是 PostgreSQL material state；`next_refresh_at_ms` 和
  refresh target `due_at_ms` 共同决定下一次 provider IO、profile-current 脏目标唤醒
  以及下游公共 profile/icon 新鲜度。
- 如果 TTL 留在 service/repository，operator 调整 `workers.yaml` 时只能改变
  provider-block retry，不能改变 ready/missing/error source-cache 的刷新节奏；更糟的是
  将来直接调用 service 时，可以绕过 worker 的正式 runtime policy，生成看似正常但
  不可审计的刷新时间。

修复：

- `AssetProfileRefreshWorkerSettings` 新增正式 `ready_refresh_ms=21600000`、
  `missing_refresh_ms=900000` 和 `error_refresh_ms=900000`，并写入默认 workers YAML。
- 删除 `AssetProfileRepository` 的 ready/missing/error refresh 常量。
- `write_ready_asset_profile(...)`、`write_missing_asset_profile(...)` 和
  `write_error_asset_profile(...)` 改为必须显式接收 `next_refresh_at_ms`。
- worker 在 claim 后读取并正数化三个正式 settings，分别计算 ready/missing/error
  `next_refresh_at_ms`，同一个值同时传入 `asset_profiles.next_refresh_at_ms` 写入和
  `asset_profile_refresh_targets.due_at_ms` reschedule。
- 架构 guard 扩展到 worker/service/repository/settings，禁止 TTL 常量、
  `now_ms + 常量` 的隐式 service 计算，以及 settings 字段缺失回归。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 worker/service/repository 仍包含
  `READY_REFRESH_MS`、`MISSING_REFRESH_MS`、`ERROR_REFRESH_MS` 和 `now_ms + 常量`。
- GREEN：focused architecture + worker/service/settings 单测命令通过，`14 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root250 - PulseAdmissionPolicy 仍保留 admission policy 默认阈值

发现：

- `PulseCandidateWorkerSettings` 已经承载 `failure_circuit_per_hour` 和
  `failure_circuit_reasons`，worker 也把 failure circuit 计数和阈值传给
  `PulseAdmissionPolicy.classify(...)`。
- 但 `PulseAdmissionPolicy.classify(...)` 仍保留
  `recent_failure_count=0`、`failure_circuit_per_hour=3` 和
  `timeline_debounce_seconds=600` 默认。
- timeline-only evidence change 的 debounce 还是 service-local magic number，没有进入
  `settings.workers.pulse_candidate`。

根因：

- 这是 Root190 后的“策略所有权只治理 runtime 生效路径，未治理 policy API 表面”的残留。
- Pulse admission policy 不是普通纯函数默认值：它决定 dirty trigger 是写
  `pulse_agent_jobs`、写 suppression edge state，还是被 failure circuit / timeline debounce
  拦截。这个选择直接影响 public `pulse_candidates` 的刷新速度和 agent cost。
- 成熟 Kappa/CQRS 里，触发 admission 的阈值、debounce、预算都属于 single writer worker
  的 operator-visible runtime policy；service/policy 只执行调用方给出的策略，不应在缺参时
  自己选择一个可工作的产品默认。

修复：

- `PulseCandidateWorkerSettings` 新增正式 `timeline_debounce_seconds=600`，默认
  workers YAML 同步暴露。
- `PulseCandidateWorker` 构造时直接读取并正数化/零值化
  `timeline_debounce_seconds`，调用 `PulseAdmissionPolicy.classify(...)` 时显式传入。
- `PulseAdmissionPolicy.classify(...)` 改为必须显式接收 `recent_failure_count`、
  `failure_circuit_per_hour` 和 `timeline_debounce_seconds`；删除 policy-local 默认。
- 架构 guard 禁止 policy 重新出现这三个默认参数，并要求 worker/settings 保持正式字段和
  显式传参。

验证：

- RED：focused architecture 命令初始 `1 failed`，因为 policy 仍包含
  `recent_failure_count: int =`、`failure_circuit_per_hour: int =` 和
  `timeline_debounce_seconds: int =`。
- GREEN：focused policy/worker/settings/architecture 命令通过，`18 passed`。
- 扩展非集成验证：Pulse admission policy、Pulse candidate worker、dirty-trigger worker、
  settings 和 architecture guard 组合通过，`75 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root251 - NotificationRuleEngine 仍能在服务层读取当前时钟

发现：

- `NotificationWorker` 在 runtime 中会先计算本轮 `now_ms`，再调用
  `NotificationRuleEngine.evaluate(now_ms=now_ms)`。
- 但 `NotificationRuleEngine.evaluate(...)` 的签名仍允许 `now_ms=None`，并在缺参时调用
  `_now_ms()` 读取当前 wall clock。
- 也就是说，通知候选生成虽然被 worker 管住了主路径，但 service API 表面仍保留第二套
  时间来源。

根因：

- 这是“runtime 主路径治理完成，但 service 可重放合同未收紧”的同类残留。
- Notification rule evaluation 会读取 events、account alerts、Pulse rows、News rows，并写入
  `notifications` 和 `notification_deliveries`。这些候选的 recency/window/cooldown 判断都依赖
  evaluation time。
- 在成熟 Kappa/CQRS 中，派生写入的时间戳必须来自单 writer 的本轮运行上下文；service
  只根据传入 facts/settings/time 做纯判断。否则重跑同一批 material facts 时，候选集会因为
  service 内部当前时钟漂移而变化，破坏 replay/debug 能力。

修复：

- `NotificationRuleEngine.evaluate(...)` 改为必须显式接收 `now_ms: int`。
- 删除 `notification_rules.py` 中的 `import time` 和 `_now_ms()`。
- 架构 guard 新增检查：禁止 rule engine 重新出现 `now_ms: int | None = None`、
  `_now_ms()`、service-local current-clock fallback，并要求 `NotificationWorker` 继续显式传入
  `now_ms`。

验证：

- RED：新增架构 guard 初始 `1 failed`，命中 `import time`、可选 `now_ms`、fallback 表达式和
  `_now_ms()`。
- GREEN：notification rules、notification worker runtime 和该架构 guard 组合通过，`62 passed`。
- Targeted ruff 通过；生产残留扫描无命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root252 - Notification rule 查询窗口和 News overscan 仍是服务层隐藏策略

发现：

- Root251 删除了 rule engine 的隐式当前时钟，但 `notification_rules.py` 仍保留四个会改变候选集的
  module-level 常量：
  - `WATCHED_ACTIVITY_WINDOW_MS`
  - `NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS`
  - `NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT`
  - `NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER`
- 这些常量决定 watched account activity 的扫描窗口、News high-signal 的新鲜度过滤，以及
  News high-signal 从 read model 拉多少候选再做去重/外部推送过滤。

根因：

- 这是通知链路的“查询策略半配置化”：`candidate_limit` 已经在 `settings.notifications`，但
  实际 News 查询宽度还是 `max(500, candidate_limit * 20)`，recency 还是 service-local 2 小时。
- 在 Kappa/CQRS 语义下，notification rule evaluation 是从 material facts / read models 派生
  `notifications` facts 和 `notification_deliveries` 控制行的 business decision。候选范围本身就是
  策略，不是纯算法常量。
- 如果这些窗口/overscan 留在 service，operator 调整 `config.yaml` 时无法完整解释为什么某条
  notification 出现或缺失；直接调用 rule service 也会继续继承隐藏默认。

修复：

- `NotificationsConfig` 新增正式字段：
  - `watched_activity_window_ms=3600000`
  - `news_high_signal_recency_window_ms=7200000`
  - `news_high_signal_query_min_limit=500`
  - `news_high_signal_query_multiplier=20`
- 默认 `config.yaml` 模板同步暴露这四个字段。
- `NotificationRuleEngine` 删除上述 service-local 常量，读取
  `self.settings.notifications.*` 计算 watched activity window、News recency 和 News query limit。
- 架构 guard 禁止这些常量回到 `notification_rules.py`，并要求 settings/rule service 保持正式字段和
  显式读取。

验证：

- RED：新增 architecture guard 初始 `1 failed`，命中四个 service-local policy 常量；行为/settings
  RED 初始失败，因为 schema 拒绝新字段。
- GREEN：focused architecture 命令通过，`1 passed`；行为/settings 命令通过，`6 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root253 - Signal Pulse notification 分页预算仍是服务层常量

发现：

- Root252 已经把 watched/news 查询窗口和 News overscan 放进 `settings.notifications`。
- 但同一个 rule engine 里仍保留 `MAX_SIGNAL_PULSE_NOTIFICATION_PAGES = 5`。
- 这个值决定 Signal Pulse notification 每个 scope/status 最多翻多少页，因此也决定
  `signal_pulse_candidate` 通知候选覆盖范围和查询成本。

根因：

- 这是同一类 query budget ownership 残留：`candidate_limit`、query dimensions 和 News overscan
  都已配置化，但分页次数仍由 service-local 常量控制。
- 对成熟 Kappa/CQRS 来说，notification rule evaluation 是 worker 派生写入的一部分；
  查询宽度属于 runtime/config policy，而不是 rule service 的隐藏默认。

修复：

- `NotificationsConfig` 新增正式 `signal_pulse_max_pages=5`，默认 `config.yaml` 模板同步暴露。
- `NotificationRuleEngine` 删除 `MAX_SIGNAL_PULSE_NOTIFICATION_PAGES`，Signal Pulse 分页循环读取
  `self.settings.notifications.signal_pulse_max_pages`。
- 架构 guard 禁止分页常量回归，并要求 settings/rule service 保持正式字段和显式读取。

验证：

- RED：focused architecture 命令初始 `1 failed`，命中 `MAX_SIGNAL_PULSE_NOTIFICATION_PAGES`；
  行为/settings RED 初始失败，因为 schema 拒绝 `signal_pulse_max_pages`。
- GREEN：focused architecture 命令通过，`1 passed`；行为/settings 命令通过，`7 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root254 - NotificationWorker 构造器仍保留 external delivery max_attempts 默认

发现：

- `notification_rule` 的正式 runtime factory 已经从
  `settings.workers.notification_delivery.max_attempts` 传入 `delivery_max_attempts`。
- 但 `NotificationWorker.__init__(...)` 仍保留 `delivery_max_attempts: int = 5`。
- 这意味着直接构造 rule worker 的调用点可以绕过正式 `notification_delivery` worker 设置，用
  rule worker 自己的默认值决定新建 `notification_deliveries.max_attempts`。

根因：

- 这是“主 factory 已治理，但构造器 ABI 仍兼容旧策略”的残留。
- `notification_deliveries.max_attempts` 是外部 side-effect 控制面事实，会决定投递 retry/dead
  状态机；它应该只有一个 policy owner，即 `settings.workers.notification_delivery.max_attempts`。
- 如果 rule worker 构造器继续兜底为 5，审计时无法证明某条 delivery 的 retry budget 来自
  `workers.yaml`，还是来自绕过 factory 的旧调用。

修复：

- `NotificationWorker` 构造器改为必须显式接收 `delivery_max_attempts: int`，删除默认值。
- runtime factory 继续从 `workers.notification_delivery.max_attempts` 注入。
- 单元、架构和集成 helper 构造点全部显式传值；架构 guard 禁止
  `delivery_max_attempts: int =` 回流，并要求 factory 传入正式 setting。

验证：

- RED：focused architecture 命令初始 `1 failed`，命中
  `delivery_max_attempts: int =`。
- GREEN：focused architecture + notification worker runtime 命令通过，`19 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root255 - NewsItemBriefWorker 复用已完成/失败 run 时仍把缺失 run_id 还原为空字符串

发现：

- `NewsItemBriefWorker` 会复用 matching 的 completed `news_item_agent_runs` 来恢复
  `news_item_agent_briefs`，也会复用 matching 的 failed run 来写 failed-current。
- 但复用路径仍有多处 `str(run.get("run_id") or "")`：
  - restore completed current 时可把 `agent_run_id` 写成空字符串；
  - failed run outcome 可把 `failed_current_run_id` 写成空字符串；
  - invalid completed run 的 deterministic audit 可把 `source_run_id` 写成空字符串；
  - validation helper 遇到缺 `run_id` 时返回 `None`，让 worker 继续二次调用模型。

根因：

- 这是 run ledger 身份被当成“可选展示字段”的残留。
- `news_item_agent_runs.run_id` 是 append-only agent run ledger 与 current brief read model
  的关联键。成熟 Kappa/CQRS 中，复用 persisted run 是一种状态机分支，不是 best-effort cache。
- 如果缺 `run_id` 时继续调用模型，系统会把 malformed PostgreSQL ledger row 伪装成“没有可复用 run”，
  既浪费模型预算，也掩盖 run/current brief 关联已经断裂。

修复：

- 新增 `_required_run_id(run, reason=...)`，直接读取 `run["run_id"]` 并要求非空。
- completed run validation、completed current restore、failed run validation、failed-current outcome、
  invalid completed run audit 都改为使用该 helper。
- 缺失/空 `run_id` 现在抛 `news_item_brief_run_id_required:<reason>`，由 worker 将 dirty target 标为
  error/retry；不会二次调用模型，也不会写空 `agent_run_id`。
- 架构 guard 禁止 `run_id=str(run.get("run_id") or "")`、
  `failed_current_run_id=str(run.get("run_id") or "")`、`source_run_id = str(...)`
  和缺 run_id 返回 `None` 的 fallback 回流。

验证：

- RED：新增两个单测和一个架构 guard 初始 `3 failed`；completed/failed missing-run-id
  case 都继续调用了 provider，架构 guard 命中四个 fallback token。
- GREEN：focused missing-run-id + architecture 命令通过，`3 passed`。
- 扩展非集成验证：News item brief 单测文件和对应架构 guard 通过，`28 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root256 - PulseJobsRepository.enqueue_job 仍保留 max_attempts 默认写策略

发现：

- `PulseCandidateWorker._enqueue_if_due(...)` 已经从正式
  `settings.workers.pulse_candidate.max_attempts` 读取重试预算，并把
  `self.max_attempts` 显式传给 `PulseJobsRepository.enqueue_job(...)`。
- 但 `PulseJobsRepository.enqueue_job(...)` 自身仍保留 `max_attempts: int = 3`。
- 这意味着直接调用 repository 的路径可以绕过 worker settings，在新建或 re-enqueue
  `pulse_agent_jobs` 时写出默认 `max_attempts=3`。

根因：

- Root191 已经治理了 admission policy 读取 existing failed job row 时的 `max_attempts or 3`
  fallback，但写入侧还残留同一个思想：把 retry budget 当成 repository 可补齐的技术默认。
- 在 Kappa/CQRS 中，`pulse_agent_jobs.max_attempts` 是控制面事实；后续 claim、failed/dead
  分类和 admission suppression 都依赖这列解释状态机。它应该能追溯到一个 operator-visible
  runtime policy，而不是某个 SQL repository 的 Python 默认参数。
- PostgreSQL 最佳实践角度，写入控制列的 API 应把 required policy 放在调用边界。否则 DB
  row 形状看起来完整，实际却丢失了“为什么是 3 次”的配置来源，审计只能看到结果，不能看到决策源。

修复：

- `PulseJobsRepository.enqueue_job(...)` 删除 `max_attempts` 默认，调用方必须显式提供。
- `PulseCandidateWorker` 继续从正式 worker settings 注入 `max_attempts`；测试和辅助调用也全部显式传值。
- 单元测试证明缺 `max_attempts` 时在调用边界失败且不触达 SQL；架构 guard 禁止
  `max_attempts: int = 3` / `max_attempts: int =` 回流到 enqueue API。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖显式 `max_attempts` 入队契约。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root257 - AccountAlertService 仍保留读服务层查询窗口/宽度默认值

发现：

- `/api/account-alerts`、CLI `account-alerts` 和 notification rule engine 都会显式传入
  account alert 的 `window` 与 `limit`。
- 但 `AccountAlertService.account_alerts(...)` 自身仍保留 `window="24h"` 和 `limit=50` 默认。

根因：

- Account Alert 是 read-side 支撑服务，查询窗口和返回宽度属于调用边界或 notification 配置策略。
- 把 `24h/50` 留在 read service 内，会形成第二个查询策略源：直接调用服务时可以绕过 API/CLI
  validator 或 notification `candidate_limit`，拿到一套看似合理但不可追踪的默认范围。
- 从 PostgreSQL 最佳实践看，read path 的 `LIMIT` 和时间窗口应由入口层校验后显式下推，这样 planner
  预算、响应成本和产品语义都能从调用参数解释，而不是藏在 service method ABI 里。

修复：

- `AccountAlertService.account_alerts(...)` 删除 `window` 和 `limit` 默认，调用方必须显式提供。
- API、CLI、notification rule engine 继续显式传参，无行为变化。
- 单元测试证明缺 `window` 或 `limit` 时在调用边界失败且不触达 repository；架构 guard 禁止
  `window: str = "24h"` / `limit: int = 50` 等读服务默认回流。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖显式 account-alert 查询边界。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root258 - SearchService 仍保留搜索窗口、范围和页宽默认值

发现：

- `/api/search` 已经从 query params 读取 `limit`、`scope`、`window`，并在路由层做边界处理后显式传入
  `SearchService.search(...)`。
- `/api/search/inspect` 也把 inspect 请求的 `limit`、`scope`、`window` 显式传给 Search read model。
- 但 `SearchService.search(...)` 自身仍保留 `limit=20`、`scope="all"` 和 `window="24h"`，且
  `_since_ms(...)` 对未知窗口使用 `WINDOW_MS.get(window, WINDOW_MS["24h"])` 静默回落。
- CLI `parallax search` 没有声明 `--window`，实际依赖 read service 的 `24h` 默认窗口。

根因：

- Search 是 target-first read model，查询窗口、可见范围和页宽共同决定 PostgreSQL 扫描预算、RRF
  融合候选宽度和产品语义。它们属于 public surface / caller policy，不属于 read service ABI。
- 把 `20/all/24h` 留在 service 层，会制造第二套搜索策略源：绕过 API/CLI 的直接调用可以拿到一组看似正常、
  但无法从请求或配置追溯的查询边界。
- 未知窗口静默回落到 `24h` 会把调用错误伪装成“正常但较宽/较窄的结果”，这对 PostgreSQL hot path
  尤其危险：planner 与 latency 预算被隐藏默认改变，审计时只能看到执行结果，看不到错误输入。

修复：

- `SearchService.search(...)` 删除 `limit`、`scope`、`window` 默认，调用方必须显式传入。
- Search read service 对未知 `scope` 和 `window` 失败关闭，不再把 malformed direct-call contract
  恢复成 `all` 或 `24h`。
- CLI `parallax search` 增加 `--window {5m,1h,4h,24h}`，默认 `24h` 由 CLI parser 拥有，并显式传给
  Search read service。
- 单元测试覆盖缺失查询边界、非法 scope/window 在触达 repository 前失败；架构 guard 禁止
  `limit: int =`、`scope: str =`、`window: str =` 和 `WINDOW_MS.get(window...)` 回流。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖 Search explicit query-boundary contract。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root259 - Token-target timeline 读服务仍把未知窗口/范围恢复成默认视图

发现：

- `/api/token-case`、`/api/target-posts` 和 `/api/target-social-timeline` 都从公开 query params
  解析 `window`、`scope` 和 `limit`，并把这些查询边界传给 token-target read service。
- 但 `TokenTargetPostsService.target_posts(...)` 仍用
  `WINDOW_MS.get(window, WINDOW_MS["1h"])`，未知窗口会静默回落到 `1h`。
- `TokenTargetSocialTimelineService.timeline(...)` 也保留同样的 `1h` fallback，且 `_bucket(...)`
  对未知窗口走默认 `5m` bucket。
- 两个服务都用 `scope == "matched"` 决定 watched filter；直接调用传入未知 scope 时会被当成 `all`。

根因：

- Token Case timeline 和 target posts 是同一个 target/window/scope 视图的两种分页形态。窗口、范围和页宽
  决定 `TokenTargetRepository.timeline_rows(...)` 的 `since_ms`、`watched_only` 和 SQL `LIMIT`。
- 把未知窗口恢复成 `1h`、把未知 scope 恢复成 `all`，会把调用者错误伪装成一次成功的 PostgreSQL read。
  这会污染产品解释：用户以为看到的是请求窗口/范围，实际看到的是 service-local 默认视图。
- 从 PostgreSQL 最佳实践看，read path 的时间边界和 filter 应在入口层校验后显式下推；服务层不应在
  触发 SQL 前改写错误输入，否则 explain/latency/结果宽度都无法从请求参数追溯。

修复：

- `TokenTargetPostsService` 和 `TokenTargetSocialTimelineService` 改为通过 `WINDOW_MS[window]`
  读取正式窗口；未知窗口抛出 typed error，不触达 repository。
- 两个 read service 都改为 `_watched_only(scope)`，未知 scope 抛出 typed error，不再被当成 `all`。
- `TokenTargetSocialTimelineService._bucket(...)` 显式列出 `1h`，未知窗口失败关闭。
- 单元测试覆盖两个服务的 invalid scope/window before repository call；架构 guard 禁止
  `WINDOW_MS.get(window...)` 和 `watched_only=scope == "matched"` 回流。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖 token-target timeline explicit scope/window contract。
- 扩展非集成覆盖通过：target posts service、social timeline service 和 API read-path architecture 文件。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root260 - Token Radar projection 窗口计算仍保留 1h/24h 恢复逻辑

发现：

- `TokenRadarProjectionWorker` 已经从正式
  `settings.workers.token_radar_projection.windows/scopes/venues/hot_windows` 读取 projection work policy，
  并把 work items 传给 `TokenRadarProjection.rebuild_dirty_targets(...)`。
- 但 `TokenRadarProjection` 内部仍有多处窗口 fallback：
  `_project_source_request(...)` 和 `_source_requests_for_targets(...)` 用
  `WINDOW_MS.get(window, WINDOW_MS["1h"])`；
  `_rank_source_repair_analysis_since_ms(...)` 对未知 work-item window 用 `24h`，对空 work items 也默认 `24h`；
  `_project_group(...)` 在未传 `window_ms` 时恢复成 `1h`。

根因：

- Token Radar projection 的窗口不是普通 helper 参数，而是当前行身份、rank-source 修复读宽、
  baseline/attention history、publication state 和 downstream dirty fan-out 的控制面维度。
- Worker settings 已经是窗口策略 owner；service 再保留 `1h/24h` 恢复逻辑，会让 malformed
  direct-call 或 malformed work-item 继续写入/修复一个看似合理的窗口，破坏 `(projection_version, window, scope, venue)`
  的可审计性。
- 从 PostgreSQL 最佳实践看，projection 查询的时间边界必须由配置/work item 显式决定。把未知窗口恢复成更宽的
  `24h` rank-source repair 或更窄的 `1h` source scoring，会让 SQL 读宽和结果语义无法从控制面状态解释。

修复：

- 新增 `TokenRadarProjectionWindowError` 和 `_window_ms(window)`，所有 projection 窗口毫秒解析都通过
  `WINDOW_MS[window]`。
- `_rank_source_repair_analysis_since_ms(...)` 要求非空、合法 work-item windows，不再用 `24h` 兜底。
- `_project_group(...)` 未显式传 `window_ms` 时要求合法 `window`；显式非正 `window_ms` 也失败。
- 单元测试覆盖未知窗口不再走 `1h`、rank-source repair 空/坏 work-item 不再走 `24h`；架构 guard 禁止
  `WINDOW_MS.get(window...)`、`default=WINDOW_MS["24h"]` 和 `WINDOW_MS["1h"]` fallback 回流。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖 Token Radar projection explicit window contract。
- 扩展非集成覆盖通过：Token Radar projection unit 文件和 publication-state architecture 文件，`108 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root261 - Pulse timeline context 仍把坏窗口/范围恢复成 1h/all

发现：

- `PulseCandidateWorker` 已经把 trigger 的 `window` 和 `scope` 显式传入
  `build_pulse_timeline_context(...)`。
- 但 timeline context 服务本身仍保留 `window="1h"`、`scope="all"` 默认值。
- 具体窗口计算还用 `WINDOW_MS.get(window, WINDOW_MS["1h"])`，timeline signature
  的重复文本占比和价格变化也通过 `windows.get(window, windows["1h"])` 恢复。
- `_scope_rows(...)` 对 `matched` 以外的所有 scope 都返回全量 rows，等价于把未知 scope 当成 `all`。

根因：

- Pulse timeline context 不是 UI 辅助数据；它参与 `timeline_signature`、selected posts、
  post clusters、evidence packet 和后续 admission/agent job 决策。
- 如果坏窗口被恢复成 `1h`，坏 scope 被恢复成 `all`，系统会写出一个可哈希、可入队、
  看似正常的 Pulse candidate，但它不再忠实描述 dirty trigger 的 `(window, scope)`。
- 这会把输入契约错误变成业务事实，后续 `pulse_agent_jobs.timeline_signature`、edge state
  和 admission debounce 都会基于错误视图继续运转。
- 从 PostgreSQL 和 CQRS 最佳实践看，读宽和过滤范围必须由上游控制面显式决定；服务层不能在计算签名前改写坏边界。

修复：

- `build_pulse_timeline_context(...)` 现在要求显式 `window` 和 `scope`。
- 新增 `PulseTimelineContextWindowError` / `PulseTimelineContextScopeError`；
  窗口通过 `WINDOW_MS[window]` 解析，未知窗口失败。
- `_scope_rows(...)` 显式接受 `matched` 和 `all`，未知 scope 失败，不再默认为全量。
- timeline signature 使用 `windows[window]`，不再回退到 `1h`。
- 单元测试覆盖坏窗口和坏 scope；架构 guard 禁止 `window="1h"`、`scope="all"`、
  `WINDOW_MS.get(window...)`、`windows.get(window...)` 回流。

验证：

- 当前 focused 单元 + 架构命令通过，覆盖 Pulse timeline context explicit window/scope contract。
- 扩展非集成覆盖通过：Pulse timeline context unit 文件和对应 Pulse no-compat guard，`13 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root262 - API `_scope` validator 仍把未知 scope 改写成 matched

发现：

- 多个公开读 API 复用 `_scope(...)`：Token Radar、Search、Signal Pulse、recent events、ops diagnostics。
- 各路由本身已经通过 query 参数声明了明确默认值，比如 `scope="all"` 或 `scope="matched"`。
- 但 `_scope(value)` 仍然把任何未知值恢复成 `matched`。
- 这意味着 `scope=typo` 不会成为 `400 invalid_scope`，而会变成一次合法的 watched/matched PostgreSQL 查询。

根因：

- 入口 validator 混淆了“默认值”和“兼容恢复”。默认值应该属于具体 API surface；
  validator 只应该验证和规范化已经传入的值。
- 把坏 scope 恢复成 `matched` 会产生两层误导：响应里的 `scope` 看起来是服务端有意选择的范围，
  SQL 也会按 watched/matched 过滤执行，日志上很难追溯用户原始请求是非法的。
- 这和 Root258/259/261 是同一个根：read path 边界被 service/validator 层偷偷改写，
  让 PostgreSQL 读宽、过滤范围和产品语义脱离请求合同。

修复：

- `_scope(...)` 现在只接受 `all` 和 `matched`。
- 未知 scope 抛出 `ApiBadRequest("invalid_scope", field="scope")`。
- API route 的默认值仍留在 route signature 上；默认行为不变，只有 malformed input 从静默改写变成失败。
- 新增 Signal Pulse API 行为测试证明坏 scope 不触发 repository read；
  架构 guard 禁止 `return value if value in SCOPES else "matched"` 回流。

验证：

- 当前 focused API scope validator 命令通过。
- 扩展非集成覆盖通过：Signal Pulse、Ops、Narrative/Search 相关 API contract 和 API read-path architecture 文件，`34 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root263 - Ops capture-tier repair helper 仍把坏窗口恢复成 24h

发现：

- `parallax ops enqueue-token-capture-tier-rank-set` 的 CLI parser 已经用 choices 限制
  `--window` 为 `5m|1h|4h|24h`。
- 但内部 helper `_enqueue_token_capture_tier_rank_set(...)` 仍使用
  `WINDOW_MS.get(parsed_window, WINDOW_MS["24h"])`。
- 这意味着测试、后续 ops 复用或直接调用 helper 时，坏窗口不会失败，而会变成一次 `24h` repair scan。

根因：

- Ops repair 被误当成“人工脚本所以可以宽容”。但这条路径会读取 active Radar targets，
  计算 rank-set payload hash，并在 execute 模式写 `token_capture_tier_dirty_targets`。
- 对 Kappa/CQRS 来说，ops repair 可以做 broad discovery，但必须是显式 operator input；
  不能由 helper 自己扩大扫描窗口。
- 从 PostgreSQL 最佳实践看，repair scan 的 `since_ms` 是控制查询成本和 enqueue 范围的核心边界。
  把 malformed window 恢复成 `24h`，会让一次错误调用变成更宽的 rank-set repair 查询和潜在 dirty queue 写入。

修复：

- `_enqueue_token_capture_tier_rank_set(...)` 改为通过 `_ops_window_ms(parsed_window)` 计算 `since_ms`。
- `_ops_window_ms(...)` 直接使用 `WINDOW_MS[window]`，未知窗口抛 `ValueError("invalid ops window: ...")`。
- 单元测试覆盖 direct helper bad window，不触碰 repository。
- 架构 guard 禁止 `WINDOW_MS.get(parsed_window...)` 和 `WINDOW_MS["24h"]` fallback 回流到 helper。

验证：

- 当前 focused ops capture-tier window 命令通过。
- 扩展非集成覆盖通过：ops backfill command、capture-tier parser guard 和 architecture guard，`25 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root264 - Ops diagnostics runtime payload 仍保留 route 之外的查询默认值

发现：

- `/api/ops/diagnostics` 路由已经拥有公开默认值：`since_hours=4`、`window="1h"`、`scope="all"`。
- 路由也已经在调用 runtime payload 前执行 `_window(window)` 和 `_scope(scope)` 校验。
- 但 `ops_diagnostics_payload(...)` 本身仍然定义 `since_hours=4`、`window="1h"`、`scope="all"`。
- 这意味着直接调用 runtime helper 的测试、脚本或后续复用路径可以绕过 surface contract，
  让 runtime 重新选择诊断读窗口和 scope。

根因：

- 诊断 payload 被当成“内部工具函数”，所以默认值被复制到了 route 之外。
- 在 CQRS 读链路里，这会制造第二个契约所有者：API 以为自己已经验证了查询边界，
  runtime helper 却仍能在缺失输入时恢复成看似合法的 PostgreSQL 读范围。
- 从 PostgreSQL 性能角度，`since_hours/window/scope` 决定诊断 payload 中 domain
  freshness、watchlist、queue/domain read 的扫描宽度。默认值重复会让一次 direct-call
  漏参变成实际查询，而不是早失败。

修复：

- `ops_diagnostics_payload(...)` 现在要求显式传入 `since_hours`、`window`、`scope`。
- API route 继续保留用户可见默认值，并在调用 runtime helper 前完成校验。
- 新增单元测试证明 runtime helper 缺少查询边界时直接失败。
- 新增架构 guard 禁止 `since_hours: int =`、`window: str =`、`scope: str =`
  回流到 runtime payload，同时确认 route 仍拥有公开默认值和 `_window/_scope` 校验。

验证：

- 当前 focused ops diagnostics boundary 命令通过，`3 passed`。
- 扩展非集成覆盖通过：ops diagnostics unit、ops API contract、API read-path architecture guard，`27 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root265 - Pulse freshness health 底层仍保留 4h 默认窗口

发现：

- `SignalPulseService` 会为公开 Signal Pulse health 固定传入 `since_hours=4`。
- `parallax pulse health` / replay CLI 会把 operator 参数 `args.since_hours` 显式传给
  `PulseFreshnessHealthService.health(...)`。
- 但 `PulseReadRepository.freshness_health(...)` 和
  `PulseFreshnessHealthService.health(...)` 仍然各自定义 `since_hours=4`。
- 这让 direct-call repository/service 调用即使漏掉 health horizon，也会继续执行
  Pulse freshness SQL。

根因：

- 4h 是公开 health 产品语义，不是 repository 或低层 service 的固有事实。
- Pulse freshness 查询会派生 `since_ms`，再读取 recent jobs、runs、candidate counts。
  这个窗口控制 PostgreSQL 读宽度和健康判定语义，不能在多个层重复定义。
- 重复默认值会让测试或后续复用路径绕过 `SignalPulseService` / CLI 的显式契约，
  使同一 health payload 看起来可重放，实际读窗口却由底层 fallback 决定。

修复：

- `PulseReadRepository.freshness_health(...)` 现在要求显式 `since_hours`。
- `PulseFreshnessHealthService.health(...)` 现在要求显式 `since_hours`。
- `SignalPulseService` 仍显式传入 4h，CLI 仍显式传 operator 参数；用户可见行为不变。
- 新增单元测试覆盖 repository/service direct-call 漏参失败。
- 新增架构 guard 禁止 `since_hours: int =` 回流到底层 Pulse freshness health 边界。

验证：

- 当前 focused Pulse freshness boundary 命令通过，`3 passed`。
- 扩展非集成覆盖通过：Pulse read repository health、write-gate health/service、
  Signal Pulse service 和 architecture guard，`39 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root266 - Pulse recommendation clipper 仍为缺失 playbook horizon 补 1h

发现：

- `FinalDecision.playbook.monitoring_horizon` 在正式 v2 决策 schema 中是必填字段。
- `recommendation_clipper` 在把决策裁剪成 `ignore` / `abstain` 时，会把 playbook 改成
  `has_playbook=False` 的稳定形状。
- 但裁剪时仍使用 `payload.get("playbook", {}).get("monitoring_horizon") or "1h"`。
- 这意味着上游 agent output 或 replay audit 如果缺失 playbook horizon，
  clipper 会把 malformed decision 修成看似合法的 1h 决策。

根因：

- RecommendationClipper 是 deterministic gate ceiling，不是 agent output normalizer。
- `monitoring_horizon` 属于正式 agent decision contract；裁剪阶段只能保留已验证字段，
  不能补写默认值来让坏输出通过后续 `FinalDecision.model_validate(...)`。
- 这个问题虽不直接扩大 SQL，但会破坏 Kappa/CQRS 的 replay 语义：
  同一条 `pulse_agent_runs` / stage audit 看起来产生了完整 playbook，
  实际上完整性来自裁剪兼容层，而不是模型输出和 schema validation。

修复：

- 新增 `_playbook_monitoring_horizon(...)`，要求 payload 中存在非空
  `playbook.monitoring_horizon`。
- `_clip_to_ignore(...)`、`_clip_to_abstain(...)`、`_replace_recommendation(...)`
  都只复用已有 horizon。
- 缺失 horizon 抛 `pulse_recommendation_clipper_playbook_horizon_required`。
- 新增单元测试覆盖 malformed decision 不再恢复成 1h。
- 新增架构 guard 禁止 `or "1h"` 回流到 recommendation clipper。

验证：

- 当前 focused recommendation clipper horizon 命令通过，`2 passed`。
- 扩展非集成覆盖通过：recommendation clipper、write-gate health 相关单元和
  Pulse architecture guards，`17 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root267 - Macro asset correlation builder 仍保留 60d 查询默认

发现：

- `/api/macro/assets/correlation` 已经通过 `_correlation_window(request)` 拥有公开默认值：
  缺少 `window` 时使用 `60d`，未知窗口返回 `invalid_window`。
- route 会用该 window 计算 `correlation_query_bounds(window)`，再按 bounds 从
  `macro_observations` 读取观测。
- 但 `build_macro_asset_correlation(...)` 本身仍然定义 `window="60d"`。
- 这让 direct-call builder 调用在漏掉 window 时仍可构造 60d correlation payload。

根因：

- 60d 是 HTTP 产品默认值，不是 correlation builder 的内在计算事实。
- 对 PostgreSQL 链路来说，window 决定 `lookback_days`、`limit_per_series` 和
  进入内存相关性计算的数据宽度；这个边界必须在 route 层显式确定。
- builder 自带默认值会制造第二个窗口 owner，使 API 校验、查询 bounds 和
  payload builder 之间的契约不再单一。

修复：

- `build_macro_asset_correlation(...)` 现在要求显式 `window`。
- API route 继续保留用户可见 `60d` 默认和 invalid-window 校验。
- 新增单元测试覆盖 direct-call 漏 window 失败。
- 新增架构 guard 禁止 `window: str = "60d"` 回流到 builder，同时确认 route
  仍显式传入 `window=window`。

验证：

- 当前 focused macro asset correlation window 命令通过，`2 passed`。
- 扩展非集成覆盖通过：macro correlation unit、相关 API contract 和 architecture guard，`8 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root268 - Pulse/Narrative dirty claim 仍能把坏窗口/范围变成 all 或 24h

发现：

- `PulseCandidateWorker` 从 `pulse_trigger_dirty_targets` claim 中读取 `window` / `scope`
  后，只检查字段是否非空。
- 后续 Pulse timeline hydration 直接使用 `watched_only=scope == "matched"`。
  当 claim 里的 `scope` 是非空坏值时，表达式为 false，实际会按 all-public 范围读取
  `token_targets.timeline_rows_for_event_ids(...)`。
- `NarrativeAdmissionWorker` 也只检查 dirty claim 的 `window` / `scope` 非空；
  source-set 查询同样使用 `watched_only=scope == "matched"`。
- Narrative 额外保留 `_window_ms(window).get(..., 86_400_000)`，使未知窗口可恢复为
  `24h` source-set 宽度。

根因：

- dirty target row 是 worker 控制面的事实，不是可容错的用户输入草稿。
  claim 被 worker 成功领取后，`window/scope` 决定后续精确 current-row lookup、source-set
  时间窗口和 watched/public 过滤，属于 PostgreSQL 读宽度合同。
- 成熟 Kappa/CQRS worker 的 dirty claim 处理应先验证 claimed row 是否仍符合当前 worker
  settings，再进入 payload read；坏 claim 应走 error/retry 或 dead-letter，而不是被解释成更宽的合法查询。
- 当前问题和 Root259/261/262 是同一根：`scope == "matched"` 被当成过滤器实现细节，
  却没有在调用点之前证明 scope 已经合法，于是 malformed scope 被静默降级成 all-public。

修复：

- `PulseCandidateWorker` 在 claim 字段非空后，要求 `window` 属于 `self.windows`，
  `scope` 属于 `self.scopes`；不满足时抛
  `pulse_trigger_dirty_target_invalid_window/scope` 并进入现有 dirty trigger error/retry 分支。
- `NarrativeAdmissionWorker` 初始化时保存正式 settings `windows/scopes`，
  `_process_claim_sync(...)` 通过 `_required_claim_member(...)` 校验 claim 维度。
- Narrative `_window_ms(...)` 改为严格 `NARRATIVE_WINDOW_MS_BY_KEY[window]`，
  删除未知窗口恢复成 `24h` 的 fallback。
- 新增单元测试证明坏 dirty claim 不会触发 token-radar exact row、timeline 或 narrative
  payload reads。
- 新增 architecture guard 防止 dirty claim window/scope strict contract 和
  Narrative 24h fallback 回流。

验证：

- Focused dirty-claim dimension 命令通过，`5 passed`。
- 扩展非集成覆盖通过：Narrative worker、Pulse dirty-trigger worker 和 architecture guard，`19 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root269 - Token Radar projection service 仍保留工作宽度和 lease owner 默认值

发现：

- `TokenRadarProjectionWorker` 已经从 formal worker settings 读取 `limit`、
  `lease_ms`、`retry_ms`，并把 `rank_limit` 和 `lease_owner=self.name`
  传给 `TokenRadarProjection.rebuild_dirty_targets(...)`。
- 但 projection service 自身仍保留 `limit=100`、`rank_limit=100` 和
  `lease_owner="token_radar_projection"` 默认值。
- 这意味着测试、脚本或未来维护代码可以绕过 worker，直接用服务层默认值 claim
  dirty targets、refresh rank set，形成第二个批宽/lease owner policy owner。

根因：

- `limit/rank_limit/lease_owner` 不是纯计算参数，而是 PostgreSQL 控制面合同：
  它们决定 `claim_due(... LIMIT ...)`、rank publication 的读取宽度，以及 dirty claim
  的 worker 归属。
- 成熟 Kappa/CQRS 架构中，derived read model 的 catch-up 宽度和 lease identity
  应由唯一 runtime writer 的配置拥有；projection service 只执行被显式注入的 work。
- 服务层默认值会让“worker manifest/settings 是唯一运行时 policy 来源”的边界失真，
  也会让生产 SQL 性能审计无法从 `workers.yaml` 推导真实批宽。

修复：

- `TokenRadarProjection.rebuild(...)`、`refresh_rank_set(...)`、
  `rebuild_dirty_targets(...)` 和 `_rebuild_dirty_targets_in_transaction(...)`
  现在要求 caller 显式传入 work width。
- dirty target rebuild 还要求显式 `rank_limit` 和 `lease_owner`，worker 继续传
  `rank_limit=self.limit`、`lease_owner=self.name`。
- 单元测试覆盖缺少 `limit/rank_limit/lease_owner` 时在 claim/publish 前失败。
- 架构 guard 用 AST 校验这些参数是 required keyword-only 参数，并禁止
  `100`/default owner 回流。

验证：

- 当前 focused Token Radar policy 命令通过，`4 passed`。
- 扩展非集成覆盖通过：Token Radar projection、market-only projection 和 architecture
  guard，`100 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root270 - Watchlist overview 仍用输出 limit 掩盖无界 source-event 扫描

发现：

- `/api/watchlist/handle/{handle}/overview` 的 route 没有暴露 overview limit；
  route/service 只传 `handle/scope/since_ms` 到 repository。
- `WatchlistIntelRepository.handle_overview(...)` 保留 `limit=500` 默认值，但这个
  `limit` 只限制最终 cluster 输出。
- SQL 本身没有 `LIMIT`，会把该 handle 在 3d 窗口内的全部 `events` 拉入内存，
  然后对全部 event ids 做 token resolution fan-out。
- 旧性能审计里已经把这个路径标为 P1：`limit` 不是 SQL source-row limit。

根因：

- Watchlist overview 把“产品展示多少 clusters”和“PostgreSQL 读取多少 source rows”
  混成一个隐藏 repository 默认。
- 成熟 CQRS read path 应把窗口、source sample 宽度、输出 cluster 宽度分开：
  完整指标用聚合 SQL，明细/cluster 构造用 bounded sample，避免 request-time 全窗口 fan-out。
- repository 层的 `limit=500` 让 API surface、service config 和 SQL 执行宽度之间没有单一 owner；
  运维无法从公开 route/read config 推导一次 overview 请求的最大源事件读取量。

修复：

- `WatchlistReadWindowConfig` 现在显式包含 `window_days`、`overview_source_limit`
  和 `overview_cluster_limit`，route helper 是这些 public read defaults 的 owner。
- `WatchlistHandleReadService` 要求显式 config，并把 source/cluster budgets 传给 repository。
- `WatchlistIntelRepository.handle_overview(...)` 要求显式 `source_limit` 和
  `cluster_limit`，删除 `limit=500` 默认。
- Repository 先用聚合 SQL 计算窗口 source count / latest timestamp，再用 `LIMIT %s`
  读取 bounded source sample 做 token resolution fan-out 和 cluster 构造。
- 新增 Watchlist 域架构文档和 architecture guard，防止无界 overview scan 回流。

验证：

- Focused Watchlist overview 命令通过，`5 passed`。
- 扩展非集成覆盖通过：Watchlist repository/API unit 和 architecture guard，`9 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root271 - Pulse stale-running job 清理仍有 repository/helper 批宽默认值

发现：

- `PulseCandidateWorker.process_due_jobs_once_async(...)` 每轮在 claim agent job
  前都会清理 exhausted stale-running `pulse_agent_jobs`。
- 生产 helper `_terminalize_exhausted_stale_running_jobs(...)` 仍写死
  `limit=100`，同时
  `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)` 也保留
  `limit=100` 默认。
- 这条路径写 `pulse_agent_jobs` dead state 和 `worker_queue_terminal_events`
  终态证据，是控制面生产写路径，不是诊断分页。

根因：

- Pulse 已经把 `job_running_timeout_ms`、`max_attempts`、dirty-trigger lease/retry
  等策略收敛到 `settings.workers.pulse_candidate`，但 stale-running 终态清理的
  batch width 没有被建模成 formal worker policy。
- 在成熟 Kappa/CQRS worker 设计里，catch-up/cleanup 的 SQL 宽度必须由唯一
  runtime writer 的 manifest/settings 拥有；repository 只执行被注入的 SQL 预算。
- helper/repository 默认值会让一次 worker cycle 的最大写宽度无法从 `workers.yaml`
  和 worker inventory 推导出来，也会让未来 direct caller 绕过 worker policy。

修复：

- 新增 `settings.workers.pulse_candidate.stale_running_terminalization_batch_size`
  及默认 workers YAML 项。
- `PulseCandidateWorker` 构造时读取该设置，并显式传给
  `_terminalize_exhausted_stale_running_jobs(...)`。
- Helper 接收 required `limit`，再传给
  `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`。
- Repository 删除 `limit=100` 默认；漏传 `limit` 会在 SQL 前失败。
- 单元测试和 architecture guard 防止 `limit=100` / repository-local batch 默认回流。

验证：

- Focused Pulse terminalization policy 命令通过，`7 passed`。
- 扩展非集成覆盖通过：Pulse job repository、Pulse candidate worker、
  dirty-trigger worker 和 Pulse architecture guard，`119 passed`。
- 配置单元测试通过，`114 passed`。
- Targeted ruff 通过；mypy 在 `UV_CACHE_DIR=/private/tmp/parallax-uv-cache`
  下通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root272 - News item brief worker 仍用反射兼容松散 validation/audit/admission 对象

发现：

- `NewsItemBriefWorker` 的 completed-run reuse 已经通过
  `validate_news_item_brief_output(...)` 生成正式
  `NewsItemBriefValidationResult`，但后续仍用 `getattr(validation, ...)`
  读取 `publishable/status/errors`。
- Provider failure audit 的正式来源是
  `AgentExecutionError.audit: AgentExecutionRequestAudit | AgentExecutionResultAudit`，
  但 `_provider_error_audit(...)` 仍通过 `getattr(audit, "model_dump", None)`
  和 Mapping fallback 接受松散 audit 形状。
- `_dict(...)` 和 `_object_payload(...)` 还接受 dataclass/asdict、任意
  `model_dump`、`__slots__`，导致 `NewsItemAgentAdmission` 这类 formal domain
  result 可以被普通对象兼容替代。

根因：

- News item brief 是 LLM-backed worker，最需要把“执行平面 audit”和“领域校验结果”
  分开并强类型化；否则 provider/测试 fake 的任意对象形状会变成生产合同。
- 成熟 Kappa/CQRS 下，agent 结果不是事实，只有经过 formal validation 后写入
  run ledger/current brief 的结构化状态才是可重放证据。反射兼容层会把 malformed
  execution output 伪装成可恢复状态。
- 这种 shim 还会削弱 SQL/链路审计：`news_item_agent_runs` 的 audit 字段看似完整，
  但来源可能不是 AgentExecutionGateway 的正式 audit envelope。

修复：

- `_completed_run_validation(...)` 现在返回带
  `NewsItemBriefValidationResult` 的内部 typed 结果，reuse 判断直接读取
  `validation.publishable/status/errors`。
- `_provider_error_audit(...)` 只接受正式
  `AgentExecutionRequestAudit | AgentExecutionResultAudit`，错误 audit 类型直接失败。
- `_audit_dict(...)` 要求 provider result 的 `agent_run_audit` 是 Mapping；
  非 Mapping 不再被 duck-typed。
- `_agent_admission_payload(...)` 明确要求 `NewsItemAgentAdmission`，删除
  `_object_payload` 和 `_dict` 的 dataclass/model_dump/slots fallback。
- 新增单元测试和 architecture guard 防止反射入口回流。

验证：

- Focused News item-brief formal-contract 命令通过，`4 passed`。
- 扩展非集成覆盖通过：News item-brief worker 和 News architecture guard，`74 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root273 - News item brief 实体域支撑仍把 formal entity lane 当作松散对象

发现：

- `NewsItemBriefInputPacket.entity_lanes` 已经是正式的
  `NewsItemBriefEntityLane` Pydantic 合同，且 `extra="forbid"`。
- 但 `news_item_brief_entity_support._entity_lane_domains(...)` 仍用
  `getattr(entity, "market_domain", "")`、`getattr(entity, "entity_type", "")`、
  `getattr(entity, "target_id", None)`、`getattr(entity, "target_type", None)` 和
  `getattr(entity, "candidate_targets", ())` 推导市场域。
- 这意味着 malformed entity lane、测试 fake、旧 Mapping 形状或缺字段对象不会在
  输入包边界失败，而会被吞成空 domain / 无 candidate targets。

根因：

- News item brief 的实体支撑代码处在 agent prompt/validation 前的证据边界。
  它决定哪些实体和 source-backed keys 可以作为市场域证据进入 item-brief 输出校验。
- 成熟 Kappa/CQRS 设计里，输入包是 worker 从 PostgreSQL material facts 构造出来的
  可重放合同；如果这里继续 duck typing，错误就会从“坏事实/坏包”降级成
  “证据不足”。这会掩盖事实链路或 packet builder 的结构问题。
- `getattr(..., fallback)` 在这种位置不是无害兼容，而是把 schema 漂移变成静默业务
  分支：market_domain 缺失不再报错，而是让后续 domain support 变窄，最终可能影响
  publishable validation、alert eligibility 和 page projection 的可解释性。

修复：

- `_entity_lane_domains(...)` 改为接收 `NewsItemBriefEntityLane`。
- 直接读取 `entity.market_domain`、`entity.entity_type`、`entity.target_id`、
  `entity.target_type` 和 `entity.candidate_targets`。
- 新增单元测试证明正式 entity lane 正常推导 domain，而 loose Mapping 输入会失败。
- 新增 architecture guard 防止 `getattr(entity, ...)`、`hasattr`、`model_dump`、
  `__slots__` 等对象反射兼容重新进入 entity support。

验证：

- Focused News item-brief entity-lane contract 命令通过，`2 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root274 - Signal Pulse public list 仓库仍保留 `limit=50` 隐藏读宽度

发现：

- `/api/pulse` 和 `SignalPulseService.pulse(...)` 已经把 public list 的 `limit`
  作为显式查询边界传入 repository。
- 但 `PulseReadRepository.list_candidates(...)` 仍有 `limit: int = 50` 默认值。
- 这使直接 repository 调用可以绕过 API/service 的 validated limit，把一次 PostgreSQL
  read width 静默恢复成 50。

根因：

- CQRS 读模型的 public list 宽度属于 surface/service 合同，不属于 repository。
  Repository 负责执行被注入的 SQL 边界，而不是替用户或测试 fake 决定产品默认。
- 成熟 Kappa/CQRS 下，public read path 的 `window/scope/limit/cursor` 必须能从
  API/CLI/service 入参和日志中重建；仓库默认会制造“看似正常、实际缺边界”的查询。
- 这种默认值在性能审计里尤其危险：SQL 仍然有 `LIMIT`，但 limit 的来源不是显式
  调用方，后续很难判断读宽度是产品选择、测试偶然还是遗留兼容。

修复：

- `PulseReadRepository.list_candidates(...)` 删除 `limit=50`，要求调用方显式传入
  `limit`。
- 保留 repository 内部 `max(0, min(int(limit), 200))` 防御性硬上限，但该上限只约束
  显式传入值，不再提供产品默认。
- 新增单元测试证明漏传 `limit` 在 SQL 前失败。
- 新增 architecture guard 防止 `limit: int =` 默认回流，并确认
  `SignalPulseService.pulse(...)` 继续显式传 `limit=limit`。

验证：

- Focused Pulse public list-width 命令通过，`2 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root275 - ProjectionRepository 诊断读仍保留 `20/50` 控制面默认宽度

发现：

- Token Radar projection 的运行时 dirty claim / rank publish 宽度已经由
  `TokenRadarProjectionWorker` 显式传入。
- 但 `ProjectionRepository.list_runs(...)` 仍有 `limit=20`，
  `ProjectionRepository.list_dirty_ranges(...)` 仍有 `limit=50`。
- `status_summary()` 自身已经显式用 `limit=1` 读 latest run；遗留默认主要让直接
  diagnostic/test 调用可以不声明 SQL 宽度。

根因：

- `projection_runs` 和 `projection_dirty_ranges` 是投影控制面，不是普通日志表。
  查询它们虽然是诊断读，但仍然是 PostgreSQL read width，需要调用方显式声明。
- 成熟 Kappa/CQRS 的控制面审计要求：worker 写宽度、repair 宽度、diagnostic 读宽度
  都能从调用边界推导。Repository 默认会让状态页或调试脚本的查询宽度变成隐藏策略。
- 这类默认值不会直接破坏 serving row，但会削弱性能审计：一次看似小的状态查询是
  因为调用方选择了 20/50，还是因为仓库兜底，日志里无法区分。

修复：

- `ProjectionRepository.list_runs(...)` 改为 required `limit`。
- `ProjectionRepository.list_dirty_ranges(...)` 改为 required `limit`。
- `status_summary()` 保持显式 `limit=1`。
- integration 测试源码中 `list_runs(projection_name=...)` 改为显式 `limit=20`
  （按用户指令未运行 integration）。
- 新增单元测试和 architecture guard 防止 `limit=20` / `limit=50` 回流。

验证：

- Focused projection diagnostic limit 命令通过，`2 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root276 - Resolution refresh source-dirty enqueue 仍把 resolver decision 当松散对象兼容

发现：

- `token_resolution_refresh._source_dirty_event_for_decision(...)` 在生成
  `token_radar_source_dirty_events` 输入前，仍通过 `getattr(decision, ..., None)`
  读取 `target_type` / `target_id` / `event_id`。
- 上游 `TokenIntentResolver.resolve(...)` 的正式返回值已经是
  `TokenIntentResolutionDecision` / `DeterministicResolution`，且 reprocess 外层已经在
  `RepositorySession.transaction` 中写 resolution、lookup、discovery 和 source-dirty。
- 这条反射兼容会让 malformed resolver mock 或未来错误 DTO 被解释成“没有 dirty work”，而不是在 source-dirty 事实边界前失败。

根因：

- resolution refresh 处在事实写入和 Token Radar source-dirty 控制面之间。它不是展示层 DTO 适配点，而是决定哪些 source event edge 进入投影链路的关键边界。
- 成熟 Kappa/CQRS 的做法是：投影控制面的 enqueue 输入来自正式事实/决策合同；如果决策对象不是正式合同，应当失败并回滚当前 reprocess 事务，而不是用缺字段默认值静默跳过。
- `getattr(..., None)` 看似提高测试/兼容性，实际隐藏了两类根因：resolver 返回类型漂移，以及 source-dirty 边缺失。两者都会让后续 Token Radar catch-up 看起来“无事可做”，增加排障成本。

修复：

- `_source_dirty_event_for_decision(...)` 改为接收并校验
  `TokenIntentResolutionDecision`。
- source-dirty enqueue 前直接读取 `decision.target_type`、
  `decision.target_id`、`decision.event_id`。
- loose resolver decision object 现在以
  `token_resolution_refresh_decision_contract_required` 失败，并且不会写 source-dirty enqueue。
- 新增单元测试和 architecture guard 禁止 `getattr(decision, ...)` /
  `decision.get(...)` / `hasattr(decision, ...)` 回流。

验证：

- Focused resolution decision contract 命令通过，`2 passed`。
- Broader token resolution refresh unit/architecture 命令通过，`10 passed`。
- ruff、mypy 和残留反射扫描通过；残留命中只在 architecture guard 的禁止字符串里。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root277 - IngestService 首次 source-dirty enqueue 仍接受 dict/object resolver decision

发现：

- Root276 收紧了 resolution reprocess，但 `IngestService` 首次 ingest 事务里仍保留
  `_decision_value(decision, key)`。
- 这个 helper 同时支持 `dict` 和任意对象属性，服务于 lookup-key replacement、
  discovery lookup enqueue、market capture context、watched-account alert fallback 和
  `token_radar_source_dirty_events` enqueue。
- 上游 `resolve_prepared(...)` 已经返回正式
  `TokenIntentResolutionDecision` / `DeterministicResolution`，所以 dict/object 双形态不再是必要适配，而是事实写入边界的兼容残留。

根因：

- ingest 是第一条 durable fact transaction：`events`、`token_intents`、
  `token_intent_resolutions` 和 source-dirty fan-out 在同一个事务里建立。
- 如果这里接受 dict-like 或 loose resolver decision，系统会形成两套 source-dirty 输入合同：
  初次 ingest 可以靠 `_decision_value` 兼容，resolution reprocess 却要求正式 decision。
- 成熟 Kappa/CQRS 的关键不是“能把各种 shape 都读出来”，而是投影控制面输入必须来自正式事实/决策模型。否则 resolver 类型漂移会被解释成空 lookup、空 source-dirty 或错误 market capture，后续 worker 只能看到“没有工作”，看不到真实错误。

修复：

- `IngestService.commit_prepared_event(...)` 的 `resolutions` 参数改为
  `list[TokenIntentResolutionDecision]`，并在写 resolution 前校验正式合同。
- `market_resolution_for_decision(...)`、`_cex_pricefeed_for_decision(...)`、
  `_source_dirty_events_for_resolutions(...)`、`_discovery_lookup_keys_for_resolutions(...)`
  改为直接读取 formal decision fields。
- 删除 `_decision_value(...)` dict/object 兼容 helper。
- 新增单元测试和 architecture guard 禁止 `_decision_value(...)`、
  `isinstance(decision, dict)`、`decision.get(...)`、
  `getattr(decision, ...)`、`hasattr(decision, ...)` 回流。

验证：

- Focused ingest resolution decision contract 命令通过，`2 passed`。
- Broader ingest/source-dirty unit/architecture 命令通过，`17 passed`。
- ruff、mypy 和残留扫描通过；残留命中只在 architecture guard 的禁止字符串里。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root278 - NarrativeReadModel 仍把 Token Radar 旧 `type/id` 别名当目标身份兼容

发现：

- `NarrativeReadModel._extract_targets(...)` 和 `_hydrate_row(...)` 仍通过
  `row.get("target_type") or row.get("type")`、
  `row.get("target_id") or row.get("id")` 读取 Token Radar row identity。
- 当前 Narrative runtime 的事实边界已经是 `narrative_admissions`，历史
  `token_discussion_digests` 只能作为 legacy context 被读。
- Token Radar serving identity 和 Narrative admission claim 也已经收紧到正式
  `target_type` / `target_id` 或正式 dirty target fields，因此公开读模型继续接受
  `type/id` 会留下最后一段旧 payload shape 兼容。

根因：

- 这是 Kappa/CQRS 里典型的“写链路已硬切，读组合层还在帮旧 DTO 复活”的问题。
  读模型为了让旧行还能展示 discussion digest，把历史目标身份恢复逻辑留在
  public hydration 中，结果公开读路径变成了第二套 target-key normalizer。
- 成熟 CQRS 的读端可以组合历史上下文，但不能改写事实身份：如果当前 serving row
  没有正式 `target_type` / `target_id`，正确状态是 narrative context missing，而不是用
  旧 `type/id` 反推 digest key。
- 这个兼容会削弱故障定位。上游投影或 API schema 漂移本应表现为“缺 narrative
  target identity”，但旧回退会让页面继续显示历史 digest，看起来像当前链路仍然健康。

修复：

- `NarrativeReadModel` 只从 `target_type` / `target_id` 提取 Token Radar target identity。
- 只有旧 `type/id` 的 Token Radar row 不再触发历史 digest lookup，返回显式
  `no_ready_digest` / `not_ready`。
- 新增单元测试证明即使 repository 中存在 matching ready digest，旧 alias-only row 也不会被
  rehydrate。
- 新增 architecture guard 禁止 `row.get("type")`、`row.get("id")` 及
  `target_type/target_id` 旧别名回退重回 Narrative read model。

验证：

- Focused Narrative read-model identity 命令通过，`2 passed`。
- 残留扫描只在 architecture guard 的禁止字符串里命中旧 alias token。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root279 - CEX detail snapshot repository 仍用 `CexToken/binance` 默认恢复 serving identity

发现：

- `CexDetailSnapshotRepository.upsert_snapshot(...)` 在写
  `cex_detail_snapshots` 时仍使用 `snapshot.get("target_type") or "CexToken"` 和
  `snapshot.get("exchange") or "binance"`。
- `_detail_payload_hash(...)` 使用同样的默认值参与 current-row payload hash。
- `CexOiRadarBoardWorker` / builder 已经是 `cex_detail_snapshots` 的唯一 runtime writer，
  且 CEX domain 明确 detail snapshot 是 one current row per exchange/native market。
  因此 repository 继续补身份默认，会让 malformed writer output 看起来像合法 current row。

根因：

- 这里混淆了 builder 的产品假设和 repository 的 serving-row 身份边界。
  CEX domain 当前确实是 Binance/CexToken lane，但这个事实应该由 writer/builder 明确输出，
  不应该在 repository/hash 层被恢复。
- 成熟 Kappa/CQRS 的 current read model 写入边界必须先验证稳定身份，再计算 payload hash
  和执行 upsert。否则缺 `target_type` / `exchange` 的坏快照会被哈希成合法
  `CexToken/binance` 当前行，后续 `IS DISTINCT FROM` 只会证明兼容后的 payload 未变，而不是证明
  writer 输出正确。
- 这也削弱 PostgreSQL 最佳实践：current row 的主身份和唯一查询语义应该来自显式字段，
  而不是 SQL 参数构造时的 Python 默认值。默认值会把 schema/DTO 漂移藏进正常 upsert。

修复：

- 新增 `_required_snapshot_text(...)`，要求 `snapshot_id`、`target_type`、`target_id`、
  `exchange`、`native_market_id` 非空。
- `upsert_snapshot(...)` 在 SQL 参数构造前读取这些正式身份字段；缺失或空值抛出
  `cex_detail_snapshot_identity_required:<field>`，不会执行 SQL。
- `_detail_payload_hash(...)` 使用同一正式身份 helper，payload hash 不再对缺失
  `target_type` / `exchange` 做 `CexToken/binance` 兼容恢复。
- 新增单元测试覆盖 hash 和 upsert SQL 前失败；新增 CEX architecture guard 禁止默认值回流。

验证：

- Focused CEX detail identity 命令通过，`11 passed`。
- 残留扫描只在 architecture guard 的禁止字符串里命中旧默认 token。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root280 - CEX detail builder 仍会制造 `cex_token:unknown` 或静默跳过空 market

发现：

- Root279 已经让 `CexDetailSnapshotRepository` 要求正式 snapshot identity，但
  `build_cex_detail_snapshot(...)` 仍然在缺 `cex_token_id`、缺可用 `target_id`、缺
  `base_symbol` 时返回 `cex_token:unknown`。
- `CexOiRadarBoardWorker` 构建 detail snapshots 时还保留
  `if row.get("native_market_id")` 过滤，这会把缺 market identity 的坏行转换成
  “没有 detail 行可写”的成功发布路径。
- 这两个点都发生在 `cex_detail_snapshots` current read model 写入之前，repository
  再严格也只能挡住空字段，挡不住已经被 builder 伪造成非空的 product key。

根因：

- 上一层 builder 把“产品假设”和“身份修复”混在一起：Binance v1 lane 可以明确输出
  `exchange=binance`、`target_type=CexToken`，但不能把缺失目标身份补成
  `cex_token:unknown`，也不能让 worker 用过滤条件绕过失败。
- 成熟 Kappa/CQRS 的 current read model 身份必须在 payload 存在前就稳定且可解释：
  `native_market_id` 决定 one current row per exchange/native market，`target_id`
  决定 Token Case / Pulse 如何把 detail snapshot 关联到 CEX token。`cex_token:unknown`
  会把多个坏源行折叠到同一个假 token；静默跳过则会让 board 发布成功但 detail
  缺口没有 terminal/error 证据。
- PostgreSQL 角度看，这会污染唯一键和 `payload_hash` 语义：`IS DISTINCT FROM`
  只能证明伪身份下 payload 未变，不能证明写入身份正确；而跳过 detail 行会造成
  board/detail 事务表面成功、读侧却缺少可审计原因。

修复：

- `build_cex_detail_snapshot(...)` 先通过 `_required_symbol(row, "native_market_id")`
  要求非空 native market，再构造 `snapshot_id`。
- `_target_id(...)` 不再返回 `cex_token:unknown`；route-like `binance:<market>` 不能作为
  `CexToken` identity，缺可用 `cex_token_id` / 非 route `target_id` / `base_symbol`
  时抛出 `cex_detail_snapshot_identity_required:target_id`。
- `CexOiRadarBoardWorker` 不再用 `if row.get("native_market_id")` 静默过滤 detail
  snapshot；坏身份会进入同一失败/attempt 记录路径。
- 单元测试覆盖缺 native market、缺/unknown target identity、以及仍允许从稳定
  `base_symbol` 派生 `cex_token:<BASE>`；architecture guard 禁止旧 unknown/skip 路径。

验证：

- Focused CEX detail builder identity 命令通过，`6 passed`。
- CEX builder/worker/repository/architecture 小集合通过，`47 passed`。
- Targeted ruff 和 mypy 通过；残留扫描只在 architecture guard 的禁止字符串里命中旧
  unknown/skip token。`snapshot_id` f-string 保留，但其输入已经先经过 required
  native market 校验。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root281 - Binance OI row builder 对缺 `native_market_id` 的 universe route 静默跳过

发现：

- `build_binance_oi_radar_rows(...)` 先调用 `client.list_24h_tickers()` 和
  `client.list_funding_premium()`，随后在循环里用
  `str(route.get("native_market_id") or "").strip().upper()` 取 symbol。
- 当 symbol 为空时旧代码直接 `continue`。如果 selected universe 里有 malformed
  `price_feeds` route，这会减少 board row 数；极端情况下可以生成 `rows=[]`、
  `failed=0` 的“成功空板”输入。
- `CexOiRadarBoardWorker` 对 `built["failed"] == 0` 会走 success/partial 发布路径，
  所以这种数据契约错误可能清空/改变 `cex_oi_radar_rows`，而不是保留当前板并记录
  failed attempt。

根因：

- 这里把“provider 单 symbol 拉取失败”和“PostgreSQL universe route 身份坏了”混成同一类
  可跳过状态。前者可以进入 `failed_symbols` 并继续处理其他 symbol；后者说明当前
  read model 的稳定 product key 还没成立，不能开始 provider IO，更不能发布成功空板。
- 成熟 Kappa/CQRS 的顺序应该是：先从 PostgreSQL 读到正式 universe route identity，
  验证 selected work item 的 key，再调用外部 provider，最后写 current read model。
  旧代码把 provider IO 放在 route identity 验证之前，导致错误的事实/控制输入被包装成
  正常投影结果。
- PostgreSQL 最佳实践层面，`cex_oi_radar_rows` 的 row identity 是
  provider/exchange/period/target。缺 `native_market_id` 的 route 没有 target，
  不应通过 `payload_hash`/publication state 变成一个可比较的“空集合成功版本”。

修复：

- `build_binance_oi_radar_rows(...)` 先为 selected universe 构造
  `(route, _required_symbol(route, "native_market_id"))`，缺失时抛出
  `cex_oi_radar_identity_required:native_market_id`。
- selected routes 为空时直接返回空结果，不做 provider IO；selected routes 非空时，
  route identity 校验完成后才调用 Binance ticker/premium/OI provider。
- `CexOiRadarBoardWorker` 现有异常路径会记录 `latest_attempt_status=failed`，并保留已有
  current board/detail rows。
- 单元测试证明缺 native market 会在 provider IO 前失败；worker 测试证明 malformed
  universe route 不发布 board，只记录 failed attempt；architecture guard 禁止旧
  `if not symbol: continue` / native-market 默认表达式回流。

验证：

- Focused Binance OI route identity 命令通过，`3 passed`。
- CEX OI builder/worker/detail/repository/architecture 小集合通过，`53 passed`。
- Targeted ruff 和 mypy 通过；残留扫描只在 architecture guard 的禁止字符串里命中旧
  native-market skip/default token，生产代码剩余 `continue` 仅属于单 symbol provider-history
  失败分支。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root282 - CEX board payload hash 把 computed fallback 时间当成内容签名

发现：

- `build_binance_oi_radar_rows(...)` 在 Binance OI history 没有 provider
  `observed_at_ms` 时，会把 worker `now_ms` 写入 row 的 `observed_at_ms`，并标记
  `observed_at_source="computed"`。
- `CexOiRadarRepository._board_payload_hash(...)` 仍把传入的
  `source_frontier_ms` 和每行 `row.get("observed_at_ms")` 放入 board payload hash。
  因此同一批 Binance 数值未变，只要 worker 下一轮运行时间变了，hash 就会变。
- 成功空板也有同类问题：`rows=[]` 时 `source_frontier_ms` 来自本轮
  `computed_at_ms`，所以合法空 current board 会在每次成功尝试时得到不同 hash。

根因：

- 旧实现没有区分“provider 事实时间”和“projection/attempt 运行时间”。成熟
  Kappa/CQRS 的 current read model 内容签名只能描述可服务内容本身；`computed_at_ms`
  或 provider 缺时间时的 computed fallback 只能描述投影尝试状态。
- 这会直接破坏“unchanged projections write zero serving rows”：`payload_hash`
  每轮变化后，repository 会进入 delete/upsert 路径，即使市场内容没有变化。PostgreSQL
  层面会带来无意义 WAL、索引更新、autovacuum 压力和 publication state 抖动；业务层面则会让
  operator 误以为 CEX board 内容在持续更新。
- Root279-281 已经解决了 CEX identity 伪造/跳过问题；本轮补上的是 current-row
  生命周期问题：身份正确也不够，内容签名还必须排除 run/attempt/timestamp 身份。

修复：

- `_source_frontier_ms(...)` 只从 provider-observed row 取最大 source frontier；没有
  provider 时间时仍可把 publication state 的 frontier 记录为 attempt 时间，但它不再参与
  content hash。
- `_board_payload_hash(...)` 使用 `_provider_observed_at_ms(row)` 生成 row payload；
  `observed_at_source="computed"` 的 fallback 时间在 hash 中视为 `None`。
- 新增 `_board_hash_source_frontier_ms(...)`：有 provider 时间时使用 provider frontier；
  computed-only rows 或成功空 board 在 hash 中使用 `None`，保证同内容重复投影写零 serving rows。
- 新增单元测试覆盖 computed fallback 时间变化和成功空板 attempt 时间变化；architecture guard
  禁止直接把 `row.get("observed_at_ms")` 放回 board hash。

验证：

- RED：`uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_ignores_computed_fallback_observed_timestamps tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_publish_board_skips_serving_row_writes_when_only_computed_observed_time_changes -q`
  初始失败，`2 failed`。
- RED：`uv run pytest tests/architecture/test_cex_oi_kappa_contract.py::test_cex_oi_board_payload_hash_ignores_computed_runtime_timestamps -q`
  初始失败，`1 failed`。
- GREEN：focused CEX board hash 命令通过，`4 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root283 - CEX board repository 仍允许空 period/target/native market 进入 current row identity

发现：

- Root279-282 已经收紧了 CEX detail identity、Binance universe route identity
  和 board content hash，但 `CexOiRadarRepository.publish_board_with_result(...)`
  仍用 `str(period)` 构造 board period，并用
  `_row_id(board_period, str(row["target_id"]))` 构造 serving row id。
- `_board_payload_hash(...)` / `_board_row_payload(...)` 仍直接读取
  `row["target_id"]` 和 `row["native_market_id"]`。空字符串不会触发
  PostgreSQL `NOT NULL`，会变成稳定但无业务含义的 board key / row id /
  payload hash。
- `record_attempt_failure(...)` 和 skipped/failed attempt-state 更新也会把空
  period 写成 `binance:USDT:PERPETUAL:` 这种合法文本 key。

根因：

- 这是 repository 边界缺失，不是 provider 层数据偶发脏值。成熟 Kappa/CQRS
  要求 current read model 的 product/window key 在 payload 生成前成立：
  `period` 决定 board 窗口，`target_id` 决定 serving row 的产品身份，
  `native_market_id` 决定 CEX market 可解释性。任何一个为空，都不是“空数据”，
  而是 current identity 不存在。
- PostgreSQL 最佳实践上，`TEXT NOT NULL` 只能阻止 NULL，不能阻止 `''`。
  如果应用层把空字符串哈希进 row id，数据库会非常高效地保存一个错误主键；
  后续 `ON CONFLICT`、`IS DISTINCT FROM`、payload hash 和 publication state
  都只能证明这个伪 key 的内容是否变化，不能证明 key 本身是正确产品。
- 这类错误会绕过单 writer 的表面安全：即使只有 `CexOiRadarBoardWorker`
  写表，只要 repository 接受伪身份，重放和 catch-up 仍会稳定地产生错误 current
  rows。单 writer 是必要条件，形式身份校验才是 current read model 的入口条件。

修复：

- 新增 `_required_board_text(...)` / `_required_board_row_text(...)`，在 board
  key、row id、payload hash、upsert 参数和 attempt-state period 写入前要求
  `period`、`target_id`、`native_market_id` 非空。
- `_row_id(...)` 自身也做防御性校验，避免未来直接调用时恢复空 target hash。
- 单元测试覆盖空 period、空 target/native market 在 SQL 前失败，以及 payload
  hash 不再接受空 current identity；architecture guard 禁止旧
  `str(period)` / `str(row["target_id"])` / direct row identity 形态。

验证：

- RED：focused CEX board identity 命令初始失败，`7 failed`。
- GREEN：同一 focused 命令通过，`7 passed`。
- CEX builder/worker/repository/architecture 小集合通过，`79 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root284 - CEX derivative series 对重叠历史点无条件冲突更新

发现：

- `CexDerivativeSeriesRepository.upsert_open_interest_points(...)` 给
  `cex_derivative_series` 写 open-interest history point 时，使用
  `ON CONFLICT(series_id) DO UPDATE SET ...`，但没有 `WHERE` 条件。
- Binance OI history 拉取天然会和上一轮 poll 重叠。即使同一个
  `series_id` 的 `value_numeric`、`value_usd`、`raw_payload_json` 完全未变，
  PostgreSQL 也会执行一次 UPDATE。
- 旧实现还在 Python 侧固定 `written += 1`，所以 replay 的 unchanged conflict
  row 会被报告成“写入成功”，掩盖 SQL 写放大。

根因：

- 这里不是数据库性能神秘变差，而是应用层把“幂等 replay”实现成了“每次都更新”。
  成熟 Kappa/CQRS 里 provider history overlap 是正常现象；重复看到同一个历史点时，
  正确行为应该是 no-op，而不是产生新的 WAL、索引版本和 autovacuum 压力。
- PostgreSQL 的 `ON CONFLICT DO UPDATE` 如果不加 `WHERE`，即使值相同也会形成行版本。
  对高频 worker 来说，这会把 provider 轮询频率转化为存储 churn，而不是只在事实变化时写入。
- `written += 1` 又进一步让运行指标失真：operator 看到的是“每轮都有写入”，但这些写入
  可能只是相同历史点被重复覆盖。SQL rowcount 才是这类 upsert 的真实写入证据。

修复：

- `cex_derivative_series` open-interest upsert 的 conflict branch 增加：
  `value_numeric IS DISTINCT FROM excluded.value_numeric`、
  `value_usd IS DISTINCT FROM excluded.value_usd`、
  `raw_payload_json IS DISTINCT FROM excluded.raw_payload_json`。
- 新增 `_cursor_rowcount(...)`，用数据库 cursor rowcount 累计实际 insert/update 数；
  unchanged conflict rows 返回 0。
- 单元测试证明 rowcount=0 时 repository 返回 `written == 0`；architecture guard
  禁止 `written += 1` 并要求冲突更新带 `IS DISTINCT FROM`。

验证：

- RED：focused CEX derivative-series 命令初始失败，`2 failed`。
- GREEN：同一 focused 命令通过，`2 passed`。
- CEX builder/worker/repository/architecture 小集合通过，`81 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root285 - CEX derivative series 仍允许空身份段进入 series hash 和 PostgreSQL 唯一键

发现：

- Root284 修掉了 `cex_derivative_series` 的重叠历史点写放大，但
  `_series_id(...)` 仍直接对 `provider`、`native_market_id`、`metric`、
  `period` 做 `strip()` / case normalization 后参与 hash。
- `upsert_open_interest_points(...)` 也把原始 `provider`、`exchange`、
  `native_market_id`、`period` 传入 SQL 参数。空字符串不会触发
  PostgreSQL `TEXT NOT NULL`，但会通过唯一索引
  `(provider, native_market_id, metric, period, observed_at_ms)` 成为稳定业务键。
- 结果是坏身份并不会表现成短暂异常，而会变成可重放、可冲突更新、可被运维指标误读的
  durable history row。

根因：

- 这是典型的“稳定但非法 identity”问题。Kappa/CQRS 的事实/历史表可以是 append/history，
  但业务键仍必须在写入前成立；历史表不是 current row，不代表可以把空 provider 或空 market
  当作合法维度。
- PostgreSQL 最佳实践上，`NOT NULL` 只表达“存在一个文本值”，不表达“这个文本是可解释的产品身份”。
  如果应用层把空字符串 hash 成 `series_id`，数据库会高效地维护这个伪键，并且后续
  `ON CONFLICT`、rowcount、`IS DISTINCT FROM` 都只能围绕伪键保持一致，不能恢复真实 identity。
- 由于 `series_id` hash 和唯一业务键都由这些字段组成，hash 输入与 SQL 参数必须共用同一套
  required-normalized 边界；否则会出现 hash 看似规范化、SQL 维度仍为空或带空格的分叉。

修复：

- 新增 `_required_series_text(...)`，在 `series_id` hash 和 upsert SQL 前要求
  `provider`、`exchange`、`native_market_id`、`metric`、`period` 非空。
- `upsert_open_interest_points(...)` 在 repository 边界生成规范化的
  `series_provider` / `series_exchange` / `series_native_market_id` / `series_period`，
  并将同一组规范值用于 hash 和 SQL 参数。
- 单元测试覆盖空 provider/exchange/native_market_id/period 在 SQL 前失败，以及
  `_series_id(...)` 不再接受空 hash 段；architecture guard 禁止恢复直接
  `provider.strip().lower()` 等兼容形态。

验证：

- RED：focused CEX derivative-series identity 命令初始失败，`9 failed`。
- GREEN：同一 focused 命令通过，`9 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root286 - CEX detail snapshot builder 仍用 builder-local Binance fallback 恢复 exchange 身份

发现：

- Root279-280 已经要求 `cex_detail_snapshots` repository 和 builder 在 current snapshot
  identity 成立前失败，但 `build_cex_detail_snapshot(...)` 仍在输出里使用
  `row.get("exchange") or "binance"`，同时把 `snapshot_id` 和 market source ref 写死成
  `cex-detail:binance:...` / `market:cex:binance:...`。
- `CexOiRadarBoardWorker` 是 Binance worker 这件事是真实 runtime 事实，但旧实现没有把
  exchange 作为 worker/provider 输入传给 builder，而是让 builder 自己恢复缺失 exchange。
- 这会让缺失 exchange 的 writer row 看起来拥有完整 `cex_detail_snapshots` serving identity，
  并把 source refs / payload hash 绑定到 builder-local 默认值。

根因：

- 这是 CQRS 投影边界的 ownership 混乱：exchange 属于 writer/provider 维度，而不是 builder 的
  兼容默认。成熟 Kappa/CQRS 要求 current read model 的 product identity 在 projection 输入处
  明确，builder 只做 deterministic projection，不替缺失身份补业务事实。
- PostgreSQL repository 层已经能拒绝空 `exchange`，但如果 builder 在上游恢复为 `binance`，
  repository 看到的是完整字段，无法区分“worker 明确声明 Binance”和“builder 为缺失字段兜底”。
- 这种 fallback 的危险在于它不一定导致重复行，而是导致错误行稳定且幂等：payload hash、source refs、
  snapshot_id 都会一致地指向 `binance`，从而把兼容默认伪装成正式事实。

修复：

- `build_cex_detail_snapshot(...)` 新增必需参数 `exchange`，并用 `_required_text(exchange, "exchange")`
  在 snapshot identity 构造前校验。
- `snapshot_id`、`exchange` 字段和 `market:cex:<exchange>:...` source ref 统一使用同一个
  normalized `snapshot_exchange`；builder 不再读取 `row.get("exchange") or "binance"`。
- `CexOiRadarBoardWorker` 在调用 detail builder 时显式传入 `exchange="binance"`，让单 runtime writer
  持有 Binance provider/exchange identity。
- 单元测试覆盖空 exchange 在 snapshot identity 前失败，以及非 Binance exchange 不再被硬编码 source refs
  覆盖；architecture guard 禁止恢复 hardcoded Binance snapshot id/source ref 和 builder-local exchange fallback。

验证：

- RED：focused CEX detail builder exchange 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- CEX builder/worker/repository/architecture 小集合通过，`92 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root287 - Token Case missing CEX detail block 仍合成 Binance snapshot identity

发现：

- `TokenCaseService._cex_detail(...)` 已经要求 `cex_detail_snapshots.latest_snapshot(...)`
  repository 合同存在；当 persisted snapshot 缺失时，它会返回结构化 missing block。
- 但旧 missing block 仍根据 target 的 `native_market_id` 合成
  `snapshot_id="cex-detail:binance:<native_market_id>"`，并用
  `target.get("provider") or "binance"` 填充 `exchange`。
- 这没有写 PostgreSQL，但会把“没有 read-model row”展示成“存在一个 Binance snapshot identity
  只是状态 missing”，污染 public read payload 的事实边界。

根因：

- 这是读侧 CQRS 语义污染：missing block 可以携带 target/native-market 上下文，帮助 UI 解释缺失；
  但 `snapshot_id` 和 `exchange` 是 `cex_detail_snapshots` projection row 的身份字段，只能来自
  persisted row。
- 如果 read service 在缺失时合成这些字段，前端、Search Inspect、Pulse 或后续调试会无法区分：
  “DB 有一条 missing snapshot row” 与 “DB 没有 snapshot row，service 临时造了一个 id”。
- 这类错误不产生 SQL 写放大，却会削弱 Kappa/CQRS 的可审计性：read path 开始修饰缺失事实，
  让 operator 看到一个并不存在的 projection identity。

修复：

- Token Case missing CEX detail block 现在返回 `snapshot_id: None`、`exchange: None`。
- 保留 `target_type`、`target_id`、`native_market_id`、symbol/quote 和
  `degraded_reasons=["cex_detail_snapshot_missing"]`，用于诚实展示缺失状态。
- 单元测试覆盖 missing block 不再合成 snapshot identity；architecture guard 禁止恢复
  `cex-detail:binance` 和 `provider or "binance"` 读侧 fallback。

验证：

- RED：focused Token Case CEX detail missing 命令初始失败，`2 failed`。
- GREEN：同一 focused 命令通过，`2 passed`。
- Token Case/Search Inspect/read-path architecture 小集合通过，`43 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root288 - CEX detail repository 读方法允许空 query identity 进入 SQL

发现：

- `CexDetailSnapshotRepository.latest_snapshot(...)` 直接把 `target_type` / `target_id`
  作为 SQL 参数传入。
- `latest_snapshot_by_market(...)` 直接执行 `exchange.lower()` 和 `native_market_id.upper()`，
  然后查询 `cex_detail_snapshots`。
- 如果直接调用方传入空字符串，repository 不会报 malformed query identity，而是对
  `target_id=''` 或 `native_market_id=''` 发起 PostgreSQL lookup，最后表现为“没查到 row”。

根因：

- 这是后端读代码的 query-boundary 缺失。成熟 CQRS 读路径可以返回“没有 read model row”，
  但前提是查询 key 本身是正式产品身份；空 query key 不是 cache miss，而是调用合同错误。
- PostgreSQL 最佳实践上，`WHERE target_id = '' LIMIT 1` 成本可能很小，但它会把 malformed
  caller state 伪装成正常 miss，削弱问题定位，并让 API/Token Case/Search Inspect 等读路径在
  不同层各自补救。
- 读 repository 是最靠近 SQL 的稳定边界，应统一负责 query identity 校验；否则每个 public
  route 都可能保留一套隐式空字符串行为。

修复：

- 新增 `_required_query_text(...)`，`latest_snapshot(...)` 在 SQL 前要求非空
  `target_type` / `target_id`。
- `latest_snapshot_by_market(...)` 在 SQL 前要求非空 `exchange` / `native_market_id`，
  并只使用通过校验后的 normalized lower/upper values。
- 单元测试覆盖四个空查询字段在 SQL 前失败；architecture guard 禁止恢复直接 SQL 参数 tuple
  和 `exchange.lower()` / `native_market_id.upper()` 直传形态。

验证：

- RED：focused CEX detail query identity 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`5 passed`。
- CEX builder/worker/repository/architecture 小集合通过，`96 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root289 - `/api/cex/detail` 仍把半截查询身份当成空结果

发现：

- Root288 已经让 `CexDetailSnapshotRepository` 在 SQL 前拒绝空 query identity，但
  `/api/cex/detail` 路由层仍然用 `if target_type and target_id` / `elif symbol` 做
  truthy 分支。
- 只传 `target_type=CexToken` 而不传 `target_id` 时，旧路由不会报 malformed query，
  而是返回 `{"ok": true, "data": null}`。
- 传 `symbol=BTCUSDT&exchange= ` 时，旧路由会把空 exchange 传给 repository；真实
  repository 严格化后这类请求可能变成 500，测试 fake 则会继续把它伪装成正常读。

根因：

- 这是 public API read surface 的查询模式身份没有 formalize。成熟 CQRS 里，public
  route 可以拥有默认值和用户输入校验，但不能把“调用者给了半截 key”解释成“合法 key
  查询不到 row”。
- Repository 边界能防止空 key 进入 SQL，但路由层仍要区分三种状态：没有发起 detail 查询、
  用完整 target key 查询但没有 snapshot、以及查询 key 本身不完整。把后两者都折叠成
  `data:null` 会让 operator 和前端无法判断是产品缺数据还是请求/调用合同错误。
- PostgreSQL 最佳实践层面，这不是缺索引问题，而是不要让 DB lookup 承担输入语义判断；
  否则每一层都可能保留自己的空字符串/None 兼容路径。

修复：

- `/api/cex/detail` 新增 `_cex_detail_target_query(...)` 和
  `_cex_detail_market_query(...)`，在进入 repository 前形成正式查询身份。
- partial target query 返回 `ApiBadRequest("invalid_cex_detail_query", field=...)`；
  market query 中空 `symbol` 或空 `exchange` 同样在路由层 400。
- 路由仍允许无查询参数返回 `data:null`，这代表“未请求具体 detail”，不再和半截 target
  identity 混在一起。
- 单元测试使用 FastAPI `TestClient` 覆盖 400 和“不碰 repository”；architecture guard
  禁止恢复 truthy 分支和原始参数直传 repository。

验证：

- RED：`uv run pytest tests/unit/test_api_cex_contract.py -q` 初始失败，`2 failed`。
- GREEN：同一单元测试通过，`2 passed`。
- CEX API + API read-path architecture 小集合通过，`26 passed`。
- Targeted ruff 和 `routes_cex.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root290 - `/api/cex/detail` 允许 target 与 market 双查询模式静默择一

发现：

- Root289 让 `/api/cex/detail` 拒绝 partial target key 和空 market key，但完整
  `target_type/target_id` 与完整 `symbol/exchange` 可以同时出现。
- 旧路由会优先走 target lookup，静默忽略 market lookup。比如 `target_id=cex_token:ETH`
  与 `symbol=BTCUSDT` 同时传入时，API 返回 ETH target 查询结果，而不是暴露请求歧义。

根因：

- 这是查询 identity 从“非空”走向“唯一明确”时漏掉的一层。成熟 CQRS 读 API 不仅要保证
  key 可查询，还要保证一次请求只有一个明确 lookup mode；否则调用方可以把两个互相矛盾的
  product keys 塞进同一个 read path，后端用分支优先级替调用方做隐式选择。
- 这种兼容行为不直接制造 SQL 性能问题，但会制造诊断盲区：operator 看到的是合法 snapshot，
  实际请求却包含被丢弃的另一组身份，无法判断前端、CLI 或调用者到底想读哪个 projection row。
- PostgreSQL/read-model 边界已经严格后，API surface 也必须停止保留“多给参数也能用”的宽松兼容。

修复：

- `/api/cex/detail` 在形成 `target_query` 和 `market_query` 后，如果两者同时存在，
  在打开 repository session 前返回 `invalid_cex_detail_query`，`field="query"`。
- 单元测试覆盖双模式查询 400 且不碰 repository；architecture guard 要求互斥错误发生在
  `runtime.repositories()` 之前。

验证：

- RED：`uv run pytest tests/unit/test_api_cex_contract.py -q` 初始失败，新增用例 `1 failed`。
- GREEN：同一单元测试通过，`3 passed`。
- CEX API + API read-path architecture 小集合通过，`27 passed`。
- Targeted ruff 和 `routes_cex.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root291 - CEX detail snapshot 仍把缺失 quote_symbol 恢复成 USDT

发现：

- `build_cex_detail_snapshot(...)` 在构造当前 detail snapshot 时使用
  `_symbol(row.get("quote_symbol")) or "USDT"`。
- `CexDetailSnapshotRepository.upsert_snapshot(...)` 和 `_detail_payload_hash(...)` 也使用
  `snapshot.get("quote_symbol") or "USDT"`。
- 这意味着上游 writer row 或测试 fake 缺少 quote 时，系统不会暴露 malformed market
  identity/content，而是写出看似完整的 USDT 永续 detail row。

根因：

- 这是 CEX detail current row 的内容身份被默认值修复。虽然当前 v1 worker 只发布 Binance
  USDT perpetual，但这个事实应来自 `price_feeds` universe row 和 worker 输出，而不是 builder
  或 repository 在缺字段时自行恢复。
- PostgreSQL `TEXT NOT NULL` 不能拒绝空字符串；repository 如果继续用 `or "USDT"`，就会把
  “缺字段”变成稳定 payload hash 和 serving row，后续审计无法区分真实 USDT 合约与默认补值。
- 成熟 Kappa/CQRS 的做法是：provider/raw 输入可以被标准化，但进入 current read model 前，
  产品关键字段必须已经明确；缺 quote 是 writer/output contract 错，而不是 read model 的 partial
  状态。

修复：

- Builder 改为 `_required_symbol(row, "quote_symbol")`，缺 quote 时在 snapshot id/payload
  写入前失败。
- Repository 在 upsert SQL 参数和 `_detail_payload_hash(...)` 中都使用
  `_required_snapshot_text(snapshot, "quote_symbol")`。
- 单元测试覆盖 builder、payload hash、upsert SQL 前失败；architecture guard 禁止恢复
  `quote_symbol or "USDT"` 默认。

验证：

- RED：focused CEX detail quote-symbol 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`15 passed`；CEX detail builder/repository/architecture
  小集合通过，`48 passed`。
- 更宽 CEX 非集成套件通过，`99 passed`。
- Targeted ruff、mypy 和 quote 默认残余扫描通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root292 - CEX detail snapshot 仍允许空 base_symbol 写入当前行

发现：

- Root291 已经要求 `quote_symbol` 不能由 builder/repository 默认成 `USDT`，但
  `build_cex_detail_snapshot(...)` 仍先把 `base_symbol` 读取为可选 `_symbol(...)`，然后把它
  直接写入 snapshot。
- `CexDetailSnapshotRepository.upsert_snapshot(...)` 和 `_detail_payload_hash(...)` 仍使用
  `snapshot.get("base_symbol") or ""`。
- 如果上游 row 有正式 `cex_token_id`、`native_market_id` 和 `quote_symbol`，但缺
  `base_symbol`，旧代码会写出一个合法 snapshot id 和 target id，却让 serving row 的
  base symbol 为空。

根因：

- 这是“身份字段严格，展示/合约字段宽松”的另一层兼容。CEX detail 当前行不只是 lookup key；
  它也是 Token Case、CEX detail rail 和 Pulse evidence 读到的市场合约摘要。`base_symbol`
  为空会让目标身份看起来成立，但用户可见和 agent evidence 里的市场描述残缺。
- PostgreSQL `TEXT NOT NULL` 仍然挡不住空字符串；repository 用 `or ""` 会把 writer 输出缺陷
  变成稳定 payload hash。
- 成熟 Kappa/CQRS 里，builder 可以临时用可选 base 判断 route-like target 是否能派生 CEX token，
  但最终 current row 的 `base_symbol` 必须是正式 writer output，缺失应失败而不是落库。

修复：

- Builder 保留 `target_base_symbol` 作为 target 派生判断输入，但最终写出的 `base_symbol`
  改为 `_required_symbol(row, "base_symbol")`。
- Repository 在 upsert SQL 参数和 `_detail_payload_hash(...)` 中都使用
  `_required_snapshot_text(snapshot, "base_symbol")`。
- 单元测试覆盖 builder、payload hash、upsert SQL 前失败；architecture guard 禁止恢复
  `base_symbol or ""` 默认。

验证：

- RED：focused CEX detail base-symbol 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`17 passed`；CEX detail builder/repository/architecture
  小集合通过，`51 passed`。
- 更宽 CEX 非集成套件通过，`102 passed`。
- Targeted ruff 和 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root293 - Binance OI board 上游 route 仍把缺失 base_symbol 洗成空字符串

发现：

- `build_binance_oi_radar_rows(...)` 已经在 Binance provider IO 前要求
  selected universe route 的 `native_market_id` 非空，但仍用
  `str(route.get("base_symbol") or "").strip().upper()` 构造 board row。
- 结果是 malformed `price_feeds` universe row 可以先完成 Binance ticker/premium/OI
  provider 调用，再发布 `base_symbol=""` 的 board row；随后 detail builder 才因为
  Root292 的保护失败。
- 失败边界虽然最终会避免 detail snapshot 落库，但错误发生得太晚：provider IO 已经发生，
  board/detail 的原子发布路径也已经进入后半段。

根因：

- 这是身份合同在链路中“下游严格、上游宽松”的残留。成熟 Kappa/CQRS writer 应该在读取
  selected universe route 后、任何外部 IO 和 current-row 构造前验证完整产品市场身份。
- `base_symbol` 在 CEX board/detail 里不是装饰字段；它参与用户可见市场解释、CEX token
  target 语义和 detail snapshot 的后续构造。把缺失 base 洗成空字符串，会让 upstream board
  row 看起来成功，而真实合同错误被推迟到另一个 projection helper。
- PostgreSQL 最佳实践上，不能依赖 `TEXT NOT NULL` 或下游 repository 来识别空文本业务键；
  writer 边界应尽早拒绝 malformed route，避免无意义 provider IO、事务回滚成本和诊断噪音。

修复：

- Binance OI row builder 在 selected route 阶段同时要求
  `_required_symbol(route, "native_market_id")` 和
  `_required_symbol(route, "base_symbol")`。
- Board row 使用已验证的 `base_symbol`，删除 `or ""` 空字符串兼容。
- Worker 单元测试覆盖缺 base 的 universe route 通过 attempt-failure 路径记录失败且不发布
  board；architecture guard 禁止恢复 `base_symbol or ""` 并要求校验发生在 provider IO 前。

验证：

- RED：focused builder/worker 命令初始失败，`2 failed`；builder 没拦住，worker 到
  detail snapshot 才失败。
- GREEN：focused builder/worker/architecture 命令通过，`3 passed`。
- 更宽 CEX 非集成套件通过，`104 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root294 - CoinGlass enrichment 仍把缺失 base_symbol 当作 provider unavailable

发现：

- `enrich_row_with_coinglass(...)` 使用
  `str(row.get("base_symbol") or "").strip().upper()` 读取待 enrichment 的 board row。
- 缺 base 时旧代码返回 `coinglass_status="unavailable"` 和
  `coinglass_symbol_missing`，而不是暴露上游 writer row malformed。
- Root293 已经让 Binance builder 在 provider IO 前要求 route base，但 direct service
  caller 仍可绕过该边界，把坏 board row 交给 CoinGlass enrichment。

根因：

- 这是把“上游 row 身份缺失”误分类成“外部 provider 数据不可用”。成熟 Kappa/CQRS 的
  degraded/partial 状态应表达 provider 响应缺失、字段缺失或 enrichment 调用失败，不能用来掩盖
  current-row 输入合同缺失。
- 如果 enrichment service 继续把缺 base 降级为 unavailable，detail snapshot 会把
  CoinGlass 不可用和 writer 输出坏身份混在一起；operator 无法判断是 provider 没数据，还是
  `cex_oi_radar_rows` 自己已经不完整。
- PostgreSQL 最佳实践和 worker 事务语义都要求在外部 IO 前拒绝 malformed business key，
  而不是生成看似合法的 degraded payload。

修复：

- CoinGlass enrichment 改为 `_required_symbol(row, "base_symbol")`，缺 base 抛出
  `coinglass_detail_identity_required:base_symbol`。
- 删除 `coinglass_symbol_missing` 降级分支；provider 异常仍保留为 partial degraded reasons。
- 单元测试证明缺 base 在 provider 调用前失败；architecture guard 禁止恢复空字符串和
  `coinglass_symbol_missing`。

验证：

- RED：focused CoinGlass enrichment 命令初始失败，`2 failed`。
- GREEN：focused 单元/架构命令通过，`2 passed`。
- 更宽 CEX 非集成套件通过，`106 passed`。
- Targeted ruff、mypy 和 base-symbol residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root295 - CEX detail repository 仍为缺失状态字段补默认枚举

发现：

- `CexDetailSnapshotRepository.upsert_snapshot(...)` 在 SQL 参数里使用
  `snapshot.get("status") or "partial"`、
  `snapshot.get("baseline_status") or "missing"`、
  `snapshot.get("coinglass_status") or "unavailable"`。
- `_detail_payload_hash(...)` 也使用同样默认值，因此缺状态字段和显式 partial/missing/unavailable
  会得到相同 payload hash。
- 未知状态值也能穿过 fake repository 测试，依赖数据库层或后续消费者才可能暴露。

根因：

- 这是 repository 把 writer 输出合同和 projection 状态机混在一起。Builder/worker 可以根据
  baseline 与 CoinGlass enrichment 结果推导 ready/partial/missing/unavailable；repository 只应
  验证并持久化正式状态，不应重新解释缺字段。
- 成熟 Kappa/CQRS 的 current row hash 必须代表 writer 已经决定的产品状态。repository 默认值会让
  malformed writer output 与真实 degraded 状态不可区分，削弱零写入判断和 replay 审计。
- PostgreSQL `TEXT NOT NULL` 既不能拒绝空字符串，也不能表达枚举语义；至少在 repository SQL
  边界必须先做非空与枚举校验，避免坏状态进入 upsert/payload hash。

修复：

- 新增 `_required_snapshot_status(...)`，对 `status`、`baseline_status`、`coinglass_status`
  做非空和枚举校验。
- SQL upsert 参数和 `_detail_payload_hash(...)` 都改为使用同一个状态校验函数。
- 单元测试覆盖缺状态和未知状态在 payload hash / upsert SQL 前失败；architecture guard 禁止
  repository-local status 默认值。

验证：

- RED：focused detail repository status 命令初始失败，`13 failed`。
- GREEN：同一 focused 命令通过，`13 passed`。
- 更宽 CEX 非集成套件通过，`118 passed`。
- Targeted ruff、mypy 和 status 默认 residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root296 - CEX detail builder 仍把缺失 CoinGlass 状态补成 unavailable

发现：

- Root295 已经让 repository/hash 边界要求正式 `coinglass_status`，但
  `build_cex_detail_snapshot(...)` 仍用 `row.get("coinglass_status") or "unavailable"`。
- `enrich_rows_with_coinglass(...)` 在 `client is None`、`limit <= 0` 或 row 超出 enrichment
  top-K 时直接返回原 row，导致 detail builder 成为第二个状态默认层。
- 单元测试甚至显式断言 limit 外的 row 没有 `coinglass_status`。

根因：

- 这是 projection stage 责任不清：CoinGlass enrichment stage 才知道“未配置、未选中、调用失败、
  enrichment 成功”这些状态，detail builder 只应把已经形成的 board/enrichment row 转成 detail
  snapshot。
- 如果 builder 默认 unavailable，缺失 `coinglass_status` 和正式“没有 CoinGlass enrichment”的产品状态
  会混在一起，operator 无法判断是 stage 未执行、row malformed，还是正式 degraded。
- 成熟 Kappa/CQRS 的 read-model链路应当每一 stage 输出完整 contract；下游 stage 验证并转换，
  不再补上游缺字段。

修复：

- `enrich_rows_with_coinglass(...)` 对所有返回 row 显式写出 `coinglass_status`：成功为
  `ready`，异常为 `partial`，未配置/limit 外为 `unavailable`。
- `build_cex_detail_snapshot(...)` 改为 `_required_status(row, "coinglass_status")`，缺失或未知
  CoinGlass 状态在 snapshot 构造前失败。
- 单元测试覆盖无 client、limit 外、缺 status、未知 status；architecture guard 禁止 builder 默认
  unavailable。

验证：

- RED：focused enrichment/builder 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`5 passed`。
- 更宽 CEX 非集成套件通过，`121 passed`。
- Targeted ruff、mypy 和 CoinGlass status residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root297 - CEX board repository 仍允许空 base/quote symbol 写入当前行

发现：

- Root293 已经让 Binance OI builder 在 provider IO 前要求 route `base_symbol`，但
  `CexOiRadarRepository` 自己仍在 payload hash 中直接使用
  `row["base_symbol"]` / `row["quote_symbol"]`。
- Upsert SQL 参数也直接传 `row["base_symbol"]` / `row["quote_symbol"]`，因此 direct repository
  caller 或 malformed writer output 可以把空文本写入 `cex_oi_radar_rows`。
- PostgreSQL schema 只保证 `TEXT NOT NULL`，无法拒绝空字符串。

根因：

- 这是“上游 builder 严格、最终 serving repository 宽松”的边界错位。成熟 Kappa/CQRS 中，
  current read-model repository 必须是最后一道产品 row 合同边界；不能假设所有 direct caller
  都经过唯一 builder。
- `base_symbol` 和 `quote_symbol` 不只是展示字段。它们参与 CEX board 的市场解释、detail
  snapshot 构造和 agent evidence 语义。空 symbol 会形成稳定 payload hash，却不是合法市场合同。
- 依赖数据库非空约束不够；PostgreSQL 最佳实践是业务键/产品字段在 SQL 参数化前完成语义校验。

修复：

- `_board_row_payload(...)` 对 `base_symbol` 和 `quote_symbol` 使用
  `_required_board_row_text(...)`。
- `publish_board_with_result(...)` 在 upsert 参数化前同样验证 row `base_symbol` / `quote_symbol`。
- 单元测试覆盖 payload hash 和 upsert SQL 前失败；architecture guard 禁止直接读取
  `row["base_symbol"]` / `row["quote_symbol"]`。

验证：

- RED：focused CEX board symbol 命令初始失败，`5 failed, 5 passed`。
- GREEN：同一 focused 命令通过，`10 passed`。
- 更宽 CEX 非集成套件通过，`125 passed`。
- Targeted ruff、mypy 和 board symbol residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root298 - CEX detail builder 仍把缺失 period 降级成 unknown 业务原因

发现：

- `build_cex_detail_snapshot(...)` 已经从 worker 显式接收 `period`，但
  `_oi_delta_slots(...)` 仍用 `str(period or "").strip().lower()` 解析。
- 当 period 为空且 row 携带 `open_interest_change_pct_1h` 时，旧代码不会失败，而是写入
  `oi_change_period_unknown_not_1h` degraded reason。
- 这会把 worker/settings wiring 缺失伪装成一个正常的“非 1h OI delta”业务降级。

根因：

- 这是 control-plane 输入和业务状态混在一起的残留。`period` 是
  `CexOiRadarBoardWorker` 从 formal worker settings 读取的时间桶，决定 board row 的
  OI delta 语义；它不是 detail builder 可以本地补成 `unknown` 的展示字段。
- 成熟 Kappa/CQRS writer 在 current read-model 构造前必须先验证时间窗口/产品身份等写入
  维度。缺 period 说明 writer runtime contract 断了，而不是 provider 没数据或非 1h 窗口。
- PostgreSQL 最佳实践上，不能把缺失控制字段编码进 JSON degraded reason 后继续写 row；
  这会让 payload hash、重放审计和 operator 排障都失去根因边界。

修复：

- `build_cex_detail_snapshot(...)` 新增 `_required_period(period)`，在 snapshot 构造早期要求
  非空 period，并规范化后传给 OI delta slot 映射。
- `_oi_delta_slots(...)` 不再使用 `period or ""` 或 `unknown` fallback；有效但非 1h/4h/24h
  的 period 仍产生显式 `oi_change_period_<period>_not_1h` degraded reason，例如 `5m`。
- 单元测试覆盖空 period 在 OI delta 映射前失败；architecture guard 禁止恢复
  `str(period or "").strip().lower()` 和 `or "unknown"`。

验证：

- RED：focused detail period 命令初始失败，`2 failed`。
- GREEN：同一 focused 命令通过，`2 passed`。
- 更宽 CEX 非集成套件通过，`126 passed`。
- Targeted ruff、mypy 和 period/unknown residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root299 - CEX detail payload hash 仍接受旧 JSON column alias

发现：

- `CexDetailSnapshotRepository.upsert_snapshot(...)` 的 SQL 参数只写正式 writer 字段
  `level_bands`、`degraded_reasons`、`source_refs`。
- 但 `_detail_payload_hash(...)` 仍读取
  `snapshot.get("level_bands") or snapshot.get("level_bands_json")` 等旧 DB column alias。
- direct writer caller 如果传入 `level_bands_json` / `source_refs_json`，payload hash 会代表 alias
  内容，而 SQL 实际写入空 JSON；hash 与持久化行内容产生分叉。

根因：

- 这是 repository 把“DB read row 形状”和“writer snapshot 输入合同”混成了一个 payload
  hash 输入。`*_json` 是 PostgreSQL column 命名和 `_public_snapshot(...)` 读回映射的内部形状，
  不是 `upsert_snapshot(...)` 的 writer contract。
- 成熟 Kappa/CQRS 的 current-row payload hash 必须只描述即将写入 serving row 的正式 payload。
  允许旧 alias 参与 hash，会让 unchanged projection 判断、replay 审计和 `IS DISTINCT FROM`
  gating 都建立在一份没有实际落库的内容上。
- PostgreSQL 最佳实践上，JSONB column name 与应用层 writer DTO 应保持单向映射：读路径可以把
  `level_bands_json` 转回 `level_bands`，写路径不能接受两套字段名。

修复：

- `_detail_payload_hash(...)` 新增 `_reject_legacy_json_aliases(snapshot)`，遇到
  `level_bands_json`、`degraded_reasons_json`、`source_refs_json` 直接失败。
- payload hash 的 list/source-ref 输入只读取正式 `level_bands`、`degraded_reasons`、`source_refs`。
- 单元测试覆盖 payload hash 和 upsert SQL 前失败；architecture guard 禁止恢复旧 alias fallback。

验证：

- RED：focused detail JSON alias 命令初始失败，`7 failed`。
- GREEN：同一 focused 命令通过，`7 passed`。
- 更宽 CEX 非集成套件通过，`132 passed`。
- Targeted ruff、mypy 和 alias residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root300 - CEX detail builder 仍接受旧 level_bands_json 输入形状

发现：

- Root299 已经让 repository payload hash 拒绝旧 `*_json` alias，但
  `build_cex_detail_snapshot(...)` 仍使用
  `row.get("level_bands") or row.get("level_bands_json")`。
- 因此 direct builder caller 可以把 DB 读行/旧 DTO 形状重新喂进 writer builder，builder 会把
  `level_bands_json` 洗成正式 `level_bands` snapshot 输出。
- 这不是 provider 缺数据，而是 writer 输入边界仍保留旧字段名兼容。

根因：

- 这是“repository 已严格、builder 仍兼容”的同类边界错位。`level_bands_json` 是 PostgreSQL
  column/read-row 映射形状；CEX detail builder 的输入应该来自 board/enrichment stage，字段名为
  `level_bands`。
- 成熟 Kappa/CQRS stage 之间应传递一个正式 DTO 形状。允许 builder 接受 DB column alias，会把
  read-model storage detail 反向泄漏到 writer pipeline，削弱 stage ownership 和回放可解释性。
- PostgreSQL 最佳实践上，JSONB column 后缀属于表结构，不应成为 domain service 的兼容输入。

修复：

- `build_cex_detail_snapshot(...)` 新增 `_reject_legacy_json_aliases(row)`，遇到
  `level_bands_json` 直接抛出 `cex_detail_snapshot_legacy_json_alias:level_bands_json`。
- Builder 只从正式 `level_bands` 读取 liquidation level bands。
- 单元测试覆盖旧 alias 在 snapshot 构造前失败；architecture guard 禁止恢复
  `row.get("level_bands") or row.get("level_bands_json")`。

验证：

- RED：focused detail builder level-bands alias 命令初始失败，`2 failed`。
- GREEN：同一 focused 命令通过，`2 passed`。
- 更宽 CEX 非集成套件通过，`133 passed`。
- Targeted ruff、mypy 和 fallback residual scan 通过；生产中只剩显式拒绝常量/错误路径。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root301 - CEX board repository 仍把缺失 observed_at_source 当作 provider freshness

发现：

- `CexOiRadarRepository` 的 board payload hash 通过 `_provider_observed_at_ms(row)` 决定哪些
  `observed_at_ms` 进入 content signature。
- 旧代码在 `observed_at_source` 缺失或未知时，既不失败也不视为 computed，而是返回
  `int(observed_at_ms)`，等价于把它当 provider-observed freshness。
- Upsert SQL 还用 `int(row.get("observed_at_ms") or computed_at)`，缺时间戳时把 runtime
  attempt 时间写进 current row。

根因：

- 这是观测时间的事实来源没有形成正式 tuple 合同。Binance builder 已经输出
  `observed_at_ms` 与 `observed_at_source=provider|computed`，repository 作为最终 current-row
  边界却还允许 direct caller 省略来源。
- 成熟 Kappa/CQRS 的 payload hash 必须只包含真实 provider freshness；computed fallback 是
  attempt/publication metadata，不能因 source 缺失而混入 content signature。
- PostgreSQL 最佳实践上，不能用 `or computed_at` 补 current-row 事实字段；这会让 replay
  或 direct writer 调用把运行时间写成市场观测时间，造成不必要的 `IS DISTINCT FROM` 更新和
  WAL churn。

修复：

- CEX board repository 新增 `_required_observed_at_ms(row)` 和
  `_required_observed_at_source(row)`。
- `observed_at_source` 只允许 `provider` 或 `computed`；缺失或未知在 payload hash/SQL 前失败。
- Upsert SQL 写入的 `observed_at_ms` 来自正式 row 字段，不再用 `computed_at` 兜底。
- 单元测试覆盖缺/非法 observation tuple 在 hash 与 SQL 前失败；architecture guard 禁止恢复旧
  `observed_at_ms or computed_at` 和缺 source fallback。

验证：

- RED：focused board observation 命令初始失败，`7 failed`。
- GREEN：同一 focused 命令通过，`7 passed`。
- 更宽 CEX 非集成套件通过，`139 passed`。
- Targeted ruff、mypy 和 observation fallback residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root302 - CEX board repository 仍把缺失 score_components 补成空对象

发现：

- `CexOiRadarRepository` 在 upsert SQL 中使用 `Jsonb(row.get("score_components") or {})`。
- `_board_row_payload(...)` 同样使用 `"score_components": row.get("score_components") or {}`。
- 这会让“scoring stage 没有输出 components”和“scoring stage 明确输出空 components”得到同一个
  payload hash 和同一份 serving row。

根因：

- `score_components` 是 `score_oi_radar_row(...)` 的正式输出，用于解释 CEX board rank/score；
  repository 不应该重新定义缺失 components 的语义。
- 成熟 Kappa/CQRS current-row hash 应描述 writer 已决定的 scoring payload。缺失 scoring
  explanation 是 malformed writer output，不是空 explainability payload。
- PostgreSQL JSONB 最佳实践上，空对象可以是合法业务值，但不能被用作 missing field 的隐式默认；
  否则 hash gate 和审计无法区分 pipeline 漏字段与真实空对象。

修复：

- 新增 `_required_score_components(row)`，要求 `score_components` 存在且是 mapping。
- Upsert SQL Jsonb 参数和 `_board_row_payload(...)` payload hash 都使用同一个验证函数。
- 非字符串 key 仍由 `stable_current_payload_hash(...)` 的现有结构校验捕获。

验证：

- RED：focused board score-components 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`5 passed`。
- 更宽 CEX 非集成套件通过，`143 passed`。
- Targeted ruff、mypy 和 score-components residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root303 - CEX detail builder 仍根据时间戳猜 observed_at_source

发现：

- Root301 已经让 board repository 要求 `observed_at_ms` / `observed_at_source` tuple，但
  `build_cex_detail_snapshot(...)` 仍在 `_observed_at_source(...)` 中用缺失 source + 时间戳等于
  `computed_at_ms` 来推断 `computed`，否则推断 `provider`。
- Direct builder caller 可以省略 source，让 detail snapshot 自行猜测事实来源。
- 这会让 board 与 detail 对同一 market observation 的 freshness 语义不一致。

根因：

- 这是 stage 间合同不一致：board/enrichment row 已经应该携带 observation tuple，detail builder
  不应该重新解释或恢复缺失 source。
- 成熟 Kappa/CQRS 的 read-model stage 只能转换正式输入，不能用运行时间相等性来推导事实来源；
  timestamp equality 是脆弱实现细节，不是业务合同。
- PostgreSQL 最佳实践上，source/freshness 语义应在进入 payload hash/source refs 前显式校验，
  否则 provider freshness 和 computed metadata 会在 replay 时互相污染。

修复：

- `build_cex_detail_snapshot(...)` 改为 `_required_observed_at_ms(row)` 和
  `_required_observed_at_source(row)`。
- `observed_at_source` 只允许 `provider` 或 `computed`；缺失/未知 source 和缺时间戳都在
  snapshot 构造前失败。
- 删除 detail builder 的 timestamp-equality source 推断路径；单元和 architecture guard 覆盖。

验证：

- RED：focused detail observation 命令初始失败，`4 failed`。
- GREEN：同一 focused 命令通过，`4 passed`。
- 更宽 CEX 非集成套件通过，`146 passed`。
- Targeted ruff、mypy 和 detail observation residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root304 - CEX detail repository payload hash 仍推断 observed_at_source

发现：

- Root303 已经让 detail builder 要求 observation tuple，但
  `CexDetailSnapshotRepository._provider_observed_at_ms(...)` 仍在 payload hash 边界兼容缺失
  `observed_at_source`。
- 旧代码先读取 `source = str(snapshot.get("observed_at_source") or "").strip().lower()`，如果不是
  `provider/computed`，再用 `observed_at_ms == computed_at_ms` 推断 computed，否则把 timestamp
  当 provider freshness。
- Direct repository caller 因此仍可让 detail payload hash 猜测 freshness 来源。

根因：

- 这是 repository hash 边界仍保留 read/write stage 之前的推断逻辑。Builder 可以根据正式 row
  输出 detail snapshot；repository 只能验证和持久化，不能重新解释缺失 source。
- 成熟 Kappa/CQRS 的 hash gate 要基于 writer 输出合同，不能基于 runtime timestamp equality。
  否则 replay 中相同业务 payload 会因 computed time 或 source 缺失被错误纳入/排除 hash。
- PostgreSQL `IS DISTINCT FROM` gating 只有在 payload hash 与持久化事实一致时才有效；source
  推断会让 hash 变成“猜出来的 freshness”，降低可审计性。

修复：

- `_provider_observed_at_ms(snapshot)` 在 `observed_at_ms` 存在时必须调用
  `_required_observed_at_source(snapshot)`。
- `observed_at_source` 只允许 `provider` 或 `computed`；缺失或未知 source 在 payload hash /
  upsert SQL 前失败。
- 删除 detail repository 的 timestamp-equality source 推断路径。

验证：

- RED：focused detail repository observation 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`5 passed`。
- 更宽 CEX 非集成套件通过，`150 passed`。
- Targeted ruff、mypy 和 detail repository observation residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root305 - CEX detail repository 仍把缺失 JSON list 字段补成空列表

发现：

- `CexDetailSnapshotRepository.upsert_snapshot(...)` 使用
  `Jsonb(list(snapshot.get("level_bands") or []))`、`degraded_reasons`、`source_refs`
  同类默认。
- `_detail_payload_hash(...)` 也会把缺失或非 list payload 通过 `_list_payload(...)` 折成空列表。
- 因此 malformed writer output 缺少 list 字段时，会和正式空 list 得到同一个 hash 与 SQL payload。

根因：

- 空 list 是合法业务值，但 missing field 是 writer DTO 不完整。repository 不能把这两个状态合并。
- 成熟 Kappa/CQRS current-row hash 要描述 writer 输出的正式 shape；如果 hash/SQL 边界补空列表，
  replay 审计无法判断是 stage 明确输出“无 levels/无 degraded reasons/无 source refs”，还是 stage
  漏字段。
- PostgreSQL JSONB 最佳实践上，list payload 应在 SQL 参数化前做类型/存在性校验，而不是依赖
  `Jsonb([])` 兜底。

修复：

- 新增 `_required_snapshot_list(snapshot, field)`，要求 `level_bands`、`degraded_reasons`、
  `source_refs` 存在且为 list/tuple。
- Upsert SQL 和 payload hash 都使用同一个 list 字段校验函数。
- 删除不再需要的 `_list_payload(...)` 兼容 helper。

验证：

- RED：focused detail list-payload 命令初始失败，`13 failed`。
- GREEN：同一 focused 命令通过，`13 passed`。
- 更宽 CEX 非集成套件通过，`162 passed`。
- Targeted ruff、mypy 和 list default residual scan 通过，生产命中为零。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root306 - CEX derivative series 仍把缺失 raw_payload 补成空对象

发现：

- `CexDerivativeSeriesRepository.upsert_open_interest_points(...)` 在 JSONB 参数化时使用
  `Jsonb(point.get("raw_payload") or {})`。
- 缺失 `raw_payload`、`raw_payload=None`、甚至非 mapping payload 都会被折叠成 `{}` 或进入旧
  fallback 路径。
- 这会让“provider 原始历史点证据缺失”和“provider 明确返回空对象”得到同一个
  `raw_payload_json`，也会让 `IS DISTINCT FROM` 变更判断失去证据语义。

根因：

- `cex_derivative_series` 是可重放的 provider-history 投影，`raw_payload_json` 是审计 provider
  原始点的证据字段，不是 repository 可以自行制造的默认值。
- 成熟 Kappa/CQRS 的历史投影也需要正式 point DTO；否则重放时无法判断某个历史点是 provider
  确实没有附带细节，还是上游 writer 漏传字段。
- PostgreSQL JSONB 最佳实践上，`{}` 可以是合法业务 payload，但不能作为 missing field 的隐式
  替身；否则 JSONB `IS DISTINCT FROM` 和 rowcount 只能比较“被补过的对象”，不是比较真实
  provider evidence。

修复：

- 新增 `_required_raw_payload(point)`，要求每个 derivative history point 在 SQL 前携带
  mapping-shaped `raw_payload`。
- 缺失或 `None` payload 抛出 `cex_derivative_series_raw_payload_required`，非 mapping payload
  抛出 `cex_derivative_series_raw_payload_invalid`。
- Upsert SQL 的 JSONB 参数只来自 `_required_raw_payload(point)`；architecture guard 禁止恢复
  `Jsonb(point.get("raw_payload") or {})`。

验证：

- RED：focused derivative raw-payload 命令初始失败，`4 failed`。
- GREEN：同一 focused 命令通过，`4 passed`。
- `test_cex_derivative_series_repository.py` 通过，`15 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root307 - CEX derivative series 仍把缺失 cursor rowcount 计成一行写入

发现：

- `_cursor_rowcount(cursor, default=1)` 使用 `getattr(cursor, "rowcount", default)`。
- 当 cursor 没有 `rowcount`，或者 rowcount 是非数字值时，旧逻辑返回默认值 `1`。
- 这会让 driver/fake cursor 合同漂移被记录成真实写入，直接污染“重放未变历史点写 0 行”的
  idempotency 证据。

根因：

- Root280 已经要求 overlapping provider-history rows 用 `IS DISTINCT FROM` 跳过未变更新，并用
  cursor rowcount 作为写入审计证据；但 rowcount helper 仍保留了测试/兼容默认值。
- 成熟 Kappa/CQRS 的投影写入指标必须来自数据库驱动事实，而不是 repository 猜测。否则
  publication/worker notes 中的 rows_written 会把“无法证明”误报成“写了一行”。
- PostgreSQL 最佳实践上，`rowcount` 是 DML 结果合同的一部分。缺失 rowcount 是驱动或测试假对象
  不符合 psycopg contract，应显式失败，而不是用默认数修补。

修复：

- `_cursor_rowcount(cursor)` 直接读取 `cursor.rowcount`。
- 缺失 rowcount 抛出 `cex_derivative_series_rowcount_required`；无法转成整数时抛出
  `cex_derivative_series_rowcount_invalid`。
- 删除 helper 的 default 参数和 `return default` fallback；architecture guard 禁止恢复
  `getattr(cursor, "rowcount", default)`。

验证：

- RED：focused derivative rowcount 命令在修正测试收集问题后失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- `test_cex_derivative_series_repository.py` 通过，`17 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root308 - CEX board publication 仍把缺失 cursor rowcount 当成默认写入数

发现：

- `CexOiRadarRepository.publish_board_with_result(...)` 的删除路径使用
  `_cursor_rowcount(delete_cursor, default=0)`，upsert 路径使用
  `_cursor_rowcount(upsert_cursor, default=1)`。
- `_cursor_rowcount(...)` 用 `getattr(cursor, "rowcount", default)`，并在 rowcount 非数字时返回
  default。
- 因此 board publication 可以把缺失 rowcount 记成 delete 0 行，或把 invalid/no-op upsert 记成
  1 行写入。

根因：

- CEX board 是 current read model，`board_rows_written` 是判断一次发布是否真实改写服务行的重要审计
  信号。这个信号必须来自 PostgreSQL DML cursor，而不是 repository 对 delete/upsert 的“合理猜测”。
- 之前已经把 board payload hash、`IS DISTINCT FROM` upsert guard、provider freshness 等语义收紧，
  但写入计数仍保留测试兼容默认值，导致 Kappa/CQRS 的“未变投影写 0 行”证据链最后一环仍可被伪造。
- PostgreSQL 最佳实践上，`rowcount` 缺失或不可解析是驱动/假对象合同错误；如果继续默认成 0/1，
  会掩盖数据库驱动、测试 fake、或 repository session wiring 的真实漂移。

修复：

- `CexOiRadarRepository._cursor_rowcount(cursor)` 直接读取 `cursor.rowcount`。
- 缺失 rowcount 抛出 `cex_oi_radar_rowcount_required`；不可转成整数时抛出
  `cex_oi_radar_rowcount_invalid`。
- 删除 board delete/upsert 的 default 参数；architecture guard 禁止恢复 default rowcount helper。

验证：

- RED：focused board rowcount 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root309 - CEX detail snapshot 仍把缺失 cursor rowcount 当成 no-op 写入

发现：

- `CexDetailSnapshotRepository._rowcount(cursor)` 使用
  `int(getattr(cursor, "rowcount", 0) or 0)`。
- cursor 缺少 `rowcount` 时，旧逻辑直接返回 `0`；cursor rowcount 为非法字符串时，则冒出未归类的
  `ValueError`。
- 这会让 detail snapshot upsert 的写入审计无法区分“PostgreSQL 确认没有改写行”和“驱动/测试 fake
  没有提供 DML rowcount 证据”。

根因：

- `cex_detail_snapshots` 和 board/current rows 一样，是可重放 current read model；它的
  `payload_hash IS DISTINCT FROM` guard 是否生效，需要用数据库 rowcount 做事实证据。
- 旧 helper 把 missing rowcount 解释成 no-op，看似保守，实际是在隐藏 wiring/driver 合同错误。
  成熟 Kappa/CQRS 不应把“无法证明有写入”当成“证明没有写入”。
- PostgreSQL 最佳实践上，DML cursor 的 `rowcount` 是写入路径 contract。缺失或不可解析应以仓储
  领域错误显式失败，这样测试 fake 和生产驱动漂移都会被早期发现。

修复：

- `_rowcount(cursor)` 直接读取 `cursor.rowcount`。
- 缺失 rowcount 抛出 `cex_detail_snapshot_rowcount_required`；不可转成整数时抛出
  `cex_detail_snapshot_rowcount_invalid`。
- architecture guard 禁止恢复 `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused detail rowcount 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root310 - `/api/cex/radar-board` 仍把缺失 board rows / score components 补成空结构

发现：

- `routes_cex._public_board(...)` 使用 `board.get("rows") or []`。
- `_public_row(...)` 使用 `payload.pop("score_components_json", None)` 后再 `components or {}`。
- 这会让 repository 返回的 malformed board payload 在 API 层被恢复成“合法空 board”或“合法空解释对象”。

根因：

- Root302 已经把 CEX board `score_components` 变成 repository writer 边界的正式输出；但 public
  shaping 层仍保留了独立兼容默认值，相当于把刚收紧的 read-model contract 在最后一跳重新放宽。
- 成熟 Kappa/CQRS 的读路径只能转换 persisted read model，不应该修复 repository/session 返回的
  缺字段 payload。缺 `rows` 是 repository contract 漂移，不是产品上的空 board；缺
  `score_components_json` 是 serving row 缺解释证据，不是空解释。
- PostgreSQL 最佳实践层面，JSONB score components 已经由写入边界保证 mapping-shaped；API 再补
  `{}` 会隐藏数据库行、repository row mapping 或测试 fake 的真实错误。

修复：

- 新增 `_required_board_rows(board)`，要求 repository board payload 带正式 `rows` list。
- 新增 `_required_score_components_json(row)`，要求每行带 mapping-shaped `score_components_json`。
- `_public_row(...)` 在成功验证后直接删除 `score_components_json` 并输出 public
  `score_components`，不再使用 `pop(..., None)` 或 `{}` fallback。

验证：

- RED：focused CEX radar-board API shaping 命令初始失败，`4 failed`。
- GREEN：同一 focused 命令通过，`4 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root311 - CEX detail builder 仍为 malformed level band 合成通用 level 证据

发现：

- `build_cex_detail_snapshot(...)` 使用 `_list_of_dicts(row.get("level_bands"))`，会静默过滤非 dict
  band，也会把非 list 的 `level_bands` 变成空列表。
- `_source_refs(...)` 对每个 band 使用 `band.get("kind") or "level"`，缺失 kind 时会合成通用
  `level`。
- band 缺失 `price` 时旧逻辑直接 `continue`，使 malformed level evidence 在 source refs 中消失，
  但仍可能留在 snapshot payload 里。

根因：

- `level_bands` 是 CoinGlass enrichment 输出给 `cex_detail_snapshots` 的正式证据结构，不是展示层
  可以任意容错的列表。`kind` 和 `price` 共同决定 source ref identity；缺任何一个都不应生成或跳过。
- 成熟 Kappa/CQRS 的 current detail row 应该记录明确的 provider/enrichment evidence。把缺 kind
  补成 `level` 会制造伪 source identity；跳过缺 price 会让 snapshot payload 和 source refs
  不一致，削弱审计可解释性。
- PostgreSQL JSONB 最佳实践上，JSONB list 可以存结构化 evidence，但结构校验应在 SQL 前完成；
  不能把 malformed JSON shape 留给后续查询或前端解释。

修复：

- 新增 `_required_level_bands(row)`，当 `level_bands` 存在时要求其为 list/tuple。
- 每个 band 必须是 dict，且必须有非空 `kind` 和可数值化 `price`。
- `_source_refs(...)` 使用验证后的 `band["kind"]` / `band["price"]`，不再补 `level` 或跳过缺
  price。

验证：

- RED：focused detail level-band 命令初始失败，`5 failed`。
- GREEN：同一 focused 命令通过，`5 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root312 - CEX detail degraded reasons 仍接受 scalar/object 兼容清洗

发现：

- `build_cex_detail_snapshot(...)` 使用 `_strings(row.get("degraded_reasons"))`，会把字符串、dict 或
  其他对象清洗成一个字符串原因列表。
- `enrich_row_with_coinglass(...)` 使用 `list(row.get("degraded_reasons") or [])` 继承上游原因；如果
  上游传入字符串，会被拆成字符列表；如果传入非字符串 item，也会继续混入 snapshot payload。
- `_coinglass_unavailable(...)` 也会原样保留 malformed `degraded_reasons`，让无 CoinGlass client /
  超出 enrichment budget 的路径继续把坏形状传给 detail builder。

根因：

- `degraded_reasons` 是 detail read model 的审计解释字段，和 `level_bands` / `source_refs` 一样属于
  writer/enrichment 输出合同，不是展示层自由文本兼容入口。
- 成熟 Kappa/CQRS 下，降级原因需要可重放、可聚合、可审计；把 scalar/object 自动转成字符串会隐藏
  上游 writer contract 漂移，也会让同一坏输入在 payload hash 里表现成“合法但奇怪”的原因集合。
- PostgreSQL JSONB 最佳实践上，JSONB list 字段应在进入 SQL 或 snapshot payload 前校验结构。否则后续
  查询、UI、agent evidence 会被迫解释混合类型数组，增加 planner/query 和业务语义的不确定性。

修复：

- `build_cex_detail_snapshot(...)` 改为 `_required_degraded_reasons(row)`：字段缺失或 `None` 表示无既有
  降级原因；字段存在时必须是 list/tuple，且每个 item 必须是非空字符串。
- `coinglass_detail_enricher` 新增 `_inherited_degraded_reasons(row)`， enriched 和 unavailable 路径都先
  校验/规范化既有原因，再追加 CoinGlass provider failure reason。
- architecture guard 禁止恢复 `_strings(row.get("degraded_reasons"))` 和
  `list(row.get("degraded_reasons") or [])` 兼容路径。

验证：

- RED：focused degraded-reasons 命令初始失败，`10 failed, 1 passed`。
- GREEN：同一 focused 命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root313 - Binance OI provider DTO 缺字段被静默恢复成空指标

发现：

- `build_binance_oi_radar_rows(...)` 通过 `_attr(value, name)` 读取 Binance ticker、funding 和
  open-interest history 对象，内部使用 `getattr(value, name, None)`。
- provider 序列中如果出现缺 `open_interest_value`、`quote_volume_24h`、`last_funding_rate` 等字段的
  畸形对象，旧代码不会失败，而是把该指标变成 `None` 后继续评分、排序并构造 board row。
- `mark_price` 使用 `premium.mark_price or ticker.last_price` 语义，导致合法的 `0.0` 会被当成缺失值，
  覆盖成 ticker last price。

根因：

- `CexOiMarketProvider` 已经定义了正式 DTO：`CexOiTicker24h`、`CexFundingPremium`、
  `CexOpenInterestPoint`。builder 是 provider adapter 和 current board read model 之间的合同边界，
  不能再用对象反射把坏 DTO 补成“合法空指标”。
- 成熟 Kappa/CQRS 的关键不是“尽量产出一行”，而是保证 current row 可由正式输入重放。缺字段对象代表
  provider adapter 合同破损；如果把它写成 `NULL` 指标，后续 repository payload hash、UI、agent evidence
  都会把系统故障误读成真实市场缺失数据。
- PostgreSQL 最佳实践上，`NULL` 应该表达业务上允许的缺失值，而不是上游对象形状错误。否则同一 SQL
  schema 无法区分“provider 无该指标”和“adapter 没按协议返回字段”，审计和告警都会失真。

修复：

- 删除 `_attr(...)` / `getattr(..., None)` 兼容读取。
- 对 ticker、funding、OI history 分别使用字段级 helper；对象存在但缺字段时抛
  `cex_oi_radar_provider_contract_required:*`。
- 保留“没有匹配 ticker/premium/history row”作为合法可选数据，但不保留“有对象却缺字段”的兼容路径。
- `mark_price` 改为显式 `premium_mark_price if premium_mark_price is not None else ticker_last_price`，
  保留合法 `0.0` 值。

验证：

- RED：focused provider-DTO 命令初始失败，`4 failed`。
- GREEN：同一 focused 命令通过，`4 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root314 - Binance OI runtime wiring 仍把集成 DTO 缺字段洗成领域 DTO 的 `None`

发现：

- Root313 让 `build_binance_oi_radar_rows(...)` 不再吞掉 malformed `CexOiTicker24h` /
  `CexFundingPremium` / `CexOpenInterestPoint`。
- 但上游 `BinanceUsdmFuturesOiProvider` 仍通过 `getattr(row, "quote_volume_24h", None)`、
  `getattr(row, "last_funding_rate", None)`、`getattr(row, "open_interest_value", None)`、
  `getattr(row, "time_ms", None)` 把集成层对象映射成领域 provider DTO。
- 如果 `BinanceUsdmFuturesClient` 或测试替身返回缺字段对象，wiring 会先构造字段存在但值为 `None`
  的领域 DTO；这样 Root313 的 builder 边界就看不见原始合同破损。

根因：

- runtime provider wiring 是集成 DTO 到领域 provider DTO 的第一道合同边界。它不能把“对象没有字段”
  和“provider 明确返回字段值为 null/None”混成同一种 `None`。
- 成熟 Kappa/CQRS 链路里，adapter 层应该把外部 provider 响应解析成正式输入，writer 只消费正式输入。
  如果 adapter 层先把缺属性洗成 `NULL` 指标，current read model 会把 adapter bug 当作市场数据缺口写入，
  后续 SQL hash、排序、降级解释和 agent evidence 都会失真。
- PostgreSQL 最佳实践上，`NULL` 是业务值，不是契约错误的遮羞布。把缺属性转换为 `NULL` 会让数据库无法
  区分“Binance 真的没有指标”和“本地 wrapper 没按协议返回字段”。

修复：

- `BinanceUsdmFuturesOiProvider` 改用 `_required_row_field(row, field)` 读取集成 DTO 字段。
- `_row_symbol(row)` 也要求正式 `symbol` 字段且非空，避免空 symbol 造成 ticker/funding 行被静默过滤。
- 字段存在但值为 `None` 仍是合法 provider 数据；字段不存在会抛
  `binance_oi_provider_contract_required:*`。
- architecture guard 禁止 CEX OI wiring 恢复 `getattr(row, ..., None)` 和 empty-symbol defaults。

验证：

- RED：focused provider-wiring 命令初始失败，`4 failed`。
- GREEN：同一 focused 命令通过，`4 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root315 - Macro current snapshot JSON 字段缺失被仓储洗成空对象/空数组

发现：

- `build_macro_view_snapshot(...)` 会显式产出 `panels_json`、`indicators_json`、`triggers_json`、
  `data_gaps_json`、`source_coverage_json`、`features_json`、`chain_json`、`scenario_json`、
  `scorecard_json`。
- 但 `MacroIntelRepository.insert_snapshot(...)` 和 `_macro_snapshot_payload_hash(...)` 在写
  `macro_view_snapshots` 前使用 `snapshot.get(...) or {}` / `or []`。
- 如果 projection engine 或 direct writer 漏掉某个正式 section，旧代码会把它转换成合法空结构，
  参与 payload hash 并写入 current snapshot。

根因：

- `macro_view_snapshots` 是 current read model，不是宽容 DTO 反序列化层。它的 JSON section 是
  projection engine 的正式输出合同；仓储只能验证并持久化，不能代造缺失业务含义。
- 成熟 Kappa/CQRS 中，projection 的可重放性依赖“同一事实输入产生同一显式输出”。缺字段和显式空字段
  是两种不同状态：前者代表 writer bug，后者代表业务上确实没有内容。旧兜底把这两者折叠成同一
  payload hash，导致 unchanged 判断、下游 daily brief wake、API 展示和审计都失真。
- PostgreSQL 最佳实践上，JSONB 空对象/空数组是业务值，不是 schema/contract 错误的替代品。把缺失字段
  静默写成 `{}` / `[]` 会让数据库无法区分“投影计算得到空集合”和“投影代码没有产出该 section”。

修复：

- 新增 `_macro_snapshot_payload(...)` 作为 hash 和 SQL 参数绑定的共同入口。
- mapping section 通过 `_required_snapshot_mapping(...)` 校验，list section 通过
  `_required_snapshot_list(...)` 校验。
- 缺字段抛 `macro_view_snapshot_payload_required:*`，错类型抛
  `macro_view_snapshot_payload_invalid:*`。
- 显式空 dict/list 仍然有效，但必须由 projection engine 写出。

验证：

- RED：focused Macro snapshot 命令初始失败，`19 failed`。
- GREEN：同一 focused 命令通过，`19 passed`。
- 仓储相关组通过，`60 passed`；按当前用户指令，本轮不运行 integration-heavy gate。

### Root316 - `/api/macro` 仍把坏 current snapshot section 洗成空 public payload

发现：

- Root315 让 `MacroIntelRepository` 不再把缺失 snapshot section 写入 `macro_view_snapshots`。
- 但 `/api/macro` 的 `_public_macro(...)` 仍然用 `snapshot.get("panels_json") or {}`、
  `snapshot.get("triggers_json") or []` 等逻辑 shaping public payload。
- 这意味着已存在的坏 current row、测试替身、或未来读仓储回归仍可能被 API 返回为合法空面板/空 trigger，
  而不是暴露 read-model 合同破损。

根因：

- API read path 是 current read model 的消费边界，不是第二个 projection writer。它可以在
  `snapshot is None` 时返回明确的 `macro_view_snapshot_missing`，但不能在 snapshot 存在时替
  projection/仓储制造缺失 JSON section。
- 成熟 Kappa/CQRS 的读路径应该保持 persisted read model 的语义透明：缺行是缺行，坏行是坏行，
  显式空对象/数组才是业务上的空内容。旧 API 兜底把“坏行”和“显式空内容”折叠成同一种 public payload，
  UI、agent、operator 都会误以为 Macro projection 正常但没有内容。
- PostgreSQL 最佳实践上，JSONB 字段中的 `{}` / `[]` 是持久化业务值。API 层再补一次默认值，会绕过
  数据库约束、payload hash 和仓储校验，形成读路径兼容 shim。

修复：

- `_public_macro(...)` 在 snapshot 存在时通过 `_required_snapshot_mapping(...)` 和
  `_required_snapshot_list(...)` 校验 public section。
- 缺 section 抛 `macro_view_snapshot_section_required:*`，错类型抛
  `macro_view_snapshot_section_invalid:*`。
- `snapshot is None` 的明确缺口响应保持不变，仍返回 `macro_view_snapshot_missing`。
- architecture guard 禁止 `/api/macro` 恢复 `snapshot.get(...) or {}` / `or []` section 兜底。

验证：

- RED：focused Macro API snapshot 命令初始失败，`19 failed`。
- GREEN：同一 focused 命令通过，`19 passed`。
- API Macro focused group 通过，`39 passed`；按当前用户指令，本轮不运行 integration-heavy gate。

### Root317 - Macro module view builder 仍把坏 current snapshot 洗成空模块 payload

发现：

- Root316 只切断了 `/api/macro` 根 payload 的 section 默认值。
- 继续检查模块页读路径发现，`build_macro_module_view(...)` 仍通过
  `_mapping(snapshot.get("features_json"))`、`_mapping(snapshot.get("scenario_json"))`、
  `_mapping(snapshot.get("chain_json"))` 和 `_sequence(snapshot.get("data_gaps_json"))`
  构造 `macro_module_view_v3`。
- 因此同一条坏的 `macro_view_snapshots` current row，在根 `/api/macro` 会失败，但在
  `/api/macro/modules/...` 仍可能被渲染成空 feature、空 scenario、空 transmission 或空 data health。

根因：

- module view builder 是 read-model projector 的读侧消费边界，不是另一个兼容投影器。它可以在
  `snapshot is None` 时构造明确的 missing module view，但 snapshot 一旦存在，就必须忠实消费
  `macro_view_snapshots` 的正式 section 合同。
- 成熟 Kappa/CQRS 里，一个 current read model 不能在不同 read path 上有不同真值规则。Root315
  让 writer 不再制造空 section，Root316 让根 API 不再制造空 section；如果 module builder 继续兜底，
  它就成了第三个隐形 writer，把 projection bug 重新包装成合法 UI payload。
- PostgreSQL 最佳实践上，JSONB 的 `{}` / `[]` 是显式业务值。module builder 把缺字段转换为
  `{}` / `[]`，会绕过 payload hash、仓储边界和 API 根 payload 的校验，让同一坏行在不同路由表现不一致。

修复：

- `build_macro_module_view(...)` 在 present snapshot 路径先调用
  `_macro_module_view_snapshot_sections(...)`，一次性验证全部正式 JSON sections。
- mapping section 缺失抛 `macro_module_view_snapshot_section_required:*`，错类型抛
  `macro_module_view_snapshot_section_invalid:*`；list section 同样要求 present 且 list-shaped。
- `module_read`、`module_evidence`、`transmission` 和 `data_health` 只消费验证后的 section。
- `snapshot=None` 的 missing module view 保持合法，仍显式返回 `macro_view_snapshot_missing`。
- architecture guard 禁止 module builder 恢复 `_mapping(snapshot.get(...))` 或
  `_sequence(snapshot.get(...))` section 兜底。

验证：

- RED：focused Macro module view 命令初始失败，`19 failed`。
- GREEN：同一 focused 命令通过，`19 passed`。
- Macro/API focused group 通过，`82 passed`；targeted ruff 通过。按当前用户指令，本轮不运行
  integration-heavy gate。

### Root318 - Token Radar 下游 fan-out 和 Capture Tier dirty hash 仍允许旧 target alias 抢正式 identity

发现：

- Root231 已经要求 `token_radar_current_rows` 使用正式 `target_type_key` / `identity_id`
  作为 current identity，不能再从 `target_type` / `target_id` / `intent_id` 恢复 serving key。
- 但继续沿 rank-change 下游链路追踪后发现，Pulse Trigger、Narrative Admission、
  Token Profile Current、Token Capture Tier dirty enqueue，以及 Capture Tier rank-set
  `payload_hash` 仍读取 `target_type` / `target_id`，或用
  `row.get("target_type") or row.get("target_type_key")` 让旧字段优先。
- `token_radar_venue_for_rank_input(...)` 也存在同类问题：rank input 同时携带 formal
  `target_type_key` 和旧 `target_type` 时，旧字段会决定 venue，可能把 CEX 当前行错误归到默认/Dex
  venue 或反向污染 rank-set 过滤。

根因：

- 之前的 hard-cut 主要切在“写入 current row”和“repository publication identity”边界，
  但没有把同一身份规则扩展到 current row 的所有消费者。结果是数据库里已经有正式 identity，
  下游 dirty target / hash / venue 选择仍像兼容 DTO 一样信任旧 alias。
- 成熟 Kappa/CQRS 里，current read model 一旦发布，消费者必须以 current row 的正式 key 为唯一产品身份。
  旧字段可以作为历史 payload 或诊断上下文存在，但不能再参与下游工作队列 key、payload hash 或分区选择。
  否则同一条 serving row 会在不同消费者眼里拥有不同身份，破坏单 writer、可重放 dirty hash、
  unchanged projection zero-write，以及 PostgreSQL 队列去重。
- PostgreSQL 层面的具体风险是：dirty target 表依赖 `(work_name, partition_key)` 和
  `payload_hash` 做幂等合并；如果 hash 输入可被旧 alias 覆盖，数据库无法区分“业务内容变化”
  和“兼容字段污染”，也无法稳定跳过 unchanged rows。

修复：

- 新增 `_current_row_resolved_target(row)`，统一从正式 `target_type_key` / `identity_id`
  读取下游可解析目标；只允许 `Asset` / `CexToken` 进入 Pulse、Narrative、Profile 和 Capture Tier
  fan-out。
- Capture Tier dirty rank-set hash 改为要求 `target_type_key` / `identity_id`，alias-only row
  抛 `token_capture_tier_rank_set_identity_required`，冲突的旧 `target_type` / `target_id`
  不再影响 hash。
- `token_radar_venue_for_rank_input(...)` 改为 formal key 存在时只信 formal key；只有缺少
  `target_type_key` 的旧 rank-source 输入才退回源事实 `target_type`。
- architecture guard 禁止下游 fan-out、Capture Tier hash、rank-input venue 恢复
  `target_type` / `target_id` alias override。

验证：

- RED：focused Root318 命令初始失败，`8 failed`；补充 venue RED 初始失败，`2 failed`。
- GREEN：focused Root318 命令通过，`8 passed`；venue focused 命令通过，`2 passed`。
- Token Radar projection / Capture Tier dirty target / architecture 组合通过，`125 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root319 - Token Radar generic dirty enqueue 仍用旧 alias 和静默 skip 恢复队列 identity

发现：

- Root236 已经把 `token_radar_dirty_targets` 与 `token_radar_source_dirty_events` 的 post-claim
  done/error completion identity 切成正式 claimed-row contract。
- 继续从 generic `enqueue_targets(...)` 入口反查后发现，`TokenRadarDirtyTargetRepository._target_key(...)`
  仍从 `target_type` / `target_id` / `intent_id` 恢复缺失的
  `target_type_key` / `identity_id`，而 `_dirty_records(...)` 对空 identity 直接 `continue`。
- `TokenRadarSourceDirtyEventRepository._source_event_records(...)` 也仍从 `event_id`、
  `target_type`、`target_id` 恢复正式 source-edge queue key，并把缺字段行当作空 dirty work 跳过。
- 上游 ingest 和 resolution reprocess 已经产出正式 `source_event_id`、`target_type_key`、
  `identity_id`；因此这些 repository fallback 不再是必要映射，而是遗留兼容 shim。

根因：

- 代码把“producer 在入队前把事实字段映射成正式 queue command”和“repository 修复任意旧 DTO”
  混在了一起。前者是 Kappa/CQRS 的边界归一化，后者会让控制面表继续接受多种身份语言。
- 成熟 Kappa/CQRS 中，dirty queue 是投影控制面的事实来源：queue key 和 payload hash 决定是否需要重算、
  是否能合并重复 work、以及 claim/done CAS 是否能精确命中。enqueue repository 应校验命令形状，
  不应把 malformed producer 输出改写成看似合法的工作项。
- PostgreSQL 层面的风险很直接：`token_radar_dirty_targets` 的 target key / `payload_hash`，
  以及 `token_radar_source_dirty_events` 的 `(projection_version, source_event_id, target_type_key, identity_id)`
  去重语义都会被旧 alias 污染；静默 skip 还会把“应该重投影但 payload 坏了”伪装成“没有 dirty work”。

修复：

- `TokenRadarDirtyTargetRepository.enqueue_targets(...)` 改为通过 `_required_enqueue_text(...)` 读取
  `target_type_key` 与 `identity_id`，缺字段、`None`、空字符串都抛
  `token_radar_dirty_target_enqueue_identity_required`。
- `TokenRadarSourceDirtyEventRepository` enqueue 同样要求 `source_event_id`、
  `target_type_key`、`identity_id`，错误抛
  `token_radar_source_dirty_event_enqueue_identity_required`。
- 删除 enqueue-time 的 `target_type` / `target_id` / `intent_id` / `event_id` alias fallback
  和 blank-row skip；architecture guard 固化这些禁止项。

验证：

- RED：focused dirty enqueue 命令初始失败，`9 failed`。
- GREEN：同一 focused 命令通过，`9 passed`。
- Token Radar dirty enqueue / ingest / reprocess / architecture 组合通过，`73 passed`。
- targeted ruff、mypy 和 residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root320 - News page row 仓储仍把缺失 JSON sections 补成空结构

发现：

- `build_news_page_row(...)` 已经产出 semantic page-row payload，包括 `token_lanes`、
  `fact_lanes`、`story`、`source`、`signal`、`agent_brief`、`market_scope`、
  `agent_admission` 等字段。
- 但 `NewsRepository._page_row_payload(...)` 在写 `news_page_rows` 前仍用
  `payload.get(...) or []`、`payload.get(...) or {}` 和
  `payload.get("agent_brief") or {"status": "pending"}` 清洗缺失字段。
- 这意味着 malformed page projection row 可以被仓储洗成“合法的空 JSONB section”，再进入
  payload hash 和 `INSERT INTO news_page_rows`。

根因：

- Page projection service 是 writer，repository 是持久化边界。repository 可以把正式字段转成 JSONB，
  但不能替 writer 制造业务 section。否则缺字段、空 section、pending agent state 会在 payload hash
  中变成同一种内容，审计时无法区分“投影真的输出空列表/空对象”和“writer 漏字段”。
- 成熟 Kappa/CQRS 里，current read model 的 payload hash 是 idempotency 和 zero-write 的依据。
  如果仓储在 hash 前补默认值，数据库层面的 `payload_hash IS DISTINCT FROM` 会稳定地跳过或覆盖错误内容，
  但错误来源已经被抹掉。
- PostgreSQL 最佳实践上，JSONB `[]` / `{}` 是显式业务值，不是缺字段的替代品。让仓储默认它们会削弱
  schema/contract 测试，也会让 API/UI 读到貌似完整的 News page row。

修复：

- `NewsRepository._page_row_payload(...)` 改为通过 `_required_page_list(...)` 和
  `_required_page_mapping(...)` 校验 page-row sections。
- `token_lanes`、`fact_lanes`、`token_impacts`、`content_tags` 必须显式 list-shaped；
  `story`、`content_classification`、`source`、`signal`、`provider_rating`、`agent_brief`、
  `market_scope`、`agent_admission` 必须显式 mapping-shaped。
- 缺字段抛 `news_page_row_payload_required:*`，错类型抛
  `news_page_row_payload_invalid:*`；architecture guard 禁止旧 `or []` / `or {}` /
  pending agent 默认值回流。

验证：

- RED：focused News page-row payload 命令初始失败，`16 failed`。
- GREEN：同一 focused 命令通过，`16 passed`。
- News page repository / projection / architecture 组合通过，`56 passed`。
- targeted ruff、mypy 和 residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root321 - News item detail 读路径仍从 raw item 修复坏 page row

发现：

- Root320 已经把 `news_page_rows` 写入边界切成 formal JSON section：缺 `story`、
  `signal`、`market_scope`、`agent_admission`、lane 等字段会在 payload hash / SQL 前失败。
- 但 `NewsRepository.get_news_item_detail(...)` 在已经查到 current `news_page_rows` 后，仍然用
  `projected.get(...) or item_payload.get(...)`、`_json_dict(...)`、`_json_list(...)` 和
  `_projection_missing_signal(...)` 兜底。
- 结果是：坏的 current page row 写不进新数据，但历史坏 row、测试替身或未来绕过写边界的 malformed row
  仍可能在 detail API 被洗成“看起来完整”的 public payload。

根因：

- 这是典型的 CQRS 读侧兼容层回流。writer hard-cut 只能保证新写入；如果 reader 仍把 raw facts 当成
  projected serving fields 的备份来源，系统就有两套 truth：`news_page_rows` 和 `news_items`。
- 成熟 Kappa/CQRS 中，read model 是可重建的 serving contract。缺投影字段应该暴露为投影损坏或需要
  rebuild，而不是在 HTTP request path 里被修复。否则 worker/rebuild 的错误会被 API 层隐藏，排障时
  只能看到“页面正常但 read model 不可信”。
- PostgreSQL 层面的风险是 JSONB section 语义被污染：`{}` / `[]` 是投影明确输出的值，不是缺失字段的
  read-time 替代品。读路径把缺失补成空结构，会绕开 schema/contract guard，也让 payload hash、
  projection version、row ownership 的审计失去可解释性。

修复：

- `get_news_item_detail(...)` 改为通过 `_required_projected_page_text(...)`、
  `_required_projected_page_mapping(...)`、`_required_projected_page_list(...)` 读取 current page row。
- `representative_news_item_id`、`story_key`、`content_class`、agent admission text 字段必须是非空
  projected text；`story`、`signal`、`provider_rating`、`content_classification`、`market_scope`、
  `agent_admission`、`page_source`、`page_agent_brief` 必须是 mapping；lane/tag/impact 字段必须是 list。
- 缺字段抛 `news_item_detail_projection_required:*`，错类型抛
  `news_item_detail_projection_invalid:*`；raw `news_items` 只保留 base item、source/provider observation、
  facts/current brief/run evidence 的职责，不再修复 projected page fields。
- 删除已无生产调用的 `_signal_from_agent_brief(...)`、`_projection_missing_signal(...)` 和
  `_direction_label(...)`，并把架构守卫改成禁止这些退休 fallback helper 回流。

验证：

- RED：focused News item detail projection 命令初始失败，`21 failed`。
- GREEN：同一 focused 命令通过，`21 passed`。
- News repository / architecture 组合通过，`103 passed`。
- targeted ruff、mypy 和 production residual scan 通过；残留扫描同时覆盖旧 detail fallback 片段和退休 helper。
  按当前用户指令，本轮不运行 integration-heavy gate。

### Root322 - News page list / notification candidate 读路径仍跳过 page-row section 校验

发现：

- Root320 让 `news_page_rows` 写入边界要求 formal JSON section；Root321 又让 item detail 读路径不能从
  raw `news_items` 修复坏投影。
- 但 `list_news_page_rows(...)` 和 `list_news_high_signal_notification_candidates(...)` 仍然把数据库 row
  `dict(row)` 后直接返回，只额外对 projected `agent_brief` 调 `_public_agent_brief_payload(...)`。
- `_public_agent_brief_payload(...)` 会把 `None`、非 mapping 或带旧 contract key 但非 current contract 的
  agent brief 转成 `{"status": "pending"}`。因此 malformed current page row 在列表和通知候选读路径里仍能被
  降级为“正常 pending”或未经校验的 public JSON。

根因：

- 这是 Root321 的同类问题，但发生在列表/通知候选链路而非 detail 链路。写侧 hard-cut 和 detail hard-cut
  不能证明所有 public consumers 都遵守 read-model contract。
- 成熟 CQRS 中，read model 的每个 public consumer 都必须保持同一个投影契约：如果 current row present，
  public list、detail、notification worker 都读这个 current row；坏 row 应触发显性错误或 rebuild，而不是
  consumer 各自用 helper/default 得出不同 public 状态。
- PostgreSQL 角度上，JSONB section 的 `NULL`、非 list/mapping、空 list/object、pending agent brief
  是不同语义。让 notification candidate 把坏 `agent_brief_json` 降级为 pending，会把“投影坏了”和
  “agent 尚未 ready”混为一类，直接影响 alert eligibility 和外部通知排障。

修复：

- 新增 `_projected_news_page_row_payload(...)`，供 News page list 和 high-signal notification candidate
  共用 projected-row shaping。
- 列表完整模式要求 `story`、`signal`、`provider_rating`、`source`、`agent_brief`、`market_scope`、
  `agent_admission`、`content_classification` 为 mapping，`source_ids`、`source_domains`、`token_lanes`、
  `fact_lanes`、`token_impacts`、`content_tags` 为 list，关键 identity/admission/content 字段为非空 text。
- 通知候选精简模式校验其 SQL 实际选择的 projected sections；`agent_brief` 必须先通过
  `_required_news_page_row_mapping(...)`，再进入 public sanitizer 裁剪字段。
- 缺字段抛 `news_page_row_projection_required:*`，错类型抛
  `news_page_row_projection_invalid:*`；架构 guard 禁止旧 `payload.get("agent_brief")` pending 兜底回流。

验证：

- RED：focused News page list projection 命令初始失败，`26 failed`。
- GREEN：同一 focused 命令通过，`26 passed`。
- News repository / architecture 组合通过，`129 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root323 - Token Profile public 读模型仍把坏 current 行洗成 pending/空 JSON

发现：

- `TokenProfileCurrentWorker` 是 `token_profile_current` 的唯一 runtime writer，当前行由
  exact profile/evidence sources、`cex_token_profiles` 和 ready local image rows 投影而来。
- 但 `TokenProfileReadModel._block_from_row(...)` 对已经存在的 current row 仍使用
  `(_clean(row.get("status")) or "pending").lower()`，`_payload(...)` 对非 mapping
  `source_payload_json` 返回 `{}`，`_quality_flags(...)` 对非 list flags 返回 `[]`。
- 结果是：缺 current row 的合法 public `pending` 状态，和 present current row 的损坏状态被合并了。
  一个缺 `status`、缺 `source_kind`、坏 `quality_flags_json` 或坏 `source_payload_json` 的 serving row
  会被 API/UI 读成“还在 pending / 没有 raw / 没有 flags”，而不是暴露为投影损坏。

根因：

- 这是 read-side compatibility shim 留在 current read model consumer 里的典型症状。写侧
  `TokenProfileCurrentRepository.upsert_current(...)` 已要求 `status` / `source_kind` 等字段，
  但 public 读侧仍假定历史坏行、测试替身或绕过仓储的行可以被补成正常状态。
- 成熟 Kappa/CQRS 里，missing current row 和 malformed current row 是两类状态：前者可以是
  bounded catch-up 尚未完成，后者说明单 writer / rebuild / schema 合同被破坏。把二者合并为
  `pending` 会让运维误判 worker backlog，也会让前端和通知链路看起来“只是还没刷新”。
- PostgreSQL 角度上，JSONB `{}` 和 `[]` 是显式投影值，不是坏列的替代品。读路径制造空 object/array
  会污染 payload hash、当前行审计和 SQL schema guard 的语义。

修复：

- `TokenProfileReadModel` 对 present `token_profile_current` 行要求 formal current-row fields：
  `status` 必须存在且属于 ready/missing/unsupported/error；`source_kind` 必须是非空 text；
  `quality_flags_json` 必须是 list；`source_payload_json` 必须是 mapping。
- 缺字段抛 `token_profile_current_public_required:*`，错类型或空 text 抛
  `token_profile_current_public_invalid:*`。
- 缺 current row 的 `Asset` 仍返回显式 `pending` block，缺 current row 的 `CexToken` 仍返回显式
  `unsupported` block；只有 present malformed row 被视为投影损坏。

验证：

- RED：focused Token Profile current-row public contract 命令初始失败，`9 failed`。
- GREEN：同一 focused 命令通过，`9 passed`。
- Token Profile read/repository/worker/architecture 局部组合通过，`36 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root324 - Signal Pulse public mapper 仍把坏 candidate JSON 洗成空 decision/数组

发现：

- Signal Pulse 的 public list/detail 都从 persisted `pulse_candidates` 读 serving rows，`display_status`、
  `evidence_packet_hash` 和 v3 `factor_snapshot_json` gate 已经能过滤掉不该公开的行。
- 但进入 `pulse_item_from_row(...)` 后，`decision_json` 仍通过 `_dict(row.get("decision_json"))`
  变成 `{}`，`gate_reasons_json`、`risk_reasons_json`、`evidence_event_ids_json`、
  `source_event_ids_json` 仍通过 `_list(...)` 变成 `[]`。
- 这意味着 present 且 displayable 的 `pulse_candidates` row 如果这些 JSON 列损坏，public API 会返回
  空 summary、空风险/证据数组，而不是暴露 read-model row 损坏。

根因：

- 这是 Pulse public read model 里的读侧 DTO 兼容层。它最初看起来像 UI 容错，但实际上把
  `pulse_candidates` 的 serving contract 降成“尽量拼出一个 payload”。
- 成熟 Kappa/CQRS 里，`pulse_candidates` 是 agent/worker 写出的 public/hidden current row；
  list/detail mapper 只能转换它，不能成为第二个投影 writer。坏 JSON 列应该触发显性错误或 rebuild，
  否则 operator 会看到“候选存在但没有解释/证据”，却不知道是 agent 输出坏了、repository 写坏了，还是
  public mapper 偷偷吞掉了字段。
- PostgreSQL JSONB 层面，`[]` 和 `{}` 是明确业务值。把 `NULL`、非 list、非 mapping 在 read path
  转成空结构，会让 schema 默认、payload 审计和前端解释语义不可区分。

修复：

- `pulse_item_from_row(...)` 改为通过 `_required_candidate_list(...)` 读取
  `gate_reasons_json`、`risk_reasons_json`、`evidence_event_ids_json`、`source_event_ids_json`。
- `_decision(...)` 改为通过 `_required_candidate_mapping(...)` 读取 `decision_json`。
- 缺字段抛 `signal_pulse_public_candidate_required:*`，错类型抛
  `signal_pulse_public_candidate_invalid:*`；架构 guard 禁止旧 `_dict(row.get("decision_json"))` 和
  top-level `_list(row.get(...))` public mapper fallback 回流。

验证：

- RED：focused Signal Pulse public candidate JSON contract 命令初始失败，`11 failed`。
- GREEN：同一 focused 命令通过，`11 passed`。
- Signal Pulse service/API/read-repository/architecture 局部组合通过，`48 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root325 - Event Token projection 仍把坏 resolution JSON/身份洗成空公共字段

发现：

- `/api/recent`、WebSocket replay/live payload 和 watchlist timelines 都通过
  `EventTokenProjectionQuery` 读取 current `token_intent_resolutions`，再拼入 identity、
  event market capture 和 latest market tick。
- `IntentResolutionRepository.insert_resolution(...)` 写 `reason_codes_json`、
  `candidate_ids_json`、`lookup_keys_json` 时使用 PostgreSQL `Jsonb(...)`，正式运行形态是 JSONB
  array。
- 但 public projection 仍保留 `_loads(row.get(...), [])`：`NULL`、空字符串、坏 JSON 字符串会被洗成
  `[]`，非字符串值会原样放行；同时 `resolution_id`、`intent_id`、`event_id`、
  `resolution_status` 通过 `str(row.get(...) or "")` 被洗成空字符串。

根因：

- 这是事实投影读路径里的历史兼容层。它最初可能是为了兼容测试替身或早期 JSON-string DB 驱动形态，
  但在当前 PostgreSQL/psycopg JSONB 合同下，public mapper 不应再承担“解析旧字符串/补空数组”的职责。
- 成熟 Kappa/CQRS 里，`token_intent_resolutions` 是 material fact/current resolution edge；
  event-token projection 是只读投影，不是第二个修复 writer。缺失或坏形态代表 resolver、migration、
  repository 写入或 fake contract 出错，应该显性失败并触发修复/重放，而不是给前端一个看似正常但证据为空的
  token resolution。
- PostgreSQL 角度上，`[]` 是有业务含义的“明确没有候选/lookup/reason”，不是 `NULL`、坏 JSON 字符串、
  dict 或缺列的替代值。读路径制造空数组会污染审计、调试和缓存语义，也让 SQL schema 的 NOT NULL/JSONB
  约束失去可观测性。

修复：

- `EventTokenProjectionQuery` 删除 read-side `json.loads` compatibility helper。
- selected current rows 现在必须提供非空 `resolution_id`、`intent_id`、`event_id`、
  `resolution_status`，缺失抛 `event_token_projection_required:*`，空 text 抛
  `event_token_projection_invalid:*`。
- `reason_codes_json`、`candidate_ids_json`、`lookup_keys_json` 必须是 list-shaped JSONB 值；缺失抛
  `event_token_projection_required:*`，字符串/dict 等错误形态抛 `event_token_projection_invalid:*`。
- unresolved rows 仍按 SQL/read-model语义不进入 public payload；这次 hard-cut 只针对已经被选中的 resolved
  public row。

验证：

- RED：focused Event Token projection contract 命令初始失败，`12 failed`。
- GREEN：同一 focused 命令通过，`12 passed`。
- Event Token / Binance CEX read path / API read-path architecture 局部组合通过，`49 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root326 - Token Radar projection 仍用 display symbol/空数组修复 resolution 事实

发现：

- Root325 切掉了 `/api/recent` 事件 token projection 的 resolution JSON 兼容层，但 Token Radar
  current-row publication 仍在另一条链路里读取同一事实源。
- `TokenRadarProjection._project_group(...)` 仍把 latest source row 的
  `resolution_status` 缺失修成 `"NIL"`，把 `reason_codes_json`、`candidate_ids_json`、
  `lookup_keys_json` 缺失或错误形态修成 `[]`。
- 更深的一层是 `_projection_identity_key(...)`：当 unresolved row 没有 `target_type/target_id` 且
  `lookup_keys_json` 没给出 `symbol:` / `address:` lookup key 时，它会从 `display_symbol` 重新拼一个
  `LookupKey/symbol:...` serving identity。

根因：

- 这不是 UI 兜底，而是 current-row identity 的事实边界被 read-model writer 重写了。Token Radar
  current rows 的 stable key 是产品/window/scope/target identity；如果 projection 可以从
  `display_symbol` 发明 unresolved identity，那么缺失 lookup-key 事实会变成另一个看似稳定的 current row。
- 成熟 Kappa/CQRS 里，`token_intent_resolutions.lookup_keys_json` 是 deterministic resolver 的输出事实，
  也是 unresolved attention row 的 identity 输入。缺 lookup key 代表 resolver/reprocess/edge hydration
  合同损坏，不应该由 projection 用展示字段修复。
- PostgreSQL JSONB 层面，`[]` 表示 resolver 明确没有候选/lookup/reason；`NULL`、字符串、dict 或缺列
  都是不同的损坏状态。把这些状态投影成空数组，会污染 `resolution_json`、payload hash、dirty fan-out
  和后续 Pulse/Narrative/Profile 消费者看到的解释链。

修复：

- `TokenRadarProjection._project_group(...)` 改为通过 `_required_resolution_text(...)` 读取
  `resolution_status`，通过 `_required_resolution_list(...)` 读取 `reason_codes_json`、
  `candidate_ids_json`、`lookup_keys_json`。
- 缺字段抛 `token_radar_projection_resolution_required:*`，错类型或空 status 抛
  `token_radar_projection_resolution_invalid:*`。
- `_projection_identity_key(...)` 对 unresolved row 只从 formal `lookup_keys_json` 取
  `LookupKey/...` identity；没有 lookup key 时抛 `token_radar_projection_identity_required`，不再从
  `display_symbol` 反推 serving identity。

验证：

- RED：focused Token Radar resolution/identity contract 命令初始失败，`11 failed`。
- GREEN：同一 focused 命令通过，`11 passed`。
- Token Radar projection/publication-state/source-width 局部组合通过，`141 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root327 - Token Radar resolved lane 仍用宽松 target truthy 判定降级坏高置信 resolution

发现：

- Root326 要求 Token Radar 的 `resolution_json` 和 unresolved `LookupKey` identity 使用正式 resolution 字段。
  但 `_has_resolved_target(...)` 仍用 `bool(row.get("target_id"))` 和
  `str(row.get("resolution_status") or "")` 判定 resolved lane。
- 对 `EXACT` / `UNIQUE_BY_CONTEXT` 这类高置信 resolution，如果 `target_type` 缺失、空字符串或变成
  `MarketInstrument` 等非 Token Radar resolved target 类型，旧逻辑不会按事实损坏处理。它可能被降级成
  attention，或在部分组合下被当作 resolved lane 输入继续投影。
- 这会让 deterministic resolver 的“已解析目标”合同在 projection writer 里变成“只要有一点 target-like
  字段就尽量发布”，破坏 current-row lane 语义。

根因：

- resolved lane 是产品语义，不是显示层分类。成熟 Kappa/CQRS 中，`EXACT` / `UNIQUE_BY_CONTEXT`
  必须意味着 resolver 给出了可投影的正式 target identity；如果 target identity 不完整或类型不在
  Token Radar 的 resolved target 集合内，应该暴露 resolver/SQL hydration 损坏。
- 将坏高置信 row 降级为 attention 会掩盖 resolver 和 rank-source hydration 的错误：operator 看到的是
  “注意力行/市场缺失”，但真实问题是 material fact 与 projection contract 不一致。
- PostgreSQL 角度上，`target_type` / `target_id` 是 current-row key 与下游 fan-out 的输入，不是 nullable
  展示字段。宽松 truthy 判定会让 payload hash、lane、market gate 和 downstream dirty routing 的证据链断裂。

修复：

- `_has_resolved_target(...)` 改为接收已经验证过的 `resolution_status`。
- 对非高置信状态仍返回 attention；对 `EXACT` / `UNIQUE_BY_CONTEXT`，必须通过
  `_required_resolved_target_text(...)` 验证 `target_type` 和 `target_id`。
- `target_type` 只允许 `Asset` 或 `CexToken`；缺失抛
  `token_radar_projection_resolved_target_required:*`，空值/错误类型抛
  `token_radar_projection_resolved_target_invalid:*`。
- demoted Asset 仍保持既有 attention 语义；本次 hard-cut 只阻止 malformed 高置信 target identity 被静默降级或误投。

验证：

- RED：focused Token Radar high-confidence target contract 命令初始失败，`6 failed`。
- GREEN：同一 focused 命令通过，`6 passed`。
- Token Radar projection/publication-state/source-width 局部组合通过，`147 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root328 - Token Radar resolved Asset target 仍把缺失 `asset_identity_current` 解释洗成空 identity

发现：

- Root326/Root327 已经要求 Token Radar 使用正式 resolution 字段和高置信 target identity。
- 但 `_target(...)` 在构造 resolved `Asset` payload 时仍然用
  `row.get("asset_identity_reason_codes") or []` 和
  `row.get("asset_identity_conflict_count") or 0`。
- 这意味着 `token_radar_rank_source_events` 没有正确 join 到 `asset_identity_current`，
  或者 rank-source hydration 返回了错误字段形状时，当前行仍会显示成“没有 reason codes / 没有冲突”，
  而不是暴露 identity-current 链路损坏。

根因：

- `asset_identity_current` 是资产身份解释的当前事实，不是 target payload 的装饰字段。
  resolved `Asset` 已经进入产品 resolved lane，如果此时 identity confidence、selection reason codes
  和 conflict count 不完整，说明 resolver、rank-source edge hydration、schema/default 或 projection writer
  之间的合同断了。
- 成熟 Kappa/CQRS 里，缺 current row 和显式空 reason list 是不同状态。前者要靠 worker/rebuild/SQL
  边界修，后者才是 writer 有意输出的事实。读模型 writer 在投影时用 `[]` / `0` 修补，会让 payload hash、
  operator 调试和下游 Pulse/Profile/Narrative 解释链都误以为身份证据已经正常存在。
- PostgreSQL 角度上，`selection_reason_codes_json JSONB NOT NULL DEFAULT '[]'` 和
  `conflict_count NOT NULL DEFAULT 0` 是表约束/写入默认，不是读路径吞掉上游 join 缺口的许可。投影代码必须区分
  “DB 行明确写了空数组/0”和“hydrated row 缺列或类型错误”。

修复：

- `_project_group(...)` 调用 `_target(latest, resolved=resolved)`，把 resolved 上下文显式传入 target shaping。
- unresolved/no-target 状态不再在 `_target(...)` 内用 `"NIL"` 本地默认修复，而是复用已验证的
  `_required_resolution_text(...)`。
- resolved `Asset` payload 必须通过 `_required_asset_identity_text(...)`、
  `_required_asset_identity_list(...)` 和 `_required_asset_identity_int(...)` 读取
  `asset_identity_confidence`、`asset_identity_reason_codes` 和
  `asset_identity_conflict_count`。
- 缺字段抛 `token_radar_projection_asset_identity_required:*`；错类型、空 confidence 或负 conflict count 抛
  `token_radar_projection_asset_identity_invalid:*`。demoted/attention Asset 不强制要求 identity-current
  解释，但如果提供了部分坏字段仍会显性失败。

验证：

- RED：focused Token Radar resolved Asset identity contract 命令初始失败，`7 failed`。
- GREEN：同一 focused 命令通过，`7 passed`。
- Token Radar projection/publication-state/source-width 局部组合通过，`154 passed`。
- targeted ruff、mypy 和 production residual scan 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root329 - Token Radar target request / rank-source payload 仍把 legacy target alias 当成可修复输入

发现：

- Root318/319 已经把 current-row 下游 fan-out、Capture Tier hash、dirty enqueue 和 dirty completion 都切到
  formal `target_type_key` / `identity_id`。
- 但 `TokenRadarProjection._source_requests_for_targets(...)` 和
  `TokenRadarProjection._project_source_request(...)` 仍然用
  `target.get("target_type_key") or target.get("target_type")`、
  `target.get("identity_id") or target.get("target_id")` 来恢复目标身份。
- `TokenRadarRankSourceQuery._target_payloads(...)` 同样接受 `target_type` / `target_id`
  alias；`affected_targets_for_event_ids(...)` 对缺失 formal identity 的 SQL 输出会静默跳过。
- 结果是：dirty 队列入口已经 strict，但 rank-source repair、latest market context、source request generation
  这一层仍有第二个兼容入口，可以把 malformed target 变成“正常请求”或“空 repair work”。

根因：

- target request 是 projection 控制平面的命令，不是 public DTO。成熟 Kappa/CQRS 里，命令边界应该只接受一个
  canonical identity。alias mapping 可以发生在 producer/adaptor 的前置规范化阶段，但不能出现在 query helper
  或 projection helper 里。
- 这个漏洞会让同一条 target 在不同链路里拥有两种语义：dirty claim/done/error 使用 formal key，
  rank-source repair 和 target-feature delete/upsert 却可能从 legacy alias 取 key。这样会破坏 payload hash、
  target-feature stale delete、market-context overlay 和 downstream rank partition 的可解释性。
- PostgreSQL 角度上，`jsonb_to_recordset(%s::jsonb)` 的输入 payload 是临时请求表。它应该是强 schema 的
  参数集合，而不是“尽量修复”的 JSONB blob。缺 `target_type_key` / `identity_id` 时继续执行 SQL 或返回空列表，
  会把数据合同错误伪装成“没有受影响 target”，使索引/计划/行数诊断都看不见真正的坏输入。

修复：

- 新增 `_required_target_identity_text(...)`，`_project_source_request(...)` 在任何 projection/delete/upsert
  前验证 `target_type_key` 和 `identity_id`。
- `_source_requests_for_targets(...)` 不再接受 `target_type` / `target_id` alias，也不再静默跳过缺字段 target。
- `TokenRadarRankSourceQuery._target_payloads(...)` 新增 `_required_target_payload_text(...)`，用于
  `latest_market_context_for_targets(...)` 和 `populate_edges_for_targets(...)` 的 JSONB request payload。
- `latest_market_context_for_targets(...)` 和 `affected_targets_for_event_ids(...)` 对 SQL 输出的 formal target
  identity 也 fail-fast，避免把坏 query 输出洗成空 target key 或空受影响集合。

验证：

- RED：focused target request / rank-source payload contract 命令初始失败，`11 failed`；补充 latest-market-context
  输出侧 RED 初始失败，`2 failed`。
- GREEN：focused 与补充命令通过。
- Token Radar projection / rank-source query / publication-state / source-width 局部组合通过，`178 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root330 - Token Radar target-feature 私有缓存还原 current row 时仍会制造空 serving identity

发现：

- Root329 已经把 target request / rank-source payload 边界切成 formal identity。
- 但 `_row_from_target_feature(...)` 从 projection-private `token_radar_target_features` 构造
  `token_radar_current_rows` 时，`row_id`、`target_type_key` 和 `identity_id` 仍使用
  `str(row.get("target_type_key") or "")` / `str(row.get("identity_id") or "")`。
- 如果 target-feature 私有缓存行缺 formal identity，current-row shaping 不会失败，而是生成空 identity 段的
  row_id 和 serving key。legacy `target_type` / `target_id` 仍可能留在 row 上，造成“看起来有 target，
  但 formal current key 为空”的矛盾。

根因：

- `token_radar_target_features` 是 projection-private cache，但它仍是 current-row writer 的输入。
  私有缓存不等于弱 schema：一旦它参与 current publication，就必须遵守 serving identity contract。
- 成熟 Kappa/CQRS 中，private projection cache 可以 rebuild，但不能在 publish 时把 malformed cache row 洗成
  current row。否则会污染稳定 generation、payload hash、first-seen、Pulse/Narrative/Profile fan-out 和 API
  排序结果。
- PostgreSQL 角度上，空字符串不是“缺身份”的正确表达。它会绕过 Python 层异常，进入 deterministic id/hash
  计算，导致多个坏 row 在同一个空 key 空间里碰撞或被误判为正常 unchanged projection。

修复：

- `_row_from_target_feature(...)` 开始时通过 `_required_projection_row_text(row, "target_type_key")`
  和 `_required_projection_row_text(row, "identity_id")` 读取 formal identity。
- row_id、current row `target_type_key` / `identity_id`、以及缺 source intent 时的 `intent_id` fallback
  都复用已验证的 formal `identity_id`。
- legacy `target_type` / `target_id` 仍可作为展示/target payload context 留在 row 上，但不能替代 formal
  serving key。

验证：

- RED：focused target-feature current-row identity 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- Token Radar projection / rank-source query / publication-state / source-width 局部组合通过，`181 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root331 - Token Radar target-feature 还原 current row 时仍修补 row-id 维度和 factor snapshot

发现：

- Root330 已经要求 `_row_from_target_feature(...)` 必须有 formal `target_type_key` / `identity_id`。
- 但同一个 current-row shaping helper 仍然对 `projection_version`、`window`、`scope`、`lane` 使用
  `str(row.get(...) or "")`，对 `lane` 使用 `"attention"` 默认，对
  `latest_event_received_at_ms` 使用 `0`，对 `factor_snapshot_json` 使用 `{}`。
- 这意味着一个损坏的 `token_radar_target_features` 私有缓存行，仍能被发布成带空 row-id 段、
  默认 attention lane、零 source frontier、空 factor payload 的 current row。

根因：

- current-row key 不只由 target identity 决定；`projection_version/window/scope/lane/venue/target`
  一起构成产品窗口下的稳定行身份。缺任何一个维度都不是“可默认”，而是 projection-private cache contract
  损坏。
- `latest_event_received_at_ms` 驱动 source frontier、lag 和 publication offset；默认成 `0` 会把坏输入伪装成
  “很旧的事实”或空前沿，误导 worker 健康和 SQL 诊断。
- `factor_snapshot_json` 是 rank/current row 的核心 payload。把缺 snapshot 修成 `{}` 会绕过 payload/hash
  和解释链路，让 operator 看到的不是“projection 输入坏了”，而是一个缺解释的当前行。
- PostgreSQL 最佳实践上，JSONB 和时间戳字段的 NOT NULL / shape contract 应在 writer/read-model 边界显性验证。
  用 Python 层空值默认掩盖坏行，会让唯一键、UPSERT、payload hash 和 publication 状态都基于错误的规范化结果。

修复：

- `_row_from_target_feature(...)` 新增并使用 `_required_target_feature_current_row_text(...)` 读取
  `projection_version`、`window`、`scope`、`lane`。
- 新增 `_required_target_feature_current_row_mapping(...)`，要求 `factor_snapshot_json` 是非空 mapping。
- 新增 `_required_target_feature_current_row_int(...)`，要求 `latest_event_received_at_ms` 是非负 integer。
- row_id、lane、source frontier 和 factor payload 全部使用验证后的值，不再使用空串、`attention`、`0` 或 `{}` 默认。

验证：

- RED：focused target-feature current-row dimension/snapshot 命令初始失败，`9 failed`。
- GREEN：同一 focused 命令通过，`9 passed`。
- Token Radar projection / rank-source query / publication-state / source-width 局部组合通过，`190 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root332 - Token Radar rank-set selection 仍把坏 rank input 静默当成无可发布行

发现：

- Root331 已经要求 `_row_from_target_feature(...)` 在 current-row 构造时验证 target-feature 控制字段。
- 但 `_rank_current_rows(...)` 在进入 ranking 前仍然使用
  `int(row.get("latest_event_received_at_ms") or 0)` 做窗口过滤；缺最新事件时间的 rank input 会被当成
  `0`，然后静默作为过期行被排除。
- `_select_top_ranked_by_lane(...)` 仍用 `str(row.get("lane") or "") == lane` 选择 resolved/attention；
  缺 lane 或未知 lane 的 ranked row 会从两个 lane 都消失。

根因：

- rank-set selection 是 current publication 的最后一道门。它可以过滤真实过期行，但不能把 malformed
  private-cache row 当成“没有 rank input”。
- 成熟 CQRS/Kappa 里，空发布和坏输入是两种不同状态：空发布表示事实窗口内没有候选；坏输入表示 writer 或私有缓存合同破损。
  用 `0` 和空 lane 让坏输入消失，会把 projection failure 伪装成正常 empty/unchanged generation。
- PostgreSQL 诊断上，这会让 operator 只看到 `source_rows=0` 或少量 rows，而看不到是哪条 target-feature row
  缺时间/lane。source frontier、lag、row count 和 retry/error 记录都会失真。

修复：

- 新增 `_rank_input_latest_event_received_at_ms(...)`，要求 `latest_event_received_at_ms` 存在且是非负 integer。
- 新增 `_rank_input_lane(...)`，要求 `lane` 存在且只能是 `resolved` 或 `attention`。
- `_rank_current_rows(...)` 的 freshness filter 和 `_select_top_ranked_by_lane(...)` 的 lane grouping 都使用
  这些 helper，坏 rank input fail-fast，不再消失。

验证：

- RED：focused rank-set selection contract 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- Token Radar projection / rank-source query / publication-state / source-width 局部组合通过，`193 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root333 - Token Radar current-row `created_at_ms` 仍可由 runtime wall clock 补出

发现：

- Root331/332 已经把 target-feature current-row 构造和 rank-set selection 的关键字段切到 formal contract。
- 但 `_row_from_target_feature(...)` 的 `created_at_ms` 仍然使用
  `row.get("last_scored_at_ms") or row.get("updated_at_ms") or _now_ms()`。
- 当 target-feature 缺 `last_scored_at_ms` 时，current row 会从 `updated_at_ms` 或当前运行时 wall clock 得到
  时间戳，而不是暴露私有缓存行损坏。

根因：

- `created_at_ms` 是 public current row 的时间字段，不能由 publication 时刻临时决定。否则同一批 rank input 在不同
  worker attempt 中可能得到不同 current-row payload，破坏“可重放 projection”的基本假设。
- `updated_at_ms` 是私有 cache row 的存储更新时间，不等价于 scoring time；`_now_ms()` 更是 runtime attempt
  时间。把二者作为 public current row 时间 fallback，会把控制平面时间混入产品读模型。
- PostgreSQL 最佳实践上，timestamp fallback 应该发生在写入事实/私有缓存的明确 writer 边界，而不是在 read-model
  publication 时二次修补。否则 unchanged projection、payload hash、operator 时间诊断都会受到 wall clock 漂移影响。

修复：

- `_row_from_target_feature(...)` 通过 `_required_target_feature_current_row_int(row, "last_scored_at_ms")`
  读取 scoring time。
- `created_at_ms` 直接使用验证后的 `last_scored_at_ms`。
- 不再接受 `updated_at_ms` 或 `_now_ms()` 作为 current-row timestamp compatibility input。

验证：

- RED：focused target-feature current-row timestamp 命令初始失败，`3 failed`。
- GREEN：同一 focused 命令通过，`3 passed`。
- Token Radar projection / rank-source query / publication-state / source-width 局部组合通过，`196 passed`。
- targeted ruff 和 mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root334 - Token Radar target-feature cache writer 仍在替 malformed 投影行补默认

发现：

- Root330-333 已经把 `token_radar_target_features` 读回 current row 的路径切到 formal contract。
- 但写入私有缓存的 `TokenRadarRepository._target_feature_payload(...)` 仍然在入口处修补上游投影行：
  缺 `factor_snapshot_json` 变 `{}`，缺 `lane` 变 `attention`，缺
  `source_max_received_at_ms` 或 `created_at_ms` 变 `computed_at_ms`，缺
  `source_event_ids_json` 变 `[]`。
- 这意味着 malformed projection row 仍可能先被写进 `token_radar_target_features`，再由后续 current-row
  hard-cut 暴露，错误位置被推迟了一跳。

根因：

- `token_radar_target_features` 虽是 projection-private cache，但它不是“弱 schema 缓冲区”。它是 rank-set
  publication 的输入，应该保存投影 writer 已经确定的 lane、source frontier、source provenance、scoring time
  和 factor snapshot。
- repository writer 使用 `computed_at_ms`、`attention`、`[]`、`{}` 做补救，会把 writer contract 破损伪装成
  合法 cache row。成熟 Kappa/CQRS 的边界应该在 writer 入库前失败，而不是让私有缓存承载兼容语义。
- PostgreSQL 诊断上，这会污染 `latest_event_received_at_ms`、`created_at_ms` 和 payload hash。operator
  看到的是一条“看似可重放”的 cache row，但真实来源时间和 provenance 已经被写入时钟替代。

修复：

- `_target_feature_payload(...)` 改为先验证 `factor_snapshot_json`、`lane`、`source_max_received_at_ms`、
  `source_event_ids_json` 和 `created_at_ms`。
- `lane` 只能是 `resolved` 或 `attention`；时间字段必须是非负 integer；source event ids 必须是 list；
  factor snapshot 必须是非空 mapping。
- 缺字段统一报 `token_radar_target_feature_payload_required:*`，字段形状错误统一报
  `token_radar_target_feature_payload_invalid:*`。
- repository payload shaping 不再用 `attention`、`computed_at_ms`、`[]` 或 `{}` 修补投影输出。

验证：

- RED：focused target-feature payload writer 命令初始失败，单测 `9 failed`；架构 guard `1 failed`。
- GREEN：同一 focused 命令通过，`10 passed`。
- Token Radar repository 全文件通过，`40 passed`；publication-state hard-cut 架构文件通过，`28 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width 局部组合通过，`237 passed`。
- targeted ruff 和 repository mypy 通过；按当前用户指令，本轮不运行 integration-heavy gate。

### Root335 - Token Radar factor snapshot 核心评分字段仍可被 cache writer 降级成 `0/discard`

发现：

- Root334 已经要求 `_target_feature_payload(...)` 写入 `token_radar_target_features` 前必须有
  `factor_snapshot_json`、`lane`、source frontier、source event ids 和 `created_at_ms`。
- 但 `factor_snapshot_json` 内部的核心 score / decision / gate 字段还没有被正式契约钉住：
  `composite.rank_score` 缺失时 writer 会写成 `0.0`，`composite.recommended_decision` 或
  `gates.max_decision` 缺失时 writer 会写成 `discard`。
- 这让 malformed scoring output 看起来像“低分且丢弃”的合法投影结果，而不是上游评分链路断裂。

根因：

- 在 Kappa/CQRS 里，read model 可以重建，但不能在 cache writer 里重新解释业务决策。`rank_score`、
  `recommended_decision`、`max_decision` 是 scoring projection 的输出，不是 repository 能补的展示字段。
- `0.0` 和 `discard` 都是有业务含义的值。把缺失字段映射到这些值，会把“无事实”变成“事实为低信号/不推荐”，
  后续 payload hash、rank selection、Signal Pulse、notification 签名都会认为这是可重放的业务状态。
- PostgreSQL 侧的后果是诊断被误导：operator 看到的是有效 cache row 和稳定 hash，而不是失败在 scoring
  contract 的具体字段。成熟的 Kappa/CQRS 边界应该在 payload hash / SQL 之前让 malformed row 失败。

修复：

- 在 `factor_snapshot_contract` 中要求 `composite.rank_score`、`composite.recommended_decision`、
  `gates.max_decision`，并复用正式 Token Radar decision 集合 `discard/watch/high_alert`。
- `_target_feature_payload(...)` 直接从已验证的 `composite` 和 `gates` 读取核心字段；缺失或非法值在 SQL
  前失败，不再用 `_rank_score(...) or 0.0`、`raw_alpha_score` 兜底或 `discard` 默认。
- Signal Pulse / notification 测试 fixture 同步到合法 v3 factor snapshot：`max_decision` 是正式字段，
  不能再用 `alert` 这类非法枚举制造签名变化。

验证：

- RED：factor snapshot contract focused 命令初始失败，`3 failed`；target-feature core score/decision
  单测初始失败，`3 failed`；架构 guard 初始失败，`1 failed`。
- GREEN：同一 focused 组合通过，分别为 `3 passed`、`3 passed`、`1 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width /
  factor-snapshot-fallback 局部组合通过，`253 passed`。
- Notification rules 和 Signal Pulse service 局部组合中，先暴露旧 fixture 缺 `max_decision` / 使用非法
  `alert`，修正后通知规则 + Signal Pulse service 通过，`80 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；默认 uv cache 目录在沙箱内不可写，
  mypy 使用 `UV_CACHE_DIR=/private/tmp/parallax-uv-cache` 重跑通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root336 - Token Radar compact rank selection 仍把坏缓存输入降级成 `0/discard`

发现：

- Root335 已经让 target-feature cache writer 不再把缺失的 factor snapshot core fields 修成 `0.0` 或
  `discard`。
- 但 rank-set 重新排序路径仍然在读取 projection-private compact rank inputs 时保留兜底：
  `raw_composite_score` 缺失会经 `_display_score_from_value(row.get(...))` 变成 `0`，
  `gates_max_decision` 缺失会经 `row.get(...)` 和 `_decision_from_score_and_gates(...)` 变成
  `discard`，`_compact_rank_key(...)` 也会把缺 `rank_score` / `recommended_decision` 的 ranked row
  排成低优先级而不是失败。

根因：

- compact rank input 是 `token_radar_target_features` 私有缓存的 rank-set 入参，不是展示层 DTO。
  这里把缺字段当成低分/丢弃，会让旧坏缓存行悄悄参与窗口过滤、排序、publication hash 和 downstream
  fan-out。
- `discard` 不是“未知”，而是正式决策；`0.0` 也不是“缺分”，而是可排序的最低分。用它们作为缺失兜底，
  会把数据质量问题改写成业务判断，破坏 CQRS read model 的可重建性和可解释性。
- PostgreSQL 诊断上，坏行不会表现为明确的 rank input contract failure，而是表现为排序靠后或 no-op，
  operator 很难追到源头字段缺失。

修复：

- `rank_compact_inputs(...)` 在 fallback raw score 路径上改用 `_rank_input_display_score(row, "raw_composite_score")`，
  缺失或非法值直接报 `token_radar_rank_input_required/invalid:*`。
- `gates_max_decision` 通过 `_rank_input_decision(row, "gates_max_decision")` 读取，并且
  `_decision_from_score_and_gates(...)` 也要求 `max_decision` 是正式 `discard/watch/high_alert`。
- `_compact_rank_key(...)` 要求 ranked row 已有正式 `rank_score` 和 `recommended_decision`，不再自己修补
  `0.0` 或 `discard`。

验证：

- RED：compact rank input focused 单测初始失败，`4 failed`；架构 guard 初始失败，`1 failed`。
- GREEN：同一 focused 命令通过，`4 passed` 和 `1 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width / factor-snapshot fallback
  合并局部组合通过，`258 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；SDD validation 期间同步修正了因代码行号漂移
  造成的 Background citation 行号。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root337 - Token Factor Evaluation 仍把缺失 `rank_score` 计入 0 分桶

发现：

- `settle_token_factor_scores(...)` 会读取历史 `token_radar_current_rows.factor_snapshot_json`，再写入
  `token_score_evaluations` 作为评分诊断读模型。
- 该路径的 `_rank_score(...)` 仍然使用 `composite.get("rank_score") or 0.0`，并在类型转换失败时
  `return 0.0`。
- 因此一个 malformed v3 snapshot 缺少 `composite.rank_score` 时，不会暴露为坏投影输入，而会被写入
  `0-19` bucket。

根因：

- `token_score_evaluations` 虽是诊断读模型，但它的 bucket、IC、coverage 用来判断 scoring 质量。缺失
  score fact 不是“最低分”，而是上游 Token Radar scoring / publication contract 破损。
- `0.0` 是合法业务分数，不是 unknown sentinel。把缺失字段修成 `0.0` 会污染最低分桶，并让 Spearman
  IC、bucket coverage、family coverage 看起来像真实低信号样本。
- 从 Kappa/CQRS 角度，evaluation job 是读模型派生链路的一段 replay，不应该在 replay 时替上游事实补业务
  含义。成熟方案会让坏事实在消费边界失败，便于定位 writer contract，而不是把诊断结果静默降级。
- PostgreSQL 侧的后果是诊断表保存了稳定但错误的聚合输入：operator 无法从 SQL 结果判断这是缺失字段，
  只能看到一个合法低分 bucket。

修复：

- `settle_token_factor_scores(...)` 在 settle 单行前复用
  `require_token_factor_snapshot(..., field_name="factor_snapshot_json")`。
- `_rank_score(...)` 只读取已验证 snapshot 的 `composite["rank_score"]`，不再使用 `or 0.0` 或
  conversion-error 0 分 fallback。
- Token Factor Evaluation 单测 fixture 升级为完整 v3 factor snapshot，避免测试继续依赖旧的半结构 payload。
- 新增架构 guard，禁止 factor evaluation 路径重新引入缺失 `rank_score` 到 0 分桶的兼容逻辑。

验证：

- RED：focused Token Factor Evaluation 单测初始失败，`1 failed`；架构 guard 初始失败，`1 failed`。
- GREEN：同一 focused 命令通过，分别为 `1 passed` 和 `1 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`24 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width 局部组合通过，`245 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`269 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；残留 fallback 扫描只命中架构 guard
  的 forbidden-token literals。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root338 - Token Factor Evaluation 仍从 current-row 顶层身份修补坏 snapshot subject

发现：

- Root337 让 `settle_token_factor_scores(...)` 先校验 v3 `factor_snapshot_json` 并要求
  `composite.rank_score`。
- 但 `_settle_row(...)` 仍然用
  `subject.get("target_type") or row.get("target_type")` 和
  `subject.get("target_id") or row.get("target_id")` 来构造诊断样本身份。
- `_market_tick_target(...)` 也接收原始 row，并在 CEX 路径中重新从 `row.get("factor_snapshot_json")`
  做 `_mapping(...)`，保留了消费端二次修补入口。

根因：

- `token_score_evaluations` 要做价格结算，所以它需要一个可结算 subject identity；但这个要求属于
  evaluation 消费边界，不应错误扩大成全局 factor snapshot contract。未解析 attention row 可以是合法
  Token Radar snapshot，却不一定有 resolved asset target id。
- 对 evaluation 而言，缺 `subject.target_id` 不是普通 `missing_subject` bucket 样本，而是历史 Token Radar
  row 的 scoring payload 不适合被结算。用 current-row 顶层 `target_type/target_id` 回填，会把两个不同
  contract 混在一起：current-row serving identity 和 factor snapshot subject identity。
- 成熟 Kappa/CQRS 的 replay 诊断应该读取一个边界明确的 payload。跨层 fallback 会让损坏位置不可见：
  operator 只能看到一个被结算或被归因的样本，追不到 snapshot subject 本身缺字段。

修复：

- 在 Token Factor Evaluation 内新增 `_subject_identity(...)`，只接受 snapshot subject 的
  `target_type` 和 `target_id`，缺失时报
  `factor_snapshot_json.subject.target_type/target_id is required`。
- `_market_tick_target(...)` 改为接收已验证 snapshot 和 subject，不再接收原始 row，也不再二次
  `_mapping(row.get("factor_snapshot_json"))`。
- 保持全局 `require_token_factor_snapshot(...)` 不强制 `subject.target_id`，避免误伤合法 unresolved
  attention snapshots。
- Pulse worker 测试中残留的旧 `recommended_decision="low_info"` fixture 改为正式 `discard`，保持 Root335
  后的 decision contract 一致。

验证：

- RED：Token Factor Evaluation subject identity focused 单测初始失败，`1 failed`；架构 guard 初始暴露
  service fallback token。尝试全局 subject contract 后，broader Token Radar/Pulse 组暴露 unresolved
  attention 语义冲突，随后收窄为 evaluation 消费边界。
- GREEN：最终 focused subject identity 命令通过，`2 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`28 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width 局部组合通过，`245 passed`。
- Pulse candidate/job/API Signal Pulse 局部组合通过，`109 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`271 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；subject fallback 残留扫描只命中
  架构 guard 的 forbidden-token literals。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root339 - Token Factor Evaluation 仍把缺失结算时间降级成 epoch 0

发现：

- Root337/338 已经让 Token Factor Evaluation 使用正式 v3 snapshot、正式 `rank_score` 和 settlement-local
  subject identity。
- 但 `_settle_row(...)` 仍然使用 `int(row.get("computed_at_ms") or 0)` 作为市场入场时间、exit window
  起点、`sample_start_ms/sample_end_ms` 和 daily IC 分桶时间。
- 当历史 current row 缺顶层 `computed_at_ms`，或该字段和 snapshot provenance 漂移时，诊断 replay 会使用
  `0` 或错误顶层时间，而不是使用 v3 snapshot 自带的 `provenance.computed_at_ms`。

根因：

- v3 `factor_snapshot_json.provenance.computed_at_ms` 才是 scoring payload 的计算时间；Token Factor
  Evaluation 是 replay 这个 scoring payload 的诊断消费者。
- 顶层 `computed_at_ms` 是历史 row/query 形状的一部分，不应覆盖 snapshot provenance。用 `or 0` 修补会把
  “缺结算时间”变成合法 epoch 时间，污染 market lookup、sample range、daily IC 和 bucket 诊断。
- 成熟 Kappa/CQRS replay 要从同一个 payload 读取评分、身份和时间，以保证重放一致性。跨层时间 fallback 会让
  相同 snapshot 在不同 row 形状下得到不同结算结果。

修复：

- Token Factor Evaluation 新增 `_snapshot_computed_at_ms(...)`，从已验证 snapshot 的
  `provenance["computed_at_ms"]` 读取 settlement time。
- `_settle_row(...)` 不再读取 `row.get("computed_at_ms") or 0`。
- 新增单测证明缺顶层 `computed_at_ms` 时，market lookup、exit window、sample range 都使用 snapshot
  provenance time。
- 新增架构 guard 禁止 `row.get("computed_at_ms") or 0` 回到 evaluation 路径。

验证：

- RED：focused provenance-time 单测初始失败，market lookup 使用 `at_ms=0`；架构 guard 初始命中
  `row.get("computed_at_ms") or 0`。
- GREEN：同一 focused 命令通过，`2 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`28 passed`。
- Token Radar repository / projection / rank-source / publication-state / source-width 局部组合通过，`245 passed`。
- Pulse candidate/job/API Signal Pulse 局部组合通过，`109 passed`。
- Notification rules / Signal Pulse service 局部组合通过，`80 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`273 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；旧时间 fallback 扫描只在架构 guard
  和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root340 - Token Factor Evaluation 仍从 `composite.family_scores` 读取 family 诊断分数

发现：

- v3 factor snapshot contract 已经要求顶层 `families.<family>.score`，并把各 family 的 raw score、score、
  weight、facts 和 factors 作为正式 explainability payload。
- 但 `_family_scores(...)` 仍然读取 `snapshot.get("composite").get("family_scores")`。
- 这意味着一个合法 v3 snapshot 只要没有可选的 `composite.family_scores` alias，`family_rank_ic` 和
  `family_coverage` 就会把全部 family 分数当成缺失，诊断结果显示 `None` / `0.0 coverage`。

根因：

- `composite` 是最终决策聚合层，正式核心字段是 `rank_score` 和 `recommended_decision`；family 解释分数的
  正式归属是 `families.*.score`。
- 测试 fixture 同时写入了 `families.*.score` 和 `composite.family_scores`，掩盖了消费端读取旧 alias 的问题。
- 从 Kappa/CQRS 角度，诊断 replay 必须读取同一份正式 scoring payload。把 family diagnostics 绑到可选 alias
  会让合法事实在诊断读模型里看起来像缺失数据，误导 scoring 质量评估和 family coverage 判断。

修复：

- Token Factor Evaluation 的 `_family_scores(...)` 改为从已验证 snapshot 的 `families` 读取。
- 新增 `_family_score(...)`，直接读取 `families[family]["score"]`。
- 新增单测覆盖“合法 snapshot 无 `composite.family_scores` 但有正式 `families.*.score`”时，family IC 和
  coverage 仍正常计算。
- 新增架构 guard 禁止 evaluation 路径重新读取 `composite.family_scores`。

验证：

- RED：focused family-score 单测初始失败，`family_rank_ic.social_heat` 为 `None`；架构 guard 初始命中
  `composite.get("family_scores")` 和 `snapshot.get("composite")`。
- GREEN：同一 focused 命令通过，`1 passed` + `1 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`30 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`275 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；旧 alias 扫描只在架构 guard
  和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root341 - Token Factor Evaluation 仍用行情上下文修补 CEX 结算身份

发现：

- Root338 已经让 settlement subject identity 不再从 current-row 顶层字段修补。
- 但 `_market_tick_target(...)` 的 CEX 路径仍会读取
  `subject.get("provider") or decision_latest.get("provider")`，并允许
  `subject.get("native_market_id") or subject.get("instrument")`。
- 因此一个缺 `subject.provider` 的 CEX snapshot，可以被 `market.decision_latest.provider` 修补成
  `cex_symbol` 结算 key；一个缺 `subject.native_market_id` 的 snapshot，也可以被旧 `instrument` alias
  修补后进入 market tick lookup。

根因：

- CEX settlement key 是 subject market identity，不是行情上下文。`market.decision_latest` 是价格/市场
  observation payload，它可以说明行情新鲜度和价格值，但不能补足“这个样本应结算哪个 CEX instrument”。
- `instrument` 是旧字段语义；v3 subject 的正式字段是 `provider` + `native_market_id`。
- 成熟 Kappa/CQRS replay 应该让坏 subject 在消费边界变成 `missing_market_target`，而不是让 context
  payload 或 alias 把损坏隐藏成合法 settlement 样本。

修复：

- `_market_tick_target(...)` 的 CEX 分支只读取 `subject.provider` 和 `subject.native_market_id`。
- 删除 CEX settlement 路径对 `market.decision_latest.provider` 和 `subject.instrument` 的 fallback。
- `_market_tick_target(...)` 不再接收整个 snapshot，只接收已验证 subject，进一步减少二次读取 payload 的入口。
- 新增单测覆盖缺 subject provider / 缺 native market id 但有 fallback 信息时，样本保持 `missing_market_target`。
- 新增架构 guard 禁止 market-context provider 和 `instrument` alias 回到 evaluation settlement。

验证：

- RED：两个 focused CEX 单测初始都失败，`settled_count` 为 `1`；架构 guard 初始命中
  `decision_latest` provider 和 `instrument` alias fallback。
- GREEN：同一 focused 命令通过，三个目标分别 `1 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`33 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`278 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；旧 CEX fallback 扫描只在架构
  guard 和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root342 - Token Factor Evaluation 仍允许 market-tick subject type 直通结算

发现：

- Root338-341 已经把结算 score、subject id、时间、family diagnostics 和 CEX market key 都收回到正式
  `factor_snapshot_json`。
- 但 `_subject_identity(...)` 仍允许 `subject.target_type in {"chain_token", "cex_symbol"}`，并直接返回
  `target_id` 给 `_market_tick_target(...)`。
- 这让一条旧式 market-tick key 形态的 snapshot 可以绕过正式 Token Radar subject 合同，直接进入
  `latest_at_or_before(...)` / `first_between(...)` 行情结算。

根因：

- `chain_token` / `cex_symbol` 是 market tick 查询目标类型，不是 Token Radar score-evaluation 的业务
  subject 类型。
- 成熟 Kappa/CQRS replay 里，diagnostic consumer 应该先验证“被结算的产品主体”是正式 `Asset` 或
  `CexToken`，再从这个正式主体派生 market tick lookup key。
- 之前把 lookup key type 和 subject type 混在同一入口，等于允许旧事实形态继续作为兼容输入；这会削弱
  v3 factor snapshot 的 schema 边界，也让坏历史样本绕开 contract failure，污染 bucket、IC 和 coverage。

修复：

- `_subject_identity(...)` 现在只接受 `Asset` / `CexToken`；其他 `target_type` 统一失败为
  `factor_snapshot_json.subject.target_type is invalid`。
- `_market_tick_target(...)` 删除 direct `chain_token` / `cex_symbol` passthrough，只从正式 `Asset` /
  `CexToken` subject 派生 market tick lookup key。
- 新增单测覆盖 direct `chain_token` 和 direct `cex_symbol` subject，即使行情数据存在，也必须在 market
  lookup 和 upsert 前失败。
- 新增架构 guard 禁止 direct market-tick subject passthrough 回到 evaluation 路径。

验证：

- RED：focused direct-subject 命令初始失败两个参数化用例，direct `chain_token` / `cex_symbol` 未抛错；
  架构 guard 初始命中 passthrough token。
- GREEN：AC338 focused 命令通过，`3 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`35 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`280 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；旧 direct-subject passthrough 扫描只在
  架构 guard 和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root343 - Token Factor Evaluation 仍用 Asset subject 旧 alias 修补行情结算身份

发现：

- Root342 已经禁止 `chain_token` / `cex_symbol` 作为 score-evaluation subject 直通 market tick lookup。
- 但 `_market_tick_target(...)` 的 Asset 分支仍然读取
  `subject.get("chain") or subject.get("chain_id")` 和
  `subject.get("address") or subject.get("asset_address")`。
- 因此一个缺正式 `subject.chain` 或 `subject.address` 的 Asset snapshot，只要带着旧 `chain_id` /
  `asset_address` alias，仍会被修补成 `chain_token` lookup key 并完成结算。

根因：

- `chain` / `address` 是 v3 factor snapshot subject 里的正式 Asset market identity；`chain_id` /
  `asset_address` 是投影输入或旧 payload 里的兼容字段。
- 成熟 Kappa/CQRS replay 应该让 consumer 只读 writer 已经规范化后的正式 payload。消费端继续读取 alias，
  等于给历史/坏 snapshot 留了第二套 schema，削弱了“projection writer 负责规范化，diagnostic replay
  负责验证和消费”的边界。
- 这类 alias fallback 会把“缺正式结算市场身份”的样本伪装成合法已结算样本，污染 score bucket、IC 和
  coverage，同时让 schema 漂移更难被观察到。

修复：

- `_market_tick_target(...)` 的 Asset 分支只读取 `subject.chain` 和 `subject.address`。
- 删除 score-evaluation settlement 对 `subject.chain_id` 和 `subject.asset_address` 的 fallback。
- 新增参数化单测覆盖缺 `chain` 但有 `chain_id`、缺 `address` 但有 `asset_address`，两者都必须成为
  `missing_market_target`，且不得触发行情查询。
- 新增架构 guard 禁止 Asset subject market identity alias fallback 回到 evaluation 路径。

验证：

- RED：focused Asset alias 命令初始失败两个参数化用例，`settled_count` 为 `1`；架构 guard 初始命中
  `chain_id` / `asset_address` fallback。
- GREEN：AC339 focused 命令通过，`3 passed`。
- Token Factor Evaluation + factor-snapshot fallback 架构组合通过，`38 passed`。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`283 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；旧 Asset alias fallback 扫描只在
  架构 guard 和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root344 - Token Radar Projection 仍保留 retired snapshot-row 排序兼容 helper

发现：

- AC332 已经把 rank-set publication 收到 compact rank input 合同：`raw_composite_score`、
  `gates_max_decision`、ranked `rank_score` 和 `recommended_decision` 都必须是正式字段。
- 但 `token_radar_projection.py` 里仍保留旧 `_rank_key(...)`，它会吞掉 invalid factor snapshot，把坏行
  排到 `(3, 0.0, 0, 0, 0)`。
- 同一文件还保留 `_display_score_from_value(...)`、`_factor_snapshot_for_ranking(...)` 和
  `_raw_composite_score(...)`，其中 `_raw_composite_score(...)` 仍从 `composite.raw_alpha_score` fallback
  并 clamp 到 0-100。

根因：

- 这些 helper 已经不在生产调用链里，但它们仍表达了一套旧排序语义：invalid snapshot 可以降级排序，
  缺 `rank_score` 可以用 `raw_alpha_score` 或 `0.0` 修补。
- 对 Kappa/CQRS read model 来说，死代码里的兼容语义也有风险：后续维护者很容易把它重新接回 rank
  publication，绕开 compact rank input 的正式 contract。
- 成熟架构里，旧入口和旧 helper 要一起删除；否则“当前主路径正确”会和“代码库仍保留备用旧路径”并存，
  审计时无法证明没有第二套行为。

修复：

- 删除 retired `_rank_key(...)`、`_display_score_from_value(...)`、
  `_factor_snapshot_for_ranking(...)`、`_raw_composite_score(...)`。
- 删除只为旧 `_rank_key(...)` 存在的单测 import 和直接单测。
- 新增架构 guard，禁止这些 retired helper、`raw_alpha_score` fallback、invalid-snapshot demotion 回到
  Token Radar projection。

验证：

- RED：新增架构 guard 初始失败，命中 6 个 retired helper/fallback token。
- GREEN：同一架构 guard 通过，`1 passed`；compact ranking focused 组合通过，`6 passed`。
- Token Radar projection / publication-state 组合通过，实际计数记录在 SDD verification。
- 合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，实际计数记录在 SDD verification。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；retired helper/fallback 扫描只在
  架构 guard 和文档说明中命中，生产代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root345 - Token Radar Projection patch 阶段仍修补 ranked-row metadata

发现：

- Root344 删除了 retired snapshot-row 排序 helper 后，rank publication 已经只剩 compact rank input +
  `_compact_rank_key` 主路径。
- 但 `_patch_ranked_current_row(...)` 仍在最后发布 current row 时修补 ranked-row metadata：
  `normalization_status` 缺失会变成 `no_signal`，`cohort_status` 缺失会变成 `not_ranked`，
  `cohort_size`、`rank`、`latest_event_received_at_ms` 会变成 `0`，`factor_ranks` 会变成空 map。
- 同一 patch 阶段还直接读取 `rank_score` / `recommended_decision`，没有先区分“ranker 正式输出了字段”
  和“ranked row 根本是 malformed”。

根因：

- 成熟 Kappa/CQRS 里，ranked compact row 是一个正式中间投影输出；current-row patch 只能消费它，不能
  在发布边界重新解释缺失字段。
- `no_signal` / `not_ranked` 是合法业务状态，不是缺字段时的兼容默认值。把 malformed ranked row 修成这些
  状态，会把上游 rank-source / normalizer / rank publication 的合同破裂隐藏成稳定的 serving row。
- source watermark `0` 尤其危险：它让 current-row/frontier 看起来有确定来源，但实际上失去了真实
  `latest_event_received_at_ms`，后续 freshness、fan-out、capture-tier dirty hash 都会基于假边界运行。

修复：

- 新增 ranked-row metadata 校验 helper：缺字段报 `token_radar_ranked_row_required:*`，形状/枚举错误报
  `token_radar_ranked_row_invalid:*`。
- `_patch_ranked_current_row(...)` 在修改 current row 或 `factor_snapshot_json` 前要求
  `normalization_status`、`cohort_status`、`cohort_size`、`cohort_metadata`、`factor_ranks`、`rank`、
  `rank_score`、`recommended_decision`、`latest_event_received_at_ms` 都来自正式 ranked row。
- `rank_score` 和 `recommended_decision` 继续复用 rank-input 数值/decision 校验；缺失先作为 ranked-row
  metadata 缺失失败，非法值作为 rank-input invalid 失败。
- 新增架构 guard，禁止恢复 `no_signal` / `not_ranked` / rank `0` / source watermark `0` / 空 rank map
  patch 默认值。

验证：

- RED：新增 Root345 聚焦命令初始失败，18 个 unit case 和 1 个 architecture guard 失败，证明旧 patch
  阶段仍接受缺失/非法 ranked metadata。
- GREEN：同一聚焦命令通过，`19 passed`；Token Radar projection / publication-state 组合通过，
  `190 passed`；合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`301 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；ranked-row 默认修补残留扫描只在
  架构 guard、生产错误码 helper 和文档说明中命中，生产默认修补代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root346 - Token Radar Projection normalized rank payload 仍有局部默认解释

发现：

- Root345 让 `_patch_ranked_current_row(...)` 要求了大部分 ranked-row metadata，但 normalized rank payload
  里仍有三个局部洞：
  - `cohort_in_cohort` 通过 `ranked.get("cohort_in_cohort") is True` 读取，缺失或非法值都会变成 `False`。
  - `alpha_rank` 通过 `ranked.get("alpha_rank")` 读取，缺失会变成 `None`。
  - `factor_ranks` 只校验为 mapping；缺 family 会跳过该 family 的 score 更新，非法字符串会走到
    `float(rank)`，越界值如 `2.0` 可能写入异常 family score。

根因：

- `cohort_in_cohort=False` 和 `alpha_rank=None` 都是合法业务含义：前者表示正式判定不在 cohort，后者表示
  正式 no-signal / 不可排名。它们不能同时当作缺字段 fallback。
- `factor_ranks` 是 cross-section normalizer 的正式输出，不是 best-effort hint。少一个 family 或 rank
  值越界，说明 normalizer 输出损坏；patch 层如果静默跳过，会让 current row 的 family score 混用旧 raw score
  和新 normalized score。
- 对成熟 Kappa/CQRS 来说，normalized rank payload 是 read-model publication 的中间事实包；current-row patch
  只能验证和消费，不能再做“能算多少算多少”的兼容解释。

修复：

- 新增 `_ranked_row_bool(...)`、`_ranked_alpha_rank(...)`、`_ranked_factor_ranks(...)`。
- `cohort_in_cohort` 必须是 bool；缺失报 `token_radar_ranked_row_required:cohort_in_cohort`，非法报
  `token_radar_ranked_row_invalid:cohort_in_cohort`。
- `alpha_rank` 必须存在；`normalization_status="ranked"` 时必须是 `0..1` 数字，
  `normalization_status="no_signal"` 时必须是 `None`。
- `factor_ranks` 必须精确包含所有 Token Radar factor family；每个值必须是 `None` 或 `0..1` 数字。
- patch 阶段不再通过 `ranked.get("cohort_in_cohort") is True`、`ranked.get("alpha_rank")` 或
  `float(rank)` 修补/解释 normalized payload。

验证：

- RED：新增 Root346 聚焦命令初始失败，10 个 failure，证明旧 patch 阶段仍接受缺失/非法 membership、
  alpha rank 和 family rank map，且非法 rank 字符串会冒出非合同化 `ValueError`。
- GREEN：同一聚焦命令通过，`11 passed`；Token Radar projection / publication-state 组合通过，
  `201 passed`；合并后的非集成 Token Radar / Token Factor Evaluation 局部组合通过，`312 passed`。
- targeted ruff、mypy、SDD validation/index、`git diff --check` 通过；normalized-rank fallback 残留扫描只在
  架构 guard、生产错误码/helper 调用和文档说明中命中，生产 fallback 代码不再命中。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root347 - Token Radar Repository 写入计数仍默认估算 PostgreSQL rowcount

发现：

- CEX board/detail/derivative-series repository 已经要求真实 `cursor.rowcount` 证据。
- 但 `TokenRadarRepository.publish_current_generation(...)` 仍在 current-row upsert 后使用
  `getattr(cursor, "rowcount", 1)`，缺失 rowcount 会被记成一行 serving-row 写入。
- 同一 repository 的 current-row delete、target-feature write/delete、target-feature retention prune 仍使用
  `getattr(cursor, "rowcount", 0)`，缺失 rowcount 会被记成无写入。

根因：

- Kappa/CQRS 的关键审计信号之一是“unchanged projection 写 0 serving rows”。这个数字必须来自
  PostgreSQL 冲突更新和删除语句的实际结果，而不是 repository 对 driver 行为的乐观估算。
- `rowcount=1` 默认尤其危险：当 cursor/fake/driver 合同漂移时，系统会把“没有 PostgreSQL 写入证据”当成
  “已经写入一行 current row”，掩盖 SQL `IS DISTINCT FROM` no-op gate、测试 fake、事务边界或 driver wrapper
  的错误。
- `rowcount=0` 默认也不是安全的：它会把缺失证据伪装成 no-op，让 target-feature retention、delete 和 cache
  upsert 的写放大/无写入审计失真。
- 成熟架构里，写入计数是 observability contract，不是 convenience return value；缺失或非法 rowcount 应该
  作为 repository/driver wiring 错误暴露。

修复：

- 新增 `_cursor_rowcount(cursor)`，直接读取 `cursor.rowcount`。
- 缺失 rowcount 抛 `token_radar_repository_rowcount_required`。
- bool、负数、不可转整数等非法 rowcount 抛 `token_radar_repository_rowcount_invalid`。
- current-row delete/upsert、target-feature write/delete、target-feature retention prune 全部改为调用该 helper。
- 新增单测覆盖 current-row upsert 缺失/非法 rowcount，以及 target-feature write 缺失/非法 rowcount。
- 新增架构 guard 禁止 `TokenRadarRepository` 恢复 `getattr(cursor, "rowcount", 0/1)` 默认估算。

验证：

- RED：新增 focused rowcount 命令初始失败 3 个 case，证明缺失 rowcount 被当成一行写入，非法 rowcount 冒出
  普通 `ValueError`，架构 guard 命中默认 rowcount 读取。
- GREEN：focused rowcount 命令通过，`5 passed`；Token Radar repository / publication-state architecture 组合
  通过，`80 passed`。
- 更宽的非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root348 - Token Radar dirty queue 写入计数仍默认缺失 rowcount 为 0

发现：

- Root347 收紧了 current-row / target-feature serving 写入计数，但 `token_radar_dirty_targets` 和
  `token_radar_source_dirty_events` 两个 dirty queue repository 仍在多处 mutation 后使用
  `getattr(cursor, "rowcount", 0)`。
- 目标 dirty queue 的 market enqueue、done、error、catch-up/repair enqueue 等路径，以及 source dirty queue 的
  done/error completion 路径，都可能把缺失 `cursor.rowcount` 解释成 “0 行 changed”。

根因：

- dirty queue 在 Kappa/CQRS 中是 projection 控制面，不是普通辅助表。它的 enqueue、completion、retry、
  catch-up 计数是 worker 判断 backlog、lease、失败重试和 repair 是否真正落库的重要可观测信号。
- 默认 `0` 看似保守，实际会隐藏 repository fake、driver wrapper 或事务边界漂移：系统会把“没有 PostgreSQL
  DML 结果证据”误读为“这次确实没有 dirty work 被写入/完成”。
- 这会让 worker 链路的 stale read model 问题更难定位：读模型没更新时，日志和统计可能显示队列写入为 0，
  但真实原因是写入证据缺失，而不是 SQL no-op。

修复：

- `token_radar_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`，直接读取 `cursor.rowcount`。
- 缺失 rowcount 抛 `token_radar_dirty_target_rowcount_required`；bool、负数、不可转整数等非法 rowcount 抛
  `token_radar_dirty_target_rowcount_invalid`。
- `token_radar_source_dirty_event_repository.py` 增加同类 helper，缺失/非法错误码分别为
  `token_radar_source_dirty_event_rowcount_required` 和 `token_radar_source_dirty_event_rowcount_invalid`。
- 所有返回 changed-row count 的 target/source dirty mutation 路径改为调用 helper；架构 guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused dirty-queue rowcount 命令初始失败 8 个 case，证明缺失 rowcount 被当成 0 行 changed，
  非法 rowcount 冒出非合同化转换错误，架构 guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`8 passed`；Token Radar dirty queue / source-width 组合通过，`72 passed`。
- 更宽的非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root349 - Token Radar rank-source edge mutation count 仍把缺失 SQL 证据当成 0

发现：

- `TokenRadarRankSourceQuery.populate_edges_for_event_ids(...)` 和
  `populate_edges_for_targets(...)` 通过 SQL CTE 返回 `upserted_count` / `deleted_count`，但旧代码使用
  `(row or {}).get("...") or 0` 累计 changed rows。
- 如果 `fetchone()` 没有返回 count row、返回 row 缺列、或 count 值非法，旧逻辑会把缺失值解释成 0，
  或冒出非合同化 `ValueError`。
- `prune_edges(...)` 也仍使用 `getattr(cursor, "rowcount", 0)`，缺失 DELETE rowcount 会被记成无 prune。

根因：

- `token_radar_rank_source_events` 是 projection-private edge 表，但它直接决定 target-feature 和 current-row 的输入集合。
  edge population / stale-edge delete / retention prune 的 changed-row count 是投影是否真的更新 source packet 集合的审计证据。
- 成熟 Kappa/CQRS 里，unchanged edge set 可以写 0 行，但这个 0 必须来自 PostgreSQL SQL aggregate 或 DML
  `rowcount`，不能来自 Python 对缺失结果的默认值。
- 默认 0 会把 SQL shape、driver row factory、fake cursor、事务 wrapper 漂移隐藏成“rank-source 没变化”，后续 current-row
  stale 时很难区分是真 no-op 还是 edge maintenance 没有可验证执行。

修复：

- populate 路径新增 `_mutation_count_result(...)` 和 `_required_mutation_count(...)`，要求 SQL count row 存在，
  且 `upserted_count` / `deleted_count` 是非 bool、非负整数。
- prune 路径新增 `_cursor_rowcount(cursor)`，要求真实 PostgreSQL cursor rowcount。
- 缺失 count row 抛 `token_radar_rank_source_write_count_required:*`；非法 count 抛
  `token_radar_rank_source_write_count_invalid:*`；缺失/非法 prune rowcount 抛
  `token_radar_rank_source_rowcount_required/invalid`。
- 架构 guard 禁止恢复 `(row or {})`、count `.get(... ) or 0` 和 `getattr(cursor, "rowcount", 0)`。

验证：

- RED：focused rank-source mutation-count 命令初始失败 17 个 case，证明缺失/非法 SQL count 证据和 prune
  rowcount 会被默认或非合同化报错。
- GREEN：同一 focused 命令通过，`17 passed`；Token Radar rank-source/projection/source-width 非集成组合通过，
  `356 passed`。
- targeted ruff、mypy 通过；更宽的 SDD/static/residual 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root350 - Pulse dirty-trigger completion count 仍把缺失 rowcount 当成 0

发现：

- `PulseTriggerDirtyTargetRepository.mark_done(...)`、`mark_error(...)` 和 `reschedule(...)` 在 DELETE/UPDATE
  后使用 `int(getattr(cursor, "rowcount", 0) or 0)` 返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 行完成或重排；字符串 rowcount 会冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `pulse_trigger_dirty_targets` 是 Signal Pulse 的 projection 控制面。done/error/reschedule 的计数决定 worker
  是否真的释放、重试或延后了 dirty trigger。
- 对成熟 Kappa/CQRS 来说，dirty target completion 不是“尽力而为”的统计值，而是 worker 链路的执行证据。
  0 行 changed 可以是真正的 stale completion token/no-op，但必须由 PostgreSQL 证明。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有 Pulse dirty work 被完成”，
  让 Pulse candidate stale/backlog 问题在日志和指标里变成假 no-op。

修复：

- `pulse_trigger_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `pulse_trigger_dirty_target_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `pulse_trigger_dirty_target_rowcount_invalid`。
- done/error/reschedule 三个 completion mutation 全部改为调用该 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 Pulse architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused Pulse dirty-trigger rowcount 命令初始失败 13 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 没有合同化失败，架构 guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`13 passed`。
- 后续非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root351 - Narrative Admission dirty-target completion count 仍把缺失 rowcount 当成 0

发现：

- `NarrativeAdmissionDirtyTargetRepository.mark_done(...)`、`mark_error(...)` 和 `reschedule(...)` 在 DELETE/UPDATE
  后仍使用 `int(getattr(cursor, "rowcount", 0) or 0)` 返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 行完成或重排；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `narrative_admission_dirty_targets` 是 `NarrativeAdmissionWorker` 的控制面。它决定哪些 Token Radar
  current rows 被重新 exact-load 并写入 `narrative_admissions`。
- done/error/reschedule 的 changed-row count 是 worker 是否真的释放、重试或延后 dirty claim 的执行证据，
  不是普通 convenience return value。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有 Narrative dirty
  target 被完成”，让 stale admission 或 backlog 问题在日志和指标里变成假 no-op。

修复：

- `narrative_admission_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `narrative_admission_dirty_target_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `narrative_admission_dirty_target_rowcount_invalid`。
- done/error/reschedule 三个 completion mutation 全部改为调用该 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused Narrative dirty-target rowcount 命令初始失败 13 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 没有合同化失败，架构 guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`13 passed`。
- 后续非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root352 - News projection dirty-target completion count 仍把缺失 rowcount 当成 0

发现：

- `NewsProjectionDirtyTargetRepository.mark_done(...)` 和 `mark_error(...)` 在 DELETE/UPDATE 后仍使用
  `int(getattr(cursor, "rowcount", 0) or 0)` 返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 行完成或重试；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `news_projection_dirty_targets` 是 `NewsPageProjectionWorker` 和 `NewsSourceQualityProjectionWorker` 的控制面。
  done/error 的计数决定 worker 是否真的释放或重试了 page/source-quality dirty target。
- 在 Kappa/CQRS 中，News page/source-quality projection 的 correctness 依赖 durable dirty queue 与
  `RepositorySession.transaction`，changed-row count 是执行证据，不是 convenience return value。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有 News dirty target
  被完成/重试”，让 stale News page rows 或 source-quality backlog 在日志和指标里变成假 no-op。

修复：

- `news_projection_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `news_projection_dirty_target_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `news_projection_dirty_target_rowcount_invalid`。
- done/error 两个 completion mutation 全部改为调用该 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 News architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused News dirty-target rowcount 命令初始失败 9 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 没有合同化失败，架构 guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`9 passed`；News dirty-target/projection architecture 组合通过，`87 passed`。
- targeted ruff、mypy 通过；更宽的 SDD/static/residual 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root353 - Notification insert 状态机用裸 rowcount 判定 created/existing

发现：

- `NotificationRepository.insert_notification_with_outcome(...)` 在 `INSERT INTO notifications ... ON CONFLICT DO NOTHING`
  后直接使用 `if cursor.rowcount == 0:` 决定进入既有通知聚合路径。
- `NotificationRepository.enqueue_delivery(...)` 在 `INSERT INTO notification_deliveries ... ON CONFLICT DO NOTHING`
  后也直接使用 `if cursor.rowcount == 0:` 决定 insert-only delivery 是否已存在。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现冒出未合同化的 `AttributeError`；字符串、bool、负数或多行
  rowcount 会被当成“插入成功”，从而错误分类通知事实或投递控制状态。

根因：

- `notifications` 是通知事实表，`notification_deliveries` 是外部投递控制面。`INSERT ... DO NOTHING` 的
  rowcount 在这里不是普通日志指标，而是决定“新事实 / 既有事实聚合 / 新投递 / 已有投递”的状态机证据。
- 成熟 Kappa/CQRS 的写侧状态分类必须来自 PostgreSQL 执行证据。`0` 可以代表真实冲突/no-op，但只能在
  PostgreSQL 单行 rowcount 证明后成立。
- 裸 `cursor.rowcount == 0` 没有验证 rowcount 的存在、类型和单行语义，会把 driver wrapper、测试 fake、
  autocommit 边界或 SQL 执行结果漂移隐藏成业务状态，使重复聚合、外部 push requeue/insert-only 语义和投递
  backlog 诊断出现假象。

修复：

- `notification_repository.py` 新增 `_single_row_write_count(...)`。
- 通知事实 insert 缺失 rowcount 抛 `notification_insert_rowcount_required`，非法 rowcount 抛
  `notification_insert_rowcount_invalid`。
- insert-only delivery enqueue 缺失 rowcount 抛 `notification_delivery_enqueue_rowcount_required`，非法 rowcount 抛
  `notification_delivery_enqueue_rowcount_invalid`。
- 允许的 rowcount 只保留 PostgreSQL `INSERT ... DO NOTHING` 单行语义：`0` 或 `1`；bool、负数、多行、
  非整数或缺失 evidence 均失败。
- 新增单测覆盖缺失、字符串、bool、负数和 `2` rowcount；新增 Notification architecture guard 禁止恢复
  裸 `cursor.rowcount == 0` 或默认 rowcount 兼容读取。

验证：

- RED：focused Notification rowcount 命令初始失败 11 个 case，证明缺失 rowcount 未合同化，非法 rowcount
  被当成创建成功，architecture guard 命中裸 rowcount 判定。
- GREEN：同一 focused 命令通过，`11 passed`。
- 后续非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root354 - SignalRepository watched-account alert insert 用裸 rowcount 判定 created/existing

发现：

- `SignalRepository.insert_account_token_alert(...)` 在
  `INSERT INTO account_token_alerts ... ON CONFLICT DO NOTHING` 后直接用
  `if cursor.rowcount == 0:` 判定“既有 alert / 新建 alert”。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现冒出未合同化的
  `AttributeError`；字符串、bool、负数或多行 rowcount 会被当成“插入成功”，从而错误分类
  watched-account alert 事实状态。

根因：

- `account_token_alerts` 虽然由 ingest 写入，但它不是临时 UI 派生物；它被 WebSocket event
  payload、`/api/notifications/account-alerts`、CLI read-model、account-quality/notification 读面消费。
- `INSERT ... DO NOTHING` 的 rowcount 在这里是事实写入状态机证据：`0` 只能代表 PostgreSQL
  证明了 conflict/no-op，`1` 才代表新 alert fact。
- 裸 `cursor.rowcount == 0` 没有验证 rowcount 的存在、类型和单行语义，会把驱动包装、测试 fake
  或事务边界漂移隐藏成业务状态。成熟 Kappa/CQRS 下，这类事实写入分类必须 fail closed，而不是由
  Python 对象宽松 truthiness 决定。

修复：

- `signal_repository.py` 新增 `_single_row_write_count(...)`。
- 缺失 rowcount 抛 `signal_repository_rowcount_required`。
- bool、负数、多行或非整数 rowcount 抛 `signal_repository_rowcount_invalid`。
- 允许的 rowcount 只保留 PostgreSQL 单行 `INSERT ... DO NOTHING` 语义：`0` 或 `1`。
- 新增单测覆盖缺失、字符串、bool、负数和 `2` rowcount；扩展 architecture guard 禁止恢复裸
  `cursor.rowcount == 0` 或默认 rowcount 兼容读取。

验证：

- RED：focused SignalRepository rowcount 命令初始失败 6 个 case，证明缺失 rowcount 未合同化，
  非法 rowcount 被当成创建成功，architecture guard 命中裸 rowcount 判定。
- GREEN：同一 focused 命令通过，`6 passed`。
- 后续非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root355 - ProjectionRepository stale-running cleanup 把缺失 rowcount 当成 0 个 abandoned run

发现：

- `ProjectionRepository.mark_stale_running_runs(...)` 在
  `UPDATE projection_runs SET status = 'abandoned' ...` 后使用
  `int(getattr(result, "rowcount", 0) or 0)` 返回 abandoned run 数。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 stale run；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `projection_runs` 是 Token Radar projection 控制面。stale-running cleanup 的返回值不是普通日志数字，
  而是 projection worker 是否真的把超时 running run 标记为 abandoned 的执行证据。
- 默认 0 会把 driver wrapper、事务边界或 SQL 执行结果契约漂移隐藏成“没有 stale run”，使 projection
  运行状态、失败恢复和 freshness 诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 需要保留“没有行需要变更”和“没有执行证据”之间的差异。前者是
  PostgreSQL rowcount=0，后者必须 fail closed。

修复：

- `projection_repository.py` 新增 `_cursor_rowcount(...)`。
- 缺失 rowcount 抛 `projection_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `projection_repository_rowcount_invalid`。
- `mark_stale_running_runs(...)` 改为只通过该 helper 返回 abandoned-run count。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(result, "rowcount", 0)` 默认 zero-run accounting。

验证：

- RED：focused ProjectionRepository rowcount 命令初始失败 5 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`5 passed`。
- 后续非集成、静态、SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root356 - NewsRepository 普通写路径把缺失 rowcount 当成 0 个 changed row

发现：

- `NewsRepository` 的 item lifecycle、source-quality status、page-row mutation 路径仍使用
  `getattr(cursor, "rowcount", 0)`、`int(getattr(cursor, "rowcount", 0) or 0)` 或
  `cursor.rowcount or 0` 返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 行变更；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- 这些返回值直接影响 News writer/projection worker 对“处理完成、需要重试、source quality 是否变化、page rows
  是否删除”的判断。它们不是普通日志数字，而是 PostgreSQL DML 执行证据。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有变化”，造成 News
  页面投影、source-quality dirty enqueue、processing recovery 出现假象。
- 成熟 Kappa/CQRS 下，`rowcount=0` 和“没有 rowcount 证据”必须保留语义差异：前者是数据库证明的 no-op，
  后者是 repository/driver 契约破损，必须 fail closed。

修复：

- `news_repository.py` 新增 `_cursor_rowcount(...)`。
- 缺失 rowcount 抛 `news_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `news_repository_rowcount_invalid`。
- item lifecycle、source-quality status update、page-row delete/replace changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 和 `cursor.rowcount or 0` 默认 zero-row accounting。

验证：

- RED：focused NewsRepository rowcount 命令初始失败 5 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`5 passed`。
- NewsRepository/source-quality/architecture 非集成组通过，`148 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root357 - Asset Profile Refresh target completion 把缺失 rowcount 当成 0 个 refresh target

发现：

- `AssetProfileRefreshTargetRepository.reschedule(...)` 和 `mark_error(...)` 在更新
  `asset_profile_refresh_targets` 后使用 `int(getattr(cursor, "rowcount", 0) or 0)` 返回
  changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 target 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `asset_profile_refresh_targets` 是 DEX profile source-cache 的控制面。reschedule/error count 影响 worker
  对 provider profile refresh 目标是否真正完成重排或重试的判断。
- 默认 0 会把 driver wrapper、测试 fake 或 SQL 执行结果契约漂移隐藏成“没有目标被更新”，导致 profile
  refresh retry/due_at 诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。

修复：

- `asset_profile_refresh_target_repository.py` 新增 `_cursor_rowcount(...)`。
- 缺失 rowcount 抛 `asset_profile_refresh_target_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `asset_profile_refresh_target_rowcount_invalid`。
- reschedule/error completion changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-target accounting。

验证：

- RED：focused Asset Profile Refresh target rowcount 命令初始失败 5 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`5 passed`。
- Asset Profile Refresh target 非集成组通过，`12 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root358 - Token Profile Current dirty completion 把缺失 rowcount 当成 0 个 profile target

发现：

- `TokenProfileCurrentDirtyTargetRepository.mark_done(...)` 和 `mark_error(...)` 在删除/更新
  `token_profile_current_dirty_targets` 后仍使用默认 rowcount 语义返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 target 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `token_profile_current_dirty_targets` 是 public token profile/icon current-row projection 的控制面。done/error
  count 不是普通日志数字，而是 worker 是否真的消费、重试或释放 profile-current dirty target 的执行证据。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有目标被更新”，导致
  profile current 刷新滞后、logo dirty fan-out、public pending/error 状态诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者是 stale completion token 或真正 no-op，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `token_profile_current_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `token_profile_current_dirty_target_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `token_profile_current_dirty_target_rowcount_invalid`。
- done/error completion changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-target accounting。

验证：

- RED：focused Token Profile Current dirty rowcount 命令初始失败 5 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`5 passed`。
- Token Profile Current dirty 非集成组通过，`18 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root359 - Market Tick Current dirty completion 把缺失 rowcount 当成 0 个 market target

发现：

- `MarketTickCurrentDirtyTargetRepository.mark_done(...)` 和 `mark_error(...)` 在删除/更新
  `market_tick_current_dirty_targets` 后使用 `int(getattr(cursor, "rowcount", 0) or 0)` 返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 target 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `market_tick_current_dirty_targets` 是 Market Tick Current projection 的控制面，而 `market_tick_current`
  又是 Token Radar market-current dirty fan-out 的输入之一。done/error count 会影响 worker 对市场当前行
  completion/retry 是否实际发生的判断。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有目标被更新”，导致
  market-current backlog、Token Radar market dirty enqueue、`market_tick_current_updated` wake 诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者是 stale completion token 或真正 no-op，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `market_tick_current_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `market_tick_current_dirty_target_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `market_tick_current_dirty_target_rowcount_invalid`。
- done/error completion changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-target accounting。

验证：

- RED：focused Market Tick Current dirty rowcount 命令初始失败 5 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`5 passed`。
- Market Tick Current dirty 非集成组通过，`25 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root360 - Token Image Source dirty completion 把缺失 rowcount 当成 0 个 image-source target

发现：

- `TokenImageSourceDirtyTargetRepository.mark_done(...)` 和 `mark_error(...)` 在删除/更新
  `token_image_source_dirty_targets` 后使用默认 rowcount 语义返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 target 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `token_image_source_dirty_targets` 是 token image mirror 的控制面，它把 provider logo URL 镜像为本地
  `token_image_assets`，再影响 public profile/icon current-row fan-out。
- done/error count 不是普通统计数字，而是“这个 image-source claim 是否真的被 PostgreSQL CAS 删除或释放重试”的执行证据。
  默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有目标被更新”，导致 image mirror
  backlog、重试、public logo 本地化链路诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者是 stale completion token 或真正 no-op，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `token_image_source_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `token_image_source_dirty_target_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `token_image_source_dirty_target_rowcount_invalid`。
- done/error completion changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-target accounting。

验证：

- RED：focused Token Image Source dirty rowcount 命令初始失败 6 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`6 passed`。
- Token Image Source dirty 非集成组通过，`18 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root361 - Token Capture Tier dirty enqueue/done 把缺失 rowcount 当成 0 个 capture-tier target

发现：

- `TokenCaptureTierDirtyTargetRepository.enqueue_rank_set(...)` 在 upsert `token_capture_tier_dirty_targets`
  后使用默认 rowcount 语义返回 `targets` changed count。
- `mark_done(...)` 在删除已完成 dirty target 后同样使用默认 rowcount 语义返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 target 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `token_capture_tier_dirty_targets` 是 market capture tier projection 的控制面。它决定 active Token Radar
  targets 何时重算为 stream、poll、inline-only 三类采集 tier。
- enqueue/done count 影响 worker 是否观察到 rank-set dirty 写入、completion 是否真的删除 claim，以及 market tick stream/poll
  订阅或轮询目标变化是否可诊断。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有目标被更新”，导致
  capture tier backlog、market tick 采集目标、下游 current market projection 诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者可以表示 unchanged rank-set 或 stale completion token，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `token_capture_tier_dirty_target_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `token_capture_tier_dirty_target_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `token_capture_tier_dirty_target_rowcount_invalid`。
- enqueue/done changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-target accounting。

验证：

- RED：focused Token Capture Tier dirty rowcount 命令初始失败 6 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`6 passed`。
- Token Capture Tier dirty 非集成组通过，`13 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root362 - Token Capture Tier projection demotion 把缺失 rowcount 当成 0 个 demoted hot row

发现：

- `TokenCaptureTierRepository.demote_hot_rows_outside_rank_set(...)` 在把不在当前 rank set 里的 tier 1/2
  rows 降级为 inline-only 后，仍使用 `int(getattr(cursor, "rowcount", 0) or 0)` 返回 demoted count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 hot row 被降级；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `token_capture_tier` 是 market capture tier 的 rebuildable control projection，而不是普通缓存。demotion count
  是“上一次 rank set 之外的 hot rows 是否真的被 PostgreSQL 降级”的执行证据。
- 默认 0 会把 driver wrapper、测试 fake、事务边界或 SQL 执行结果契约漂移隐藏成“没有 hot rows 需要降级”，导致
  stream/poll 订阅目标、poll 预算、live_price_gateway 目标集合以及 market-current 下游诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者是 rank set 没有需要降级的目标，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `token_capture_tier_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `token_capture_tier_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `token_capture_tier_repository_rowcount_invalid`。
- demotion changed-row accounting 通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-demotion accounting。

验证：

- RED：focused Token Capture Tier demotion rowcount 命令初始失败 6 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`6 passed`。
- Token Capture Tier repository 非集成组通过，`12 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root363 - Discovery lookup queue 写入把缺失 rowcount 当成 0 个 lookup work

发现：

- `DiscoveryRepository.enqueue_lookup_keys(...)`、`mark_lookup_done(...)`、`reschedule_lookup_claims(...)`
  在写入 `token_discovery_dirty_lookup_keys` 后仍使用默认 rowcount 语义返回 changed-row count。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 0 个 lookup queue 变化；字符串 rowcount 冒出普通
  `ValueError`，bool 或负数 rowcount 也没有被识别为 driver 契约错误。

根因：

- `token_discovery_dirty_lookup_keys` 是 resolution_refresh 的控制面队列，决定 NIL/AMBIGUOUS lookup 是否进入
  OKX DEX discovery、是否完成、是否重试。
- enqueue/done/reschedule count 是“queue write/CAS 是否真的发生”的 PostgreSQL 执行证据。默认 0 会把 driver wrapper、
  fake cursor、事务边界或 SQL 执行结果漂移隐藏成“没有 lookup work 变化”，让 resolution backlog、hot not-found retry、
  terminal ledger 和下游 `resolution_updated` wake 诊断出现假象。
- 成熟 Kappa/CQRS 的控制面 mutation 必须区分 PostgreSQL 证明的 `rowcount=0` 与“没有 rowcount 证据”。
  前者可以表示 unchanged/stale CAS，后者是 repository/driver 契约损坏，必须 fail closed。

修复：

- `discovery_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `discovery_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `discovery_repository_rowcount_invalid`。
- enqueue/done/reschedule changed-row accounting 全部通过 helper。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 zero-lookup accounting。

验证：

- RED：focused Discovery lookup rowcount 命令初始失败 16 个 case，证明缺失 rowcount 被当成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`16 passed`。
- DiscoveryRepository 非集成组通过，`36 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root364 - Enriched Event event-anchor 生命周期把缺失 rowcount 当成 no-op

发现：

- `EnrichedEventRepository.attach_backfill_capture(...)` 和
  `mark_backfill_terminal(...)` 在更新 `enriched_events` 的 pending anchor
  生命周期后，仍通过 `int(getattr(cursor, "rowcount", 0) or 0) == 1` 分类结果。
- 当 cursor/fake/driver 没有 `rowcount` 时，旧实现把它解释成 `False`，也就是“没有 pending anchor 行被 attach/terminal”。
- bool、字符串、负数或多行 rowcount 也没有被合同化识别；其中多行尤其危险，因为这两条路径语义上应是
  单个 `(event_id, intent_id)` pending anchor 的状态转换。

根因：

- `enriched_events` 是 event market context 的 PostgreSQL material fact / lifecycle state，
  不是普通缓存。pending、ready、terminal 的转换会影响 Token Radar、Pulse evidence packet、
  event/read API 对 event-anchor 市场上下文的判断。
- `rowcount=0` 和“没有 rowcount 证据”是两种完全不同的状态：
  前者表示 PostgreSQL 证明没有 pending row 命中，可能是 stale claim、重复完成或已经 terminal；
  后者表示 repository/driver/test fake 合同损坏。
- 旧的默认 0 把驱动证据缺失隐藏成正常 no-op，会让 event-anchor backfill backlog、
  provider quote 缺失、terminal 原因和事件市场上下文诊断全部失真。
- 成熟 Kappa/CQRS 对事实生命周期 CAS 的要求是 fail closed：只有数据库证明的
  `rowcount=0/1` 才能参与状态分类；缺失、非法或多行结果必须暴露为合同错误。

修复：

- `enriched_event_repository.py` 新增 `_single_row_mutation_applied(cursor)`。
- 缺失 rowcount 抛 `enriched_event_repository_rowcount_required`。
- bool、负数、非整数或非 `0/1` rowcount 抛 `enriched_event_repository_rowcount_invalid`。
- attach/terminal lifecycle 写入全部通过 helper 分类结果。
- 新增单测覆盖缺失、字符串、bool、负数、多行 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` 默认 no-op accounting。

验证：

- RED：focused Enriched Event lifecycle rowcount 命令初始失败 15 个 case，证明缺失 rowcount 被当成
  no-op，非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`19 passed`。
- EnrichedEventRepository 非集成组通过，`24 passed`；ruff 和 mypy 通过。
- 后续 SDD 和 residual scan 证据记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root365 - Macro Intel 写计数把缺失 rowcount 伪装成 sync/projection 成功

发现：

- `complete_macro_sync_window(...)`、`retry_macro_sync_window(...)`、
  `fail_macro_sync_window(...)`、`update_macro_sync_state(...)` 和
  `rebuild_macro_sync_state(...)` 原先把缺失 `cursor.rowcount` 当成 `0` 或 `1`。
- `enqueue_macro_projection_dirty_target(...)` 和
  `enqueue_macro_projection_dirty_targets_for_changes(...)` 原先把缺失 rowcount 当成
  `1` 或 `len(targets)`，等价于没有数据库执行证据也上报 dirty target 已写入。
- `mark_macro_projection_dirty_targets_done/error(...)`、current-series 删除和
  `_insert_observation_series_rows_chunk(...)` 原先把缺失 rowcount 当成 `0` 或
  `len(rows)`，会把 projection done/error 和 current-row upsert 诊断变成推断值。
- 单行语义路径还没有拒绝多行 rowcount；bool、字符串、负数等非法 rowcount 也没有统一合同化失败。

根因：

- Macro Intel 同时包含 provider 同步控制面、projection dirty queue 和 request-path current series read model。
  这些表不是普通缓存：`macro_sync_windows` 决定 provider IO 重试/终止，
  `macro_sync_state` 决定下一轮 catch-up frontier，
  `macro_projection_dirty_targets` 决定 projection 是否有 due work，
  `macro_observation_series_rows` 是 `/api/macro` 读路径的 compact current projection。
- 成熟 Kappa/CQRS 里，事实/控制面写入的返回计数必须来自 PostgreSQL 执行结果。
  `rowcount=0` 表示数据库证明没有命中或冲突行未变化；缺失 rowcount 表示 repository/driver/test fake
  合同坏掉。把后者洗成 0、1、`len(targets)` 或 `len(rows)`，会把链路错误伪装成“没有变更”或“已经写入”。
- 这会直接污染 worker 观测：Macro Sync 可能误报 window 完成/重试状态，dirty queue 可能误报目标入队/完成，
  current-series refresh 可能误报删除/写入数量，最终让 Macro read model stale、empty 或过度重写都难以定位。
- PostgreSQL 最佳实践不是“尽量兼容 cursor 形状”，而是在写路径把驱动执行证据作为正式合同；
  单行 CAS 还必须拒绝多行 rowcount，避免 SQL predicate 变宽后悄悄扩大状态转换范围。

修复：

- `macro_intel_repository.py` 新增 `_cursor_rowcount(cursor)` 和 `_single_rowcount(cursor)`。
- 缺失 rowcount 抛 `macro_intel_repository_rowcount_required`。
- bool、负数、非整数或单行路径中的多行 rowcount 抛
  `macro_intel_repository_rowcount_invalid`。
- Macro sync terminal/retry/fail、sync-state repair、projection dirty enqueue/done/error、
  current-series 删除和 upsert 计数全部改为读取真实 PostgreSQL rowcount。
- 新增单测覆盖缺失、字符串、bool、负数和单行路径多行 rowcount；新增 architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)`、`getattr(cursor, "rowcount", None)`、
  `return len(targets)` 和 `return len(rows)` 这类兼容计数。

验证：

- RED：focused Macro rowcount 命令初始失败 77 个 case，证明缺失 rowcount 会被旧实现洗成 false/0/1/len，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`77 passed`。
- Macro rowcount/transaction/Kappa 非集成组通过，`143 passed`；targeted ruff 和 repository mypy 通过。
- residual scan 确认 Macro 生产代码只剩 `_cursor_rowcount(...)` / `_single_rowcount(...)` 和显式错误码，
  旧兼容字面量只出现在 architecture guard 与历史文档。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root366 - Narrative admissions 写入把缺失 rowcount 当成 0 个 admission 变更

发现：

- `NarrativeRepository.upsert_admissions(...)` 在写入 current `narrative_admissions` 后返回 `upserted`
  changed count。
- `NarrativeRepository.stale_admission_target(...)` 在删除 stale `narrative_admissions` 后返回
  `staled_admissions` changed count。
- 两条路径原先都通过默认 rowcount 语义把缺失执行证据洗成 `0`。

根因：

- `narrative_admissions` 是 Narrative Intel 当前 runtime read model，不是历史 digest/semantic 兼容表；
  它由 `NarrativeAdmissionWorker` 单 writer 写入，Token Radar / Token Case 等读路径依赖它表达当前 source-set admission。
- 在这条链路里，`rowcount=0` 有明确业务含义：payload hash 未变、目标已不存在，或者 PostgreSQL 证明没有 stale row。
  “cursor 没有 rowcount”则是 driver / repository fake / wiring 合同破损。
- 旧代码把后者降级成前者，会让 worker 观测出现假健康：admission upsert 可能实际没有执行证据，
  stale cleanup 可能没有被证明发生，但诊断仍显示 0 个 admission 变更。
- 成熟 Kappa/CQRS 里，unchanged projection 写 0 serving rows 必须由数据库证明；缺失执行证据必须 fail closed，
  否则 current read model 的 freshness、stale cleanup 和 dirty-target 完成链路会失去可审计性。

修复：

- `narrative_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `narrative_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `narrative_repository_rowcount_invalid`。
- `upsert_admissions(...)` 与 `stale_admission_target(...)` 的 changed count 都改为读取真实 PostgreSQL rowcount。
- 新增单测覆盖缺失、字符串、bool、负数 rowcount；architecture guard 禁止恢复
  `getattr(cursor, "rowcount", 0)` / `getattr(admissions, "rowcount", 0)` 默认 zero-admission accounting。

验证：

- RED：focused Narrative admission rowcount 命令初始失败 13 个 case，证明缺失 rowcount 被旧实现洗成 0，
  非法 rowcount 未合同化失败，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`13 passed`。
- Narrative admission / dirty target / worker / read-model 非集成组通过，`70 passed`。
- targeted ruff 和 repository mypy 通过。
- residual scan 确认 Narrative 生产代码只剩 `_cursor_rowcount(...)` 与显式错误码，
  旧兼容字面量只出现在 architecture guard 与历史文档。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root367 - Pulse stale agent-run cleanup 把缺失 rowcount 当成 0 个 stale run

发现：

- `PulseJobsRepository.mark_stale_agent_runs_failed(...)` 会把超时的 `pulse_agent_runs` 从 `running`
  标记为 `failed/timeout`，并返回 stale run changed count。
- 旧实现使用 `int(cursor.rowcount or 0)`；缺失 rowcount 会变成裸 `AttributeError`，
  bool、字符串、`None` 和负数 rowcount 没有被合同化失败，其中 bool/string 还可能被当成合法计数。

根因：

- `pulse_agent_runs` 是 Pulse agent execution plane 的审计/控制面，不是 public read model，
  但它决定 operator 对 LLM run 超时、cleanup 和 worker 健康的观测。
- 在成熟 Kappa/CQRS 里，控制面不是业务真相，但控制面 mutation 的 changed-row count 仍必须来自 PostgreSQL
  执行证据；`rowcount=0` 表示数据库证明没有 stale running run，缺失 rowcount 表示 driver/fake/wiring 合同坏掉。
- 旧默认 zero-run accounting 会把“没有执行证据”伪装成“没有 stale run”，让 Pulse timeout cleanup、
  agent run health 和后续排障看起来正常。

修复：

- `pulse_jobs_repository.py` 新增 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `pulse_jobs_repository_rowcount_required`。
- bool、负数或非整数 rowcount 抛 `pulse_jobs_repository_rowcount_invalid`。
- `mark_stale_agent_runs_failed(...)` 的返回计数改为读取真实 PostgreSQL rowcount。
- 新增单测覆盖缺失、字符串、bool、`None`、负数 rowcount；新增 architecture guard 禁止恢复
  `cursor.rowcount or 0`、`getattr(cursor, "rowcount", 0)` 这类默认 zero-run accounting。

验证：

- RED：focused PulseJobsRepository stale-run rowcount 命令初始失败 7 个 case，证明缺失 rowcount
  未合同化、非法 rowcount 被接受或以错误异常泄漏，architecture guard 命中默认 rowcount 读取。
- GREEN：同一 focused 命令通过，`7 passed`。
- Pulse job repository / job service / dirty trigger / worker 非集成组通过，`139 passed`。
- targeted ruff 和 repository mypy 通过。
- residual scan 确认 PulseJobsRepository 生产代码只剩 `_cursor_rowcount(...)` 与显式错误码，
  旧兼容字面量只出现在 architecture guard 与历史文档。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root368 - Evidence fact writes 把非法 rowcount 当成 created/existing/inserted 事实分类

发现：

- `EvidenceRepository.insert_raw_frame(...)` 写入 `raw_frames` 时，旧实现直接用
  `cursor.rowcount == 1` 判断 provider raw-frame input observation 是否新插入。
- `EvidenceRepository.insert_event_without_commit(...)` 写入 `events` 时，旧实现用
  `cursor.rowcount != 0` 判断 material fact 是否新插入。
- `EntityRepository.insert_event_entities(...)` 写入 `event_entities` 时，旧实现用
  `int(cursor.rowcount == 1)` 叠加 inserted entity count。

根因：

- `raw_frames` 是 provider raw inputs，`events` 和 `event_entities` 是 material facts；它们虽然不全是
  public read model，但它们是后续 Token Radar、asset identity、event anchor、alert 和 worker dirty fan-out 的
  事实源入口。
- 在 PostgreSQL `INSERT ... DO NOTHING` 单行写路径里，`rowcount=1` 表示数据库证明新行插入，
  `rowcount=0` 表示数据库证明 conflict/no new row。缺失 rowcount、bool、字符串、`None`、负数或多行
  rowcount 都不是业务状态，而是 repository / driver / fake cursor / SQL predicate 合同损坏。
- 旧代码把 bool 的 Python 等值语义、字符串 truthiness 或非 0 比较混入事实分类，会让 ingest 层把“没有可靠执行证据”
  伪装成“已插入”或“已存在”。这会污染最上游的 Kappa 日志：下游再怎么单 writer、稳定 key、bounded catch-up，
  都是在消费一个已经被错误分类的事实入口。
- PostgreSQL 最佳实践不是让 repository 尽量容忍 cursor 形状，而是在写路径把驱动执行证据合同化；
  特别是单行 `INSERT ... DO NOTHING` 必须拒绝多行 rowcount，防止 SQL predicate 或 conflict target 变化后悄悄扩大写入范围。

修复：

- `evidence_repository.py` 新增 `_single_rowcount(cursor)`。
- 缺失 rowcount 抛 `evidence_repository_rowcount_required`。
- bool、负数、非整数或多行 rowcount 抛 `evidence_repository_rowcount_invalid`。
- `insert_raw_frame(...)` 与 `insert_event_without_commit(...)` 都只接受 `_single_rowcount(cursor) == 1`
  作为新行插入证据。
- `entity_repository.py` 新增 `_single_rowcount(cursor)`。
- 缺失 rowcount 抛 `entity_repository_rowcount_required`。
- bool、负数、非整数或多行 rowcount 抛 `entity_repository_rowcount_invalid`。
- `insert_event_entities(...)` 的 inserted count 改为逐条累加真实 PostgreSQL 单行 rowcount。
- 新增单测覆盖 `raw_frames`、`events`、`event_entities` 的缺失、bool、字符串、`None`、负数和多行
  rowcount；新增 architecture guard 禁止恢复裸 `cursor.rowcount == 1`、`cursor.rowcount != 0`、
  `int(cursor.rowcount == 1)` 或 `getattr(cursor, "rowcount", 0)`。

验证：

- RED：focused Evidence rowcount 命令初始失败 22 个 case，证明缺失 rowcount 以裸 `AttributeError` 泄漏，
  非法 rowcount 被旧实现接受或误分类，architecture guard 命中裸 rowcount 比较。
- GREEN：同一 focused 命令通过，`22 passed`。
- Evidence repository / collector / ingest dirty-target / provider raw-frame architecture 非集成组通过，`37 passed`。
- targeted ruff 和 Evidence repository mypy 通过。
- residual scan 确认 Evidence/Entity 生产代码只剩 `_single_rowcount(...)` 与显式错误码，
  旧裸比较字面量只出现在 architecture guard 与历史文档。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root369 - CEX read-model rowcount helper 把 bool/负数洗成正常写入计数

发现：

- `CexOiRadarRepository._cursor_rowcount(...)` 仍通过 `max(0, int(rowcount))`
  统计 `cex_oi_radar_rows` delete/upsert 写入数。
- `CexDetailSnapshotRepository._rowcount(...)` 仍通过 `max(int(rowcount), 0)`
  统计 `cex_detail_snapshots` upsert 写入数。
- `CexDerivativeSeriesRepository._cursor_rowcount(...)` 仍通过 `max(0, int(rowcount))`
  统计 `cex_derivative_series` upsert 写入数。

根因：

- 前面 Root303/304/305 已经切掉了 CEX read-model 的缺失 rowcount 默认值，但 helper 里还保留
  Python 类型转换和 clamp 兼容层。
- 在 Python 里 `True` 会被 `int(True)` 变成 `1`，于是 malformed fake cursor / driver evidence
  会被伪装成“PostgreSQL 写入了一行”。
- `rowcount=-1` 会被 `max(..., 0)` 洗成 `0`，于是 driver contract 损坏会被伪装成“unchanged projection/no-op”。
- 成熟 CQRS 的语义应该更窄：`rowcount=0` 只能表示 PostgreSQL 明确证明没有 serving-row mutation；
  bool、负数、字符串或缺失 rowcount 都不是业务状态，而是 repository/driver/wiring 合同损坏。

修复：

- `cex_oi_radar_repository.py`、`cex_detail_snapshot_repository.py`、
  `cex_derivative_series_repository.py` 的 rowcount helper 都改为直接读取 `cursor.rowcount`。
- 缺失 rowcount 分别抛 `cex_oi_radar_rowcount_required`、
  `cex_detail_snapshot_rowcount_required`、`cex_derivative_series_rowcount_required`。
- bool、负数或非整数 rowcount 分别抛对应 `*_rowcount_invalid`，不再经过 `int(...)` 或 `max(...)` 修复。
- CEX 域架构、全局 CONTRACTS、architecture guard 和单测都记录同一条合同。

验证：

- RED：focused CEX rowcount 命令初始失败 9 个 case、通过 4 个 case，证明 bool/负数被旧 helper 接受，
  architecture guard 命中 `return max(0, int(rowcount))` 和 `return max(int(rowcount), 0)`。
- GREEN：同一 focused 命令通过，`13 passed`。
- CEX repository / CEX architecture 非集成组通过，`140 passed`。
- targeted ruff 和 CEX repository mypy 通过。
- residual scan 确认 CEX 生产代码只剩 `rowcount: object = cursor.rowcount`、
  `isinstance(rowcount, bool)` 与显式错误码；旧 `max/int(rowcount)` 兼容字面量只出现在 architecture guard。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root370 - Token Radar rowcount helper 仍把 numeric string 当成 PostgreSQL 写入证据

发现：

- `TokenRadarRepository._cursor_rowcount(...)` 仍会对 `cursor.rowcount` 执行 `int(rowcount)`。
- `TokenRadarDirtyTargetRepository._cursor_rowcount(...)` 仍会对 target dirty queue mutation count 执行同样转换。
- `TokenRadarSourceDirtyEventRepository._cursor_rowcount(...)` 仍会对 source dirty queue mutation count 执行同样转换。
- `TokenRadarRankSourceQuery._cursor_rowcount(...)` 仍会对 rank-source prune rowcount 执行同样转换。

根因：

- Root347/348/349 已经把缺失 rowcount 默认值切掉，并拒绝 bool/负数/非数字字符串；但 helper 仍然接受
  `"1"`、`"3"` 这类 numeric string。
- PostgreSQL/psycopg 的 `cursor.rowcount` 合同是整数执行证据。字符串数字不是“数据库证明写入了 N 行”，而是
  fake cursor、driver adapter 或测试替身的形状漂移。
- 如果 repository 接受 numeric string，Token Radar current-row publication、target/source dirty queue
  accounting、rank-source prune diagnostics 都会把 wiring damage 伪装成正常 changed-row count；这会削弱
  Kappa/CQRS 对“unchanged projection 写 0 行”的可证明性。

修复：

- 四个 helper 全部改为读取 `rowcount: object = cursor.rowcount`。
- bool 或非 `int` 直接抛各自的 `*_rowcount_invalid`，负数也抛 invalid。
- 删除 `count = int(rowcount)` 兼容路径；SQL aggregate count 解析仍保留在 rank-source population 的显式
  aggregate result helper 中，不和 cursor rowcount 混用。
- 单测新增 numeric string rowcount case；architecture guard 禁止恢复 `count = int(rowcount)`。

验证：

- RED：focused Token Radar rowcount 命令初始失败 8 个 case、通过 8 个 case，证明 `"1"` / `"3"`
  被旧 helper 接受，architecture guard 命中 `count = int(rowcount)`。
- GREEN：同一 focused 命令通过，`16 passed`。
- Token Radar repository / dirty queue / source dirty / rank-source / architecture 非集成组通过，`192 passed`。
- targeted ruff 和 Token Radar touched production mypy 通过。
- residual scan 确认生产 Token Radar helper 只剩 `rowcount: object = cursor.rowcount`、
  `isinstance(rowcount, bool) or not isinstance(rowcount, int)` 与显式错误码；`count = int(rowcount)`
  只出现在 architecture guard forbidden literals。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root371 - Notification read-marker 写入仍用 `len(rows)` 伪装 changed-row accounting

发现：

- `NotificationRepository.mark_all_read(...)` 旧实现先 SELECT 未读 notification ids，再逐行
  UPSERT `notification_reads`，最后返回 `len(rows)`。
- `NotificationRepository.mark_author_read(...)` 虽然使用 `INSERT ... RETURNING`，但仍返回
  `len(rows)`，没有验证 PostgreSQL cursor rowcount。
- `NotificationRepository.mark_read(...)` 在确认 notification 存在后直接返回 `True`，没有检查
  read-marker UPSERT 的 cursor rowcount。

根因：

- `notification_reads` 不是核心 material fact，但它是 public notification read state。repository
  返回的 success/count 会被 API 或 operator UI 当成真实 read-state mutation 结果。
- `len(rows)` 只能说明 Python 侧拿到了多少候选/RETURNING 行，不能证明 PostgreSQL 执行了多少行写入。
  在 `mark_all_read(...)` 旧实现里，这还造成 N+1 写入：一次预选未读 ids，再对每个 id 单独 UPSERT。
- 成熟 CQRS/Kappa 的写入边界应该把“候选集合大小”和“数据库实际 changed rows”分开。`rowcount=0`
  可以表示 PostgreSQL 明确证明没有 changed row；缺失、bool、负数、非整数或与 RETURNING 行数不一致的
  rowcount 都是 repository/driver/fake cursor 合同损坏，不是业务 no-op。
- PostgreSQL 最佳实践上，bulk read-marker 应使用一条 `INSERT ... SELECT ... RETURNING`，并用 cursor
  rowcount 与返回行数交叉校验，而不是用应用层循环和 `len(rows)` 代替执行证据。

修复：

- `mark_read(...)` 的 read-marker UPSERT 现在使用 `_single_row_write_count(...)`，缺失 rowcount 抛
  `notification_read_mark_rowcount_required`，非法 rowcount 抛
  `notification_read_mark_rowcount_invalid`。
- `mark_all_read(...)` 改为单条 `WITH unread AS (...) INSERT INTO notification_reads ... RETURNING
  notification_id`，消除 SELECT+逐行 UPSERT 的 N+1 写法。
- `mark_all_read(...)` 与 `mark_author_read(...)` 都通过 `_returned_write_count(...)` 校验
  cursor rowcount 必须等于 RETURNING 行数；缺失 rowcount 抛
  `notification_read_bulk_rowcount_required`，非法或不一致 rowcount 抛
  `notification_read_bulk_rowcount_invalid`。
- 新增 architecture guard 禁止在 read-marker sections 恢复 `return len(rows)`、`getattr(cursor,
  "rowcount", 0)` 或 `cursor.rowcount or 0`。

验证：

- RED：focused notification read-marker rowcount 命令初始失败 `16 failed`，证明缺失 rowcount、非法
  rowcount 和 `return len(rows)` 均未被旧实现阻断。
- GREEN：同一 focused 命令通过，`16 passed`。
- Notification worker runtime / rules / hard-cut architecture 非集成组通过，`110 passed`。
- targeted ruff 和 `NotificationRepository` mypy 通过。
- residual scan 确认生产通知仓库已无 `return len(rows)`，只剩 `_write_count(...)`、
  `_returned_write_count(...)`、`rowcount: object = cursor.rowcount` 与显式通知 read-marker 错误码。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root372 - Token Radar generic dirty enqueue 用候选记录数冒充队列写入数

发现：

- `TokenRadarDirtyTargetRepository.enqueue_targets(...)` 旧实现执行
  `INSERT INTO token_radar_dirty_targets ... ON CONFLICT DO UPDATE` 后返回 `len(records)`。
- `TokenRadarSourceDirtyEventRepository.enqueue_events(...)` 旧实现执行
  `INSERT INTO token_radar_source_dirty_events ... ON CONFLICT DO UPDATE` 后也返回 `len(records)`。
- 这两个 generic enqueue 路径与同 repository 里的 market/current/catch-up enqueue 不一致；后者已经从
  PostgreSQL `cursor.rowcount` 取 changed-row count。

根因：

- `records` 是应用层去重后的候选宽度，不是数据库执行证据。`ON CONFLICT DO UPDATE` 可能因为冲突、WHERE
  predicate、future SQL 条件变化或 driver/wiring 损坏而实际改变 0 行、1 行或多行。
- Token Radar dirty queues 是 Kappa/CQRS 的 wake/catch-up 控制面。generic target/source enqueue 如果把候选
  数当写入数，会让 worker/backlog/repair 诊断以为已经写入了 dirty work；真实 PostgreSQL 可能没有产生任何
  可 claim 的队列 mutation。
- 这会削弱 “NOTIFY 只是 wake hint，worker 重新读 DB” 的模型：wake 可以多发，但 repository 返回的 changed-row
  count 不能由 Python 候选数伪造，否则 operator 看到的 repair/enqueue 证据不是数据库事实。

修复：

- `enqueue_targets(...)` 保存 `cursor = self.conn.execute(...)`，返回 `_cursor_rowcount(cursor)`。
- `enqueue_events(...)` 保存 `cursor = self.conn.execute(...)`，返回 `_cursor_rowcount(cursor)`。
- target/source enqueue 缺失 rowcount 分别抛 `token_radar_dirty_target_rowcount_required` /
  `token_radar_source_dirty_event_rowcount_required`。
- bool、负数、非整数、numeric string rowcount 分别抛对应 `*_rowcount_invalid`。
- architecture guard 现在切到 `enqueue_targets` / `enqueue_events` sections，禁止恢复 `return len(records)`。

验证：

- RED：focused Token Radar dirty enqueue rowcount 命令初始失败 `11 failed`，证明缺失/非法 rowcount 被旧 generic
  enqueue 接受，architecture guard 命中 `return len(records)`。
- GREEN：同一 focused 命令通过，`11 passed`。
- Token Radar target dirty / source dirty / source-width architecture 非集成组通过，`85 passed`。
- targeted ruff 和 touched production mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root373 - News projection dirty enqueue 用候选记录数冒充队列写入数

发现：

- `NewsProjectionDirtyTargetRepository.enqueue_targets(...)` 执行
  `INSERT INTO news_projection_dirty_targets ... ON CONFLICT DO UPDATE` 后返回 `len(records)`。
- 同一 repository 的 done/error 路径已经要求 PostgreSQL `cursor.rowcount`，但 enqueue 入口仍把应用层候选数当成
  changed-row count。

根因：

- `records` 只能说明 Python 侧形成了多少 dirty target 候选，不能证明 PostgreSQL 插入或更新了多少队列行。
- News page/source-quality projection 依赖 dirty target queue 做 bounded catch-up。enqueue 如果按候选数报成功，
  operator 看到的 repair/enqueue 计数会和数据库事实脱钩；实际 SQL 可能因为冲突、条件谓词或 driver/wiring
  损坏而没有产生对应的可 claim work。
- 成熟 Kappa/CQRS 的队列控制面必须把“候选宽度”“wake hint”和“持久化 changed-row evidence”分开。
  NOTIFY 可以只是提示，但 repository 返回的队列写入数必须来自 PostgreSQL。

修复：

- `enqueue_targets(...)` 现在保存 `cursor = self.conn.execute(...)`，返回 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `news_projection_dirty_target_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `news_projection_dirty_target_rowcount_invalid`。
- 新增 architecture guard 禁止在 `enqueue_targets` section 恢复 `return len(records)` 或默认 rowcount 兼容。

验证：

- RED：focused News dirty enqueue rowcount 命令初始失败 `6 failed`，证明缺失/非法 rowcount 被旧 enqueue 接受，
  rowcount=0 时仍返回候选数，architecture guard 命中 `return len(records)`。
- GREEN：同一 focused 命令通过，`6 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root374 - Market Tick Current dirty enqueue 用候选记录数冒充队列写入数

发现：

- `MarketTickCurrentDirtyTargetRepository.enqueue_targets(...)` 执行
  `INSERT INTO market_tick_current_dirty_targets ... ON CONFLICT DO UPDATE ... WHERE ...` 后返回
  `len(records)`。
- 该 SQL 的 conflict update 有 `WHERE` 谓词；当 dirty payload、reason、due time、watermark、priority、lease/error
  状态都不需要改变时，PostgreSQL 可以明确返回 rowcount=0，但旧实现仍把候选数报告为已写入。

根因：

- Market Tick Current dirty queue 是 market tick facts 到 `market_tick_current` 当前读模型的控制面。
  enqueue 返回值应表达“数据库实际产生/刷新了多少 dirty target”，不是“worker 试图排队多少 target”。
- 把候选数当 changed-row count 会让 replay、repair、backlog 指标以为 current projection 有新 work；但真实队列可能没有任何
  可 claim 的 mutation。
- 这和成熟 Kappa/CQRS 的核心思想相反：当前读模型和 dirty queues 都是可重放的 DB 状态，不能用应用层候选宽度替代
  PostgreSQL 执行证据。

修复：

- `enqueue_targets(...)` 保存 `cursor = self.conn.execute(...)`，返回 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `market_tick_current_dirty_target_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `market_tick_current_dirty_target_rowcount_invalid`。
- 新增 architecture guard 禁止在 `enqueue_targets` section 恢复 `return len(records)`。

验证：

- RED：focused Market Tick Current dirty enqueue rowcount 命令初始失败 `6 failed`，证明缺失/非法 rowcount 被旧 enqueue
  接受，rowcount=0 时仍返回候选数，architecture guard 命中 `return len(records)`。
- GREEN：同一 focused 命令通过，`6 passed`。
- Market Tick Current dirty repository / architecture 非集成组通过，`31 passed`。
- targeted ruff 和 repository mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root375 - Token Radar first-seen upsert 用候选记录数冒充读模型写入数

发现：

- `TokenRadarRepository.upsert_first_seen_batch(...)` 执行
  `INSERT INTO token_radar_target_first_seen ... ON CONFLICT DO UPDATE` 后返回 `len(records)`。
- `token_radar_target_first_seen` 是 `listed_at_ms` 的紧凑读模型；虽然它不参与 alpha 评分，但它仍由
  `TokenRadarProjectionWorker` 单 writer 维护，并且属于当前 Radar serving 元数据链路。

根因：

- `records` 只表示 projection 在 Python 侧形成了多少去重后的 first-seen 候选，不能证明 PostgreSQL 实际插入或更新了多少
  `token_radar_target_first_seen` 行。
- 当前 SQL 目前没有 `WHERE ... IS DISTINCT FROM`，所以多数真实 PostgreSQL 执行会让 rowcount 接近候选数；但这正是危险点：
  代码把“当前 SQL 的偶然形态”当成契约，掩盖了缺失 cursor、fake cursor、driver/wiring 损坏或未来 SQL 收窄导致的真实
  no-op。
- 成熟 Kappa/CQRS 里，read model 元数据也必须遵循同一条原则：候选集合、wake hint、持久化 changed-row evidence 是三个不同层。
  first-seen 是展示元数据，不是评分事实，但它的写入计数仍然必须来自数据库事实。

修复：

- `upsert_first_seen_batch(...)` 现在保存 `cursor = self.conn.execute(...)`，返回 `_cursor_rowcount(cursor)`。
- 缺失 rowcount 抛 `token_radar_repository_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `token_radar_repository_rowcount_invalid`。
- 新增 first-seen 单元测试和 architecture guard，禁止恢复 `return len(records)` 或 `return len(rows)`。

验证：

- RED：focused Token Radar first-seen rowcount 命令初始失败 `6 failed`，证明 rowcount=0 时旧实现仍返回候选数，缺失/非法
  rowcount 被接受，architecture guard 命中 `return len(records)`。
- GREEN：同一 focused 命令通过，`6 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root376 - Pulse job terminalization 用 RETURNING 行数绕过 rowcount 证据

发现：

- `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)` 执行
  `UPDATE pulse_agent_jobs ... RETURNING job.*` 后直接 `return len(rows)`。
- `PulseJobsRepository.terminalize_stale_jobs_by_window(...)` 执行
  `UPDATE pulse_agent_jobs ... RETURNING *` 后用 `terminalized += len(rows)` 累加。
- 这两条路径随后会写 `worker_queue_terminal_events`，属于 Pulse agent job 控制面 terminal/dead 状态转换。

根因：

- `UPDATE ... RETURNING` 的 `rows` 确实来自 PostgreSQL 结果集，不是 Python 输入候选；但它仍不是完整执行证据。
  成熟的 PostgreSQL 写入契约需要校验 cursor rowcount 与 RETURNING 行数一致。
- 旧实现会在读取 rows 后立即写 terminal ledger。若 fake cursor/driver 缺失 rowcount、rowcount 类型错误，或 rowcount 与
  RETURNING rows 不一致，系统仍会把 returned rows 当作 terminalized job count 并写入 terminal ledger。
- 对 Kappa/CQRS 来说，`pulse_agent_jobs` 是 agent 执行控制面，`worker_queue_terminal_events` 是 terminal ledger。
  两者必须在同一事务内反映同一组 DB-proven source rows；不能先相信 returned row list，再把 malformed rowcount 留给事后诊断。

修复：

- 两条 batch terminalization 路径都先保存 cursor，再 `fetchall()`。
- 新增 `_returned_rowcount(cursor, rows)`：先走 `_cursor_rowcount(cursor)`，再要求 `count == len(rows)`。
- rowcount 缺失抛 `pulse_jobs_repository_rowcount_required`。
- bool、负数、非整数或与 RETURNING rows 不一致抛 `pulse_jobs_repository_rowcount_invalid`。
- 校验发生在 `_terminalize_pulse_job(...)` 写 terminal ledger 之前。

验证：

- RED：focused Pulse job terminal RETURNING rowcount 命令初始失败 `10 failed`，证明旧实现会在 rowcount 缺失/非法/不一致时继续进入
  terminal ledger，architecture guard 命中 `return len(rows)` / `terminalized += len(rows)`。
- GREEN：同一 focused 命令通过，`10 passed`。
- Pulse job repository / Pulse architecture 非集成组通过，`76 passed`。
- targeted ruff 和 repository mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root377 - News projection terminal delete 用 RETURNING 行数绕过 rowcount 证据

发现：

- `NewsProjectionDirtyTargetRepository.terminalize_targets(...)` 删除已 claim 的
  `news_projection_dirty_targets` 后，旧实现直接遍历 deleted rows 写 `worker_queue_terminal_events`，
  最后 `return len(deleted_records)`。
- 这条路径是 News page/source-quality dirty-target 的 terminal ledger 链路；它不是普通查询，而是 queue hot row 删除与
  terminal evidence 写入的一次控制面状态转换。

根因：

- `DELETE ... RETURNING queue.*` 的 returned rows 确实来自 PostgreSQL，不是 Python 输入候选；但 returned row list
  仍然不能替代 cursor execution evidence。
- 成熟 PostgreSQL 写入合同需要先证明 `cursor.rowcount` 存在、类型合法、非负，并且与 RETURNING 行数一致。否则 fake cursor、
  driver 适配层或 SQL predicate 漂移可能让 terminal ledger 记录一组没有完整执行证据的 source rows。
- 对 Kappa/CQRS 来说，`news_projection_dirty_targets` 是可重放投影调度状态，`worker_queue_terminal_events` 是终态审计账本。
  两者必须在同一事务内由同一组 DB-proven deleted rows 驱动，不能先写 ledger，再把 malformed rowcount 留给后续诊断。

修复：

- 新增 `_delete_claimed_target_rows(records)`，保存 DELETE cursor、`fetchall()`，并返回
  `(deleted_records, deleted_count)`。
- 新增 `_returned_rowcount(cursor, rows)`：先走 `_cursor_rowcount(cursor)`，再要求 `count == len(rows)`。
- rowcount 缺失抛 `news_projection_dirty_target_rowcount_required`。
- bool、负数、非整数或与 RETURNING rows 不一致抛 `news_projection_dirty_target_rowcount_invalid`。
- `terminalize_targets(...)` 只在 `_returned_rowcount(...)` 通过后写 `terminalize_source_row(...)`，并返回
  PostgreSQL 证明的 `deleted_count`，不再返回 `len(deleted_records)`。

验证：

- RED：focused News terminal RETURNING rowcount 命令初始失败 `9 failed`，证明旧实现会在 rowcount 缺失/非法/不一致时继续进入
  terminal ledger，architecture guard 找不到 `_returned_rowcount(...)` 并命中旧的 length accounting。
- GREEN：同一 focused 命令通过，`9 passed`。
- News projection dirty-target unit / News KISS architecture 非集成组通过，`103 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root378 - News source disable 用 RETURNING rows/len(rows) 冒充 changed-row count

发现：

- `NewsRepository.disable_unconfigured_source_rows(...)` 执行
  `UPDATE news_sources ... RETURNING *` 后只返回 disabled rows。
- `NewsRepository.disable_unconfigured_sources(...)` 再用 `return len(rows)` 作为禁用 source 数。
- 这条路径位于 configured-source reconciliation：它会把不再出现在配置里的 `managed_by_config` source 标记为 disabled，
  并把 disabled row 拼回 reconcile 结果。

根因：

- returned rows 虽然来自 PostgreSQL，但它仍只是结果集，不是完整 mutation execution evidence。
- `news_sources` 是 News fetch/source-quality/read status 的事实入口之一。disable 不是 UI 辅助计数，而是改变后续 fetch claim、
  source status、page projection servable filter 的事实状态。
- 成熟 Kappa/CQRS 里，配置源候选、`UPDATE ... RETURNING` 结果集、以及 PostgreSQL cursor rowcount 是三层证据：
  只有 rowcount 存在、类型合法、非负，并且与 returned disabled rows 一致，系统才能把这次 source disable 作为 changed-row
  事实报告给上层。
- 旧实现会让 fake cursor、driver 适配层缺失 rowcount、rowcount 类型错误或 rowcount/RETURNING 不一致的问题被 `len(rows)` 掩盖。

修复：

- 新增 `_disable_unconfigured_source_rows(...)`，保存 UPDATE cursor、`fetchall()`，并返回 `(disabled_rows, disabled_count)`。
- 新增/复用 `_returned_rowcount(cursor, rows)`：先走 `_cursor_rowcount(cursor)`，再要求 `count == len(rows)`。
- rowcount 缺失抛 `news_repository_rowcount_required`。
- bool、负数、非整数或与 RETURNING rows 不一致抛 `news_repository_rowcount_invalid`。
- `disable_unconfigured_source_rows(...)` 返回已验证过的 rows；`disable_unconfigured_sources(...)` 返回 PostgreSQL 证明的
  `disabled_count`，不再返回 `len(rows)`。

验证：

- RED：focused News source disable RETURNING rowcount 命令初始失败 `9 failed`，证明旧实现接受缺失/非法/不一致 rowcount，
  architecture guard 找不到 `_disable_unconfigured_source_rows(...)` / `_returned_rowcount(...)` 合同。
- GREEN：同一 focused 命令通过，`9 passed`。
- News repository / News KISS architecture 非集成组通过，`146 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认 `news_repository.py` 已无
  `return len(rows)` / `disabled_count = len(rows)`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root379 - Discovery terminal delete 用 RETURNING rows/len(deleted_rows) 绕过 rowcount 证据

发现：

- `DiscoveryRepository.terminalize_lookup_claims(...)` 通过
  `DELETE FROM token_discovery_dirty_lookup_keys ... RETURNING queue.*` 删除已 claim 的 lookup key。
- 旧实现只比较 `len(deleted_rows)` 和 `len(records)`，随后写 `worker_queue_terminal_events` terminal ledger。
- 返回值里的 deleted count 也来自 `len(deleted_rows)`，不是 PostgreSQL cursor rowcount。

根因：

- returned rows 是结果集，不是完整 DML 执行合同。成熟 PostgreSQL 写入路径需要同时证明 cursor rowcount 存在、
  类型合法、非负，并且与 RETURNING rows 一致。
- `token_discovery_dirty_lookup_keys` 是 `resolution_refresh` 的控制面队列，`worker_queue_terminal_events`
  是 terminal ledger。两者必须在同一事务里由同一组 DB-proven deleted rows 驱动。
- 旧实现会让 fake cursor、driver 适配层缺失 rowcount、rowcount 类型错误或 rowcount/RETURNING 不一致的问题被
  `len(deleted_rows)` 掩盖；更严重的是 terminal ledger 可能已经写入，后续才暴露计数证据不完整。

修复：

- `_delete_lookup_claims_returning(...)` 现在保存 DELETE cursor、执行 `fetchall()`，并返回
  `(deleted_rows, deleted_count)`。
- 新增 `_returned_rowcount(cursor, rows)`：先走 `_cursor_rowcount(cursor)`，再要求 `count == len(rows)`。
- rowcount 缺失抛 `discovery_repository_rowcount_required`。
- bool、负数、非整数或与 RETURNING rows 不一致抛 `discovery_repository_rowcount_invalid`。
- `terminalize_lookup_claims(...)` 只在 `_returned_rowcount(...)` 通过后写 terminal ledger，并返回
  PostgreSQL 证明的 `deleted_count`，不再返回 `len(deleted_rows)`。

验证：

- RED：focused Discovery terminal RETURNING rowcount 命令初始失败 `9 failed`，证明旧实现会在 rowcount
  缺失/非法/不一致时继续进入 terminal ledger，architecture guard 找不到 `_returned_rowcount(...)`
  并命中旧的 `len(deleted_rows)` accounting。
- GREEN：同一 focused 命令通过，`9 passed`。
- Discovery repository / runtime worker hard-cut architecture 非集成组通过，`45 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认 `discovery_repository.py` 已无
  `len(deleted_rows)` / `deleted_count = len(deleted_rows)`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root380 - Registry US equity deactivation 用 RETURNING rows/len(row) 冒充 changed-row count

发现：

- `RegistryRepository.deactivate_missing_us_equity_symbols(...)` 通过
  `UPDATE us_equity_symbols ... RETURNING symbol` 下线未出现在 Nasdaq Trader 当前集合里的股票 symbol。
- 旧实现把 `fetchall()` 结果放进 `row`，然后返回 `len(row)`。
- active-symbols 非空和空集合两个分支都存在同一类问题：返回值来自 RETURNING result set 长度，而不是 PostgreSQL cursor
  rowcount。

根因：

- `us_equity_symbols` 不是 UI 辅助表，而是确定性 resolver 的 registry 事实/控制状态。它决定 US equity symbol 能否在
  same-symbol DEX 资产前被提升，也会影响 Stocks Radar social/read 路径的解释边界。
- returned symbols 虽然来自 PostgreSQL，但它仍只是结果集。成熟 PostgreSQL 写路径要把 DML execution evidence
  和 result set 区分开：cursor rowcount 必须存在、类型合法、非负，并且与 returned symbols 数量一致。
- 旧实现会让 fake cursor、driver adapter 缺失 rowcount、rowcount 类型错误、或者 rowcount/RETURNING 不一致的问题被
  `len(row)` 掩盖。结果是 registry 状态的 changed-row accounting 看似成功，实际缺少 PostgreSQL 执行证据。

修复：

- `deactivate_missing_us_equity_symbols(...)` 现在保存 UPDATE cursor，执行 `fetchall()`，并返回
  `_returned_rowcount(cursor, rows)`。
- `_cursor_rowcount(cursor)` 直接读取 `cursor.rowcount`，缺失抛 `registry_repository_rowcount_required`。
- bool、负数、非整数 rowcount 抛 `registry_repository_rowcount_invalid`。
- `_returned_rowcount(cursor, rows)` 要求 rowcount 与 returned symbols 数量一致，不再接受 `return len(row)` 或
  `return len(rows)` 式兼容计数。

验证：

- RED：focused Registry US equity deactivate RETURNING rowcount 命令初始失败 `9 failed`，证明旧实现接受缺失/非法/不一致
  rowcount，architecture guard 找不到 `_returned_rowcount(...)` 合同。
- GREEN：同一 focused 命令通过，`9 passed`。
- Registry repository / runtime worker hard-cut architecture 非集成组通过，`20 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认 `registry_repository.py` 已无
  `return len(row)`、`return len(rows)`、rowcount `getattr(...)` 或 `int(...)` 兼容路径。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root381 - Token Image Asset lifecycle 用 RETURNING row/静默 UPDATE 绕过单行 rowcount 证据

发现：

- `TokenImageAssetRepository.upsert_pending_sources(...)` 逐条执行
  `INSERT INTO token_image_assets ... ON CONFLICT ... RETURNING image_id`。
- 旧实现用 `row is not None` 累加 `affected`，等价于把 RETURNING row 是否存在当成 changed-row count。
- `mark_ready(...)` 也通过 `UPDATE ... RETURNING *` 返回 ready row，但没有验证 cursor rowcount。
- `mark_error(...)` 和 `mark_unsupported(...)` 是同一张 `token_image_assets` lifecycle 表的单行 UPDATE，旧实现静默执行 SQL，
  不验证 PostgreSQL 是否提供了合法 rowcount。

根因：

- `token_image_assets` 是本地 media mirror 的 rebuildable read-side 状态，公共 profile/icon URL 只能来自 ready local rows，
  不能来自 provider URL。它虽不是业务事实表，但它是 profile-current 公共读路径的重要支撑。
- pending/ready/error/unsupported lifecycle mutation 是单行目标写入。成熟 PostgreSQL 写路径要证明 cursor rowcount 存在、
  类型合法、非 bool、非负，并且只能是 `0` 或 `1`。
- 对带 RETURNING 的 pending/ready 路径，还必须证明 rowcount 与 returned row 是否存在一致。否则 fake cursor、driver adapter
  缺失 rowcount、rowcount 类型错误、或 rowcount/RETURNING 不一致的问题会被 returned row 掩盖。

修复：

- `upsert_pending_sources(...)` 捕获 cursor，`fetchone()` 后通过 `_single_returning_rowcount(cursor, row)` 累加 affected。
- `mark_ready(...)` 捕获 cursor，先验证 `_single_returning_rowcount(cursor, row)`，再返回 ready row 或抛缺失 source 的错误。
- `mark_error(...)` 和 `mark_unsupported(...)` 通过 `_single_rowcount(cursor)` 验证单行 UPDATE 证据。
- `_cursor_rowcount(cursor)` 缺失抛 `token_image_asset_repository_rowcount_required`；bool、负数、非整数、multi-row、或
  rowcount/RETURNING 不一致抛 `token_image_asset_repository_rowcount_invalid`。

验证：

- RED：focused Token Image Asset lifecycle rowcount 命令初始失败 `31 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，
  architecture guard 命中 `row is not None` / `affected += 1` 计数。
- GREEN：同一 focused 命令通过，`31 passed`。
- Token Image Asset repository / architecture 非集成组通过，`40 passed`。
- Token Image Mirror worker/service 相关非集成组通过，`30 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认 `token_image_asset_repository.py` 已无旧的
  `row is not None` affected 计数、rowcount `getattr(...)` 或 `return int(rowcount)` 兼容路径。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root382 - Event Anchor job RETURNING 路径用 returned row/list 长度代替 PostgreSQL rowcount 证据

发现：

- `EventAnchorBackfillJobRepository.claim_due(...)` 通过 `UPDATE event_anchor_backfill_jobs ... RETURNING jobs.*` 领取 job，
  旧实现直接返回 `fetchall()` 的 rows。
- `mark_done(...)` 和 `reschedule(...)` 通过 `UPDATE ... RETURNING event_id, intent_id` 返回 bool，旧实现是
  `return row is not None`。
- `mark_terminal(...)` 通过 `UPDATE ... RETURNING *` 后写 `worker_queue_terminal_events`，旧实现只检查 `row is None`，
  没有证明 PostgreSQL 实际 changed-row count 与 returned row 一致。
- terminal retry、stale cleanup helper、historical-ready reconcile 也都依赖 `UPDATE ... RETURNING` rows 或
  `len(updated_rows)` 报告状态推进。

根因：

- `event_anchor_backfill_jobs` 是 Event Anchor worker 的控制面，不是产品事实；但它决定一次事件 market anchor
  backfill 是否被领取、重试、done、expired、failed 或重新投回 pending。
- 这个表的状态推进会进一步影响 `enriched_events` lifecycle 和 terminal ledger。尤其 terminal path 必须先证明
  job row 的 CAS 更新真实发生，才能写 `worker_queue_terminal_events`。
- 成熟 PostgreSQL 写路径需要区分 result set 和 execution evidence：`RETURNING` rows 是数据，`cursor.rowcount`
  是 DML 证据。fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，不能用 returned row/list
  继续构造 worker 状态。

修复：

- `claim_due(...)`、stale cleanup helpers、historical-ready reconcile 改为捕获 cursor 后调用 `_returning_rows(cursor)`；
  helper 会先验证 `_returned_rowcount(cursor, rows)`。
- `mark_done(...)`、`mark_terminal(...)`、terminal retry、`reschedule(...)` 改为 `_single_returning_rowcount(cursor, row)`；
  单行 CAS 只接受 `0/1`，并要求 rowcount 与 returned row 是否存在一致。
- `_cursor_rowcount(cursor)` 缺失抛 `event_anchor_job_repository_rowcount_required`；bool、负数、非整数、多行、
  或 rowcount/RETURNING 不一致抛 `event_anchor_job_repository_rowcount_invalid`。
- terminal ledger 写入现在发生在 rowcount/RETURNING 一致性验证之后。

验证：

- RED：focused Event Anchor job RETURNING rowcount 命令初始失败 `35 failed`，证明旧实现接受缺失/非法/mismatched
  rowcount，architecture guard 命中 returned-row / returned-list accounting。
- GREEN：同一 focused 命令通过，`35 passed`。
- Event Anchor repository / worker / runtime architecture 非集成组通过，`67 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认旧的 `return row is not None`、
  rowcount `getattr(...)`、rowcount `or 0` 和 `"updated_count": len(updated_rows)` fallback 已从
  `event_anchor_backfill_job_repository.py` 移除。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root383 - Token Profile Current upsert 用 RETURNING 行存在性冒充 changed-row 证据

发现：

- `TokenProfileCurrentRepository.upsert_current(...)` 已经通过 `payload_hash IS DISTINCT FROM` 保证 unchanged public profile/icon row 不写 serving row。
- 但旧实现执行 `INSERT ... ON CONFLICT ... RETURNING true AS changed` 后，通过 `getattr(returned, "fetchone", None)` 和 `changed_row is not None` 报告 changed 布尔值。
- `TokenProfileCurrentWorker` 直接用这个布尔值累加 `rows_written`，所以 fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，worker 可能把“拿到了 returned row”当成“PostgreSQL 实际写了 current row”。

根因：

- Root66 解决了 `token_profile_current` repository-owned commit 的事务边界，Root354 解决了 profile dirty-target completion rowcount，但 current-row upsert 自身的 changed 证据仍停留在 result set presence。
- 对成熟 CQRS/Kappa 来说，`token_profile_current` 是公共 profile/icon 当前读模型：稳定 key 是 `(target_type, target_id)`，unchanged path 必须写零 serving rows，`rows_written` 必须是 PostgreSQL 执行证据，而不能是 cursor 返回形状。
- `RETURNING true AS changed` 返回的是数据行；`cursor.rowcount` 才是 DML 执行证据。两者必须一致，且单行 current-row upsert 只能接受 `0/1`。

修复：

- `upsert_current(...)` 改为捕获 cursor，`fetchone()` 后通过 `_single_returning_changed(cursor, row)` 返回 changed。
- `_cursor_rowcount(cursor)` 缺失抛 `token_profile_current_repository_rowcount_required`；bool、负数、非整数、多行、或 rowcount/RETURNING 不一致抛 `token_profile_current_repository_rowcount_invalid`。
- 架构守护禁止恢复 optional `fetchone` probing、`changed_row is not None`、或 returned-row presence changed accounting。

验证：

- RED：focused Token Profile Current RETURNING changed rowcount 命令初始失败 `10 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard 命中 optional `fetchone` probing 和 returned-row changed accounting。
- GREEN：同一 focused 命令通过，`10 passed`。
- Token Profile Current repository / worker / read-model 非集成组通过，`42 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root384 - Market Tick Current upsert 用 RETURNING 行存在性冒充 changed/wake 证据

发现：

- `MarketTickCurrentRepository.upsert_current_from_tick(...)` 已经通过 `IS DISTINCT FROM` 约束 unchanged market current row 不写 serving row。
- 但旧实现执行 `INSERT ... ON CONFLICT ... RETURNING true AS changed` 后直接 `.fetchone()`，再用 `bool(row and row["changed"])` 报告 changed。
- `MarketTickCurrentProjectionWorker` 用这个 changed 布尔值决定是否 enqueue Token Radar market dirty work、是否发 `market_tick_current_updated` wake，因此 fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，可能把“拿到了 returned row”当成“PostgreSQL 实际写了 current market row”。

根因：

- Root355/Root370 已经把 `market_tick_current_dirty_targets` 的 completion/enqueue rowcount 证据硬化，但 serving `market_tick_current` upsert 本身还停留在 result-set presence。
- 对成熟 CQRS/Kappa 来说，`market_tick_current` 是所有市场热路径的 compact current read model：稳定 key 是 `(target_type, target_id)`，unchanged path 必须写零 serving rows，下游 dirty enqueue 和 wake 决策必须来自 PostgreSQL DML 证据。
- `RETURNING true AS changed` 返回的是数据行；`cursor.rowcount` 才是 DML 执行证据。两者必须一致，且单行 current-row upsert 只能接受 `0/1`。

修复：

- `upsert_current_from_tick(...)` 改为捕获 cursor，`fetchone()` 后通过 `_single_returning_changed(cursor, row)` 返回 changed。
- `_cursor_rowcount(cursor)` 缺失抛 `market_tick_current_repository_rowcount_required`；bool、负数、非整数、多行、或 rowcount/RETURNING 不一致抛 `market_tick_current_repository_rowcount_invalid`。
- 架构守护禁止恢复 `return bool(row and row["changed"])`、`dict(row or {})`、或 returned-row presence changed accounting。

验证：

- RED：focused Market Tick Current RETURNING changed rowcount 命令初始失败 `8 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard 也找不到 rowcount helper。
- GREEN：同一 focused 命令通过，`8 passed`。
- Market Tick Current repository / worker / architecture 非集成组通过，`49 passed`。
- targeted ruff 和 repository mypy 通过；production-only residual scan 确认旧的 `return bool(row and row["changed"])`、`dict(row or {})` 和 returned-row-only changed accounting 已从 `market_tick_current_repository.py` 移除。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root385 - Token Capture Tier upsert 用 RETURNING 行存在性冒充 rows_written 证据

发现：

- `TokenCaptureTierRepository.upsert_tier(...)` 已经通过 `IS DISTINCT FROM`
  约束 unchanged capture-tier row 不写 serving/control projection row。
- 但旧实现执行 `INSERT ... ON CONFLICT ... RETURNING true AS changed` 后直接
  `.fetchone()`，再用 returned-row presence 报告 changed。
- `TokenCaptureTierWorker` 会把这个 changed 布尔值累计进 `rows_written`，
  因此 fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，可能把
  “拿到了 returned row”当成“PostgreSQL 实际插入或更新了 capture tier row”。

根因：

- Root361 已经把 `token_capture_tier_dirty_targets` 的 enqueue/done rowcount
  证据硬化，Root362 已经把 hot-tier demotion rowcount 证据硬化，但 serving/control
  `token_capture_tier` upsert 本身还停留在 result-set presence。
- 对成熟 CQRS/Kappa 来说，`token_capture_tier` 是 Token Radar rank-set 派生出的
  capture-control projection：稳定 key 是 `(target_type, target_id)`，unchanged path
  必须写零 rows，worker 的 `rows_written` 必须来自 PostgreSQL DML 证据。
- `RETURNING true AS changed` 只能说明 SQL 返回了行；`cursor.rowcount` 才是 DML
  执行证据。单行 capture-tier upsert 只能接受 `0/1` rowcount，并且必须与
  returned-row presence 完全一致。

修复：

- `upsert_tier(...)` 改为捕获 cursor，`fetchone()` 后通过
  `_single_returning_changed(cursor, row)` 返回 changed。
- `_cursor_rowcount(cursor)` 缺失抛
  `token_capture_tier_repository_rowcount_required`；bool、负数、非整数、多行、
  或 rowcount/RETURNING 不一致抛 `token_capture_tier_repository_rowcount_invalid`。
- 架构守护禁止恢复 `return row is not None`、`dict(row or {})`、或
  returned-row presence changed accounting。

验证：

- RED：focused Token Capture Tier RETURNING changed rowcount 命令初始失败
  `9 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  也找不到 `_single_returning_changed` helper。
- GREEN：同一 focused 命令通过，`9 passed`。
- Token Capture Tier repository / worker / dirty-target architecture 非集成组通过，
  `50 passed`。
- targeted ruff 和 repository mypy 通过；residual scan 确认旧的 returned-row-only
  changed accounting 已从 `token_capture_tier_repository.py` 移除。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root386 - Asset Identity Current upsert 用 RETURNING 行存在性冒充 identity rows_written 证据

发现：

- `IdentityEvidenceRepository.recompute_current_identity(...)` 会用 deterministic
  policy 从 `asset_identity_evidence` 选择当前 canonical symbol/name/confidence，
  然后把 `_upsert_current_identity(...)` 返回的 changed 布尔值转成
  `rows_written`。
- 但旧实现执行 `INSERT ... ON CONFLICT ... RETURNING true AS changed` 后用
  optional `fetchone` probing 和 returned-row presence 报告 changed。
- 这意味着 fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，身份
  current row 可能被报告为已写入，即使 PostgreSQL 没有提供有效 DML 证据。

根因：

- Root60 已经把 `IdentityEvidenceRepository` 的 repository-owned transaction
  边界硬化，但 current identity write 的 changed accounting 仍保留旧的 result-set
  presence 语义。
- `asset_identity_current` 虽然是 identity truth/current selection，不是普通 public
  read model，但它是 Token Radar resolved Asset payload 的上游门控证据。成熟
  Kappa/CQRS 里，这种 current-row projection/fact selection 必须有稳定 key
  `asset_id`，unchanged path 写零行，`rows_written` 必须来自 PostgreSQL DML 证据。
- `RETURNING true AS changed` 返回的是结果行；`cursor.rowcount` 才是执行证据。
  单行 current identity upsert 只能接受 `0/1` rowcount，并且必须与 returned-row
  presence 完全一致。

修复：

- `_upsert_current_identity(...)` 改为捕获 cursor，`fetchone()` 后通过
  `_single_returning_changed(cursor, row)` 返回 changed。
- `_cursor_rowcount(cursor)` 缺失抛
  `identity_evidence_repository_rowcount_required`；bool、负数、非整数、多行、
  或 rowcount/RETURNING 不一致抛 `identity_evidence_repository_rowcount_invalid`。
- 架构守护禁止恢复 optional `fetchone` probing、`dict(row or {})`、或
  returned-row presence changed accounting。

验证：

- RED：focused Asset Identity Current RETURNING changed rowcount 命令初始失败
  `9 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  也找不到 `_cursor_rowcount` helper。
- GREEN：同一 focused 命令通过，`9 passed`。
- Asset Identity repository / ingest / resolution-refresh architecture 非集成组通过，
  `41 passed`。
- targeted ruff 和 repository mypy 通过；residual scan 确认旧的 optional fetchone
  / returned-row-only changed accounting 已从 `identity_evidence_repository.py` 移除。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root387 - Macro current snapshot / daily brief 用 RETURNING 行存在性冒充 changed 证据

发现：

- `MacroIntelRepository.insert_snapshot(...)` 和
  `upsert_macro_daily_brief(...)` 都已经用 `payload_hash IS DISTINCT FROM`
  约束 unchanged current row 不写 serving row。
- 但旧实现执行 `INSERT ... ON CONFLICT ... RETURNING true AS changed` 后直接
  `.fetchone()`，再通过 `bool(dict(row or {}).get("changed", False))`
  报告 changed。
- `MacroViewProjectionWorker` 用 snapshot changed 决定是否发
  `macro_view_snapshot_updated`，`MacroDailyBriefProjectionWorker` 用 daily brief
  changed 累加 `rows_written`。因此 fake cursor、driver adapter、或
  rowcount/RETURNING 不一致时，Macro 可能把“拿到了 returned row”误报成
  “PostgreSQL 实际写了 current read model row”。

根因：

- 前面 Root59/Root88 已经硬化了 Macro projection 的 session transaction 和
  dirty-target rowcount，但 `macro_view_snapshots` 与 `macro_daily_briefs` 这两个
  current serving row 的 changed accounting 仍停在 result-set presence。
- 成熟 Kappa/CQRS 对 current read model 的要求不只是稳定 key 和
  `payload_hash` gate；worker 的 wake、`rows_written`、freshness 诊断也必须来自
  PostgreSQL DML 执行证据。
- `RETURNING true AS changed` 返回的是结果行；`cursor.rowcount` 才是执行证据。
  单行 current-row upsert 只能接受 `0/1` rowcount，并且必须与 returned-row
  presence 完全一致。

修复：

- `insert_snapshot(...)` 和 `upsert_macro_daily_brief(...)` 改为捕获 cursor，
  `fetchone()` 后通过 `_single_returning_changed(cursor, row)` 返回 changed。
- `_cursor_rowcount(cursor)` 缺失抛 `macro_intel_repository_rowcount_required`；
  bool、负数、非整数、多行、或 rowcount/RETURNING 不一致抛
  `macro_intel_repository_rowcount_invalid`。
- 架构守护禁止恢复 `return bool(dict(row or {}).get("changed", False))` 或
  returned-row-only changed accounting。

验证：

- RED：focused Macro current RETURNING changed rowcount 命令初始失败
  `17 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  命中旧 fallback。
- GREEN：同一 focused 命令通过，`17 passed`。
- Macro 单元目录 + Macro 架构 + runtime worker 静态约束非集成组通过，
  `439 passed`。
- targeted ruff 通过；repository mypy 通过。对包含测试文件的严格 mypy 命令仍命中
  既有测试 typing 债，本轮以生产文件 mypy 和非集成测试作为有效证据。
- production residual scan 确认旧的
  `return bool(dict(row or {}).get("changed", False))` 已从 `src/parallax`
  生产代码移除。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root388 - News zero-edge 旧 item 删除用 RETURNING 行存在性冒充删除证据

发现：

- `NewsRepository._delete_zero_edge_news_item(...)` 在 canonical edge remap
  cleanup 后删除没有 observation edge 的旧 `news_items`。
- 旧实现执行 `DELETE FROM news_items ... RETURNING items.news_item_id` 后直接
  `.fetchone()`，再用 `row is not None` 返回删除成功。
- 这个路径会影响 canonical item remap 后的事实整理和后续 page reprojection
  affected set。fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，
  NewsRepository 可能把“拿到了返回行”当成“PostgreSQL 实际删除了一行旧
  news item”。

根因：

- 前面 Root352/Root378 已经要求 NewsRepository 普通 changed-row accounting
  和 source-disable RETURNING 路径使用真实 rowcount，但 canonical cleanup 的
  zero-edge delete 仍停留在 result-set presence。
- 成熟 Kappa/CQRS 里，canonical remap 后的旧事实清理不是普通内存整理；它是
  material fact 与 projection dirty set 之间的状态转换。返回行是数据，不能单独
  作为 DML 执行证据。
- PostgreSQL 最佳实践要求 `DELETE ... RETURNING` 的 cursor rowcount 必须存在、
  类型合法、非负，并且与 returned rows 数量一致；否则应该暴露 repository/driver
  合同错误，而不是把返回行存在性转换成 boolean。

修复：

- `_delete_zero_edge_news_item(...)` 改为捕获 cursor，`fetchone()` 后构造
  returned rows，并通过 `_returned_rowcount(cursor, rows)` 校验 rowcount 与返回行
  数一致。
- rowcount 缺失抛 `news_repository_rowcount_required`；bool、负数、非整数、
  或 rowcount/RETURNING 不一致抛 `news_repository_rowcount_invalid`。
- 架构守护禁止恢复 `return row is not None`，并要求该 delete-returning helper
  使用 `_returned_rowcount(...)` 后再返回 boolean。

验证：

- RED：focused News zero-edge delete RETURNING rowcount 命令初始失败
  `10 failed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  命中旧的 returned-row-only boolean accounting。
- GREEN：同一 focused 命令通过，`10 passed`。
- NewsRepository 单元文件 + 相关 News architecture guards 非集成组通过，
  `105 passed`。
- targeted ruff 通过；`news_repository.py` mypy 通过。
- residual scan 确认 `_delete_zero_edge_news_item(...)` 已使用
  `_returned_rowcount(cursor, rows)`；相邻 `row is not None` 命中属于
  `SELECT ... FOR UPDATE` lock helper，不是 delete-returning accounting。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root389 - worker_queue_terminal_events ledger 写入用 RETURNING 行存在性冒充平台 terminal 证据

发现：

- `terminalize_source_row(...)` 写 `worker_queue_terminal_events` 时执行
  `INSERT ... ON CONFLICT ... RETURNING *`，旧实现直接 `.fetchone()` 后返回
  `_row_dict(row)`。
- `resolve_terminal_event(...)` 对 operator retry/archive/quarantine 执行
  `UPDATE worker_queue_terminal_events ... RETURNING *`，旧实现同样只看返回行，
  随后可能运行 retry transition。
- 这意味着 fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，平台层会把
  “拿到了 terminal ledger 返回行”误当成“PostgreSQL 确实写入或更新了唯一的
  terminal 控制面证据”。

根因：

- 前面多个 roots 已经把 caller-side 终止队列收紧为：先验证
  `DELETE/UPDATE ... RETURNING` 的 cursor rowcount，再写
  `worker_queue_terminal_events`。
- 但共享平台账本自身仍停在 result-set presence。这个位置比普通 domain repository
  更关键，因为 terminal ledger 是 worker 终止证据、operator 行动、以及 retry
  transition 的共同控制面。
- 成熟 Kappa/CQRS 架构要求 derived/control read model 的每一次状态转换都有可验证的
  PostgreSQL DML 执行证据；`RETURNING` 返回的是数据，`cursor.rowcount` 才是执行证据。
  operator retry transition 更不能在 malformed update evidence 之后继续运行。

修复：

- `terminalize_source_row(...)` 和 `resolve_terminal_event(...)` 改为捕获 cursor，
  `fetchone()` 后通过 `_single_returning_rowcount(cursor, row)` 验证。
- `_cursor_rowcount(cursor)` 缺失抛 `queue_terminal_rowcount_required`；bool、负数、
  非整数、多行、或 rowcount/RETURNING 不一致抛
  `queue_terminal_rowcount_invalid`。
- `resolve_terminal_event(...)` 在 retry transition 前完成 rowcount 校验，确保 operator
  action payload 与 retry 重排不会来自 malformed update evidence。

验证：

- RED：focused Queue Terminal RETURNING rowcount 命令初始失败 `10 failed`，证明旧实现不检查
  缺失/非法/mismatched rowcount，architecture guard 命中缺失的 `_cursor_rowcount`
  合同。
- GREEN：同一 focused 命令通过，`10 passed`。
- 更宽的 Queue Terminal 非集成组通过，`26 passed`；targeted ruff 和
  `queue_terminal.py` production mypy 通过；residual scan 确认
  `terminalize_source_row(...)` / `resolve_terminal_event(...)` 都在返回 terminal
  rows 或运行 retry transition 前调用 `_single_returning_rowcount(cursor, row)`。
- SDD validator、work-index regen/check 和 `git diff --check` 均通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root390 - app/runtime/job_queue 保留未接线通用队列执行器，形成第二套控制面生命周期入口

发现：

- 早期生成审计已经标记过 `app/runtime/job_queue.py` “看起来未接线”。
- 当前生产代码里，`JobQueue` 类没有 runtime 实例化；`ops_diagnostics` 只需要
  `JOB_QUEUE_DESCRIPTORS` / `JobQueueDescriptor` 来枚举 `pulse_agent_jobs` 和
  `notification_deliveries` 的只读状态。
- 但旧模块仍保留 `BackoffPolicy`、`JobQueue.claim_batch(...)`、
  `finalize_success(...)`、`finalize_failure(...)` 和 `reclaim_stale(...)`，其中还包含
  UUID lease token、time-based now、`UPDATE ... RETURNING *` claim/finalize SQL。

根因：

- 这是典型的“迁移到 domain repository 后，没有删除旧泛化执行器”的兼容残留。
- 对成熟 Kappa/CQRS 来说，`pulse_agent_jobs` 和 `notification_deliveries` 是控制面状态，
  不是一个可以被 app-runtime 泛型 helper 任意 claim/finalize 的通用表。
- 当前架构已经把 Pulse job 生命周期交给 `PulseJobsRepository`，把 notification delivery
  生命周期交给 `NotificationRepository` / delivery worker session transaction。保留一个未接线但
  可执行的通用 `JobQueue` 会制造第二套 retry/backoff/lease/stale 语义，并绕开前面已经硬化的
  domain-specific rowcount、transaction、claim-field 合同。

修复：

- `src/parallax/app/runtime/job_queue.py` 收窄为 descriptor-only 模块，只暴露
  `JobQueueDescriptor`、`PULSE_AGENT_JOBS`、`NOTIFICATION_DELIVERIES` 和
  `JOB_QUEUE_DESCRIPTORS`。
- 删除 `BackoffPolicy`、`JobQueue`、`claim_batch`、`finalize_success`、
  `finalize_failure`、`reclaim_stale`、UUID/time 生成和旧 `RETURNING *` executor SQL。
- `tests/unit/test_job_queue.py` 改为验证 ops diagnostic descriptor 元数据；架构守护禁止
  通用 executor token 回归，同时确认 `ops_diagnostics` 仍只读导入 descriptors。

验证：

- RED：focused JobQueue descriptor-only 命令初始失败 `1 failed, 3 passed`，architecture guard
  命中旧 `BackoffPolicy` / `JobQueue` / claim/finalize/reclaim / UUID/time / `RETURNING *`
  executor SQL。
- GREEN：同一 focused 命令通过，`4 passed`。
- 更宽的 descriptor-only worker-runtime 非集成组通过，`5 passed`。
- targeted ruff 通过；`job_queue.py` + `ops_diagnostics.py` mypy 通过。
- production residual scan 对 `src/parallax/app/runtime/job_queue.py` 无旧 executor token 命中，确认
  `BackoffPolicy` / `JobQueue` / claim/finalize/reclaim / UUID/time / `RETURNING *` 已从生产模块移除。
- SDD validator、work-index regen/check 和 `git diff --check` 均通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root391 - Pulse admission edge/budget 写入用 RETURNING 行存在性冒充预算和边状态证据

发现：

- `PulseAdmissionRepository.claim_edge_budget(...)` 对
  `pulse_candidate_run_budget` 执行
  `INSERT ... ON CONFLICT ... WHERE enqueue_count < max ... RETURNING enqueue_count`，
  旧实现直接用 `row is not None` 判断是否拿到 candidate edge budget。
- `record_edge_observation(...)`、`mark_edge_job_enqueued(...)`、
  `mark_edge_budget_rejected(...)`、`_mark_edge_suppressed(...)`、
  `_mark_edge_admitted(...)`、`mark_edge_run_finished(...)` 等 edge-state 路径也都
  `RETURNING *` 后直接把返回行转成 required/optional row。
- 这些路径决定 Pulse admission 是否继续 enqueue agent、是否 suppress edge、以及 edge state
  是否进入下一次 dirty-trigger 判断。fake cursor、driver adapter、或 rowcount/RETURNING
  不一致时，旧代码会把“返回行存在或不存在”当成“PostgreSQL 确实执行了预期的单行状态转换”。

根因：

- 前面已经收紧了 Pulse job 生命周期和 dirty-trigger completion rowcount，但
  admission repository 的 edge/budget 小状态机仍停留在 result-set presence。
- 对成熟 Kappa/CQRS 来说，`pulse_candidate_edge_state` 和
  `pulse_candidate_run_budget` 是控制面节流与 admission 边状态，不是普通内存缓存。
  budget boolean 必须来自 PostgreSQL DML 执行证据；否则 worker 可能在预算未真实写入时
  enqueue agent，或在 edge state 未真实更新时推进后续状态。
- PostgreSQL 最佳实践要求单行 `RETURNING` 路径检查 `cursor.rowcount` 是否为合法 0/1，并且
  与返回行存在性一致。返回行是数据，rowcount 才是执行证据。

修复：

- `PulseAdmissionRepository` 新增 `_cursor_rowcount(...)`、
  `_single_returning_rowcount(...)`、`_required_returning_row(...)` 和
  `_optional_returning_row(...)`。
- required edge upsert 路径必须 rowcount=1 且有返回行；optional edge-state update 路径允许
  rowcount=0/1，但必须与返回行存在性一致。
- `claim_edge_budget(...)` 只在 `_single_returning_rowcount(cursor, row) == 1` 后返回
  `True`，预算耗尽的 no-row 情况必须由 PostgreSQL rowcount=0 证明。
- 架构守护禁止恢复 `return row is not None` 和 rowcount 默认兜底。

验证：

- RED：focused PulseAdmission returning-rowcount 命令初始失败
  `13 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  命中缺失的 `_cursor_rowcount` 合同。
- GREEN：同一 focused 命令通过，`14 passed`。
- Pulse admission/transaction 非集成组通过，`34 passed`。
- targeted ruff 通过；`pulse_admission_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root392 - Pulse playbook snapshot/outcome 写入把返回行和回读 SELECT 当成 playbook 写入证据

发现：

- `PulsePlaybooksRepository.upsert_playbook_snapshot(...)` 对
  `pulse_playbook_snapshots` 执行
  `INSERT ... ON CONFLICT ... DO UPDATE ... WHERE ... IS DISTINCT FROM ... RETURNING *`。
  旧实现先 `fetchone()`，如果没有返回行，再用同一个 stable key 做 `SELECT *` 回读。
- 这意味着 PostgreSQL 明确表示“冲突行内容未变化，因此 rowcount=0/no row”时，repository
  会把旧行读回来并返回成一次成功写入。
- `upsert_playbook_outcome(...)` 也直接把 `RETURNING *` 的返回行转成 playbook outcome row，
  没有验证 cursor rowcount 是否存在、是否合法、是否与返回行一致。

根因：

- Pulse playbook 是 agent 决策后的审计/执行建议 read model，仍属于单 writer、可重放的
  Kappa/CQRS 派生状态。它不能把“读到了既有行”冒充成“本轮确实写了行”。
- `ON CONFLICT ... WHERE ... IS DISTINCT FROM` 的成熟用法正是为了让 unchanged projection 写
  零行；旧 fallback SELECT 把这个 PostgreSQL 信号抹平，重新引入了“为了返回看起来完整的 row
  而兼容回读”的习惯。
- 与前面的 admission/job rowcount 问题同源：返回行是数据，不是 DML 执行证据；执行证据必须来自
  PostgreSQL `cursor.rowcount`，并且要和返回行存在性一致。

修复：

- `PulsePlaybooksRepository` 新增 `_cursor_rowcount(...)`、
  `_required_returning_row(...)` 和 `_optional_returning_row(...)`。
- snapshot 写入允许唯一的 no-op 形态：rowcount=0 且 no row，返回 `None`；changed snapshot
  必须 rowcount=1 且有返回行。
- outcome 写入是 required single-row `RETURNING`，必须 rowcount=1 且有返回行。
- 删除 snapshot fallback `SELECT`；架构守护禁止恢复 `return _row(row)`、fallback `SELECT *`、
  以及 rowcount 默认兜底。

验证：

- RED：focused PulsePlaybooks returning-rowcount 命令初始失败
  `17 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，且 snapshot no-row
  会跑 fallback SELECT。
- GREEN：同一 focused 命令通过，`19 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root393 - Pulse public candidate upsert/hide 用 fallback SELECT 抹平零写入信号

发现：

- `PulseCandidatesRepository.upsert_candidate(...)` 对 `pulse_candidates` 执行
  `INSERT ... ON CONFLICT ... DO UPDATE ... WHERE ... IS DISTINCT FROM ... RETURNING *`。
  旧实现如果 `fetchone()` 为空，会立刻执行
  `SELECT * FROM pulse_candidates WHERE candidate_id = %s`，再把回读行返回。
- 这会把 PostgreSQL 的“unchanged projection，rowcount=0/no row”改写成“repository 返回了候选行”，
  等于让公开 read model 的零写入看起来像一次成功写入。
- `hide_public_candidate_for_low_information(...)` 也直接把 optional `RETURNING *` 返回行转成
  optional row，没有验证 cursor rowcount 是否存在、是否合法、是否与返回行一致。

根因：

- `pulse_candidates` 是 Signal Pulse 的公开 read model，正是 Kappa/CQRS 中最不应该靠请求期或
  repository fallback 补语义的表。
- 旧代码把“返回一个方便调用方使用的 row”优先级放在“保留 PostgreSQL 执行事实”之上，导致
  unchanged projection 与 changed projection 在 repository 边界被混淆。
- 成熟方案应让 DML 证据、返回数据和 read model 语义分离：rowcount=0/no row 表示没有服务行变化；
  rowcount=1/row 表示写入或状态转换发生；缺失/非法/mismatched rowcount 表示 driver/repository
  证据损坏。

修复：

- `PulseCandidatesRepository` 新增 `_cursor_rowcount(...)` 和 `_optional_returning_row(...)`。
- public candidate upsert 与 low-information hide 都验证 rowcount 为合法 0/1，并要求与返回行存在性一致。
- unchanged candidate upsert 或 no-op hide 返回 `None`；changed candidate write 必须 rowcount=1 且有返回行。
- 删除 candidate fallback `SELECT`；架构守护禁止恢复 fallback `SELECT *`、`return _row(row)`、
  `return _optional_row(row)` 和 rowcount 默认兜底。

验证：

- RED：focused PulseCandidates returning-rowcount 命令初始失败
  `18 failed, 3 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，且 candidate no-row upsert
  会跑 fallback SELECT。
- GREEN：同一 focused 命令通过，`21 passed`。
- Pulse candidate/playbook/transaction 非集成组通过，`58 passed`；targeted ruff 和
  `pulse_candidates_repository.py` mypy 通过。
- 未来 integration 断言已改为 no-change upsert 返回 `None`；按当前用户指令，本轮不运行 integration-heavy gate。

### Root394 - Pulse agent run/step audit 写入把 RETURNING 行当成审计账本执行证据

发现：

- `PulseRunsRepository.insert_agent_run(...)`、`finish_agent_run(...)` 和
  `insert_agent_run_step(...)` 都使用 `RETURNING *` 后直接返回 `_row(row)` 或
  `_optional_row(row)`。
- fake cursor、driver adapter、或 rowcount/RETURNING 不一致时，旧代码会把“返回行存在”
  当成“PostgreSQL 确实写入/更新了一条 agent audit row”。
- `finish_agent_run(...)` 虽然先读 existing run，但后续 UPDATE 的执行证据仍没有被验证；
  required insert/upsert 路径则在 no row 时会退化成低层 `NoneType` 转换错误，而不是清晰的 repository
  rowcount 合同错误。

根因：

- Pulse agent audit ledger 是 worker 决策链的因果账本：run、step、cost、模型响应、证据包 hash 和
  public candidate 写入都依赖它解释“这次 agent 到底发生了什么”。
- 前面已经修了 job、admission、candidate、playbook 的 PostgreSQL 执行证据，但 run/step 审计表仍停在
  result-set presence 模式。
- 成熟的 Kappa/CQRS 写侧应把 audit row 当作可验证事实，而不是“只要 driver 给了 row 就算成功”。
  required insert/upsert 必须 rowcount=1 且有 row；optional finish 必须让 0/1 rowcount 和返回行一致。

修复：

- `PulseRunsRepository` 新增 `_cursor_rowcount(...)`、
  `_required_returning_row(...)` 和 `_optional_returning_row(...)`。
- `insert_agent_run(...)` 与 `insert_agent_run_step(...)` 必须 rowcount=1 且有返回行。
- `finish_agent_run(...)` 在 existing-run SELECT 后验证 UPDATE rowcount 与返回行存在性一致。
- 架构守护禁止恢复 direct `_row(row)` / `_optional_row(row)` 返回和 rowcount 默认兜底。

验证：

- RED：focused PulseRuns returning-rowcount 命令初始失败
  `26 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`27 passed`。
- Pulse run/candidate/playbook/transaction 非集成组通过，`85 passed`；targeted ruff 和
  `pulse_runs_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root395 - Pulse agent eval/runtime 审计写入继续信任 RETURNING 行存在性

发现：

- `PulseAgentEvalRepository.upsert_agent_runtime_version(...)`、
  `insert_agent_eval_case(...)` 和 `upsert_agent_eval_result(...)` 都使用
  `RETURNING *` 后直接 `_row(row)`。
- 这些表记录 runtime manifest、eval case、eval result，是 Pulse agent 执行平面的评测/审计账本。
  旧代码没有验证 cursor rowcount 是否存在、是否合法、是否与返回行一致。
- 当 driver adapter 返回 malformed rowcount、或 rowcount 与返回行不一致时，旧实现仍可能返回 eval
  audit row，或者在 no row 场景退化成低层 `NoneType` 转换错误。

根因：

- 前面已经把 run/step、candidate、playbook、admission 的写入证据收紧，但 eval/runtime 审计表还保留了
  “结果集存在即成功”的旧写法。
- 成熟 Kappa/CQRS 的 agent execution plane 需要可解释、可回放的审计因果链。runtime/case/result
  audit rows 必须由 PostgreSQL DML 执行证据证明，而不是由返回行对象存在性证明。

修复：

- `PulseAgentEvalRepository` 新增 `_cursor_rowcount(...)` 和 `_required_returning_row(...)`。
- runtime-version、eval-case、eval-result 三条 required `RETURNING` 写路径都要求 rowcount=1 且有返回行。
- 架构守护禁止恢复 direct `_row(row)` 返回和 rowcount 默认兜底。

验证：

- RED：focused PulseAgentEval returning-rowcount 命令初始失败
  `28 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`29 passed`。
- Pulse agent eval/run/candidate/playbook/transaction 非集成组通过，`114 passed`；targeted ruff 和
  `pulse_agent_eval_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root396 - Pulse evidence packet upsert 在 run-link 前缺少 PostgreSQL 执行证据

发现：

- `PulseEvidenceRepository.upsert_packet(...)` 对 `pulse_evidence_packets` 执行
  `INSERT ... ON CONFLICT ... RETURNING evidence_packet_id` 后，旧实现只检查 `fetchone()` 是否为
  `None`。
- 随后它立刻更新 `pulse_agent_runs.evidence_packet_id` 和 `evidence_packet_hash`。也就是说，只要
  driver 返回了一个 row-like 对象，即使没有合法 `cursor.rowcount`，agent run audit 也可能被链接到
  这个 packet id/hash。
- 这条路径不是普通缓存写入。sealed evidence packet 是 Pulse agent 调用前的证据边界，
  `pulse_agent_runs` 是后续 replay、cost、eval、candidate 决策追溯的因果账本。

根因：

- 前序治理已经把 run/step、eval、candidate、playbook、admission 的 `RETURNING` 写入收紧到
  rowcount/row 一致，但 evidence packet 本体仍停留在“返回行存在即成功”的旧模式。
- 成熟 Kappa/CQRS 的 agent 链路要求证据包持久化和 run audit 链接是同一条可验证因果链：
  packet write 必须先由 PostgreSQL 证明“确实写入/更新了一行”，然后才允许 run 指向该 packet。
- 如果这里允许缺失、非法或 mismatched rowcount，后续 eval/candidate/playbook 即使都严格，也可能建立在
  一个未被数据库执行证据确认的 evidence boundary 上。

修复：

- `PulseEvidenceRepository` 新增 `_cursor_rowcount(...)` 和 `_required_returning_row(...)`。
- `upsert_packet(...)` 先保存 cursor，再 `fetchone()`，并要求 rowcount=1 且有返回行。
- 只有 packet upsert 通过验证后才更新 `pulse_agent_runs.evidence_packet_id/hash`。
- 架构守护禁止恢复 direct `.execute(...).fetchone()`、`if row is None` 和 rowcount 默认兜底。

验证：

- RED：focused PulseEvidence returning-rowcount 命令初始失败
  `10 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`11 passed`。
- Pulse evidence/eval/run/candidate/playbook/admission/transaction 非集成组通过，`140 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root397 - CEX profile source cache 的 RETURNING 写入仍用返回行存在性当执行证据

发现：

- `CexTokenProfileRepository.upsert_ready_profile_if_token_exists(...)` 对
  `cex_token_profiles` 执行 `INSERT ... SELECT FROM cex_tokens ... RETURNING *`。
- 旧实现直接 `.fetchone()`，然后 `return dict(row) if row else None`。
- 这个方法的语义有两个合法分支：如果没有 matching routed `cex_tokens`，应返回 `None`；如果存在，
  则刷新一条 Binance CEX profile source-cache row。但旧实现没有要求 PostgreSQL `cursor.rowcount`
  证明这两个分支。

根因：

- Root76 已经修掉了 CEX source-cache repository 的裸 commit/缺 transaction 问题，但只治理了事务边界，
  没治理 DML 执行证据。
- `cex_token_profiles` 虽然不是 public serving row，却是 `TokenProfileCurrentWorker` exact-load 的持久
  source cache；它会影响 public token profile/icon 选择。
- 成熟 Kappa/CQRS 对 source cache 的要求不是“只要在事务里写就行”，还要区分“没有可写目标”
  和“确实刷新了一条 source-cache row”。这个区分必须来自 PostgreSQL rowcount，而不是 driver
  返回行是否 truthy。

修复：

- `CexTokenProfileRepository` 新增 `_cursor_rowcount(...)` 和 `_optional_returning_row(...)`。
- `upsert_ready_profile_if_token_exists(...)` 现在先保存 cursor、fetch row，再验证 rowcount 为合法
  0/1 且与返回行存在性一致。
- rowcount=0/no row 是唯一合法 no-existing-token 结果；rowcount=1/row 是唯一合法刷新结果；
  缺失、bool、负数、字符串、多行或 rowcount/row mismatch 都失败。
- 架构守护禁止恢复 direct `.execute(...).fetchone()`、`dict(row) if row else None` 和 rowcount 默认兜底。

验证：

- RED：focused CEX token profile returning-rowcount 命令初始失败
  `9 failed, 4 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`13 passed`。
- CEX profile sync / Asset Market sync / Token Profile Current source-query 非集成组通过，`34 passed`。
- targeted ruff 和 `cex_token_profile_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root398 - append-only market tick fact 写入把 RETURNING tick_id 当成创建/冲突证据

发现：

- `MarketTickRepository._insert_tick_returning_id(...)` 对 `market_ticks`
  执行 `INSERT ... ON CONFLICT ... DO NOTHING RETURNING tick_id` 后，旧实现直接
  `.fetchone()`。
- 这条写入的合法语义只有两个：rowcount=1 且有 `tick_id` 表示新市场 tick fact
  已插入；rowcount=0 且无返回行表示同一个 provider/target/observed_at tick 已经存在。
- 旧实现没有验证 cursor rowcount，因此缺失、bool、负数、多行、字符串 rowcount，或
  rowcount/RETURNING 行不一致，都可能被误判为 inserted id 或 dedupe conflict。

根因：

- 前面已经把 `market_tick_current` projection、dirty target、capture tier 等读模型/控制面写入收紧，
  但 append-only fact table 本身仍保留了“返回行存在性就是执行证据”的旧写法。
- 在成熟 Kappa/CQRS 里，事实表比读模型更靠近真相边界。`market_ticks` 是 Token Radar、Pulse
  evidence、Token Case/Search Inspect market-live、LivePriceGateway fan-out 的市场事实来源；
  如果事实写入分类不可信，后续 current projection 即使严格，也会继承错误的 created/duplicate
  诊断。
- PostgreSQL `RETURNING` 行是结果载体，不是单独的执行证明。创建/冲突分类必须由 rowcount 与
  returned-row presence 一起证明。

修复：

- `MarketTickRepository` 新增 `_cursor_rowcount(...)` 和 `_optional_returning_id(...)`。
- `_insert_tick_returning_id(...)` 现在保存 cursor、fetch row，并要求 rowcount 为合法 0/1 且与
  返回行存在性一致。
- rowcount=1/row 才返回 inserted `tick_id`；rowcount=0/no row 才返回 `None` 表示 dedupe；
  缺失、bool、负数、字符串、多行或 mismatch 都失败。
- 架构守护禁止恢复 direct `.execute(...).fetchone()`、`if row is None` 分支和 rowcount 默认兜底。

验证：

- RED：focused MarketTickRepository returning-rowcount 命令初始失败
  `9 failed, 11 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`20 passed`。
- 更宽的 Asset Market market-tick 非集成验证、targeted static、SDD/static hygiene 继续记录在 SDD
  verification 中；按当前用户指令，本轮不运行 integration-heavy gate。

### Root399 - notification delivery requeue/claim 把 RETURNING 行当成队列状态机证据

发现：

- `NotificationRepository.enqueue_or_requeue_delivery(...)` 对 `notification_deliveries`
  执行 `INSERT ... ON CONFLICT ... DO UPDATE ... WHERE status IN ('failed', 'dead') RETURNING *`
  后，旧实现直接 `fetchone()` 并 `return dict(row) if row is not None else None`。
- `NotificationRepository.claim_next_delivery(...)` 对 pending/failed/stale running delivery 执行
  `UPDATE ... RETURNING delivery.*` 后，同样直接把返回行存在性当成 claimed/no-delivery 结论。
- 这两条路径的合法语义都是 0/1 行：rowcount=0 且无返回行表示没有 requeue/claim work；
  rowcount=1 且有返回行表示刚刚 reactivated 或 claimed 一条 delivery。旧实现没有验证这个
  PostgreSQL 执行证据。

根因：

- Root349/Root367 已经把 notification insert/read-marker 的 rowcount 证据收紧，Root390 也删除了
  app-runtime generic queue executor；但通知投递控制面仍留下了“RETURNING 行存在即状态机成功”的旧模式。
- `notification_deliveries` 不是产品事实，而是 side-effect/control ledger。成熟 Kappa/CQRS 会把它和
  `notifications` fact 分开治理：它不能决定业务真相，但它必须严格决定外部推送是否被重试、认领、
  失败或完成。
- 如果 requeue/claim 可以在缺失、非法、多行或 rowcount/row mismatch 时继续返回 delivery row，
  worker 会把 malformed driver/wiring state 当成真实队列状态，进而唤醒或执行外部 IO。

修复：

- `NotificationRepository` 新增 `_optional_returning_row(...)`，复用 `_single_row_write_count(...)`
  的非 bool、非负 int、0/1 检查。
- `enqueue_or_requeue_delivery(...)` 和 `claim_next_delivery(...)` 现在先保存 cursor，再 fetch row，
  并要求 rowcount 与 returned-row presence 一致。
- rowcount=0/no row 才返回 `None`；rowcount=1/row 才返回 delivery dict；缺失、bool、负数、字符串、
  多行或 mismatch 都失败。
- 架构守护禁止恢复 `return dict(row) if row is not None else None`、rowcount 默认兜底或 optional
  returned-row-only 分类。

验证：

- RED：focused notification delivery returning-rowcount 命令初始失败
  `13 failed, 12 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`25 passed`。
- Notification rules/runtime/architecture 非集成组通过，`148 passed`。
- targeted ruff 和 `notification_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

剩余观察：

- 这次修的是 SQL 执行证据边界，不是 delivery lease 协议本身。当前 `complete_delivery(...)` /
  `fail_delivery(...)` 仍主要按 `delivery_id` 写终态；如果未来允许多 worker 或更激进的 stale-running
  reclaim，建议单独设计 persisted lease/attempt token 或 CAS 条件，避免旧 worker 在超时重领后写入终态。

### Root400 - Macro sync-window enqueue/claim 把 RETURNING 行当成 provider work 启动证据

发现：

- `MacroIntelRepository.enqueue_macro_sync_window(...)` 对 `macro_sync_windows` 执行
  `INSERT ... ON CONFLICT ... RETURNING sync_window_id` 后，旧实现直接 `.fetchone()` 并
  `str(dict(row or {})["sync_window_id"])`。
- `claim_macro_sync_window(...)` 和 `claim_macro_sync_window_by_id(...)` 对
  `macro_sync_windows` 执行 `UPDATE ... RETURNING sync_window.*` 后，旧实现直接
  `return dict(row) if row is not None else None`。
- 这三条路径都在 Macro fact-ingest 控制面上：enqueue 应该是 rowcount=1 且有 id；
  claim/no-work 应该只有 rowcount=0/no row 或 rowcount=1/window row 两种合法状态。

根因：

- Root361 已经治理了 Macro terminal/retry/failure、sync-state repair、projection dirty/current row
  的 rowcount 证据；Root383 也治理了 `macro_view_snapshots` / `macro_daily_briefs`
  current-row `RETURNING true AS changed`。但最早决定 provider work 是否启动的
  `macro_sync_windows` enqueue/claim 仍保留 returned-row-only 分类。
- 成熟 Kappa/CQRS 中，`macro_sync_windows` 不是产品事实，但它是 fact ingest 的控制面。它一旦误报
  “已 claim”，`MacroSyncWorker` 就会在 DB transaction 外启动 packaged macrodata provider IO。
- 因此这里的 SQL 证据边界不是小的 mapper 健壮性问题，而是“是否允许外部源读取开始”的状态机门。
  返回行只是载体；必须由 PostgreSQL rowcount 与 row presence 一起证明。

修复：

- `MacroIntelRepository` 新增 `_optional_returning_row(...)` 和 `_required_returning_row(...)`。
- `enqueue_macro_sync_window(...)` 现在要求 rowcount=1 且有返回行，才返回 `sync_window_id`。
- `claim_macro_sync_window(...)` / `claim_macro_sync_window_by_id(...)` 现在只接受 rowcount=0/no row
  作为 no-work，rowcount=1/row 作为 claimed window；缺失、bool、负数、字符串、多行或 mismatch 都失败。
- 架构守护禁止恢复 `dict(row or {})`、`return dict(row) if row is not None else None` 和 rowcount 默认兜底。

验证：

- RED：focused Macro sync-window returning-rowcount 命令初始失败
  `25 failed, 2 passed`，证明旧实现不检查缺失/非法/mismatched rowcount。
- GREEN：同一 focused 命令通过，`27 passed`。
- Macro sync/repository/projection architecture 非集成组通过，`228 passed`。
- targeted ruff 和 `macro_intel_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root401 - News page-row upsert 用 RETURNING 行存在性分类 inserted/updated/unchanged

发现：

- `NewsRepository.replace_page_rows_for_items(...)` 写公共 News page read model
  `news_page_rows`，SQL 使用
  `INSERT ... ON CONFLICT ... WHERE payload_hash IS DISTINCT FROM ... RETURNING (xmax = 0) AS inserted`。
- 旧逻辑直接用 returned row 是否存在来分类：`None` 算 unchanged，有 row 且
  `inserted=true` 算 inserted，否则 updated。
- 这条路径虽然不是 provider fact ingest，但它是 `/api/news`、News item detail 和 high-signal
  notification candidates 的公共 read model 写入边界。

根因：

- Root320/321/322 已经把 `news_page_rows` 的 payload 和读路径收紧成 formal projected-row
  contract；Root352/384 也收紧了 NewsRepository changed-row/delete-returning rowcount。
  但 page-row upsert 的核心 changed/unchanged 分类仍停在 returned-row-only。
- 成熟 CQRS 投影要求“未变化投影写零 serving rows”可由数据库执行证据证明。这里 `WHERE
  news_page_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash` 的正确语义是：
  payload 不变时 PostgreSQL rowcount=0/no row；payload 改变或新行插入时 rowcount=1/row。
- 如果 fake cursor、driver adapter 或异常 DB wrapper 返回 row 但没有合法 rowcount，旧代码会把 malformed
  证据升级为 inserted/updated，从而污染 projection write counts，也破坏“unchanged 写零行”的可审计性。

修复：

- `NewsRepository` 新增 `_optional_returning_row(...)`，复用 `_cursor_rowcount(...)` 的
  `news_repository_rowcount_required` / `news_repository_rowcount_invalid` 错误语义。
- `replace_page_rows_for_items(...)` 现在保存 cursor，`fetchone()` 后要求 rowcount 为合法 0/1，
  且与 returned-row presence 一致。
- rowcount=0/no row 才计入 `unchanged`；rowcount=1/row 才继续通过 `(xmax = 0)` 区分
  inserted vs updated；缺失、bool、负数、字符串、多行或 mismatch 都失败。
- 架构守护禁止恢复 `if returned is None:` / `elif bool(returned["inserted"])` 这种直接 returned-row
  分类，以及 rowcount 默认兜底。

验证：

- RED：focused News page-row returning-rowcount 命令初始失败
  `9 failed, 2 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  命中缺失的 `_optional_returning_row` 合同。
- GREEN：同一 focused 命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root402 - News source claim 用 RETURNING 返回行推断已领取 source

发现：

- `NewsRepository.claim_due_sources(...)` 是 `NewsFetchWorker` 启动 provider fetch
  的控制面入口：它在 `news_sources` 中选择 due source，执行
  `UPDATE news_sources ... RETURNING sources.*`，然后把 returned rows 返回给 worker。
- 旧实现把 `self.conn.execute(...).fetchall()` 的返回行直接转换为 source rows，没有检查
  cursor rowcount。
- 因此 fake cursor、driver adapter 或异常 DB wrapper 即使缺少 rowcount、返回 bool/负数/字符串
  rowcount，或 rowcount 与 returned rows 数量不一致，也会被解释成“成功领取了这些 source”。

根因：

- Source claim 不只是一个查询，它是 News fetch provider IO 的租约边界。成熟的 Kappa/CQRS
  worker 设计要求“是否领取了工作”由数据库执行结果证明，而不是由 Python 返回对象的存在性证明。
- `FOR UPDATE SKIP LOCKED` + `UPDATE ... RETURNING sources.*` 的正确语义是：
  rowcount=0/空返回表示没有 due work；rowcount=N 且返回 N 行才表示领取了 N 个 source。
  缺失、非法或 mismatch rowcount 是 repository/driver 状态损坏，不能降级为正常空队列或正常 claim。
- 之前 Root177 已经把 source-claim lease 放回 formal worker settings，Root374 已经收紧 source-disable
  returning rowcount，但 claim 本身仍停在 returned-list-only，导致同一张 `news_sources`
  表的“禁用”和“领取”执行证据不一致。

修复：

- `NewsRepository.claim_due_sources(...)` 现在保存 `UPDATE news_sources ... RETURNING sources.*`
  cursor，`fetchall()` 后调用既有 `_returned_rowcount(cursor, rows)`。
- `_returned_rowcount(...)` 复用 `_cursor_rowcount(...)`，缺失 rowcount 报
  `news_repository_rowcount_required`，bool、负数、非整数或与 returned rows 数量不一致时报
  `news_repository_rowcount_invalid`。
- 架构守护禁止恢复 `).fetchall()` 链式写法、`return len(rows)` / `claimed_count = len(rows)` 和
  rowcount 默认兜底。

验证：

- RED：focused News source-claim RETURNING rowcount 命令初始失败
  `9 failed, 2 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，architecture guard
  命中链式 `.fetchall()`。
- GREEN：同一 focused 命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root403 - News fetch-run finalization 用 RETURNING row 推进 source 状态

发现：

- `NewsRepository.finish_fetch_run(...)` 是 `NewsFetchWorker` 每个 provider fetch run 的收口边界：
  它先更新 `news_fetch_runs`，再按 success/failure 更新 `news_sources` 的成功时间、失败次数和下一次
  fetch 时间，最后把 finalized run row 返回给调用方。
- 旧实现直接执行 `UPDATE news_fetch_runs ... RETURNING *` 后链式 `.fetchone()`，没有检查
  cursor rowcount，也没有在更新 `news_sources` 前证明 fetch-run row 真的被唯一更新。
- 如果 cursor 缺失 rowcount、rowcount 为 bool/字符串/负数/0/2，或者 rowcount 与返回 row 不一致，
  旧路径仍可能继续推进 `news_sources` 状态；无返回 row 时还会在 source 已更新后才以
  `dict(None)` 形式暴露粗糙异常。

根因：

- Fetch run 是控制面审计 ledger，`news_sources` 是后续 due-source claim 的调度状态。成熟
  Kappa/CQRS 里，调度状态推进必须建立在 PostgreSQL 执行证据上，而不是建立在 Python
  returned-row 对象的存在性或后续异常上。
- `UPDATE news_fetch_runs ... RETURNING *` 的正确语义是 required single-row：rowcount=1 且有
  returned run row 才能说明这个 fetch run 被 finalized；其他组合都是 repository/driver 损坏或
  stale run id，不应继续更新 source success/failure state。
- 这个缺口和 Root402 是同一类问题：source claim 已经要求 rowcount 匹配 returned rows，但 fetch
  run finalize 仍允许 returned-row-only 成功路径，导致同一条 `news_fetch` 控制链的入口和出口证据不一致。

修复：

- `NewsRepository.finish_fetch_run(...)` 现在保存 `UPDATE news_fetch_runs ... RETURNING *` cursor，
  `fetchone()` 后立即调用 `_required_returning_row(cursor, row)`。
- `_required_returning_row(...)` 复用 `_optional_returning_row(...)` 的 rowcount/row 一致性校验，
  并要求必须返回一行；rowcount=0/no row、缺失 rowcount、非法 rowcount 或 mismatch 都失败。
- 只有 fetch-run row 通过 required single-row 校验后，代码才会更新 `news_sources` success/failure
  状态并返回 finalized run row。
- 架构守护禁止恢复链式 `).fetchone()`、`return dict(row)`、`if row is None:` 和 rowcount 默认兜底。

验证：

- RED：focused News fetch-run finalize RETURNING rowcount 命令初始失败
  `11 failed, 1 passed`，证明旧实现不检查缺失/非法/mismatched rowcount，并且 missing row 会在 source
  update 之后才触发原始 `TypeError`。
- GREEN：同一 focused 命令通过，`12 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root404 - News fetch-run start 不验证 ledger insert/source touch rowcount

发现：

- `NewsRepository.start_fetch_run(...)` 是 `NewsFetchWorker` 每个 source provider IO 前的启动边界：
  它创建 `news_fetch_runs` running ledger row，随后更新 `news_sources.last_fetch_at_ms`，最后把 run id
  返回给 worker。
- 旧实现对 `INSERT INTO news_fetch_runs` 和后续 `UPDATE news_sources` 都没有读取 cursor rowcount。
- 因此 fake cursor、driver adapter 或异常 DB wrapper 即使缺失 rowcount、返回 bool/负数/字符串/0/2，
  也会被解释成“fetch run 已启动”，并可能推进 source 的 last-fetch 调度字段。

根因：

- Fetch-run start 和 finish 是同一个控制面生命周期的两端。Root403 已经要求 finish 先证明
  `news_fetch_runs` finalize row 再更新 source 状态；start 也必须先证明 running ledger row 已写入，
  再触碰 source 调度状态。
- 成熟 Kappa/CQRS worker 里，run ledger 是审计与重放边界，source row 是调度边界。二者必须在同一
  PostgreSQL 事务里按顺序用执行证据推进；不能把“SQL 被调用了”当成“数据库改变了恰好一行”。
- 这个问题不是性能瓶颈本身，但会破坏性能和可靠性诊断：source 看起来刚 fetch 过，run ledger 却可能
  没有可靠启动证据，后续 source-quality、worker status 和人工排障都会读到分裂状态。

修复：

- `NewsRepository.start_fetch_run(...)` 现在分别保存 `INSERT INTO news_fetch_runs` 和
  `UPDATE news_sources` 的 cursor。
- 新增 `_required_rowcount(cursor, expected=1)`，复用 `_cursor_rowcount(...)` 的
  `news_repository_rowcount_required` / `news_repository_rowcount_invalid` 语义。
- 插入 running fetch-run row 必须 rowcount=1，否则不会更新 `news_sources`；source update 也必须
  rowcount=1，否则不会返回 run id。
- 架构守护禁止恢复裸 `self.conn.execute(...)` 写法和 rowcount 默认兜底。

验证：

- RED：focused News fetch-run start rowcount 命令初始失败
  `17 failed, 1 passed`，证明旧实现不检查 insert/source update rowcount，并且 architecture guard
  命中缺失的 `_required_rowcount` 合同。
- GREEN：同一 focused 命令通过，`18 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root405 - News configured-source upsert 用 RETURNING row 当执行证据

发现：

- `NewsRepository.upsert_source(...)` 是 `NewsFetchWorker` reconcile `settings.news_intel.sources`
  到 `news_sources` 的控制面入口。它先读 existing source 判断 inserted/updated/duplicate，再对 inserted/updated
  路径执行 `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *`。
- 旧实现直接链式 `self.conn.execute(...).fetchone()`，随后 `return {**dict(row), "status": status}`。
- 因此缺失 cursor rowcount、非法 rowcount、rowcount/returned-row mismatch 都会被忽略；如果没有返回 row，
  还会退化成 Python 的 `NoneType` 异常，而不是明确的 repository rowcount 合同错误。

根因：

- Source reconcile 是 News Kappa 入口的“配置事实进入控制面”步骤。`news_sources` 不是 UI 缓存，而是后续
  due-source claim、fetch-run ledger、source-quality projection 和 provider-contract 诊断共同读取的调度事实。
- 成熟 Kappa/CQRS 架构里，配置源 upsert 需要证明数据库恰好接受了一行 source control-plane state，
  然后 worker 才能把它当成可 claim、可 fetch、可诊断的事实。仅有 returned row presence 不足以区分
  “PostgreSQL 写入一行”与“driver/adapter 返回了不完整或不可信结果”。
- Root402/403/404 已经把 claim、finish、start 收进 rowcount 证据链；如果 reconcile 仍信任 `RETURNING`
  行存在性，News fetch 生命周期的第一个入口仍保留一处兼容性裂缝。

修复：

- `NewsRepository.upsert_source(...)` 现在保存 `INSERT INTO news_sources ... RETURNING *` cursor，
  `fetchone()` 后调用 `_required_returning_row(cursor, row)`。
- `_required_returning_row(...)` 要求 rowcount=1 且必须有一行；缺失 rowcount、非法 rowcount、
  rowcount/row mismatch 或 no-row 都以 `news_repository_rowcount_required/invalid` 暴露。
- duplicate 路径仍然只返回已读 existing row，不执行写入；inserted/updated 路径才需要 required single-row
  PostgreSQL 证据。
- 架构守护禁止在 write 段恢复链式 `).fetchone()`、`dict(row)` 和 rowcount 默认兜底。

验证：

- RED：focused News source upsert RETURNING rowcount 命令初始失败 `10 failed, 1 passed`，证明旧实现不检查
  missing/invalid/mismatched rowcount，且 missing row 产生原始 `NoneType` 异常。
- GREEN：同一 focused 命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root406 - News provider-item upsert 用 RETURNING row 当 provider fact 执行证据

发现：

- `NewsRepository.upsert_provider_item(...)` 是 `NewsFetchWorker` 把 provider raw input 写入
  `news_provider_items` 的事实入口。它先读取 source/provider type，再查找现有 provider item，最后在
  inserted/updated 路径执行 `INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *`。
- 旧实现直接链式 `self.conn.execute(...).fetchone()`，随后
  `return {**dict(row), "status": status, "incoming_provider_payload_status": incoming_provider_payload_status}`。
- 因此 missing rowcount、非法 rowcount、rowcount/returned-row mismatch 都会被忽略；如果 PostgreSQL 没有返回 row，
  还会落成原始 `NoneType` 错误，而不是统一的 repository rowcount 合同错误。

根因：

- Kappa/CQRS 的边界不是“provider 返回了一条 payload”，而是“PostgreSQL 持久化了一条可重放、可去重、可审计的
  observation fact”。`news_provider_items` 是 `news_items` canonical merge、story/duplicate evidence、page dirty
  和 fetch-run accounting 的前置事实，不是临时缓存。
- 成熟 Kappa 设计里，provider raw frame 只是输入；事实入口必须证明数据库恰好接受了一行 provider observation。
  仅信任 returned row 会把 driver/adapter 的异常结果误当作事实写入成功，让 fetch accounting 和后续投影基于不可信证据前进。
- Root402-405 已经把 source claim、fetch-run start/finalize 和 source reconcile 纳入 rowcount 证据链；如果 provider-item
  upsert 仍然只信任 returned row，News fetch 生命周期会在最关键的 raw-input -> persisted-fact 边界留下同类兼容性代码。

修复：

- `NewsRepository.upsert_provider_item(...)` 现在保存 `INSERT INTO news_provider_items ... RETURNING *` cursor，
  `fetchone()` 后调用 `_required_returning_row(cursor, row)`。
- `_required_returning_row(...)` 要求 rowcount=1 且必须有一行；缺失 rowcount、非法 rowcount、rowcount/row mismatch
  或 no-row 都以 `news_repository_rowcount_required/invalid` 暴露。
- duplicate/no-material-change 路径仍然返回已读 existing row；inserted/updated 路径必须有 required single-row PostgreSQL 证据。
- 架构守护禁止在 provider-item write 段恢复链式 `).fetchone()`、`dict(row)` 返回和 rowcount 默认兜底。

验证：

- RED：focused News provider-item upsert RETURNING rowcount 单元命令初始失败 `9 failed, 1 passed`，证明旧实现不检查
  missing/invalid/mismatched rowcount，且 missing row 产生原始 `NoneType` 异常；对应 architecture guard 也初始失败，命中
  `).fetchone()` 和 `dict(row)` 旧写法。
- GREEN：focused provider-item 单元命令通过，`10 passed`；对应 architecture guard 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root407 - News canonical item upsert 用 RETURNING row 当 canonical fact 执行证据

发现：

- `NewsRepository.upsert_canonical_news_item(...)` 是 `NewsFetchWorker` 把 `news_provider_items`
  observation 归并成 canonical `news_items` 的核心事实入口。它在拿到 provider observation、canonical identity、
  representative 判断和 edge 状态之后，执行
  `INSERT INTO news_items ... ON CONFLICT (canonical_item_key) ... RETURNING *`。
- 旧实现直接链式 `self.conn.execute(...).fetchone()`，随后从 `row["news_item_id"]` 构造
  `news_item_observation_edges`、provider-article/material duplicate remap、summary refresh 和 affected item set。
- 因此 missing rowcount、非法 rowcount、rowcount/returned-row mismatch 都会被忽略；如果没有 returned row，
  会在 edge payload 构造处落成原始 `NoneType` 下标错误，而不是 repository rowcount 合同错误。

根因：

- `news_items` 是 News Kappa 链路里从 provider observation 进入产品事实的 canonical merge 点。后续 story identity、
  item processing、agent admission、page projection 和 dirty target 都从这个 canonical item/edge 集合继续前进。
- 成熟 Kappa/CQRS 架构里，canonical merge 不是“Python 拿到一个 row object”就完成，而是数据库必须证明
  `news_items` 恰好插入或更新了一行，之后 observation edge 和 remap cleanup 才能使用 canonical `news_item_id`。
- Root406 已经把 raw input -> provider observation 的事实入口收进 rowcount 证据链；如果 canonical item upsert 仍然只信任
  returned row，那么 provider fact -> product fact 的下一跳仍会让 fetch accounting、edge 写入和 dirty-set 判断基于不可信证据前进。

修复：

- `NewsRepository.upsert_canonical_news_item(...)` 现在保存 `INSERT INTO news_items ... RETURNING *` cursor，
  `fetchone()` 后调用 `_required_returning_row(cursor, row)`。
- edge payload、provider-article remap、material duplicate remap 和 observation summary refresh 都使用
  `returned_row["news_item_id"]`，确保这些后续写入只发生在 PostgreSQL 已证明 canonical row 存在之后。
- `_required_returning_row(...)` 要求 rowcount=1 且必须有一行；缺失 rowcount、非法 rowcount、rowcount/row mismatch
  或 no-row 都以 `news_repository_rowcount_required/invalid` 暴露。
- 架构守护禁止在 `news_items` write 段恢复链式 `).fetchone()` 或 rowcount 默认兜底。

验证：

- RED：focused News canonical item upsert RETURNING rowcount 单元命令初始失败 `9 failed, 1 passed`，证明旧实现不检查
  missing/invalid/mismatched rowcount，且 missing row 在 edge payload 构造处产生原始 `NoneType` 错误；对应 architecture
  guard 也初始失败，命中链式 `).fetchone()`。
- GREEN：focused canonical item 单元+架构命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root408 - News observation edge upsert 缺少 rowcount 执行证据

发现：

- `NewsRepository.upsert_canonical_news_item(...)` 在 canonical `news_items` 已经返回后，会写入
  `news_item_observation_edges`，把 provider observation 规范连接到 canonical item。
- 旧实现直接执行 `INSERT INTO news_item_observation_edges ... ON CONFLICT (provider_item_id) DO UPDATE`
  而不检查 cursor rowcount。只要 canonical item returned row 存在，后续 provider-article remap、material duplicate
  remap、summary refresh 和 affected item accounting 都会继续。
- 因此缺失 rowcount、非法 rowcount、rowcount=0 或多行异常都无法阻断链路；系统会把“canonical item 存在”误当成
  “provider observation 已经被 PostgreSQL 成功连接到 canonical item”。

根因：

- Root407 只证明了 canonical product fact 行存在，但 observation edge 是另一条事实边。成熟 Kappa/CQRS 里，事实节点和事实边都必须有独立的数据库执行证据。
- `news_item_observation_edges` 是后续 duplicate lookup、provider-native article remap、summary refresh 和 dirty-set accounting 的规范 SQL 连接面；如果这个 edge 写入没有 rowcount 证据，后续读模型和处理 worker 看到的是可能缺边或错边的事实图。
- 这不是单纯的异常处理问题，而是事实图完整性边界缺失：provider raw input -> provider observation -> canonical item -> observation edge 的每一跳都需要 PostgreSQL 证明，不能用上一跳成功替代下一跳成功。

修复：

- `upsert_canonical_news_item(...)` 现在保存 observation-edge `INSERT ... ON CONFLICT` cursor，并在 provider-article remap、material duplicate remap、summary refresh 和 affected item accounting 之前调用 `_required_rowcount(cursor, expected=1)`。
- `_required_rowcount(...)` 通过统一 `_cursor_rowcount(...)` 拒绝缺失、布尔、负数、非整数和非预期 rowcount。
- 单元测试覆盖 missing/invalid/zero/multi-row edge rowcount；architecture guard 禁止恢复裸 `self.conn.execute(...)`、`getattr(cursor, "rowcount", 0)` 或 `cursor.rowcount or 0` 兼容兜底。

验证：

- RED：focused observation-edge rowcount 单元命令初始失败 `8 failed, 2 passed`，证明旧实现完全忽略 edge cursor rowcount；对应 architecture guard 也初始失败，命中裸 `self.conn.execute(...)`。
- GREEN：focused observation-edge 单元+架构命令通过，`10 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root409 - News observation summary refresh 用 fallback SELECT 掩盖 RETURNING 证据缺失

发现：

- `NewsRepository._refresh_news_item_observation_summary(...)` 在 observation edge 写入、provider-article remap 和 material duplicate
  remap 后，用 `UPDATE news_items ... RETURNING items.*` 把 edge summary 聚合回 canonical `news_items`。
- 旧实现直接链式 `self.conn.execute(...).fetchone()`，如果没有返回 row，就执行
  `SELECT * FROM news_items WHERE news_item_id = %s` fallback，并返回该旧 item row 或 `{}`。
- 因此 missing rowcount、非法 rowcount、rowcount/returned-row mismatch、甚至 required summary refresh 没有返回当前 item row，
  都可能被 fallback SELECT 掩盖。后续 affected-item accounting 会继续使用一个未被证明“已按 edge summary 刷新”的 item row。

根因：

- Root408 证明的是 observation edge 被写入；但 Kappa/CQRS 链路里，edge 写入后还要把 source/provider-article 聚合投回
  canonical item fact，供 fetch affected set、item processing、page projection 和 read model dirty work判断。
- 成熟 PostgreSQL/CQRS 写路径不能用读回旧 row 代替写入证明。`UPDATE ... RETURNING` 的语义是“这次 refresh 写到了哪一行”；fallback
  `SELECT` 的语义只是“这个 item 现在存在”，二者不能互换。
- 对旧 item 的 zero-edge cleanup，rowcount=0/no row 可以是显式 cleanup 状态；但它也必须由 cursor rowcount 证明，而不能由
  fallback SELECT 修补成看似可继续的 summary row。

修复：

- `_refresh_news_item_observation_summary(...)` 现在捕获 `UPDATE news_items ... RETURNING items.*` cursor，`fetchone()` 后根据
  `required` 参数调用 `_required_returning_row(cursor, row)` 或 `_optional_returning_row(cursor, row)`。
- 当前 canonical item refresh 默认 `required=True`，必须 rowcount=1 且返回当前 item row；old zero-edge cleanup 显式传
  `required=False`，允许 rowcount=0/no row 返回 `{}`，但不再 fallback SELECT。
- 架构守护禁止恢复链式 `).fetchone()`、fallback `SELECT * FROM news_items WHERE news_item_id`、`return dict(fallback)` 或
  rowcount 默认兜底。

验证：

- RED：focused observation-summary rowcount 命令初始失败 `11 failed, 1 passed`，证明旧实现忽略 missing/invalid/mismatched
  rowcount，且 required no-row refresh 会被 fallback SELECT 掩盖；architecture guard 同时命中链式 `).fetchone()` 和 fallback SELECT。
- GREEN：focused observation-summary 单元+架构命令通过，`12 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root410 - News edge-remap RETURNING rows 缺少 rowcount 证据

发现：

- `NewsRepository._remap_provider_article_edges_to_news_item(...)` 和
  `_remap_material_duplicate_edges_to_news_item(...)` 会通过 CTE 更新 `news_item_observation_edges`，并用
  `RETURNING remapped.old_news_item_id` / `SELECT DISTINCT old_news_item_id` 生成需要 cleanup 的旧 canonical item 集合。
- 旧实现直接链式 `self.conn.execute(...).fetchall()`，随后返回 old item id 列表。
- 因此 missing rowcount、非法 rowcount、rowcount/returned-row mismatch 都不会阻断链路；后续 old-item summary cleanup、
  dirty-target remap、zero-edge delete 和 affected-item accounting 会继续使用未被 PostgreSQL rowcount 证明的旧 item id 集合。

根因：

- Root408 证明了新 observation edge 被写入，Root409 证明了 canonical item summary refresh；但 provider-article/material duplicate
  remap 是同一事实图的“旧边迁移”步骤，不是普通查询。
- 成熟 Kappa/CQRS 里，边迁移返回的旧 item id 集合会驱动后续写操作和 dirty fan-out，因此它本身也是写路径执行证据的一部分。
  只信任 returned rows 会把 driver/adapter 的异常返回误当作“旧边迁移成功且这些旧 item 需要清理”。
- 这会让 affected-item accounting 在事实图迁移未被证明时继续推进，最终让 `news_fetch` 报告的 dirty targets 和后续 page projection
  依赖不完整的 canonical merge 证据。

修复：

- 两个 edge-remap helper 现在都保存 cursor，`fetchall()` 后调用 `_returned_rowcount(cursor, rows)`。
- 只有 cursor rowcount 与 returned old item-id rows 匹配时，才把 old item ids 返回给 old-item summary cleanup、dirty-target remap 和
  affected-item accounting。
- 架构守护禁止恢复链式 `).fetchall()`、rowcount 默认兜底或直接返回 old item-id comprehension。

验证：

- RED：focused edge-remap rowcount 命令初始失败 `17 failed, 2 passed`，证明 provider-article/material duplicate remap 都忽略
  missing/invalid/mismatched cursor rowcount；architecture guard 同时命中链式 `.fetchall()` 和直接返回 old item-id 列表。
- GREEN：focused edge-remap 单元+架构命令通过，`19 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root411 - News agent run/current brief RETURNING rows 缺少 rowcount 证据

发现：

- `NewsRepository.insert_news_item_agent_run(...)` 写入 append-only `news_item_agent_runs` ledger 时，旧实现直接
  `self.conn.execute(... RETURNING * ...).fetchone()` 后 `return dict(row)`。
- `NewsRepository.upsert_news_item_agent_brief(...)` 写入 current item-scoped `news_item_agent_briefs` read model 时也使用同样的
  chained `fetchone()` / `dict(row)` 路径。
- 因此 missing rowcount、布尔/字符串/负数/零/多行 rowcount、rowcount 与返回行不匹配，都会被忽略；如果没有返回行，只会暴露成
  原始 `NoneType` 错误，而不是 News repository 的统一 PostgreSQL 证据错误。

根因：

- `news_item_agent_runs` 不是普通审计日志附属品，它是 `NewsItemBriefWorker` 对 LLM 执行、prompt/schema/validator/hash/usage 的
  append-only audit ledger。`news_item_agent_briefs` 则是当前 item brief read model，后续 page projection、high-signal notification
  和外部推送 eligibility 都依赖它。
- 成熟 Kappa/CQRS 架构里，agent 执行结果从“模型响应”进入“可服务 current brief”之间必须有数据库确认点。只相信 returned row
  等于把驱动返回对象当成事实提交证明，破坏了事实链路：模型可能执行了，Python 也可能拿到一个 row-like 对象，但 PostgreSQL
  没被证明恰好写入了一行。
- 这会让 `NewsItemBriefWorker` 在 audit/current write 证据不完整时继续 dirty page rows 或报告 publishable state，最终把
  agent 运行审计、当前 brief、页面投影和通知候选串成一个不可重放的“看似成功”状态。

修复：

- `insert_news_item_agent_run(...)` 现在保存 cursor，`fetchone()` 后调用 `_required_returning_row(cursor, row)`。
- `upsert_news_item_agent_brief(...)` 同样保存 cursor 并使用 `_required_returning_row(cursor, row)`，要求 rowcount=1 且必须返回一行。
- 单元测试覆盖缺失 rowcount、非法/不匹配 rowcount、缺失 required row 和正常 rowcount=1；架构守护禁止恢复 chained
  `.fetchone()`、`return dict(row)` 或 rowcount 默认兜底。

验证：

- RED：focused News agent run/current brief rowcount 命令初始失败 `18 failed, 2 passed`，证明旧实现忽略 missing/invalid/mismatched
  rowcount，且 no-row required 写入暴露为原始 `NoneType`。
- GREEN：focused agent run/current brief 单元+架构命令通过，`20 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root412 - News old-item representative reselection RETURNING row 缺少 rowcount 证据

发现：

- `_reselect_news_item_representative_from_edges(...)` 在 canonical edge remap cleanup 中处理“旧 item 仍有 observation edges”的分支。
- 它通过 `WITH representative_edge AS (...) UPDATE news_items AS items ... RETURNING items.*` 从剩余 edges 中重选代表 provider/source/payload。
- 旧实现直接链式 `self.conn.execute(...).fetchone()`，然后 `return dict(row) if row is not None else {}`。
- 因此 missing rowcount、非法 rowcount、rowcount/row mismatch，甚至 rowcount=1 但没有 returned row，都不会以 News repository 的 PostgreSQL
  证据错误失败；后续仍可能清理 item-scoped derived facts 或继续 affected-item accounting。

根因：

- Root409 证明了 observation summary aggregate refresh，Root410 证明了 edge remap old-id 返回集合；但代表边重选是同一 old-item cleanup
  链路里的第三个写事实步骤。
- 这里的 `{}` 是允许的，但只应表示“PostgreSQL 明确 rowcount=0 且没有 representative edge row 可更新”。旧实现把“没有 returned row”
  和“合法 no-op”混成一类，破坏了 PostgreSQL 写入证据。
- 成熟 Kappa/CQRS 里，旧 item 的 representative fact 会影响后续 item processing、page projection 和 derived fact cleanup。只靠 returned row
  presence 会把 driver/adapter 异常伪装成“代表边已刷新或无须刷新”，从而让事实图和派生清理之间出现不可重放空洞。

修复：

- `_reselect_news_item_representative_from_edges(...)` 现在保存 cursor，`fetchone()` 后调用
  `_optional_returning_row(cursor, row)`。
- rowcount=0/no row 是唯一合法的 no-representative-edge cleanup 结果；rowcount=1/row 是唯一合法的 representative fact refresh。
- 单元测试覆盖缺失 rowcount、非法/不匹配 rowcount、rowcount=1/no-row mismatch、显式 zero-row no-op 和正常 rowcount=1；
  架构守护禁止恢复 chained `.fetchone()`、`return dict(row)` 或 rowcount 默认兜底。

验证：

- RED：focused representative-reselection rowcount 单元命令初始失败 `9 failed, 2 passed`；架构守护初始失败，命中 chained
  `).fetchone()` 和 `return dict(row)`。
- GREEN：focused representative-reselection 单元命令通过，`11 passed`；架构守护通过，`1 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root413 - News item-process claim RETURNING rows 缺少 rowcount 证据

发现：

- `NewsRepository.claim_unprocessed_items(...)` 是 `NewsItemProcessWorker` 的状态机入口：它把 `raw` / `process_retryable`
  的 `news_items` 更新为 `processing`，写入 `processing_lease_owner`、`processing_leased_until_ms`，并递增 `processing_attempts`。
- SQL 使用 `WITH picked AS (...) claimed AS (UPDATE news_items AS items ... RETURNING items.*) SELECT ... FROM claimed ...` 返回 claim rows。
- 旧实现直接链式 `self.conn.execute(...).fetchall()`，随后 `return [dict(row) for row in rows]`。
- 因此 missing rowcount、非法 rowcount、rowcount 与 returned claim rows 不匹配，都会被忽略；worker 会把未被 PostgreSQL rowcount 证明的
  claim rows 当成已租约工作继续处理。

根因：

- `claim_unprocessed_items` 不是普通读查询，它是 worker lease/CAS 边界。返回的每一行都会驱动 deterministic entity/token/fact writes、
  content classification、market scope/story identity、agent admission、retry/terminal transition 和 page/brief dirty enqueue。
- 成熟 Kappa/CQRS worker 入口必须先证明“这些 rows 确实被数据库本次更新为 processing”，再让 worker 在事务外执行 CPU/LLM/后续写入。
  只信任 returned rows 会让驱动异常、adapter fake cursor 或不完整 claim evidence 伪装成有效租约。
- 这类缺口会把 control-plane state 和 material fact writes 串成不可重放状态：worker 以为自己持有 lease，但 PostgreSQL claim 证据并不完整。

修复：

- `claim_unprocessed_items(...)` 现在保存 cursor，`fetchall()` 后调用 `_returned_rowcount(cursor, rows)`。
- 只有 cursor rowcount 与 returned claim rows 数量一致时，才返回 `claimed_rows` 给 `NewsItemProcessWorker`。
- 单元测试覆盖缺失 rowcount、非法/不匹配 rowcount、显式 zero-row no-op 和正常 rowcount=1；架构守护禁止恢复 chained
  `.fetchall()`、直接 `return [dict(row) for row in rows]` 或 rowcount 默认兜底。

验证：

- RED：focused item-process claim rowcount 命令初始失败 `9 failed, 2 passed`，证明旧实现忽略 missing/invalid/mismatched rowcount；
  architecture guard 同时命中 chained `.fetchall()` 和 direct returned-list accounting。
- GREEN：focused item-process claim 单元+架构命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root414 - News current brief schema cleanup RETURNING ids 缺少 rowcount 证据

发现：

- `NewsRepository.clear_current_briefs_outside_schema(...)` 是 current item-brief read model 的 schema-version maintenance 边界。
- 它删除 schema_version 不符合当前版本的 `news_item_agent_briefs` 行，通过 `DELETE FROM news_item_agent_briefs ... RETURNING news_item_id` 返回被清理的 current brief ids。
- 旧实现直接链式 `self.conn.execute(...).fetchall()`，随后 `return [str(row["news_item_id"]) for row in rows]`。
- 因此 missing rowcount、非法 rowcount、rowcount 与 returned ids 不匹配，都不会失败；维护路径会把未被 PostgreSQL rowcount 证明的 returned ids 当成已清理结果。

根因：

- Root411 证明了 fresh `news_item_agent_runs` / `news_item_agent_briefs` 写入需要 required single-row 证据，但 schema cleanup 是同一个 current read model 的维护写边界。
- 这个 cleanup 看起来只是“删旧 schema”，但它改变的是 serving current brief 状态；后续 page projection / high-signal publication 会把缺失 current brief 解释为真实降级状态。
- 成熟 Kappa/CQRS 对派生 current read model 的维护操作也要可重放、可解释：rowcount=0/no rows 是合法 no-op；rowcount=N/returned N ids 才是合法 cleanup；driver/adapter 证据异常不能伪装成成功清理。

修复：

- `clear_current_briefs_outside_schema(...)` 现在保存 cursor，`fetchall()` 后调用 `_returned_rowcount(cursor, rows)`。
- 只有 cursor rowcount 与 returned deleted ids 数量一致时，才返回 `cleared_ids`。
- 单元测试覆盖缺失 rowcount、非法/不匹配 rowcount、zero-row no-op 和正常多行删除；架构守护禁止恢复 chained `.fetchall()`、直接 returned-list cleanup accounting 或 rowcount 默认兜底。

验证：

- RED：focused current-brief schema cleanup rowcount 单元命令初始失败 `8 failed, 2 passed`，证明旧实现忽略 missing/invalid/mismatched rowcount。
- GREEN：focused cleanup 单元命令通过，`10 passed`；架构守护通过，`1 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root415 - News projection dirty-target claim RETURNING rows 缺少 rowcount 证据

发现：

- `NewsProjectionDirtyTargetRepository.claim_due(...)` 是 News page/source-quality projection 的 dirty-target 租约入口。
- SQL 先用 `FOR UPDATE SKIP LOCKED` 选择 due targets，再执行 `UPDATE news_projection_dirty_targets ... RETURNING news_projection_dirty_targets.*` 返回 claim rows。
- 旧实现直接链式 `.fetchall()` 并返回 `[dict(row) for row in rows]`；missing rowcount、非法 rowcount、rowcount 与 returned rows 不匹配，都不会失败。
- 结果是 projection worker 可能把未被 PostgreSQL rowcount 证明的 dirty target rows 当成已租约工作，继续 rebuild `news_page_rows` 或 source-quality rows。

根因：

- `claim_due` 不是普通读路径，而是 worker lease/CAS 边界。这里返回的 rows 会决定后续 projection 是否有权写 derived read model、mark done/error、或进入 retry。
- 成熟 Kappa/CQRS 的 claim 语义必须由数据库状态迁移证明：rowcount=0/no rows 才是 no-work；rowcount=N/returned N rows 才是合法 leased work。
- 只信任 returned rows 会把 driver/adapter 的不完整证据变成“工作已经被租到”的事实，破坏 single-writer projection 的可解释性和失败可重放性。

修复：

- `claim_due(...)` 现在保存 cursor，`fetchall()` 后调用 `_returned_rowcount(cursor, rows)`。
- 只有 cursor rowcount 与 returned claim rows 数量一致时，才返回 `claimed_rows`。
- 单元测试覆盖缺失 rowcount、非法/不匹配 rowcount、zero-row no-op 和正常 claim；架构守护禁止恢复 chained `.fetchall()`、直接 returned-list claim accounting 或 rowcount 默认兜底。

验证：

- RED：focused dirty-target claim rowcount 命令初始失败 `9 failed, 2 passed`，证明旧实现忽略 missing/invalid/mismatched rowcount；architecture guard 同时命中 chained `.fetchall()` 和 direct returned-list accounting。
- GREEN：focused dirty-target claim 单元+架构命令通过，`11 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root416 - Notification aggregate UPDATE 缺少 rowcount 证据

发现：

- `NotificationRepository._aggregate_notification_row(...)` 是通知事实聚合边界：当 `INSERT INTO notifications ... ON CONFLICT DO NOTHING`
  返回冲突后，它会把同一 `dedup_key` 的既有通知行更新为最新 severity/title/body/entity/source/payload/channel，并递增或保留
  `occurrence_count`。
- 旧实现对 `UPDATE notifications ... WHERE notification_id = %s` 只执行 `self.conn.execute(...)`，随后直接 `return True`。
- 因此 cursor 缺失 rowcount、rowcount 非整数、rowcount=0、或 rowcount>1 时，调用方仍会得到 `aggregated=True`，并继续读取
  `notification_by_id(...)`、触发 external delivery requeue 或报告 worker 已聚合通知。

根因：

- Root353 已经修正了 `INSERT ... DO NOTHING` 的 0/1 rowcount 分类，但聚合 UPDATE 是不同语义：它不是“可选插入”，而是
  `notification_id` 定位的确定性事实更新。
- 这里把“冲突插入可为 0/1”的 helper 语义误延伸到了“既有行必须更新 1 行”的状态机边界，导致 PostgreSQL 执行证据缺口继续存在。
- 成熟 Kappa/CQRS 中，`notifications` 是产品通知 ledger；聚合不是普通读后修饰，而是在单 writer 内改变 serving fact。没有 rowcount=1
  证明时，不能把后续 delivery wake 或 UI 聚合状态建立在 returned/readback 结果上。

修复：

- 聚合 UPDATE 现在保存 cursor，调用 `_single_row_write_count(...)` 读取真实 PostgreSQL rowcount。
- `notification_aggregate_rowcount_required` 覆盖缺失 rowcount；`notification_aggregate_rowcount_invalid` 覆盖非法、0 行或多行更新。
- 新增单元测试覆盖缺失 rowcount、非法 rowcount、0/多行 rowcount 和 rowcount=1 成功聚合；新增 architecture guard 禁止恢复裸
  UPDATE 后直接 `return True`。

验证：

- RED：focused notification aggregate rowcount 命令初始失败 `7 failed, 1 passed`，证明旧实现没有读取聚合 UPDATE rowcount；
  architecture guard 初始找不到 `_single_row_write_count(...)`。
- GREEN：focused aggregate rowcount 命令通过，`8 passed`。
- 通知单元+架构非集成组通过，`88 passed`；targeted ruff 和生产仓储 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root417 - Token fact 仓储写入缺少 rowcount/RETURNING 执行证据

发现：

- `TokenEvidenceRepository.insert(...)` 和 `TokenIntentRepository.insert(...)` 旧实现执行 `INSERT ... ON CONFLICT DO UPDATE` 后，通过
  `self.get(...) or {}` 写后读取返回事实行；主写入 cursor 的 PostgreSQL `rowcount` 没有被读取，写入 SQL 也没有 `RETURNING *`。
- `TokenEvidenceRepository.delete_by_event_id(...)`、`TokenIntentRepository.delete_by_event_id(...)`、`TokenIntentLookupRepository.replace_lookup_keys(...)`
  的 delete/upsert 路径只执行 SQL，不验证 cursor 是否携带真实非负 rowcount。
- `IntentResolutionRepository.insert_resolution(...)` 在 advisory lock 后先 supersede 旧 current resolution，再 upsert 新 resolution；旧实现没有验证
  supersede `UPDATE` 是否正好更新 1 行，也用 `self.get(resolution_id) or {}` 作为 resolution upsert 的成功证明。
- 这些表不是普通缓存：`token_evidence`、`token_intents`、`token_intent_lookup_keys`、`token_intent_resolutions`
  是 ingest/rebuild/reprocess 之后所有 Token Radar、event token projection、search/watchlist timeline 的 token 事实根。

根因：

- 前面 Root372/Root398-416 已经反复暴露同一类问题：系统很多写路径把 returned row、fallback SELECT 或 Python list 长度当成数据库执行证明。
  Token fact 仓储是更靠前的事实入口，如果这里仍然允许写后读取兜底，后续所有派生 read model 都可能在“事实是否真的被 PostgreSQL 接受”未被证明时推进。
- 成熟 Kappa/CQRS 的事实写入边界应区分三件事：SQL 是否执行、影响了几行、返回了哪一行。`SELECT` readback 只能证明某个 id 当前存在，
  不能证明本次 mutation 成功，也不能发现 driver/adapter 缺失 rowcount、rowcount 非整数、0 行或多行异常。
- 对 lookup replacement 和 resolution supersede，这个区别尤其关键：delete 可以合法影响 0..N 行，lookup key upsert 必须逐 key 影响 1 行；
  `ON CONFLICT DO NOTHING` evidence link 可合法 0/1；resolution supersede 必须更新当前旧行 1 行。把这些语义混成“没有异常就成功”
  会让事实图的边和 current 状态机出现不可重放空洞。

修复：

- `TokenEvidenceRepository.insert(...)` 和 `TokenIntentRepository.insert(...)` 改为 `INSERT ... ON CONFLICT ... RETURNING *`，并通过
  `_required_returning_row(cursor, row)` 要求 rowcount=1 且必须返回一行；删除旧的 `self.get(...) or {}` 成功兜底。
- token evidence/intent delete 路径读取 `_cursor_rowcount(cursor)`，接受真实非负影响行数，但拒绝缺失、布尔、负数和非整数 rowcount。
- `TokenIntentRepository` 的 evidence link `INSERT ... ON CONFLICT DO NOTHING` 使用 `_optional_single_rowcount(cursor)`，只允许 0/1；
  `TokenIntentLookupRepository.replace_lookup_keys(...)` 的 delete 接受非负 rowcount，每个 lookup upsert 必须 rowcount=1。
- `IntentResolutionRepository.insert_resolution(...)` 只在存在 current 且 resolution_id 不同时执行 supersede UPDATE，并要求该 UPDATE rowcount=1；
  resolution upsert 同样使用 `RETURNING * + rowcount=1` 返回刚写入的 current resolution 行。
- 新增单元测试覆盖 missing/invalid rowcount、required single-row 0/2、evidence link optional 0/1、resolution supersede update rowcount；
  新增 architecture guard 禁止恢复 fallback SELECT、rowcount 默认兜底和未验证的 RETURNING 写路径。

验证：

- RED：focused token fact rowcount 命令初始失败 `27 failed, 1 passed, 13 deselected`，证明旧实现忽略 missing/invalid rowcount、required
  single-row 异常和 evidence-link optional rowcount；architecture guard 同时命中旧 fallback/readback 形状。
- GREEN：同一 focused 命令通过，`28 passed, 13 deselected`。
- token fact 单元+事务/rowcount 架构非集成组通过，`42 passed`；targeted ruff 通过，四个生产 token fact 仓储 mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root418 - Pulse evidence packet run-link UPDATE 缺少 rowcount 证据

发现：

- Root396 已经把 `pulse_evidence_packets` 的 `INSERT ... ON CONFLICT ... RETURNING evidence_packet_id`
  收紧到 rowcount=1 且必须有返回行。
- 但同一个 `upsert_packet(...)` 后半段仍然直接执行 `UPDATE pulse_agent_runs SET evidence_packet_id = ..., evidence_packet_hash = ... WHERE run_id = ...`，
  没有读取这个 UPDATE 自己的 PostgreSQL `cursor.rowcount`。
- 这意味着 packet row 本身已经被证明写入成功，但 run audit ledger 是否真的链接到了该 packet 仍未被证明。缺失 rowcount、0 行、2 行或非法
  rowcount 都可能在旧代码里表现为 `upsert_packet(...)` 成功。

根因：

- 前序修复把“packet fact 存在”当作 evidence boundary 的关键证据，但没有把“agent run audit 指向该 packet”视为第二个独立数据库 mutation。
- 成熟 Kappa/CQRS 的 agent 审计链不是只证明最后有一个 packet id/hash，而是证明因果链上每个状态跃迁都由 PostgreSQL 明确接受：
  packet row 写入/更新是一段事实，`pulse_agent_runs` 账本链接是另一段事实。
- 一个 mutation 的 rowcount/RETURNING 不能替另一个 mutation 背书；否则 sealed evidence packet 和 replay/cost/eval/candidate 账本之间会出现
  “packet 已写、run 未必链接”的可重放空洞。

修复：

- `PulseEvidenceRepository` 新增 `_required_single_rowcount(...)`，复用严格 `_cursor_rowcount(...)` 契约。
- `upsert_packet(...)` 在 packet `RETURNING` 通过 `_required_returning_row(cursor, row)` 后，保存
  `run_link_cursor = self.conn.execute(...)`，并要求 `_required_single_rowcount(run_link_cursor)`。
- 新增单元测试覆盖 run-link UPDATE 缺失 rowcount、布尔/字符串/负数/0/多行 rowcount；架构守护要求保留
  `_required_single_rowcount(run_link_cursor)`。

验证：

- RED：focused PulseEvidence run-link rowcount 命令初始失败 `8 failed, 10 passed`，证明旧实现只证明 packet upsert，不证明 run-link UPDATE。
- GREEN：同一 focused 命令通过，`18 passed`。
- Pulse evidence/eval/run/candidate/playbook/admission 非集成组通过，`125 passed`；targeted ruff 和 `pulse_evidence_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root419 - ProjectionRepository dirty-range claim 只信 returned rows，不校验 rowcount

发现：

- `ProjectionRepository.claim_dirty_ranges(...)` 对 `projection_dirty_ranges` 执行
  `UPDATE ... RETURNING ranges.*`，旧实现直接链式 `.execute(...).fetchall()`，再把返回 rows 转成 dict 列表。
- Root81 已经要求 `ProjectionRepository` 控制面写入进入 connection transaction，Root355 已经要求 stale `projection_runs`
  cleanup 用真实 rowcount。但 dirty-range claim 这条 returned-row lease 路径仍没有验证 `cursor.rowcount` 与 returned rows 一致。
- 这意味着 worker/ops 可以把 returned rows 当成已成功 lease 的 dirty ranges，即使 driver/fake 缺少 rowcount、rowcount 非法，或者 rowcount 与 rows 数量不一致。

根因：

- 前序治理把“普通 UPDATE 计数”和“控制面事务边界”拆开修了，但没有覆盖 `UPDATE ... RETURNING` claim 这种批量 lease 语义。
- 成熟 Kappa/CQRS 里，控制面 claim rows 不是只读结果集，而是 worker 获得处理权的状态跃迁。`projection_dirty_ranges`
  从 pending 到 running 的跃迁必须由 PostgreSQL 同时证明“更新了 N 行”和“返回了这 N 行”。
- 如果只相信 returned rows，缺失/漂移的 cursor rowcount 会让投影 worker 在控制面证据不完整时继续处理 dirty work；如果只相信 rowcount，又会丢掉具体 lease identity。
  两者必须匹配。

修复：

- `claim_dirty_ranges(...)` 改为保存 cursor，执行 `rows = cursor.fetchall()` 后调用 `_returned_rowcount(cursor, rows)`。
- 新增 `_returned_rowcount(...)`，复用 `_cursor_rowcount(...)`，要求 rowcount 等于 `len(rows)`；缺失 rowcount 抛
  `projection_repository_rowcount_required`，非法或 mismatched rowcount 抛 `projection_repository_rowcount_invalid`。
- 新增单元测试覆盖 missing/invalid/mismatched rowcount，并保留 rowcount=0/rows=[] 的 no-work claim 合法路径；架构守护禁止恢复链式 `.fetchall()`。

验证：

- RED：focused ProjectionRepository claim rowcount 命令初始失败 `8 failed, 1 passed, 7 deselected`，证明旧实现不检查 claim returned-rowcount。
- GREEN：同一 focused 命令通过，`9 passed, 7 deselected`。
- 按当前用户指令，本轮不运行 integration-heavy gate；后续非集成组、static 和 SDD gate 记录在 SDD verification。

### Root420 - ProjectionRepository 普通控制面写入仍无单行执行证明

发现：

- Root81 已经要求 `ProjectionRepository` 控制面写入进入 connection transaction，Root355/Root419 分别收紧 stale cleanup 和 dirty-range claim 的 rowcount 证据。
- 但 `advance_offset(...)`、`finish_run(...)`、`enqueue_dirty_range(...)` 仍只执行 `INSERT/UPDATE`，不保存 cursor，也不检查 PostgreSQL rowcount。
- `start_run(...)` 更隐蔽：旧实现先插入 `projection_runs`，再 `return self.run_by_id(resolved_run_id) or {}`。这个读回只证明“后来能按 run_id 读到一行”，不能证明本次 INSERT 成功影响了 exactly one row。

根因：

- 前序治理按“最刺眼的异常路径”推进：先修 transaction ownership，再修 stale cleanup 计数，再修 returned-row claim。剩余普通控制面 DML 因为没有返回业务计数，被误当作“执行了就行”。
- 但成熟 Kappa/CQRS 的投影控制面不是普通日志：`projection_offsets` 是 frontier，`projection_runs` 是运行审计状态机，`projection_dirty_ranges` 是 work lease 控制队列。每次写入都必须由 PostgreSQL 证明执行结果。
- fallback readback 是兼容性思维，不是状态机证明。它会把“本次 INSERT 没有可信 rowcount / 没有返回行 / 更新了 0 或多行”的错误折叠成“读到某个同 key 行”，从而削弱幂等、审计和重放语义。

修复：

- `advance_offset(...)`、`finish_run(...)`、`enqueue_dirty_range(...)` 保存 cursor，并调用 `_required_single_rowcount(cursor)`，要求 rowcount exactly 1。
- `start_run(...)` 改为 `INSERT INTO projection_runs ... RETURNING *`，保存 cursor 后 `fetchone()`，再通过 `_required_returning_row(cursor, row)` 同时验证 rowcount=1 和 returned row 存在。
- 新增单元测试覆盖 missing/invalid/0/2 rowcount，以及 `start_run` rowcount=1 但无 returned row；架构守护禁止恢复 `run_by_id(resolved_run_id) or {}` 读回兜底。

验证：

- RED：focused ProjectionRepository required-control-write 命令初始失败 `30 failed, 15 deselected`，证明旧实现不检查普通控制面写入 rowcount，也不拒绝 `start_run` 无 returned row。
- GREEN：同一 focused 命令通过，`30 passed, 15 deselected`。
- ProjectionRepository 非集成组通过，`49 passed`；targeted ruff 和 `projection_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate；SDD validator/index/diff 记录在 SDD verification。

### Root421 - Token Radar API 为 Narrative hydration 临时合成目标身份字段

发现：

- `/api/token-radar` 的 public rows 来自 `AssetFlowService`，正式目标身份在 nested `target.target_type` / `target.target_id`。
- 但 `routes_radar._token_radar_data(...)` 旧实现先调用 `_with_top_level_targets(...)`，把 nested target 临时复制成顶层 `target_type` / `target_id` 和 `_synthetic_target_*` 标记，再在 hydrate 后 `_strip_synthetic_targets(...)` 删除。
- 这说明 NarrativeReadModel 仍要求旧顶层目标身份形状，API route 被迫承担 read-model identity adapter 职责。

根因：

- Root278 已删除 NarrativeReadModel 对旧 `type` / `id` alias 的兼容，但没有把 Narrative hydration 对齐到 Token Radar 当前 public DTO 的正式 `target` 对象。
- 结果是旧 alias 被删了，但又在 API 层新增了“合成顶层字段再剥离”的桥。它不写数据库，却仍是兼容性代码：public read path 在运行时修补 read-model identity shape。
- 成熟 CQRS 的 public read path 应只组合当前读模型，不应为下游 hydrator 临时伪造身份字段；身份规范应在 read model 边界内被理解。

修复：

- `routes_radar._token_radar_data(...)` 直接把 `AssetFlowService.asset_flow(...)` 的 public payload 交给 `NarrativeReadModel.hydrate_token_radar(...)`，删除 `_with_top_level_targets`、`_strip_synthetic_targets` 和 `_synthetic_target_*` 标记。
- `NarrativeReadModel` 新增 `_target_identity(row)`，优先读取 formal public `row["target"]["target_type"]` / `row["target"]["target_id"]`，同时保留 direct formal `target_type` / `target_id` 行形状；仍不读取旧 `type` / `id` alias。
- 新增单元测试证明 nested public target 可直接 hydrate，API route 传给 hydrator 的行没有合成字段；架构守护禁止 synthetic target helper 复活。

验证：

- RED：focused Token Radar narrative hydration 命令初始失败 `3 failed`，证明旧 NarrativeReadModel 不读 nested target，route 仍合成 `_synthetic_target_*`。
- GREEN：同一 focused 命令通过，`3 passed`。
- Narrative read model/API narrative/route guard 非集成组通过，`19 passed`；targeted ruff 和 routes/narrative mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate；后续 SDD validator/index/diff 记录在 SDD verification。

### Root422 - RegistryRepository upsert 用写后读回替代 PostgreSQL 写入证据

发现：

- `RegistryRepository.upsert_cex_token(...)`、`upsert_pricefeed(...)`、`upsert_us_equity_symbol(...)`
  旧实现执行裸 `INSERT ... ON CONFLICT DO UPDATE` 后，通过 `_row_by_id(...) or {}` 读回结果。
- `upsert_chain_asset(...)` 虽然已经使用 `RETURNING *` CTE，但最后仍是 `dict(row) if row else {}`，没有验证
  PostgreSQL `cursor.rowcount`。
- 这些不是普通缓存行，而是 `registry_assets`、`cex_tokens`、`price_feeds`、`us_equity_symbols` 事实/控制行：
  它们驱动 deterministic resolution、CEX/DEX 市场路由、Token Profile source sync、US equity symbol elevation，以及后续 Token Radar/market routing。

根因：

- 前序治理修好了 connection transaction ownership，但没有把“本次 mutation 是否被 PostgreSQL 接受 exactly one row”也收紧成合同。
- 写后读回只证明“同 key 后来能读到一行”，不能证明本次 upsert 写了 exactly one row；在并发、driver 证据缺失、mock 兼容和
  `ON CONFLICT` 分支漂移时，它会把执行证据缺口伪装成成功事实。
- 成熟 Kappa/CQRS 里，registry facts 是上游身份/路由事实，不是 read-model 旁路缓存。每条 upsert 必须由 PostgreSQL 的
  `RETURNING` 行和 `cursor.rowcount` 同时证明；否则 resolver、profile sync、market tick routing 会继承一条来源不明确的事实链。

修复：

- 四个 upsert 都保存 cursor，`fetchone()` 后通过 `_required_returning_row(cursor, row)` 返回。
- CEX token、price feed、US equity symbol upsert SQL 增加 `RETURNING *`；chain asset 既有 CTE result 也统一校验
  rowcount=1 和 returned row。
- 删除 `_row_by_id(...)` 写后读回兜底，新增单元测试覆盖缺失 rowcount、非法/非 1 rowcount、rowcount=1 但没有 returned row；
  架构守护禁止 `_row_by_id`、`dict(row) if row else {}`、`) or {}` 回归。

验证：

- RED：focused registry upsert rowcount 命令初始失败 `9 failed, 46 deselected`，证明旧实现不要求 upsert cursor rowcount，也不拒绝
  rowcount=1/no-row。
- GREEN：同一 focused 命令通过，`37 passed, 18 deselected`。
- RegistryRepository 非集成组通过，`57 passed`；targeted ruff 和 `registry_repository.py` mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate；SDD validator/index/diff 记录在 SDD verification。

### Root423 - PulseJobsRepository 单行 RETURNING 状态迁移只信 returned row

发现：

- `PulseJobsRepository` 已经修过 terminal batch 的 returned-rowcount，也修过 stale agent-run cleanup 的裸 rowcount。
- 但单行 `pulse_agent_jobs` 状态迁移仍有链式 `self.conn.execute(... RETURNING ...).fetchone()`：
  `enqueue_job(...)`、`claim_due_job(...)`、`mark_job_succeeded(...)`、`mark_job_failed(...)`、terminal retry、
  worker timeout cancel、backpressure release、provider cooldown release 都会从 returned row presence 推导状态机结果。
- 这些路径不是普通读；它们决定 job 是否被 lease、是否进入 retry/dead、是否释放 attempt、以及 terminal ledger 是否可以写入。
  缺失 rowcount、非法 rowcount、rowcount=1 但无 row、rowcount=0 但有 row，在旧代码里都可能被折叠成“有/无返回行”的业务结论。

根因：

- 前序治理先修了批量 terminalization 和 stale cleanup，因为它们直接返回数量；但单行 `RETURNING *` 更容易被误认为“有 row 就够了”。
- 成熟 Kappa/CQRS 的 job control plane 是 worker 处理权和重试状态机，不是展示缓存。`UPDATE ... RETURNING` 需要同时证明两件事：
  PostgreSQL 更新了 0/1 行，以及返回行和更新行数一致。只拿 row 不看 rowcount，会让 fake driver、驱动异常或 CAS 漂移伪装成合法 lease/result。
- terminal ledger 是第二阶段副作用，必须在 job mutation execution evidence 通过以后才能写。否则会出现“terminal evidence 已写，但 job 状态迁移本身没有被 PostgreSQL 证明”的因果倒挂。

修复：

- `PulseJobsRepository` 新增 `_single_returning_rowcount(...)`、`_required_returning_row(...)`、`_optional_returning_row(...)`。
- `enqueue_job(...)` 作为 required enqueue，只接受 rowcount=1 且有返回 row。
- `claim_due_job(...)`、success/failure、terminal retry、worker timeout cancel、backpressure/provider cooldown release 作为 optional CAS/claim 路径，只接受 rowcount=0/no-row 或 rowcount=1/row。
- 架构守护禁止这些单行 mutation 恢复链式 `.fetchone()`、`_row(row)`、`_optional_row(row)` 或 rowcount 默认兜底。

验证：

- Focused Pulse job 命令通过，`63 passed, 45 deselected`。
- Pulse job/service/worker 近邻非集成组通过，`183 passed, 38 deselected`。
- Targeted ruff、`pulse_jobs_repository.py` mypy 和单文件 residual `RETURNING ... .fetchone()` 扫描通过。
- 本次未单独重放 pre-fix RED，因为实现 patch 先于第一次 focused run；新增测试已覆盖旧缺口的 missing/invalid/mismatched rowcount 失败形态。
- 按当前用户指令，本轮不运行 integration-heavy gate；SDD validator/index/diff 记录在 SDD verification。

### Root424 - DiscoveryRepository claim/result 状态从 returned rows 或写后读回推导

发现：

- `DiscoveryRepository.claim_due_lookup_keys(...)` 通过 `UPDATE token_discovery_dirty_lookup_keys ... RETURNING queue.*`
  lease due lookup work，但旧实现直接链式 `.fetchall()`，再把 rows 转成 dict 列表；没有证明 PostgreSQL rowcount 与 returned rows 一致。
- `start_lookup(...)` 和 `fail_lookup(...)` 写 `token_discovery_results` 后用 `self.result(...) or {}` 读回结果。
- `finish_lookup(...)` 先读取 current 判断 changed，再执行 upsert，但旧实现没有验证这次 finish upsert 是否真的影响 exactly one row。

根因：

- 前序 Discovery 治理优先修了队列 enqueue/done/reschedule changed-row counts 和 terminal delete `RETURNING` rowcount，但遗漏了两条更贴近 worker 状态机的边：
  due claim lease 以及 result running/found/error ledger。
- 对成熟 Kappa/CQRS 来说，`token_discovery_dirty_lookup_keys` 是控制面 lease，`token_discovery_results` 是 provider lookup 的事实/状态账本。
  worker 是否可以开始 provider IO、是否可以报告 found/error，不应由“返回了几行”或“事后能按 key 读到一行”背书，而必须由本次 mutation 的 PostgreSQL 执行证据背书。
- 写后读回尤其危险：它把“本次 INSERT/UPDATE 没有可信 rowcount / 未写入 / 写了多行”的错误，折叠成“同 key 当前有一行”。
  在重试、并发 claim、running timeout 恢复和 hot not-found retry 下，这会削弱可重放性和状态机因果链。

修复：

- `claim_due_lookup_keys(...)` 改为保存 cursor，`fetchall()` 后调用 `_returned_rowcount(cursor, rows)`，要求 rowcount 与 returned claim rows 匹配；rowcount=0/no rows 是唯一 no-work claim。
- `start_lookup(...)` 和 `fail_lookup(...)` 改为 `RETURNING *`，通过 `_required_returning_row(cursor, row)` 返回；删除 `self.result(...) or {}` 写后读回。
- `finish_lookup(...)` 在返回 changed boolean 前调用 `_required_single_rowcount(cursor)`，要求 finish upsert rowcount=1。
- 新增 unit/architecture 覆盖 claim missing/invalid/mismatched rowcount、0-row no-op、start/fail rowcount=1/no-row、finish missing/invalid rowcount，以及禁止写后读回/链式 claim fetch。

验证：

- Focused Discovery command 通过，`68 passed`。
- Discovery/resolution-refresh 近邻非集成组通过，`89 passed`。
- Targeted ruff、`discovery_repository.py` mypy 和 residual write-readback/chained `RETURNING` scan 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate；SDD validator/index/diff 记录在 SDD verification。

### Root425 - Ops projection dirty repair 用宽 News 投影输入查询生成 keyset

发现：

- `enqueue_projection_dirty_targets(...)` 是显式 ops repair，不是常驻 worker；但它生成 page/brief/source-quality dirty targets 时，
  `_fetch_news_item_rows(...)` 原先读取了接近 News page/brief 投影输入的宽行：`news_sources` join、`news_token_mentions` /
  `news_fact_candidates` LATERAL JSON 聚合、provider signal、token impacts、story/admission JSON 等。
- `projection="source_quality"` 只需要 source ids，却仍会先扫描 `news_items`。
- `projection="page"` 被允许不带 `since_ms` 全量运行；旧查询在这个合法路径上会对全量 `news_items` 做宽读和 LATERAL 聚合，只为了得到
  `news_item_id` 和 watermark。

根因：

- 事务治理已经把 `--execute` 写队列约束到 connection transaction，但 SQL 读宽度还停留在“重建投影输入”的思维。
- 成熟 Kappa/CQRS 里，repair enqueue 的职责是生成 durable dirty-target keyset；真正的 projection worker 才拥有读取宽事实、组装 page/brief
  projection input 的成本。把宽输入查询放到 repair 命令，会让人工 repair 和 dry-run 变成隐藏的 read-model rebuild 热点。
- 这不是功能正确性 bug，而是 PostgreSQL 最佳实践和链路职责边界问题：全表 keyset 扫描应该窄列、可索引、按 projection 需要拆分；LATERAL
  JSON 聚合应该留在明确的 projection rebuild 路径。

修复：

- `_enqueue_news_targets(...)` 只有在 page/brief projection 被选中时才调用 `_fetch_news_item_rows(...)`；source-quality-only repair 不再扫描
  `news_items`。
- `_fetch_news_item_rows(...)` 收窄为只选 `items.news_item_id`、`items.published_at_ms AS source_watermark_ms`、`items.agent_admission_status`。
- 单测证明 source-quality-only repair 不出现 `FROM news_items`；架构测试禁止 `JOIN news_sources`、`LEFT JOIN LATERAL`、
  `news_token_mentions`、`news_fact_candidates`、`agent_admission_json`、provider signal/impact 宽列回流。

验证：

- Focused ops projection dirty repair command 通过，`10 passed`。
- 后续 targeted ruff、SDD validator/index/diff 记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root426 - Public WebSocket replay 按过滤条件基数放大 SQL 查询预算

发现：

- `/ws` 的 subscribe 消息把 `replay` 限制到 1000，但旧实现没有限制 `handles`、`cas`、`symbols`、`market_targets` 的总基数。
- 当客户端传入多个 `cas` 或 `symbols` 时，`PublicWebSocketHub._replay_events(...)` 会对每个过滤值分别调用
  `repos.evidence.recent_events(limit=replay, ...)`，再逐条读取 entities、alerts、token intents 和 projected event tokens。
- 这意味着单个 public subscribe 可以把一次 replay 放大成 `N * replay` 的事件读取和 payload 补全，而外层 API 看起来仍然“有 replay limit”。

根因：

- 旧边界只把“返回多少条 replay 消息”当成预算，没有把“过滤条件基数”和“每个过滤值的 SQL fan-out”当成预算。
- 成熟 Kappa/CQRS 的读侧 replay 也是 public query，不是无成本 fan-out。读模型正确性来自 PostgreSQL，但 PostgreSQL 读压力必须由产品窗口、页大小和 filter cardinality 一起限定。
- 这个问题不在 worker，也不在 `events` 表本身；根因是 WebSocket surface 处缺少 query-shaping contract，导致一个订阅消息可以绕过 HTTP route 的 limit 思维，触发多次 API-pool 读。

修复：

- `ws.py` 新增 `MAX_REPLAY_LIMIT = 1000` 和 `MAX_SUBSCRIPTION_FILTER_VALUES = 50`，超限 subscribe 返回 `too_many_filters`，并且在错误时不改写当前 client subscription。
- `_handle_client_message(...)` 先解析到局部变量，验证通过后才提交到 `client`，避免 invalid/oversized subscribe 造成半更新状态。
- token-filter replay 使用 `_per_filter_replay_limit(...)` 按 `len(cas)+len(symbols)` 分摊总 replay limit，不再对每个 symbol/address 使用完整 replay limit。
- 单元测试覆盖 oversized filter 不打开 repository session、多 filter replay 每条 SQL 只拿分摊后的 limit。

验证：

- Focused unit command 通过，`5 passed`。
- Targeted static 和 SDD/static gate 记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root427 - WebSocket replay 在预算内仍逐事件补全 public projection payload

发现：

- Root426 已经限制了 replay 数量和 filter 基数，但 `_replay_events(...)` 旧路径仍在每个 replay event 上调用
  `_payload_for_event(...)`。
- `_payload_for_event(...)` 每次都会分别调用 `entities_for_event`、`alerts_for_event`、`intents_for_event`、
  `event_tokens.for_event`。因此 replay=1000 时，即使入口预算正确，也会产生最多 4000 次单事件补全查询。
- HTTP `/api/recent` 同一类 public event payload 已经使用 `_payloads_for_events(...)` 批量补全；WebSocket replay 与 HTTP read path
  在 SQL shape 上不一致。

根因：

- Root426 解决了“一个 subscribe 触发多少 replay event 查询”的入口放大，但没有继续审到 replay page shaping 层。
- 成熟 CQRS 读侧的页查询应该把 page id set 作为批量 read boundary：先确定本页事件，再批量读取 projected entities/alerts/intents/resolutions。
  按事件循环补全会把一个有界 page 重新变成 N+1 查询链。
- 这不是 payload 语义问题，而是 public read-side composition 的 SQL 性能边界问题。读模型仍然正确，但读成本随 replay page size 线性乘上 projection 种类。

修复：

- `_replay_events(...)` 现在先收集 raw event rows，token-filter replay 去重并按 `received_at_ms` 排序后截断到总 limit。
- 新增 `PublicWebSocketHub._payloads_for_events(...)`，对 replay page 统一调用 `entities_for_events`、`alerts_for_events`、
  `intents_for_events`、`event_tokens.for_events`。
- live publish 的 `_payload_for_event(...)` 保持单事件路径，replay 才使用页级批量补全。
- 单元测试证明 handle replay 页使用 batch APIs，且不调用单事件补全接口。

验证：

- RED：新增 `test_ws_replay_batches_projected_event_payloads_for_page` 初始失败，证明旧实现没有调用 `event_tokens.for_events(...)`。
- GREEN：public event/WebSocket unit command 通过，`6 passed`。
- Targeted static 和 SDD/static gate 记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root428 - Watchlist configured handles overview 对每个 handle 循环查询事实表

发现：

- `/api/watchlist/handles/overview` 只展示配置的 watchlist handles，但 `WatchlistIntelRepository.handles_overview(...)` 旧实现会对每个 handle 调 `_handle_overview_counts(...)`。
- `_handle_overview_counts(...)` 每个 handle 分别查询一次 latest event、一次 recent count；配置 50 个 handle 时就是 100 条 SQL。
- 这条路径虽然没有 provider IO，也不写 read model，但它是 public read API，SQL 成本跟配置 handle 基数线性放大。

根因：

- 前序治理把单 handle overview 的 source sample 做了 bounded limit，但 configured handles overview 仍保留“Python 循环组合读”的旧形状。
- 成熟 CQRS 读侧应该把输入 keyset 作为 SQL 边界：一次把 configured handle set 交给 PostgreSQL 聚合，保持输入顺序，再返回公共 payload。
- 按 handle 循环读事实表会让 API request 成本取决于配置长度，而不是一个可解释的 page/window/query budget；这和前面 WebSocket replay filter fan-out 是同一种 SQL shaping 漏洞。

修复：

- `handles_overview(...)` 改为单条 `WITH input_handles AS (...)` keyset 查询，通过 `unnest(%s::text[]) WITH ORDINALITY` 保持配置顺序。
- `events_by_handle` 在 PostgreSQL 内一次聚合 `last_source_event_at_ms` 和 `recent_source_event_count`，不再保留 `_handle_overview_counts(...)` per-handle helper。
- 架构守护要求 Watchlist repository 保留 `input_handles` / `WITH ORDINALITY` / `events_by_handle` 批量查询形状，并禁止 `_handle_overview_counts` 复活。

验证：

- RED：`test_handles_overview_batches_configured_handles_in_one_keyset_query` 初始失败，证明旧实现会继续发第二条 per-handle SQL。
- GREEN：Watchlist repository focused unit command 通过，`4 passed`。
- 后续 targeted static 和 SDD/static gate 记录在 SDD verification。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root429 - Watchlist configured handles overview 的批量 SQL 仍用全历史聚合求 latest

发现：

- Root428 把 `/api/watchlist/handles/overview` 从 Python N+1 改成了单条 keyset SQL，但第一版 SQL 用 `MAX(events.received_at_ms)` 在 `events_by_handle` 里同时求 last event 和 recent count。
- 这消除了 round trip 放大，却把 latest-event 查询变成了每个 configured handle 的全历史聚合。
- 数据库已经有 `idx_events_author_received_event_lower_desc` 这类 `(lower(author_handle), received_at_ms DESC, event_id DESC)` 索引，latest event 的最优读形态应是按 handle 做 descending index probe + `LIMIT 1`。

根因：

- “一次 SQL”被误当成了完整性能边界，但 PostgreSQL 最佳实践还要求 query shape 对齐索引和语义。
- latest event 和 recent count 是两个不同成本模型：latest 需要顶部一行，recent count 只需要 `since_ms` 窗口内范围。把它们放进同一个 full-history aggregate，会让 API 成本继续受单个 handle 历史深度影响。
- 成熟 CQRS 读侧不仅要避免 N+1，还要让每个 public query 的扫描宽度和产品窗口/输入 keyset 对齐。

修复：

- `handles_overview(...)` 保持一条 SQL 和 `WITH ORDINALITY` 输入顺序，但拆出 `latest_by_handle` 和 `recent_counts`。
- `latest_by_handle` 使用 `LEFT JOIN LATERAL (...) ORDER BY events.received_at_ms DESC, events.event_id DESC LIMIT 1`。
- `recent_counts` 只 join `events.received_at_ms >= since_ms` 的窗口范围。
- 架构守护禁止 `MAX(events.received_at_ms)` 回到 configured handles overview，并要求 `latest_by_handle` / `LEFT JOIN LATERAL` / `recent_counts` markers。

验证：

- RED：新增 `test_handles_overview_uses_indexable_latest_probe_and_windowed_count` 初始失败，证明 Root428 第一版 SQL 没有 `latest_by_handle` lateral probe。
- GREEN：Watchlist repository focused unit command 通过，`5 passed`。
- 非集成组合验证通过：Watchlist repository + Watchlist architecture guard，`6 passed`。
- Targeted static 通过：相关 Watchlist repository/test/architecture ruff clean，repository mypy clean。
- SDD/static gate 通过：`validate_sdd_artifacts.py`、`regen_sdd_work_index.py --check`、`git diff --check` 均 clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root430 - Account Quality 多账号读路径仍是 3H 次 SQL 的 read-side N+1

发现：

- `/api/notifications/account-quality` 通过 `AccountQualityService.account_quality_for_handles(...)` 读取多个 handle。
- 服务层虽然会 normalize/dedupe handle，但随后对每个 handle 调一次 `repository.account_quality(handle)`。
- 单个 `account_quality(handle)` 又分别查询 `account_profiles`、`account_token_call_stats`、`account_quality_snapshots`，所以 H 个 handle 会变成 3H 次 SQL。

根因：

- 前面的 Account Quality 治理把 read service 与 backfill 写服务拆开了，但只修了所有权边界，没有继续收紧多账号读路径的查询预算。
- “服务层去重”被误当成了足够的 boundedness；在成熟 CQRS 读侧，public endpoint 的成本应该由输入 keyset 和固定 SQL 数量决定，而不是由 Python 循环把单账号 reader 重复调用。
- token-call stats 与 quality snapshots 的 per-handle `LIMIT 50/20` 是 SQL 语义，应由 PostgreSQL 的 partition window rank 表达；如果在 Python 里逐个 handle 调查询，数据库无法整体规划 keyset 访问，应用层 round trip 也会随 handle 数线性放大。

修复：

- `AccountQualityService.account_quality_for_handles(...)` 改为调用 `repository.accounts_quality(unique_handles)`，不再循环调用单账号 reader。
- `AccountQualityRepository.accounts_quality(...)` 改为 3 条固定批量 SQL：profiles、token-call stats、quality snapshots。
- 每条 SQL 使用 `unnest(%s::text[]) WITH ORDINALITY` 作为 normalized handle keyset，并保留输入顺序。
- stats/snapshots 使用 `ROW_NUMBER() OVER (PARTITION BY handle ...)` 在 PostgreSQL 内做 per-handle `50/20` 窗口限制，避免全局 `LIMIT` 或 Python 二次截断改变语义。
- 架构守护禁止服务层/仓储层回到 per-handle `account_quality(...)` loop，并要求 keyset/window-rank SQL markers。

验证：

- RED：`test_account_quality_for_handles_uses_batched_repository_read` 初始失败，证明服务层仍调用 per-handle `account_quality`。
- RED：`test_accounts_quality_batches_profiles_stats_and_snapshots_by_handle_keyset` 初始失败，证明 repository 对 3 个输入 handle 发了 9 次 SQL。
- GREEN：两个 focused Account Quality 测试转绿，架构守护 `test_account_quality_multi_handle_reads_use_batched_keyset_sql` 通过。
- 非集成组合验证通过：Account Quality service/repository + 相关架构守护，`11 passed, 1 skipped`；skip 是现有 PostgreSQL 测试库不可用保护。
- Targeted static 通过：相关 Account Quality read service/repository/test/architecture ruff clean，read service + repository mypy clean。
- SDD/static gate 通过：`validate_sdd_artifacts.py`、`regen_sdd_work_index.py --check`、`git diff --check` 均 clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root431 - Resolution reprocess 对每个 intent 单独读取 evidence，worker 成本随 reprocess_limit 放大

发现：

- `resolution_refresh` worker 会按 dirty lookup 结果调用 `reprocess_recent_token_intents(...)`，受正式 `settings.workers.resolution_refresh.reprocess_limit` 控制。
- reprocess 先取一批 intents，但旧实现进入 loop 后对每个 intent 调一次 `repos.token_evidence.evidence_for_intent(...)`。
- 这让最多 `reprocess_limit` 个 intent 变成 1 次 intent 查询 + N 次 evidence 查询；当 `reprocess_limit` 为 500 时，单轮 worker 可产生 501 次读侧 SQL。

根因：

- 前面的治理把 resolution refresh 拉回 dirty lookup queue consumer，并硬化了 session transaction、source-dirty 决策、provider IO 边界，但没有继续审计 reprocess 内部的 payload hydration 宽度。
- `evidence_for_intent(...)` 是合理的单 intent reader，却被 runtime batch worker 复用成 N+1 组合。成熟 Kappa/CQRS worker 的 batch 处理应先用 keyset 批量取齐 payload，再在内存中按业务单元分组执行 deterministic resolver。
- PostgreSQL 最佳实践上，这类关联表读取应让数据库一次按 `intent_id` keyset join `token_intent_evidence` 和 `token_evidence`，并按输入顺序/role/span 排序；应用层逐个 intent 查询会放大 round trip，也让 planner 无法看到整批 keyset。

修复：

- `TokenEvidenceRepository` 新增 `evidence_for_intents(intent_ids)`，用 `unnest(%s::text[]) WITH ORDINALITY` 构造 intent keyset，join `token_intent_evidence` / `token_evidence` 后一次返回所有 evidence。
- repository 在 Python 中按 `intent_id` 分组，并为没有 evidence 的 requested intent 返回空 list，保持 resolver 输入语义。
- `token_resolution_refresh._reprocess_recent_token_intents(...)` 在 loop 前批量读取 `evidence_by_intent`，loop 内只做 `dict.get(...)`。
- 架构守护禁止 reprocess 重新调用 `evidence_for_intent(str(intent...))`，并要求 repository 批量 keyset SQL markers。

验证：

- RED：`test_reprocess_batches_evidence_for_recent_intents` 初始失败，证明没有 batch call。
- RED：`test_token_evidence_for_intents_batches_keyset_and_groups_evidence` 初始失败，证明 repository 没有批量 evidence reader。
- RED：`test_token_resolution_refresh_batches_evidence_reads_for_reprocess_intents` 初始失败，证明架构守护能抓到旧 per-intent 调用。
- GREEN：新增三项 focused 测试通过；更宽的 token resolution/source-width 非集成组通过，`65 passed`。
- Targeted static 通过：相关 Token Resolution Refresh service/repository/test/architecture ruff clean，service + repository mypy clean。
- SDD/static gate 通过：`validate_sdd_artifacts.py`、`regen_sdd_work_index.py --check`、`git diff --check` 均 clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root432 - Search OR-symbol 目标解析按 token 循环查询，公开读路径成本被用户输入放大

发现：

- `SearchService._resolve_target_candidates(...)` 会识别 `btc OR eth` 这类 OR-symbol 查询。
- 旧实现对 `or_symbols` 中每个 symbol 构造一个 `symbol_intent`，再调用一次 `self.search_query.resolve_targets(symbol_intent)`。
- `SearchEventsQuery.resolve_targets(...)` 对单 symbol 会读 `cex_tokens`、`registry_assets`、`asset_identity_current`，所以一个公开 Search 请求可被用户输入 token 数放大成 N 次目标解析 SQL。

根因：

- Root258 已经把 Search 的 `limit/scope/window` 边界从 read service 默认值移到 API/CLI caller，但只治理了“查询窗口多大”，没有治理“输入集合怎样进入 PostgreSQL”。
- 成熟 CQRS read path 的输入集合应先转成数据库 keyset，由一条 SQL 处理排序、去重、ambiguity 计算；否则 Python 层循环会把同一个 read-model contract 拆成多次 round trip。
- PostgreSQL 最佳实践上，CEX token 和 Asset identity 的候选解析可以共享 `unnest(%s::text[]) WITH ORDINALITY` keyset，让 planner 看见完整输入集合；逐 symbol 调 reader 则让数据库无法整体规划，并把公开请求延迟与 token 数线性绑定。

修复：

- `SearchService._resolve_target_candidates(...)` 对 OR-symbol 查询改为一次调用 `self.search_query.resolve_symbols(or_symbols)`。
- `SearchEventsQuery.resolve_symbols(symbols)` 新增批量 SQL：
  - `input_symbols` 使用 `unnest(%s::text[]) WITH ORDINALITY` 保留输入顺序。
  - `distinct_symbols` 在 PostgreSQL 内去重。
  - CEX 与 Asset candidates 在同一条 SQL 中 union。
  - Asset ambiguity 用 `COUNT(*) OVER (PARTITION BY distinct_symbols.symbol)` 计算，语义等价于单 symbol resolver。
- 架构守护禁止 `for symbol in or_symbols` + `resolve_targets(symbol_intent)` 回归，并要求 keyset SQL markers。

验证：

- RED：`test_search_routes_symbol_or_query_to_targets` 初始失败，证明服务层没有 batch symbol call。
- RED：`test_resolve_symbols_batches_symbol_targets_with_keyset_sql` 初始失败，证明 repository 没有批量 symbol reader。
- RED：`test_search_or_symbol_resolution_uses_batched_keyset_sql` 初始失败，证明架构守护能抓到旧 per-symbol loop。
- GREEN：focused Search service/repository/architecture 命令通过，`3 passed`。
- 非集成组合验证通过：Search service/query/inspect + 相关架构守护，`21 passed`。
- Targeted static 通过：相关 Search read service/query/test/architecture ruff clean，read service + query mypy clean。
- SDD/static gate 通过：`validate_sdd_artifacts.py`、`regen_sdd_work_index.py --check`、`git diff --check` 均 clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root433 - Narrative selected-post semantics hydration 对每个 post 单独查历史语义

发现：

- `NarrativeReadModel.hydrate_target_posts(...)` 会在 Token Case / Search Inspect 的 selected posts 上调用 `repository.semantics_for_posts(posts, ...)`。
- 旧 `NarrativeRepository.semantics_for_posts(...)` 虽然方法签名接收一批 posts，但内部对每个 post 执行一次 `SELECT ... FROM token_mention_semantics ... ORDER BY ... LIMIT 1`。
- 这让一个已分页的 post detail read 继续扩展成 P 次 SQL；页面越大，历史语义 hydration 的 round trip 越多。

根因：

- 前面的 Narrative hard cut 关注的是移除 runtime LLM worker、旧 digest/semantic processing backlog、API identity shim，保证历史 semantics 只是 read-only context。
- 但“历史 context 不再是 worker 队列”并不自动意味着读成本已经 bounded。repository 方法保留了单 post reader 的实现习惯，只是在外层暴露了 batch 方法名。
- 成熟 CQRS 读路径应把已选择的 post page 作为 keyset 交给 PostgreSQL，使用 lateral latest-row probe 取每个 post 最新语义；应用层不应该把一个 bounded page 再拆成 P 个 DB round trip。

修复：

- `NarrativeRepository.semantics_for_posts(...)` 将 selected posts materialize 成 parallel arrays：`event_id[]`、`target_type[]`、`target_id[]`。
- SQL 使用 `unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY` 构造 `input_posts`，再用 `distinct_posts` 去重并保留首次输入顺序。
- 对每个 distinct post 使用 `LEFT JOIN LATERAL (...) ORDER BY computed_at_ms DESC NULLS LAST, queued_at_ms DESC NULLS LAST LIMIT 1` 取最新 semantic row。
- 架构守护禁止 `for post in posts` + per-post `token_mention_semantics` 查询回归。

验证：

- RED：`test_semantics_for_posts_batches_post_keyset_with_lateral_latest` 初始失败，证明 repository 仍在 loop 里 `.fetchone()`。
- RED：`test_narrative_post_semantics_hydration_uses_batched_keyset_sql` 初始失败，证明架构守护能抓到旧 per-post SQL。
- GREEN：focused Narrative semantics repository/architecture 命令通过，`2 passed`。
- 非集成组合验证通过：Narrative repository SQL contract + read model + 相关架构守护，`34 passed`。
- Targeted static 通过：相关 Narrative repository/read-model/test/architecture ruff clean，repository mypy clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root434 - Signal Pulse notification 候选发现复用 public-list 分页，worker SQL 成本被 scope/status/page 放大

发现：

- `NotificationRuleEngine._signal_pulse_candidates(...)` 已经从正式 `settings.notifications` 读取 window、scopes、statuses、candidate limit 和 page budget。
- 但旧实现仍按 `for scope in scopes`、`for status in statuses`、`for page in signal_pulse_max_pages` 调用 `self.pulse.list_candidates(...)`。
- `list_candidates(...)` 是 public Signal Pulse 列表读接口；把它拿来做 worker notification candidate discovery，会让一次 `notification_rule` 评估变成 `S * T * P` 次公开列表 SQL。

根因：

- Root181/182/253 已经把 Signal Pulse notification 的查询参数从服务层常量移到正式配置，但只治理了“预算从哪里来”，没有治理“预算怎样进入数据库”。
- 成熟 Kappa/CQRS worker 发现候选时，应把配置好的 scope/status 集合作为 read-side keyset 交给 PostgreSQL，一次性完成过滤、排序和每组限额；不应复用 public cursor pagination API 来模拟 worker 扫描。
- PostgreSQL 最佳实践上，每个 scope/status bucket 的上限应由 `ROW_NUMBER() OVER (PARTITION BY scope,status ...)` 在一条 SQL 内完成。应用层三重循环会增加 round trip、重复 planner 成本，并让 worker idle/周期成本随配置维度膨胀。

修复：

- `NotificationRuleEngine._signal_pulse_candidates(...)` 改为一次调用 `PulseReadRepository.list_signal_pulse_notification_candidates(...)`。
- 新增 `PulseReadRepository.list_signal_pulse_notification_candidates(...)`：
  - `input_scopes` 使用 `unnest(%s::text[]) WITH ORDINALITY` 保留配置顺序。
  - `input_statuses` 使用 public status / display status parallel arrays，保持状态映射显式。
  - SQL 在 `pulse_candidates` 上一次过滤 window、scope、display status、`pulse_status` 和 `evidence_packet_hash`。
  - `ROW_NUMBER() OVER (PARTITION BY input_scopes.scope, input_statuses.public_status ORDER BY updated_at_ms DESC, candidate_id DESC)` 控制每个 scope/status bucket 的候选预算。
- 架构守护禁止 Signal Pulse notification 再通过 `list_candidates(...)`、cursor 或 page loop 做候选发现。

验证：

- 初次 focused run 在测试契约更新后失败，暴露默认 Signal Pulse 规则包含 `all` 与 `matched` 两个 scope，测试断言低估了正式配置。
- GREEN：Notification/Pulse focused command 通过，`8 passed`。
- 已新增 repository SQL 合约测试，证明候选发现使用单条 keyset/window SQL。
- 已新增架构守护，禁止 worker rule 回退到 public-list cursor pagination。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root435 - Watched-account activity 时间窗口只在服务层过滤，没有下推 PostgreSQL

发现：

- `NotificationRuleEngine._watched_account_activity(...)` 会计算 `since_ms = now_ms - watched_activity_window_ms`。
- 旧实现调用 `self.evidence.recent_events(limit=..., watched_only=True)`，然后在 Python 层用 `received_at_ms < since_ms` 跳过旧事件。
- `EvidenceRepository.recent_events(...)` 没有 `since_ms` 参数，因此 SQL 只能读“最近 N 条 watched events”，而不是“窗口内 watched events”。

根因：

- Root252 已经把 watched-account activity window 从服务层常量移到正式配置，但没有把这个时间窗口变成 PostgreSQL predicate。
- 这会造成两个问题：第一，数据库无法利用 `received_at_ms` 谓词缩小扫描范围；第二，如果最近 N 条 watched events 中混入很多窗口外事件，窗口内但排序更靠后的候选可能被 limit 截断前就丢失。
- 成熟 CQRS/worker read path 的窗口语义应该尽早下推到 read repository；服务层可以保留防御性判断，但不能把核心时间窗口只放在 Python 过滤里。

修复：

- `NotificationRuleEngine._watched_account_activity(...)` 调用 `EvidenceRepository.recent_events(...)` 时传入 `since_ms`。
- `EvidenceRepository.recent_events(...)` 新增可选 `since_ms` 参数，并在 SQL `WHERE` 中加入 `e.received_at_ms >= %s`。
- 架构守护要求 notification rule code 保留 `since_ms=since_ms`，repository 单测证明 SQL shape 包含 `e.received_at_ms >= %s`。

验证：

- GREEN：focused watched-activity / EvidenceRepository / architecture 命令通过，`3 passed`。
- 更宽非集成组合通过：Notification rules + EvidenceRepository + notification architecture，`93 passed`。
- Targeted static 通过：相关 Notification/Evidence 生产与测试文件 ruff clean，生产文件 mypy clean。
- SDD/static gate 通过：`validate_sdd_artifacts.py`、`regen_sdd_work_index.py --check`、`git diff --check` 均 clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root436 - Watched-account token alert 没有使用 notification worker 的显式评估时钟

发现：

- Root251 已要求 `NotificationRuleEngine.evaluate(now_ms=...)` 使用显式 worker-run 时钟，避免 rule service 自己读墙钟。
- 但 `_watched_account_token_alerts(...)` 旧实现调用 `AccountAlertService.account_alerts(window="1h", limit=...)` 时没有传 `now_ms`。
- `SignalRepository.account_alerts(...)` 因此会在 repository 内部用 `_now_ms()` 计算 alert window。这样同一次 notification worker evaluation 里，watched activity / Signal Pulse / News 使用 worker `now_ms`，而 watched token alert 使用 repository wall clock。

根因：

- 前面的显式时钟治理只切断了 `NotificationRuleEngine` 自己的 `_now_ms()` fallback，没有继续追到下游 read service。
- Kappa/CQRS worker 的一个周期应有一个可复现的 evaluation timestamp；窗口谓词必须来自这个输入，而不是让 repository 在深层重新决定当前时间。
- 否则测试、回放、慢 worker 周期、批量处理和真实生产时间之间会出现细微漂移：同一批候选的窗口边界不是同一个时刻。

修复：

- `AccountAlertService.account_alerts(...)` 改为要求显式 `now_ms`。
- `NotificationRuleEngine._watched_account_token_alerts(...)` 传入 worker evaluation `now_ms`。
- `/api/notifications/account-alerts` 和 CLI `account-alerts` 也在 surface 边界传入当前时间，保持 API/CLI 是时钟 owner，而不是 repository。
- 架构守护要求 watched-account token alert section 保留 `now_ms=now_ms`。

验证：

- GREEN：focused account-alert explicit-clock 命令通过，`4 passed`。
- 更宽非集成组合通过：AccountAlertService + Notification rules + notification architecture + API/CLI 相关单测，`116 passed`。
- Targeted static 通过：相关 AccountAlert/Notification/API/CLI 文件 ruff clean，生产文件 mypy clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root437 - WebSocket token replay 仍按每个 token filter 单独查询 recent events

发现：

- Root426 已经限制了 `/ws` subscribe 的 replay 上限、filter 总数和 per-filter replay budget。
- Root427 也把 replay payload hydration 改成了 page-level batch，不再对每个 event 单独读 entities / alerts / intents / token resolutions。
- 但 token-filter replay 分支仍然对每个 CA 和 symbol 调一次 `EvidenceRepository.recent_events(...)`，也就是一个 subscribe replay 仍会产生 `C + S` 次 recent-event SQL。

根因：

- Root426 的“预算下切”只是阻止每个 filter 都跑完整 replay limit，但没有把 token filter 集合变成 PostgreSQL keyset。
- 成熟 CQRS 读路径的 filter 集合应在 repository 边界一次性进入 SQL，由数据库做去重、排序和每组限额；应用层循环调用单-filter reader 仍然把 public read cost 绑定到用户输入数量。
- PostgreSQL 最佳实践上，CA/symbol filters 可以通过 `unnest(... WITH ORDINALITY)` materialize 成 keyset，再用 `ROW_NUMBER() OVER (PARTITION BY filter_kind, filter_chain, filter_value ...)` 保留 per-filter bucket budget。这样 replay 的查询预算由一个 SQL 和显式 bucket limit 决定，而不是由 filter 数产生多次 round trip。

修复：

- `PublicWebSocketHub._replay_events(...)` 对 token filters 改为一次调用 `repos.evidence.recent_events_for_token_filters(...)`。
- `EvidenceRepository.recent_events_for_token_filters(...)` 新增单条 keyset/window SQL：
  - `input_filters` 使用 `unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY` 表达 CA/symbol filter 集合。
  - `distinct_filters` 在 PostgreSQL 内去重。
  - CA filter 保留 `evm_unknown` 扩展到 `EVM_QUERY_CHAINS` 的既有语义。
  - `ROW_NUMBER() OVER (PARTITION BY filter_kind, filter_chain, filter_value ...)` 在 SQL 内限制每个 filter 的 replay bucket。
  - 最终按 `received_at_ms DESC, event_id DESC` 去重排序并应用总 replay limit。
- 公共合同、可靠性文档和 worker 设计说明都从“per-filter query budget”更新为“single token-filter keyset/window query”。

验证：

- RED：focused WebSocket/Evidence/architecture 命令初始失败，证明旧实现对四个 symbol 发了四次 `recent_events(...)`，repository 没有 `recent_events_for_token_filters(...)`，静态 guard 抓到 per-filter loop。
- GREEN：同一 focused 命令通过，`3 passed`。
- 新增 EvidenceRepository SQL shape 测试，要求 `input_filters`、`distinct_filters`、`ROW_NUMBER() OVER` 和 `event_rank <= %s` markers。
- 新增 architecture guard，禁止 `/ws` token replay 回到 `for chain, ca in client.cas` / `for symbol in client.symbols` 的 per-filter query 形态。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root438 - Pulse policy evaluator radar rows 按 window/scope 发 12 次 SQL

发现：

- `pulse_policy_evaluator.fetch_candidate_rows(...)`、`fetch_run_rows(...)` 和 `fetch_job_rows(...)` 都已经把 `EVALUATED_WINDOWS` / `EVALUATED_SCOPES` 作为数组 keyset 交给 PostgreSQL。
- 但 `fetch_radar_rows(...)` 仍然在 Python 里对 4 个 window 和 3 个 scope 做双层循环，每组调用一次 `token_radar_current_rows` + `token_radar_publication_state` 查询。
- 结果是一次 Pulse policy evaluation 固定产生 12 次 radar-current SQL 读，虽然这些读本质上共享同一 projection_version、venue、ready publication state 和时间窗口谓词。

根因：

- 这不是 worker writer 的事实链路错误，而是 ops/evaluation read surface 的 SQL 预算漂移：评估维度被当成应用层循环，而不是数据库 keyset。
- 成熟 CQRS 读模型的原则是：读端可以做分析和对照，但查询预算必须由显式 keyset、窗口谓词和 limit 决定；不能让 window/scope 组合数自然变成 round trip 数。
- PostgreSQL 最佳实践上，这里不需要 12 条 SQL。`window = ANY(%s)` 和 `scope = ANY(%s)` 足以表达同一个有界 evaluated grid，并让 planner 在一次 join/filter/order 内处理 ready publication state。

修复：

- `fetch_radar_rows(...)` 改为单条 `token_radar_current_rows` 查询：
  - `token_radar_current_rows."window" = ANY(%s)`。
  - `token_radar_current_rows.scope = ANY(%s)`。
  - 保留 `state.latest_attempt_status = 'ready'` 和 published-at window gate。
  - 继续禁止用 `state.current_generation_id = token_radar_current_rows.generation_id` 作为 serving gate。
  - 排序改为 `window, scope, rank`，让一个 keyset 查询的返回顺序稳定。
- 单测 FakeConn 改成模拟一次 window/scope keyset 查询，防止旧的逐 window/scope 分支继续被测试替身默默支持。
- 新增 architecture guard，禁止 `fetch_radar_rows(...)` 回到 `for window in EVALUATED_WINDOWS` / `for scope in EVALUATED_SCOPES` 和单值 `= %s` 形态。

验证：

- RED：focused Pulse policy evaluator 命令初始失败，单测显示 `token_radar_current_rows` 被查询 12 次，architecture guard 抓到双层循环和单值 window/scope SQL。
- GREEN：同一 focused 命令通过，`2 passed`。
- 更宽非集成组合通过：Pulse policy evaluator 单元文件 + 新 architecture guard，`11 passed`。
- Targeted static 通过：相关 production/query/test 文件 ruff clean，生产 query 文件 mypy clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root439 - Projection validation audit 按 Token Radar sample 行逐个查 intent/asset

发现：

- `ProjectionValidationAudit.run(...)` 先从 `token_radar_current_rows` 取 sample rows。
- 随后对每一行分别执行 `SELECT 1 AS ok FROM token_intents WHERE intent_id = %s`。
- 当 row 的 `target_type = 'Asset'` 时，又逐行执行 `SELECT 1 AS ok FROM registry_assets WHERE asset_id = %s`。
- 最后再单独查询 `MAX(computed_at_ms)` 判断 projection 是否存在。
- 因此 `ops validate-projections --sample N` 的 SQL round trip 数量会变成 `1 + N + asset_rows + 1`，sample 越大，诊断成本越高。

根因：

- 这不是事实写入链路错误，而是 ops validation read surface 把“集合引用完整性校验”写成了应用层逐行 probe。
- 成熟 Kappa/CQRS 的运维诊断可以采样，但采样后的 referential check 应该在 PostgreSQL 内通过 join/aggregate 一次完成；否则诊断命令本身会成为大表/高 sample 场景下的负载来源。
- PostgreSQL 最佳实践上，sample keyset、intent 引用、asset 引用和 latest freshness 都能在一个 CTE 查询里表达。`LEFT JOIN` 找缺失引用，`COUNT(*) FILTER` 计算 mismatch bucket，应用层只消费聚合结果。

修复：

- `ProjectionValidationAudit.run(...)` 改为单条 SQL：
  - `sampled_radar_rows` CTE 负责从 `token_radar_current_rows` 取有界 sample。
  - `reference_counts` CTE 通过 `LEFT JOIN token_intents` 和 `LEFT JOIN registry_assets` 校验引用。
  - `COUNT(*) FILTER` 分别统计 missing intent 和 missing asset。
  - `latest_radar` CTE 同条查询内计算 `MAX(computed_at_ms)`。
- `checked_count` 和 `mismatch_count` 直接来自 PostgreSQL 聚合，不再由 Python 逐行累加。
- 新增单元 fake connection 记录 SQL 形状，证明只执行一条 sampled reference SQL。
- 新增 architecture guard，禁止 `for row in radar_rows` 和 per-row `SELECT 1` 引用 probe 回归。

验证：

- RED：focused ProjectionValidationAudit 命令初始失败，单测没看到 `WITH sampled_radar_rows AS`，architecture guard 抓到逐行 intent/asset probe。
- GREEN：同一 focused 命令通过，`2 passed`。
- 更宽非集成组合通过：Postgres audit 单元文件 + 新 architecture guard，`2 passed`。
- Targeted static 通过：相关 production/audit/test 文件 ruff clean，`postgres_audit.py` mypy clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root440 - News item-process source watermark 用 runtime now 兜底缺失事实时间

发现：

- `NewsItemProcessWorker` 在处理 `news_items` 后会 enqueue page reprojection 和 item brief dirty targets。
- Dirty target 的 `source_watermark_ms` 原来来自 `_source_watermark_ms(processed_item, fallback_ms=now)`。
- `_source_watermark_ms(...)` 会优先取 `fetched_at_ms` / `published_at_ms`，但当两者都缺失或非法时直接返回 worker runtime `now`。
- 这会把一个缺少事实时间的 item 排成“刚刚发生”的 dirty work，影响 `news_projection_dirty_targets` 的 source-watermark 排序/覆盖语义。

根因：

- 这是典型的事实时间和处理时间混淆。`published_at_ms` / `fetched_at_ms` 是 provider/news item 的 persisted source time；`now_ms` 是 worker 处理时钟。
- 成熟 Kappa/CQRS 的 read-model dirty watermark 应该来自可重放事实，而不是运行时处理时间。否则相同 PostgreSQL 事实在不同重试时间会产生不同的 dirty ordering，难以解释也难以重放。
- 真实 `NewsRepository` 已经在 canonical item 写入时把缺失 `published_at_ms` 规范化为 `fetched_at_ms`；因此 worker 的 runtime-now fallback 不是必要容错，而是测试/fake 层遗留的兼容兜底。

修复：

- `_source_watermark_ms(...)` 删除 `fallback_ms` 参数。
- 缺少正数 `fetched_at_ms` 和 `published_at_ms` 时抛出 `news_item_process_source_watermark_required[:news_item_id]`，让 item-process 走现有 retry/terminal 状态机。
- `enqueue_page_reprojection(...)` 和 `enqueue_item_brief_work(...)` 的 source watermark 均只从 persisted item time 计算。
- 成功路径测试 fixture 补充 `published_at_ms`，不再靠 worker runtime now 隐式通过。
- News domain 架构文档声明 item-process dirty targets 必须从 persisted `news_items.published_at_ms` / `fetched_at_ms` 取 source freshness。
- 新增 architecture guard，禁止 `fallback_ms` 和 `_source_watermark_ms(processed_item, fallback_ms=now)` 回归。

验证：

- RED：focused News item-process watermark 命令初始失败，单测发现 helper 仍暴露 `fallback_ms`，architecture guard 抓到 runtime-now fallback。
- GREEN：同一 focused 命令通过，`2 passed`。
- 更宽非集成组合通过：News worker 单元文件、事务 dirty target 测试和新 architecture guard，`42 passed`。
- Targeted static 通过：相关 worker/test/architecture 文件 ruff clean，`news_item_process_worker.py` mypy clean。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root441 - News page `latest_at_ms` 用 projection `computed_at_ms` 补事实时间

发现：

- `build_news_page_row(...)` 原来把页面 row 的 `latest_at_ms` 写成 `int(item.get("published_at_ms") or computed_at_ms)`。
- 当投影输入缺少 `published_at_ms` 或该值非法时，页面排序时间会退回到 page projection 的计算时间。
- 这条路径和 Root440 属于同一类问题：缺失 source fact 被运行时钟伪装成“刚发生”。

根因：

- `latest_at_ms` 是 public News page 的服务排序/新鲜度字段，应描述 canonical item 的事实时间，而不是投影重算发生的时间。
- 成熟 Kappa/CQRS 中，current read model 的内容字段必须由可重放事实决定；`computed_at_ms` 可以记录投影运行元数据，但不能参与业务排序语义。
- 真实 `NewsRepository.upsert_news_item(...)` 已经把缺失 provider published time 规范化为 canonical `published_at_ms=fetched_at_ms`，且 `news_items.published_at_ms` 是 NOT NULL；因此 page projection 的 `computed_at_ms` fallback 是测试/fake/旧形状残留，不是生产必需兼容。

修复：

- `latest_at_ms` 改为 `_item_published_at_ms(item)`，只接受正数 canonical `published_at_ms`。
- 缺少或非法 `published_at_ms` 时抛出 `news_page_projection_published_at_required[:news_item_id]`，让 page projection dirty target 走现有 error/retry/terminal 路径。
- 新增单测证明 `fetched_at_ms` 和 `computed_at_ms` 都不能覆盖 canonical `published_at_ms`，以及缺失 published time 会 fail closed。
- 新增 architecture guard，禁止 `item.get("published_at_ms") or computed_at_ms` 回归。
- News domain 架构文档声明 page-row `latest_at_ms` 只能来自 canonical projected item `published_at_ms`。

验证：

- 聚焦命令通过：News page projection 两个单测 + architecture guard，`3 passed`。
- 更宽非集成组合通过：完整 `test_news_page_projection.py` + `test_news_intel_boundaries.py`，`27 passed`。
- Targeted static 通过：相关 production/test 文件 ruff clean，`news_page_projection.py` mypy clean。
- Docker Compose 配置校验通过；`make docker-up` 已越过 `parallax config` 初始化，但在访问本机 Docker daemon socket `/Users/qinghuan/.docker/run/docker.sock` 时被系统拒绝，属于当前环境权限阻塞而不是 Compose 配置解析失败。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root442 - Token Image Mirror 失败源没有正式 retry budget 和终态阻断

发现：

- `TokenImageMirrorWorker` 的失败路径已经把 `token_image_source_dirty_targets` 交给 repository `mark_error(...)` 处理，并读取 `self.settings.max_attempts`。
- 但正式 `TokenImageMirrorWorkerSettings` 和默认 `workers.yaml` 模板没有 `max_attempts` 字段；单测 fake settings 临时带了该字段，所以真实 settings 启动路径反而更容易暴露问题。
- 对坏 provider logo URL，如果只做 retry/update 而没有 exhausted terminal ledger 和 re-admission 阻断，同一个 `source_url_hash:target_type:target_id` 会被 Token Profile projection 反复重新放回 dirty queue。

根因：

- 这是 worker 运行时实现、正式配置面、控制面状态机三者脱节。成熟 Kappa/CQRS 里，retry cadence、retry budget、terminal ledger 都是可审计的控制面事实，不能只存在于 worker fake 或隐式对象属性上。
- `retry_ms` 决定“下一次什么时候试”，`max_attempts` 决定“什么时候承认这条输入不可继续自动处理”。二者混在一起会造成 backlog 看起来只是延迟，实际是坏源无限再入队。
- `token_image_source_dirty_targets` 是控制面队列，不是事实源。耗尽重试后应该删除 claim 并写 `worker_queue_terminal_events`，让 operator action 成为恢复入口，而不是让 profile projection 下一轮又自动补回同一条坏任务。

修复：

- `TokenImageMirrorWorkerSettings` 新增正式 `max_attempts: int = Field(default=3, ge=1)`，默认 workers YAML 同步输出 `token_image_mirror.max_attempts: 3`。
- `TokenImageSourceDirtyTargetRepository.mark_error(...)` 按 claimed-row `attempt_count` 与正式 `max_attempts` 分类：未耗尽则按 `retry_ms` 释放重试，耗尽则 CAS 删除源 dirty row，并在同一连接事务里写 `worker_queue_terminal_events`。
- terminal target key 固定为 `source_url_hash:target_type:target_id`，payload hash、lease owner、attempt count 都来自 claimed row，不重新计算或补默认值。
- Token Profile image-source admission 查询 unresolved terminal events；同一个 image source target 在 operator resolve 之前不会被再次 enqueue。
- CLI queue retry 支持 `token_image_mirror` / `token_image_source_dirty_targets`，保留人工解除终态后的恢复入口。

验证：

- 聚焦命令通过：正式 workers 默认值、exhausted terminalization、image mirror worker/source admission/profile current、architecture settings contract，`28 passed`。
- 更宽非集成组合通过：image-source dirty repository、image mirror worker、source admission、profile current、CLI queue ops、bootstrap wiring、worker settings，`78 passed`。
- Architecture guard 通过：image-source dirty connection transaction、rowcount evidence、TokenImageMirror formal settings contract，`3 passed`。
- Targeted ruff/mypy、SDD validation、`git diff --check`、`docker compose config --quiet` 通过。
- `make docker-up` 已越过 `parallax config` 初始化并确认使用 `/Users/qinghuan/.parallax/config.yaml` 与 `/Users/qinghuan/.parallax/workers.yaml`，但访问 `/Users/qinghuan/.docker/run/docker.sock` 被当前宿主环境拒绝，属于 Docker daemon 权限阻塞，不是 Compose 配置解析或应用配置失败。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root443 - Binance CEX profile sync 接受 object/dict 双形态并把缺失 raw payload 写成空 JSON

发现：

- `sync_cex_token_profiles(...)` 原来通过 `_field(profile, key)` 同时支持 `dict.get(...)` 和 `getattr(...)`。
- 同一服务还把缺失 `provider` 补成 `binance_cex_profile`，把缺失 `symbol` 补成 `base_symbol`，并把缺失或非 dict 的 `raw_payload` 写成 `{}`。
- `CexTokenProfileRepository.upsert_ready_profile_if_token_exists(...)` 也接受 `raw_payload=None` 并通过 `raw_payload or {}` 写入 `cex_token_profiles.raw_payload_json`。

根因：

- CEX profile source cache 是后续 Token Profile 当前投影和 image-source admission 的 persisted source，不是临时 provider helper。进入 `cex_token_profiles` 之前，provider 输出必须已经是正式、可审计、可重放的记录。
- object/dict 双形态反射让 provider adapter 的正式输出契约不可见：一个测试 fake 或旧对象只要有同名属性就能绕过 adapter 规范化，形成第二套输入语言。
- 空 raw payload 更危险：它把“provider 输出缺失审计载荷”的事实伪装成一个合法但信息量为零的 source-cache row。成熟 Kappa/CQRS 里，raw provider payload 是审计输入，不是业务事实，但它必须能解释事实来源；缺失时应 fail closed，而不是写空 JSON。

修复：

- `sync_cex_token_profiles(...)` 先在事务外把 provider rows materialize 成正式 Mapping 记录，必填 `base_symbol`、`provider`、`symbol`、`logo_url`、`source_ref`、mapping-shaped `raw_payload`。
- object-attribute profile、缺 provider、缺 symbol、无效 logo URL、缺 source ref、缺/非 Mapping raw payload 都在打开 DB transaction 前失败。
- `CexTokenProfileRepository` 写 SQL 前要求 mapping-shaped raw payload；不再把 `None`、list、字符串等输入写成 `{}`。
- Asset Market 架构、Worker Flow、Workers inventory 和 architecture guard 同步禁止 object-reflection、provider/symbol fallback、empty raw-payload fallback 回归。

验证：

- 聚焦非集成命令通过：CEX sync unit、CEX profile repository unit、runtime worker architecture contract，`149 passed`。
- Targeted ruff 通过：CEX sync/repository、对应 unit、architecture guard clean。
- Targeted mypy 通过：`cex_token_profile_sync.py` 与 `cex_token_profile_repository.py` 无问题。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root444 - Token Profile Current 写侧仍接受旧 JSON 字段别名

发现：

- `project_token_profile_current(...)` 原来构造 current row 时输出 `quality_flags` 和 `source_payload`。
- `TokenProfileCurrentRepository.upsert_current(...)` 又通过 `row.get("quality_flags_json", row.get("quality_flags", []))` 和 `row.get("source_payload_json", row.get("source_payload", {}))` 同时接受正式字段和旧别名。
- 这导致 projection 服务、worker fake、仓储输入之间存在两套 row 语言：即使缺失正式 `quality_flags_json` / `source_payload_json`，仓储也会用旧别名或空 JSON 继续写 public `token_profile_current`。

根因：

- Root323 已经把 public `TokenProfileReadModel` 收紧为 formal current-row contract，但写侧仍保留旧别名兼容，形成“读侧严格、写侧宽松”的断层。
- 对成熟 Kappa/CQRS 来说，`token_profile_current` 是 public current read model，字段名就是投影和存储的合同；兼容别名会让坏投影输入被仓储洗白，破坏单 writer 可审计性。
- 空 flags/payload fallback 尤其危险：它把“投影没有提供 source payload / quality flags”的错误伪装成“来源干净且无审计载荷”，后续 payload hash 和 unchanged-row 判断都会建立在被修补后的假内容上。

修复：

- Token Profile Current projection ready/status rows 改为直接输出 `quality_flags_json` 和 `source_payload_json`。
- `TokenProfileCurrentRepository.upsert_current(...)` SQL 前要求正式 JSON 字段存在，`quality_flags_json` 必须是 list，`source_payload_json` 必须是 Mapping；缺失或错类型分别抛 `token_profile_current_repository_required:*` / `token_profile_current_repository_invalid:*`。
- 单测覆盖缺失字段、错类型字段和旧 `quality_flags` / `source_payload` 别名输入，确认失败发生在 SQL 前。
- Architecture guard 禁止仓储恢复 `row.get("quality_flags_json", row.get("quality_flags"...))`、`row.get("source_payload_json", row.get("source_payload"...))` 或旧别名读取。

验证：

- 聚焦非集成命令通过：Token Profile Current projection/repository/worker 组合和新 architecture guard，`57 passed`。
- Targeted ruff 通过：projection/repository、对应 unit、architecture guard clean。
- Targeted mypy 通过：`token_profile_current_projection.py` 与 `token_profile_current_repository.py` 无问题。
- SDD 校验、SDD index check、`git diff --check`、`docker compose config --quiet` 通过。
- `make docker-up` 触发显式 `docker-check` 前置检查后失败，原因是当前 shell 不能访问 Docker daemon；这是环境权限阻塞，不是 Compose 或应用配置解析失败。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root445 - Token Radar 下游 dirty target 用 projection computed_at 补 source watermark

发现：

- `_pulse_trigger_target(...)`、`_narrative_admission_target(...)` 和 `_token_profile_current_target(...)` 原来都通过 `int(row.get("source_max_received_at_ms") or computed_at_ms)` 计算下游 `source_watermark_ms`。
- 这意味着 Token Radar current row 一旦缺失正式 `source_max_received_at_ms`，下游 Pulse Trigger、Narrative Admission、Token Profile Current dirty queue 仍会被写入一个看似有效的水位。
- 该水位来自 projection 运行时的 `computed_at_ms`，不是源事件、市场事实或 current row source frontier。

根因：

- 这是事实时间和处理时间混用。`source_watermark_ms` 是下游消费者判断 catch-up、去重、排序和 freshness 的事实源前沿；`computed_at_ms` 只是投影本次运行的处理元数据。
- 在成熟 Kappa/CQRS 里，下游 dirty target 的 watermark 必须可追溯到 material facts 或正式 current row source frontier。用 projection 时间补洞会把“投影输入 malformed”伪装成“源事实刚刚更新”，让下游 worker 产生错误的新鲜度判断。
- 更深一层，这是兼容性兜底残留：为了让 dirty fan-out 不因旧 row 形态中断，代码把缺字段修补成 runtime time。但 current read model 的字段合同已经收紧后，这类兜底会反过来掩盖投影链路的坏输入。

修复：

- 新增 `_downstream_source_watermark_ms(row)`，只接受正整数 current-row `source_max_received_at_ms`。
- Pulse Trigger、Narrative Admission、Token Profile Current 三条下游 fan-out 全部改用该 helper。
- 缺失、0、负数、bool、字符串等非法 source watermark 都抛 `token_radar_downstream_source_watermark_required`，失败发生在 dirty target payload 构造前。
- Architecture guard 禁止 `int(row.get("source_max_received_at_ms") or computed_at_ms)` 回归；Token Intel、全局架构、Worker Flow、Workers inventory 和 SDD 同步写入该边界。

验证：

- RED：新增缺失 source watermark 单测时，三条 target builder 都没有抛错，`3 failed`，证明旧代码确实走了 `computed_at_ms` 兜底。
- GREEN：缺失/非法 source watermark、下游 fan-out 现有行为、payload hash 噪声隔离和 architecture guard 的聚焦组合通过，`22 passed`；完整 `test_token_radar_projection.py` 加 architecture guard 也通过，`188 passed`。
- Targeted ruff/mypy、SDD validation、SDD index check、`git diff --check`、`docker compose config --quiet` 通过。
- `make docker-up` 在当前 shell 仍会停在 `docker-check`，因为无法访问 Docker daemon socket；这属于环境权限阻塞，不是 Compose 配置或本次代码修复失败。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root446 - Token Profile Current dirty repository 继续用运行时间修补 source watermark

发现：

- `TokenProfileCurrentDirtyTargetRepository._source_watermark_ms(...)` 原来接受 tuple target，并在 mapping target 缺少 `source_watermark_ms` 时依次用 `computed_at_ms`、`updated_at_ms`、最终 `now_ms` 补水位。
- `token_profile_image_repair_targets(...)` 从 `token_profile_current.updated_at_ms` 读出 `source_watermark_ms` 后，又用 `row["source_watermark_ms"] or now_ms` 修补空值。
- `AssetProfileRefreshWorker` 和 `TokenImageMirrorWorker` 作为 profile-current dirty producer，也会把缺失的 claim/source watermark 补成运行时 `now_ms`。

根因：

- Root445 只修掉了 Token Radar producer 端的 `computed_at_ms` 兜底，但下游 Asset Market dirty repository 仍是宽入口。成熟 Kappa/CQRS 里，repository 是控制面事实入口，不应该把 malformed producer payload 洗白。
- `token_profile_current_dirty_targets.source_watermark_ms` 影响 claim 合并、payload hash、租约释放和 freshness 排序。用 `updated_at_ms` 或 `now_ms` 修补会把“队列/投影处理时间”伪装成“源事实新鲜度”，使后续 Token Profile Current worker 对 source frontier 的判断失真。
- tuple target 是更隐蔽的兼容面：它只有 identity，没有水位、priority、payload 语义。继续支持它等于允许 producer 绕过正式 dirty command 语言。

修复：

- `TokenProfileCurrentDirtyTargetRepository.enqueue_targets(...)` 现在只接受 mapping-shaped target，并要求正整数 `source_watermark_ms`。
- 缺失、tuple target、0、负数、bool、字符串等输入都在 SQL 前抛 `token_profile_current_dirty_target_source_watermark_required`。
- `token_profile_image_repair_targets(...)` 对 current-row source watermark 做同样正整数校验，缺失时抛 `token_profile_image_repair_source_watermark_required`，不再用 ops 运行时间补。
- Asset Profile Refresh 和 Token Image Mirror producer 改为传递 claim/source 自带水位；缺水位分别以 `asset_profile_refresh_source_watermark_required` 和 `token_image_mirror_profile_dirty_source_watermark_required` 暴露坏控制面输入。
- Asset Market 架构、全局架构、Worker Flow、Workers inventory、SDD 与 architecture guard 同步禁止 `computed_at_ms`、`updated_at_ms`、tuple identity 和 `now_ms` 水位兜底回归。

验证：

- RED：新增 dirty repository、ops image repair、architecture guard 后，当前实现分别出现 9 个 repository 失败、1 个 ops 失败、1 个 architecture 失败，证明旧代码确实会修补水位。
- GREEN：Token Profile Current dirty repository、ops projection dirty target、Asset Profile Refresh worker、Token Image Mirror worker、Token Profile hard-cut architecture 组合通过，`50 passed`。
- Targeted ruff/mypy 通过。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root447 - Token Image Source dirty enqueue 继续用 observed/updated/now 修补 source watermark

发现：

- `TokenImageSourceDirtyTargetRepository._target_records(...)` 原来会把缺失或 falsy 的
  `source_watermark_ms` 依次修补成 target-level `observed_at_ms`，最后修补成 enqueue
  时的运行时 `now_ms`。
- `image_source_candidates_for_target(...)` 的 `_source_watermark_ms(...)` 原来先读源行
  `observed_at_ms`，缺失时退到 `updated_at_ms`，再缺失时返回 `0`；随后 repository
  又会把这个 `0` 洗成 `now_ms`。
- 结果是 Token Profile Current 的图片 admission 可以把“源行没有事实观察时间”伪装成
  “刚刚有新事实到达”，并把坏水位写入 `token_image_source_dirty_targets`。

根因：

- Root446 收紧的是 profile-current dirty queue，但 Token Image Mirror 还有一条相邻的
  image-source dirty queue。两者都是控制面队列，`source_watermark_ms` 都承担事实前沿语义；
  只修 profile-current queue 会留下一个同类入口。
- `updated_at_ms` 是 source-cache 行的写入/处理时间，不是 provider logo URL 被观察到的事实时间。
  target-level `observed_at_ms` 也不是 dirty command 的正式字段。把这些值当作 source watermark
  会让控制面状态混入处理时间，破坏 Kappa/CQRS 中“事实时间”和“投影/队列运行时间”的分离。
- 更深层是兼容性宽入口残留：为避免历史 source row 缺字段导致 admission 中断，service 和
  repository 分别保留了 fallback。成熟的 CQRS 写入口不应该修补 malformed producer payload，
  而应该 fail closed，让上游事实缺口暴露出来。

修复：

- `TokenImageSourceDirtyTargetRepository.enqueue_targets(...)` 现在只接受正整数
  `source_watermark_ms`。
- 缺失、target-level `observed_at_ms`、0、负数、bool、字符串等输入都在 SQL 前抛
  `token_image_source_dirty_target_source_watermark_required`。
- `image_source_candidates_for_target(...)` 现在只从正整数 source-row `observed_at_ms` 生成
  image-source dirty watermark；缺失、`updated_at_ms` only、0、负数、bool、字符串都抛
  `token_image_source_admission_source_watermark_required`。
- Asset Market 架构、全局架构、Worker Flow、Workers inventory、SDD 与 architecture guard
  同步禁止 `updated_at_ms`、target-level `observed_at_ms`、runtime `now_ms` 水位修补回归。

验证：

- RED：新增 dirty repository、admission service、architecture guard 后，当前实现出现 `13 failed`，
  证明旧代码确实接受了缺失/非法水位并依赖兼容兜底。
- GREEN：同一聚焦命令转为 `14 passed`；Token Image Source dirty/admission/image mirror 非集成组
  通过，`69 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

### Root448 - Asset Profile Refresh target enqueue 继续用 updated/now 修补 source watermark

发现：

- `AssetProfileRefreshTargetRepository._target_records(...)` 原来通过
  `target.get("source_watermark_ms") or target.get("updated_at_ms") or now_ms`
  计算 `asset_profile_refresh_targets.source_watermark_ms`。
- `asset_profile_refresh_targets` 被 `AssetProfileRefreshWorker` claim 后，成功写入
  `asset_profiles` source cache 时会把 claimed `source_watermark_ms` 继续传入
  `token_profile_current_dirty_targets`。
- 这意味着刷新目标入队阶段如果没有正式 source watermark，仍会用 source-cache
  `updated_at_ms` 或运行时 `now_ms` 伪造一个看似有效的事实前沿，随后污染 Profile Current
  dirty queue。

根因：

- `asset_profile_refresh_targets` 是 profile source refresh 的控制面输入，不是单纯的调度表。
  它的 `source_watermark_ms` 表示触发刷新目标的上游事实前沿；`due_at_ms` 才是运行调度时间。
- 旧实现把 source watermark 和 queue/source-cache 更新时间混在一起，延续了“缺字段也尽量跑下去”的
  兼容性宽入口。成熟 Kappa/CQRS 中，控制面队列应暴露 malformed producer payload，而不是在
  repository 层把坏输入洗成新事实。
- Root446/447 已经收紧 profile-current 和 image-source dirty queue，但 Asset Profile Refresh
  仍是上游相邻入口；只收紧下游会留下一个继续制造伪水位的源头。

修复：

- 新增 `AssetProfileRefreshTargetRepository._source_watermark_ms(...)`，只接受正整数
  `source_watermark_ms`。
- 缺失、`updated_at_ms` only、0、负数、bool、字符串等输入全部在 SQL 前抛
  `asset_profile_refresh_target_source_watermark_required`。
- `now_ms` 只保留为 `due_at_ms` / `updated_at_ms` 调度与写入元数据，不再作为 source watermark
  兜底。
- Asset Market 架构、全局架构、Worker Flow、Workers inventory、SDD 与 architecture guard
  同步禁止 `updated_at_ms` 和 runtime `now_ms` 水位修补回归。

验证：

- RED：新增 Asset Profile Refresh target watermark 单测和 architecture guard 后，当前实现出现
  `7 failed` 单测加 `1 failed` 架构测试，证明旧代码会接受缺失/非法水位并继续执行 enqueue SQL。
- GREEN：同一聚焦命令转为 `8 passed`；Asset Profile Refresh 非集成组通过，`27 passed`。
- 按当前用户指令，本轮不运行 integration-heavy gate。

## 剩余风险和建议

1. 如果 Stocks Radar 需要真实 quote，必须新建 persisted quote fact/current read model，而不是恢复 request-time provider。
2. 如果 Notification Delivery 要支持更强并发/抢占，需要为 `notification_deliveries` 设计 lease/attempt token 或 CAS 终态写入。
3. 如果 Pulse 需要作者 handle 级查询，应新增 normalized author edge projection。
4. 如果 account-quality backfill 需要常态化运行，应新增 manifest worker、dirty target 和 bounded catch-up，而不是把 ops service 接回 API/read service。
5. 当前 integration suite 中 `macrodata bundle history` 被多次调用，是验证成本的大头。建议单独治理测试 fixture 或 mockable bundle boundary，但不要把 provider IO 混回 read path。
6. 最终完成前仍需在用户允许时跑完整 gate，或把 integration-heavy 部分拆成可接受的分段替代；当前用户指令下只记录轻量验证。

## 第一性判断

这次根修的原则是：不要为了让页面“现在看起来有数据”而牺牲事实链路、单 writer、可重放性和 PostgreSQL 可预测性。读路径宁可诚实返回 unavailable，也不要在 request path 偷偷补 provider IO；worker 宁可删除 helper，也不要保留第二套生命周期；SQL 宁可收窄语义，也不要把 JSONB expansion 变成公共查询合同。

这就是 KISS 在当前系统里的实际含义：少保留旧入口，少保留兼容兜底，把每条数据的来源、writer、生命周期和查询成本放回明确边界里。
