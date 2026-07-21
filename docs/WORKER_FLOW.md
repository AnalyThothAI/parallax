# Worker Flow and Debugging

This is the operational runbook. The canonical inventory and ownership map is `docs/WORKERS.md`; do not duplicate it here.

## The state machine

Dirty-target workers use one durable pattern:

```text
dirty target
  -> due
  -> leased (bounded claim)
  -> load minimal input
  -> optional provider/model I/O outside transaction
  -> explicit write transaction
       -> current read-model write or no-op
       -> publication/audit state
       -> acknowledge exact claim
  -> next bounded interval catch-up
```

Failure is explicit:

```text
retryable error -> clear lease + future due_at + last_error
attempt budget exhausted -> terminal evidence + remove/terminalize source row
operator retry -> recreate source work + mark terminal action
operator archive/quarantine -> preserve audit, make it non-actionable
```

Status queues such as `notification_deliveries` use named states and compare-and-set transitions, but the same ownership rules apply.

## First checks

For live-data or missing-row problems:

1. Run `uv run parallax config` and confirm `config_path` and `workers_config_path` point to `~/.parallax/`.
2. Check `/healthz` and `/readyz` for process/DB/schema composition only.
3. Check `/api/status` or `/api/ops/diagnostics` for the running worker/provider state.
4. Use `parallax ops queue-inspect --status active` for on-demand queue counts.
5. Inspect unresolved terminal events before changing code or replaying work.
6. Trace one stable target key from material facts -> dirty target -> current row -> API.

Do not diagnose live behavior from fixture YAML, example `.env`, generated docs, or process-local recollection.

## Symptom routing

| Symptom | First boundary to inspect |
|---|---|
| API returns no current row | current read-model key and publication state |
| Worker is idle with expected work | durable dirty target and due/lease fields |
| Worker ran but row is stale | source watermark, stable payload hash, zero-write comparison |
| Queue grows | claim limit, lease expiry, retry budget, terminal events |
| Provider repeatedly fails | provider status and terminal/config-hash policy |
| Duplicate external action | side-effect dedup key and CAS completion state |
| Readiness is 503 | DB liveness, startup schema result, composition only |
| Status is degraded but readiness is 200 | expected provider/worker degradation separation |
| Work appears delayed | interval cadence, durable due/lease fields, and bounded catch-up query |

## Token Radar

Trace:

```text
event
  -> token intent
  -> current resolution with target identity
  -> token_radar_dirty_targets(target_type_key, identity_id)
  -> rank source edge / target feature
  -> token_radar_current_rows
  -> token_radar_publication_state
```

There is no source-event queue and no generic projection run/offset ledger. If a resolved target is missing, inspect the identity carried by the resolution and the target dirty row. If publication is stale, inspect the stable product/window/scope/venue state—not historical attempts.

## Market Current

Normal market ingestion appends `market_ticks`, advances `market_tick_current`,
and enqueues changed Token Radar targets in one transaction. There is no current
projection worker or dirty queue. If the derived current table needs repair,
run bounded `parallax ops rebuild-market-current --execute` batches and carry
the returned stable target cursor into the next batch. The repair reads only
persisted facts and uses the same current-write service as normal ingestion.

## News

Trace:

```text
news_sources
  -> news_fetch_runs + provider items
  -> canonical news item
  -> deterministic processing
  -> story_brief dirty target / model run / current brief
  -> page dirty target / page current row
```

Only `page` and `story_brief` are valid dirty-target kinds. A deterministic HTTP/auth/payment/configuration failure disables or terminalizes the source against its current `config_payload_hash`. Reconciliation resumes it only after that hash changes. Historical fetch success is short-retention; failed/terminal evidence is retained longer.

## Macro

Trace:

```text
macro_sync_windows
  -> provider bundle
  -> macro_observations
  -> macro_projection_dirty_targets
  -> compact bounded series
  -> macro_view_snapshots (regime + route-ready module views)
```

`macro_sync_runs` is the single attempt ledger. `macro_observations` is raw fact truth. Series rows contain compact projection data; event text/source fields live only in the whitelisted `event_metadata_json`. The assets daily brief is embedded only in the assets module payload, and all catalog module payloads are written by the same view worker; module routes do not rebuild them.

## Notifications

Rule evaluation is deterministic and provider-free. It creates or aggregates a notification and activates delivery rows in one transaction. Delivery then:

1. claims a row with an expected status/version;
2. closes the transaction;
3. sends externally;
4. opens a new transaction;
5. completes or retries with compare-and-set predicates.

Never hold a DB transaction open across the network call. Never send without a durable delivery row and stable dedup basis.
The unique `notifications.dedup_key` constraint is the sole semantic dedup authority; payload JSON is not scanned for a second identity. External-push cooldown remains independent and applies across distinct notification identities.

## Safe operator actions

- `retry`: recreate the supported source queue transition, then record who retried and why.
- `archive`: preserve evidence and remove it from unresolved work.
- `quarantine`: preserve evidence while flagging it for investigation.

Retired queues have no retry transition. Their unresolved terminal events are archived during the hard-cut migration rather than deleted or left actionable.

## Completion evidence

A worker change is complete when targeted tests show:

- bounded claim and lease behavior;
- success/read-model/ack atomicity;
- retry and terminal transition behavior;
- restart and downtime interval catch-up;
- stable-key idempotency and unchanged zero-write;
- provider I/O outside transactions;
- status surfaces remain DB-query-free except authenticated ops inspection.

Production performance claims additionally require live PostgreSQL evidence; unit tests cannot establish queue depth, table size, p95, temp spill, or provider freshness.
