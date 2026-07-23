# Workers

`src/parallax/app/runtime/worker_manifest.py` is the minimal scheduling/status inventory: worker name, start priority, queue tables, and stable current-model identities. `workers.yaml` contains runtime knobs; it cannot create workers, aliases, or ownership.

`worker_factories()` is the only callable composition registry. Its tuple groups factories by domain because those modules import the shared factory context; it is not a second per-worker descriptor. Every domain factory must return its complete formal key set, using the single `InactiveWorker` implementation when configuration, operator intent, or provider state prevents a real worker. Composition fails immediately when the final key set differs from the manifest or when two factories return the same key.

## Inventory

`all_worker_manifests()` is the executable inventory consumed by scheduling and status code. This document intentionally does not copy that list into a second hand-maintained table. The manifest declares stable identity columns for every worker-owned current read model; transactionally maintained current tables such as `market_tick_current` are documented by their owning domain. Run IDs, attempts, generations, timestamps, and UUID snapshots are forbidden serving identities. Domain architecture maps describe each worker's facts and provider boundaries.

Transactionally maintained does not mean unrebuildable: `market_tick_current`
has a bounded explicit fact-replay application operation, not a hidden eighteenth
worker or a second dirty queue.

## Runtime lifecycle

Every long-running worker is a `platform.runtime.WorkerBase` subclass:

```text
WorkerScheduler
  -> run_once()
  -> WorkerResult + duration telemetry
  -> interval catch-up
  -> bounded backoff after failure
```

The scheduler is the only owner of task start, stop, and status. `WorkerBase`
awaits one `run_once()` at a time and never spawns or force-cancels an
iteration task. Provider, database, network, and subprocess boundaries own
their explicit timeouts; scheduler shutdown waits for the current iteration to
finish before closing resources.

## Queue rules

- Claim a bounded batch with `FOR UPDATE SKIP LOCKED` or an equivalent compare-and-set transition.
- Queue identity is the product target, not the triggering event or attempt.
- Claim increments attempts; provider backpressure must occur before a business
  claim when possible.
- Success acknowledges the exact claimed identity/payload inside the same application-owned transaction as its read-model write.
- Retry clears the lease and sets a bounded future due time.
- Exhaustion moves the source snapshot to `worker_queue_terminal_events`; it is not silently deleted.
- Every worker re-reads durable PostgreSQL work on a bounded interval; correctness has no wake-message dependency.

A clock-sensitive projection may additionally re-evaluate persisted read-model
inputs on a deterministic time bucket without manufacturing a queue row. Macro
uses this only for UTC-date and completed-session freshness changes; the same
single writer and stable payload-hash gate still apply.

News page projection is the sole owner of
`news_projection_dirty_targets`; every row has `projection_name = 'page'`,
`target_kind = 'news_item'`, and an empty window.

## Provider and side-effect rules

Provider/network/subprocess/file work is performed outside DB transactions.
The worker loads and claims minimal durable input, closes the transaction,
performs I/O, then persists the result through a new explicit transaction.

External notification delivery uses a ledger and compare-and-set
completion/failure. The production worker inventory has no model-execution
worker, model queue, or model-owned current read model.

## Status surfaces

- `/healthz`: process liveness only.
- `/readyz`: database liveness plus cached startup schema/composition.
- `/api/status`: the single typed in-memory runtime snapshot; no SQL.
- `parallax ops queue-inspect`: authenticated, on-demand queue SQL.
- `/api/ops/diagnostics`: the same runtime snapshot plus authenticated, on-demand database/domain/queue SQL.

Queue backlog or one degraded provider does not make the HTTP process unready.

## Configuration

Real runtime configuration is operator-owned:

- `~/.parallax/config.yaml`: application, providers, credentials, storage.
- `~/.parallax/workers.yaml`: enabled state, intervals, batch/lease/attempt/timeouts.

Use `uv run parallax config` to confirm the active paths. Never infer live settings from examples, `.env`, or fixtures.

## Change checklist

When a worker changes:

1. Update the minimal manifest only if inventory, start order, queue ownership, or current-model identity changes.
2. Keep stable-key and single-writer architecture tests green.
3. Verify the queue's claim/success/retry/terminal state machine with targeted tests.
4. Verify unchanged projections write zero serving rows.
5. Keep provider I/O outside transactions and terminal evidence recoverable.

Operational diagnosis lives in `docs/WORKER_FLOW.md`; domain-specific stage maps live beside each domain as `ARCHITECTURE.md`.
