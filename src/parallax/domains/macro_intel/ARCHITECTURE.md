# Macro Intel Architecture

Macro Intel owns deterministic macro regime read models inside
`parallax`. Normal freshness is owned by the `macro_sync` runtime
worker: it claims bounded sync windows, runs the packaged `macrodata-cli`
history bundle outside DB transactions, and persists normalized observations
as facts. API routes and frontend pages never call FRED, NY Fed, Treasury,
Cboe, CFTC, crypto providers, or macrodata directly.

## Ownership

| Object | Category | Runtime writer |
|--------|----------|----------------|
| `macro_observations` | Fact | `MacroSyncWorker` in normal runtime; `macro import-bundle` only for offline replay/seed. |
| `macro_import_runs` | Import audit | `MacroSyncWorker` and offline replay. It records coverage and diagnostics; it is not the product truth. |
| `macro_sync_windows` | Sync control | `MacroSyncWorker` only. It owns claim, retry, and bounded catch-up state; claimed windows must carry valid `attempt_count` and `max_attempts` before retry-budget classification. |
| `macro_sync_runs` | Sync audit | `MacroSyncWorker` and `macro sync` through the same service. It records redacted provider/source health. |
| `macro_projection_dirty_targets` | Projection control | `MacroSyncWorker` enqueues after changed facts; `MacroViewProjectionWorker` claims before reading facts. |
| `macro_observation_series_rows` | Read model | `MacroViewProjectionWorker` only. It is a compact current-only projection from `macro_observations` and owns request-path latest/history rows. |
| `macro_observation_series_publication_state` | Read-model state | `MacroViewProjectionWorker` only. It records the current source signature and latest refresh status. |
| `macro_view_snapshots` | Read model | `MacroViewProjectionWorker` only. One stable current row keyed directly by natural `projection_version`; no synthetic snapshot identifier. |
| `macro_daily_briefs` | Read model | `MacroDailyBriefProjectionWorker` only. One stable row per brief key, currently `assets_today`, derived from the current macro view snapshot. |

## Flow

```text
macro_sync_windows
  -> MacroSyncWorker claim
  -> packaged macrodata history bundles configured in workers.macro_sync.bundle_names
  -> macro_observations / macro_import_runs / macro_sync_runs
  -> wake macro_observations_imported
  -> macro_projection_dirty_targets
  -> repositories/macro_intel_repository.py
  -> macro_observation_series_rows
  -> services/macro_feature_engine.py
  -> services/macro_regime_engine.py
  -> services/macro_scenario_engine.py
  -> runtime/macro_view_projection_worker.py
  -> macro_regime_v4 in macro_view_snapshots
  -> wake macro_view_snapshot_updated
  -> MacroDailyBriefProjectionWorker
  -> assets_today in macro_daily_briefs
  -> /api/macro and /api/macro/modules/{module_id}
  -> macro_module_view_v3
  -> web /macro
```

The macro regime engine emits component scores with evidence and data gaps.
The hard-cut public projection is `macro_regime_v4`. Runtime code does not
fall back to `macro_regime_v3` or `macro_module_view_v1`. The
`macro_observation_series_rows` projection absorbs observation dedupe and
per-concept history ranking before request time. Macro API/module/series
request paths read that table for latest observations, bounded concept series,
and history counts directly by `projection_version`. They do not run
`row_number()` over `macro_observations` and do not fall back to raw
observations when projected rows are absent.

`MacroViewProjectionWorker` claims `macro_projection_dirty_targets` first. If no
dirty target is due, it does not scan `macro_observations`. After a claim, it
refreshes `macro_observation_series_rows` before it builds and writes the
`macro_regime_v4` snapshot. The refresh writer may use window functions over
`macro_observations` because it is the single projection writer; request paths
may not. Refresh is source-signature based: unchanged facts update only
`macro_observation_series_publication_state` with
`latest_attempt_status='unchanged'` and write zero serving rows, while changed
facts replace the compact current rows and the single current snapshot for the
projection version in one `RepositorySession.transaction`. Dirty-target claim,
series refresh, snapshot write, and dirty-target done state are committed by the
worker session transaction, not by worker-level `commit=True` fragments. If the
projection fails after claim, partial read-model writes are rolled back before
the dirty target is marked retryable. `macro_view_snapshot_updated` is emitted
only after that transaction exits. A refresh that selects zero rows marks
publication state `failed`, raises `macro_observation_series_empty`, and leaves
existing current rows untouched. Runtime physical generations, run ids, and
timestamp snapshot ids are not a serving contract. Existing current-series rows
must carry non-empty `payload_hash` values before change detection; malformed
current rows fail before delete/insert instead of comparing as empty signatures.

`MacroViewProjectionWorker` is configured only by the formal
`macro_view_projection` worker settings. Its worker-session statement timeout,
dirty-target claim batch, lease, retry cadence, lookback window, and
per-series history cap are direct settings reads. The minimum history coverage
for `lookback_days` and `limit_per_series` is enforced by the settings schema,
not by runtime fallback constants in the worker. The factory injects a
post-commit `wake_emitter`; there is no constructor `wake_bus` alias for this
read-model writer.

`MacroDailyBriefProjectionWorker` is also configured only by its formal
`macro_daily_brief_projection` worker settings. It reads worker-session
statement timeout directly, has no provider IO, and keeps `assets_today` as the
stable current-row key for `macro_daily_briefs`.

`MacroIntelRepository.refresh_observation_series_rows_for_concepts(...)`
requires a connection transaction before deleting exited current rows, inserting
changed current rows, or updating `macro_observation_series_publication_state`.
Missing connection transaction support is a repository/session contract failure,
not a `nullcontext` compatibility path. Existing current-row payload hashes are
required read-model signatures for changed/unchanged comparison.
Macro sync-window terminal/retry/failure writes, `macro_sync_state` repair,
`macro_projection_dirty_targets` enqueue/done/error mutations, and
`macro_observation_series_rows` delete/upsert paths also require PostgreSQL
`cursor.rowcount` evidence before returning write counts. Missing or invalid
rowcount is malformed repository/driver state, not zero Macro work or inferred
target/row-length success; single-row sync/state paths reject multi-row counts.
Macro projection dirty-target claim `UPDATE ... RETURNING` paths also require
cursor rowcount to match returned claimed rows before projection payloads are
loaded or reported as claimed.
Macro sync-window enqueue and claim `RETURNING` paths validate rowcount against
returned-row presence before reporting enqueued, no-work, or claimed control
state; returned-row presence alone is not a sync-window state-machine contract.
`macro_view_snapshots` and `macro_daily_briefs` current-row
`RETURNING true AS changed` writes use the same evidence rule: the cursor
rowcount must be a valid single-row count and must match returned-row presence
before snapshot changed booleans, downstream wakes, daily-brief writes, or
worker `rows_written` accounting are reported.

`MacroIntelRepository` repository-owned `macro_projection_dirty_targets`
claim/done/error mutations also require a callable connection transaction before
dirty-target SQL. `MacroViewProjectionWorker` keeps those queue writes
caller-owned with `commit=False` inside `RepositorySession.transaction`; direct
repository callers that omit transaction support fail before claim, delete, or
retry SQL instead of falling back to naked `self.conn.commit()`. Failure
completion receives formal `settings.workers.macro_view_projection.max_attempts`
and `worker_name`; claims below budget are rescheduled, while exhausted claims
are deleted with `RETURNING queue.*` and recorded in
`worker_queue_terminal_events` using the claimed payload hash and stable
`projection_name:projection_version:target_kind:target_id` target key.

The `macro_regime_v4` snapshot stores:

- `panels_json`, `indicators_json`, `triggers_json`, and `data_gaps_json`:
  deterministic display/module payloads emitted by the regime engine. Empty
  objects or arrays are valid only when the engine emits those fields
  explicitly; `MacroIntelRepository` must not restore missing sections through
  `{}` or `[]` defaults before payload hash or `macro_view_snapshots` upsert.
- `features_json`: concept-keyed semantic label fields, latest value,
  freshness days, history point counts, `20d` / `60d` / `252d` history windows,
  deltas, z-score, percentile, score participation, structured data gaps, and
  source metadata.
- `source_coverage_json`: latest coverage ratio, history coverage ratio,
  required/current concept counts, required/history-ready concept counts,
  concepts below minimum history, and latest observed date.
- `chain_json`: seven deterministic transmission nodes: `liquidity`, `rates`,
  `fed_corridor`, `volatility`, `credit`, `positioning`, and `cross_asset`.
- `scenario_json`: current regime, confirmations, contradictions, trade map,
  validation indicators, and watch triggers.
- `scorecard_json`: projection version, overall/chain scores, coverage ratio,
  history coverage ratio, observed/required concept counts, data-gap count, and
  chain regimes.

Snapshot status is history-aware:

- `missing`: no usable required facts.
- `partial`: latest facts exist but required module/history coverage is
  insufficient, including one-point-per-concept imports.
- `stale`: facts exist but freshness windows are exceeded.
- `ready`: latest facts, required history coverage, and data-quality thresholds
  pass.

UI and LLM-facing surfaces must read those deterministic fields rather than
recomputing or inventing macro conclusions. Sparse source coverage should
surface as `data_gap` / neutral scenario context, not as a false stress signal.
When a current snapshot is absent, `/api/macro` may return the explicit
`macro_view_snapshot_missing` data-gap response. When a snapshot is present,
its JSON sections are part of the persisted read-model contract; the API must
require mapping/list-shaped `panels_json`, `indicators_json`, `triggers_json`,
`data_gaps_json`, `source_coverage_json`, `features_json`, `chain_json`,
`scenario_json`, and `scorecard_json` instead of repairing malformed rows with
empty objects or arrays.
Module pages consume only `macro_module_view_v3`, whose payload is
display-ready: semantic snapshot headers, tiles, one primary chart with
minimum-point status, typed display tables, `module_read`, `module_evidence`,
`transmission`, `data_health`, summarized provenance rows,
and related routes. The `/macro/assets` module is a real page, not a parent
redirect. It combines the assets module view with the optional
`assets_today` daily brief read model; the API reads the persisted brief and
does not recompute the daily judgement during request handling. A missing
`assets_today` row is an honest absent read-model value; a missing
`latest_macro_daily_brief` repository method is a route/repository contract
failure and must not be treated as "no brief". Overview/global regime fields
describe the whole macro state; module-local `data_health` describes page
readiness without overriding global scores. Raw provider payloads, old
provenance JSON blobs, and old v1/v2 module fields are not public compatibility
surfaces. `data_health` gap rows are display-ready source-health records:
module pages preserve the backend `label`, `severity`, `scope`, and
`remediation_hint` so missing implemented depth sources are shown as concrete
repair actions rather than frontend-inferred provider advice or opaque warning
chips.
Module view shaping follows the same persisted-snapshot contract as
`/api/macro`: `snapshot=None` may render an explicit missing module view, but a
present snapshot must carry the formal mapping/list-shaped JSON sections before
the builder can produce `macro_module_view_v3`. The builder must not restore
missing `features_json`, `chain_json`, `scenario_json`, or `data_gaps_json`
through empty compatibility payloads.
The overview module's decision console is derived from `scenario_json` and
module data-health payloads inside the module-view builder, then rendered by
the frontend without local macro scoring. `top_changes`, `quality_blockers`,
`trade_map`, `future_catalysts`, `watchlist_alerts`, and `data_credibility`
are the first-screen compression layer; raw indicator codes are not
user-facing product copy. Source-backed official calendar, Treasury auction,
Federal Reserve text events, and projected News Intel story rows are rendered
as the top-level `module_read.market_event_flow` block after
`structured_analysis`, not as duplicated decision-console event sections. Macro
overview may consume the `news_page_rows` read model for source-backed news
events, but must not repair or reshape raw `news_items` as a macro fallback.
Standalone macrodata event bundles such as `macro-calendar-core`,
`treasury-auction-core`, and `fed-text-core` are part of the default
`macro_sync` bundle set and may also be imported into `macro_observations` as
`event:*` concepts. Those event concepts are importable facts and projected
series rows for module display, but they do not expand `MACRO_CORE_CONCEPTS`,
do not participate in numeric `macro_regime_v4` scoring/history readiness, and
changed event-only dirty targets refresh `macro_observation_series_rows`
without rebuilding the current macro snapshot. Text/document events such as
Fed statements, minutes, press releases, and speeches may have
`value_numeric=NULL` in both facts and `macro_observation_series_rows`; product
copy is taken from the raw payload/provenance title, never from a numeric
sentinel value. Overview market-event rows preserve official `source_url`
provenance when present; Fed text rows also expose `document_type` and speech
`speaker` metadata for inspection without restoring deleted Fed text routes or
adding text-score compatibility fields. Official calendar rows preserve
source-provided release timing and reference periods when available, including
BLS `event_time_et` and `reference_period`.
`macro-calendar-core` currently covers official Federal Reserve, BEA, and BLS
next-release events; BLS rows remain event-only and do not imply
actual-vs-consensus, revision, or surprise coverage.
Proxy-only and gap-only macro modules are hard-deleted from the public macro
module catalog instead of being hidden or kept as compatibility shells. Removed
ids use the ordinary unsupported-module route; future pages need real persisted
facts and a new catalog entry before they become product surface again.

Offline replay is also a fact-ingest path. `macro import-bundle` writes
`macro_observations`, `macro_import_runs`, and
`macro_projection_dirty_targets` through `RepositorySession.unit_of_work` and
`require_transaction`; it must not fall back to raw `conn.transaction` or
manual commits when test/runtime sessions omit the formal contract.

## CLI And Operations

- Docker installs `AnalyThothAI/macrodata-cli` from the pinned Git tag.
  Runtime sync uses the packaged `macrodata` executable when the console
  script is healthy, or the installed Python package entrypoint when the
  script is absent or stale. It does not use `uv run macrodata`, and
  deployment must not mount or reference a host-local `/Users/.../macrodata-cli`
  checkout.
- Docker operators provide `FINANCE_FRED_API_KEY` through environment or a
  deployment secret manager. Config stores only the env var name and status
  surfaces expose only env names/booleans, never secret values.
- Runtime macrodata execution reads the formal root settings properties
  `macrodata_fred_api_key_env` and `macrodata_fred_api_key`, plus
  `workers.macro_sync.macrodata_timeout_seconds`; it must not probe older
  nested `providers.macrodata` shapes or root-level timeout fallbacks.
  The default FRED env name is owned by settings. If
  `macrodata_fred_api_key_env` is `null` or blank, runtime code treats env
  lookup as disabled and must not restore `FINANCE_FRED_API_KEY` locally.
- `workers.macro_sync.macrodata_timeout_seconds` bounds the macrodata child
  process. Timeout is recorded as source health and does not rely on worker
  thread cancellation to stop provider IO.
- `workers.macro_sync` is the single formal execution-budget contract for
  sync source identity, `bundle_names`, due-window enqueue cadence, claim
  lease, retry delay, session timeout, and bounded windows per cycle. Runtime
  code must read those fields directly and must not synthesize defaults from
  older settings shapes or constructor wake aliases.
- `uv run parallax macro sync --bundle macro-core --start <YYYY-MM-DD>
  --end <YYYY-MM-DD>` runs one operator-triggered bounded window through the
  same `MacroSyncService` as `macro_sync`.
- `uv run parallax macro import-bundle --file /path/bundle.json`
  imports a saved macrodata-cli envelope for offline replay/seed.
  `--stdin` is the streaming equivalent. It emits the persisted-fact wake hint
  but is not the normal freshness path. The importer requires
  `RepositorySession.unit_of_work` and `require_transaction`; it must not fall
  back to raw `conn.transaction` or manual commits when test/runtime sessions
  omit the formal contract.
- `uv run parallax macro status` reports migration readiness,
  observation count, concept count, history readiness, concepts below minimum
  history, latest import run, latest sync run, sync queue state,
  `facts_max_observed_at`, projection lag, latest snapshot, and installed
  `macrodata-cli` package/bundle capability. If
  `required_bundle_series_available` is false, the packaged macrodata
  dependency is too old for the current Parallax series map even if individual
  providers can fetch data manually.
- `volatility/vix` uses persisted macro facts only. MOVE is represented by the
  packaged macrodata Yahoo Finance `yahoo:^MOVE` proxy mapped to `vol:move`;
  licensed ICE/Bloomberg MOVE or intraday redistribution is tracked only as
  source backlog until a separate approved feed exists.
- `MacroSyncService.enqueue_due_windows(...)` reports sync queue state only
  through the formal `MacroIntelRepository.macro_sync_queue_summary(...)`
  contract over persisted `macro_sync_windows`; missing method support is
  repository/session wiring failure, not an empty queue-summary state.
- Macro Sync provider-failure classification reads the claimed window
  `attempt_count` and `max_attempts` directly before choosing retryable versus
  failed state. Missing or non-positive values are malformed claim-window state,
  not first-attempt defaults.
- `uv run parallax db health` must report the expected migration
  version before real-data verification.

Live-data debugging must first confirm runtime config with
`uv run parallax config`. Report only paths, booleans, and command
results; do not print raw WebSocket tokens, API keys, or provider secrets.

## Known Data-Source Limits

Real runtime smoke must use operator-owned config at `~/.parallax/`
and the current migration head. Provider failures from the packaged macrodata
bundle are represented as structured partial coverage, reason codes, and data
gaps. If FRED public CSV times out or no optional FRED API key is configured,
that is a source-health/data-quality gap and should leave affected pages
`partial`; it is not a frontend issue and must not be hidden behind `ready`.
The pinned macrodata contract exposes `ok`, `stale`, `partial`, and
`unavailable` data quality. Macro sync persists `ok` as an `ok` run and maps
the other three explicit quality states to `partial`; retired `empty` and
unknown values fail the import contract instead of becoming compatibility
successes.
