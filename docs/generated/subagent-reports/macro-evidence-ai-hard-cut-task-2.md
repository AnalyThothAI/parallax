# Subagent Report - 2026-07-23-macro-evidence-ai-hard-cut / Task 2

Mode: write-allowed

## Findings

- The production News product-AI chain was hard-deleted: the story-brief prompt, provider client/interface, admission and policy services, input/stage/validation helpers, types, repositories, worker, provider wiring, bootstrap composition, runtime status/telemetry, worker factory entry, and worker manifest entry are gone. The surviving manifest declares `news_item_process` and the single `news_page_projection` writer only (`src/parallax/app/runtime/worker_manifest.py:85-97`).
- News processing now persists deterministic entity, token-mention, fact-candidate, content-classification, market-scope, and story-identity facts, then enqueues only page reprojection (`src/parallax/domains/news_intel/runtime/news_item_process_worker.py:76-173`). The News page row is rebuilt from those persisted facts with stable story identity and contains no model admission/output or notification eligibility (`src/parallax/domains/news_intel/services/news_page_projection.py:14-87`).
- News projection repair and dirty-target handling now expose only the `page` projection. News repositories and page SQL no longer read or write story-agent ledgers or AI-derived page columns.
- Token/Search pseudo-AI was hard-deleted: `search_agent_brief.py` and `token_radar_narrative_admission.py` are gone, their read-model consumers were removed, rank-source `llm_*` inputs and semantic-catalyst storage/payload wiring were removed, and the surviving transparent factor snapshot contains only `social_heat`, `social_propagation`, and `timing_risk` (`src/parallax/domains/token_intel/scoring/factor_snapshot.py:34-102`). Projection/factor versions were bumped so old derived rows cannot masquerade as current rows.
- The `news_high_signal` rule and its aggregation/reactivation path were removed. The rule engine now emits only source-backed watched-account activity and watched-account token alerts (`src/parallax/domains/notifications/services/notification_rules.py:23-29`), with positive unit coverage retained.
- Provider-neutral structured-JSON execution remains importable and tested but dormant in production composition. `AgentStageSpec` accepts a required nonblank caller-owned lane instead of embedding a News lane (`src/parallax/platform/agent_execution.py:89-111`), while bootstrap constructs no model gateway or product consumer (`src/parallax/app/runtime/bootstrap.py:75-117`).
- No compatibility lane, alias, renamed pseudo-AI brief, deterministic replacement prose, or provider call inside a database transaction was introduced.

## Scope Adherence

Owned scope: pass

Conflict set: pass

All implementation diffs are inside the Task 2 touch set. A transient edit to `src/parallax/app/operations/queue_health.py` was restored after the scope audit, so it is absent from the final Task 2 diff. No Task 2 implementation change remains under API surfaces, Alembic migrations, Macro, or `web/`. This report itself is the handoff-required generated evidence artifact.

## Changed Files

The implementation changed or deleted files within these exact owned groups:

- `src/parallax/app/operations/news.py`
- `src/parallax/app/runtime/**`
- `src/parallax/domains/news_intel/**`
- `src/parallax/domains/token_intel/**`
- `src/parallax/domains/notifications/**`
- `src/parallax/platform/agent_*.py`
- `src/parallax/integrations/model_execution/**`
- `tests/unit/domains/news_intel/**`
- `tests/unit/domains/token_intel/**`
- `tests/unit/domains/notifications/**`
- `tests/unit/integrations/model_execution/**`

Deleted production units include the News story-brief prompt/client/interfaces/repository/worker/services/types, Token SearchAgentBrief and narrative-admission read models, and the News-specific model-execution client. Modified units cover fact-only News projection/repositories/workers, transparent Token factors/repositories/read models, watched-account-only notification rules/runtime/repository semantics, production runtime composition, and provider-neutral model-execution primitives. Retired-product unit tests were deleted; surviving fact-path and dormant-library tests were updated.

## Required Reading Evidence

Task classification: Product LLM Agent Run; Read Model Change Review; Worker/runtime composition review.

- `AGENTS.md`: PostgreSQL material-fact truth, single-writer rebuildable read models, stable product keys, zero-write unchanged projections, and bounded interval catch-up.
- `docs/agent-playbook/task-reading-matrix.md`: Product LLM Agent Run and Read Model Change Review reading/verification boundaries.
- `docs/AGENT_EXECUTION.md`: former product News lane, shared execution/audit semantics, and provider-start/no-start distinctions.
- `docs/ARCHITECTURE.md`: Kappa/CQRS fact, read-model, control-plane, and provider-input boundaries.
- `docs/RELIABILITY.md`: durable catch-up and current-read-model invariants.
- `docs/WORKERS.md`: cross-domain worker inventory, ownership, and runtime lifecycle.
- `docs/WORKER_FLOW.md`: claim, retry, terminalization, bounded catch-up, and projection writer rules.
- `docs/agent-playbook/read-model-change-checklist.md`: stable identity, one writer, idempotency, and non-empty-state review checklist.
- `src/parallax/domains/news_intel/ARCHITECTURE.md`, `src/parallax/domains/token_intel/ARCHITECTURE.md`, and `src/parallax/domains/notifications/ARCHITECTURE.md`: owning domain facts, read models, and consumer boundaries.
- `src/parallax/platform/agent_execution.py` and `src/parallax/integrations/model_execution/execution_gateway.py`: provider-neutral structured-output, capability, audit, hashing, capacity, timeout, and failure primitives retained by the hard cut.
- `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/bootstrap.py`, `src/parallax/app/runtime/worker_factories/news_intel.py`, and current provider wiring: production composition and one-writer inventory inspected before and after deletion.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`, `plan.md`, and `tasks.md`: AC11/AC12, hard-cut scope, fact-path replacement boundary, dormant-library constraint, and exact Task 2 gate.

## Verification Evidence

Fresh exact Task 2 gate after the final source/test edits:

```text
$ uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q
........................................................................ [ 15%]
........................................................................ [ 30%]
........................................................................ [ 46%]
........................................................................ [ 61%]
........................................................................ [ 76%]
........................................................................ [ 92%]
....................................                                     [100%]
468 passed in 4.15s
exit code: 0
```

Additional deletion seam:

```text
$ uv run pytest tests/architecture/test_product_ai_hard_delete.py -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0
```

Changed-owned-file Ruff result: `All checks passed!`, exit code 0. Python compile-all over the owned source/test groups passed, and `git diff --check` passed after trailing-blank cleanup.

## Remaining Risks

- Root-owned config, API/CLI, health/ops, schemas, and their tests still contained legacy News worker/rule and News/Token pseudo-AI contract references at the Task 2 handoff boundary; Task 4 must remove them without compatibility fields. `src/parallax/app/operations/queue_health.py` also needs its root-owned retired worker discriminator removed.
- Task 3 must land the non-empty-state Alembic hard cut that drops News agent tables/page AI columns, Token semantic/`llm_*` columns, queue constraints, and retired notification rows. Fact-only repository SQL and the bumped projection versions require that schema cut before full runtime validation.
- Frontend and canonical documentation are separate tasks and must remove the retired consumers/descriptions. The current News domain architecture map intentionally remained untouched because documentation is outside Task 2 implementation scope.
- This task did not run a live PostgreSQL migration/runtime. Parent acceptance still requires the migration integration gate, API/frontend gates, full architectural residual scan, and full repository verification after all parallel tasks merge.
