# Verification — Daily Macro SPY Judgment

**Status**: Verified
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/plan.md`
**Branch**: `codex/daily-macro-spy-judgment`
**Worktree**: `.worktrees/daily-macro-spy-judgment/`
**Approved by**: delegated user goal and GitHub Issue #6
**Approved at**: 2026-07-23

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Point-in-time full EvidencePack. | Pass | `make test-integration` exited 0; the real-provider shadow compiled 209 frozen facts for session 2026-07-22 with a stable pack hash. |
| AC2 - Complete six-page, official-text, News, lineage, and hash evidence. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/domains/macro_intel/test_macro_evidence_pack.py -q` and `make test-integration` exited 0; the bounded Agent view selected 34 page-referenced citations while the immutable pack retained all 209 facts and exclusions. |
| AC3 - Real DeepAgents Analyst and native isolated Reviewer. | Pass | `uv run pytest tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q` and the `uv run python - <<'PY'` provider shadow exited 0; runtime used `deepagents==0.6.12`, one Analyst submission, one native `task`, and Reviewer `pass`. |
| AC4 - Deterministic gates and bounded review. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/domains/macro_intel/test_macro_evidence_pack.py -q` and `uv run pytest tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q` exited 0 across schema, reference, health, pass/revise/block, one-revision, short-citation expansion, and renderer gates. |
| AC5 - Simple SPY-only four-state output. | Pass | `make check` exited 0; the real degraded shadow produced only SPY 5D=`no_call` and 20D=`no_call`, with no scores, probabilities, confidence, positions, or trade fields. |
| AC6 - Fail-closed publication semantics. | Pass | `make test-integration` exited 0 with blocked/retryable/failed paths and no partial publication; the provider shadow called no publication path. |
| AC7 - Immutable and idempotent publications. | Pass | The focused PostgreSQL command and `make test-integration` exited 0, proving immutable triggers, one session identity, zero-call replay, and zero publication rewrites. |
| AC8 - Safe one-writer daily runtime. | Pass | The focused 62-test command and `make test-integration` exited 0 across calendar, settle, catch-up, lease/retry, transaction-free model I/O, and atomic finalization. |
| AC9 - Separate append-only 5D/20D outcomes. | Pass | `make test-integration` exited 0 with session-aware 5D/20D outcome insertion and immutable judgment preservation. |
| AC10 - Persisted-only latest and explicit-session read. | Pass | `make regen-contract && uv run pytest tests/unit/test_docs_contract.py tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q` exited 0; API tests prove current/historical/stale/job/missing states and zero request-time model calls. |
| AC11 - Existing Macro and Product-AI boundaries preserved. | Pass | `make check`, `make test-integration`, and `make test-e2e && make test-golden` exited 0; the running operator service remained healthy on migration 0192 and the six-page lane stayed deterministic. |
| AC12 - Full installed runtime and real-provider shadow proof. | Pass | `make docker-check && docker compose build app` and `uv run python - <<'PY'` exited 0; the isolated runtime reached migration 0193 with pinned versions, and the distinct-model Analyst=`gpt-5.5` / Reviewer=`gpt-5.6-terra` shadow closed one revision with `pass` in 85.22 seconds. |

Deviations from spec:

- None. The user-approved simplification is the implemented strict schema: macro state, bounded pressures, SPY 5D/20D calls, and bounded counterevidence.

Deviations from plan:

- The real-provider smoke intentionally invoked the frozen Analyst/Reviewer boundary without inserting a job or publication into the operator database. Persisted publication/API behavior was proved separately against real PostgreSQL, and the installed image was proved against an isolated migrated database.
- The configured operator worker remains disabled. Its operator-owned settings now explicitly select Analyst `openai/gpt-5.5` and Reviewer `openai/gpt-5.6-terra` through one shared provider endpoint.

## Verification commands

```text
$ uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/domains/macro_intel/test_daily_macro_judgment_worker.py tests/unit/domains/macro_intel/test_macro_evidence_pack.py tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py tests/unit/test_api_macro_contract.py tests/unit/test_docs_contract.py tests/unit/test_worker_factories.py tests/unit/test_worker_settings.py tests/unit/test_macro_decision_workbench_migration_contract.py tests/unit/test_postgres_schema.py tests/architecture/test_product_ai_hard_delete.py -q
62 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/domains/macro_intel/test_macro_evidence_pack.py -q
8 passed
exit code: 0

$ uv run pytest tests/integration/test_daily_macro_judgment_migration.py -q
1 passed
exit code: 0

$ uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q
1 passed
exit code: 0

$ uv run pytest tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q
4 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment_worker.py tests/architecture/test_kiss_runtime_invariants.py -q
17 passed
exit code: 0

$ uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
14 passed
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q
17 passed
exit code: 0

$ uv run pytest tests/unit/test_docs_contract.py tests/contract/test_openapi_drift.py -q
5 passed
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
6 passed
exit code: 0

$ uv run pytest tests/integration/test_daily_macro_judgment_migration.py tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q
2 passed
exit code: 0

$ make regen-contract && uv run pytest tests/unit/test_docs_contract.py tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
OpenAPI JSON and TypeScript regenerated; 15 passed.
exit code: 0

$ make check
Ruff and format passed; mypy passed for 529 source files; frontend typecheck, lint, architecture 70/70, and format passed; Python unit/architecture/contract 2591 passed with 1 opt-in provider-drift skip.
exit code: 0

$ make test-integration
242 passed in 841.87 seconds.
exit code: 0

$ make test-e2e && make test-golden
E2E 5 passed; golden 4 passed.
exit code: 0

$ uv run python - <<'PY'
Redacted real-provider shadow receipt: session=2026-07-22; pack_hash_prefix=af3af5872076; health=degraded; full facts=209; Agent citations=34; Analyst=openai/gpt-5.5; Reviewer=openai/gpt-5.6-terra; deepagents=0.6.12; submissions=2; native task calls=2; dispositions=revise,pass; SPY 5D=no_call; SPY 20D=no_call; all persisted-form refs belong to the frozen pack; publication mutation=false; elapsed=85.22s.
exit code: 0

$ make docker-check && docker compose build app
Exact source image built; deepagents 0.6.12 and langchain-litellm 0.7.0 installed.
exit code: 0

$ PARALLAX_POSTGRES_PORT=56533 docker compose -p parallax_macro_shadow up -d postgres && PARALLAX_POSTGRES_PORT=56533 docker compose -p parallax_macro_shadow run --rm migrate
Fresh isolated PostgreSQL migrated through 20260723_0193.
exit code: 0

$ PARALLAX_POSTGRES_PORT=56533 docker compose -p parallax_macro_shadow run -d --name parallax_macro_shadow_app --no-deps -p 127.0.0.1:58765:8765 app
Isolated exact-source application container started.
exit code: 0

$ curl -fsS http://127.0.0.1:58765/healthz && curl -fsS http://127.0.0.1:58765/readyz && docker exec parallax_macro_shadow_app parallax db health
Health ok; readiness ok; migration_version=expected_migration_version=20260723_0193; composition ok.
exit code: 0

$ GMGN_TEST_POSTGRES_DSN="[redacted localhost:56533 DSN]" uv run python scripts/regen_db_schema.py
Generated schema contains macro_judgment_jobs, macro_judgment_publications, and macro_judgment_outcomes at Alembic head.
exit code: 0

$ curl -fsS http://127.0.0.1:8765/healthz && curl -fsS http://127.0.0.1:8765/readyz
Existing operator service remained healthy and unchanged at migration 20260723_0192.
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
SDD work index is current.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-23-daily-macro-spy-judgment --gate verify
verify gate passed.
exit code: 0
```

## Diff summary

- Domain and storage: frozen point-in-time EvidencePack, minimal strict DailyMacroJudgment, immutable session jobs/publications, append-only outcomes, and migration 0193.
- Model execution: real least-capability DeepAgents Analyst plus one native-task Reviewer, distinct explicit role models, bounded revision, and short citation IDs expanded deterministically to full frozen references.
- Runtime and read surface: one disabled-by-default daily worker, persisted-only typed API, deterministic Chinese memo, generated OpenAPI/TypeScript/database schema, and no frontend redesign.
- Safety: global fail-closed gates, degraded-horizon `no_call`, no score/probability/position/trading fields, no Agent browser/provider/SQL/shell/filesystem/memory access, and unchanged deterministic six-page Macro.

## Risks observed

- The live 2026-07-22 evidence pack is degraded because some required point-in-time capabilities are unavailable under the conservative availability policy. This correctly forces both horizons to `no_call`.
- The distinct operator model pair passed the forced-tool Analyst→Reviewer workflow. Enabling the worker remains a separate explicit operator decision because it begins recurring provider spend.
- The isolated PostgreSQL volume `parallax_macro_shadow_parallax-postgres` is intentionally retained for bounded audit replay; its containers and network were removed.

## Follow-ups

- Do not enable the experimental worker until the operator intentionally updates the worker model override and accepts daily provider cost. No further product scope is required for this spec.
