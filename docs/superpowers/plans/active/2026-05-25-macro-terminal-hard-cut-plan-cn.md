# Macro Terminal Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-25
**Owning spec:** `docs/superpowers/specs/active/2026-05-25-macro-terminal-hard-cut-spec-cn.md`
**Scope:** `macrodata-cli` and `parallax`
**Recommended branch:** `codex/macro-terminal-hard-cut`

**Goal:** 做一次真正的 macro terminal hard cut：以 `timsun.net` 的信息架构为 benchmark，但不抓取、不依赖它；用安全 FRED secret 策略、gmgn macro sync runner、`macrodata-cli` env alias 和真实 backfill smoke，把宏观终端从单点历史推进到可验证的数据链路。

**Architecture:** Runtime config 只保存 `fred_api_key_env: FINANCE_FRED_API_KEY`。`parallax` 启动 `macrodata-cli` child process 时，把 operator 环境中的 `FINANCE_FRED_API_KEY` 注入 child env 的 `FRED_API_KEY`，不走 argv。`macrodata-cli` 同时接受 `FRED_API_KEY` 和 `FINANCE_FRED_API_KEY`。宏观终端只显示确定性规则、数据缺口、source health 和历史 readiness；本轮不做 AI/LLM 解释，不保留旧 macro module 兼容性。

**Current evidence:** `macrodata-cli v0.1.5`；catalog 当前 `38` 个条目；当前 gmgn history 每个 concept 只有一个点；本工作前 FRED key 缺失。

---

## Hard-Cut Decisions

- [ ] 不保留旧 macro module compatibility，不做 payload 双轨。
- [ ] 不引入 AI/LLM explanation；所有输出来自 deterministic rules、persisted facts、source health 和 data gaps。
- [ ] 不把 FRED key 写入 repo、fixtures、docs、argv、日志或异常文本。
- [ ] `fred_api_key_env` 表示 env var 名称，默认使用 `FINANCE_FRED_API_KEY`。
- [ ] `parallax` macro sync runner 只通过 child env 暴露 `FRED_API_KEY` 给 `macrodata-cli`。
- [ ] `timsun.net` 只作为 terminal 信息架构 benchmark，不作为数据源或 runtime dependency。

## Subagent Execution Tasks 0-4

## Task 0 - Docs

**Owner:** Worker Task 0

**Files:**
- Create: `docs/superpowers/specs/active/2026-05-25-macro-terminal-hard-cut-spec-cn.md`
- Create: `docs/superpowers/plans/active/2026-05-25-macro-terminal-hard-cut-plan-cn.md`
- Modify: `docs/superpowers/specs/active/2026-05-24-macro-workbench-hard-cut-root-fix-cn.md`
- Modify: `docs/superpowers/plans/active/2026-05-24-macro-workbench-hard-cut-root-fix-plan-cn.md`

**Steps:**
- [ ] Persist the new Chinese spec and plan.
- [ ] Mark the 2026-05-24 macro workbench spec and plan as superseded near the top without deleting content.
- [ ] Include scope across `macrodata-cli` and `parallax`.
- [ ] Include safe FRED strategy, gmgn child env injection, no AI/LLM explanation, no old compatibility, current evidence, and tasks 0-4.

**Verification:**
```bash
git diff -- docs/superpowers/specs/active docs/superpowers/plans/active
```

## Task 1 - Safe FRED Config

**Owner:** Worker Task 1

**Files:**
- Modify gmgn runtime config schema and docs where macro provider settings are defined.
- Modify operator-facing setup/config examples without writing secret values.
- Add or update tests for redacted config reporting.

**Steps:**
- [ ] Add or confirm `fred_api_key_env` in macro runtime config.
- [ ] Use `FINANCE_FRED_API_KEY` as the documented env var name.
- [ ] Ensure config diagnostics report path and configured/missing booleans only.
- [ ] Ensure no command, doc, fixture, or test contains a real key.
- [ ] Update setup/contract docs to explain that real-data debugging starts from `uv run parallax config` and operator-owned files under `~/.parallax/`.

**Verification:**
```bash
uv run parallax config
rg -n "FRED|FINANCE_FRED_API_KEY|fred_api_key_env" docs src tests
```

Expected: only placeholders and redacted diagnostics are visible; no secret values are printed.

## Task 2 - gmgn Macro Sync Runner

**Owner:** Worker Task 2

**Files:**
- Modify or create the gmgn macro sync/history runner that launches `macrodata-cli`.
- Add unit tests around child process command construction and environment injection.
- Update CLI/help docs if the public command surface changes.

**Steps:**
- [ ] Add a deterministic runner path for `macrodata bundle history macro-core --start YYYY-MM-DD --end YYYY-MM-DD`.
- [ ] Read `fred_api_key_env` from runtime config.
- [ ] When the parent env contains `FINANCE_FRED_API_KEY`, inject that value into child env as `FRED_API_KEY`.
- [ ] Do not include the key in argv, persisted bundle metadata, logs, exception messages, or test snapshots.
- [ ] Return explicit data-gap/source-health diagnostics when the env var is configured but absent.

**Verification:**
```bash
uv run pytest tests/unit -q -k "macro and (sync or fred or runner)"
uv run ruff check src/parallax tests
```

Expected: tests prove child argv contains no secret while child env receives `FRED_API_KEY` when `FINANCE_FRED_API_KEY` is available.

## Task 3 - macrodata CLI Env Alias

**Owner:** Worker Task 3

**Files:**
- Modify `macrodata-cli` credential/config resolution for FRED.
- Add CLI/provider tests for `FINANCE_FRED_API_KEY` alias.
- Update `macrodata-cli` docs/help if credential env vars are documented.

**Steps:**
- [ ] Keep existing `FRED_API_KEY` support.
- [ ] Add `FINANCE_FRED_API_KEY` as a safe alias accepted by `macrodata-cli`.
- [ ] Define precedence when both env vars exist.
- [ ] Ensure diagnostic output names env vars but never prints values.
- [ ] Verify catalog still reports the expected macro universe; current evidence is `38` catalog entries.

**Verification:**
```bash
macrodata --version
macrodata catalog list
macrodata doctor
```

Expected: `FINANCE_FRED_API_KEY` alone is enough for FRED credential detection; output remains redacted.

## Task 4 - Real Backfill Smoke

**Owner:** Worker Task 4

**Files:**
- Create or update a verification note under `docs/superpowers/plans/active/`.
- Do not commit real secrets or operator-only config files.

**Steps:**
- [ ] Confirm `uv run parallax config` points at `~/.parallax/config.yaml` and `~/.parallax/workers.yaml`.
- [ ] Confirm FRED key was absent before this work and is now supplied only through operator env.
- [ ] Run `macrodata-cli` history bundle for `macro-core` over a bounded date range.
- [ ] Import the bundle into gmgn with `uv run parallax macro import-bundle --stdin`.
- [ ] Run projection once and check `uv run parallax macro status`.
- [ ] Record whether gmgn history still has one point per concept or now has enough history for terminal charts.

**Verification:**
```bash
uv run parallax config
uv run parallax db health
macrodata bundle history macro-core --start YYYY-MM-DD --end YYYY-MM-DD \
  | uv run parallax macro import-bundle --stdin
uv run parallax macro project-once
uv run parallax macro status
```

Expected: verification records version, catalog count, import/projection outcome, history point counts, and redacted FRED credential status.

## Completion Gate

- [ ] All tasks 0-4 are complete.
- [ ] No real secret appears in repo diff.
- [ ] Real backfill smoke proves the macro terminal data chain can move beyond one point per concept.
- [ ] Remaining gaps are explicit source/data gaps, not AI explanations or compatibility fallbacks.
