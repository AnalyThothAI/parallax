# Watchlist Intel Architecture

Watchlist Intel is a public read path over durable material facts. It does not
own provider IO, model execution, or a current runtime writer.

| Stage | Code | Durable inputs | Contract |
|---|---|---|---|
| Public routes | `app/surfaces/api/routes_watchlist.py` | runtime settings handles, repository session | Own public defaults for selected handles, `scope`, overview window, source sample budget, cluster budget, timeline `limit`, and cursor validation. |
| Read service | `services/watchlist_read_service.py` | `WatchlistIntelRepository` | Requires explicit `WatchlistReadWindowConfig`; validates configured handles before repository reads; passes overview source and cluster budgets explicitly. |
| Repository reads | `repositories/watchlist_intel_repository.py` | `events`, `token_intent_resolutions`, token resolution current joins | Reads only persisted PostgreSQL facts. Timeline is cursor/limit bounded. Configured-handle overview uses one keyset query for the input handle set; latest-event lookup is a lateral `ORDER BY received_at_ms DESC, event_id DESC LIMIT 1` probe and recent counts are windowed by `since_ms`. Per-handle SQL loops and full-history `MAX(received_at_ms)` aggregation are not part of the contract. Single-handle overview computes aggregate metrics separately and loads only a bounded source-event sample before token-resolution fan-out and cluster construction. |

`/api/watchlist/handle/{handle}/overview` must not call providers, worker
state, or request-time model code. It also must not scan all historical events
for a handle. The route/service boundary passes `source_limit` and
`cluster_limit` explicitly; the repository has no `limit=500` default and no
unbounded overview source query.

`/api/watchlist/handle/{handle}/timeline` remains a paged fact read over
`events` ordered by `(received_at_ms, event_id)` with a caller-owned cursor and
limit. Token resolution details are looked up only for the visible page.
Visible event rows require a non-empty `event_id`, positive `received_at_ms`,
and list-shaped `cashtags_json`, `hashtags_json`, and `mentions_json`; malformed
persisted facts fail the read instead of being repaired to empty identity,
epoch time, or empty lists.

`/api/watchlist/handles/overview` must keep configured-handle metrics as a
batch read. The repository query owns the input handle keyset, preserves input
order with `WITH ORDINALITY`, and must not issue separate last-event/count SQL
for each configured handle. It also must not compute latest events through
full-history `MAX(events.received_at_ms)` aggregation; the latest probe must
match the lower-author descending cursor index shape.
