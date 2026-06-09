# Agent Task Examples

Use these examples with `docs/agent-playbook/task-reading-matrix.md`. They are copyable starting points, not new product truth. Replace placeholders with exact files, commands, and observed evidence before sending a task to an agent or subagent.

## Real Data Provider Diagnostic

Goal:

- Diagnose why `<provider/domain symptom>` appears in a live operator run without printing secrets or treating repository fixtures as runtime config.

Context:

- Operator symptom: `<missing rows, stale profile, missing icon, source coverage gap>`.
- Affected domain: `<token_intel | asset_market | news_intel | macro_intel | ...>`.

Required reading:

- `AGENTS.md`
- `docs/SECURITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- Owning domain `ARCHITECTURE.md`

Verification:

- `uv run parallax config`
- `uv run parallax ops worker-status --help`
- Smallest domain-specific `uv run parallax ops ... --help` command before a live operation.

Done when:

- Report only redacted `config_path` / `workers_config_path` booleans, paths, row counts, and command outcomes.
- Separate provider raw inputs, PostgreSQL facts, control-plane state, read models, and API/frontend symptoms.
- Name the smallest repair or follow-up command, or explain why no live operation was run.

## Worker Backlog

Goal:

- Find why `<worker>` is stale, not waking, growing queue depth, or repeatedly failing without guessing from logs alone.

Context:

- Worker key: `<worker_manifest key>`.
- Symptom: `<queue depth, stale read model, timeout, failed status payload>`.

Required reading:

- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `src/parallax/app/runtime/worker_manifest.py`
- Owning domain `ARCHITECTURE.md`

Verification:

- `uv run parallax ops worker-status --help`
- `uv run pytest tests/architecture/test_worker_inventory_contract.py`
- `uv run pytest tests/architecture/test_worker_runtime_contracts.py`
- Targeted unit/integration test for the worker state transition.

Done when:

- Identify whether the issue is durable facts, dirty targets, job rows, wake hints, catch-up cadence, or public route behavior.
- Prove any fix with a regression test that fails before the implementation when behavior changes.
- Do not run external provider IO inside a DB worker session.

## Frontend Route Shell QA

Goal:

- Verify `<route/component>` after a UI/CSS/layout change using the fixed frontend harness and browser evidence.

Context:

- Route: `<path>`.
- Changed files: `<web/src/...>`.
- Viewports: `<desktop/tablet/mobile>`.

Required reading:

- `docs/FRONTEND.md`
- `docs/WORKFLOW.md`
- Owning route or feature files under `web/src/features/<feature>/`
- Existing component tests under `web/tests/`

Verification:

- `cd web && npm run lint`
- `cd web && npm run typecheck`
- Targeted `npm run test -- <path>` when a component test exists.
- Browser screenshots or smoke checks for affected routes when layout is user-visible.

Done when:

- No retired CSS buckets, shared UI restyling, notification internals, or `.ods-*` overrides are introduced.
- Desktop and mobile evidence show no text overflow, incoherent overlap, blank route shell, or missing critical data state.
- Final notes list screenshot paths or explain why browser verification was unnecessary.

## Read Model Change Review

Goal:

- Review or implement `<read model/projection>` so it remains rebuildable, bounded, and owned by exactly one runtime writer.

Context:

- Read model: `<table/view/current rows>`.
- Writer: `<worker/service>`.
- Consumers: `<API/CLI/WebSocket/frontend/query service>`.

Required reading:

- `docs/ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/agent-playbook/read-model-change-checklist.md`
- Owning domain `ARCHITECTURE.md`

Verification:

- Architecture test for single writer and hard-cut no-compatibility paths.
- Unit or integration test proving idempotent writes and stable row counts.
- Worker catch-up/status test when wake or queue behavior changes.

Done when:

- The review names the fact source, read-model writer, stable identity, wake source, catch-up bound, idempotency proof, and public consumers.
- The implementation contains no generation/run/attempt/timestamp/UUID current-row identity unless the owning architecture doc explicitly defines it as non-current historical state.
- Unchanged projections write zero serving rows.
