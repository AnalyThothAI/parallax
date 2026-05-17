# Pulse Agent Desk 重设计 — Verification

**日期**: 2026-05-17  
**分支**: `codex/pulse-agent-desk-redesign`  
**Plan**: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-plan-cn.md`  
**Spec**: `docs/superpowers/specs/active/2026-05-16-pulse-agent-desk-redesign-cn.md`

## 结论

本地实现与自动化验证已完成。核心 hard cut 已落地：

- `Analyst → Critic → Judge` 写路径改为 `Investigator → DecisionMaker`。
- `pulse_candidates.narrative_type` 已由迁移移除，`pulse_agent_run_steps.stage` 新写 CHECK 改为 v2 stage。
- `FinalDecision` 已扩展 narrative / bull / bear / playbook / evidence URL 字段。
- Investigator tools 使用独立 read-only tool pool，tool budget 从 `workers.yaml` 配置读取。
- API / frontend 保留 legacy stage 占位字段，避免旧审计行导致 Pulse detail UI 报错。
- Notification SurfaceCard 与稳定 signature 已覆盖。
- 新增 synthetic E2E 覆盖 worker → decision_json → read model → notification body。

未执行真实线上 30 分钟 soak 与真实截图采集；这些需要可控 live token / LLM 成本窗口，建议随 PR 合入后的 canary 环境执行。其余本地 gate 均已 fresh 运行通过。

## Fresh Verification

### Backend

```bash
uv run pytest -x
```

结果：

```text
1295 passed, 13 skipped in 967.91s (0:16:07)
```

说明：

- 13 个 skip 均为既有环境/技术债 skip：本地 `127.0.0.1:55432` postgres 凭据不可用、pre-hard-cut asset registry integration 技术债、以及一个无 source rows 的 token radar idempotency skip。
- 本轮完整通过包含 `tests/integration/test_pulse_agent_desk_migration.py`、`tests/integration/test_pulse_desk_e2e.py`、`tests/integration/test_signal_pulse_service_decision_v2.py`、OpenAPI drift、docs-generated clean-diff、architecture raw-SQL gate。

```bash
uv run ruff check .
```

结果：

```text
All checks passed!
```

### Frontend

```bash
cd web && npm test -- --run
```

结果：

```text
Test Files  59 passed (59)
Tests       188 passed (188)
Duration    39.82s
```

```bash
cd web && npm run build
```

结果：`tsc --noEmit && vite build` exit 0。Vite 仍提示 `index` chunk 超过 500 kB，这是既有 chunk-size warning，不是 build failure。

### Contract / Generated Artefacts

```bash
make regen-contract
uv run pytest tests/contract/test_openapi_drift.py -q
uv run pytest tests/integration/test_docs_generated.py -q
```

结果：

```text
wrote docs/generated/openapi.json
openapi-typescript 7.13.0 generated web/src/lib/types/openapi.ts
2 passed in 4.04s
4 passed in 32.67s
```

`docs/generated/db-schema.md`、`docs/generated/openapi.json`、`docs/generated/pulse-agent-desk-decisions.md` 已 staged，以满足 `test_make_docs_generated_clean_diff` 对 unstaged generated diff 的约束。

### Alembic

```bash
uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

结果：exit 0。日志显示成功执行：

```text
Running downgrade 20260516_0051 -> 20260516_0050
Running upgrade 20260516_0050 -> 20260516_0051
```

### Grep 防御

Plan 原始 grep 防御已执行。严格 0 命中不成立，因为本实现按 P1-11 保留 legacy stage 的只读兼容面；命中已核对为允许项：

- `AnalystOpinion` / `CritiqueReport`：0 命中。
- `_ROUTE_FOCUS` / `_STAGE_FOCUS`：0 命中。
- `pulse_stage_prompt`：仅 architecture test 注释引用 deleted 文件名。
- `narrative_type`：仅 migration、migration test、历史建表 migration 中出现。
- `analyst` / `critic` / `judge`：仅 legacy read compatibility、migration test、harness legacy-skip test、仓库历史 manifest fixture、负向/兼容断言中出现；新写路径与 stage CHECK 不再允许这些 stage。
- `agent_recommendation`：仅历史 migration、负向断言和 schema-removal tests 中出现。

额外证明：

```bash
uv run pytest tests/architecture/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime -q
```

结果：

```text
1 passed in 0.14s
```

## Targeted Regressions Added / Repaired

- `tests/integration/test_pulse_desk_e2e.py`
- `tests/integration/test_pulse_agent_desk_migration.py`
- `tests/integration/test_signal_pulse_service_decision_v2.py`
- `tests/unit/integrations/openai_agents/tools/test_tools.py`
- `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`
- `tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py`
- `tests/unit/domains/pulse_lab/test_prompt_loader.py`
- `tests/unit/domains/pulse_lab/test_agent_harness_eval_v2.py`
- `tests/unit/domains/notifications/test_pulse_surface_card.py`
- Updated legacy SignalPulse stage API/UI tests to cover `analyst/critic/judge` placeholder compatibility.

## Acceptance Notes

- `uv run pytest --timeout=120 -x` was attempted earlier, but this repo environment does not have a pytest-timeout plugin, so pytest rejected `--timeout`. The accepted full backend evidence is `uv run pytest -x`.
- Live 30-minute production-like soak and real notification/UI screenshots remain canary tasks, not local deterministic verification tasks.
