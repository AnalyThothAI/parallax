# Macro Intel Architecture

Macro Intel is a completed-snapshot Kappa/CQRS domain. PostgreSQL
`macro_observations` are the only business truth. The normal ingest lane is
`MacroSyncWorker`; `macro import-bundle` is an offline replay/seed entrypoint
into the same fact and attempt contracts. Public reads select persisted current
documents or compact series and never call a provider.

## Ownership

| Object | Kind | Single runtime writer |
|---|---|---|
| `macro_observations` | Material fact | `MacroSyncWorker`; offline import may replay the same fact contract |
| `macro_sync_windows` | Scheduling/control state | `MacroSyncWorker` |
| `macro_sync_runs` | Sync/offline-import attempt ledger | `MacroSyncWorker` and the offline import command |
| `macro_projection_dirty_targets` | Projection queue | fact import enqueues; `MacroViewProjectionWorker` claims/completes |
| `macro_observation_series_rows` | Rebuildable bounded-history read model | `MacroViewProjectionWorker` |
| `macro_observation_series_publication_state` | Series attempt/currentness state | `MacroViewProjectionWorker` |
| `macro_view_snapshots` | Stable current six-document snapshot | `MacroViewProjectionWorker` |

`macro_sync_runs` is the only import/sync attempt ledger. Attempt identity and
timestamps are audit metadata, not product identity.

## Data flow

```text
macro_sync_windows
  -> MacroSyncWorker bounded claim
  -> configured macrodata history bundle
  -> macro_observations + macro_sync_runs
  -> changed-concept dirty targets
  -> MacroViewProjectionWorker bounded catch-up
  -> compact observation series
  -> clock recheck when the UTC date or completed-market-session cutoff advances
  -> one atomic macro_decision_v2 snapshot with six typed documents
  -> six page reads + one independent series read
```

The projection worker runs on its configured interval, claims a bounded batch,
and re-reads PostgreSQL. When no target is due, it re-evaluates persisted
compact rows once per `(UTC date, latest completed US session)` bucket so
freshness and the market cutoff cannot freeze when providers publish no new
facts. A restart performs the same bounded PostgreSQL re-read; the in-memory
bucket only suppresses duplicate work within one process and is not a
correctness boundary. Provider frames and child-process output are inputs,
never serving facts. Provider execution occurs outside database transactions.

The provider boundary returns one exact `MacrodataBundleRunResult` containing
an envelope and redacted diagnostics. Runtime invokes the installed package
entrypoint through the current Python interpreter. Fact upserts, attempt
recording, sync-window completion, watermarks, and dirty-target enqueue share
one repository-session transaction.

## Fact identity

`macro_observations` preserves source/series/concept/date identity, numeric or
event value, unit/frequency/quality, provider provenance, source and ingestion
times, and the raw evidence payload. Its material identity is
concept/source/series/date. The fact payload hash excludes fetch and sync
identifiers, so identical replay writes nothing. A material change updates the
fact and enqueues the affected concept.

The offline importer validates and normalizes the complete envelope before it
opens the write transaction. It then writes facts, dirty targets, and one
`macro_sync_runs` row atomically.

## Compact series

`macro_observation_series_rows` contains only:

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

Its stable key is `(projection_version, concept_key, observed_at)`. Source
selection occurs during projection. Lifecycle clocks, source priority, raw
provider payload, and duplicate payload hashes are absent. Row-value
`IS DISTINCT FROM` guards make unchanged refreshes zero-write.

`event_metadata_json` is a flat whitelist required by official calendars,
Treasury auctions, and Federal Reserve communications: event code/text, source
URL, document type/speaker, event time/reference period, CUSIP,
announcement/settlement dates, and reopening flag. Full evidence remains in
`macro_observations`.

Series queries require explicit concepts, a supported window, and bounded
per-concept scans. The public windows are `20d`, `60d`, `120d`, `1y`, and
`3y`. A refresh that selects no rows for a concept with an already-published
partition fails closed and preserves that partition.

## Evidence snapshot deep module

`macro_concept_manifest.py` is the one ownership table for evidence concepts.
Every entry fixes its page, section, role, output and source unit, frequency,
freshness limit, legal change window, change method/periods, criticality, and
claim effect.

`build_macro_evidence_snapshot(...)` accepts persisted observations and one
computation time. It returns shared snapshot metadata plus exactly:

1. `overview`
2. `cross_asset`
3. `rates_inflation`
4. `growth_labor`
5. `liquidity_funding`
6. `credit`

Each page carries:

- snapshot version, fact watermark, latest completed US-session market cutoff,
  and computation time;
- a 1–4 week horizon;
- strict conclusion status, judgment, rule version, and actual rule hits;
- drivers, confirmations, contradictions, and upgrade/invalidation conditions;
- evidence references, page freshness, full evidence rows, and named
  unavailable capabilities.

Evidence rows retain value, unit, frequency-aware change/window, observation
date, source, series, quality, freshness/age, real sample range/count,
criticality, claim effect, and derivation inputs/formula/references where
needed. Critical missing, stale, or malformed evidence makes the affected
conclusion `insufficient_evidence`. Optional absence makes it `degraded`.
Unsupported capabilities are `not_assessed` with a reason and no numeric value.

Overview adds a deterministic decision map. `shock_summary.state` is
`dominant`, `no_dominant_shock`, or `insufficient_evidence`; the candidate,
when present, is limited to `growth`, `inflation`, `policy_real_rates`,
`term_premium_supply`, `liquidity_funding`, or `credit`. Exactly eight ordered
lanes are published: US equities, long-duration Treasuries, credit, USD, gold,
oil, crypto, and market volatility. The same versioned rules evaluate the
current completed US session and the fifth prior completed session. Each lane
contains direction, trend, categorical confidence, summary, drivers,
contradiction, invalidation, evidence references, and local degradation.
Overview also bounds key changes to three and selects at most the nearest
trustworthy official catalyst plus one nullable core invalidation. Conclusions
contain no global score, percentage confidence, probability, positioning
instruction, holdings analysis, trade output, or LLM result.

## Page-specific contracts

- **Overview**: one shock state, the exact eight-lane decision map, up to three
  five-session changes, nearest official catalyst, core invalidation, and the
  shared audit payload. Catalysts expose official date/time/timezone/source/URL,
  normalized `event_at_ms` only when trustworthy, and `today`/`upcoming`
  status; no consensus, forecast, surprise, fabricated countdown, or event
  score is inferred.
- **Cross-asset**: cutoff-aligned 20/60-session returns, volatility evidence,
  20/60-session correlations using actual common samples, and explicit
  divergences/gaps. Raw levels are never compared as returns.
- **Rates & Inflation**: ordered nominal tenors/slopes, real yields,
  breakevens, true term-premium capability, policy/funding corridor,
  release-aware inflation changes, and separate curve level/move
  classification.
- **Growth & Labor**: leading and lagging growth/labor layers remain separate;
  release growth carries its real sample and formula.
- **Liquidity & Funding**: central-bank balance sheet, Treasury cash,
  reverse-repo, reserves, secured funding, and unsecured funding remain
  separate. `Fed assets - TGA - (RRP × 1000)` is labelled an accounting proxy
  in millions of dollars and never a causal risk-asset claim.
- **Credit**: aggregate spreads, rating tail, effective yields, credit supply,
  realized damage, and financial-conditions/liquidity layers. It derives
  `CCC OAS - BB OAS`, classifies the 10-year Treasury change × HY spread-change
  quadrant, and keeps stage separate from direction. Stages are `contained`,
  `tail_stress`, `broadening`, `systemic_tightening`, `repairing`, or
  `insufficient_evidence`.

TRACE transactions, ETF premium/discount, dealer inventory, FedWatch,
consensus, economic surprise, and true term-premium data remain named
unavailable capabilities until material source facts exist. They are never
represented by placeholders or proxies.

## Atomic current snapshot

`macro_view_snapshots` has exactly one supported identity:
`snapshot_key = 'current'`. The row stores `macro_decision_v2`, shared
watermarks/cutoff/time, six required JSON objects, and one stable payload hash.
All page documents repeat the same four metadata fields; repository validation
rejects a mismatch.

Dirty-target claim, compact-series changes, snapshot upsert, publication state,
and exact claim acknowledgement share the projection transaction. A clock
recheck has no synthetic queue row: it reads only persisted compact rows and
upserts through the same single-writer repository transaction. The snapshot
hash excludes computation clocks recursively. Replaying an unchanged semantic
payload therefore writes zero serving rows, while a real age, cutoff, or
freshness change replaces the same current identity.

## Public surfaces

The only Macro HTTP reads are:

```text
/api/macro/overview
/api/macro/cross-asset
/api/macro/rates-inflation
/api/macro/growth-labor
/api/macro/liquidity-funding
/api/macro/credit
/api/macro/series
```

Each page endpoint selects its stored document directly. The series endpoint
reads compact persisted rows independently. No request path scans wide
observations, builds a page, invokes a worker/provider, joins News, or creates
an intraday judgment. Unmatched Macro paths return the ordinary application
`404`.

## Runtime configuration

Live execution uses operator-owned `~/.parallax/config.yaml` and
`~/.parallax/workers.yaml`; `uv run parallax config` is the resolved-path
authority. `workers.macro_sync` owns bundle names, provider timeout, window,
claim lease, retry cadence, and batch size. `workers.macro_view_projection`
owns statement timeout, dirty-target batch/lease/retry policy, lookback, and
per-series cap. Credentials are reported only as redacted configured state.
