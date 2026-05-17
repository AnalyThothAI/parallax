# Pulse Agent Desk 重设计 / Hardening — Verification

**日期**: 2026-05-17
**分支**: `codex/pulse-agent-desk-hardening`
**Spec**: `docs/superpowers/specs/active/2026-05-16-pulse-agent-desk-redesign-cn.md`
**Plans**:

- `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-plan-cn.md`
- `docs/superpowers/plans/active/2026-05-17-pulse-agent-desk-redesign-hardening-plan-cn.md`

## 结论

本地 deterministic gate 已完成并通过。Hardening 分支在已落地的 `Investigator → DecisionMaker`
主链路上补齐了 plan 要求的安全网、证据 allowlist、通知分页/SurfaceCard、OpenAPI contract、
详情页 v2 decision surface、docs 生成脚本、真实 Postgres E2E 和浏览器 smoke。

未执行真实线上 30 分钟 canary/soak；该项需要可控 live token、真实 LLM 成本窗口和通知环境，
应作为合入后的发布 gate 单独执行。其余本地 gate 均已 fresh 运行。

## Fresh Verification

### Backend

```bash
uv run ruff check .
```

结果：

```text
All checks passed!
```

```bash
uv run pytest -x
```

结果：

```text
1303 passed, 13 skipped in 654.64s (0:10:54)
```

说明：

- 13 个 skip 均为既有环境/技术债 skip：本地默认 Postgres 凭据、pre-hard-cut asset registry
  integration 技术债、以及无 source rows 的 token radar idempotency 场景。
- 完整后端 gate 已覆盖 OpenAPI drift、docs-generated clean-diff、architecture raw-SQL gate、
  notification rules、SurfaceCard、DecisionMaker final evidence allowlist 和 worker E2E。

### Focused Regressions

```bash
uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py tests/unit/integrations/openai_agents/tools/test_tools.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_notification_rules.py tests/unit/domains/notifications/test_pulse_surface_card.py tests/contract/test_openapi_drift.py -q
```

结果：

```text
117 passed
```

```bash
uv run pytest tests/integration/test_pulse_desk_e2e.py tests/integration/test_pulse_agent_desk_migration.py -q
```

结果：

```text
7 passed
```

### Frontend

```bash
cd web
npm test -- --run
npm run build
```

结果：

```text
Test Files  59 passed (59)
Tests       196 passed (196)
```

`npm run build` exit 0。Vite 仍有既有 `index` chunk 超过 500 kB warning，不是 build failure。

额外前端收口：

```bash
cd web
npm run lint
npm run format:check
npm test -- --run tests/unit/features/signal-lab/pulseDetail.test.ts tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx
```

结果：

```text
eslint exit 0
All matched files use Prettier code style!
Test Files  2 passed (2)
Tests       21 passed (21)
```

### Browser Smoke

```bash
cd web
npm run test:e2e -- signal-lab-filters.spec.ts
```

结果：

```text
1 passed (8.7s)
```

本次 smoke 使用 mocked Signal Pulse v2 decision payload 打开详情页，验证：

- `AGENT 推理栏` 可见。
- `v2 决策` card 可见。
- narrative、Bull、Bear、playbook 监控窗口正常渲染。
- evidence event link 保持为可点击 anchor。
- source events 区域仍正常渲染。

### Contract / Generated Artefacts

```bash
make regen-contract
uv run pytest tests/contract -m contract tests/integration/test_docs_generated.py -q
uv run pytest tests/integration/test_docs_generated.py -q
git diff --exit-code docs/generated/openapi.json web/src/lib/types/openapi.ts docs/generated/pulse-agent-desk-decisions.md docs/generated/db-schema.md
```

结果：

```text
wrote docs/generated/openapi.json
openapi-typescript 7.13.0 generated web/src/lib/types/openapi.ts
3 passed, 4 deselected
4 passed in 29.14s
```

`docs/generated/db-schema.md` 使用干净 testcontainer Postgres 的 `GMGN_TEST_POSTGRES_DSN`
生成，避免本机 dev DB 中 unrelated experimental tables 污染 schema 快照。

### Alembic

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

结果：exit 0。日志显示成功执行：

```text
Running downgrade 20260517_0052 -> 20260516_0051
Running upgrade 20260516_0051 -> 20260517_0052
```

## Residual Release Gate

- 30 分钟 live canary/soak 未在本地执行。
- Vite chunk-size warning 仍存在，属于既有 bundle 体积提醒，不阻断本次 hardening。
