# Workers

`src/parallax/app/runtime/worker_manifest.py` is the minimal scheduling/status inventory: worker name, lane, start priority, wake inputs, queue tables, and stable current-model identities. `workers.yaml` contains runtime knobs; it cannot create workers, aliases, ownership, or wake topology.

`worker_factories()` is the only callable composition registry. Its tuple groups factories by domain because those modules import the shared factory context; it is not a second per-worker descriptor. Every domain factory must return its complete formal key set, including an explicit `DisabledWorker`, `IntentionallyNotStartedWorker`, or `UnavailableWorker` when configuration or provider state prevents a real worker. Composition fails immediately when the final key set differs from the manifest or when two factories return the same key.

## Inventory

`all_worker_manifests()` is the executable inventory consumed by scheduling and status code. This document intentionally does not copy that list into a second hand-maintained table. The manifest declares stable identity columns for every current read model; run IDs, attempts, generations, timestamps, and UUID snapshots are forbidden serving identities. Domain architecture maps describe each worker's facts and provider boundaries.

## Runtime lifecycle

Every long-running worker is a `platform.runtime.WorkerBase` subclass:

```text
WorkerScheduler
  -> optional advisory single-writer lock
  -> run_once()
  -> WorkerResult + duration telemetry
  -> wake hint or interval catch-up
  -> bounded backoff after failure
```

The scheduler is the only owner of task start, stop, and status. Workers do not implement nested restart loops or soft-timeout state machines. Provider-specific timeouts plus the WorkerBase hard timeout are the timing boundary.

## Queue rules

- Claim a bounded batch with `FOR UPDATE SKIP LOCKED` or an equivalent compare-and-set transition.
- Queue identity is the product target, not the triggering event or attempt.
- Claim increments attempts; no-start provider/agent backpressure must occur before a business claim when possible.
- Success acknowledges the exact claimed identity/payload inside the same application-owned transaction as its read-model write.
- Retry clears the lease and sets a bounded future due time.
- Exhaustion moves the source snapshot to `worker_queue_terminal_events`; it is not silently deleted.
- A wake listener always has an interval catch-up, so missed `NOTIFY` messages do not lose work.

News page and story workers share one physical table but have disjoint `projection_name` discriminators. No other worker may claim their rows.

## Provider and side-effect rules

Provider/model/network/subprocess/file work is performed outside DB transactions. The worker loads and claims minimal durable input, closes the transaction, performs I/O, then persists the result through a new explicit transaction.

External notification delivery uses a ledger and compare-and-set completion/failure. Story model runs retain the side-effect audit needed to explain the current story brief. These ledgers have retention policies; append-only does not mean permanent.

## Status surfaces

- `/healthz`: process liveness only.
- `/readyz`: database liveness, startup schema compatibility, core composition.
- `/api/status`: in-memory worker/provider snapshot; no queue SQL.
- `parallax ops queue-inspect`: authenticated, on-demand queue SQL.
- `/api/ops/diagnostics`: authenticated diagnostics for the running service.

Queue backlog or one degraded provider does not make the HTTP process unready.

## Configuration

Real runtime configuration is operator-owned:

- `~/.parallax/config.yaml`: application, providers, credentials, storage.
- `~/.parallax/workers.yaml`: enabled state, intervals, batch/lease/attempt/timeouts.

Use `uv run parallax config` to confirm the active paths. Never infer live settings from examples, `.env`, or fixtures.

## Change checklist

When a worker changes:

1. Update the minimal manifest only if inventory, lane, start order, wake input, queue ownership, or current-model identity changes.
2. Keep stable-key and single-writer architecture tests green.
3. Verify the queue's claim/success/retry/terminal state machine with targeted tests.
4. Verify unchanged projections write zero serving rows.
5. Keep provider I/O outside transactions and terminal evidence recoverable.

Operational diagnosis lives in `docs/WORKER_FLOW.md`; domain-specific stage maps live beside each domain as `ARCHITECTURE.md`.
