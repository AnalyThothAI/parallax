# Macro Intel Architecture

Macro Intel owns deterministic macro regime read models inside
`gmgn-twitter-intel`. It does not fetch FRED, NY Fed, Treasury, Cboe, CFTC, or
crypto provider data directly; normalized observations arrive as persisted
facts from the packaged `macrodata-cli` bundle command or an
operator-maintained path.

## Ownership

| Object | Category | Runtime writer |
|--------|----------|----------------|
| `macro_observations` | Fact | `gmgn-twitter-intel macro import-bundle` / operator maintenance path. Normal runtime projection does not mutate it. |
| `macro_import_runs` | Import audit | `gmgn-twitter-intel macro import-bundle`. It records coverage and diagnostics; it is not the product truth. |
| `macro_view_snapshots` | Read model | `MacroViewProjectionWorker` only. |

## Flow

```text
macrodata bundle history macro-core
  -> macro-core JSON bundle
  -> app/surfaces/cli/commands/macro.py import-bundle
  -> macro_observations / macro_import_runs
  -> repositories/macro_intel_repository.py
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
`macro_regime_v4` snapshot stores:

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
`transmission`, `data_health`, `section_boards`, summarized provenance rows,
and related routes. Overview/global regime fields describe the whole macro
state; module-local `data_health` and `section_boards` describe page readiness
and section evidence without overriding global scores. Raw provider payloads,
old provenance JSON blobs, and old v1/v2 module fields are not public
compatibility surfaces.

## CLI And Operations

- Docker installs `AnalyThothAI/macrodata-cli` from the `v0.1.5` Git tag.
  Its executable is `macrodata`; do not mount or reference a host-local
  `/Users/.../macrodata-cli` checkout in deployment.
- `macrodata bundle macro-core --asof <YYYY-MM-DD> | gmgn-twitter-intel macro
  import-bundle --stdin` is the container-native import path. The v0.1.5 bundle
  emits Yahoo-backed cross-asset proxies (`asset:spy`, `asset:qqq`, `asset:iwm`,
  `asset:tlt`, `asset:hyg`, `asset:lqd`, `asset:gld`, `asset:uso`, `fx:dxy`,
  `crypto:btc`, and `crypto:eth`) which are projected as canonical concepts.
- Chart-ready runs use the history bundle path:

  ```bash
  macrodata bundle history macro-core --start <YYYY-MM-DD> --end <YYYY-MM-DD> \
    | uv run gmgn-twitter-intel macro import-bundle --stdin
  uv run gmgn-twitter-intel macro project-once
  ```

- `uv run gmgn-twitter-intel macro import-bundle --file /path/bundle.json`
  imports a macrodata-cli `macro-core` bundle. `--stdin` is the streaming
  equivalent. The command upserts observations and writes one import-run audit
  row with status, coverage, and reason codes.
- `uv run gmgn-twitter-intel macro project-once` reads persisted
  `MACRO_CORE_CONCEPTS` history, builds a `macro_regime_v4` snapshot, and writes
  `macro_view_snapshots`.
- `uv run gmgn-twitter-intel macro status` reports migration readiness,
  observation count, concept count, history readiness, concepts below minimum
  history, latest import run, and latest snapshot.
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
