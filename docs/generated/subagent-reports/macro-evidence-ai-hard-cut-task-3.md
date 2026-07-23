# Subagent Report - 2026-07-23-macro-evidence-ai-hard-cut / Task 3

Mode: write-allowed

## Findings

- The legacy generic Macro score/regime/scenario/module chain was hard-deleted. The replacement entry point is `build_macro_evidence_snapshot(observations, computed_at_ms=...)` in `src/parallax/domains/macro_intel/services/macro_evidence_snapshot.py`; it reads persisted observation rows only and performs no provider, repository, runtime, configuration, or model call.
- The snapshot has exact top-level keys `projection_version`, `fact_watermark`, `market_cutoff`, `computed_at_ms`, `overview`, `cross_asset`, `rates_inflation`, `growth_labor`, `liquidity_funding`, and `credit`. Every page contains `page_id`, the shared `snapshot`, `conclusion`, `horizon`, `drivers`, `confirmations`, `contradictions`, `upgrade_invalidation`, `evidence_refs`, `freshness`, `evidence`, and `unavailable_evidence`, followed only by its typed domain sections. The six documents are therefore one atomic evidence contract rather than generic module dictionaries.
- `macro_concept_manifest.py` is the single immutable concept ownership table. Its 108 projection concepts are provider-backed and carry page, section, evidence role, output unit, source unit, frequency, freshness, legal change window, criticality, and claim effect. Daily, weekly, monthly, quarterly, irregular, and event concepts do not share observation offsets. The current upstream calendar contract was checked against `macrodata-cli`: official calendar observations use `days_until`; the historical `days` fixture is rejected instead of normalized through a compatibility path.
- Evidence construction now validates source/series/unit/frequency/data-quality metadata before any rule may consume a value. Critical missing, invalid, stale, or legally insufficient history fails the affected claim closed; optional manifest gaps degrade it. Named unavailable capabilities such as TRACE, ETF premium/discount, dealer inventory, FedWatch, consensus, surprise, and true Treasury term premium are emitted as `not_assessed` with no value and no implicit readiness impact.
- Cross-asset rules use the latest completed market cutoff, require exact 20/60-session endpoints, and calculate correlations only on common dated return intervals with actual sample start/end/count. Risk-on/risk-off is a cross-domain confirmation, never a dominant-shock family.
- Rates & Inflation separates nominal tenor levels/slopes, real yields, breakevens, funding corridor, release-aware inflation, and unavailable true term premium. Curve level (`inverted`, `upward_sloping`, `flat`, or `mixed`) is separate from the aligned 2Y/10Y move (`bull_steepener`, `bear_steepener`, `bull_flattener`, `bear_flattener`, or `mixed`); missing legal-window changes remain `insufficient_evidence`.
- Growth & Labor preserves leading/lagging and release-aware metrics. Liquidity & Funding preserves balance-sheet, treasury-cash, reverse-repo, reserves, secured-funding, and unsecured-funding layers. Its `net_liquidity` evidence is explicitly a non-causal accounting proxy: Fed assets minus TGA minus RRP after conversion to `millions_usd`, with formula, inputs, references, and actual sample range. It does not drive a risk-asset rule.
- Credit OAS evidence is normalized at the evidence boundary from source percent to `basis_points`, with transparent `source_percent * 100` derivation; effective yields remain percent. Credit exposes explicit derived `CCC OAS - BB OAS` basis-point evidence, keeps stage and direction separate, and uses `widening`/`narrowing` without a tightening alias. The golden current-state matrix IG 78bp / HY 269bp / BB 158bp / B 286bp / CCC 978bp / NFCI -0.55 produces CCC-BB 820bp, `tail_stress`, and `narrowing`, while aggregate broadening and systemic tightening remain separate rules.
- Dominant shock is restricted to families `growth`, `inflation`, `policy_real_rates`, `term_premium_supply`, `liquidity_funding`, and `credit`, and statuses `confirmed`, `provisional`, `divergent`, and `insufficient_evidence`. No data-backed term-premium trigger exists, so it is never guessed. Future catalyst-only observations and future material dates do not advance the material fact watermark.
- Official catalysts are limited to today through the next seven days and require valid observation metadata, official time, explicit timezone, and source URL. `event_time_et` maps to `America/New_York`; a generic event time without an explicit timezone is a named gap rather than `source_reported`.
- Macro series points now have exact keys `observed_at`, `value`, `source_name`, `series_key`, `unit`, `frequency`, `data_quality`, and `event_metadata`. `event_metadata_json` is projected through a strict twelve-field whitelist; forecast, score, and other undeclared keys are discarded without compatibility fields.
- A read-only child audit found eight concrete defects during implementation: metadata/status bypass, critical-history non-closure, cutoff/common-interval misalignment, unavailable-capability degradation, an incorrect SPY direction contradiction, partial 10/30 windows labelled as 20/60, stale calendar-unit assumptions, and silently dropped catalyst metadata gaps. Each was repaired and locked by the evidence, cross-asset, manifest, and snapshot tests. Parent contract review then found and drove the exact dominant-shock enums, material-only watermark, `not_assessed` isolation, explicit catalyst timezone, OAS unit conversion and CCC-BB evidence, dynamic curve move, transparent liquidity proxy, current-state tail rule, and strict series-point shape.

## Scope Adherence

Owned scope: pass

Conflict set: pass

Implementation changes are confined to the Task 3 touch set: Macro services/constants and Macro domain unit tests. No Task 3 write was made to runtime, repositories, API, migrations, frontend, or operator configuration. The report itself is the handoff-required generated evidence artifact.

The shared worktree also contains parent-owned Task 4/5 edits under Macro unit tests, including projection worker/generation/partition/repository-currentness coverage. Those concurrent edits were exercised by the exact Task 3 gate but are not claimed as Task 3 authorship.

## Changed Files

- `src/parallax/domains/macro_intel/_constants.py`
- `src/parallax/domains/macro_intel/services/**`
- `tests/unit/domains/macro_intel/**`

New production units are the concept manifest, evidence builder, six-document snapshot builder, dominant-shock rules, and pure cross-asset, rates/inflation, growth/liquidity, and credit rule modules. `macro_series_view.py`, `macrodata_bundle_importer.py`, and the service package marker were hard-cut to the new projection/series contract. Legacy asset-correlation, assets-brief, feature, gap-payload, module catalog/view/builders, regime, and scenario units were deleted.

New tests cover the manifest, evidence metadata/freshness, snapshot contract, cross-asset alignment, rates/inflation, growth/liquidity, and Credit. Retired private-module tests were deleted; migration-constant, series-view, and importer contract tests were updated. Parent-owned concurrent projection/currentness test changes are excluded from the Task 3 authorship claim above.

## Required Reading Evidence

Task classification: Domain implementation; Read Model Change Review; deterministic Macro evidence-rule replacement.

- `AGENTS.md`: PostgreSQL material-fact truth, rebuildable single-writer read models, stable identity, unchanged zero-write, hard-cut, and operator-config boundaries.
- `docs/agent-playbook/task-reading-matrix.md`: domain implementation, read-model, worker, and handoff reading/verification matrix.
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`: owning Macro fact, series, dirty-target, projection, and consumer boundaries.
- `docs/ARCHITECTURE.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, and `docs/WORKER_FLOW.md`: Kappa/CQRS ownership, process-versus-claim readiness, one-writer recovery, and bounded catch-up invariants.
- `docs/agent-playbook/read-model-change-checklist.md`: stable product keys, material-fact inputs, idempotency, one writer, and non-empty-state review boundary.
- Existing `src/parallax/domains/macro_intel/services/**` modules were read end to end before replacement to inventory the generic score/regime/scenario/module behavior and all consumers that needed a hard delete.
- Current compact observation shapes were traced through `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, importer tests, provider mappings, and the sibling current `macrodata-cli` calendar catalog/provider contract. Repository/runtime files were read only for Task 3.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`, `plan.md`, and `tasks.md`: approved six-page skeletons, evidence metadata, dominant-shock/Credit models, unavailable-evidence semantics, AC4-AC10/AC15, hard-delete list, and exact Task 3 gate.

## Verification Evidence

Fresh exact Task 3 gate after all final source/test edits:

```text
$ uv run pytest tests/unit/domains/macro_intel -q
........................................................................ [ 35%]
........................................................................ [ 70%]
...........................................................              [100%]
203 passed in 0.32s
exit code: 0
```

Owned-scope static gate:

```text
$ uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services tests/unit/domains/macro_intel
All checks passed!
exit code: 0
```

Python compilation and whitespace checks:

```text
$ uv run python -m compileall -q src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services tests/unit/domains/macro_intel
exit code: 0

$ git diff --check -- src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services tests/unit/domains/macro_intel
exit code: 0
```

Additional final evidence: all six strict API page schemas validated both an empty snapshot and a non-empty OAS/CCC-BB/net-liquidity snapshot; the current-service/current-domain-test legacy-module scan passed; the forbidden score/probability/confidence/trade/allocation/position/leverage scan passed; and all 108 manifest concepts were verified provider-backed with zero unmapped projection concepts. Each command exited 0.

## Remaining Risks

- Task 3 does not own the atomic PostgreSQL writer, repository SQL, irreversible migration, typed routes, frontend, or generated contracts. Parent acceptance must still pass non-empty migration/replay, zero-write unchanged projection, API/OpenAPI, frontend, Docker/runtime, and full repository gates after all parallel tasks merge.
- True Treasury term premium, TRACE transactions, ETF premium/discount, dealer inventory, FedWatch, consensus, and surprise evidence remain deliberately unavailable. Adding any of them requires a new source/fact contract and rule review; this implementation does not proxy them.
- The liquidity accounting proxy combines latest available weekly/daily source observations after unit conversion. Its source-date range is exposed and it is context only; point-in-time vintage alignment or causal research would require a separate approved specification.
- Deterministic thresholds are transparent rule contracts, not backtested probabilities. Any threshold revision or new dominant-shock family trigger should be versioned and independently evaluated rather than made configurable at runtime.
