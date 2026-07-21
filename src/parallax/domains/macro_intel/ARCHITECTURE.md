# Macro Intel Architecture

Macro Intel is a Kappa/CQRS domain. PostgreSQL observations are the only
business truth; API routes read deterministic projections and never call a
macro provider. The normal ingest lane is `MacroSyncWorker`. `macro
import-bundle` is an offline replay/seed entrypoint into the same fact and
attempt contracts.

## Ownership

| Object | Kind | Single runtime writer |
| --- | --- | --- |
| `macro_observations` | Material fact | `MacroSyncWorker`; offline import may replay the same fact contract. |
| `macro_sync_windows` | Scheduling/control state | `MacroSyncWorker`. |
| `macro_sync_runs` | Sync or offline-import attempt ledger | `MacroSyncWorker` and the offline import command. |
| `macro_projection_dirty_targets` | Projection queue | Fact import enqueues changed concepts; `MacroViewProjectionWorker` claims and completes them. |
| `macro_observation_series_rows` | Rebuildable bounded-history read model | `MacroViewProjectionWorker`. |
| `macro_observation_series_publication_state` | Projection attempt/currentness state | `MacroViewProjectionWorker`. |
| `macro_view_snapshots` | Stable current macro snapshot | `MacroViewProjectionWorker`. |

There is no second import-attempt table. `macro_sync_runs` records both
provider-window attempts and offline imports; an offline row has
`sync_window_id=NULL` and may have no requested date range when the imported
bundle contains neither observations nor an as-of date. Coverage, missing
series, provider errors, reason codes, fact write counts, watermarks, timing,
and redacted diagnostics live on that one attempt row. Attempt rows are audit
metadata, not product truth.

There is also no separate daily-brief table, column, or worker. The assets
daily brief is embedded only in the `assets` entry of `module_views_json`.
Every catalog module payload is built in the same projection transaction.
Schema revision `20260722_0186` drops the retired top-level
`macro_view_snapshots.assets_brief_json` column.

## Data flow

```text
macro_sync_windows
  -> MacroSyncWorker bounded claim
  -> configured macrodata history bundle
  -> macro_observations + macro_sync_runs
  -> changed concept dirty targets
  -> MacroViewProjectionWorker bounded catch-up
  -> macro_observation_series_rows
  -> macro_regime_v4 + module_views_json in macro_view_snapshots
  -> /api/macro, /api/macro/series, /api/macro/modules/{module_id}
```

The projection worker runs on its configured interval, claims a bounded batch,
and re-reads PostgreSQL. Provider raw frames and child-process output are
inputs, never serving facts.

The provider boundary returns one exact `MacrodataBundleRunResult` containing
an envelope and redacted diagnostics. Runtime invokes only the installed
package entrypoint through the current Python interpreter; there is no
console-script, `PATH`, legacy catalog, or result-shape fallback.

## Fact identity and ingest

`macro_observations` keeps provider evidence, including raw payload, source
priority, provider timestamp, and ingestion timestamp. Its material identity
is concept/source/series/date. The fact payload hash excludes runtime fetch and
sync identifiers, so a replay of identical evidence is a no-op. A material
change updates the fact and enqueues the affected concept; unchanged evidence
writes no serving row and creates no dirty target.

Provider execution happens outside database transactions. Fact upserts,
attempt recording, sync-window completion, state watermarks, and dirty-target
enqueue happen in one repository-session transaction. A stale lease or failed
terminal transition rolls that transaction back.

The offline importer first validates and normalizes the complete envelope,
then writes facts, dirty targets, and one `macro_sync_runs` row in one
`RepositorySession.transaction`. It does not open a raw connection transaction
or keep a separate import ledger.

## Compact series read model

`macro_observation_series_rows` intentionally contains only:

- `projection_version`
- `concept_key`
- `observed_at`
- `value_numeric`
- `source_name`
- `series_key`
- `unit`
- `frequency`
- `data_quality`
- `event_metadata_json`

Its stable key is `(projection_version, concept_key, observed_at)`. The source
winner is selected while projecting from facts. The table does not persist a
rank, source priority, provider timestamp, raw provider payload, ingestion or
projection clocks, or a duplicate row payload hash. Changed/unchanged
comparison uses the compact content in memory and the upsert has a row-value
`IS DISTINCT FROM` guard. An unchanged refresh therefore writes zero serving
rows.

`event_metadata_json` is the only payload exception. It is a flat whitelist
needed by official calendar, Treasury auction, and Fed communication display:
event code/text, source URL, document type/speaker, event time/reference
period, CUSIP, announcement/settlement dates, and reopening flag. Full raw
evidence remains only in `macro_observations`.

Serving history queries require explicit concepts, lookback, and per-concept
limit. They use requested concepts plus a `LATERAL` indexed scan ordered by
`observed_at DESC`, so one concept cannot consume another concept's budget and
the request path does not globally rank or sort the wide fact table. The
primary key supports this fixed-prefix reverse scan; a second history-order
index would duplicate it.

A refresh selecting no rows for a concept that already has current rows fails
closed and preserves the last published partition. Dirty-target claim, compact
series mutation, snapshot write, and target completion are caller-owned by the
projection transaction. Failed work rolls back partial projection writes
before retry state is recorded.

## Snapshot and public surfaces

`macro_view_snapshots` has one stable row per `projection_version`. The current
contract is `macro_regime_v4`; runtime code does not fall back to older
projection or module versions. The snapshot stores deterministic panels,
indicators, triggers, gaps, feature history, source coverage, transmission
chain, scenarios, scorecard, and one
`module_views_json` entry for every stable `MACRO_MODULE_IDS` key. The assets
brief exists only as `module_views_json.assets.daily_brief`. Missing JSON
sections or module keys are malformed rows, not values to repair with empty
compatibility defaults.

`/api/macro/modules/{module_id}` reads its precomputed module object directly
from `module_views_json`; it does not query observations, call the module
builder, or join News at request time. The independent `/api/macro/series`
surface reads compact series rows. Missing facts or coverage surface as
explicit gaps/partial status. Event rows consume `event_metadata_json`; they
never fall back to raw payload or provenance blobs. UI and LLM-facing code
render persisted deterministic conclusions rather than recomputing provider
evidence.

## Runtime configuration

Live execution uses operator-owned `~/.parallax/config.yaml` and
`~/.parallax/workers.yaml`. `uv run parallax config` is the authority for the
resolved paths. `workers.macro_sync` owns bundle names, provider execution
timeout, window size, claim lease, retry cadence, and batch size.
`workers.macro_view_projection` owns statement timeout, dirty-target batch,
lease/retry budget, lookback, and per-series cap. Credentials are reported only
as redacted configuration state.
