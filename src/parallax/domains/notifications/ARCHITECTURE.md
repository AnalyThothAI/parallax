# Notifications Architecture

## Boundary

Notifications is a deterministic CQRS projection plus a durable external
side-effect ledger. It does not ingest provider frames, create market facts,
or consume generated prose. The rule worker reads persisted watched-account
facts, derives candidates, and writes the notification serving projection.
The delivery worker consumes only persisted delivery work. Public HTTP and
WebSocket reads never call providers.

## Truth and ownership

| State | Category | Runtime writer |
|---|---|---|
| `events`, `account_token_alerts` | upstream material facts | collector through the Evidence ingest transaction |
| `notifications` | rebuildable notification serving projection | `NotificationWorker` (`notification_rule`) |
| `notification_reads` | material operator read state | notification command/API surface |
| `notification_deliveries` | durable external-delivery state machine | enqueue: `NotificationWorker`; claim/complete/fail: `NotificationDeliveryWorker` |

Only two rule ids are supported:

- `watched_account_activity`
- `watched_account_token_alert`

Stable notification identity is `dedup_key`, derived from rule id, persisted
source identity/occurrence time, and the configured cooldown bucket. Runtime
time may bound the source query, but it never replaces a missing source
timestamp. Duplicate aggregation updates the same stable row and does not
create generation-, attempt-, timestamp-, or UUID-identified serving state.

The database unique constraint on `dedup_key` is the sole dedup authority.
Payload JSON carries source evidence but is not scanned for another identity.
The notification list response contains both `items` and `summary`; there is
no parallel summary endpoint.

## Worker flows

```text
events + account_token_alerts
  -> NotificationRuleEngine.evaluate(now_ms)
  -> NotificationCandidate
  -> notifications insert/aggregate
  -> notification_deliveries enqueue for configured external channels
  -> commit
  -> WebSocket publish

notification_deliveries due rows
  -> transactional claim and configuration validation
  -> external I/O outside the database transaction
  -> transactional complete or retry/dead transition
```

`NotificationWorker` evaluates and persists candidates in one repository unit
of work. It enqueues external delivery only for a newly created notification;
repeated source evidence cannot reactivate a failed delivery. WebSocket
publication happens only after the transaction exits.

`NotificationDeliveryWorker` never keeps a transaction open across network
I/O. Completion and failure are compare-and-set repository transitions using
the persisted attempt contract.

Both workers are interval-driven and re-read durable work on each bounded
`interval_seconds` catch-up. Batch size, statement timeout, delivery attempts,
running timeout, and stale-running terminalization batch size come from the
formal worker settings.

## Hard boundaries

- Rules fail closed on missing source timestamps or identities; they do not
  substitute the worker clock, blank ids, or empty JSON.
- The rule engine does not read News projections or infer signal strength from
  a headline, score, or generated field.
- The rule engine does not write SQL. Repositories own notification,
  read-state, and delivery SQL; workers own transaction and side-effect order.
- External providers are adapters used only by the delivery worker after a
  durable claim. They cannot change notification identity or serving state.
- `notification_reads` is material operator state and survives projection
  rebuild/repair.
- `notification_deliveries` is an operational audit/state-machine ledger, not
  a derived API cache. Retry resumes from persisted status and attempt count.
- Repeated evidence from the exact same source reference produces no serving
  mutation or second delivery.
