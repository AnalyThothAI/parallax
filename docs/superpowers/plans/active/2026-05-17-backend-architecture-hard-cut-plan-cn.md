# Backend Architecture Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性完成后端三阶段架构优化：修红质量门并拆 surface，拆 provider/worker composition，拆 Pulse 高耦合核心链路；全程硬切，不保留兼容性代码。

**Architecture:** 保留现有 Kappa/CQRS、PostgreSQL facts、read model 单写者、`WorkerBase` 生命周期、`DBPoolBundle` pool 隔离和 canonical worker registry。重构只改变代码分解和契约一致性，不新增运行时 worker、不新增兼容路由、不保留旧字段桥接、不做双写或双读。

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Alembic, psycopg, Pydantic v2, pytest, ruff, mypy, React/OpenAPI generated contracts.

---

## Review Fixes Integrated

本版已吸收 3 个只读子 agent 对审计和当前代码链路的 P0/P1 review：

- P0: API split 必须同步迁移 `create_app()` 的异常注册入口，不能把 app-level exception handler 错放到 `APIRouter`。
- P0: provider split 必须同步修改 architecture guard，允许 `app/runtime/provider_wiring/**` 作为唯一 provider wiring package。
- P0: worker factory split 必须保留 `collector` 注入，否则 canonical worker map 会丢 ingestion worker。
- P1: `market_overlay -> market_candles` 必须覆盖后端 schema、runtime payload、OpenAPI、generated TS、手写 frontend contracts、search model、fixtures/MSW/E2E mocks。
- P1: `PulseRepository` 拆分必须先定义新 `RepositorySession` contract 和跨表事务所有者，不能先删 facade 再找调用点。
- P1: Pulse admission、job success、job failure 三段事务边界必须由 use-case runner 编排，子 repository/writer 不能自己开连接或自行 commit。
- P1: OpenAI Pulse 边界移动必须通过纯 Python domain tool runtime 注入，不能让 domain service 反向 import `agents` SDK primitive。
- P1: API/CLI 测试里对旧私有 helper/import path 的依赖必须随 hard-cut 一次性迁移。

## Target Directory Shape

硬切后的目标结构是“composition root + public surface + domain-owned use cases + integration adapters”：

```text
src/parallax/
  app/
    runtime/
      bootstrap.py                  # process facade: DB, providers, repositories, workers, scheduler
      providers_wiring.py           # provider wiring public facade only
      provider_wiring/
        types.py                    # wired provider dataclasses
        asset_market.py             # cross-provider asset-market assembly
        okx.py
        gmgn.py
        binance.py
        openai.py
        marketlane.py
      worker_factories/
        ingestion.py                # collector injection
        asset_market.py
        token_intel.py
        pulse.py
        watchlist.py
        notifications.py            # rule+delivery share one wake waiter
        enrichment.py
        harness.py
      repository_session.py         # DB connection-scoped repository bundle
    surfaces/
      api/
        http.py                     # include routers only
        exceptions.py               # ApiBadRequest/ApiUnauthorized + handlers
        responses.py                # JSON/File response helpers
        dependencies.py             # runtime/auth helpers
        validators.py
        routes_status.py
        routes_events.py
        routes_token_image.py
        routes_search.py
        routes_radar.py
        routes_watchlist.py
        routes_pulse.py
        routes_harness.py
        routes_notifications.py
      cli/
        main.py                     # entrypoint dispatch only
        parser.py
        commands/
          config.py
          db.py
          serve.py
          read_models.py
          ops.py
  domains/
    pulse_lab/
      repositories/
        pulse_admission_repository.py
        pulse_jobs_repository.py
        pulse_candidates_repository.py
        pulse_runs_repository.py
        pulse_harness_repository.py
        pulse_read_repository.py
        pulse_playbooks_repository.py
      services/
        pulse_trigger_scanner.py
        pulse_admission_service.py
        pulse_job_runner.py
        pulse_audit_ledger_writer.py
        pulse_eval_recorder.py
        pulse_failure_recorder.py
        agent_tool_runtime.py        # pure Python tool runtime, no OpenAI SDK
        pulse_decision_runtime.py    # stage specs/prompts/domain validation
      runtime/
        pulse_candidate_worker.py    # thin WorkerBase shell
  integrations/
    openai_agents/
      pulse_decision_agent_client.py # SDK runner, schema parse, safety net only
      tools/                         # OpenAI tool wrappers call injected runtime
```

这个结构符合最佳实践：`app/runtime` 只做 composition；`surfaces` 只做协议翻译；`domains` 拥有 use case、transaction semantics、business vocabulary；`integrations` 只适配外部 SDK/API。唯一需要刻意守住的是不要把 `provider_wiring/` 拆成第二套业务层，它仍然只是 composition package。

## Hard-Cut Rules

- 删除旧契约、旧测试期望、旧命名和旧 public schema 字段；不新增 `_compat_*`、`legacy_*_fallback`、`if old field then new field`。
- `market_overlay` 统一改名为一等产品概念 `market_candles`；不保留别名字段、不保留 frontend 双读 fallback。
- `runtime.tool_names_by_stage` 是 Pulse harness 工具契约唯一来源；`runtime.tools_enabled` 删除，active docs/spec 也不能继续宣称它是现行契约。
- `integrations/openai_agents` 不再 import `domains.pulse_lab.queries` 或 `domains.pulse_lab.services`；OpenAI tool wrapper 只调用 injected runtime/context。
- API/CLI 拆分必须是行为等价硬切：旧 import path 不保留 shim，测试和调用点一次性迁到新模块。
- Worker construction 和 provider wiring 只保留一个 canonical 入口：`bootstrap()` 调用新 factory；不保留旧 `_construct_workers` 大函数或旧 provider construction 辅助路径。
- Pulse repository 拆分必须保持同连接、同事务边界；跨表 use case 由 domain service/repository 编排，不允许子 repository 自行开 pool。

## Pre-flight

- [ ] 确认当前未跟踪文件不属于本计划：`docs/superpowers/specs/active/2026-05-17-pulse-agent-harness-v3-hard-cut-cn.md`。
- [ ] 创建工作树：`git worktree add .worktrees/backend-architecture-hard-cut -b codex/backend-architecture-hard-cut main`。
- [ ] 在工作树确认：`git worktree list && git status --short && git branch --show-current`。
- [ ] 记录已知红基线：`uv run ruff check src`, `uv run mypy src`, `uv run pytest tests/unit -q`。
- [ ] 只在新工作树中修改 `src/`, `tests/`, `docs/`, `web/`。

## Phase 1 — Green Baseline And Surface Split

### Task 1: Hard-cut Pulse harness manifest contract

**Files:**
- Modify: `src/parallax/domains/pulse_lab/services/agent_harness.py`
- Modify: `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`
- Modify: `tests/unit/domains/pulse_lab/test_agent_harness_eval_v2.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/parallax/domains/pulse_lab/ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-plan-cn.md` or move it to completed/historical if superseded.

- [ ] Keep the new contract: `runtime.tool_names_by_stage` is the source of truth; `runtime.tools_enabled` is deleted.
- [ ] Rename the old test `test_pulse_harness_manifest_advertises_two_stages_and_tools_enabled` so its name no longer encodes the deleted field.
- [ ] Assert `"tools_enabled" not in runtime`.
- [ ] Assert `runtime["tool_names_by_stage"]["investigator"]` is non-empty.
- [ ] Assert `decision_maker` tool list may be empty when fallback tools are disabled.
- [ ] Document: "tools enabled" means a stage has a non-empty tool list; there is no separate bool.
- [ ] Remove/update active docs/spec text that still advertises `runtime.tools_enabled` as a current contract.
- [ ] Verify: `uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py tests/unit/domains/pulse_lab/test_agent_harness_eval_v2.py -q`.

### Task 2: Clear backend quality gate red items

**Files:**
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/services/agent_harness_eval.py`
- Modify: `src/parallax/domains/asset_market/read_models/token_profile_read_model.py`
- Modify: `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py`
- Modify: `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py`
- Modify: `src/parallax/domains/asset_market/runtime/live_price_gateway.py`
- Modify: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
- Modify: `src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Modify: `pyproject.toml` only if adding a precise `jsonref` typing ignore is cleaner than local ignores.

- [ ] Run `uv run ruff check src --fix` and inspect the diff; manually fix the B009 private `getattr` and long line.
- [ ] Replace nullable list comprehensions with typed local variables in profile and live market paths.
- [ ] Add explicit provider availability guard in `MarketTickStreamWorker._stream_and_persist_ticks`.
- [ ] Cast or normalize repository return rows at module boundaries rather than returning `Any`.
- [ ] Fix watchlist `social_event` optional access with one typed `_dict` normalization.
- [ ] Add missing return annotation in `PulseRepository`.
- [ ] Resolve `jsonref` mypy noise with a targeted ignore or stub config; do not disable mypy broadly.
- [ ] Verify: `uv run ruff check src`, `uv run mypy src`, `uv run pytest tests/unit -q`.

### Task 3: Split FastAPI surface by route group

**Files:**
- Create: `src/parallax/app/surfaces/api/exceptions.py`
- Create: `src/parallax/app/surfaces/api/responses.py`
- Create: `src/parallax/app/surfaces/api/dependencies.py`
- Create: `src/parallax/app/surfaces/api/validators.py`
- Create: `src/parallax/app/surfaces/api/routes_status.py`
- Create: `src/parallax/app/surfaces/api/routes_events.py`
- Create: `src/parallax/app/surfaces/api/routes_token_image.py`
- Create: `src/parallax/app/surfaces/api/routes_radar.py`
- Create: `src/parallax/app/surfaces/api/routes_search.py`
- Create: `src/parallax/app/surfaces/api/routes_watchlist.py`
- Create: `src/parallax/app/surfaces/api/routes_pulse.py`
- Create: `src/parallax/app/surfaces/api/routes_harness.py`
- Create: `src/parallax/app/surfaces/api/routes_notifications.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `tests/integration/test_api_http.py`
- Modify: `tests/integration/test_api_health.py`
- Modify: `tests/integration/watchlist/test_watchlist_intel_api.py`
- Modify: `tests/integration/watchlist/test_watchlist_overview_api.py`
- Modify: `tests/unit/test_public_event_token_payloads.py`
- Modify: `tests/contract/test_openapi_drift.py`

- [ ] Move `ApiUnauthorized`, `ApiBadRequest`, `api_unauthorized_response`, and `api_bad_request_response` to `exceptions.py`.
- [ ] Keep exception handler registration in `app/runtime/app.py`; do not pretend `APIRouter` owns app-level handlers.
- [ ] Move `_json`, file/image response helpers, and token-image cache helpers to `responses.py` or `routes_token_image.py`.
- [ ] Move auth/runtime helpers from `http.py` into `dependencies.py`.
- [ ] Move `_limit`, `_window`, `_scope`, `_target_type`, cursor/status validators into `validators.py`.
- [ ] Move each route group to its own router module with `router = APIRouter(...)`.
- [ ] Reduce `create_api_router()` to include route modules only.
- [ ] Update tests that import private helpers from `api.http` to import the new route/dependency modules.
- [ ] Do not leave old route registration code in `http.py`.
- [ ] Verify: `uv run pytest tests/integration/test_api_http.py tests/integration/test_api_health.py tests/integration/watchlist/test_watchlist_intel_api.py tests/integration/watchlist/test_watchlist_overview_api.py tests/unit/test_public_event_token_payloads.py tests/contract/test_openapi_drift.py -q`.

### Task 4: Split CLI command surface

**Files:**
- Create: `src/parallax/app/surfaces/cli/parser.py`
- Create: `src/parallax/app/surfaces/cli/commands/__init__.py`
- Create: `src/parallax/app/surfaces/cli/commands/config.py`
- Create: `src/parallax/app/surfaces/cli/commands/db.py`
- Create: `src/parallax/app/surfaces/cli/commands/serve.py`
- Create: `src/parallax/app/surfaces/cli/commands/read_models.py`
- Create: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `src/parallax/app/surfaces/cli/main.py`
- Modify: `src/parallax/cli.py`
- Modify: `tests/integration/test_cli.py`
- Modify: `tests/unit/test_cli_search_query.py`
- Modify: `tests/unit/test_token_radar_audit_cli.py`
- Modify: `docs/generated/cli-help.md`

- [ ] Move parser construction to `parser.py`.
- [ ] Move command implementations by domain into `commands/*`.
- [ ] Hard-cut root shim: `parallax.cli` exports `main` only unless a test documents a current public API that must move to a named command module.
- [ ] Move `_audit_token_radar_rows` to `commands/ops.py` or a domain read-model command module; update tests to import the new owner.
- [ ] Keep `parallax.cli:main` as the installed command entrypoint, but remove behavior from the root shim.
- [ ] Preserve token-radar one-shot advisory lock behavior during CLI ops split.
- [ ] Regenerate CLI help: `uv run python scripts/regen_cli_help.py`.
- [ ] Verify: `uv run pytest tests/integration/test_cli.py tests/unit/test_cli_search_query.py tests/unit/test_token_radar_audit_cli.py -q`.

### Task 5: Rename `market_overlay` hard-cut to `market_candles`

**Files:**
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/search_agent_brief.py`
- Modify: `src/parallax/domains/asset_market/read_models/market_candles_service.py`
- Modify: `tests/unit/test_market_candles_service.py`
- Modify: `tests/unit/test_search_agent_brief.py`
- Modify: `tests/unit/test_search_inspect_service.py`
- Modify: `tests/unit/test_token_target_social_timeline_service.py`
- Modify: `tests/integration/test_api_http.py`
- Modify: `tests/contract/test_openapi_drift.py`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/generated/openapi.json`
- Modify: `web/src/lib/types/openapi.ts`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/features/search/model/searchCase.ts`
- Modify: `web/src/features/search/ui/SearchAmbiguousCase.tsx` if it consumes the old field.
- Modify: `web/tests/fixtures/tokenCaseFixture.ts`
- Modify: `web/tests/fixtures/appRouteFixtures.ts`
- Modify: `web/tests/msw/scenarios.ts`
- Modify: `web/tests/e2e/support/mockApi.ts`
- Modify: `web/tests/unit/features/search/model/searchCase.test.ts`
- Modify: `web/tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`

- [ ] Rename schema field and all response payload references to `market_candles`.
- [ ] Delete frontend dual-read fallback: no `result.market_overlay ?? result.timeline.market_overlay`.
- [ ] Delete tests that assert absence of legacy overlays and replace them with tests asserting the new field name.
- [ ] Add contract tests that scan `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`, and `web/src/lib/types/frontend-contracts.ts` for absence of `market_overlay`.
- [ ] Regenerate contract: `make regen-contract`.
- [ ] Verify backend: `rg -n "market_overlay|_overlay_live_market|live_market overlay" src tests docs/CONTRACTS.md docs/generated/openapi.json web/src/lib/types/openapi.ts web/src/lib/types/frontend-contracts.ts` returns no runtime/public contract hits.
- [ ] Verify frontend: `cd web && npm run typecheck && npm run test -- --run`.

## Phase 2 — Composition Split

### Task 6: Split provider wiring by provider family

**Files:**
- Create: `src/parallax/app/runtime/provider_wiring/__init__.py`
- Create: `src/parallax/app/runtime/provider_wiring/types.py`
- Create: `src/parallax/app/runtime/provider_wiring/okx.py`
- Create: `src/parallax/app/runtime/provider_wiring/gmgn.py`
- Create: `src/parallax/app/runtime/provider_wiring/binance.py`
- Create: `src/parallax/app/runtime/provider_wiring/openai.py`
- Create: `src/parallax/app/runtime/provider_wiring/marketlane.py`
- Create: `src/parallax/app/runtime/provider_wiring/asset_market.py`
- Modify: `src/parallax/app/runtime/providers_wiring.py`
- Modify: `src/parallax/app/surfaces/cli/main.py` or the new CLI command modules after Task 4.
- Modify: `src/parallax/domains/asset_market/services/event_market_capture.py`
- Modify: `tests/unit/test_providers_wiring.py`
- Modify: `tests/unit/test_provider_capabilities.py`
- Modify: `tests/unit/test_event_market_capture.py`
- Modify: `tests/unit/test_ingest_event_market_capture.py`
- Modify: `tests/integration/test_ingest_enriched_events.py`
- Modify: `tests/architecture/test_src_domain_architecture.py`

- [ ] Move provider dataclasses to `types.py`.
- [ ] Move concrete OKX adapters and chain mapping to `okx.py`.
- [ ] Move GMGN gateway/provider adapter to `gmgn.py`.
- [ ] Move Binance profile adapters to `binance.py`.
- [ ] Move OpenAI provider adapters to `openai.py`.
- [ ] Move Marketlane construction to `marketlane.py`.
- [ ] Move cross-provider asset-market assembly and fallback DEX quote provider to `asset_market.py`.
- [ ] Reduce `providers_wiring.py` to a public facade that exports `wire_providers`, `wire_asset_market_providers`, and dataclass types.
- [ ] Update provider unit tests to monkeypatch family modules, not facade-private functions.
- [ ] Update architecture guard now: `app/runtime/provider_wiring/**` is the only provider-wiring package allowed to join `integrations.*` with domain provider protocols.
- [ ] Keep all other runtime/app/surface/domain files outside that allowlist.
- [ ] Verify: `uv run pytest tests/unit/test_providers_wiring.py tests/unit/test_provider_capabilities.py tests/unit/test_event_market_capture.py tests/unit/test_ingest_event_market_capture.py tests/integration/test_ingest_enriched_events.py tests/architecture/test_src_domain_architecture.py -q`.

### Task 7: Split worker construction by domain factory

**Files:**
- Create: `src/parallax/app/runtime/worker_factories/__init__.py`
- Create: `src/parallax/app/runtime/worker_factories/ingestion.py`
- Create: `src/parallax/app/runtime/worker_factories/asset_market.py`
- Create: `src/parallax/app/runtime/worker_factories/token_intel.py`
- Create: `src/parallax/app/runtime/worker_factories/pulse.py`
- Create: `src/parallax/app/runtime/worker_factories/watchlist.py`
- Create: `src/parallax/app/runtime/worker_factories/notifications.py`
- Create: `src/parallax/app/runtime/worker_factories/enrichment.py`
- Create: `src/parallax/app/runtime/worker_factories/harness.py`
- Modify: `src/parallax/app/runtime/bootstrap.py`
- Modify: `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] Move each worker construction block out of `_construct_workers`.
- [ ] Keep disabled placeholders and canonical key enforcement in one small central function.
- [ ] Make each factory return `dict[str, WorkerBase]` for only its owned worker keys.
- [ ] Add ingestion factory or central collector injection so `runtime.workers["collector"] is runtime.collector` when collector is enabled.
- [ ] Notifications factory must construct `notification_rule` and `notification_delivery` together so they share one `_LocalWakeWaiter`.
- [ ] Delete the old monolithic `_construct_workers` body after the factories are wired.
- [ ] Verify: `uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py -q`.

### Task 8: Move OpenAI Pulse orchestration out of `integrations`

**Files:**
- Create: `src/parallax/domains/pulse_lab/services/agent_tool_runtime.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py`
- Modify: `src/parallax/domains/pulse_lab/providers.py`
- Modify: `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/parallax/integrations/openai_agents/tools/__init__.py`
- Modify: `src/parallax/integrations/openai_agents/tools/_context.py`
- Modify: `src/parallax/integrations/openai_agents/tools/recent_tweets.py`
- Modify: `src/parallax/integrations/openai_agents/tools/price_action.py`
- Modify: `src/parallax/integrations/openai_agents/tools/official_profile.py`
- Modify: `tests/unit/integrations/openai_agents/tools/test_tools.py`
- Modify: `tests/unit/test_pulse_decision_agent_client.py`
- Modify: `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`
- Modify: `tests/architecture/test_src_domain_architecture.py`
- Modify: `src/parallax/domains/pulse_lab/ARCHITECTURE.md`

- [ ] Move Pulse-specific tool query assembly, prompt contract assembly, supporting evidence validation, URL enrichment, and harness hash input assembly into `domains/pulse_lab/services`.
- [ ] Domain `agent_tool_runtime.py` must be pure Python and must not import `agents`, OpenAI SDK classes, or integration modules.
- [ ] `PulseToolContext` carries an injected tool runtime; OpenAI function-tool wrappers call context methods and do not import domain queries/services.
- [ ] Keep `integrations/openai_agents` responsible only for SDK calls, function-tool wrapper registration, structured output parsing, safety net calls, and external adapter errors.
- [ ] Add architecture guard: `integrations/openai_agents` may import domain provider protocols/types only, not domain queries/services.
- [ ] Verify: AST import scan shows no `integrations/openai_agents` imports from `domains.pulse_lab.queries` or `domains.pulse_lab.services`.
- [ ] Verify: `uv run pytest tests/unit/integrations/openai_agents tests/unit/domains/pulse_lab tests/unit/test_pulse_decision_agent_client.py -q`.

## Phase 3 — Pulse Core Split

### Task 9: Split PulseRepository by table cluster and session contract

**Files:**
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_candidates_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_runs_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_harness_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py`
- Create: `src/parallax/domains/pulse_lab/repositories/pulse_playbooks_repository.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Modify: `src/parallax/app/surfaces/api/routes_pulse.py`
- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Modify: `src/parallax/app/runtime/bootstrap.py`
- Modify: `tests/integration/test_pulse_repository.py`
- Modify: `tests/integration/test_signal_pulse_service_decision_v2.py`
- Modify: `tests/integration/test_pulse_desk_e2e.py`
- Modify: `tests/integration/test_pulse_agent_desk_migration.py`
- Modify: `tests/integration/test_api_http.py`
- Modify: `tests/unit/test_signal_pulse_service.py`
- Modify: `tests/unit/test_notification_rules.py`
- Modify: `tests/unit/test_notification_worker_runtime.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] Define the new repository session contract before moving callers: `repos.pulse_admission`, `repos.pulse_jobs`, `repos.pulse_candidates`, `repos.pulse_runs`, `repos.pulse_harness`, `repos.pulse_read`, and `repos.pulse_playbooks`.
- [ ] Move admission/budget/edge/job enqueue SQL that must remain atomic to `pulse_admission_repository.py`.
- [ ] Move job claim, retry, succeeded, failed, dead, and failure-loop SQL to `pulse_jobs_repository.py`.
- [ ] Move candidate upsert/list/read-model SQL to `pulse_candidates_repository.py`.
- [ ] Move `pulse_agent_runs` and `pulse_agent_run_steps` SQL to `pulse_runs_repository.py`.
- [ ] Move harness versions, eval cases, and eval results to `pulse_harness_repository.py`.
- [ ] Move public summary/listing reads to `pulse_read_repository.py`.
- [ ] Move playbook snapshots to `pulse_playbooks_repository.py`.
- [ ] Migrate `SignalPulseService`, API pulse routes, notification rules, bootstrap wiring, and tests away from `repos.pulse`.
- [ ] Update single-writer allowlist to the new Pulse repository files in the same task.
- [ ] Keep `PulseRepository` only as a temporary local migration facade inside this hard-cut branch; delete it before final verification.
- [ ] Verify: `rg -n "class PulseRepository|repos\\.pulse\\b|PulseRepository\\(" src tests` shows no remaining runtime/test dependency except historical docs or explicit deletion tests.

### Task 10: Split PulseCandidateWorker into use-case services

**Files:**
- Create: `src/parallax/domains/pulse_lab/services/pulse_trigger_scanner.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_admission_service.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_job_runner.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_audit_ledger_writer.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_failure_recorder.py`
- Create: `src/parallax/domains/pulse_lab/services/pulse_eval_recorder.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/integration/test_pulse_desk_e2e.py`
- Modify: `tests/integration/test_pulse_agent_desk_migration.py`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`

- [ ] Move scanning and enqueue/admission decisions to `PulseTriggerScanner` and `PulseAdmissionService`.
- [ ] `PulseAdmissionService` owns the cross-table transaction for edge observation, budget claim, job enqueue, and edge admitted state.
- [ ] Move one claimed job execution to `PulseJobRunner`.
- [ ] `PulseJobRunner` owns transaction choreography; writers/recorders receive the same `repos`/`conn` and write with `commit=False`.
- [ ] Preserve LLM-before/after transaction split: pre-LLM running run ledger, post-LLM success ledger, failure ledger.
- [ ] Move `pulse_agent_runs` and `pulse_agent_run_steps` write sequencing to `PulseAuditLedgerWriter`.
- [ ] Move exception classification, failed run finalization, and job failure update to `PulseFailureRecorder`.
- [ ] Move deterministic eval case/result creation to `PulseEvalRecorder`.
- [ ] Add tests: success path writes candidate/run/steps/eval/job done together.
- [ ] Add tests: failure path writes failed run/failed step/eval/job retry-or-dead together.
- [ ] Add test: injected exception before candidate upsert cannot leave a done job.
- [ ] Document: Pulse candidate list/detail remains HTTP/poll; WS only receives derived notifications.
- [ ] Add notification/WS regression proving notification runtime can still read Pulse candidate rows after repo split.
- [ ] Reduce `PulseCandidateWorker.run_once()` to scan, claim, call runner, and report `WorkerResult`.
- [ ] Verify: `uv run pytest tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_desk_e2e.py tests/integration/test_pulse_agent_desk_migration.py tests/unit/test_notification_worker_runtime.py -q`.

### Task 11: Delete compatibility leftovers and obsolete abstractions

**Files:**
- Delete or document/remove from runtime: `src/parallax/app/runtime/job_queue.py`
- Delete or wire/document: `src/parallax/integrations/coingecko/search_client.py`
- Modify: `tests/unit/test_job_queue.py`
- Modify: `tests/integrations/test_coingecko_search.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/TECH_DEBT.md`
- Modify active docs/specs under `docs/superpowers/{plans,specs}/active/` when they still advertise removed current contracts.

- [ ] If `JobQueue` is not adopted by all domain queues in this hard cut, delete it and delete `tests/unit/test_job_queue.py`.
- [ ] If CoinGecko is not a runtime provider in this hard cut, delete the adapter and its tests; otherwise add real settings/wiring/docs in the provider split.
- [ ] Run `rg -n "legacy|compat|fallback_to|tools_enabled|market_overlay|JobQueue|Coingecko" src tests docs web` and classify every hit as historical migration/completed-doc text or remove it.
- [ ] Do not allow removed contracts to remain in active docs/specs; update or archive superseded active plans.
- [ ] Update docs to reflect the new module map and remove stale wording.

### Task 12: Add architecture guards for the new shape

**Files:**
- Modify: `tests/architecture/test_src_domain_architecture.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Create: `tests/architecture/test_backend_decomposition_contracts.py`

- [ ] Add guard that `app/surfaces/api/http.py` cannot exceed 250 LOC and cannot define more than `create_api_router` plus route inclusion glue.
- [ ] Add guard that `app/runtime/providers_wiring.py` is facade-only and concrete provider classes live under `app/runtime/provider_wiring/`.
- [ ] Add guard that `app/runtime/bootstrap.py` does not contain monolithic worker construction blocks.
- [ ] Add guard that `integrations/openai_agents` does not import `domains.pulse_lab.queries` or `domains.pulse_lab.services`.
- [ ] Add guard that `market_overlay` and `tools_enabled` do not appear in runtime/public contract paths, generated OpenAPI, generated TS, hand-authored frontend contracts, or active specs/plans.
- [ ] Add guard that runtime/tests do not depend on `repos.pulse` or `class PulseRepository`.
- [ ] Add guard that `parallax.cli` exports only the hard-cut public CLI entrypoint.
- [ ] Verify: `uv run pytest tests/architecture -q`.

## Final Verification

- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run mypy src`.
- [ ] Run `uv run pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract"`.
- [ ] Run `uv run pytest tests/integration -m integration`.
- [ ] Run `uv run pytest tests/e2e -m e2e`.
- [ ] Run `uv run python -m compileall src tests`.
- [ ] Run `cd web && npm run typecheck && npm run test -- --run`.
- [ ] Run `make check-all` and paste full output into a verification artefact.
- [ ] Regenerate docs/contracts after API/CLI/public schema changes: `make regen-contract docs-cli-help`.
- [ ] If any Alembic migration changes appear, also run `make docs-db-schema` and `uv run pytest tests/integration/test_docs_generated.py -q`.
- [ ] Record skipped tests, coverage, e2e golden path, diff summary, and remaining risks in verification.

## Rollback

This is a hard-cut refactor and is not safely rolled back piecemeal. Rollback strategy is branch-level revert before merge, or full PR revert after merge. No migration is expected unless a later implementation task adds schema cleanup; if schema cleanup appears, it must include an explicit Alembic downgrade or a documented non-reversible hard-cut note.

## Acceptance Criteria

- [ ] `ruff`, `mypy`, unit, architecture, contract, integration, e2e, compileall, web tests, and `make check-all` pass in the worktree.
- [ ] `rg -n "market_overlay|tools_enabled|fallback_to|_compat_|legacy_runtime_payload" src tests web docs/CONTRACTS.md docs/generated/openapi.json web/src/lib/types/openapi.ts web/src/lib/types/frontend-contracts.ts docs/superpowers/plans/active docs/superpowers/specs/active` has no runtime/current-contract hits.
- [ ] `app/surfaces/api/http.py`, `app/surfaces/cli/main.py`, `app/runtime/providers_wiring.py`, and `app/runtime/bootstrap.py` are facade-level modules, not behavior centers.
- [ ] `app/runtime/provider_wiring/**` is the only provider composition package, and no other runtime/surface/domain file joins concrete integrations with domain provider protocols.
- [ ] `runtime.workers` always contains canonical worker keys, and enabled collector still maps to the prebuilt runtime collector.
- [ ] Pulse run execution is testable through scanner/admission/runner/audit/failure/eval services without opening a 1000+ LOC worker file.
- [ ] Pulse repository table clusters are separately owned, cross-table transactions are explicitly owned, and the old aggregate `PulseRepository` facade is removed.
- [ ] Docs `ARCHITECTURE.md`, `CONTRACTS.md`, `WORKERS.md`, generated contracts, and active specs/plans match the new hard-cut runtime.
