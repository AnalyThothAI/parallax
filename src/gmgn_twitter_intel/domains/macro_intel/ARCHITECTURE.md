# Macro Intel Architecture

Macro Intel owns deterministic macro regime read models inside
`gmgn-twitter-intel`. Normal freshness is owned by the `macro_sync` runtime
worker: it claims bounded sync windows, runs the packaged `macrodata-cli`
history bundle outside DB transactions, and persists normalized observations
as facts. API routes and frontend pages never call FRED, NY Fed, Treasury,
Cboe, CFTC, crypto providers, or macrodata directly.

## Ownership

| Object | Category | Runtime writer |
|--------|----------|----------------|
| `macro_observations` | Fact | `MacroSyncWorker` in normal runtime; `macro import-bundle` only for offline replay/seed. |
| `macro_import_runs` | Import audit | `MacroSyncWorker` and offline replay. It records coverage and diagnostics; it is not the product truth. |
| `macro_sync_windows` | Sync control | `MacroSyncWorker` only. It owns claim, retry, and bounded catch-up state. |
| `macro_sync_runs` | Sync audit | `MacroSyncWorker` and `macro sync` through the same service. It records redacted provider/source health. |
| `macro_projection_dirty_targets` | Projection control | `MacroSyncWorker` enqueues after changed facts; `MacroViewProjectionWorker` claims before reading facts. |
| `macro_observation_series_rows` | Read model | `MacroViewProjectionWorker` only. It is a compact current-only projection from `macro_observations` and owns request-path latest/history rows. |
| `macro_observation_series_publication_state` | Read-model state | `MacroViewProjectionWorker` only. It records the current source signature and latest refresh status. |
| `macro_view_snapshots` | Read model | `MacroViewProjectionWorker` only. One stable row per projection version, keyed as `macro-view:{projection_version}:current`. |

## Flow

```text
macro_sync_windows
  -> MacroSyncWorker claim
  -> packaged macrodata bundle history macro-core
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
projection version in one transaction. A refresh that selects zero rows marks
publication state `failed`, raises `macro_observation_series_empty`, and leaves
existing current rows untouched. Runtime physical generations, run ids, and
timestamp snapshot ids are not a serving contract.

The `macro_regime_v4` snapshot stores:

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
Module pages consume only `macro_module_view_v3`, whose payload is
display-ready: semantic snapshot headers, tiles, one primary chart with
minimum-point status, typed display tables, `module_read`, `module_evidence`,
`transmission`, `data_health`, summarized provenance rows,
and related routes. Overview/global regime fields describe the whole macro
state; module-local `data_health` describes page readiness without overriding
global scores. Raw provider payloads,
old provenance JSON blobs, and old v1/v2 module fields are not public
compatibility surfaces.

## CLI And Operations

- Docker installs `AnalyThothAI/macrodata-cli` from the `v0.1.5` Git tag.
  Its executable is `macrodata`; runtime sync uses that packaged executable,
  not `uv run macrodata`, and deployment must not mount or reference a
  host-local `/Users/.../macrodata-cli` checkout.
- Docker operators provide `FINANCE_FRED_API_KEY` through environment or a
  deployment secret manager. Config stores only the env var name and status
  surfaces expose only env names/booleans, never secret values.
- `workers.macro_sync.macrodata_timeout_seconds` bounds the macrodata child
  process. Timeout is recorded as source health and does not rely on worker
  thread cancellation to stop provider IO.
- `uv run gmgn-twitter-intel macro sync --bundle macro-core --start <YYYY-MM-DD>
  --end <YYYY-MM-DD>` runs one operator-triggered bounded window through the
  same `MacroSyncService` as `macro_sync`.
- `uv run gmgn-twitter-intel macro import-bundle --file /path/bundle.json`
  imports a saved macrodata-cli `macro-core` envelope for offline replay/seed.
  `--stdin` is the streaming equivalent. It emits the persisted-fact wake hint
  but is not the normal freshness path.
- `uv run gmgn-twitter-intel macro status` reports migration readiness,
  observation count, concept count, history readiness, concepts below minimum
  history, latest import run, latest sync run, sync queue state,
  `facts_max_observed_at`, projection lag, and latest snapshot.
- `uv run gmgn-twitter-intel db health` must report the expected migration
  version before real-data verification.

Live-data debugging must first confirm runtime config with
`uv run gmgn-twitter-intel config`. Report only paths, booleans, and command
results; do not print raw WebSocket tokens, API keys, or provider secrets.

## Known Data-Source Limits

Real runtime smoke must use operator-owned config at `~/.gmgn-twitter-intel/`
and the current migration head. Provider failures from the packaged macrodata
bundle are represented as structured partial coverage, reason codes, and data
gaps. If FRED public CSV times out or no optional FRED API key is configured,
that is a source-health/data-quality gap and should leave affected pages
`partial`; it is not a frontend issue and must not be hidden behind `ready`.
