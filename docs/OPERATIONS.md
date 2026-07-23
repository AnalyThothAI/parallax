# Operations

This document owns runtime configuration, worker/reliability invariants,
diagnosis, and safe repair boundaries.

## Runtime truth

Real configuration is operator-owned:

- `~/.parallax/config.yaml`: application, PostgreSQL, providers, credentials,
  storage, and notifications;
- `~/.parallax/workers.yaml`: enabled state, cadence, batch, lease, retry, and
  timeout settings.

Confirm the active paths with `uv run parallax config`. Never infer live state
from fixtures, examples, `.env`, generated docs, or a new CLI process. Report
paths, redacted configured booleans, provider names, error classes, and command
results; never secret values.

## Health and status

| Surface | Meaning | SQL/queue inspection |
|---|---|---|
| `/healthz` | process liveness | none |
| `/readyz` | DB liveness plus cached startup schema/composition | no queue inspection |
| `/api/status` | authenticated typed in-memory runtime snapshot | none |
| `parallax ops ...` | explicit on-demand diagnosis and repair | command-specific |

Queue backlog, optional provider degradation, and claim-level evidence gaps do
not make the HTTP process unready. Macro critical gaps produce
`insufficient_evidence`; optional gaps remain explicit degradation.

## Worker ownership

`src/parallax/app/runtime/worker_manifest.py` is the executable inventory for
worker names, start order, queue tables, and worker-owned stable read-model
identities. `worker_factories()` is the only callable composition registry.
Configuration may disable workers but cannot invent names or owners.

Every long-running worker is a `WorkerBase` subclass:

```text
WorkerScheduler
  -> run_once()
  -> WorkerResult + duration telemetry
  -> bounded interval catch-up / backoff
```

The scheduler owns start, stop, and status. One iteration runs at a time.
Provider, DB, subprocess, and network boundaries own their explicit timeouts.

## Durable queue and transaction rules

- PostgreSQL facts/control rows are the only recovery source.
- Claims are bounded and leased with `SKIP LOCKED` or compare-and-set.
- Queue identity is the stable product target, not an event or attempt.
- Success writes the current model and acknowledges the exact claim in one
  application-owned transaction.
- Retry clears the lease and schedules a bounded future attempt.
- Exhaustion preserves the source snapshot in
  `worker_queue_terminal_events`.
- Workers re-read durable work on bounded intervals; there is no wake plane.
- Provider/network/subprocess/filesystem I/O occurs outside DB transactions.
- Current rows use stable keys and skip unchanged payload writes.

External delivery follows claim -> close transaction -> I/O -> CAS complete or
retry. It requires a durable delivery ledger and stable dedup identity.

## First checks

For missing or stale live data:

1. run `uv run parallax config`;
2. check `/healthz` and `/readyz`;
3. inspect authenticated `/api/status`;
4. run `uv run parallax ops queue-inspect --status active`;
5. inspect unresolved terminal events;
6. trace one stable target from fact -> dirty target -> current row -> API.

| Symptom | Inspect first |
|---|---|
| no API row | current key and publication state |
| idle worker with expected work | durable target plus due/lease fields |
| stale row after a run | fact watermark, payload hash, zero-write comparison |
| growing queue | claim size, lease expiry, retry budget, terminal events |
| repeated provider failure | provider status and deterministic terminal policy |
| duplicate external action | dedup key and CAS delivery state |
| readiness 503 | DB liveness and startup schema/composition |
| status degraded, readiness 200 | expected runtime/product separation |

## Domain traces

Token Radar:

```text
event -> intent -> resolution -> token_radar_dirty_targets
  -> factor edges/features -> token_radar_current_rows -> publication
```

Market current is maintained transactionally with `market_ticks`; it has no
projection worker or dirty queue. Repair uses bounded
`parallax ops rebuild-market-current --execute` fact replay.

News:

```text
news_sources -> fetch/provider facts -> canonical item
  -> deterministic processing -> page dirty target -> news_page_rows
```

`page` is the only News projection kind. Deterministic source failures are tied
to `config_payload_hash` and resume only after operator configuration changes.

Macro:

```text
sync window -> macro_observations -> projection dirty target
  -> compact series -> one current snapshot with six page documents
```

All six documents share one projection version, fact watermark, completed US
session cutoff, and computation time. Freshness re-evaluation uses persisted
rows and a deterministic date/session bucket, not a second queue or writer.

Notifications create/aggregate the notification and activate delivery rows in
one transaction. Sending happens later outside the transaction.

## Operator actions and retention

Supported terminal actions are:

- retry: recreate the supported source transition and record reason/time;
- archive: preserve evidence but remove it from unresolved work;
- quarantine: preserve and mark evidence for investigation.

Retired queues have no retry path. Successful operational attempts may have
short retention; failed/terminal evidence and unresolved side effects are kept
longer. Current models retain one stable row per identity.

Destructive migrations use bounded timeouts, transform data before constraints,
drop children before parents, avoid `CASCADE`/`IF EXISTS`, and preserve material
facts plus unresolved side-effect/terminal evidence.

Do not remove `events.raw_json` or `events.event_json` until every event has a
verified raw-frame edge and locator, historical coverage reaches 100%, and
ambiguous payloads are archived immutably.

For PostgreSQL query and queue performance diagnosis, use
[references/POSTGRES_PERFORMANCE.md](references/POSTGRES_PERFORMANCE.md).
