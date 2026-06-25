# Live Provider Diagnostics - 2026-06-24

Scope: read-only live diagnostics against the operator-owned Parallax runtime
configuration. This report complements
`docs/reviews/kappa-cqrs-backend-worker-audit-2026-06-24.md`, which was a
static/unit architecture audit.

## Safety Boundary

- Runtime config was confirmed through `uv run parallax config`.
- `config_path`: `~/.parallax/config.yaml`
- `workers_config_path`: `~/.parallax/workers.yaml`
- Both paths are under the operator-owned `~/.parallax/` runtime directory.
- No provider keys, API tokens, proxy URLs, PostgreSQL DSNs, article titles,
  event ids, asset addresses, notification ids, or raw payloads were copied into
  this report.

## Commands Run

Read-only CLI diagnostics:

```bash
uv run parallax config
uv run parallax ops worker-status --help
uv run parallax ops worker-status
uv run parallax ops projection-status --help
uv run parallax ops projection-status
uv run parallax ops validate-projections --help
uv run parallax ops validate-projections --sample 100
uv run parallax ops audit-token-radar --help
uv run parallax ops audit-token-radar --window 5m --scope all --limit 20
uv run parallax ops factor-diagnostics --help
uv run parallax ops factor-diagnostics --window 5m --scope all --limit 50
uv run parallax ops news-dedup-diagnostics --help
uv run parallax ops news-dedup-diagnostics --window-hours 24
uv run parallax macro --help
uv run parallax macro status
uv run parallax pulse --help
uv run parallax pulse health
uv run parallax notification-deliveries --help
uv run parallax notification-deliveries --limit 20
uv run parallax ops queue-inspect --help
uv run parallax ops queue-inspect --status active --limit 20
uv run parallax ops queue-inspect --worker resolution_refresh --source-table token_discovery_dirty_lookup_keys --status active --limit 1
uv run parallax ops queue-inspect --status active --worker resolution_refresh --limit 5
uv run parallax ops run-resolution-refresh --help
```

Additional read-only SQL probes used the project's own settings loader and
PostgreSQL client, and executed SELECT-only probes. No data mutation commands
were run.

## Runtime Provider Config

- Handles configured: 148.
- API WebSocket token configured: yes.
- Store engine: PostgreSQL.
- Product LLM configured: yes, provider `litellm`.
- GMGN configured: yes.
- OKX DEX configured: yes.
- Binance enabled: yes.
- Macrodata enabled: yes.
- FRED key configured by redacted boolean: yes.

## Worker Runtime Snapshot

- Worker manifests: 26.
- Enabled workers: 22.
- Disabled workers: 4.
- Running workers in the sampled CLI snapshot: 0.

Workers/lane states that need attention:

| Worker/lane | Runtime status | Evidence |
| --- | --- | --- |
| `resolution_refresh` | blocked/degraded queue | 3,300 active dirty lookups, 3,291 failed, 8,736 unresolved terminal lookups |
| `event_anchor_backfill` | blocked terminal queue | 21,172 unresolved terminal jobs |
| `token_radar_projection` | degraded source queue | about 211 active source dirty events, about 198 failed in the sampled worker-status output |
| `macro_view_projection` | degraded dirty targets | 137 failed macro projection dirty targets in the latest sample; due count 0 and max sampled attempt count 399 |
| `token_image_mirror` | blocked terminal queue | 2 unresolved terminal image-source targets |
| `pulse_candidate` | disabled by config | about 13.9k due trigger dirty targets; expected while disabled |
| `cex_oi_radar_board` | disabled by config | CEX OI/detail read models are empty by configuration |

The worker-status CLI showed no worker process currently running, but facts and
read models were still fresh during the live probes. That suggests another
runtime process had recently written data, or the sample caught a quiet moment
between worker loops. The important boundary is that the PostgreSQL truth layer
was reachable and current.

A refreshed read-only `ops worker-status` sample on 2026-06-25 returned 26
workers: 22 enabled, 0 running, with effective statuses 22 `stopped`, 3
`disabled`, and 1 `intentionally_not_started`. A later redacted sample in the
same follow-up showed nonzero queue depths for `pulse_candidate` 14,235,
`resolution_refresh` 3,300, `token_radar_projection` 288,
`macro_view_projection` 137, `token_profile_current` 28,
`event_anchor_backfill` 2, and `token_capture_tier` 1. No live queue row or fact
row was mutated.

## Provider Inputs And Facts

Live provider/fact evidence was present across social/events, market ticks,
news, and macro:

| Boundary | Evidence |
| --- | --- |
| Events | 2,473,976 total rows; latest row age about 0.9s in the table freshness probe |
| Events by transport, last 1h | `direct_ws`: 5,796 rows; latest age about 0.7s |
| Token intents | 385,024 total rows; latest age about 12s |
| Token intent resolutions | 770,418 total rows; latest age about 12s by `created_at_ms` |
| Market ticks | 3,708,208 total rows; latest age about 3.2s |
| Market ticks, last 1h | tier1 websocket chain-token ticks: 11,216 rows; tier2/tier3 chain-token and Binance CEX symbol rows also present |
| Registry assets | 52,451 total rows; latest age about 15s |
| Asset identity current | 52,118 total rows; latest age about 33s |
| News provider items | 83,141 total rows; latest age about 52s |
| News canonical items | 68,568 total rows; latest age about 47s |
| Macro observations | 84,208 total rows; required history coverage ready |

Some provider `observed_at_ms` values were a few seconds ahead of the database
clock. This is consistent with upstream timestamp skew and should not be treated
as a Kappa/CQRS violation by itself.

## Asset Market Capture And Current Projection

Additional SELECT-only probes confirmed the live Asset Market chain is active
under `~/.parallax` runtime settings. Asset Market worker toggles were enabled
for `token_capture_tier`, `market_tick_stream`, `market_tick_poll`,
`market_tick_current_projection`, and `live_price_gateway`.

| Boundary | Aggregate evidence |
| --- | --- |
| `token_capture_tier` | 20,320 total rows; 10 Tier 1 stream rows; 64 Tier 2 poll rows; 20,246 inline-only rows; latest update age about 5.2s |
| `token_capture_tier_dirty_targets` | 1 total due/unleased row; max attempt 0; no non-positive watermarks |
| `market_ticks` | 3,726,875 total append-only facts; 10,142 received in the last hour; latest age about 2.7s |
| `market_ticks` by lane | 3,394,816 Tier 1 WS rows; 136,301 Tier 2 poll rows; 195,758 Tier 3 inline rows |
| `market_tick_current` | 28,879 current rows; latest update age about 2.7s; stable key cardinality bounded to current market targets |
| `market_tick_current_dirty_targets` | 0 active rows; no leased rows; no retry-budget pressure |
| `token_radar_dirty_targets` from market current | 3 market-current dirty rows due; max attempt 0 |
| Queue Terminal market queues | 0 unresolved `market_tick_current_dirty_targets`; 0 unresolved `token_capture_tier_dirty_targets` |

The code audit found and fixed one queue lifecycle gap after this live probe:
`market_tick_current_dirty_targets` now terminalizes retry-budget-exhausted
claims and supports Queue Terminal retry from the terminal source snapshot. No
live repair or mutation was run.

A 2026-06-25 follow-up SELECT-only probe found the market-current projection
fully caught up with append-only tick facts under the same `~/.parallax`
runtime config:

| Boundary | Aggregate evidence |
| --- | --- |
| `market_ticks` append-only facts | 3,893,994 total facts across 29,500 targets; 8,668 received in the preceding hour; latest observed/received timestamps aligned with the probe time |
| `market_ticks` by lane | 3,552,263 Tier 1 WS rows across 2,769 targets; 141,912 Tier 2 poll rows across 16,056 targets; 199,819 Tier 3 inline rows across 29,030 targets |
| `market_tick_current` | 29,500 rows; 29,500 distinct stable keys; 0 duplicate key groups; 0 missing identity, tick id, or payload hash fields |
| Current vs latest append-only tick | 29,500 latest tick targets; 0 missing current rows; 0 stale current rows; 0 payload-hash mismatches |
| `market_tick_current_dirty_targets` | 0 total, due, leased, failed, or unresolved terminal rows |
| Token Radar market-dirty fan-out | 0 active market-dirty rows, 0 due, 0 leased, 0 failed |

Static review confirmed `MarketTickCurrentProjectionWorker` is the runtime owner
of `market_tick_current`: it claims durable dirty targets, reads the latest
append-only `market_ticks` fact per stable target key, upserts the current row
only when visible data changes, and enqueues Token Radar market dirty work in the
same worker transaction. The rebuild service is an operator maintenance path
guarded by the projection advisory lock, not a second runtime writer. No live
worker pass, queue retry/archive, rebuild, current-row mutation, or provider call
was executed in this follow-up.

The same 2026-06-25 follow-up also covered the upstream capture-tier control
projection:

| Boundary | Aggregate evidence |
| --- | --- |
| `token_capture_tier` | 20,672 rows; 20,672 distinct stable keys; 0 duplicate key groups; 0 missing identities; 0 invalid tiers; 0 missing scores |
| Capture tiers | Tier 1: 10 `chain_token`, 0 non-chain targets; Tier 2: 31 `chain_token` and 19 `cex_symbol`; Tier 3: 20,232 `chain_token` and 380 `cex_symbol` |
| `token_capture_tier_dirty_targets` | 1 fresh due global rank-set row, attempt count 0, positive source watermark, no `last_error`, no unresolved terminal rows |
| Token Radar rank source | Current rows exist for the active `token-radar-v13-social-attention` windows/scopes; sampled rows had 0 missing source watermarks |

Static review confirmed `TokenCaptureTierWorker` is the single runtime writer for
`token_capture_tier`, has no provider dependency slots, and performs dirty claim,
tier upsert/demotion, and dirty done state inside one `RepositorySession`
transaction. The lone due dirty row was a fresh Token Radar rank-set refresh, not
a high-attempt retry backlog. No live worker pass, queue retry/archive, tier-row
mutation, or provider call was executed in this follow-up.

The Tier 1/Tier 2 market tick writer follow-up found append-only facts fresh and
well-formed:

| Boundary | Aggregate evidence |
| --- | --- |
| Writer target set | 10 Tier 1 chain-token stream targets; 33 Tier 2 chain-token poll targets; 20 Tier 2 CEX poll targets |
| `market_ticks` quality | 3,896,373 total facts across 29,512 targets; 10,333 received in the preceding hour; 0 missing identity, tick id, payload hash, or positive price fields |
| Recent writer lanes | Tier 1 OKX DEX WS: 9,796 facts across 17 targets in the preceding hour; Tier 2 GMGN DEX poll: 221 facts across 72 targets; Tier 2 Binance CEX poll: 144 facts across 30 targets |
| Current dirty fan-out | `market_tick_current_dirty_targets` had 0 total, due, leased, or failed rows in the follow-up sample |

Static review confirmed stream and poll provider IO happens outside database
sessions. Fact persistence uses `MarketTickPersistenceService` inside a worker
transaction to insert append-only `market_ticks` and enqueue current dirty targets
only for actually inserted tick ids; wakes are emitted after the transaction.
`MarketTickRepository` uses deterministic tick ids and `ON CONFLICT ... DO
NOTHING`, and insert-returning paths require cursor rowcount evidence before
reporting inserted ids. No live writer pass, provider request, fact mutation, or
queue mutation was executed in this follow-up.

The same 2026-06-25 read-only pass covered `live_price_gateway` as a
presentation-only cache/fan-out layer. Runtime config came from
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`; the gateway was enabled with
`target_limit=100`, `target_ttl_seconds=300`, `interval_seconds=2`, and
`statement_timeout_seconds=30`.

| Boundary | Aggregate evidence |
| --- | --- |
| Selected live targets | 59 Tier 1/2 rows under the configured target limit: 43 `chain_token`, 16 `cex_symbol`; 10 Tier 1 rows and 49 Tier 2 rows |
| Formal target-type check | 0 non-formal Tier 1/2 target rows; 0 legacy `Asset` rows; 0 legacy `CexToken` rows |
| 300 second TTL coverage | 38 of 59 selected targets had a fresh latest tick: 33 of 43 `chain_token`, 5 of 16 `cex_symbol` |
| Fresh tick age range | min about 7.6s; p50 about 117.3s; max about 269.5s |
| Fresh provider distribution | 10 OKX DEX WS targets, 23 GMGN DEX REST targets, 5 Binance CEX REST targets |

Static review confirmed `LivePriceGateway` does not own provider IO, facts,
read models, control-plane rows, or wake channels. It reads active live targets
from `token_capture_tier`, reads recent `market_ticks` through
`MarketTickRepository.latest_for_targets(...)`, stores only in-process cache
state, and publishes through the async hub `publish(payload)` contract. The code
repair removed the remaining gateway-local legacy target conversion from
`Asset` / `CexToken` into `chain_token` / `cex_symbol`; live rows were already
formal, so no live mutation or provider call was required.

## Asset Profiles And Token Images

Additional SELECT-only probes covered the profile/icon chain under the same
`~/.parallax` runtime settings. Worker toggles were enabled for
`asset_profile_refresh`, `token_profile_current`, `token_image_mirror`, and
`token_radar_projection`.

| Boundary | Aggregate evidence |
| --- | --- |
| `asset_profile_refresh_targets` | 0 active rows; no due, leased, high-attempt, or non-positive-watermark rows |
| `asset_profiles` | 0 source-cache rows |
| `token_profile_current_dirty_targets` | 45 total dirty rows; all due/unleased; max attempt 0; 45 updated in the last hour |
| `token_profile_current` | 25,549 public profile rows; 14,981 ready; 133 unsupported; no pending/error rows in the aggregate probe; 13,295 rows used local token-image URLs; 0 provider-logo public URLs; 0 missing formal JSON/payload hashes |
| `token_image_source_dirty_targets` | 0 active rows |
| `token_image_assets` | 17,582 image rows; 17,552 ready; 10 error; 20 unsupported; 17,552 local public URLs; 0 provider public URLs; 0 ready rows missing storage |
| Queue Terminal image queues | 2 unresolved terminal image-source rows; both in the retry-budget bucket |

The public `token_profile_current` and `token_image_assets` surfaces were
healthy: provider logo URLs were not exposed as public logo URLs, local image
rows had storage, and present profile rows carried the formal public JSON
fields. The remaining image terminal rows are operator triage items, not a
public read-model leak.

The source-cache lane had a real producer catch-up gap. A read-only aggregate
found 293 current Asset identities with chain/address metadata and no
`asset_profiles` or refresh targets. The runtime producer only faned out profile
refresh work from changed Token Radar rank rows, so unchanged current rows could
stay unseeded after enabling the profile source-cache lane. A code fix now adds
a bounded catch-up to `asset_profile_refresh`: before claiming provider work, it
reads default-venue current Asset identities, excludes existing source-cache and
active refresh-target rows, and enqueues missing provider-scoped
`asset_profile_refresh_targets` using the source row's positive watermark. An
equivalent read-only probe showed the next run would find 55 missing candidates
per configured DEX profile provider. No live write or provider fetch was run
from this diagnostic session.

A 2026-06-25 follow-up profile-current review found the public projection and
image boundary healthy under the same `~/.parallax` runtime settings. An
adjacent CLI queue-health sample saw 30 due `token_profile_current_dirty_targets`
with max attempt 0; a SELECT-only SQL sample moments later saw 0 active dirty
rows, consistent with ordinary worker catch-up rather than a stuck queue.

| Boundary | Aggregate evidence |
| --- | --- |
| `token_profile_current_dirty_targets` | 0 active rows in the SQL sample, 0 leased, 0 failed, 0 non-positive source watermarks |
| `token_profile_current` | 25,890 rows, 25,890 stable keys, 15,186 ready, 10,571 missing, 133 unsupported, 0 error |
| Public profile contract | 0 missing payload hashes, 0 missing formal JSON fields, 0 non-local public logo URLs, 0 logo URLs missing image ids |
| `token_image_assets` | 17,772 rows, 17,737 ready, 15 error, 20 unsupported, 0 pending, 0 non-local public URLs |
| `token_image_source_dirty_targets` | 0 active rows, 0 due, 0 leased, 0 failed, 0 non-positive source watermarks |
| Image Queue Terminal | 7 unresolved image-source rows in the retry-budget bucket |

Static review confirmed `TokenProfileCurrentWorker` claims only
`token_profile_current_dirty_targets`, exact-loads persisted profile/evidence
sources through the formal `RepositorySession.source_query`, writes
`token_profile_current` as the only public profile read model, and admits image
mirror work only through `token_image_source_dirty_targets`. No live profile,
image, dirty-target, or terminal row was mutated in this follow-up.

A more focused 2026-06-25 Token Image Mirror follow-up found the local media
mirror itself healthy. Runtime config came from
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`; `token_image_mirror` was enabled with
`batch_size=100`, `retry_ms=300000`, `max_attempts=3`, and
`statement_timeout_seconds=120`.

| Boundary | Aggregate evidence |
| --- | --- |
| `token_image_source_dirty_targets` | 0 total active rows; 0 due, leased, failed, non-positive-watermark, or missing-hash rows |
| `token_image_assets` lifecycle | 17,777 rows: 17,742 ready, 15 error, 20 unsupported |
| Ready local file check | 17,742 ready rows checked against `~/.parallax/cache/token-images`; 0 missing files |
| Public URL contract | 0 remote `token_image_assets.public_url` rows; 0 ready rows missing local media metadata; 0 non-ready rows carrying public URLs |
| Source URL allow-list | 0 invalid persisted source URLs; hosts were limited to `gmgn.ai`, `static.oklink.com`, and `bin.bnbstatic.com` |
| Provider/status mix | Binance CEX profile: 280 ready; GMGN stream snapshot: 9,494 ready, 10 error, 3 unsupported; OKX DEX evidence: 7,968 ready, 5 error, 17 unsupported |
| Public profile logo contract | `token_profile_current` had 25,899 rows, 13,459 local logo URLs, and 0 remote logo URLs |
| Image Queue Terminal | 7 unresolved image-source terminal rows in the retry-budget bucket |

Static review confirmed `TokenImageMirrorWorker` reads only due dirty targets and
does not scan source tables. It writes pending source rows before provider IO,
then performs HTTP fetch and local file writes outside the claim transaction.
Ready/error/unsupported image lifecycle updates and downstream profile-current
dirty fan-out use repository/session transactions with `commit=False`, cursor
rowcount evidence, claimed completion keys, formal retry cadence, and positive
source watermarks. No live dirty row, image row, terminal event, provider fetch,
or local file was mutated in this follow-up. The `source_limit` setting remains
accepted by the settings schema/default YAML for existing operator configs, but
the current runtime does not use it as a source-scan limit because the mirror is
dirty-target driven.

## Resolution Refresh And Discovery Queue

Additional SELECT-only probes covered the `resolution_refresh` /
`token_discovery_dirty_lookup_keys` control-plane path under the same
`~/.parallax` runtime settings. The sampled worker-status output reported
`resolution_refresh` enabled but not currently running.

| Boundary | Aggregate evidence |
| --- | --- |
| `token_discovery_dirty_lookup_keys` | 3,300 active rows in the latest sampled probe; 3,291 carried `last_error`; no rows had non-positive attempt counts; max attempt count 167 |
| Claim eligibility | 9 active rows were due/unleased in the SELECT-only probe; `ops queue-inspect --status active --worker resolution_refresh` reported 22-23 due rows in adjacent CLI samples |
| Active lookup-type mix | 2,345 `dex_symbol_lookup` rows and 955 `address_lookup` rows |
| Active attempt bands | 11 rows at attempt 1; 47 rows at attempts 2-3; 163 rows at attempts 4-10; 3,079 rows above attempt 10 |
| Discovery result status mix | 11,676 `found`, 4,467 `error`, and 4,402 `not_found` result rows overall; 419 `error` results were updated in the last 24h |
| Queue Terminal discovery rows | 8,736 unresolved terminal rows in the `retry_budget_exhausted` bucket |

Static code audit of the current worker/repository path found that
`claim_due_lookup_keys(...)` does not filter out over-budget rows. Once a row
passes the queue/result due gate and is claimed, provider-error,
provider-unavailable, and hot not-found paths route exhausted claims through
`terminalize_lookup_claims(...)`, which deletes the active source row and writes
`worker_queue_terminal_events` from the deleted source snapshot. No live
mutation or provider lookup was run from this diagnostic session.

The active high-attempt rows therefore look like runtime backlog, not an
observed permanent skip in current code. The current queue contract carries
attempt budget by active lookup key, not by every new payload hash update; that
keeps poison lookups bounded, but it should remain an explicit design choice
when reviewing whether newly observed evidence for an existing lookup key should
receive a fresh retry budget.

The 2026-06-25 follow-up also reviewed the current `ResolutionRefreshWorker`,
`DiscoveryRepository`, `RegistryRepository`, worker factory, and one-shot ops
runner. The one-shot `run-resolution-refresh` command still constructs the
formal worker and only overrides batch/reprocess limits through the settings
model-copy contract; it is not a separate compatibility path. Static scan found
no retained read-only due-list helper, direct `repos.conn.commit()` fallback,
loose DEX candidate reflection, or old chain/quote-provider constructor path.
Targeted worker, integration, and architecture tests for this slice passed. No
live provider lookup, queue retry/archive, or source-row mutation was run.

## Macro Provider Coverage

A 2026-06-25 Macro Sync follow-up reviewed the fact-ingest lane under the same
`~/.parallax` runtime settings. `macro_sync` was enabled with the configured
bundle set `macro-core`, `macro-calendar-core`, `treasury-auction-core`,
`fed-text-core`, and `crypto-derivatives-core`; `batch_size=3`,
`lease_ms=300000`, `retry_delay_ms=900000`, `max_attempts=8`,
`macrodata_timeout_seconds=240`, and `statement_timeout_seconds=30`.

| Boundary | Aggregate evidence |
| --- | --- |
| `macro_observations` | 84,330 fact rows across 188 concepts; 0 missing fact payload hashes; latest ingest age about 66.5 minutes in the sample |
| Observation source coverage | `fred`: 45,592 rows; `yahoo`: 33,690; `nyfed`: 3,533; `treasury_fiscal`: 766; `cboe`: 564; `deribit`: 72; `okx`: 52; official calendar/text and CFTC rows also present |
| `macro_sync_windows` | 851 done, 18 failed historical rows, 21 pending due rows; 0 running, 0 expired-running, 0 active over-budget rows; pending rows had max attempt 0 |
| Current configured bundle state | `crypto-derivatives-core`, `fed-text-core`, and `macro-core` observed through 2026-06-25; `macro-calendar-core` through 2026-07-30; `treasury-auction-core` through 2026-07-27 |
| Recent sync runs | Last 24h had runs for all configured product bundles; no recent `error_code` buckets were present |
| `macro_import_runs` | 869 `ok`, 2,554 `partial`, 264 `unavailable` audit rows |
| Projection dirty fan-out | `macro_projection_dirty_targets` still had 137 Macro View rows with high attempts; this is the Macro View Projection queue already diagnosed separately, not a Macro Sync fact-ingest write-path violation |

Static review confirmed provider execution runs after a persisted window claim
and outside DB sessions. Successful imports parse formal macrodata bundle
envelopes, write `macro_observations`, `macro_import_runs`, `macro_sync_runs`,
`macro_sync_state`, and changed-concept projection dirty targets inside one
repository unit of work, then send `macro_observations_imported` as a
post-commit wake hint. Noop overlap imports record seen/noop counts but do not
dirty projections or wake. Provider failures record retryable/failed window
state and sync-run audit without fabricating observation facts. No live
macrodata provider call, sync-window retry, observation write, or dirty-target
mutation was run in this follow-up.

Macro observations are populated by multiple named sources:

| Source | Rows | Latest observed date |
| --- | ---: | --- |
| `fred` | 45,536 | 2026-06-24 |
| `yahoo` | 33,650 | 2026-06-24 |
| `nyfed` | 3,527 | 2026-06-23 |
| `treasury_fiscal` | 765 | 2026-06-22 |
| `cboe` | 560 | 2026-06-23 |
| `deribit` | 64 | 2026-06-24 |
| `okx` | 46 | 2026-06-24 |

`uv run parallax macro status` reported:

- Migration ready: yes.
- Macrodata CLI package available, version `0.1.22`.
- Required series: 189; missing required series: 0.
- Required bundles: 5; missing required bundles: 0.
- Required-history concepts ready: 141/141.
- Projection lag days: 0.
- Latest snapshot status: `ready`.
- Latest snapshot as-of date: 2026-06-24.
- Current regime: `term_premium_pressure`.
- Data gaps: 6 optional/staleness/history gaps in the ready snapshot.

The macro sync queue still had open/failed work in the status output, but the
serving projection was current and ready. Treat this as a queue hygiene item,
not an observed public macro outage.

Follow-up SELECT-only diagnostics on the failed Macro projection queue traced
one live failure bucket to an implemented crypto derivatives concept with
`intraday` frequency. A pure feature-engine probe over current persisted macro
series rows succeeded after adding `intraday` to the formal freshness contract,
with a two-day stale window and no fallback to daily semantics. No live Macro
queue row was retried, archived, deleted, or mutated.

A 2026-06-25 follow-up SELECT-only Macro projection probe found the serving
read models healthy but the dirty-target queue still degraded by an implemented
core series frequency that was not in the feature freshness contract:

| Boundary | Aggregate evidence |
| --- | --- |
| `macro_projection_dirty_targets` | 137 active rows, all failed, 0 due/unleased in the sample, min/max attempts 112/399, all `concept` targets |
| Active failure bucket | 137 rows in `feature_frequency_unknown`; no unresolved Macro Queue Terminal rows |
| `macro_observation_series_rows` | 79,938 current rows, 188 concepts, 188 latest rows, 0 missing payload hashes, 0 duplicate stable keys |
| Series frequencies | `daily`, `weekly`, `monthly`, `quarterly`, `intraday`, `event`, and 3 `irregular` rows |
| `macro_view_snapshots` | 1 current `macro_regime_v4` snapshot, status `ready`, regime `term_premium_pressure`, 0 missing payload hashes |
| Publication state | latest attempt status `published`; no latest-attempt error bucket |

The failing live source shape was one core concept with three numeric
`irregular` frequency series rows. The feature engine now treats `irregular` as
a formal supported frequency with a 140-day stale window, still without a
fallback from unknown frequencies to daily semantics. A read-only replay over
the persisted `irregular` series built one macro feature from three rows. No
live Macro worker pass, queue retry/archive/delete, or read-model mutation was
run.

A 2026-06-25 follow-up SELECT-only Macro Daily Brief projection probe found the
derived daily-brief read model aligned with the current Macro View snapshot:

| Boundary | Aggregate evidence |
| --- | --- |
| `macro_daily_briefs` | 1 row, 1 distinct `brief_key`, 0 missing keys, 0 missing payload hashes, 0 malformed payloads |
| Current brief | stable `assets_today` key, status `ready`, brief/as-of date `2026-06-24`, 4 rendered blocks |
| Source snapshot | current `macro_regime_v4` snapshot, status `ready`, as-of date `2026-06-24`, regime `term_premium_pressure` |
| Runtime settings | enabled, interval 86,400s, statement timeout 30s, wakes on `macro_view_snapshot_updated` |

Static review confirmed `macro_daily_brief_projection` has no provider IO,
reads only `macro_view_snapshots` through the repository session, writes only
the `macro_daily_briefs` read model with stable `brief_key` identity, and keeps
`computed_at_ms` out of the payload hash so unchanged projections write zero
serving rows. No live worker pass or read-model mutation was run.

## Derived Read Models

| Read model | Rows | Freshness |
| --- | ---: | --- |
| `token_radar_current_rows` | 437 to 449 during probes | latest 3s to 37s depending on probe time |
| `token_radar_publication_state` | 48 | latest about 0.6s in the table freshness probe |
| `token_profile_current` | about 25,500 | latest about 15s to 20s |
| `token_image_assets` | 17,563 | latest about 7.4 minutes |
| `news_page_rows` | 6,113 to 6,117 | latest about 37s to 47s |
| `news_source_quality_rows` | 6 | latest about 37s to 47s |
| `news_story_agent_briefs` | 712 | latest about 4.8 minutes |
| `news_item_agent_briefs` | 6,783 | latest about 5.4 days |
| `macro_view_snapshots` | 1 | latest about 12h, still as-of 2026-06-24 and projection lag 0 |
| `macro_daily_briefs` | 1 | latest about 12h |
| `pulse_candidates` | 0 | expected while `pulse_candidate` is disabled |
| `narrative_admissions` | 0 | expected while `narrative_admission` is disabled |
| `cex_oi_radar_rows` | 0 | expected while `cex_oi_radar_board` is disabled |
| `cex_detail_snapshots` | 0 | expected while `cex_oi_radar_board` is disabled |
| `asset_profiles` | 0 | source-cache lane was enabled; bounded current-row catch-up was added after this probe |

Kappa/CQRS serving health looks good for Token Radar and News. The empty CEX
and Pulse surfaces match disabled workers. The empty `asset_profiles` table was
explained by the Asset Profile catch-up gap described above; the fix keeps the
runtime producer on the control-plane queue instead of writing source-cache or
public read-model rows directly.

## Token Radar

Projection status:

- `token-radar` status: `ready`.
- Projection version: `token-radar-v13-social-attention`.
- Latest sampled run: status `ready`, rows read 2, rows written 1, no error.
- Offset status: ready, no last error.

Validation:

- `uv run parallax ops validate-projections --sample 100`: `ok=true`.
- Checked rows: 89.
- Mismatches: 0.
- Missing current-row references: 0.

5-minute audit:

- Current public row count: 5.
- Violations: none.
- Source current-window rows: 41.
- Social lag: about 8.3s.
- Market lag: about 7.6s.

Factor diagnostics:

- Current public row count: 5.
- Rank score unique count: 4.
- Rank-score standard deviation: about 4.79.
- Saturation violations: none.
- Alpha, identity, and social health were ready for all 5 sampled rows.
- Market health had 2 missing and 1 partial row. This is a coverage issue, not
  a projection invariant failure.

Additional SELECT-only dirty-queue probe:

| Queue | Aggregate evidence |
| --- | --- |
| `token_radar_dirty_targets` | 0 active rows in the SELECT-only probe; an adjacent CLI queue-health sample saw 8 due/unleased rows with max attempt 0; no unresolved terminal rows |
| `token_radar_source_dirty_events` | 269 active rows in the SELECT-only probe, 189 due/unleased, 257 with `last_error`, max attempt 4,452, and no unresolved terminal rows; an adjacent CLI queue-health sample saw 275 active rows, 215 due, 269 failed, max attempt 4,453 |

Static code audit confirmed that current source/target dirty error completion
will terminalize exhausted claimed rows. The latest code repair in this pass
tightened the claim mutation itself: both source and target dirty
`claim_due(...)` paths now require PostgreSQL rowcount evidence matching the
returned claim rows before the projection service can process claimed work. The
read-only live probe did not run the worker or mutate queue rows.

The 2026-06-25 follow-up also confirmed the current serving layer remained
healthy while the source-dirty backlog was present: 423 current rows, 423
distinct stable current keys, 48 ready publication-state rows, and 0 current
rows missing payload hashes. Runtime settings for `token_radar_projection` were
the formal worker settings under `~/.parallax/`: enabled, batch size 20, lease
120s, retry 30s, retry budget 3, with four configured windows, two scopes, and
six venues. Static scan found no runtime call to the recent-resolved catch-up
helpers; those remain explicit ops/candidate surfaces rather than the worker
loop. The remaining source-dirty queue rows were dominated by
asset-identity-related error buckets; aggregate joins showed both Asset and
CexToken source-dirty rows in that historical failure bucket, consistent with
the previous batch-level failure mode that the current target-isolation repair
addresses. No live worker pass, queue retry/archive, or serving-row mutation was
run.

The refreshed source-dirty error-bucket probe also found a batch-isolation
risk: most failed source dirty rows pointed at Asset targets whose identity
state had since become available, while a much smaller remainder still lacked
current identity. The old projection loop wrapped all affected targets in one
exception boundary, allowing one missing identity contract to mark every source
claim in the claimed batch failed. The code now handles source-dirty affected
targets independently, so successful targets can be completed even when another
target in the same source batch fails. No live Token Radar queue row was
mutated during this diagnostic pass.

## News

`uv run parallax ops news-dedup-diagnostics --window-hours 24` reported:

- Raw observation count: 83,135.
- Canonical item count: 68,564.
- Observation edge count: 83,135.
- Enabled serving rows: 6,111.
- Disabled serving rows: 0.
- Enabled exact-content visible duplicate excess: 0.
- Hard public URL visible duplicate excess: 0.
- Generic public URL visible rows: 67.
- Fact-layer material duplicate excess: 6.
- Stale duplicate brief rows: 56.
- Stale duplicate dirty targets: 0.

News source sync diagnostics showed `opennews-news` and `opennews-listing`
enabled and recently fresh; `opennews-onchain` was disabled. Public News
deduplication is healthy. Remaining material-title duplicates are fact-layer
input duplication, not visible duplicate serving rows.

A later News agent-brief read-only probe confirmed the item/story hard cut:

- `news_items`: 68,844 rows, latest about 71s old; 68,273 processed and 571
  not yet processed.
- `news_page_rows`: 6,144 serving rows, latest about 4.4s old; all rows have a
  stable story key. 827 rows had ready projected agent state and 5,317 were
  not-ready projected rows.
- `news_story_agent_briefs`: 745 current story brief rows, latest about 12s
  old; 200 ready and 545 not-ready. Only 7 story-brief rows lacked a matching
  story-shaped page row in the aggregate probe.
- `news_item_agent_briefs`: 6,783 item-scoped audit/reuse rows, latest about
  5.4 days old; 3,468 ready and 3,315 not-ready. 1,526 item-brief rows did not
  correspond to a current page row, which is expected for retained item audit
  state rather than a public serving table.
- News projection dirty targets: 4 total dirty rows, 0 due/unleased, 0 leased,
  0 at or above 3 attempts, max attempt count 0.
- News unresolved terminal rows in the sampled buckets: 0.

Code trace and targeted tests confirmed public News list rows, high-signal
notification candidates, item detail, source quality, and page projection use
`news_page_rows` and current `news_story_agent_briefs`, not stale
`news_item_agent_briefs` or item run summaries as a compatibility fallback.
Public News page and high-signal notification read-path limits now reject
malformed values before SQL instead of repairing them with `max(0, int(...))`.
This was a code repair only; no live News rows, provider requests, or serving
read results were mutated during this pass.
News item processing claims now also reject malformed claim limits and leases
before SQL; this was code-only and did not claim, mutate, or reprocess live
`news_items`.
News current-brief schema cleanup selectors now reject malformed maintenance
limits before SQL; no live `news_item_agent_briefs` cleanup was executed.
News source-quality projection input windows now reject malformed durations
before SQL; no live `news_source_quality_rows` rebuild was executed.
News dedup diagnostics now reject malformed CLI/repository diagnostic windows
instead of clamping them; no live dedup diagnostic probe was re-run or mutated.
Notification read/list limits now reject malformed values before SQL; no live
notifications or delivery rows were sent, claimed, or mutated.
News canonical rebuild operator limits now reject malformed values before
calling repository selectors; no canonical rebuild was dry-run or executed.
Evidence/entity read limits now reject malformed values before SQL; no live
event or entity diagnostic query was executed for this code repair.
Token intent/lookup read limits now reject malformed values before SQL; no live
intent lookup query or token intent fact mutation was executed.
Token Capture Tier repository read limits now reject malformed values before
SQL; no live capture-tier rows were read or mutated for this code repair.
Registry ranked live-market target limits now reject malformed values before
SQL; no live registry/target candidate query was executed.
Projection repository diagnostic and dirty-range claim limits now reject
malformed values before SQL; no live projection runs or dirty ranges were read
or claimed.
Signal alert and Token Target timeline read limits now reject malformed values
before SQL; no live alert or target timeline query was executed for this code
repair.
Account Quality token-row, Event Rebuild recent-event, and Rank Source
prune/chunk limits now reject malformed values before SQL or batching; no live
account-quality, event rebuild, rank-source prune, or provider query was
executed for this code repair.
Token Target posts/timeline and Asset Flow read-model limits now reject
malformed values before repository reads; no live token-target or asset-flow
query was executed for this code repair.
Token Search service/query limits now reject malformed values before route
selection or SQL; no live search query was executed for this code repair.
Catalyst Ranking, Stocks Radar, and Token Factor Evaluation limits now reject
malformed values before scoring or repository/query reads; no live catalyst,
stocks-radar, or factor-evaluation query was executed for this code repair.
Token Radar private-cache pruning, current-row reads, target-feature pruning,
and lane ranking now reject malformed limits before transactions, SQL, or rank
selection; no live Token Radar rows or private cache rows were read, pruned, or
published for this code repair.
News Page query, Narrative admission upsert, and Search Inspect limits now
reject malformed values before repository calls, write transactions, or token
dossier hydration; no live News, Narrative, or Search Inspect query/write was
executed for this code repair.

The News provider-contract status path was also hardened after this pass:

- Runtime `news_intel.sources` are treated as formal settings objects. Mapping
  sources at that boundary now fail with
  `news_provider_settings_contract_required` instead of being interpreted as a
  compatible provider list.
- Readiness marks that settings-contract failure unhealthy, so malformed
  runtime settings cannot appear as an otherwise healthy process with only a
  nested provider-contract payload warning.
- Provider diagnostics now read the formal `FeedFetchResult.feed` field
  directly instead of probing for an optional attribute, so malformed provider
  registry results fail at the integration boundary.

A 2026-06-25 refreshed News worker-chain probe found the current serving layer
healthy and the active projection queue clean:

| Boundary | Aggregate evidence |
| --- | --- |
| News sources/fetch | 3 configured source rows, 2 enabled, latest successful fetch about 59s old, 0 source rows with active error |
| 24h fetch runs | 2,618 successful runs, 13 failed runs, 69,663 fetched observations, 3,706 inserted and 773 updated canonical items |
| `news_items` lifecycle | 71,460 processed rows, 571 historical `process_terminal_failed` rows, 0 leased processing rows |
| `news_page_rows` | 6,400 stable serving rows, 6,400 distinct row ids, 0 missing payload hashes, latest projection about 346s old |
| `news_source_quality_rows` | 6 source/window rows, 6 distinct identities, 0 missing payload hashes, latest projection about 54s old |
| `news_projection_dirty_targets` | 4 future source-quality schedule rows, 0 due, 0 leased, 0 failed, 0 invalid, 0 missing payload hash/watermark, 0 at-or-over retry budget |
| News Queue Terminal | 0 unresolved `news_projection_dirty_targets` terminal rows |
| Agent currents | Story-current rows were fresh in all status buckets; item-brief rows remained older audit/reuse state, not public serving fallback |

Static review during this refresh found two active hard-cut gaps and one
operator-config drift. News runtime workers still repaired malformed numeric
settings with `max(1, int(...))`; News projection dirty errors retried
indefinitely instead of using worker `max_attempts`; and the live
`news_page_projection.wakes_on` override still contained retired
`news_item_brief_updated` while missing the formal `news_story_brief_updated`
wake. The code now requires positive integer worker settings, terminalizes
exhausted News projection dirty claims into Queue Terminal, and wires page
projection to the formal story-current wake graph even when stale runtime
config still contains the old channel. No live News source row, item row,
projection row, terminal row, or provider payload was mutated during this
refresh.

The News repository source-fetch and canonical rebuild entrypoints were also
hardened after this pass: source refresh interval, canonical rebuild limit,
source claim limit, and source claim lease now reject malformed values before
SQL instead of being repaired through `max(..., int(...))`.

This was a code repair only. No News source row, item row, or provider payload
was mutated in the live database during this pass.

## Pulse And Notifications

A later read-only Pulse/notification aggregate probe confirmed the disabled and
enabled surfaces independently:

- `pulse_candidate` worker enabled: no.
- `notifications.enabled`: yes.
- `notification_rule` worker enabled: yes.
- `notification_delivery` worker enabled: yes.
- `pulse_candidates`: 0 total rows, 0 public rows, 0 hidden rows, 0 public rows
  missing `evidence_packet_hash`.
- `pulse_trigger_dirty_targets`: 13,952 total rows, all due and unleased in the
  sample. Attempt count was still 0 for every sampled aggregate bucket, with no
  leased rows, no rows at or above 3 attempts, and no non-positive source
  watermark rows.
- `pulse_agent_jobs` and `pulse_agent_runs`: 0 rows.
- Unresolved `worker_queue_terminal_events` for `pulse_agent_jobs`: 0.
- `notifications`: 34,926 total rows, 1,688 created in the preceding 24h at the
  sample time, latest row about 35 seconds old. Pulse-source notifications were
  0 because Pulse serving rows are empty while disabled; News-source
  notifications were 1,138.
- `notification_deliveries`: 954 total rows, all delivered in the aggregate
  sample; pending/running/failed/dead/active-exhausted counts were 0. Latest
  delivery update was about 13 minutes old.
- Unresolved `worker_queue_terminal_events` for `notification_deliveries`: 0.

This is consistent with the Kappa/CQRS contract: Pulse facts/control input can
accumulate while the Pulse agent worker is disabled, but no public Pulse read
model rows are served. Notifications are enabled and healthy in the aggregate
sample, with delivery state fully settled.

The latest sampled notification deliveries were all delivered through the
configured push channel, with no last error and one attempt each. No notification
ids or delivery ids were copied into this report.

A 2026-06-25 refreshed SELECT-only Notification probe, again using
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`, found the delivery lane still fully
settled:

- `notifications`: 36,163 total rows, 36,163 distinct notification ids, 36,163
  distinct dedupe keys, 0 rows missing payload JSON. Rule counts were 32,411
  `watched_account_activity`, 2,584 `watched_account_token_alert`, and 1,168
  `news_high_signal`.
- `notification_deliveries`: 983 total rows, all delivered through the
  configured push provider; pending, failed, running, dead, stale-running, and
  active-over-budget counts were all 0.
- Delivery attempt contract checks found 0 invalid attempt/max-attempt rows, 0
  running rows without a claim attempt, 0 reclaimable stale-running rows, 0
  terminalizable stale-running rows, and 0 delivery orphans.

The code follow-up hardened this already-healthy queue path: Notification
workers now reject malformed non-positive runtime settings instead of repairing
them to one, repository enqueue/running policies require positive integers, and
delivery complete/fail updates are scoped to the exact claimed attempt so a
late worker cannot overwrite a newer reclaimed attempt. No live notification,
delivery, read marker, or terminal row was mutated during this pass.

A 2026-06-25 refreshed SELECT-only Pulse probe, using the same
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`, found the Pulse lane still disabled
and serving-empty:

- `pulse_candidate` worker enabled: no; Pulse agent configured: yes; configured
  max attempts: 3.
- `pulse_candidates`: 0 total rows, 0 public-like rows, 0 rows missing
  `evidence_packet_hash`.
- `pulse_agent_jobs` and `pulse_agent_runs`: 0 rows.
- Unresolved `worker_queue_terminal_events` for `pulse_candidate`: 0.
- `pulse_trigger_dirty_targets`: 14,252 total rows, all due now, 0 actively
  leased, 0 at or over the worker retry budget, 0 non-positive source
  watermark rows, 0 rows missing payload hash, max attempt count 0.
- Dirty reasons were `token_radar_exited` 14,192, `token_radar_changed` 31,
  `token_radar_rank_changed` 24, and `token_radar_entered` 5.

This is a disabled-worker control-plane backlog, not public read-model
corruption: no Pulse candidates, agent jobs, agent runs, or terminal events are
being served or mutated while the worker remains off. The code follow-up
hardened the future enabled path: Pulse worker settings and dirty-trigger claim
parameters now reject malformed values, dirty-trigger completion rejects
malformed claimed attempt counts, and agent job success/failure/release paths
are scoped to the exact claimed attempt. No live Pulse dirty target, candidate,
job, run, or terminal row was mutated during this pass.

## CEX OI Board

A 2026-06-25 refreshed SELECT-only CEX OI probe, using
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`, matched the configured disabled
state:

- `cex_oi_radar_board` worker enabled: no.
- Runtime settings were batch size 100, universe limit 100, period `5m`,
  CoinGlass enrichment limit 5, and CoinGlass level limit 6.
- `cex_oi_radar_publication_state`: 0 rows.
- `cex_oi_radar_rows`: 0 rows, 0 missing identity or score-component fields.
- `cex_detail_snapshots`: 0 rows.
- `cex_derivative_series`: 0 rows.

This is expected while the worker is disabled and confirms there is no current
CEX OI serving-row drift in live data. The code follow-up hardened the future
enabled path: board worker settings, repository read limits, Binance OI builder
limits, and CoinGlass enrichment/level limits now reject malformed values at
the boundary instead of silently repairing them. No live CEX OI publication
state, board row, detail snapshot, derivative-series row, or provider request
was mutated during this pass.

## Narrative Admission

A 2026-06-25 refreshed SELECT-only Narrative Admission probe, using
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`, matched the configured disabled
state:

- `narrative_admission` worker enabled: no.
- Runtime settings were admission limit 200, source limit 2000, lease 60,000 ms,
  retry 60,000 ms, max attempts 3, windows `["1h"]`, and scopes `["all"]`.
- `narrative_admission_dirty_targets`: 0 rows, 0 due now, 0 actively leased,
  0 at or over retry budget, 0 rows missing payload hash, 0 rows with
  non-positive source watermark.
- `narrative_admissions`: 0 rows, 0 distinct serving keys, 0 rows missing
  payload hash.
- Unresolved `worker_queue_terminal_events` for
  `narrative_admission` / `narrative_admission_dirty_targets`: 0.

This is expected while the worker is disabled and confirms there is no current
Narrative serving-row or control-plane drift in live data. The code follow-up
hardened the future enabled path: worker settings, admission thresholds, dirty
claim parameters, and dirty error retry budget now reject malformed values at
the boundary; dirty completion now rejects malformed claimed attempt counts;
and exhausted dirty claims move into Queue Terminal instead of cycling
indefinitely. No live Narrative dirty target, admission row, or terminal event
was mutated during this pass.

## Queue And Terminal Backlog

The main operational debt is queue hygiene, not current read-model corruption:

| Queue/source | Evidence | Interpretation |
| --- | --- | --- |
| `token_discovery_dirty_lookup_keys` | about 2.7k active rows; about 8.7k unresolved terminal rows | mostly provider retry-budget exhaustion for DEX symbol lookups |
| `event_anchor_backfill_jobs` | 21,727 unresolved terminal rows in the latest sample; 0 active due/stale/running jobs | provider errors/no quotes/no market data for historical anchor backfill; control-plane terminal evidence, not current fact/read-model corruption |
| `token_radar_source_dirty_events` | about 200 active rows with high retry attempts | projection source queue was degraded because exhausted retries were being rescheduled instead of terminalized; public projection validation still passed |
| `macro_projection_dirty_targets` | 137 failed rows with high retry attempts in the latest sample, all in the `feature_frequency_unknown` bucket | macro serving snapshot remains ready/current; `irregular` frequency support was added so the next due worker pass can process these active rows without live manual mutation |
| `token_image_source_dirty_targets` | 2 unresolved terminal rows | small cache/image-source cleanup item |
| `pulse_trigger_dirty_targets` | about 13.9k due rows | expected while `pulse_candidate` is disabled |

These queues should not be bulk-cleared without a domain decision. They encode
provider coverage failures and retry history. The smallest safe next step is a
targeted bucket review by worker/source table/reason bucket, followed by an
operator-approved retry, archive, or ignore policy per bucket.

A 2026-06-25 follow-up event-anchor review found no active stuck work:

| Boundary | Aggregate evidence |
| --- | --- |
| `event_anchor_backfill_jobs` active state | 0 due pending, 0 stale pending, 0 stale running, 0 leased running, 0 active jobs with non-positive attempts |
| `event_anchor_backfill_jobs` historical states | 202,024 done rows, 21,594 failed rows, 126 expired rows |
| Event-anchor Queue Terminal | 21,727 unresolved rows: 10,039 provider error, 6,170 provider no quote, 5,382 no market data, 126 expired/other, 9 timeout, 1 retry-budget bucket |
| Historical-ready reconcile | 0 pending jobs already backed by ready enriched-event anchors |
| `enriched_events` anchor facts | 201,863 `tier3_inline` async-backfill anchors with ticks; unavailable anchors are represented by provider/no-quote/no-market-data terminal reasons |
| `market_ticks` event-anchor writes | 199,783 `tier3_inline` tick rows across 29,026 targets; 183 rows in the preceding hour |

Static review confirmed `EventAnchorBackfillWorker` checks existing persisted
ticks before provider calls, runs provider quote capture outside write
transactions, and writes ticks/enriched-event lifecycle/job state inside
worker-session transactions only. Queue Terminal retry for event-anchor rows
uses the terminal source snapshot to reopen the active window instead of
requeueing at an already-expired boundary. No live event-anchor job, terminal
event, enriched-event row, market tick, or provider state was mutated in this
follow-up.

## Kappa/CQRS Assessment

Observed runtime behavior is broadly consistent with the project Kappa/CQRS
contract:

- Provider frames are being converted into PostgreSQL facts/readable material
  facts; current social, market, news, and macro facts are fresh.
- Public read models are rebuilt/served from PostgreSQL, not from provider raw
  frames directly.
- Token Radar projection validation had zero mismatches in the sample.
- News public deduplication had zero enabled visible exact-content duplicate
  excess.
- Disabled worker surfaces are empty because they are disabled, not because
  facts are missing.
- Dirty/terminal queues preserve retry and provider-failure state instead of
  mutating facts silently.

No live repair was executed in this pass because the current public serving
models were healthy or empty by configuration, while the unhealthy areas are
provider-coverage/queue-policy buckets that require an explicit operator
decision before mutation.

## Code Follow-Up Applied

This resumed pass added additional code repairs from read-only diagnostics and
static Kappa/CQRS review:

- OKX DEX WebSocket adapter cleanup now uses the public
  `connection_state_payload()` state contract instead of the provider's private
  `_websocket` field.
- Macro feature freshness now accepts the implemented `intraday` frequency
  with a two-day stale window, while still rejecting unknown frequencies instead
  of falling back to daily behavior.
- Macro feature freshness now also accepts implemented core `irregular`
  frequency with a 140-day stale window, while still rejecting unknown
  frequencies instead of falling back to daily behavior.
- Token Radar source-dirty projection now isolates failures by affected target,
  so one missing Asset identity contract does not mark unrelated source dirty
  claims in the same batch failed.
- News item agent-brief priority now requires runtime admission to be a formal
  `NewsItemAgentAdmission` object rather than reflecting arbitrary objects with
  similarly named attributes.
- Live runtime config still carried an old `news_item_brief.wakes_on`
  `news_item_processed` override. The worker factory now ignores that retired
  item-brief wake path and wires item brief with empty wake channels; story
  brief remains the current consumer of `news_item_processed`.
- Static wake-surface review also found `news_item_brief_updated` had no current
  worker consumer after the story-current hard cut. The manifest, item-brief
  worker, `WakeBus`, factory dependency injection, and `docs/WORKERS.md` now
  remove that audit-only wake-out and its dead emitter dependency.
- News runtime workers now reject malformed or non-positive worker numeric
  settings instead of repairing them to 1 at runtime.
- News projection dirty-target failures now use worker `max_attempts` to
  terminalize exhausted claims into Queue Terminal instead of retrying active
  rows indefinitely.
- News page projection factory wiring now ignores stale runtime wake overrides
  that contain retired `news_item_brief_updated` and listens to the formal
  `news_story_brief_updated` wake channel.
- The broader manifest DB wake graph now rejects orphaned and non-`WakeBus`
  channels. This removed manifest-only `event_written` /
  `notification_delivery_due` outputs and added the real `news_item_written`,
  `news_page_dirty`, and `market_tick_written` producers that the runtime already
  emitted.
- Pulse candidate backpressure accounting now requires a formal
  `AgentCapacityReservation` with an `AgentExecutionErrorClass` reason, so loose
  reservation-like objects or string reason aliases fail at the worker contract
  boundary instead of being reflected.
- Resolution Refresh DEX discovery now requires formal `DexTokenCandidate`
  provider DTOs for candidate matching, ranking, persistence, raw-payload hashing,
  and scoring. Loose objects with similarly named attributes are no longer
  accepted as provider output.
- News item/story brief agent backpressure now requires formal
  `AgentCapacityReservation` plus `AgentExecutionErrorClass` reason values.
  String reason aliases and loose reservation-like objects fail at the worker
  contract boundary instead of being accepted through `StrEnum` equality or
  value reflection.
- Pulse decision stage-audit/no-start handling now validates
  `AgentExecutionError.error_class` as the formal `AgentExecutionErrorClass`
  enum before timeout classification or backpressure rethrow. String aliases no
  longer pass through `StrEnum` equality at the model-execution boundary.
- Asset Market Binance route sync now consumes formal `BinanceUsdtPerpRoute`
  DTOs at the domain service boundary. The CLI adapter maps integration
  `BinanceUsdmRoute` rows explicitly, and loose route-like objects are no longer
  reflected as CEX route inputs.
- Token Capture Tier changed-count accounting now rejects malformed tier
  repository results instead of converting them to zero changed rows. This keeps
  tier upsert/demotion rowcount evidence from degrading into silent no-op
  accounting.
- `IngestService` now consumes formal token-intent and event-capture DTOs at
  the event fact boundary. Token intent registry/lookup/alert writes require
  `TokenIntentInput`, and event capture commit rejects loose objects with
  matching `tick` / `capture` attributes instead of treating them as material
  fact inputs.
- `TokenIntentRepository` now accepts only formal `TokenIntentInput` objects or
  mapping rows as write inputs. Loose `__slots__` objects are rejected before SQL
  instead of being reflected into `token_intents` facts.
- `TokenEvidenceRepository` now accepts only formal `TokenEvidenceInput` objects
  or mapping rows as write inputs. Loose `__slots__` objects are rejected before
  SQL instead of being reflected into `token_evidence` facts.
- `IntentResolutionRepository` now accepts only formal `DeterministicResolution`
  objects or mapping rows as write inputs. Loose `__slots__` objects are
  rejected before SQL instead of being reflected into `token_intent_resolutions`
  facts.
- `TokenIntentResolver` now accepts only formal `TokenIntentInput` /
  `TokenEvidenceInput` objects or mapping rows as resolution inputs. Loose
  intent/evidence objects are rejected before deterministic resolution instead
  of being reflected from similarly named attributes.
- `PulseCandidateWorker` now rejects malformed claimed
  `pulse_agent_jobs.context_json` before evidence packet construction. Persisted
  job context scalar identity, gate/edge mapping, and timeline/evidence list
  fields must keep their formal JSON shapes instead of being coerced into
  strings, empty mappings, empty lists, or filtered refs.

These were code repairs only. No active queue row, terminal ledger row, read
model row, provider request, or source fact was mutated in live data for this
resumed pass.

The `asset_profiles` finding was traced to code and fixed after the read-only
live probe:

- `TokenRadarProjection` now fan-outs resolved DEX Asset rank changes into
  provider-scoped `asset_profile_refresh_targets` for the configured profile
  source-cache lane shape.
- The fan-out requires formal current-row Asset identity, positive source
  watermark, and chain/address fields before enqueueing. It does not scan
  serving rows or call providers inline.
- The worker manifest now lists `asset_profile_refresh_targets`,
  `token_profile_current_dirty_targets`, and `token_capture_tier_dirty_targets`
  in `token_radar_projection` control-plane writes so diagnostics can trace the
  producer.

This was a code repair only. No live queue mutation was run in this pass.

The `token_radar_source_dirty_events` high-retry finding was also traced to a
code-level control-plane gap and fixed after the read-only live probe:

- `TokenRadarProjectionWorker` now passes formal
  `settings.workers.token_radar_projection.max_attempts` into projection
  processing alongside `lease_ms` and `retry_ms`.
- `token_radar_dirty_targets` and `token_radar_source_dirty_events` error
  completion now splits retryable claims from exhausted claims. Retryable claims
  keep the existing delayed retry behavior; exhausted claims are deleted with
  `RETURNING queue.*` and terminalized into `worker_queue_terminal_events` in
  the same projection transaction.
- `token_radar_dirty_targets` and `token_radar_source_dirty_events` claim
  `UPDATE ... RETURNING` paths now require cursor rowcount to match the returned
  claimed rows before projection code processes work.
- The same claim-rowcount evidence pattern was also applied to the other
  rebuildable dirty-target claim paths audited in this pass: Asset Profile
  Refresh, Market Tick Current, Token Capture Tier, Token Image Source, Token
  Profile Current, Macro Projection, Narrative Admission, and Pulse Trigger.
- Queue Terminal retry transitions now support both Token Radar dirty queues,
  requeueing terminal snapshots through the formal repository enqueue methods.

This was a code repair only. No active Token Radar queue row or terminal ledger
row was mutated in the live database during this pass.

The `macro_projection_dirty_targets` high-retry finding was traced to the same
control-plane class and fixed after the read-only live probe:

- `settings.workers.macro_view_projection.max_attempts` is now a formal worker
  setting and default workers config field.
- `MacroViewProjectionWorker` passes the formal retry budget and worker name
  into dirty-target error completion.
- `MacroIntelRepository.mark_macro_projection_dirty_targets_error(...)` now
  reschedules claims below budget and deletes exhausted claims with
  `RETURNING queue.*`, writing `worker_queue_terminal_events` in the same
  transaction.
- Queue Terminal retry transitions now support `macro_projection_dirty_targets`,
  requeueing current or concept projection targets through Macro repository
  enqueue methods.

This was a code repair only. No active Macro queue row or terminal ledger row
was mutated in the live database during this pass.

The `token_discovery_dirty_lookup_keys` active high-retry finding was traced to
`ResolutionRefreshWorker` provider-unavailable handling:

- Ordinary provider errors and hot not-found completions already used the
  formal retry budget and terminalized exhausted lookup claims.
- The provider-unavailable branch rescheduled the entire claimed batch without
  checking `settings.workers.resolution_refresh.max_attempts`, allowing active
  lookup rows to keep accumulating attempts while the provider stayed
  unavailable.
- The worker now splits provider-unavailable claims by retry budget. Retryable
  rows keep the delayed retry path; exhausted rows are deleted and terminalized
  through `DiscoveryRepository.terminalize_lookup_claims(...)` in the same
  session transaction.

This was a code repair only. No active Discovery queue row or terminal ledger
row was mutated in the live database during this pass.

The `event_anchor_backfill_jobs` terminal backlog was audited separately:

- The active worker path already respects the formal retry budget for temporary
  provider failures, and terminalizes unavailable/expired anchors through the
  job table plus `worker_queue_terminal_events` evidence.
- The operator retry path for terminal snapshots was too narrow: it requeued an
  expired terminal job with `active_until_ms` no later than the retry timestamp.
  That could make a manual retry immediately stale before the worker could
  claim it.
- `EventAnchorBackfillJobRepository.retry_terminal_job_from_snapshot(...)` now
  derives a fresh active window from the persisted terminal source snapshot
  when Queue Terminal retries a job.

This was a code repair only. No Event Anchor job or terminal ledger row was
mutated in the live database during this pass.

The `pulse_trigger_dirty_targets` queue was audited after the Pulse/notification
aggregate probe:

- The current live backlog had not been claimed because `pulse_candidate` is
  disabled, so this was not an observed live high-retry backlog.
- Static review found that the error path would reschedule claimed trigger dirty
  rows without applying the formal `pulse_candidate.max_attempts` retry budget
  once the worker is enabled.
- `PulseCandidateWorker` now passes `settings.workers.pulse_candidate.max_attempts`
  and the worker name into dirty-trigger error completion.
- `PulseTriggerDirtyTargetRepository.mark_error(...)` now keeps retryable claims
  on the delayed retry path, deletes exhausted claims with `RETURNING queue.*`,
  and writes `worker_queue_terminal_events` in the same transaction.
- `PulseTriggerDirtyTargetRepository.claim_due(...)` now rejects malformed
  claim limits, lease durations, retry delays, max-attempt budgets, and empty
  lease owners before SQL rather than repairing them at runtime.
- Dirty-trigger done/error/reschedule completion now rejects malformed claimed
  attempt counts before SQL rather than converting bool or string attempts.
- `PulseJobsRepository` success, failure, backpressure-release, and
  provider-cooldown-release paths now require claimed job id, attempt count, and
  claim timestamp so stale workers cannot overwrite a newer reclaimed attempt.
- Queue Terminal retry transitions now support `pulse_trigger_dirty_targets`,
  requeueing terminal snapshots through the formal repository enqueue method.

This was a code repair only. No Pulse trigger dirty row or terminal ledger row
was mutated in the live database during this pass.

The Notification worker factory was also audited:

- The disabled-notifications construction path used a dynamic
  `getattr(workers, name)` settings probe even though both notification workers
  have formal settings fields.
- The factory now uses `workers.notification_rule.enabled` and
  `workers.notification_delivery.enabled` explicitly in the disabled path, just
  as it does in the enabled construction path.
- A later Notification runtime pass removed worker/repository one-value repairs,
  added delivery stale-terminalization rowcount evidence, and made
  complete/fail updates claim-scoped by delivery id, running status, attempt
  count, and claim timestamp.

This was a code repair only. No notification or delivery row was mutated in the
live database during this pass.

Runtime orchestration was audited as a static Kappa/CQRS compatibility boundary:

- `WorkerScheduler` now rejects malformed shutdown timeout settings instead of
  repairing negative, boolean, or non-numeric values to zero.
- `DBPoolBundle` wake-listener capacity now requires formal positive worker
  concurrency from worker settings instead of repairing malformed values to one.
- Queue Health now reports malformed adapter metric rows as unavailable adapter
  errors instead of converting them into empty/idle queue metrics.

This was a code repair only. No live queue row, read model row, terminal ledger
row, source fact, or provider request was mutated during this pass.

Collector ingest active-window wiring was audited as a formal control-plane
contract:

- `_PooledIngestStore` and `IngestService` now reject malformed
  `event_anchor_backfill.active_window_ms` values instead of repairing them with
  a one-value `max(1, int(...))` fallback.
- The active window remains passed explicitly from
  `settings.workers.event_anchor_backfill.active_window_ms` through runtime
  bootstrap into event-anchor job enqueueing.

This was a code repair only. No event fact, event-anchor job, queue row, or
provider request was mutated during this pass.

Shared worker lifecycle settings were audited as a runtime contract:

- `WorkerBase` now rejects malformed interval, soft/hard timeout, and backoff
  settings instead of coercing negatives, booleans, or strings through
  `max(0, ...)` / `float(...)` repairs.
- Zero intervals, zero timeouts, and zero backoff remain valid and still floor
  to the loop's minimum wait where needed.

This was a code repair only. No worker queue, terminal ledger row, serving row,
source fact, or provider request was mutated during this pass.

Wake listener waiting was audited as a runtime timeout contract:

- `WakeWaiter.wait(...)` / `async_wait(...)` now reject negative, boolean, or
  non-numeric timeout arguments before entering the LISTEN loop instead of
  coercing them through `max(0.0, float(timeout))`.
- Internal elapsed remaining time is still bounded to zero for normal timeout
  accounting after a legitimate wait has already started.

This was a code repair only. No LISTEN/NOTIFY state, queue row, terminal ledger
row, source fact, or provider request was mutated during this pass.

Worker PostgreSQL session timeouts were audited as a DB runtime contract:

- `DBPoolBundle` now rejects malformed worker-session `statement_timeout`
  values before setting PostgreSQL `statement_timeout`, instead of coercing
  negative, boolean, or string inputs into `0ms`.
- A malformed timeout discards the checked-out worker connection instead of
  returning a connection with partially applied session config.

This was a code repair only. No DB row, queue row, terminal ledger row, source
fact, or provider request was mutated during this pass.

Notification local delivery wake waiting was audited against the same timeout
contract:

- The notification factory's shared local delivery wake helper now rejects
  negative, boolean, or non-numeric wait timeouts instead of coercing them
  through `max(0.0, float(timeout))`.

This was a code repair only. No notification row, delivery row, queue row,
terminal ledger row, source fact, or provider request was mutated during this
pass.

Model-execution provider wiring was audited as an agent runtime contract:

- Agent lane timeout lookup and Pulse pipeline provider construction now reject
  zero, negative, boolean, or non-numeric timeout values instead of coercing
  them with `float(...)`.

This was a code repair only. No agent run, queue row, terminal ledger row,
source fact, or provider request was mutated during this pass.

Collector prepared-event handoff was audited as a formal ingest contract:

- Runtime bootstrap now requires `IngestService.prepare_event(...)` to return
  `PreparedIngest`; dict-shaped prepared payloads are rejected before
  event-anchor capture/backfill work is derived.

This was a code repair only. No event fact, event-anchor job, queue row,
terminal ledger row, source fact, or provider request was mutated during this
pass.

PostgreSQL client runtime options were audited as a lower-level DB contract:

- Statement and idle-in-transaction timeout options now reject negative,
  boolean, or non-numeric values before composing connection options instead of
  coercing malformed values into `0ms`.

This was a code repair only. No DB row, queue row, terminal ledger row, source
fact, or provider request was mutated during this pass.

Watchlist public read paths were audited as provider-free read contracts:

- Watchlist window days, overview source/cluster limits, and timeline limits
  now fail before SQL when malformed instead of being coerced with
  `max(1, int(...))` or `max(0, int(...))`.
- The route remains a read-only persisted-fact/current-resolution surface; no
  provider call or read-model write path was added.

This was a code repair only. No watchlist row, event fact, queue row, terminal
ledger row, source fact, or provider request was mutated during this pass.

Event Anchor Backfill runtime parameters were audited as worker/control-plane
contracts:

- Worker settings for batch size, concurrency, attempts, lease, active window,
  and max anchor lag now reject malformed values before provider capture work.
- Job repository active-window, claim, stale-retry, and terminal retry
  parameters now reject malformed values before SQL or transaction entry.

This was a code repair only. No event-anchor job, enriched-event capture,
market tick, queue row, terminal ledger row, source fact, or provider request
was mutated during this pass.

Asset Market live market runtime settings were audited as provider-front-door
contracts:

- Market tick poll, market tick stream, live price gateway, and token capture
  tier now reject malformed batch, concurrency, subscription, target, TTL, tier
  split, lease, and projection-limit values before provider IO, DB reads, or
  dirty-target claim writes.
- Zero remains accepted only for intentionally disable-like limits such as
  subscription/target/tier split counts; booleans and strings are rejected.

This was a code repair only. No token capture tier row, market tick,
dirty-target row, terminal ledger row, source fact, or provider request was
mutated during this pass.

Asset Market current/profile refresh settings were audited as derived-worker
contracts:

- Market tick current projection, token profile current, token image mirror,
  and asset profile refresh now reject malformed batch, lease, retry,
  max-attempt, provider-retry, and refresh interval settings before queue
  claims, mark-error writes, profile provider fetches, or image mirror error
  writes.

This was a code repair only. No market tick current row, token profile row,
image asset row, asset profile row, dirty-target row, terminal ledger row,
source fact, or provider request was mutated during this pass.

Market Tick Current dirty-target repository queue policy was audited as the
market-current projection control-plane contract beneath the worker:

- Claim limit, claim lease, retry delay, max attempts, and claimed attempt
  count now reject malformed values before repository-owned transactions,
  dirty queue SQL, or terminal retry handling.

This was a code repair only. No market tick current row, market tick fact,
dirty-target row, terminal ledger row, source fact, or provider request was
mutated during this pass.

Asset Profile Refresh target repository queue policy was audited as the
provider profile refresh control-plane contract beneath the worker:

- Bounded Token Radar backfill limit, claim limit, claim lease, retry delay,
  and claimed attempt count now reject malformed values before repository-owned
  transactions, profile-refresh queue SQL, or retry handling.

This was a code repair only. No asset profile row, asset-profile refresh
target, token-profile dirty target, terminal ledger row, source fact, or
provider request was mutated during this pass.

Token Profile Current dirty-target repository queue policy was audited as the
current-profile projection control-plane contract beneath the worker:

- Claim limit, claim lease, retry delay, and claimed attempt count now reject
  malformed values before repository-owned transactions, dirty queue SQL, or
  retry handling.

This was a code repair only. No token profile row, token-profile dirty target,
token-image dirty target, terminal ledger row, source fact, or provider request
was mutated during this pass.

Token Image Source dirty-target repository queue policy was audited as the image
mirror control-plane contract beneath the worker:

- Claim limit, claim lease, retry delay, max attempts, and claimed attempt count
  now reject malformed values before repository-owned transactions, image-source
  dirty queue SQL, or terminal retry handling.

This was a code repair only. No token image asset row, token-image dirty target,
token-profile current row, terminal ledger row, source fact, or provider request
was mutated during this pass.

Token Capture Tier dirty-target repository queue policy was audited as the
rank-set projection control-plane contract beneath the worker:

- Claim limit, claim lease, and claimed attempt count now reject malformed
  values before repository-owned transactions, rank-set dirty queue SQL, or
  completion handling.

This was a code repair only. No token capture tier row, capture-tier dirty
target, terminal ledger row, source fact, or provider request was mutated
during this pass.

Discovery lookup repository queue policy was audited as the Resolution Refresh
discovery control-plane contract:

- Enqueue intent count, claim limit, claim lease, running timeout, optional hot
  not-found retry timing, and claimed attempt count now reject malformed values
  before repository-owned transactions, lookup queue SQL, result-start writes,
  or terminal retry handling.

This was a code repair only. No discovery result row, discovery dirty lookup
key, terminal ledger row, source fact, or provider request was mutated during
this pass.

Resolution Refresh runtime settings were audited as discovery/control-plane
contracts:

- Discovery batch size, reprocess limit, lease duration, max attempts, and
  hot-not-found retry delay now reject malformed values before discovery
  claims, reprocess calls, or retry-budget decisions.

This was a code repair only. No discovery lookup row, token intent,
resolution fact, dirty-target row, terminal ledger row, source fact, or
provider request was mutated during this pass.

Macro Sync and Macro View Projection runtime settings were audited as
fact-ingest and derived read-model control-plane contracts:

- Macro Sync now rejects malformed batch size before starting a claimed-window
  loop.
- Macro View Projection now rejects malformed batch, lease, lookback,
  per-series, retry, and max-attempt settings before macro dirty-target claims,
  source refresh, or dirty-target error writes.

This was a code repair only. No macro sync window, macro observation, macro
projection dirty target, terminal ledger row, source fact, or provider request
was mutated during this pass.

Token Radar Projection worker runtime settings were audited as derived
read-model control-plane contracts:

- Token Radar Projection now rejects malformed batch, lease, retry,
  max-attempt, private-cache-retention, cold interval, debug override limit,
  and elapsed interval values before dirty-target claims, projection service
  calls, or private cache pruning.

This was a code repair only. No Token Radar current row, publication-state row,
dirty-target row, source-dirty event, terminal ledger row, source fact, or
provider request was mutated during this pass.

Token Radar target/source dirty repository queue policy was audited as the
projection control-plane contract beneath the worker:

- Target and source dirty repositories now reject malformed claim limits, claim
  leases, retry delays, max attempts, and bounded repair/list limits before
  repository-owned transactions, dirty queue SQL, or terminal retry handling.

This was a code repair only. No Token Radar current row, publication-state row,
dirty-target row, source-dirty event, terminal ledger row, source fact, or
provider request was mutated during this pass.

Macro repository projection/history parameters were audited as Macro
control-plane and read-path contracts:

- Macro projection dirty-target claim/error paths now reject malformed claim
  limits, leases, retry delays, and max attempts before transactions or SQL.
- Macro latest observations, source refresh, observations-for-concepts, and
  concept history reads now reject malformed history and limit parameters
  before SQL instead of repairing them to `1`.

This was a code repair only. No macro projection dirty target, macro
observation series row, macro view snapshot, terminal ledger row, source fact,
or provider request was mutated during this pass.

News Page Projection and News Source Quality Projection runtime settings were
audited as derived read-model worker contracts:

- Page Projection and Source Quality Projection now validate batch, lease,
  retry, and max-attempt settings before repository sessions, dirty-target
  claims, projection row writes, or page-dirty fan-out.

This was a code repair only. No news page row, source-quality row,
news-projection dirty target, terminal ledger row, source fact, or provider
request was mutated during this pass.

News Item Brief and Story Brief queue/backpressure boundaries were audited as
LLM worker control-plane contracts:

- Item and Story brief workers now reject malformed queue-depth and reservation
  claim-limit values before LLM capacity reservation, dirty-target claims, or
  repository sessions.

This was a code repair only. No news item brief row, news story brief row,
agent run ledger row, news-projection dirty target, terminal ledger row, source
fact, or provider request was mutated during this pass.

News Projection Dirty Target repository claim/error parameters were audited as
shared News projection control-plane contracts:

- Claim lease, claim limit, and retry delay now reject malformed values before
  repository-owned transactions, dirty-target SQL, or terminal retry handling.
- Claimed attempt count now rejects malformed values before completion or
  terminalization SQL, so projection completion can only consume claim tokens
  returned by `claim_due`.

This was a code repair only. No news page row, source-quality row,
news-projection dirty target, terminal ledger row, source fact, or provider
request was mutated during this pass.

## Queue Tool Follow-Up Applied

The terminal backlog finding also produced an operator-surface repair:

- `ops queue-resolve-bucket` now supports a bounded dry-run/execute workflow
  over unresolved `worker_queue_terminal_events` selected by exact worker,
  source table, and reason bucket.
- Dry-run reports aggregate counts only. Execute mode still resolves one
  terminal event at a time through the existing Queue Terminal transaction and
  retry/archive/quarantine state machine.
- The command output intentionally omits terminal ids, target keys, source rows,
  event ids, lookup keys, and provider payloads.
- `ops queue-inspect` and `ops queue-resolve-bucket` now reject non-positive
  limits before sampling queue rows or active queue-health tables. This closes
  the accidental `--limit 0` default-sample behavior seen during diagnostics.
- Macro projection terminal retries now require the formal Macro repository
  enqueue methods directly rather than probing for optional method presence.

No live terminal events were archived, quarantined, or retried in this pass.

## Boundary Hard-Cut Follow-Up Applied

The latest code pass tightened API/operator/stream boundaries found while
continuing the backend compatibility audit:

- API `_limit` now rejects negative, bool, and malformed values with
  `invalid_limit` instead of repairing negatives to zero. Token Case
  `posts_limit` now uses an explicit positive page-size contract instead of
  coercing `0` to `1`.
- `ops enqueue-token-radar-dirty-targets` and
  `ops enqueue-token-capture-tier-rank-set` now reject malformed repair limits
  at both argparse and helper boundaries. Token Radar dirty-target repair also
  rejects malformed `since_ms` instead of clamping it to zero.
- `ops repair-token-profile-images` now rejects malformed limits before DB
  bundle creation or dirty-target enqueue.
- Market Tick stream target selection now reuses the formal subscription-limit
  validator before converting tier rows into stream targets.
- Market Tick Stream and OKX DEX WebSocket provider subscription limits now
  both require positive integers, matching `workers.market_tick_stream` runtime
  settings. OKX WS subscription arg selection and circuit-failure thresholds
  also reject malformed values instead of repairing them to one.
- GMGN OpenAPI, RSS-like FeedClient, OpenNews REST, and CryptoPanic feed
  provider parameters now reject malformed rate, retry, timeout, page, kline,
  and `max_items` values before sending provider requests or opening transport
  sessions.
- Macro sync scheduler parameters now reject malformed window sizing,
  bootstrap cycle cap, steady interval, and max-attempt values before reading
  sync state or enqueueing Macro sync windows.
- Agent Execution gateway `rate_units` and structured JSON
  `client_validation_retries` now reject malformed values before acquiring
  capacity, reserving RPM, or calling the model provider.
- Notification cooldown, Pulse admission thresholds, Pulse timeline evidence
  budgets, Pulse freshness windows, and Pulse evidence market freshness now
  reject malformed values at their owning runtime/read boundaries instead of
  repairing them while constructing dedup keys, enqueue decisions, read health
  windows, or agent evidence packets.
- Pulse admission budget, Signal Pulse notification read limits, Pulse
  evidence max-age queries, stale-running job terminalization, and Pulse
  operator lookback windows now reject malformed values before SQL or report
  generation instead of rewriting them into one-hour, one-attempt, or zero-age
  windows.
- Ops diagnostics windows, projection validation samples, token image retry
  scheduling, and resolution-refresh symbol candidate caps now reject malformed
  runtime inputs before SQL, transactions, or candidate retention.
- Pulse agent run, run-step, serving candidate, and decision-mapping audit
  counts now reject malformed nonnegative fields instead of rewriting negative
  or malformed audit values to zero before writing the audit ledger.
- Resolution Refresh lookup-claim `attempt_count` and error-backoff
  `error_count` now require formal integer claim values; malformed or missing
  fields are rejected instead of being cast or clamped into retry-budget and
  backoff decisions.
- Token Radar projection dirty-claim `attempt_count` now rejects malformed
  non-integer claim values instead of casting them before completing or
  terminalizing projection dirty-target work.
- Token Radar rank-source/projection no longer carries the retired
  `discovery_results_json` input surface; unresolved lookup-key snapshots now
  come only from formal `lookup_keys_json` and are marked `not_searched`.
- Pulse decision stage audit latency and safety-net retry fields now reject
  malformed values instead of zero-repairing them before writing run-step audit
  rows.
- Agent Execution gateway safety-net retry audit fields now reject malformed
  values instead of casting them into zero on successful or failed provider
  calls.
- Agent Execution gateway now requires the formal LLM gateway surface
  (`api_key`, `base_url`, `trace_export_enabled`) instead of probing optional
  attributes with runtime defaults.

This was a code repair only. No provider request, market tick, token radar row,
token profile row, dirty target, queue terminal row, or public serving row was
mutated during this pass.

## 2026-06-26 Retry-Budget Inheritance Follow-Up

This follow-up used the live operator config reported by `uv run parallax
config` and performed only read-only diagnostics against the `~/.parallax`
PostgreSQL runtime. No provider request, queue mutation, terminal-event
operator action, or serving-row write was executed.

Read-only commands run:

- `uv run parallax ops worker-status`
- `uv run parallax ops queue-inspect --worker token_radar_projection --status active --limit 5`
- `uv run parallax ops queue-inspect --worker resolution_refresh --status terminal --reason-bucket retry_budget_exhausted --limit 5`
- `uv run parallax ops queue-inspect --worker event_anchor_backfill --status terminal --reason-bucket provider_error --limit 5`
- `uv run parallax ops queue-inspect --worker token_image_mirror --status terminal --reason-bucket retry_budget_exhausted --limit 5`
- `uv run parallax ops queue-inspect --worker macro_view_projection --status active --limit 5`
- `uv run parallax ops audit-token-radar --window 1h --scope all --limit 20`
- `uv run parallax ops validate-projections --sample 100`
- `uv run parallax macro status`

Live status summary:

| Surface | Read-only result |
| --- | --- |
| Token Radar serving audit | `ok=true`, 20 sampled 1h/all rows, 0 violations, 460 current-window source rows, social lag about 15.6s, market lag about 9.1s |
| Projection validation | `ok=true`, status `ready`, 100 checked rows, 0 mismatches |
| Macro facts/read model | migration ready, history ready, 84,352 observations, 188 concepts, latest projection published, projection lag 0 days |
| Token Radar source dirty queue | 379 active-scope rows, 372 failed, 327 at/over `max_attempts=3`, 258 failed/over-budget/due/released, max attempt 4618 |
| Token Radar target dirty queue | 5 active-scope rows, 0 failed, 0 at/over budget |
| Macro projection dirty queue | 138 active-scope rows, all failed and over-budget, all future-due, max attempt 469 |
| Resolution lookup dirty queue | 3,482 active-scope rows, 3,461 failed, 3,427 over-budget, mostly future-due, max attempt 183 |

Diagnosis:

- Product read models were current enough and contract-clean in the sampled
  Token Radar and Macro surfaces; the live issue is concentrated in worker
  control-plane dirty queues, not material facts.
- Several dirty queues contained active rows with `attempt_count` already at
  or above the formal worker `max_attempts`. Code inspection found a shared
  cause: `ON CONFLICT DO UPDATE` enqueue paths cleared `last_error` and wrote a
  new `payload_hash` but did not reset `attempt_count`, so a new work payload
  could inherit the retry budget from an old failed payload.
- The fix hard-cuts this inheritance across dirty queue repositories by
  resetting `attempt_count` to `0` when the effective work payload changes.
  Same-payload retry scheduling still preserves the existing budget.

Code paths updated:

- `asset_profile_refresh_targets`
- `market_tick_current_dirty_targets`
- `token_capture_tier_dirty_targets`
- `token_discovery_dirty_lookup_keys`
- `token_image_source_dirty_targets`
- `token_profile_current_dirty_targets`
- `macro_projection_dirty_targets`
- `narrative_admission_dirty_targets`
- `news_projection_dirty_targets`
- `pulse_trigger_dirty_targets`
- `token_radar_dirty_targets`
- `token_radar_source_dirty_events`

Verification:

- `uv run pytest tests/architecture/test_dirty_queue_attempt_budget_contract.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/test_discovery_repository.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py -q`: `354 passed`
- `uv run pytest tests/unit/test_market_tick_current_repository.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/test_token_profile_current_worker.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q`: `399 passed`
- `uv run pytest tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/unit/test_asset_profile_refresh_worker.py tests/unit/test_token_capture_tier_worker.py -q`: `120 passed`
- Targeted `ruff check`: passed
- Targeted `mypy` over 12 touched source files: passed
- `git diff --check`: passed

## 2026-06-26 Verification Follow-Up

No additional live provider mutation was run. After the dirty-queue
retry-budget fix, the remaining repository test suite was continued from the
generated-docs guard in ordered split batches. The generated schema drift was
refreshed, News story/source-quality fixtures were aligned with current story
agent storage, and worker-status queue-health tests were updated to include
Queue Terminal metrics.

Additional verification:

- Final targeted regression subset over News page/search, source quality/story
  agent storage, market tick dirty claims, Pulse dirty triggers, worker missed
  wake recovery, News worker settings, source-quality worker settings, and CLI
  worker-status: `371 passed`
- Generated docs guard: `1 passed`
- Full architecture suite: `1374 passed`
- Full `ruff check src tests`: passed
- `mypy src/parallax`: passed
- GMGN OpenAPI and Macrodata runner boundary subset: `61 passed`; targeted
  Ruff and mypy passed. This removed the remaining provider/CLI runtime clamps
  found in the final compatibility scan.

## Follow-Up Work

1. After deployment or local worker restart, re-run live diagnostics to confirm
   `asset_profile_refresh_targets` begins receiving Token Radar fan-out and
   `asset_profiles` starts populating from provider refreshes.
2. Review `event_anchor_backfill_jobs` terminal buckets by final reason and age,
   then define an archive/retry policy for provider-no-quote and no-market-data
   buckets. After deploying the Event Anchor retry fix, retry only the buckets
   that should receive another bounded provider attempt.
3. After deployment or local worker restart, re-run Discovery queue diagnostics
   to confirm provider-unavailable exhausted `token_discovery_dirty_lookup_keys`
   claims move into Queue Terminal instead of accumulating active attempts; then
   review unresolved retry-budget buckets for archive/retry/provider policy.
4. After deployment or local worker restart, re-run active queue diagnostics to
   confirm newly exhausted `token_radar_source_dirty_events` and
   `token_radar_dirty_targets` rows move into Queue Terminal instead of
   accumulating unbounded active retry attempts.
5. After deployment or local worker restart, re-run active queue diagnostics to
   confirm newly exhausted `macro_projection_dirty_targets` rows move into
   Queue Terminal instead of accumulating high active retry attempts.
6. Stale `news_item_agent_briefs` rows were confirmed by code trace as
   item-scoped audit/reuse state, not the public story-current fallback. Keep
   them out of public serving paths; only remove retained audit rows if a
   separate retention policy is approved. The refreshed live aggregate showed
   fresh `news_page_rows` and `news_story_agent_briefs`, 0 unresolved News
   terminal rows, and no due/unleased News projection dirty target backlog.
7. If `pulse_candidate` is re-enabled, re-run Pulse queue diagnostics after a
   bounded worker pass to confirm newly exhausted `pulse_trigger_dirty_targets`
   rows move into Queue Terminal instead of cycling indefinitely, and define an
   operator retry/archive policy per reason bucket.
8. If `narrative_admission` is re-enabled, re-run Narrative queue diagnostics
   after a bounded worker pass to confirm exhausted
   `narrative_admission_dirty_targets` rows move into Queue Terminal instead of
   cycling indefinitely.
9. After deploying the Macro `intraday` frequency fix, re-run Macro View
   Projection queue diagnostics to confirm the existing intraday crypto
   derivatives bucket no longer fails with an unknown-frequency contract error.
10. After deploying the Token Radar source-dirty batch-isolation fix, re-run
   source dirty diagnostics to confirm repaired Asset targets complete without
   being blocked by unrelated targets that still lack current identity.
