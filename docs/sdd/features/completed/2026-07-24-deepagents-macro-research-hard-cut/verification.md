# Verification — DeepAgents Macro Research Hard Cut

**Status**: Verified
**Date**: 2026-07-24
**Owning spec**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut/plan.md`
**Branch**: `codex/deepagents-macro-hard-cut`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Approved by**: user
**Approved at**: 2026-07-24

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Material Macro facts remain. | Pass | `uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_failed_retry.py tests/integration/test_macro_research_publication.py -q` exited 0 against non-empty PostgreSQL; migration 0194 retained observations and sync ledgers while dropping derived judgment storage. |
| AC2 - One completed-session deep runtime interface. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_completed_session_macro.py tests/unit/domains/macro_intel/test_macro_research.py tests/unit/domains/macro_intel/test_macro_research_repository.py tests/unit/domains/macro_intel/test_macro_research_worker.py tests/unit/integrations/model_execution/test_macro_research_deepagent.py tests/unit/test_macro_failed_retry.py tests/unit/test_check_macro_research_publication.py -q` exited 0 across the one `CompletedSessionMacro.run/read` seam, scheduler, lease heartbeat, and formal retry path. |
| AC3 - Native DeepAgents capabilities and no forced FSM. | Pass | `uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23` exited 0 and reported native todo, checkpoint filesystem write, dynamic task delegation, structured output, all three specialists, 11 model calls, and DeepAgents 0.6.12. |
| AC4 - Agent-owned evidence selection and semantics. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_completed_session_macro.py tests/unit/domains/macro_intel/test_macro_research.py tests/unit/domains/macro_intel/test_macro_research_repository.py tests/unit/domains/macro_intel/test_macro_research_worker.py tests/unit/integrations/model_execution/test_macro_research_deepagent.py tests/unit/test_macro_failed_retry.py tests/unit/test_check_macro_research_publication.py -q` exited 0; independent runtime audit also read beyond offset 10,000 and found no total evidence-depth cap or application-authored research taxonomy. |
| AC5 - Mechanical validation only. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/unit/test_api_macro_contract.py -q` exited 0; production contains envelope/session/citation checks but no language, readiness, coverage, direction, confidence, safety-policy, or `no_call` gate. |
| AC6 - Immutable idempotent publication. | Pass | `uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_failed_retry.py tests/integration/test_macro_research_publication.py -q` exited 0 across immutable triggers, one publication per session, checkpoint resume, and zero-call replay. |
| AC7 - Persisted-only read API. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/unit/test_api_macro_contract.py -q` exited 0; only `GET /api/macro/research` remains and API reads invoke neither model nor provider. |
| AC8 - One responsive Chinese research page. | Pass | `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroResearchHardCut.test.ts` exited 0; fresh Playwright inspection at 1200x949 and 390x844 found zero page/center horizontal overflow, no citation overlap, 27 rendered citations, and zero console warning/error. |
| AC9 - Deterministic Macro paths absent. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/unit/test_api_macro_contract.py -q` exited 0; migration/runtime audit found no old projection/judgment tables, worker, API, route, or six-page/eight-lane/Daily implementation. |
| AC10 - Dormant LLM middleware absent. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/unit/test_api_macro_contract.py -q` exited 0; the generic execution gateway, output strategy, usage/capability/hash wrappers, and direct LiteLLM dependency are absent. |
| AC11 - Real provider and blind quality proof. | Pass | `uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23` exited 0 for immutable attempt 5: 4 agent-authored sections, 4 gaps, 27 closed citations, all three specialists, and artifact hash `a0b603ed4330ce7fa9083bda26e439366b38b2af9160db46dc7bd0a5fa977bbf`; independent blind review passed it as professional cautious research/watchlist with the limitations recorded below. |
| AC12 - Full selected verification and SDD gates. | Pass | `make check` exited 0: Ruff/format, mypy on 513 files, frontend typecheck/lint/68 architecture/format checks, 2415 Python tests passed, one opt-in provider-drift test skipped, and compileall passed. |

## Verification commands

```text
$ uv run pytest tests/unit/domains/macro_intel/test_completed_session_macro.py tests/unit/domains/macro_intel/test_macro_research.py tests/unit/domains/macro_intel/test_macro_research_repository.py tests/unit/domains/macro_intel/test_macro_research_worker.py tests/unit/integrations/model_execution/test_macro_research_deepagent.py tests/unit/test_macro_failed_retry.py tests/unit/test_check_macro_research_publication.py -q
41 passed in 1.86s.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_research.py -q
7 passed in 0.05s.
exit code: 0

$ uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_failed_retry.py tests/integration/test_macro_research_publication.py -q
3 passed in 15.12s.
exit code: 0

$ uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_publication.py -q
2 passed in 13.87s.
exit code: 0

$ uv run pytest tests/unit/integrations/model_execution/test_macro_research_deepagent.py -q
8 passed in 1.53s.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_research_worker.py tests/unit/test_worker_factories.py tests/unit/test_worker_settings.py -q
19 passed in 5.24s.
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/unit/test_api_macro_contract.py -q
32 passed in 2.28s.
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q
17 passed in 3.87s.
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
6 passed in 0.04s.
exit code: 0

$ uv run pytest tests/unit/test_docs_contract.py -q
1 passed in 0.03s.
exit code: 0

$ make regen-contract && uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
OpenAPI JSON and TypeScript regenerated; 19 passed.
exit code: 0

$ make docs-generated && make regen-contract && uv run pytest tests/unit/test_docs_contract.py tests/contract/test_openapi_drift.py -q
Generated CLI, score-version, WebSocket, SDD, OpenAPI, and TypeScript contracts; 5 passed.
exit code: 0

$ cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroResearchHardCut.test.ts
2 files and 19 tests passed.
exit code: 0

$ uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23
ok=true; session=2026-07-23; attempt=5; model=openai/gpt-5.6-terra; deepagents=0.6.12; model_calls=11; specialists=evidence-analyst,cross-asset-challenger,skeptical-editor; verified citations=27; prompt=macro_research_parent_v4; workflow=deepagents_macro_research_v3; artifact_hash=a0b603ed4330ce7fa9083bda26e439366b38b2af9160db46dc7bd0a5fa977bbf.
exit code: 0

$ docker compose -p parallax up -d app
Migration container exited successfully and the exact-source application image sha256:edacc9bdea3ab8c91255441caa87d5f54d2f6253b43f6e4be564ad0e4d881799 started.
exit code: 0

$ curl --fail --silent http://localhost:8765/readyz >/dev/null
Application ready; actual and expected migration are both 20260724_0195.
exit code: 0

$ for route in /macro/overview /macro/rates-inflation /macro/growth-labor /macro/liquidity-funding /macro/credit /macro/cross-asset; do http_code=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://localhost:8765${route}"); printf '%s %s\n' "$http_code" "$route"; done
All six retired browser routes returned 404.
exit code: 0

$ make check
Ruff and format passed; 794 files formatted; mypy passed for 513 source files; frontend typecheck, ESLint, 68/68 architecture checks, and Prettier passed; Python unit/architecture/contract suite reported 2415 passed and 1 opt-in provider-drift skip; compileall passed.
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
SDD work index is current.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-24-deepagents-macro-research-hard-cut --gate verify
Verify gate passed.
exit code: 0

$ git diff --check
No whitespace errors.
exit code: 0
```

Browser receipt:

- Fresh production tab loaded `/macro` with API requests for bootstrap,
  persisted Macro research, status, and notifications all returning 200.
- Desktop 1200x949 and mobile 390x844 both had
  `document.scrollWidth - clientWidth = 0` and center-column overflow `0`.
- The mobile `c_tariff_statement` citation identifier ended above its evidence
  detail (`labelBottom=6745.07`, `detailTop=6756.27`), so the former overlap is
  closed.
- The browser rendered the complete Chinese attempt-5 publication and 27
  citations with zero console warnings or errors.

Real-run receipt:

- Attempts 1-3 exposed an application-owned 100 KB tool-result rejection. The
  rejection and total paging cap were removed in favor of DeepAgents native
  filesystem offload and open-ended offset paging.
- Attempt 4 invoked all three specialists and reached checkpoint 123, then
  exposed a whole-research 480-second `asyncio.wait_for` cap. That cap and its
  configuration field were deleted; only per-provider-request and
  execute/database operational timeouts remain.
- Attempt 5 resumed the durable checkpoint, reached 125 checkpoints, and
  published once. The lease heartbeat is owner-CAS crash recovery, not a
  semantic or wall-clock capability gate.

## Deviations, risks, and omitted evidence

- The blind artifact-only review judged the publication professionally written,
  internally cautious, and usable as a Macro watchlist. It did not judge it
  sufficient as stand-alone causal or portfolio-allocation research.
- Remaining evidence weaknesses are visible rather than hidden by a gate:
  real-yield evidence is stale and point-in-time; IG/HY, VIX, SKEW, and CCC/BB
  lack changes or historical percentiles; the IWM-relative-SPY claim lacks a
  direct SPY citation; VIX3M does not prove short-tenor implied volatility;
  USO is a proxy; and several policy/inflation sources are secondary.
- Those weaknesses are recorded as data and future agent-research improvements.
  No deterministic score, safety layer, fixed asset checklist, or publication
  blocker was reintroduced to conceal or mechanically arbitrate them.
- The operator explicitly cancelled backup work and authorized direct forward
  migration. The partial PostgreSQL dump and the temporary workers configuration
  backup were deleted; no migration backup or downgrade path remains. Material
  facts are healthy and PostgreSQL is ready at migration 0195.
- The opt-in live GMGN provider-drift test was not run; `make check` skipped it
  by contract. It is unrelated to the Macro DeepAgents publication.

## Independent validation

- A separate implementation validator returned `PASS`: one publication/read
  contract, native DeepAgents topology, no semantic/safety judgment gates, no
  whole-run timeout, retired storage and public routes absent, and the live
  publication/browser path healthy.
- A separate blind semantic reviewer returned `PASS with limitations`: useful
  professional monitoring research, while explicitly rejecting any claim that
  the present evidence alone supports a causal or allocation-grade conclusion.
