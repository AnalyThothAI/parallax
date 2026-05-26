# Worker Contract Hard Cut Verification

**Date**: 2026-05-26
**Branch**: `codex/worker-contract-hard-cut`
**Worktree**: `/Users/qinghuan/Documents/code/gmgn-twitter-intel/.worktrees/worker-contract-hard-cut`

## 已落地

- 新增 `app/runtime/worker_manifest.py`，作为 worker inventory、lane、kind、class path、start priority、factory ownership、dirty target tables、queue-depth table、读写所有权和幂等证据的唯一代码来源。
- 删除 `app/runtime/worker_registry.py`，不保留 `CANONICAL_WORKER_CLASSES`、`CANONICAL_WORKER_NAMES`、`WORKER_START_PRIORITY` 兼容入口。
- 所有 worker factory 的 `WORKER_KEYS` 改为从 manifest factory ownership 派生。
- `WorkerScheduler` start priority 改为从 manifest 派生。
- `worker_status.py` 输出 `workers` + `worker_lanes`。
- `/readyz`、`/api/status`、CLI `ops worker-status`、`/api/ops/diagnostics` 暴露 lane 聚合。
- Watchlist queue descriptor 硬切为 `watchlist_handle_summary_jobs`，旧 `watchlist_summary_jobs` 不在 allowlist 中。
- API worker dependency 对未知 worker name 调用 `require_worker_manifest()` 硬失败。
- 更新当前权威 docs：`ARCHITECTURE`、`CONTRACTS`、`TESTING`、`WORKERS`、`WORKER_FLOW`、ops diagnostics spec。

## 真实配置检查

已检查生产 runtime config 路径：

```text
config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml
workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

`workers.yaml` 检查结果：

```text
key_count=26
unknown_keys=
old_worker_contract_keys=
```

未发现需要迁移的旧 worker key。本次没有打印或复制 secret 值。

## 验证命令

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py \
  tests/architecture/test_worker_inventory_contract.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  tests/architecture/test_projection_worker_idle_cost_contract.py -q
```

结果：

```text
148 passed
```

```bash
uv run pytest tests/unit/test_worker_base_runtime.py \
  tests/unit/test_worker_scheduler.py \
  tests/unit/test_worker_status.py \
  tests/unit/test_bootstrap_worker_runtime_wiring.py \
  tests/unit/test_job_queue.py \
  tests/unit/test_ops_diagnostics.py \
  tests/unit/test_settings.py \
  tests/unit/test_worker_settings.py \
  tests/unit/test_cli_worker_status_contract.py -q
```

结果：

```text
139 passed
```

```bash
uv run pytest tests/integration/test_api_health.py \
  tests/integration/test_api_http.py::test_api_status_exposes_market_tick_and_live_market_status \
  tests/integration/test_api_http.py::test_api_status_exposes_operational_state -q
```

结果：

```text
18 passed
```

```bash
uv run ruff check src/gmgn_twitter_intel tests
git diff --check
```

结果：

```text
All checks passed
```

当前源码、测试和权威 docs 扫描：

```bash
rg -n "WATCHLIST_SUMMARY_JOBS|watchlist_summary_jobs|asset_profile_consistency_worker|tweet_asset_link_worker|macro_context_projection_worker|market_tick_rollup_worker|signal_generation_worker|position_signal_projection_worker|legacy_anchor_worker_key|CANONICAL_WORKER_CLASSES|CANONICAL_WORKER_NAMES|WORKER_START_PRIORITY|worker_registry.py" \
  src tests docs/ARCHITECTURE.md docs/WORKER_FLOW.md docs/WORKERS.md docs/CONTRACTS.md docs/TESTING.md docs/RELIABILITY.md docs/SETUP.md docs/SECURITY.md
```

结果：

```text
no matches
```

## 已知非本次失败

完整运行 `uv run pytest tests/integration/test_api_http.py -q` 时，出现 3 个既有业务契约失败，未纳入本次 worker contract 修复：

- `test_token_radar_public_payload_keeps_targetless_rows_in_diagnostics`: `identity_missing_count` 为 `0`，测试期望 `>= 1`。
- `test_api_exposes_signal_pulse_empty_contract_after_hard_cut`: 查询 payload 多了 `visibility: public`。
- `test_api_signal_pulse_status_filter_uses_public_display_status_after_evidence_cut`: `status=token_watch` 返回 `400`，测试期望 `200`。

本次改动在 `test_api_http.py` 中只触碰 status/worker_lanes 断言；相关精准测试已通过。

## Subagent Review 收口

两个 review 子 agent 分别检查了 plan 合规和代码风险，主要反馈已处理：

- 权威 docs 不再指向 `worker_registry.py`。
- `docs/CONTRACTS.md` worker key 列表已补齐并按 manifest 顺序排列。
- 删除 `worker_registry.py`，不保留旧 canonical 常量导出。
- ops diagnostics 补充 `worker_lanes`。
- 增加 lane aggregation 单元测试，覆盖 failed、timeout、oldest active age、p99、queue depth 和 unknown worker 拒绝。
- 增加 manifest ownership 测试，覆盖 single-writer 表归属、dirty-target consumer 声明、禁止语义化 read-model alias 回流。
