# Providers 边界与架构强制器加固 — 设计 Spec

**Status**: Draft
**Date**: 2026-05-10
**Scope**: 源码层（`src/gmgn_twitter_intel/`）的横切关注点边界与架构测试覆盖
**对齐参考**: OpenAI Harness Engineering（`docs/references/walkinglabs-harness-engineering.md` 已记 docs 那一波；本 spec 处理 src 这一波）

---

## 1. Background

`gmgn-twitter-intel` 已在 `2026-05-10-src-domain-package-restructure` 完成源码域化，落地了 forward-only 五层流水线（Types → Repo → Service → Runtime → UI），并以 AST 测试 `tests/test_src_domain_architecture.py` 机械化执行边界。

OpenAI Harness Engineering 在"分层 SOP"之外强调第二条机械化原则：**横切关注点（auth / connectors / telemetry / feature flags）必须经由单一显式的 Providers 接口进入业务域；其余路径一律禁止并由强制器拦截**。本 spec 处理这条原则在我们仓库中的落地，并把现有架构测试从"沉默断言"升级为"agent-friendly 修复指令"。

本 spec **不处理**：
- 域化重构本身（已完成）
- 文档治理（已在 `2026-05-09-harness-engineering-restructure` 完成）

---

## 2. Current Architecture Audit

### 2.1 已遵守的 SOP 项

| SOP 要求 | 我们的实现 | 强制器证据 |
|---|---|---|
| 顶层包白名单 | `app` / `domains` / `integrations` / `platform` | `tests/test_src_domain_architecture.py::test_root_package_contains_only_entry_shims` |
| `platform/*` 不依赖业务包 | `platform/{config,db,logging,paths}/` | `…::test_platform_does_not_import_domains_or_integrations_or_app` |
| 跨域必经 `interfaces.py` | 每域均有 `interfaces.py` | `…::test_cross_domain_imports_use_interfaces` |
| Repo 不向上依赖 | repo / queries 隔离 | `…::test_repositories_and_queries_do_not_import_services_or_runtime` |
| 原始 SQL 边界 | 仅限 repo / queries / `platform.db` / `app.runtime` | `…::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` |
| 旧扁平包 import 禁断 | LEGACY_PACKAGES 全屏蔽 | `…::test_no_business_modules_import_old_flat_packages` |

### 2.2 与 SOP 偏离的 Service↔横切渗漏点

证据（Service / Runtime 层直接 import 横切实现，违反"Service 只看 Provider"原则）：

| 违规位置 | 渗漏对象 | 渗漏类别 |
|---|---|---|
| `domains/evidence/services/ingest_service.py:30` | `platform.db.postgres_client.transaction` | 持久化交易语义 |
| `domains/social_enrichment/runtime/enrichment_worker.py:13` | `platform.db.postgres_client.transaction` | 持久化交易语义 |
| `domains/asset_market/services/asset_market_sync.py:7` | `integrations.okx.chains.OKX_CHAIN_TO_CHAIN_INDEX` | External connector 常量 |
| `domains/asset_market/runtime/token_discovery_worker.py:21` | `integrations.okx.chains.OKX_CHAIN_INDEX_TO_CHAIN` | External connector 常量 |
| `domains/pulse_lab/runtime/pulse_candidate_worker.py:32` | `integrations.openai_agents.pulse_thesis_agent_client.PulseThesisClientProtocol` | LLM client 抽象 |

**合规但相邻的现状**（不计入违规，列出避免误读）：

- `domains/notifications/repositories/notification_repository.py:10` import `platform.db.postgres_client.transaction` — repo 层允许，符合现有 SQL 边界规则
- `domains/notifications/services/notification_rules.py:9` 与 `domains/notifications/runtime/notification_delivery.py:13` import `platform.config.*` — Config 直 import 在本 spec §10 中明确保留，不视为违规

### 2.3 与 SOP 偏离的 enforcement 质量

| 当前状态 | 偏离 |
|---|---|
| 架构测试断言失败仅输出 `assert offenders == []` | OpenAI 范式要求"错误消息直接注入修复指令"，让 agent 一次改对。当前 agent 见到空 list 必须自行猜测语义。 |
| 无测试断言每域必须存在某些层（types / providers / services） | 域之间层级缺失（如 `account_quality` 仅有 repo + interfaces + read_models）无人挡。 |
| 无测试断言 Service / Runtime 层的 import 域 | §2.2 中的渗漏点全部是测试盲区。 |

---

## 3. Problem Diagnosis

### 3.1 横切关注点没有"单一入口"

外部 connector 与 `platform.db.transaction` 当前由各 domain 文件**直接 import**。后果：
- 替换具体 client（OKX → 它家 DEX）需 grep 全仓改 N 处
- Service 单元测试必须 mock `platform.db.transaction`，迫使集成测试覆盖路径而非业务路径
- agent 在新增 domain 时无统一参照，行为发散

### 3.2 强制器对 agent 不友好

Forward-only 五层规则虽已执行，但当 agent 写出违规 import 时，CI 只告诉它"`offenders` 列表非空"，agent 必须读测试源码反推违反了哪条规则。OpenAI 案例的核心收益是：**修复指令直接注入到 agent 上下文**，使一次 PR 内自愈成为常态。

### 3.3 域内层级零散

9 个 domain 中无任何一个具备完整五层。部分缺失合理（`account_quality` 是只读读模型），部分缺失是历史包袱。无显式约束就不会自然收敛。

---

## 4. First Principles

1. **强制器优先于约定**：约定文件解决不了 agent 漂移，目录结构 + AST 测试可以。
2. **横切走唯一入口**：domain 业务逻辑只看本域定义的 Protocol；具体实现由组合根注入。任何"绕过"都被强制器拒绝。
3. **错误信息是接口契约**：架构测试的输出格式与代码一样需要严格设计 — 它的"消费者"是未来读到失败的 agent。
4. **既有 muscle memory 优先**：每域 `interfaces.py` 已是跨域出口；新增 `providers.py` 复用同一同构形态，agent 不需学新模式。
5. **拒绝过早抽象**：只为已存在的渗漏点立 Provider；不为想象中的 metrics / feature flags / 多 LLM 立框架。

---

## 5. Goals & Falsifiable Metrics

### 5.1 必达布尔指标

- **G1**：Service 层与 Runtime 层文件中，对 `gmgn_twitter_intel.integrations.*`、`gmgn_twitter_intel.platform.db.*`、`gmgn_twitter_intel.platform.paths.*` 的直接 import 数量 = 0。验证：新增的 AST 架构测试通过。
- **G2**：9 个 domain 全部存在 `providers.py` 文件（即使为空，含 `__all__ = []` 与一行说明）。验证：新增"每域 providers.py 必存"测试通过。
- **G3**：`app/runtime/providers_wiring.py` 是仓库内**唯一**同时 import `gmgn_twitter_intel.integrations.*` 与 `gmgn_twitter_intel.domains.*.providers` 的文件。验证：新增"装配点唯一性"测试通过。

### 5.2 监测数字指标

- **M1**：每条架构测试断言的 remediation 消息长度 ≥ 100 字符。验证：测试自反检查（meta-test）。目标值非性能阈值，是"非空"下界。
- **M2**：现有 `tests/test_src_domain_architecture.py` 中 6 条断言全部升级为三段式 remediation 输出。验证：人工 review + meta-test。

### 5.3 反指标（防过度抽象漂移）

- **R1**：`domains/<d>/providers.py` 中 Protocol 数量平均 ≤ 3 / domain。超过 → domain 过胖，应起拆分 spec，不应继续加 Protocol。
- **R2**：`app/runtime/providers_wiring.py` 内嵌 adapter 类数量 ≤ 10。超过 → 提取到独立 `app/runtime/adapters/` 包，并起独立 spec 重新评估。
- **R3**：`providers.py` 文件中**禁止**出现 `from gmgn_twitter_intel.integrations` / `from gmgn_twitter_intel.platform.db` 任一 import — Protocol 文件保持纯净。验证：新增 AST 测试。

---

## 6. Target Architecture

### 6.1 包结构增量

在现有 `app/` `domains/` `integrations/` `platform/` 四象限上，增量如下：

| 新增 | 位置 | 角色 |
|---|---|---|
| `providers.py` | 每个 `domains/<d>/` 下 | 本域所需 Protocol 与值对象的纯接口文件 |
| `providers_wiring.py` | `app/runtime/` 下 | 唯一允许同时触达 `integrations.*` + `platform.*` + `domains/*/providers` 的装配点 |

不引入新的顶层包，不改变现有模块名，不改变跨域 `interfaces.py` 角色。

### 6.2 依赖方向规则增量（在现有 `docs/ARCHITECTURE.md` 表上扩展）

| 层 | 允许 import | 拒绝 import（强制器拦截） |
|---|---|---|
| `domains/<d>/providers.py` | stdlib、第三方、本域 `types/`、`typing.Protocol` | `gmgn_twitter_intel.integrations.*`、`gmgn_twitter_intel.platform.db.*` |
| `domains/<d>/services/`、`domains/<d>/scoring/` | 现有规则 + 本域 `providers.py`、`platform.config.*`、`platform.logging.*` | `gmgn_twitter_intel.integrations.*`、`gmgn_twitter_intel.platform.db.*`、`gmgn_twitter_intel.platform.paths.*` |
| `domains/<d>/runtime/` | 同 services | 同 services |
| `app/runtime/providers_wiring.py` | `integrations.*`、`platform.*`、`domains/*/providers`、`domains/*/types` | 业务 service / scoring / runtime 实现细节（仅消费 Protocol） |
| `app/runtime/app.py` | 不变（已是组合根） | 不变 |

### 6.3 替换关系

| 现有渗漏（§2.2） | Provider 化后归宿 |
|---|---|
| Service 直 import `platform.db.transaction` | 提升为该域 `StorageProvider` 上的写入语义方法 |
| Service / Runtime 直 import `integrations.okx.chains.*` 常量 | 提升为该域 `MarketChainProvider` 上的查询方法（或值对象常量经 Protocol 暴露） |
| Runtime 直 import `integrations.openai_agents.*Protocol` | 该 Protocol 移入对应域 `providers.py`，runtime 仅依赖本域 Protocol；`integrations` 层只保留具体实现类 |

---

## 7. Conceptual Data Flow

服务进程启动序列（语义层，无代码）：

1. `app/runtime/app.py` 加载 `Settings`、创建 `db_pool`、构造 HTTP / WebSocket 客户端
2. `app/runtime/app.py` 调用 `app/runtime/providers_wiring.py` 的装配函数，传入上述基础设施
3. 装配函数实例化 `integrations.*` 具体 client，必要时套上薄 adapter 适配 domain Protocol，返回一个 `WiredProviders` 集合（每个 domain 一个 Protocol 实现槽位）
4. `app/runtime/app.py` 用 `WiredProviders` 的对应字段构造各 Service / Worker
5. 业务请求路径上，Service 仅通过 Protocol 句柄调用 — 完全不知道背后是 Postgres / OKX / OpenAI 还是 fake / in-memory

测试路径上：

1. 单元测试**不需要** mock `platform.db.transaction`、`integrations.okx.*` 等具体实现
2. 单元测试构造 fake Protocol 实现（≤ 30 行），直接传给 Service 构造函数
3. 集成测试覆盖 `providers_wiring.py` 自身的装配正确性

---

## 8. Core Models

### 8.1 Protocol（语义）

每个 `domains/<d>/providers.py` 文件**只能**定义三类符号：

- **入站 Protocol 类**：声明本域作为消费者所需的外部能力契约
- **Protocol 上传递的值对象**：用 `dataclass(frozen=True)` 表达，不携带数据库行 / HTTP response 形态
- **`__all__` 导出表**：显式列出对外暴露的符号集合

### 8.2 WiredProviders（语义）

`app/runtime/providers_wiring.py` 返回的聚合体。语义性质：

- 形态：`@dataclass(frozen=True)`，每个 domain 一个字段，字段类型是该域 Protocol
- 生命周期：进程级单例，由 `app/runtime/app.py` 持有，不参与请求路径
- 不可变：装配后字段不变；测试场景由测试自行构造替代实例

### 8.3 Adapter（语义）

当具体 client（如 `OkxDexClient`）的方法签名与域 Protocol 不一致时，写薄 adapter 类完成翻译。约束：
- adapter 默认嵌在 `providers_wiring.py` 内，不为每个 adapter 单开文件
- adapter 类不持有状态（除被适配的 client 引用之外），不做业务决策

---

## 9. Interface Contracts at Semantic Level

### 9.1 Service / Runtime 构造函数契约

任何位于 `domains/<d>/services/` 或 `domains/<d>/runtime/` 的可实例化类，其构造函数参数类型必须落在以下白名单内：

- 同域 `types/` 中的值对象
- 同域 `providers.py` 中定义的 Protocol
- `platform.config.*` 中的配置值对象（Settings 整体、或其切片字段类）
- `platform.logging.*` 中的 logger shim
- stdlib 与第三方原始类型

### 9.2 Remediation 消息契约

所有架构测试断言失败时，输出消息必须包含三段：

- **违规**：`<file:line> <符号或行为>`
- **原因**：违反了哪条不变量、为什么这条不变量存在
- **修复**：可机械执行的下一步动作清单（步骤数 ≤ 3）

字符长度 ≥ 100 字符（对应 M1）。

### 9.3 装配点唯一性契约

仓库内**只有** `app/runtime/providers_wiring.py` 一个文件允许同时出现：
- `from gmgn_twitter_intel.integrations…` 形式 import
- `from gmgn_twitter_intel.domains.<d>.providers import …` 形式 import

`app/runtime/app.py` 仍可 import `domains/*/interfaces.py` 用于跨域 read 模型与 surface 路由（已有规则）；但 `domains/*/providers` 的 import 必须经由 `providers_wiring.py`。

---

## 10. Out of Scope

下列项目明确不在本 spec 范围内，需独立 spec 推进：

- **Config 下沉到每域**：保留 `platform/config/settings.py` 单一 `Settings` 形态。Service / Runtime 仍可直接 import `Settings` 与其切片字段类。触发后续 spec 的条件见 §13。
- **`platform/logging` 抽象化**：保留直接 import `loguru` shim。无 metrics / trace 抽象。
- **`platform/paths` 抽象化**：保留直接 import 路径常量。
- **`web/` 前端架构**：归 `docs/FRONTEND.md` 单独管控。
- **删除 `src/gmgn_twitter_intel/storage/`** 残留目录：作为独立清理 PR 处理。
- **HTTP / WebSocket / CLI 公共契约变更**：本重构不触碰 `docs/CONTRACTS.md`。
- **数据库 schema 变更与 migration**：本重构纯属源码层组织变更。

---

## 11. Risks & Reverse Indicators

### 11.1 风险矩阵

| 风险 | 概率 | 影响 | 缓释 |
|---|---|---|---|
| Service 构造函数签名变更触碰过多测试 | 中 | 中 | plan 层用域内增量；保留旧构造函数为 deprecated 重载（一个 release 周期内并存） |
| Protocol 与具体 client 接口微差导致 adapter 蔓延 | 中 | 低 | 反指标 R2 盯上限；超过即起改 client 接口的 spec |
| 强制器误伤合法用例 | 低 | 低 | 装配点唯一性测试白名单仅放 `app/runtime/providers_wiring.py` 一处 |
| `typing.Protocol` 引入运行时开销 | 极低 | 极低 | Protocol 默认 structural、非 `runtime_checkable`，零开销 |
| `providers.py` 沦为复制粘贴 boilerplate | 中 | 中 | 反指标 R1；空 `providers.py` 必带显式注释；review 重点项 |
| Config 直 import 仍是渗漏点 | 已知 | 低 | 已在 §10 标为 out-of-scope，触发条件见 §13 |
| 增量迁移期间出现"半 Provider 化"状态 | 中 | 低 | plan 层规定一次只迁一域；架构测试在该域 Provider 化完成前不开启相关断言 |

### 11.2 反指标（漂移监测）

- **R1**：`domains/<d>/providers.py` 中 Protocol 数量 ≤ 3 / domain
- **R2**：`app/runtime/providers_wiring.py` 内嵌 adapter 类 ≤ 10
- **R3**：`providers.py` 不可 import `integrations.*` / `platform.db.*`

R1、R2 不进 CI（属于人工 review 项）；R3 进 CI（强制器拦截）。

---

## 12. Alternatives Considered

### 12.1 单一全局 `Providers` 容器（OpenAI 文章字面方案）

形态：`app/runtime/providers.py` 单一胖 `dataclass`，注入每个 Service。

**未采用原因**：胖参数导致 Service 携带不需要的 Provider 引用；单元测试需构造完整容器或部分 mock；与现有"每域自管边界"风格冲突。

### 12.2 按关心点全局 Protocol（`platform/providers/{market,llm,storage}.py`）

形态：Protocol 集中在 `platform/` 下统一管理，Service 按需 import。

**未采用原因**：跨域 Protocol 复用会重新引入"绕过 `interfaces.py` 直接 import 他域语义"的耦合，与已落地的"跨域必经 `interfaces.py`"规则冲突。

### 12.3 不引入 Provider，仅做强制器加固

形态：保留现状直 import，只把架构测试输出做友好。

**未采用原因**：强制器无法拦截渗漏 — 没有 Provider 边界，任何 import 都"合法"；§2.2 列出的 8 处渗漏点无法机械拒绝。

---

## 13. Evolution Path

| 触发条件 | 后续 spec 主题 |
|---|---|
| `platform/config/settings.py` 单文件超过 600 行 **或** domain 数 ≥ 12 | per-domain config 切片 |
| 接入 OTEL / Prometheus / Sentry 任一 | `platform/telemetry/` + 每域 `TelemetryProvider` |
| 出现第二个 LLM provider（除 OpenAI Agents 之外的实现） | 真正的多 provider 路由层 |
| 同一形态 Protocol 在 ≥ 3 个 domain 重复定义 | 提升到 `platform/contracts/` 共享 Protocol 包 |
| 出现 feature flag 真实需求（A/B / 灰度） | `FeatureFlagProvider` + 单独 spec |
| `app/runtime/providers_wiring.py` 单文件超过 400 行 | 拆 `app/runtime/wiring/{<concern>}.py` 子模块 |

---

## 14. Verification Outline

本节列出 spec 落地后**可以怎么证伪**，具体测试名 / 文件 / 函数签名留给 plan：

- 在仓库 head 上运行架构测试套件，所有新增断言通过
- 在仓库 head 上随机选 3 个 Service 文件，断言其 import 集合不含 `gmgn_twitter_intel.integrations.*` / `gmgn_twitter_intel.platform.db.*`
- 在仓库 head 上检查 9 个 `domains/<d>/providers.py` 全部存在
- 故意在某 Service 中加一行违规 import，运行架构测试，检查输出消息包含三段式 remediation 且字符数 ≥ 100
- 故意删除某域 `providers.py`，检查"每域 providers.py 必存"测试失败且消息可执行

---

**End of spec.**
