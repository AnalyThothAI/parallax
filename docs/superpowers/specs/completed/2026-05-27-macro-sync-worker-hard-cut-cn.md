# Spec — Macro Sync Worker Hard Cut

**Status**: Draft
**Date**: 2026-05-27
**Owner**: Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKFLOW.md`
- `docs/DESIGN_DISCIPLINE.md`
- `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-25-macro-terminal-hard-cut-spec-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`

## Background

Macro Intel currently has a documented batch-first source path rather than a
runtime fact-ingest worker. The domain architecture says the service does not
fetch FRED, NY Fed, Treasury, Cboe, CFTC, or crypto provider data directly; it
receives normalized observations from the packaged `macrodata-cli` bundle
command or an operator-maintained path
(`src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md:3`). The same
document defines `macro_observations` as facts written by
`gmgn-twitter-intel macro import-bundle` or operator maintenance, while
`macro_observation_series_rows`, generation pointers, and
`macro_view_snapshots` are read models owned by `MacroViewProjectionWorker`
(`src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md:11`).

The project-wide worker inventory makes the same distinction: the macro bundle
importer is not a long-running worker; the CLI writes `macro_observations` and
`macro_import_runs`, then the projection worker re-reads those facts
(`docs/WORKERS.md:87`). The runtime manifest registers only
`macro_view_projection` for Macro Intel, and it is classified as a projection
worker that writes `macro_view_snapshots`
(`src/gmgn_twitter_intel/app/runtime/worker_manifest.py:633`). The macro worker
factory also constructs only `MacroViewProjectionWorker`
(`src/gmgn_twitter_intel/app/runtime/worker_factories/macro_intel.py:13`).

The current projection worker refreshes projected observation rows from
persisted observations, reads bounded concept series, builds a deterministic
snapshot, and writes the read model
(`src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py:33`).
It does not call providers. The public macro routes likewise read the latest
snapshot or projected observation rows from repositories; they do not fetch
provider data at request time
(`src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py:41`).

The CLI has one-shot macro import, sync, and status commands
(`src/gmgn_twitter_intel/app/surfaces/cli/parser.py:55`). The sync runner
currently launches `uv run macrodata bundle history ...` and injects the configured
FRED key into child env
(`src/gmgn_twitter_intel/integrations/macrodata/runner.py:25`). Runtime provider
wiring for `macrodata` currently exposes only a stock quote provider, not a
macro fact sync provider
(`src/gmgn_twitter_intel/app/runtime/provider_wiring/macrodata.py:8`). Docker
mounts `~/.gmgn-twitter-intel` into `/root/.gmgn-twitter-intel`, but it does not
mount host-local source checkouts or pass FRED env by default
(`compose.yaml:95`).

Live diagnostics on 2026-05-27 showed the failure mode: `macro_view_projection`
keeps recomputing snapshots, but the newest `macro_observations` fact is still
`2026-05-23`; the latest snapshot is computed on 2026-05-27 with
`asof_date=2026-05-23`, `status=partial`, and `history_ready=false`. A read-only
host probe of `macrodata bundle history macro-core --start 2026-05-24 --end
2026-05-27` returned fresh observations through `2026-05-27`, proving the
current gap is not simply upstream absence. A container probe also showed that
the current sync runner is not container-native because it still shells through
`uv`, the FRED env is unset there, and `uv` is not available on the container
`PATH`.

## Problem

The macro page can look newly computed while serving stale business facts. The
runtime has a projection worker but no fact-ingest worker that continuously
pulls normalized macro observations into PostgreSQL. Manual or CLI-driven
imports can temporarily advance facts, but they do not make `/macro` a live
Kappa/CQRS product: freshness depends on out-of-band operator action, container
runtime settings can silently differ from host smoke tests, and the app has no
durable worker state that proves currentness, provider failure, or catch-up
progress.

## First principles

1. PostgreSQL material facts remain the only business truth. Provider envelopes
   and raw macrodata CLI output are inputs, not public truth.
2. Normal runtime has exactly one Macro Intel fact-ingest writer and exactly one
   Macro Intel read-model writer. `macro_sync` writes `macro_observations` and
   import/sync audit state; `macro_view_projection` writes projected series rows
   and snapshots.
3. HTTP handlers, React Query hooks, and frontend pages never call macro
   providers. They read deterministic read models and explicit data gaps.
4. Worker catch-up is bounded and claim-first. A no-work cycle must not scan
   large historical facts to discover work, and provider calls must occur only
   after the worker has claimed a bounded sync window or steady-state cycle.
5. Secrets live only in operator-controlled environment variables and child
   process environment. They never appear in argv, logs, DB audit JSON, frontend
   payloads, fixtures, or docs.

## Goals

- G1. Add a normal runtime `macro_sync` worker that advances
  `macro_observations` from macrodata `macro-core` history bundles without
  operator-triggered CLI imports.
- G2. Preserve Kappa/CQRS ownership: `macro_sync` writes macro facts and sync
  audit state only; `macro_view_projection` remains the only writer for
  `macro_observation_series_rows`, active generation pointers, and
  `macro_view_snapshots`.
- G3. Make Docker the production truth: a running app container can execute the
  macro sync path without `uv`, without a host-local `macrodata-cli` checkout,
  and without copying secrets into repository config.
- G4. Make freshness observable. `macro status`, worker status, and macro module
  provenance expose latest sync attempt, latest imported `asof_date`, max
  observed fact date, provider/data-quality outcome, and whether projection is
  behind facts.
- G5. Make initial history catch-up automatic but bounded. A fresh deployment
  can progress from missing or insufficient macro history toward configured
  history readiness through finite date-window claims across cycles.
- G6. Make steady-state updates resilient to provider lag and revisions. Each
  scheduled cycle re-syncs a bounded overlap window and upserts observations
  idempotently.
- G7. Remove the old batch-only runtime assumption. No macro page, projection
  worker, or readiness path may rely on a manual `macro sync` or
  `macro import-bundle` run for normal freshness.

## Non-goals

- N1. This work does not redesign the macro terminal UI, module catalog, or
  deterministic regime scoring.
- N2. This work does not add LLM explanations, AI macro briefs, or trading
  recommendations.
- N3. This work does not fetch providers from HTTP/API routes or frontend code.
- N4. This work does not keep a compatibility fallback that calls the old
  `uv run macrodata` runner from runtime.
- N5. This work does not make every upstream macro concept perfectly available;
  missing SRF, discontinued volatility series, and naturally lagged monthly or
  quarterly releases remain explicit data-health states.
- N6. This work does not change non-macro workers except for shared manifest,
  status, or documentation updates needed to register the new worker.

## Target architecture

Macro Intel gains a dedicated fact-ingest worker named `macro_sync`.

`macro_sync` is a scheduled, bounded provider-ingest worker. It owns durable
sync-window control state, claims one bounded window or steady-state cycle,
executes the packaged macrodata bundle path outside any database transaction,
validates the returned envelope, then opens a short transaction to upsert
normalized observations and record sync/import audit state. On successful fact
mutation it wakes the projection lane; the wake is a hint only, and
`macro_view_projection` still performs bounded interval catch-up.

`macro_view_projection` remains the read-model writer. It never fetches
providers and never imports macrodata envelopes. Its responsibility is unchanged:
refresh projected series rows from facts, switch active generations, build the
deterministic `macro_regime_v4` snapshot, and write the macro read model.

The macrodata integration becomes container-native. Runtime sync uses the
packaged macrodata executable or package entry point installed in the app image,
not `uv run` and not a configured host checkout. If a working directory is
configured, it must be valid inside the container; otherwise runtime uses the
installed package. The child process receives `FRED_API_KEY` only through env,
populated from the configured operator env name such as
`FINANCE_FRED_API_KEY`.

CLI macro commands may remain as operator surfaces, but they are not separate
runtime implementations. `macro sync` uses the same sync use case as the worker
for one bounded run, and `import-bundle` remains an explicit offline replay or
seed tool for saved envelopes. There is no legacy runtime branch that continues
to depend on `uv`, host-local checkouts, or manual page-refresh imports.

## Conceptual data flow

```text
macro_sync control state
  -> macro_sync worker claims bounded date window
  -> packaged macrodata macro-core history bundle
  -> normalized macro observations
  -> macro_observations / macro_import_runs / sync audit state
  -> wake hint
  -> macro_view_projection
  -> macro_observation_series_rows / active generation / macro_view_snapshots
  -> /api/macro, /api/macro/modules/{module_id}, /api/macro/series
  -> web /macro
```

The new arrow is the first one: runtime now owns a bounded provider-ingest lane
for macro facts. Existing API and UI arrows stay read-only. Existing projection
arrows stay rebuildable from facts.

## Core models

- **Macro sync source**: A configured macro bundle source. It identifies the
  bundle name, source priority, enabled state, desired bootstrap horizon,
  steady-state overlap window, and provider credential env name. It is
  configuration/control metadata, not product truth.
- **Macro sync window**: A bounded claimable unit of work. It has a date range,
  trigger reason, lifecycle state, lease metadata, attempt counters, and a
  payload identity. It exists so runtime can claim work before provider IO and
  so missed wake recovery does not require broad fact scans.
- **Macro sync run**: An audit record for one provider fetch/import attempt. It
  records source, bundle, requested date range, outcome, redacted credential
  readiness, coverage, reason codes, provider diagnostics, imported observation
  count, max observed date, and duration. It must not store raw secrets.
- **Macro observation**: The material fact already owned by Macro Intel:
  concept, source, series, observation date, numeric value, quality, source
  timestamp, and raw provider payload. Upsert identity remains stable so
  overlap-window re-syncs are idempotent.
- **Macro projection snapshot**: The deterministic read model already consumed
  by macro APIs and the frontend. It is rebuilt from projected observation
  rows, not from provider output.

## Interface contracts

- **Worker contract**: `macro_sync` appears in canonical worker status with
  enabled/running state, last result, last error, queue depth or due-window
  count when practical, claimed window count, provider run count, imported row
  count, max observed date, latest asof date, redacted credential readiness,
  and wake outcome. Idle cycles report no due work without fetching providers.
- **Config contract**: Worker config names the bundle, bootstrap horizon,
  maximum date-window span, steady-state overlap, interval, timeout, retry, and
  credential env name. Config stores env var names and booleans only, not secret
  values.
- **CLI contract**: `macro sync` is an operator-triggered execution of the same
  sync semantics used by `macro_sync`, useful for bounded verification and
  repair. `macro import-bundle` imports a saved macrodata envelope for offline
  replay or seed data, using the same validation and upsert semantics as the
  worker import path.
- **HTTP contract**: Macro APIs remain provider-free. They may expose richer
  freshness/provenance derived from sync audit and projection state, but they
  must not call macrodata, FRED, Yahoo, NY Fed, CFTC, Treasury, or Cboe.
- **Readiness/status contract**: A stale macro source is reported as stale or
  partial with reason codes. The system must distinguish "projection is current
  but facts are old" from "facts are fresh but projection has not caught up".

## Acceptance criteria

- AC1. WHEN the app starts with `macro_sync.enabled=true` and no sufficient
  macro history, THEN the worker SHALL claim bounded historical windows and
  import observations across cycles until the configured history horizon is
  covered or explicit provider/data-quality gaps are recorded.
- AC2. WHEN upstream macrodata returns observations newer than the current
  `macro_observations` max observed date, THEN the worker SHALL upsert those
  observations into facts without requiring any manual `macro sync` or
  `macro import-bundle` command.
- AC3. WHEN `macro_sync` imports facts, THEN `macro_view_projection` SHALL be
  woken or catch up by interval and write a snapshot whose `asof_date` reflects
  the newest eligible facts.
- AC4. WHEN there is no due sync window and steady-state overlap is not due,
  THEN the worker SHALL return an idle result without provider IO and without
  scanning broad `macro_observations` history.
- AC5. WHEN the worker runs inside the Docker app container, THEN it SHALL use
  the packaged macrodata runtime without `uv` and without a host-local
  `macrodata-cli` checkout.
- AC6. WHEN the configured FRED env var is present, THEN the provider child
  process SHALL receive the key via environment only; argv, logs, DB audit
  rows, API payloads, and status payloads SHALL contain only env var names and
  redacted booleans.
- AC7. WHEN the configured FRED env var is absent or a provider fails, THEN the
  worker SHALL record a retryable/data-quality outcome and macro status SHALL
  surface the source-health problem without fabricating fresh facts.
- AC8. WHEN `/api/macro`, `/api/macro/modules/{module_id}`, or
  `/api/macro/series` is called, THEN the request path SHALL read PostgreSQL
  read models/facts only and SHALL perform no provider IO.
- AC9. WHEN `macro sync` is used manually for repair, THEN it SHALL execute the
  same sync/import semantics as the worker rather than a legacy runner branch.
- AC10. WHEN architecture tests inspect worker ownership, THEN `macro_sync`
  SHALL be classified as a Macro Intel fact-ingest worker and
  `macro_view_projection` SHALL remain the only Macro Intel read-model writer.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Provider fetch is slow or rate-limited inside a normal worker loop. | High | Claim small date windows, cap window span, enforce timeouts, and record retryable source-health outcomes instead of blocking projection or API paths. |
| Initial bootstrap overloads macrodata or external providers. | High | Split history into finite windows, process a bounded number per cycle, and make progress visible in worker/status payloads. |
| A stale host-local config path works in development but fails in Docker. | High | Runtime sync must default to the packaged macrodata runtime and treat invalid container paths as configuration errors, not fallbacks. |
| Secret values leak through diagnostics. | High | Store only env var names and redacted booleans; ban secret values in argv, logs, audit JSON, API payloads, and tests. |
| Overlap-window re-sync duplicates facts. | Medium | Preserve stable observation identity and idempotent upsert semantics for source/concept/date/series. |
| Projection runs before fact import commits. | Medium | Commit facts and audit before wake hints; projection also catches up by interval from committed PostgreSQL state. |
| API currentness appears healthy because projection computed recently. | Medium | Status separates fact freshness, sync freshness, and projection freshness. |
| A manual CLI path drifts from worker semantics. | Medium | CLI sync delegates to the same sync use case; no second runner implementation is allowed. |

## Evolution path

After this hard cut, Macro Intel can add additional macro bundle sources or
provider-specific source-health adapters by adding new bounded sync sources and
windows. The design should not foreclose source-specific cadence policies,
provider-level backoff, or richer data-health pages. It should also not
collapse macro source ingestion into projection: keeping facts and read models
separate is what makes later provider additions rebuildable and auditable.

## Alternatives considered

- Alternative A — Keep manual `macro sync` / `import-bundle` as the freshness
  mechanism. Rejected because it preserves the root cause: page freshness
  depends on out-of-band operator action and no runtime worker owns facts.
- Alternative B — Make `macro_view_projection` fetch macrodata before building
  snapshots. Rejected because it mixes fact ingestion with read-model writing
  and breaks the single-writer Kappa/CQRS boundary.
- Alternative C — Fetch fresh macro data from `/api/macro` on demand. Rejected
  because request paths would perform provider IO, expose users to provider
  latency/failure, and make facts non-rebuildable.
- Alternative D — Run a host cron outside the app container. Rejected because it
  repeats the host/container drift observed in diagnostics and hides freshness
  from canonical worker status.
- Alternative E — Wrap the current `uv run macrodata` runner in a worker.
  Rejected because it is not container-native and would preserve the exact
  compatibility seam that failed in Docker.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Add `macro_sync` as the normal runtime Macro Intel fact-ingest owner; keep API/frontend provider-free; keep `macro_view_projection` as the read-model writer; report source/fact/projection freshness separately; use bounded claims before provider IO; keep secrets out of argv/logs/DB/API. |
| Ask first | Expanding `macro-core` source coverage, changing macro scoring thresholds, changing public module layout, or adding new public freshness fields that frontend must render immediately. |
| Never | No runtime fallback to manual imports, no `uv run` dependency in the app container, no host-local checkout requirement, no provider IO in API or React code, no dual old/new macro sync branches, no secret values in persisted or public diagnostics. |
