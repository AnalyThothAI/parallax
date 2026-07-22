# Verification — Backend KISS whole-chain simplification

**Status**: In Progress
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/plan.md`
**Branch**: `codex/backend-kiss-deep-audit`
**Worktree**: `.worktrees/backend-kiss-deep-audit/`
**Approved by**: delegated `/goal` for whole-architecture KISS review and implementation
**Approved at**: 2026-07-22
**Diff**: pending final `git diff main...codex/backend-kiss-deep-audit` review.

The plan and spec are the contract. This record intentionally contains no completion claim while the audit and implementation are active.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - whole-chain classified ownership map | In Progress | Tasks 1–4 and parent validation are in progress. |
| AC2 - retained single owner/transaction/recovery after cuts | In Progress | No production cut is authorized yet. |
| AC3 - behavior-focused simplified tests | In Progress | No test cut is authorized yet. |
| AC4 - exact proportional verification | In Progress | Root architecture baseline is recorded below; final gates are not run. |
| AC5 - conflict set preserved and net-negative targeted diff | In Progress | Final diff does not yet exist. |

Deviations from spec:

- None recorded.

Deviations from plan:

- None recorded.

## Verification commands

Final `make check-all` output is not yet available. It will be recorded in full only after implementation and targeted repair loops are complete.

```text
$ uv run pytest -q tests/unit/test_worker_base_runtime.py tests/unit/test_run_worker_once.py tests/unit/test_worker_settings.py tests/unit/test_settings.py
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed in 1.25s
exit code: 0

$ uv run pytest -q tests/unit/test_collector_service.py tests/contract/test_provider_protocol_fixtures.py tests/unit/test_token_intent_rebuild_runtime.py tests/integration/test_token_intent_rebuild.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py
...........................................                              [100%]
43 passed in 15.27s
exit code: 0

$ uv run pytest -q tests/unit/test_provider_capabilities.py tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/test_okx_clients.py tests/unit/integrations/news_feeds tests/unit/test_queue_terminal.py tests/integration/test_postgres_audit.py
........................................................................ [ 71%]
.............................                                            [100%]
101 passed in 26.69s
exit code: 0

$ uv run pytest -q tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/test_queue_terminal.py
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 5.44s
exit code: 0

$ uv run pytest -q tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_queue_health.py tests/unit/test_providers_wiring.py tests/unit/domains/asset_market/test_chain_identity.py tests/architecture/test_kiss_runtime_invariants.py
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 8.56s
exit code: 0
```

## Baseline diagnostics

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 1.96s
exit code: 0

$ uv run ruff check --select C90 src tests
Found 36 errors.
exit code: 1

$ uv run ruff check .
All checks passed!
exit code: 0

$ uv run pytest -q tests/unit tests/architecture tests/contract
3467 passed, 1 skipped in 44.54s
exit code: 0
```

The C90 command is an audit diagnostic, not the configured Ruff gate and not a blanket refactor target.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not run | repository threshold | In Progress |
| branch | Not run | repository threshold | In Progress |

## Skipped tests

Final skipped-test count: not yet measured.

## E2E golden path

- [ ] `/readyz` returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] `/api/recent` returned the injected event
- [ ] WS `/ws/live` pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

## Completion gate

Not run. The feature remains In Progress.

## Other commands run

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 1.96s
exit code: 0
```

The four read-only audit reports also passed their task-bound report validator. No manual UI flow is in scope.

```text
$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0
```

## Diff summary

Current files added:

- `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/{spec,plan,tasks,verification}.md`

Migrations applied:

- None.

Schema or contract changes:

- None authorized.

## Risks observed

- The production and test suites contain large modules and 36 McCabe diagnostics, but these are only candidate hotspots until source-backed review distinguishes cohesive domain logic from accidental complexity.
- Live PostgreSQL physical evidence is outside the initial audit and cannot be inferred from unit tests.

## Follow-ups

- None filed yet; Task 5 will classify findings as implement, defer for live evidence, or reject.
