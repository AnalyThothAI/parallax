# Reliability

Reliability is built from durable PostgreSQL state, stable identities, bounded recovery, and explicit external-side-effect ledgers. It is not built from in-memory wake delivery, compatibility fallbacks, or repeated health-query caches.

## Probes and status

| Surface | Meaning | May query queues? |
|---|---|---|
| `/healthz` | process is alive | no |
| `/readyz` | DB is reachable; cached startup schema/composition is valid | no |
| `/api/status` | one current in-memory runtime snapshot | no |
| authenticated ops diagnostics | queue detail, terminal evidence, provider diagnostics | yes, on demand |

A degraded optional provider, an evidence gap, or a worker business error does
not make the HTTP process unready. Startup migration/schema validation and
composition are captured once; readiness performs only lightweight DB
liveness against that cached result. Worker, collector, provider-connection,
and News-provider-contract state is captured by the single typed
`RuntimeSnapshot`; status and Ops diagnostics do not poll those components
independently.

Macro claim readiness is a document-level contract. Missing or stale critical
evidence makes the affected conclusion `insufficient_evidence`; optional gaps
make it degraded. Neither condition changes process readiness.

## Durable catch-up

- PostgreSQL facts/control rows are the recovery source.
- Every worker runs at a bounded interval and re-reads its durable queue/frontier.
- There is no separate database or in-process wake plane to reconcile.
- Claims are bounded and leased; expired leases are recoverable.
- Empty queues do not trigger broad historical scans.
- Single-writer ownership is enforced by composition and stable row identities; transaction-scoped data locks remain local to the write they protect.

## Transaction and I/O boundary

Workers/application services own transactions. Repositories never commit implicitly or accept a `commit` switch.

Provider, subprocess, filesystem, and network I/O must not occur inside a DB
transaction. The normal shape is:

```text
short claim/load transaction
  -> close DB transaction
  -> external I/O with provider timeout
  -> short persist/ack transaction
```

WorkerBase supplies sequential iteration and duration telemetry. Provider,
database, network, and subprocess boundaries own their explicit timeouts; the
generic loop does not force-cancel domain work.

## Idempotency and current rows

- Current read models use stable product/window/target keys.
- Run, generation, attempt, snapshot UUID, and computed/published timestamps are not current identities.
- A stable payload hash excludes lifecycle timestamps.
- `ON CONFLICT ... DO UPDATE ... WHERE current.payload_hash IS DISTINCT FROM excluded.payload_hash` or an explicit tuple comparison prevents unchanged writes.
- Each current read model has exactly one writer declared in the minimal worker manifest.
- Publication state records current frontier/status; it is not an alternate generation-serving table.

## Terminal evidence

Retry exhaustion or deterministic non-retryable failure creates `worker_queue_terminal_events` with the source snapshot and reason bucket. Operator actions are `retry`, `archive`, or `quarantine` and always record a reason/time.

- unresolved terminal evidence is retained;
- resolved evidence is deleted after 30 days;
- retired queues are archived during migration so they are preserved but no longer actionable;
- a queue retry is supported only when an explicit source transition exists.

## Provider failure policy

Transient transport/server errors use bounded retries. Deterministic credential, authorization, payment, unsupported-route, or invalid-configuration errors do not retry forever.

News source terminal state is tied to the source's stable `config_payload_hash`. Reconciliation keeps the source disabled while `terminal_config_payload_hash` matches and clears terminal state only when operator-controlled configuration changes.

Provider secrets are never emitted in status, terminal rows, logs, or diagnostics. Report redacted configured booleans, provider names, error classes/status codes, and active config paths only.

## Side effects

External notification delivery requires durable audit/ledger rows:

- stable dedup/input identity;
- claimed/in-flight state;
- provider/channel identity without secrets;
- result/error/latency metadata;
- compare-and-set completion or retry.

The external action happens outside the transaction. Repeated execution must either be provider-idempotent or prevented by the ledger/dedup key.

## Retention

Append-only facts and operational attempts have different policies:

- material facts: retained according to evidence/product policy;
- successful News fetch attempts: short retention (30 days);
- failed/terminal fetch attempts: longer operational audit window;
- resolved queue terminal events: 30 days;
- current read models: one stable row per product identity;
- rebuildable queues/caches: only active/current work.

Retention must preserve current-row foreign keys and unresolved external-side-effect evidence.

## Migration discipline

Destructive migrations:

- set bounded lock and statement timeouts;
- clean/transform data before constraints or drops;
- drop child objects before parents;
- avoid `CASCADE` and `IF EXISTS` so schema drift fails closed;
- are explicitly irreversible when restoration requires backup/replay;
- preserve material facts and unresolved side-effect/terminal audit.

Old Alembic history remains until a separately tested baseline migration defines a new minimum supported schema. Runtime compatibility code and migration history are different concerns.

## Known safety hold

Do not remove `events.raw_json` or `events.event_json` until every event has a verified raw-frame source edge and item locator, ambiguous historical payloads are immutably archived, and DTO construction uses normalized columns only. This is the remaining high-risk physical cleanup boundary.
