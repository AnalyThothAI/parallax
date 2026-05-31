# Providers 边界与架构强制器加固 — 设计 Spec

**Status**: Approved
**Date**: 2026-05-10
**Scope**: 源码层（`src/parallax/`）的横切关注点边界与架构测试覆盖
**对齐参考**: OpenAI Harness Engineering（`docs/references/walkinglabs-harness-engineering.md` 已记 docs 那一波；本 spec 处理 src 这一波）

---

## 1. Background

`parallax` 已在 `2026-05-10-src-domain-package-restructure` 完成源码域化，落地了 forward-only 五层流水线（Types → Repo → Service → Runtime → UI），并以 AST 测试 `tests/test_src_domain_architecture.py` 机械化执行边界。

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
| 无测试断言 Provider 入口是否纯净、是否只出现在需要横切能力的域 | Provider 形态未编码，agent 仍会把 Protocol 放回 runtime 或 integration 文件。 |
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

### 3.3 Provider 形态未显式化

部分 domain 不需要 Provider，强行补空层会制造样板代码；但一旦 Service / Runtime 需要外部 client、LLM、事务边界等横切能力，就必须有固定入口。当前仓库缺少这条"需要时必须怎么写"的机械规则。

---

## 4. First Principles

1. **强制器优先于约定**：约定文件解决不了 agent 漂移，目录结构 + AST 测试可以。
2. **横切走唯一入口**：domain 业务逻辑只看本域定义的 Protocol；具体实现由组合根注入。任何"绕过"都被强制器拒绝。
3. **错误信息是接口契约**：架构测试的输出格式与代码一样需要严格设计 — 它的"消费者"是未来读到失败的 agent。
4. **既有 muscle memory 优先**：每域 `interfaces.py` 已是跨域出口；新增 `providers.py` 复用同一同构形态，agent 不需学新模式。
5. **KISS 优先**：只为已存在的渗漏点立 Provider 或 Unit of Work；不创建空 `providers.py`；不引入全局胖容器。
6. **不做兼容性代码**：构造函数和装配点一次收敛到目标形态，不保留 deprecated 旧参数、双路径 wiring、或 release 周期并存方案。

---

## 5. Goals & Falsifiable Metrics

### 5.1 必达布尔指标

- **G1**：Service 层与 Runtime 层文件中，对 `parallax.integrations.*`、`parallax.platform.db.*`、`parallax.platform.paths.*` 的直接 import 数量 = 0。验证：新增的 AST 架构测试通过。
- **G2**：存在 Provider 需求的 domain 才有 `providers.py`；当前目标域为 `ingestion`、`asset_market`、`social_enrichment`、`pulse_lab`。验证：新增"Provider 文件只在 allowlist 内且保持纯净"测试通过。
- **G3**：`app/runtime/providers_wiring.py` 是服务进程内**唯一**同时 import `parallax.integrations.*` 与 `parallax.domains.*.providers` 的文件。`app/surfaces/cli` 的一次性 ops 命令不纳入本 spec。验证：新增"服务装配点唯一性"测试通过。
- **G4**：本重构不新增 deprecated 构造函数参数、不保留旧 wiring 分支、不添加兼容 facade。验证：人工 review + 构造函数调用点全仓搜索。

### 5.2 监测数字指标

- **M1**：每条架构测试断言失败消息必须包含 `违规`、`原因`、`修复` 三段，以及至少一个 offender 的文件路径。验证：测试自反检查（meta-test）。
- **M2**：现有 `tests/test_src_domain_architecture.py` 中 8 条断言全部升级为三段式 remediation 输出。验证：人工 review + meta-test。

### 5.3 反指标（防过度抽象漂移）

- **R1**：单个 `domains/<d>/providers.py` 中 Protocol 数量 ≤ 2。超过 → Provider 语义过胖，应重新切分能力，不继续加 Protocol。
- **R2**：`app/runtime/providers_wiring.py` 内嵌 adapter 类数量 ≤ 6。超过 → 先删除重复 adapter；仍超过再起独立 spec 评估拆分。
- **R3**：`providers.py` 文件中**禁止**出现 `from parallax.integrations` / `from parallax.platform.db` 任一 import — Protocol 文件保持纯净。验证：新增 AST 测试。

---

## 6. Target Architecture

### 6.1 包结构增量

在现有 `app/` `domains/` `integrations/` `platform/` 四象限上，增量如下：

| 新增 | 位置 | 角色 |
|---|---|---|
| `providers.py` | 仅在需要横切能力的 `domains/<d>/` 下 | 本域所需 Protocol 与值对象的纯接口文件 |
| `providers_wiring.py` | `app/runtime/` 下 | 唯一允许同时触达 `integrations.*` + `platform.*` + `domains/*/providers` 的装配点 |

不引入新的顶层包，不改变现有模块名，不改变跨域 `interfaces.py` 角色。
不为暂时不需要 Provider 的域创建空文件。

### 6.2 依赖方向规则增量（在现有 `docs/ARCHITECTURE.md` 表上扩展）

| 层 | 允许 import | 拒绝 import（强制器拦截） |
|---|---|---|
| `domains/<d>/providers.py` | stdlib、第三方、本域 `types/`、`typing.Protocol` | `parallax.integrations.*`、`parallax.platform.db.*` |
| `domains/<d>/services/`、`domains/<d>/scoring/` | 现有规则 + 本域 `providers.py`、`platform.config.*`、`platform.logging.*` | `parallax.integrations.*`、`parallax.platform.db.*`、`parallax.platform.paths.*` |
| `domains/<d>/runtime/` | 同 services | 同 services |
| `app/runtime/providers_wiring.py` | `integrations.*`、`platform.*`、`domains/*/providers`、`domains/*/types` | 业务 service / scoring / runtime 实现细节（仅装配 Provider） |
| `app/runtime/app.py` | `platform.config.*`、`platform.db.*`、`providers_wiring.py`、domain runtime / repository / read model | `integrations.*`、`domains/*/providers` |
| `app/surfaces/cli` | 维持现状 | 本 spec 不处理 CLI ops 装配 |

### 6.3 替换关系

| 现有渗漏（§2.2） | Provider 化后归宿 |
|---|---|
| Service / Runtime 直 import `platform.db.transaction` | 下沉到 repository 或 `RepositorySession` 的 Unit of Work 语义；业务层只表达"同一原子写入范围"，不直接 import DB client |
| Service / Runtime 直 import `integrations.okx.chains.*` 常量 | 放入 `providers_wiring.py` 的 OKX adapter；domain 只接触 `chain_id` / `address` / 候选 token 等业务值对象，不接触 OKX chain index |
| Runtime 直 import `integrations.openai_agents.*Protocol` | 该 Protocol 移入对应域 `providers.py`，runtime 仅依赖本域 Protocol；`integrations` 层只保留具体实现类 |

---

## 7. Conceptual Data Flow

服务进程启动序列（语义层，无代码）：

1. `app/runtime/app.py` 加载 `Settings`、创建 `db_pool`、构造 HTTP / WebSocket 客户端
2. `app/runtime/app.py` 调用 `app/runtime/providers_wiring.py` 的装配函数，传入上述基础设施
3. 装配函数实例化 `integrations.*` 具体 client，必要时套上薄 adapter 适配 domain Protocol，返回一个 `WiredProviders` 集合（只包含实际需要 Provider 的域）
4. `app/runtime/app.py` 用 `WiredProviders` 的对应字段构造各 Service / Worker；未 Provider 化的域保持现有直接 repository / service 装配
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

Provider 命名使用业务能力，不使用供应商名。可以有 `DexMarketProvider`，不出现 `OkxProvider`；可以有 `PulseThesisProvider`，不出现 `OpenAIProvider`。

### 8.2 WiredProviders（语义）

`app/runtime/providers_wiring.py` 返回的聚合体。语义性质：

- 形态：`@dataclass(frozen=True)`，每个字段对应一个真实 Provider 需求，字段类型是该域 Protocol
- 生命周期：进程级单例，由 `app/runtime/app.py` 持有，不参与请求路径
- 不可变：装配后字段不变；测试场景由测试自行构造替代实例

### 8.3 Adapter（语义）

当具体 client（如 `OkxDexClient`）的方法签名与域 Protocol 不一致时，写薄 adapter 类完成翻译。约束：
- adapter 默认嵌在 `providers_wiring.py` 内，不为每个 adapter 单开文件
- adapter 类不持有状态（除被适配的 client 引用之外），不做业务决策
- 如果具体 client 已结构化满足 Protocol，不写 adapter

### 8.4 Unit of Work（语义）

数据库事务不是外部 Provider。它属于 repository / repository session 的写入原子性边界：

- Service / Runtime 不 import `platform.db.*`
- repository 可继续 import `platform.db.postgres_client.transaction`
- 需要跨多个 repository 的原子写入时，由现有 repository session 暴露最小 Unit of Work 语义，业务层只使用上下文管理器，不接触 DB client 函数

---

## 9. Interface Contracts at Semantic Level

### 9.1 Service / Runtime 构造函数契约

任何位于 `domains/<d>/services/` 或 `domains/<d>/runtime/` 的可实例化类，新增或修改构造函数参数时必须落在以下白名单内：

- 同域 `types/` 中的值对象
- 同域 `providers.py` 中定义的 Protocol
- repository 或 repository session factory
- `platform.config.*` 中的配置值对象（Settings 整体、或其切片字段类）
- `platform.logging.*` 中的 logger shim
- stdlib 与第三方原始类型

禁止为了迁移保留新旧双参数，例如 `client` 与 `provider` 并存、`dex_client` 与 `market_provider` 并存。plan 必须一次性更新调用点。

### 9.2 Remediation 消息契约

所有架构测试断言失败时，输出消息必须包含三段：

- **违规**：`<file:line> <符号或行为>`
- **原因**：违反了哪条不变量、为什么这条不变量存在
- **修复**：可机械执行的下一步动作清单（步骤数 ≤ 3）

不使用字符数阈值；消息质量由三段结构与 offender 细节保证。

### 9.3 装配点唯一性契约

仓库内**只有** `app/runtime/providers_wiring.py` 一个文件允许同时出现：
- `from parallax.integrations…` 形式 import
- `from parallax.domains.<d>.providers import …` 形式 import

`app/runtime/app.py` 仍可 import `domains/*/interfaces.py` 用于跨域 read 模型与 surface 路由（已有规则）；但不得 import `integrations.*` 或 `domains/*/providers`。CLI ops 的 direct integration import 是本 spec 的显式例外。

---

## 10. Out of Scope

下列项目明确不在本 spec 范围内，需独立 spec 推进：

- **Config 下沉到每域**：保留 `platform/config/settings.py` 单一 `Settings` 形态。Service / Runtime 仍可直接 import `Settings` 与其切片字段类。触发后续 spec 的条件见 §13。
- **`platform/logging` 抽象化**：保留直接 import `loguru` shim。无 metrics / trace 抽象。
- **`platform/paths` 抽象化**：Service / Runtime 禁止直接 import；`platform/*`、`app/runtime`、`app/surfaces/cli` 仍可直接 import 路径常量。
- **`web/` 前端架构**：归 `docs/FRONTEND.md` 单独管控。
- **删除 `src/parallax/storage/`** 残留目录：作为独立清理 PR 处理。
- **HTTP / WebSocket / CLI 公共契约变更**：本重构不触碰 `docs/CONTRACTS.md`。
- **CLI ops Provider 化**：`app/surfaces/cli` 当前承担迁移、审计、一次性同步等维护命令；它的 integration import 作为后续独立 spec 处理。
- **数据库 schema 变更与 migration**：本重构纯属源码层组织变更。

---

## 11. Risks & Reverse Indicators

### 11.1 风险矩阵

| 风险 | 概率 | 影响 | 缓释 |
|---|---|---|---|
| Service 构造函数签名变更触碰过多测试 | 中 | 中 | plan 层按调用点一次性改完；不保留兼容参数；测试失败即补齐调用点 |
| Protocol 与具体 client 接口微差导致 adapter 蔓延 | 中 | 低 | 优先让 Protocol 贴近当前业务调用；能结构化匹配就不写 adapter |
| 强制器误伤合法用例 | 低 | 低 | 服务装配白名单仅放 `app/runtime/providers_wiring.py`；CLI ops 明确排除在本 spec 外 |
| `typing.Protocol` 引入运行时开销 | 极低 | 极低 | Protocol 默认 structural、非 `runtime_checkable`，零开销 |
| `providers.py` 沦为复制粘贴 boilerplate | 低 | 中 | 不创建空 `providers.py`；只有当前横切需求的域才建 |
| Config 直 import 仍是渗漏点 | 已知 | 低 | 已在 §10 标为 out-of-scope，触发条件见 §13 |
| 增量迁移期间出现"半 Provider 化"状态 | 中 | 低 | plan 层规定每个域一次性收敛；不引入临时兼容路径；该域完成后再开启对应断言 |

### 11.2 反指标（漂移监测）

- **R1**：单个 `domains/<d>/providers.py` 中 Protocol 数量 ≤ 2
- **R2**：`app/runtime/providers_wiring.py` 内嵌 adapter 类 ≤ 6
- **R3**：`providers.py` 不可 import `integrations.*` / `platform.db.*`

R1、R2 不进 CI（属于人工 review 项）；R3 进 CI（强制器拦截）。

---

## 12. Alternatives Considered

### 12.1 单一全局 `Providers` 容器（OpenAI 文章字面方案）

形态：`app/runtime/providers.py` 单一胖 `dataclass`，注入每个 Service。

**未采用原因**：胖参数导致 Service 携带不需要的 Provider 引用；单元测试需构造完整容器或部分 mock；与现有"每域自管边界"风格冲突。

### 12.2 每域都创建空 `providers.py`

形态：9 个 domain 全部补 `providers.py`，无 Provider 需求的域仅导出空 `__all__`。

**未采用原因**：这会制造样板代码，让"存在文件"替代"存在真实边界"。KISS 版本只在有横切入站能力时创建 Provider 文件。

### 12.3 按关心点全局 Protocol（`platform/providers/{market,llm,storage}.py`）

形态：Protocol 集中在 `platform/` 下统一管理，Service 按需 import。

**未采用原因**：跨域 Protocol 复用会重新引入"绕过 `interfaces.py` 直接 import 他域语义"的耦合，与已落地的"跨域必经 `interfaces.py`"规则冲突。

### 12.4 不引入 Provider，仅做强制器加固

形态：保留现状直 import，只把架构测试输出做友好。

**未采用原因**：强制器无法拦截渗漏 — 没有 Provider 边界，任何 import 都"合法"；§2.2 列出的 5 处 Service / Runtime 渗漏点无法机械拒绝。

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
| CLI ops 继续增长或新增第二个外部维护 sync | CLI ops 装配边界独立 spec |

---

## 14. Verification Outline

本节列出 spec 落地后**可以怎么证伪**，具体测试名 / 文件 / 函数签名留给 plan：

- 在仓库 head 上运行架构测试套件，所有新增断言通过
- 在仓库 head 上随机选 3 个 Service 文件，断言其 import 集合不含 `parallax.integrations.*` / `parallax.platform.db.*`
- 在仓库 head 上检查只有 Provider allowlist 内 domain 拥有 `providers.py`
- 故意在某 Service 中加一行违规 import，运行架构测试，检查输出消息包含 `违规` / `原因` / `修复`
- 故意在 allowlist 外 domain 新增空 `providers.py`，检查"禁止空 Provider 样板"测试失败且消息可执行
- 全仓搜索构造函数调用点，确认没有新增 deprecated 参数、兼容 facade、双 wiring 分支

---

**End of spec.**
