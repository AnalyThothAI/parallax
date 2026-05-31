# Spec — Macro Terminal Hard-Cut

**Status**: Draft
**Date**: 2026-05-25
**Owner**: Codex
**Scope**: `macrodata-cli` and `parallax`
**Supersedes**:
- `docs/superpowers/specs/active/2026-05-24-macro-workbench-hard-cut-root-fix-cn.md`
- `docs/superpowers/plans/active/2026-05-24-macro-workbench-hard-cut-root-fix-plan-cn.md`
**Related**:
- Benchmark architecture reference: `https://timsun.net/assets/`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/SETUP.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`

## 用户方向

这次不是继续修补旧 `/macro` 模块，而是做一次真正的 macro terminal hard cut。产品信息架构可以 benchmark `timsun.net` 的终端式组织方式：资产、利率、流动性、美元、信用、波动率、宏观数据源状态、历史图表和缺口说明形成一个可操作的宏观终端。但实现不能抓取、依赖、代理或复制 `timsun.net` 的数据与页面；它只作为产品架构参照。

范围同时覆盖两个仓库/包边界：

- `macrodata-cli`：宏观数据采集、catalog、FRED 凭证环境变量别名、历史 bundle 能力。
- `parallax`：运行配置、宏观同步 runner、导入/投影/HTTP/前端消费路径，以及真实 backfill smoke。

本轮不做 AI/LLM 解释层，不生成自然语言宏观观点，不让模型参与评分或归因。页面和 API 只展示确定性规则、已落库事实、可计算指标、source health，以及明确的数据缺口。

## 当前证据

2026-05-25 执行前证据：

- `macrodata-cli` 当前版本为 `v0.1.5`。
- `macrodata-cli` catalog 当前有 `38` 个条目。
- 当前 `parallax` 宏观历史对每个 concept 只有一个点，不能支撑 terminal 级别的历史变化、分位数、z-score 或多窗口 chart。
- 本工作开始前 FRED key 缺失；任何修复都不能把真实 key 写入仓库、日志、命令行参数或文档。

## 问题

旧 Macro Workbench 已经完成了一轮 contract 与 UI hard cut，但真实数据链路仍不够像一个可运行的宏观终端：

1. 历史不足：每个 concept 只有单点，页面仍无法提供有效历史曲线和多窗口指标。
2. FRED 凭证策略不安全或不完整：需要明确 operator-owned runtime config 只保存 env var 名称，不保存真实 key。
3. 跨进程同步缺口：`parallax` 调用 `macrodata-cli` 时必须把 operator env 注入给 child process，而不是通过 argv 传 key。
4. 上游 CLI 兼容性缺口：`macrodata-cli` 应接受 `FINANCE_FRED_API_KEY` 作为 FRED key 的安全别名，并在内部映射为运行所需配置。
5. 缺少真实 backfill smoke：需要证明安全凭证策略、历史 bundle、gmgn 导入、投影和状态检查可以串起来。

## Hard-Cut Rules

- 不保留旧 macro module 兼容性，不支持旧 payload 双轨，不新增 v1/v2 adapter。
- 不让前端、API handler 或 React Query 直接调用外部宏观 provider。
- 不抓取、不依赖、不复制 `timsun.net`；只 benchmark 它的信息架构。
- 不在仓库写入真实 FRED key；文档、fixtures、示例和测试只能使用 `FINANCE_FRED_API_KEY` 这类占位符。
- Runtime config 使用 `fred_api_key_env: FINANCE_FRED_API_KEY` 表达“从 operator 环境读取 key”。
- `parallax` 的 macro sync runner 启动 `macrodata-cli` child process 时，把 `FINANCE_FRED_API_KEY` 的值注入 child env 的 `FRED_API_KEY`，不能放进 argv、日志、异常文本或持久化 payload。
- `macrodata-cli` 支持 `FINANCE_FRED_API_KEY` 安全别名；真实 provider 仍可在进程内看到 `FRED_API_KEY`。
- 本轮无 AI/LLM 解释。所有 readiness、缺口、评分参与度、source health 和 chart 状态都来自确定性规则。

## 目标

- G1. 建立安全 FRED secret 策略：operator-owned config 只保存 env var 名称，真实 key 只存在于 operator 环境和 child process env。
- G2. 让 `parallax` 的 macro sync runner 能稳定调用 `macrodata-cli` 历史 bundle，并安全传递 FRED env。
- G3. 让 `macrodata-cli` 接受 `FINANCE_FRED_API_KEY` 作为 `FRED_API_KEY` 的 env alias。
- G4. 跑通真实 backfill smoke，证明 catalog、history bundle、gmgn import、projection、status 可以形成闭环。
- G5. 保持 macro terminal 为确定性数据产品：显示数据、规则、缺口和 source health，不显示 AI 解释。

## 非目标

- N1. 不实现 LLM 宏观解释、agent brief、自动交易建议或 narrative summary。
- N2. 不兼容旧 macro module contract。
- N3. 不把真实 FRED key、任何 provider secret 或 operator 私密配置复制进仓库。
- N4. 不把 `timsun.net` 作为数据源。
- N5. 不在本轮修复非 macro terminal 路由、Token Radar、CEX 或 frontend shell 的无关问题。

## 目标架构

```text
operator env:
  FINANCE_FRED_API_KEY is set outside the repo

~/.parallax/config.yaml:
  macro:
    fred_api_key_env: FINANCE_FRED_API_KEY

parallax macro sync/history runner
  -> reads env var name from runtime config
  -> copies FINANCE_FRED_API_KEY value into child env as FRED_API_KEY
  -> executes macrodata-cli without key argv

macrodata-cli v0.1.x
  -> accepts FRED_API_KEY or FINANCE_FRED_API_KEY
  -> emits macro-core history bundle

parallax macro import-bundle
  -> macro_observations / macro_import_runs
  -> projection
  -> macro terminal API/UI
```

## 数据与安全契约

- Config contract:
  - `fred_api_key_env` 是 env var 名称，不是 secret value。
  - 默认示例使用 `FINANCE_FRED_API_KEY`。
  - `uv run parallax config` 可以报告字段是否配置和配置路径，但不能打印 secret value。
- Process contract:
  - Parent process 读取 `FINANCE_FRED_API_KEY`。
  - Child process env 设置 `FRED_API_KEY`，来源是 configured env var。
  - Child argv 不包含 key。
  - 日志只能出现 env var 名称、redacted boolean、source status 和路径。
- CLI contract:
  - `macrodata-cli` 继续支持 `FRED_API_KEY`。
  - `macrodata-cli` 新增支持 `FINANCE_FRED_API_KEY` alias。
  - 两者都存在时优先级必须确定并有测试覆盖。

## 验收标准

- 新运行配置文档和示例表达 `fred_api_key_env: FINANCE_FRED_API_KEY`，仓库无真实 FRED key。
- `parallax` macro sync runner 调用 `macrodata-cli` 时通过 env 注入 `FRED_API_KEY`，测试证明 argv 不含 key。
- `macrodata-cli` 在只设置 `FINANCE_FRED_API_KEY` 时能完成 FRED provider smoke 或等价 credential detection。
- 真实 backfill smoke 记录：
  - `macrodata-cli v0.1.5` 或实际执行版本；
  - catalog 条目数，当前证据为 `38`；
  - backfill 后 gmgn history 不再是每个 concept 只有一个点；
  - FRED key 在工作前缺失，工作后只通过 env 可用。
- `/macro` terminal surface 仍只展示确定性指标、数据缺口、source health 和历史 readiness，不展示 AI/LLM 解释。
