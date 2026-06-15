# Account Quality Architecture

> Scope. Owns account profile enrichment, account token-call statistics, quality snapshots, and account alert read services. Global package boundaries live in `docs/ARCHITECTURE.md`; worker ownership lives in `docs/WORKERS.md`.

Account Quality is a read-side support domain. It does not own social event ingestion, token resolution, or market ticks. Those durable facts come from Evidence, Token Intel, Asset Market, and CEX market identity.

## Flow

```text
events + token_intent_resolutions + registry_assets / price_feeds + market_ticks
  -> ops backfill-account-quality
  -> AccountQualityBackfillService
  -> account_profiles / account_token_call_stats / account_quality_snapshots
  -> AccountQualityService
  -> /api/account-quality and CLI account-quality

GMGN directory ops command
  -> AccountQualityRepository.upsert_directory_entry
  -> account_profiles directory columns
  -> public read services
```

`/api/recent` and `/events/by-ids` may read `account_profiles` through
`AccountQualityService.watched_handles(...)` to decorate event authors with a
watched flag. They do not upsert profiles or trigger account-quality backfill.

## Truth Categories

| Category | Tables or code | Owner |
|---|---|---|
| Material facts | `events`, `token_intent_resolutions`, `registry_assets`, `price_feeds`, `market_ticks` | Upstream domains |
| Account read models | `account_profiles`, `account_token_call_stats`, `account_quality_snapshots` | Account Quality maintenance services |
| Public read services | `AccountQualityService`, `AccountAlertService` | Account Quality |
| Ops maintenance | `AccountQualityBackfillService`, GMGN directory sync command | Explicit CLI ops only |

Account-quality backfill is an ops-only maintenance path.
`account_profiles` mixes event-derived profile fields and GMGN directory
columns. It is still read-side state for product surfaces, not a material
social-event fact. Rebuilding account-quality state must replay durable upstream
facts through an explicit maintenance path. The backfill service wraps upstream
fact reads, profile/stat writes, and quality snapshot writes in one callable
connection transaction; missing transaction support is a contract failure before
backfill SQL, not permission to fall back to a naked connection commit.
Repository-owned `AccountQualityRepository` writes follow the same rule:
`account_profiles`, `account_token_call_stats`, and
`account_quality_snapshots` mutations must enter a callable connection
transaction before SQL when the repository owns the commit. Ops backfill and
GMGN directory sync keep repository writes caller-owned with `commit=False`
inside their outer transaction.

## Writer Ownership

There is no long-running Account Quality worker today.

- `AccountQualityBackfillService` is the only domain service that writes
  `account_profiles`, `account_token_call_stats`, and
  `account_quality_snapshots` from event, resolution, identity, and market
  facts. Its batch transaction is owned by the service, and repository calls in
  that path use caller-owned `commit=False`. The backfill batch `limit` is an
  explicit caller/CLI policy; the service must not keep its own limit default.
- `ops sync-gmgn-directory` may update only GMGN directory columns in
  `account_profiles`; those updates are caller-owned inside the ops connection
  transaction.
- `AccountQualityService` and `AccountAlertService` are read-only. They must not
  expose backfill, repair, upsert, insert, or commit paths.
- `AccountAlertService.account_alerts(...)` requires callers to pass `window`,
  `limit`, and `now_ms` explicitly. API, CLI, and notification-rule callers own
  those query boundaries and the read clock; the read service must not hide a
  default alert window, result width, or repository-local wall-clock fallback.
- Public read services must not expose backfill, repair, upsert, insert, or commit paths.

If account-quality backfill becomes runtime work, add a manifest-owned worker,
dirty target table, bounded catch-up loop, and a `docs/WORKERS.md` row in the
same change. Do not hide runtime work behind API reads or read-model services.

## Identity And Boundedness

- Account identity is normalized `handle`.
- Token-call statistics are stable by `(handle, token_id)`.
- Quality snapshots are stable by `(handle, window)` with
  `snapshot_id = account-quality:{handle}:{window}:current`.
- Snapshot identity must not include run ids, attempts, timestamps, or random
  UUIDs.
- Account-quality reads are bounded by requested handles and repository limits.
- Multi-handle account-quality reads use one normalized input keyset and fixed
  batch SQL for profiles, token-call stats, and snapshots. They must not call
  the single-handle `account_quality(...)` reader once per handle; per-handle
  stat and snapshot limits belong in PostgreSQL window ranks, not Python loops.

## Public Consumers

- `/api/account-quality`
- `/api/account-alerts`
- `/api/recent` and `/events/by-ids` watched-author decoration
- `parallax account-quality`
- notification rule evaluation through account alert reads

Public consumers read persisted account-quality rows. Missing rows must appear
as missing or insufficient sample state; consumers must not trigger provider IO
or maintenance backfill inline.
