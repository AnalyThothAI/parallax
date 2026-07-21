# Read Model Change Checklist

Use this checklist for any Parallax change that creates, rewrites, republishes, or reviews a derived read model. Current production examples are Token Radar, News Page, Macro views, asset-profile/current-market projections, and future read-side projections. Watchlist is an Evidence query, while retired CEX OI and Narrative products are not templates for new projections.

## Truth Boundary

- PostgreSQL material facts are the source of business truth.
- Provider raw frames are inputs, not facts.
- Derived read models are rebuildable serving projections.
- API, WebSocket, CLI, and frontend routes read facts/read models; they do not repair provider state inline.
- Generated artefacts and SDD records are engineering evidence, not runtime truth.

## Required Audit

1. Identify the material fact tables that feed the projection.
2. Identify the exact read-model table or view being written.
3. Identify the single runtime writer and its worker manifest key when it is a worker.
4. Confirm stable product/window keys for current rows.
5. Reject `generation_id`, `run_id`, `attempt`, timestamp, random UUID, or provider-frame id as current-row identity unless the table is explicitly historical.
6. Prove unchanged projections write zero serving rows.
7. Confirm row count is bounded by product/window cardinality, not by run count.
8. Confirm the worker re-reads PostgreSQL and runs bounded `interval_seconds` catch-up.
9. Confirm correctness has no database or in-process wake dependency.
10. Confirm queue-depth and status hooks are read-only.
11. Confirm public routes do not call providers or workers as a repair path.
12. Confirm domain `ARCHITECTURE.md`, `docs/WORKERS.md`, and tests name the same writer.

## Required Tests

- Architecture test for single runtime writer ownership.
- Architecture or unit test forbidding retired compatibility paths.
- Unit test for no-work / idle behavior.
- Unit or integration test for idempotent projection writes.
- Integration test when storage, query paths, worker runtime behavior, API read models, or derived read-model writes change.
- Performance-sensitive projections include cardinality and write-amplification checks.

## Review Questions

- What fact change makes this read model stale?
- What exact key makes one current row replace another?
- What durable state is found on the next interval after downtime?
- What happens when the worker starts after one hour of downtime?
- What proves that rerunning the projection does not create duplicate serving rows?
- Which public consumer would show stale or degraded state, and how is that state represented honestly?
- What old compatibility surface is removed or kept deleted by this change?

## Rejection Criteria

Reject the change until redesigned when any item below is true:

- A second runtime writer can mutate the same read model.
- Current rows are keyed by run/generation/attempt/timestamp/UUID identity.
- The projection must scan broad fact or read-model history while idle.
- Provider raw inputs bypass persisted facts.
- A public route calls a provider, worker, or repair command to hide stale state.
- The implementation keeps a compatibility shim for a retired table, field, route, or identity scheme.
