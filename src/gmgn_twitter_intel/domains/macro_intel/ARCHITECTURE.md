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
macrodata bundle macro-core
  -> macro-core JSON bundle
  -> app/surfaces/cli/commands/macro.py import-bundle
  -> macro_observations / macro_import_runs
  -> repositories/macro_intel_repository.py
  -> services/macro_feature_engine.py
  -> services/macro_regime_engine.py
  -> services/macro_scenario_engine.py
  -> runtime/macro_view_projection_worker.py
  -> macro_view_snapshots
  -> /api/macro
  -> web /macro
```

The macro regime engine emits component scores with evidence and data gaps.
The v2 snapshot stores:

- `features_json`: per-series latest value, deltas, z-score, percentile, and
  freshness diagnostics when history is available.
- `chain_json`: seven deterministic transmission nodes: `liquidity`, `rates`,
  `fed_corridor`, `volatility`, `credit`, `positioning`, and `cross_asset`.
- `scenario_json`: current regime, confirmations, contradictions, trade map,
  validation indicators, and watch triggers.
- `scorecard_json`: projection version, overall/chain scores, coverage ratio,
  observed/required series counts, data-gap count, and chain regimes.

UI and LLM-facing surfaces must read those deterministic fields rather than
recomputing or inventing macro conclusions. Sparse source coverage should
surface as `data_gap` / neutral scenario context, not as a false stress signal.

## CLI And Operations

- Docker installs `AnalyThothAI/macrodata-cli` from the `v0.1.2` Git tag.
  Its executable is `macrodata`; do not mount or reference a host-local
  `/Users/.../macrodata-cli` checkout in deployment.
- `macrodata bundle macro-core --asof <YYYY-MM-DD> | gmgn-twitter-intel macro
  import-bundle --stdin` is the container-native import path.
- `uv run gmgn-twitter-intel macro import-bundle --file /path/bundle.json`
  imports a macrodata-cli `macro-core` bundle. `--stdin` is the streaming
  equivalent. The command upserts observations and writes one import-run audit
  row with status, coverage, and reason codes.
- `uv run gmgn-twitter-intel macro project-once` reads persisted
  `MACRO_CORE_SERIES` history, builds a `macro_regime_v2` snapshot, and writes
  `macro_view_snapshots`.
- `uv run gmgn-twitter-intel macro status` reports migration readiness,
  observation count, series count, latest import run, and latest snapshot.
- `uv run gmgn-twitter-intel db health` must report the expected migration
  version before real-data verification.

Live-data debugging must first confirm runtime config with
`uv run gmgn-twitter-intel config`. Report only paths, booleans, and command
results; do not print raw WebSocket tokens, API keys, or provider secrets.

## Known Data-Source Limits

Real runtime smoke on 2026-05-21 verified the branch with operator-owned config
at `~/.gmgn-twitter-intel/` and migration `20260521_0077`. The imported
macro-core bundle had 3 available series out of 33 because `FRED_API_KEY` was
not configured and Stooq access/API-key requirements left some providers
unavailable. Those conditions are represented as structured partial coverage,
reason codes, and data gaps.

An already-running backend on `127.0.0.1:8765` returned old
`macro_regime_v1`; that process was not verified as this branch's code. Restart
the backend from `codex/macro-regime-70` before claiming live HTTP v2
verification for `/api/macro`.
