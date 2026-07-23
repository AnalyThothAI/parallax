# Agent Task Reading Matrix

This matrix routes coding agents to the minimum source-backed context for common Parallax work. It is a navigation layer, not a new source of truth. Canonical product rules still live in `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, domain `ARCHITECTURE.md` files, and code.

Before answering or editing, classify the task below. Read the required files for that category, then add optional files only when the question needs them. Answer must separate: PostgreSQL facts, read models, control plane state, cache/fan-out state, provider raw inputs, and generated artefacts.

For copyable goal/prompt patterns, use `docs/agent-playbook/task-examples.md`. For any change that creates, rewrites, republishes, or reviews a derived read model, also use `docs/agent-playbook/read-model-change-checklist.md`.

## Real Data And Provider Debugging

Use for missing provider rows, icon/profile gaps, Token Radar live data, News source coverage, macro provider freshness, or operator reports from a running service.

Required reading:

- `AGENTS.md` or `CLAUDE.md`
- `docs/SECURITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- The owning domain `src/parallax/domains/<domain>/ARCHITECTURE.md`

Diagnostic commands:

- `uv run parallax config`
- `uv run parallax ops queue-inspect --help`
- The smallest domain-specific `uv run parallax ops ... --help` command before running a live operation

Answer must separate:

- Operator-owned runtime config paths from repository examples.
- Provider raw inputs from persisted facts.
- Queue/control-plane symptoms from product truth.
- Missing/degraded public state from repair actions.

Never print secrets, cookies, tokens, proxy URLs, DSNs, or API keys. Report only redacted booleans, paths, counts, and command outcomes.

## Token Radar Or Public Row Gaps

Use for missing/duplicated Token Radar rows, stale market context, unresolved symbols, social ranking surprises, or scanner/public API mismatches.

Required reading:

- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `src/parallax/domains/token_intel/ARCHITECTURE.md`
- `src/parallax/domains/asset_market/ARCHITECTURE.md`

Diagnostic commands:

- `uv run parallax token-radar --help`
- `uv run parallax ops projection-status`
- `uv run parallax ops validate-projections --sample 100`
- `uv run parallax ops factor-diagnostics --window 5m --scope all --limit 100`
- `uv run pytest tests/architecture/test_kiss_runtime_invariants.py`

Answer must separate:

- `events`, identity, market tick, and enriched event facts.
- `token_radar_current_rows` and publication-state read models.
- Dirty-target/control-plane queues.
- API/frontend display symptoms.

## Worker Backlog Or Stuck Worker

Use for workers that do not catch up, queues that grow, stale read models, timeout loops, or scheduler status gaps.

Required reading:

- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `src/parallax/app/runtime/worker_manifest.py`
- The owning domain `ARCHITECTURE.md`

Diagnostic commands:

- `uv run parallax ops queue-inspect --help`
- `uv run pytest tests/architecture/test_kiss_runtime_invariants.py`

Answer must separate:

- Durable facts from dirty targets and job rows.
- Durable interval catch-up from public route symptoms.
- Worker status contracts from diagnostics-only logs.
- Runtime repair commands from public route behavior.

## Dormant Model Library Change

Use only for isolated provider-neutral execution, capability, hashing, usage,
or structured-output library changes. The production product has no model
consumer, worker, queue, prompt catalog, status lane, or derived model state.

Required reading:

- `docs/AGENT_EXECUTION.md`
- `src/parallax/platform/agent_execution.py`
- `src/parallax/platform/agent_capabilities.py`
- `src/parallax/platform/agent_hashing.py`
- `src/parallax/integrations/model_execution/execution_gateway.py`
- `src/parallax/integrations/model_execution/output_schema.py`
- `src/parallax/integrations/model_execution/structured_json_strategy.py`
- `src/parallax/integrations/model_execution/usage.py`

Diagnostic commands:

- `uv run pytest tests/unit/integrations/model_execution -q`
- `uv run pytest tests/architecture/test_product_ai_hard_delete.py -q`

Answer must separate:

- Dormant library behavior from supported production composition.
- Request/result audit structures from material business facts.
- Provider/schema errors from domain publication, which does not exist for the
  dormant library.
- A proposed product consumer from the current approved scope; a consumer
  requires a new spec.

## Frontend CSS Or Route Shell

Use for `web/src` UI changes, route shell work, responsive layout, CSS architecture, or component ownership.

Required reading:

- `docs/FRONTEND.md`
- `docs/WORKFLOW.md`
- The route or feature owner files under `web/src/features/<feature>/`
- Existing component tests under `web/tests/`

Diagnostic commands:

- `cd web && npm run lint`
- `cd web && npm run typecheck`
- Targeted `npm run test -- <path>` when a component test exists

Answer must separate:

- Feature owner CSS from shared UI primitives.
- Route shell concerns from feature content.
- Frontend contract payloads from backend repair or provider calls.

Use the repo-scoped `parallax-frontend-verification` skill when a UI task needs a fixed local QA loop.

## Read Model Change Review

Use for any change that adds a derived read model, changes current-row identity, changes a projection writer, changes projection catch-up behavior, or reviews read-model correctness.

Required reading:

- `docs/ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/agent-playbook/read-model-change-checklist.md`
- The owning domain `src/parallax/domains/<domain>/ARCHITECTURE.md`

Diagnostic commands:

- `uv run pytest tests/architecture/test_kiss_runtime_invariants.py`
- The smallest domain-specific architecture or integration test covering the changed projection.
- A targeted idempotency/current-row test when the read model writes serving rows.

Answer must separate:

- Material fact writes from derived read-model writes.
- Runtime writer ownership from API/query consumers.
- Stable product/window keys from run/generation/attempt/timestamp identifiers.
- Durable interval catch-up from public route symptoms.
- Provider raw inputs from persisted facts.

## Macro Evidence Snapshot Or Freshness

Use for macro sync, observations, six evidence pages, conclusion freshness,
20/60-session correlations, official catalysts, or macro provider questions.

Required reading:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- `docs/references/POSTGRES_PERFORMANCE.md` when performance or queue cost is involved

Diagnostic commands:

- `uv run parallax macro --help`
- `uv run parallax ops queue-inspect --help`
- `uv run pytest tests/architecture/test_kiss_runtime_invariants.py`

Answer must separate:

- `macro_observations` facts from compact series and the one current
  six-document snapshot.
- Sync-window/control rows and process readiness from page-level conclusion
  status.
- Critical missing/stale evidence from optional named unavailable capability.
- The latest completed US-session cutoff from intraday market time.
- Packaged `macrodata` runtime from repository fixtures.

## Agent Workflow Or Documentation Harness

Use for changes to `AGENTS.md`, `CLAUDE.md`, `docs/sdd`, sub-agent work, specs/plans, generated docs, or completion gates.

Required reading:

- `docs/WORKFLOW.md`
- `docs/DESIGN_DISCIPLINE.md`
- `docs/agent-playbook/factory-operating-model.md`
- `docs/agent-playbook/eval-repair-loop.md`
- `docs/agent-playbook/subagent-handoff-template.md`
- `docs/agent-playbook/context-packet-template.md`
- `docs/sdd/_templates/`

Diagnostic commands:

- `uv run python scripts/regen_sdd_work_index.py --check`
- `uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode read-only`
- `uv run python scripts/dispatch_sdd_task.py --feature <slug> --task <number> --mode read-only`

Answer must separate:

- Canonical docs/code from active planning artefacts.
- Generated index state from hand-written governance docs.
- Sub-agent evidence from final owner review.
