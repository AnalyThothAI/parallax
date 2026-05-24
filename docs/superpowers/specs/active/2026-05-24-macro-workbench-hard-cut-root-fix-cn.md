# Spec — Macro Workbench Hard-Cut Root Fix

**Status**: Draft
**Date**: 2026-05-24
**Owner**: Codex
**Related**:
- Benchmark: `https://timsun.net/assets/`
- Existing spec: `docs/superpowers/specs/active/2026-05-22-macro-workbench-benchmark-redesign-cn.md`
- Existing plan: `docs/superpowers/plans/active/2026-05-22-macro-workbench-benchmark-redesign-plan-cn.md`
- Architecture: `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- Frontend rules: `docs/FRONTEND.md`
- Contracts: `docs/CONTRACTS.md`

## User Direction

彻底修复 `/macro`，不保留兼容性代码，不做 v1/v2 双轨，不让旧调试式 UI 或旧 payload 继续存在。可以借鉴 `timsun.net` 的信息架构和终端式表达，但不能依赖、抓取或复制它。

## Current Findings

2026-05-24 检查结果：

- Runtime config 已确认走 operator-owned 文件：
  - `config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
  - `workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`
- `uv run gmgn-twitter-intel db health` 报告 migration ready，版本 `20260524_0093`。
- `uv run gmgn-twitter-intel macro status` 报告 latest import `status=ok`、`coverage=36/36`、snapshot `ready`，但 `observations_count=36` 且 `concept_count=36`，说明每个 concept 实际只有一个点。
- `/api/macro/series?window=60d` 对核心概念只返回 1 个点，导致 normalized return 图表显示 `0%`，z-score、percentile、5d/20d/60d delta 全部是 `insufficient_history:*`。
- 模块 `data_gaps` 没有聚合 feature-level gaps，所以页面可以同时显示满屏 `insufficient_history:*` 和“暂无数据缺口”。
- 页面直接展示 `asset:spx`、`rates:dgs10`、`millions_usd`、`insufficient_history:zscore`、raw JSON provenance、英文 trigger code，读起来像内部调试面板。
- `macrodata-cli` v0.1.5 支持 `macrodata bundle history macro-core --start --end`，所以当前历史不足不是上游概念能力缺失，而是导入/运行流程只落了 single-asof snapshot。
- `macrodata doctor` 显示 FRED API key 未配置；source smoke 中 NY Fed、Treasury Fiscal、Yahoo、CFTC 可用，FRED 当次 public CSV smoke 超时。FRED 超时必须作为 source health/data quality 显示，不能被 `ready` 掩盖。
- `cex_oi_radar_board` worker 当前 disabled；`/macro/assets/crypto-derivatives` 必须明确显示 CEX board missing/degraded，而不是把 crypto derivatives 当作 ready 页面。

## Problem

当前 `/macro` 已经有 benchmark-like route skeleton，但没有 benchmark-quality product surface：

1. **Readiness 是假的。** `coverage=36/36` 只表示每个 concept 有 latest，不表示有可画图、可算变化、可算分位数的历史样本。
2. **Contract 泄露工程字段。** Backend module payload 把 canonical concept keys、gap codes、source JSON 直接传给 UI；前端又原样渲染。
3. **页面没有页面级判断。** 美股、债券、商品、FX、利率、美联储、流动性、波动率、信用都复用全局 `term_premium_pressure` 和同两条 trigger，缺少 domain-specific read。
4. **图表不成立。** 单点 series 仍被渲染为可用图表，用户看到的是 `0%`，不是有效市场走势。
5. **设计语言不及格。** 参考站是金融终端式信息架构：KPI、表格、图表、当前解读、验证指标、数据源状态形成闭环。当前页面是灰暗面板 + raw table dump。

## Hard-Cut Rules

- Bump global macro projection to `macro_regime_v4` and module contract to `macro_module_view_v2`.
- `/api/macro` and `/api/macro/modules/*` read only the new projection/version constants. Do not fall back to `macro_regime_v3` or `macro_module_view_v1`.
- Delete or rewrite tests/fixtures that assert old raw labels, old gap shapes, or old raw provenance display. Do not make frontend accept both old and new shapes.
- Frontend must not render canonical concept keys, provider keys, raw gap codes, raw JSON provenance, or raw backend objects in user-facing cells.
- Frontend must not infer regime, score, trigger, confidence, confirmation, contradiction, or trading conclusion. Formatting and grouping are allowed; scoring is not.
- HTTP handlers and React Query hooks must not perform provider IO. Macro provider acquisition remains `macrodata-cli` bundle/history import into PostgreSQL.
- `ready` means required current facts and required history quality are usable for the page. If history is insufficient, status is `partial` or `stale`, not `ready`.

## Goals

- G1. Make historical coverage first-class: concept-level point counts, history windows, freshness, and `score_participation` must be visible to projection and module payloads.
- G2. Make `macro status` and `/api/macro` report history readiness, not only latest concept coverage.
- G3. Make module views semantic: human labels, short labels, unit labels, descriptions, table column labels, chart subtitles, source names, data quality, and localized gap messages come from backend payloads.
- G4. Make every module page answer a concrete question:
  - Assets: risk appetite and cross-asset confirmation.
  - Equities: SPX/QQQ/IWM leadership and crypto beta read.
  - Bonds: duration stress and credit confirmation.
  - Commodities: oil/gold shock and inflation impulse.
  - FX: dollar pressure and offshore liquidity pressure.
  - Crypto: BTC/ETH macro beta and risk-on confirmation.
  - Rates: curve, real rates, breakevens, and valuation pressure.
  - Fed: corridor, administered rates, SOFR/IORB plumbing, policy text gaps.
  - Liquidity: Fed assets, RRP, TGA, reserves, SOFR stress.
  - Volatility: VIX level and missing term-structure/MOVE/IV gaps.
  - Credit: IG/HY OAS, HYG/LQD confirmation, funding cost gaps.
  - Crypto derivatives: CEX OI/funding when worker data exists, explicit missing state when disabled.
- G5. Replace debug UI with terminal-grade page grammar: header, KPI strip, primary chart, supporting table, current read, confirmations, contradictions, watch triggers, invalidations, provenance, and gaps.
- G6. Make invalid data visually honest: a chart with fewer than 2 usable points renders an explicit insufficient-history state, not a line chart or `0%`.
- G7. Document the operator workflow for backfilling history with `macrodata bundle history macro-core --start --end | uv run gmgn-twitter-intel macro import-bundle --stdin`, then projecting once.

## Non-Goals

- N1. Do not scrape or depend on `timsun.net`.
- N2. Do not introduce direct FRED/Yahoo/NYFed/Treasury/CFTC provider calls inside API handlers or React code.
- N3. Do not build Fed speeches, economic calendar, options/GEX, MOVE, VIX term structure, ETF flows, or Deribit/Greeks.live facts in this hard-cut unless the facts already exist. These must remain explicit gaps.
- N4. Do not redesign the global cockpit shell outside what `/macro` needs.
- N5. Do not keep old module payload compatibility for external clients; this is an internal product hard cut.

## Target Architecture

```text
macrodata bundle history macro-core
  -> gmgn macro import-bundle
  -> macro_observations / macro_import_runs
  -> MacroViewProjectionWorker
  -> macro_regime_v4 snapshot in macro_view_snapshots
  -> /api/macro and /api/macro/modules/{module_id}
  -> macro_module_view_v2 frontend pages
```

The existing `macro_observations` fact table remains the source of truth. The hard cut changes projection semantics and public payload shape rather than adding a second compatibility read path.

## Required Backend Contract

### `macro_regime_v4`

`features_json` for each concept must include:

- `concept_key`
- `label`
- `short_label`
- `description`
- `unit`
- `unit_label`
- `latest`
- `freshness_days`
- `history_points`
- `history_windows`: at least `20d`, `60d`, `252d`
- `delta`
- `zscore`
- `percentile`
- `score_participation`
- `data_quality`
- `data_gaps`
- `source`

`source_coverage_json` must include:

- `latest_coverage_ratio`
- `history_coverage_ratio`
- `required_concept_count`
- `observed_concept_count`
- `required_history_concept_count`
- `history_ready_concept_count`
- `concepts_below_min_history`
- `latest_observed_at`

Snapshot `status` rules:

- `missing`: no usable required facts.
- `partial`: latest facts exist but required module/history coverage is insufficient.
- `stale`: facts exist but freshness windows are exceeded.
- `ready`: latest facts, required history coverage, and data quality thresholds pass.

### `macro_module_view_v2`

Module payload must be semantic and display-ready:

- `snapshot`: module id, title, subtitle, question, status, as-of, computed time.
- `tiles`: label, value, unit label, delta label, source label, observed date, quality, score participation.
- `primary_chart`: id, title, subtitle, kind, status, min points, series with labels and point counts.
- `tables`: typed tables with column labels, raw sort values, display values, row quality, and source state.
- `read`: headline, regime label, confidence label, crypto read, token impact.
- `evidence`: confirmations, contradictions, watch triggers, invalidations.
- `provenance`: summarized source rows; no raw JSON objects.
- `data_gaps`: code, label, severity, owner, score impact, remediation hint.
- `related_routes`: route label and href.

## Required Frontend Behavior

- `/macro` and all `/macro/*` routes render only `macro_module_view_v2`.
- Concept keys may appear only in non-primary technical tooltips if explicitly needed for debugging; they must not be the main label.
- Gap codes must render as Chinese labels such as “历史样本不足：无法计算 60 日变化” rather than `insufficient_history:60d`.
- Provenance must render as a compact source-quality table, never a JSON blob.
- Chart panels must show:
  - proper chart when each displayed series has at least 2 usable points;
  - insufficient-history state when points are below threshold;
  - missing state when required concepts are absent.
- Page layout must remain dense and scannable, but not nested-card debug UI. Use route-owned Macro CSS under `web/src/features/macro/`.

## Acceptance Criteria

- `uv run gmgn-twitter-intel macro status` reports history readiness and lists concepts below minimum history.
- With a fixture containing one point per concept, `/api/macro` status is `partial`, not `ready`.
- With a 60-day fixture for core concepts, `/api/macro/series` returns multi-point data and charts render non-zero normalized returns where prices moved.
- `/macro/assets`, `/macro/rates`, `/macro/fed`, `/macro/liquidity`, `/macro/volatility`, and `/macro/credit` no longer expose `asset:spx`, `rates:dgs10`, `insufficient_history:*`, or raw JSON provenance in visible page text.
- `/macro/assets/crypto-derivatives` clearly shows CEX board disabled/missing when `cex_oi_radar_board.enabled=false`.
- Frontend architecture lint passes; no retired CSS buckets or cross-feature selector leaks are introduced.
- OpenAPI and generated frontend types match the new hard-cut contracts.
- Docs explain the macro history backfill and projection workflow using operator-owned config without printing secrets.
