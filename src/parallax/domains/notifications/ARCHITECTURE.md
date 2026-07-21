# Notifications Architecture

## Boundary

Notifications is a deterministic CQRS projection plus a durable side-effect
ledger. It does not ingest provider frames or create market facts. The rule
worker reads PostgreSQL-backed facts/current read models through domain
interfaces, derives notification candidates, and writes the notification
serving projection. The delivery worker consumes only persisted delivery work.
Public HTTP and WebSocket reads never call providers.

## Truth and ownership

| State | Category | Runtime writer |
|---|---|---|
| `events`, `account_token_alerts` | upstream material facts | collector through the evidence ingest transaction |
| `news_page_rows` | upstream rebuildable current read model | owning News projection worker |
| `notifications` | rebuildable notification serving projection | `NotificationWorker` (`notification_rule`) |
| `notification_reads` | material operator read state | notification command/API surface |
| `notification_deliveries` | durable external-delivery state machine | enqueue: `NotificationWorker`; claim/complete/fail: `NotificationDeliveryWorker` |

Stable notification identity is `dedup_key`, derived from rule identity and
persisted source identity/time. Runtime time may bound a query window, but it
must not replace a missing source occurrence timestamp. Duplicate aggregation
updates the existing stable row and does not create generation-, attempt-,
timestamp-, or UUID-identified serving rows.

## Worker flows

```text
PostgreSQL facts/current projections
  -> NotificationRuleEngine.evaluate(now_ms)
  -> NotificationCandidate
  -> notifications upsert/aggregate
  -> notification_deliveries enqueue (external channels only)
  -> commit
  -> WebSocket publish + delivery wake hint

notification_deliveries due rows
  -> transactional claim and configuration validation
  -> external I/O outside the database transaction
  -> transactional complete or retry/dead failure transition
```

`NotificationWorker` evaluates and persists candidates in one repository unit
of work. Delivery wake and WebSocket publication happen only after that unit of
work exits. `NotificationDeliveryWorker` never keeps a transaction open across
network I/O; completion and failure are separate compare-and-set repository
transitions using the persisted attempt contract.

Both workers remain interval-driven even when a wake hint is available. A
missed `NOTIFY` or in-process wake therefore delays work only until the next
bounded `interval_seconds` catch-up. Batch size, statement timeout, delivery
attempts, running timeout, and stale-running terminalization batch size come
from the formal worker settings.

## Hard boundaries

- Rules read source timestamps and identities fail-closed; malformed rows are
  not repaired with the worker clock, blank ids, or empty JSON defaults.
- News recency is a required repository query boundary. The rule computes one
  `since_ms`, News SQL filters `latest_at_ms` before its limit, and the rule
  consumes typed `NewsNotificationCandidate` rows; stale wide rows are not
  fetched and filtered in Python.
- The rule engine does not write SQL. The repository owns notification,
  read-state, and delivery SQL; workers own transaction and side-effect order.
- External providers are adapters used only by the delivery worker after a
  durable claim. They cannot change notification identity or serving state.
- `notification_reads` is material operator state, not part of the rebuildable notification projection, and must not
  be deleted by notification projection rebuild/repair work.
- `notification_deliveries` is an operational audit/state-machine ledger, not a
  derived API cache. Delivery retries must resume from persisted status and
  attempt count.
- Unchanged/duplicate candidates do not report a newly created notification or
  enqueue a second delivery. A rule-specific aggregation may reactivate a
  failed delivery only through the explicit repository transition.
