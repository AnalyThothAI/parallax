# Agent Task Reading Matrix

This matrix routes coding agents to the minimum source-backed context for common Parallax work. It is a navigation layer, not a new source of truth. Canonical product rules still live in `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, domain `ARCHITECTURE.md` files, and code.

Before answering or editing, classify the task below. Read the required files for that category, then add optional files only when the question needs them. Answer must separate: PostgreSQL facts, read models, control plane state, cache/fan-out state, provider raw inputs, and generated artefacts.

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
- `uv run parallax ops worker-status --help`
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
- `uv run parallax ops audit-token-radar --help`
- `uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py`

Answer must separate:

- `events`, identity, market tick, and enriched event facts.
- `token_radar_current_rows` and publication-state read models.
- Dirty-target/control-plane queues.
- API/frontend display symptoms.

## Worker Backlog Or Stuck Worker

Use for workers that do not wake, queues that grow, stale read models, timeout loops, or scheduler status gaps.

Required reading:

- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `src/parallax/app/runtime/worker_manifest.py`
- The owning domain `ARCHITECTURE.md`

Diagnostic commands:

- `uv run parallax ops worker-status --help`
- `uv run pytest tests/architecture/test_worker_inventory_contract.py`
- `uv run pytest tests/architecture/test_worker_runtime_contracts.py`

Answer must separate:

- Durable facts from dirty targets and job rows.
- Wake hints from bounded `interval_seconds` catch-up.
- Worker status contracts from diagnostics-only logs.
- Runtime repair commands from public route behavior.

## Product LLM Agent Run

Use for Pulse, News item brief, Narrative semantics/digest, agent cost guard, model capability, schema validation, or agent audit problems.

Required reading:

- `docs/AGENT_EXECUTION.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- The owning domain `ARCHITECTURE.md`
- `src/parallax/platform/agent_execution.py`
- `src/parallax/integrations/model_execution/execution_gateway.py`

Diagnostic commands:

- `uv run pytest tests/architecture/test_agent_execution_plane_contracts.py`
- `uv run pytest tests/unit/integrations/model_execution/test_agent_execution_gateway.py`
- Domain-specific unit tests for the affected agent client or worker

Answer must separate:

- Product LLM agents from development agents.
- Agent request/result audit from domain truth.
- No-start backpressure from provider-started failure.
- Pydantic/schema validation from business validation.

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

## Macro Freshness Or Regime Readiness

Use for macro sync, macro observations, regime readiness, module pages, correlation views, or macro provider questions.

Required reading:

- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- `docs/references/POSTGRES_PERFORMANCE.md` when performance or queue cost is involved

Diagnostic commands:

- `uv run parallax macro --help`
- `uv run parallax ops worker-status --help`
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py`

Answer must separate:

- `macro_observations` facts from current series/view read models.
- Sync-window control rows from regime readiness.
- Packaged `macrodata` runtime from repository fixtures.

## Agent Workflow Or Documentation Harness

Use for changes to `AGENTS.md`, `CLAUDE.md`, `docs/superpowers`, sub-agent work, specs/plans, generated docs, or completion gates.

Required reading:

- `docs/WORKFLOW.md`
- `docs/DESIGN_DISCIPLINE.md`
- `docs/agent-playbook/subagent-handoff-template.md`
- `docs/agent-playbook/context-packet-template.md`
- `docs/superpowers/_templates/`

Diagnostic commands:

- `uv run python scripts/regen_agent_work_index.py --check`
- `uv run pytest tests/architecture/test_agent_playbook_contracts.py`
- `uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_completion_gates.py`

Answer must separate:

- Canonical docs/code from active planning artefacts.
- Generated index state from hand-written governance docs.
- Sub-agent evidence from final owner review.
