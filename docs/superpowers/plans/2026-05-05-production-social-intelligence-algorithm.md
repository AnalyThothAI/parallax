# Production Social Intelligence Algorithm Plan

日期：2026-05-05

## 目标

把 heat / quality / propagation 从展示型指标升级为生产级 deterministic scoring 闭环：可解释、可冻结、可结算、可评估。LLM 仅用于 watched-account `social-event-v2` 抽取，不进入全量 token scoring。

## 执行任务

### 1. Schema 和 Repository

修改：

- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- `src/gmgn_twitter_intel/storage/token_repository.py`

新增：

- `src/gmgn_twitter_intel/storage/token_signal_repository.py`

测试：

- `tests/test_sqlite_schema.py`
- `tests/test_token_repository.py`
- `tests/test_token_signal_repository.py`

验收：

- schema version 升级。
- 新增 token signal snapshot/outcome/evaluation/LLM label 表。
- market snapshot 支持 at-or-after、between、nearest 查询。

### 2. Baseline v2

新增：

- `src/gmgn_twitter_intel/retrieval/baseline_scoring.py`

删除：

- `src/gmgn_twitter_intel/retrieval/token_baseline.py`

修改：

- `src/gmgn_twitter_intel/retrieval/rolling_token_flow.py`
- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`

测试：

- `tests/test_baseline_scoring.py`
- `tests/test_token_rolling_flow.py`

验收：

- 使用 robust MAD/EWMA/sparse burst/data health。
- `rg` 搜不到旧 `token_baseline` 调用。

### 3. Timeline Features

新增：

- `src/gmgn_twitter_intel/retrieval/timeline_features.py`

修改：

- `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`

测试：

- `tests/test_timeline_features.py`
- `tests/test_token_social_timeline_service.py`
- `tests/test_token_flow_social_heat_contract.py`

验收：

- 真实 new authors，不用 independent_authors 伪造。
- 返回 phase、entropy、reproduction、event_ids。

### 4. Component Scoring

修改：

- `src/gmgn_twitter_intel/retrieval/scoring_common.py`
- `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py`
- `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py`
- `src/gmgn_twitter_intel/retrieval/propagation_scoring.py`
- `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- `src/gmgn_twitter_intel/retrieval/timing_scoring.py`
- `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py`

测试：

- `tests/test_social_heat_scoring.py`
- `tests/test_discussion_quality_scoring.py`
- `tests/test_propagation_scoring.py`
- `tests/test_tradeability_scoring.py`
- `tests/test_timing_scoring.py`
- `tests/test_opportunity_scoring.py`

验收：

- score version 升级为 v2/v3。
- driver gate、hard risk cap、chase cap、public-only cap 生效。
- scoring payload 包含 `data_health`。

### 5. Token Flow 集成

修改：

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`

测试：

- `tests/test_token_flow_social_heat_contract.py`
- `tests/test_token_flow_no_lookahead.py`

验收：

- token-flow 输出 `score_versions`、`data_health`、`timeline`。
- market block 包含 `snapshot_id`、`start_snapshot_id`、`before_snapshot_id`、`lookahead_risk`。
- scoring 不读取未来 market snapshot。

### 6. Freeze Snapshots

新增：

- `src/gmgn_twitter_intel/retrieval/token_signal_snapshot_service.py`

修改：

- `src/gmgn_twitter_intel/cli.py`
- `src/gmgn_twitter_intel/api/app.py`

测试：

- `tests/test_token_signal_snapshot_service.py`
- `tests/test_cli.py`

验收：

- `ops freeze-token-signals` 写入 immutable snapshot。
- snapshot id deterministic。
- freeze 不调用 LLM。

### 7. Settlement

新增：

- `src/gmgn_twitter_intel/pipeline/token_signal_settlement.py`

修改：

- `src/gmgn_twitter_intel/cli.py`

测试：

- `tests/test_token_signal_settlement.py`
- `tests/test_cli.py`

验收：

- `ops settle-token-signals` 结算 6h/24h。
- missing entry/exit/price 有显式 status。
- normalized outcome 使用 vol floor .03。

### 8. Evaluation / Calibration

新增：

- `src/gmgn_twitter_intel/retrieval/token_signal_evaluation_service.py`

修改：

- `src/gmgn_twitter_intel/api/http.py`
- `src/gmgn_twitter_intel/cli.py`

测试：

- `tests/test_token_signal_evaluation_service.py`
- `tests/test_api_http.py`
- `tests/test_cli.py`

验收：

- API/CLI 返回 score bucket evaluation。
- evaluation rows 可持久化。
- 输出 coverage、hit rate、Wilson interval。

### 9. Harness Upgrade

修改：

- `src/gmgn_twitter_intel/pipeline/social_event_extraction.py`
- `src/gmgn_twitter_intel/pipeline/harness_snapshot_builder.py`
- `src/gmgn_twitter_intel/pipeline/harness_settlement.py`
- `src/gmgn_twitter_intel/pipeline/harness_ops.py`
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`

测试：

- `tests/test_social_event_extraction.py`
- `tests/test_harness_scoring.py`
- `tests/test_harness_snapshot_builder.py`
- `tests/test_harness_settlement_credit.py`
- `tests/test_harness_ops.py`
- `tests/test_enrichment_worker.py`

验收：

- `social_event_response_format().json_schema.name == social_event_v2`。
- `schema_version == social-event-v2`。
- no fixed pricedness。
- benchmark version 为 `benchmark-zero-v1`。

### 10. 文档和清理

修改：

- `README.md`

新增：

- 本 spec。
- 本 plan。

验收：

- README 描述当前 v2 边界和 token signal 操作入口。
- `rg` 搜索旧运行时关键词无命中。
- 全量测试、lint、compileall 通过。

## 最终验证命令

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
rg -n "baseline-zero-v0|pricedness=0\\.35|long_threshold=0\\.70|social_heat_v1|discussion_quality_v1|propagation_v1|tradeability_v1|timing_v2|social_opportunity_v1|from \\.token_baseline|import token_baseline|token_baseline\\(" src tests README.md
```
