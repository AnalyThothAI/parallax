# Plan — Token 匹配与价格同步 KISS 修复

**Status**: Draft
**Date**: 2026-05-09
**Owning spec**: `docs/superpowers/specs/2026-05-09-token-extraction-pipeline-audit.md`
**Worktree**: `.worktrees/token-extraction-kiss-spec/`
**Branch**: `codex/token-extraction-kiss-spec`

## Pre-flight

- [x] Spec is approved directionally by user feedback: source-of-truth root cause is unbounded DEX symbol candidate admission.
- [x] Worktree exists at `.worktrees/token-extraction-kiss-spec/` and `git branch --show-current` is `codex/token-extraction-kiss-spec`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes.

Known-failing baseline tests:

- None expected.

## Lifecycle

This change removes the old "write every exact-symbol OKX result forever" lifecycle. The only lifecycle after this plan is:

```mermaid
stateDiagram-v2
  [*] --> SearchResult: OKX DEX symbol search row
  SearchResult --> RejectedSearch: wrong symbol or outside top 3 for chain
  SearchResult --> RetainedCandidate: exact symbol and top 3 for chain
  RejectedSearch --> [*]: not persisted
  RetainedCandidate --> ActiveAsset: write registry_assets.status=candidate
  ActiveAsset --> ResolvedTarget: resolver selects as target
  ActiveAsset --> DemotedSearch: later symbol lookup excludes it and no current resolution protects it
  DemotedSearch --> ActiveAsset: later top 3 lookup or explicit CA/payload mention reactivates it
  ResolvedTarget --> ActiveAsset: remains resolver/refresh eligible while current
```

State semantics:

| State | Storage | Resolver eligible | Price refresh eligible | Owner |
|-------|---------|-------------------|------------------------|-------|
| `RejectedSearch` | Not stored | No | No | `TokenDiscoveryWorker` |
| `RetainedCandidate` | transient before write | Not directly | Not directly | `TokenDiscoveryWorker` |
| `ActiveAsset` | `registry_assets.status IN ('candidate', 'canonical')` | Yes | Yes | `RegistryRepository` |
| `DemotedSearch` | `registry_assets.status = 'demoted_search'` | No | No | `RegistryRepository` |
| `ResolvedTarget` | current `token_intent_resolutions.target_id` | Yes | Yes | resolver/reprojection |

No compatibility state is kept. Existing search-only rows that do not survive the new lifecycle are demoted once by migration and then maintained by the symbol discovery path.

Resolver state machine after this change:

```mermaid
stateDiagram-v2
  [*] --> SymbolIntent
  SymbolIntent --> CexResolved: confirmed CEX token exists
  SymbolIntent --> NoDexCandidate: no active retained DEX candidates
  SymbolIntent --> SingleDexCandidate: one active retained DEX candidate
  SymbolIntent --> DominantDexCandidate: multiple active retained candidates and one dominates
  SymbolIntent --> AmbiguousDexCandidate: multiple active retained candidates without dominance
  CexResolved --> UNIQUE_BY_CONTEXT
  SingleDexCandidate --> UNIQUE_BY_CONTEXT
  DominantDexCandidate --> UNIQUE_BY_CONTEXT
  AmbiguousDexCandidate --> AMBIGUOUS
  NoDexCandidate --> NIL
```

`SYMBOL_CANDIDATES_STALE` is removed from the symbol identity path. Price freshness is not a resolver state; it belongs to price payloads and downstream market health.

## File-level edits

### `src/parallax/pipeline/token_discovery_worker.py`

- Lines 25-30: add candidate admission constants:
  - `DEX_SYMBOL_CANDIDATES_PER_CHAIN = 3`
  - `DEX_SYMBOL_QUALITY_VERSION = "dex_symbol_quality_v1"`
- Lines 222-250: replace the unbounded `_process_dex_symbol_lookup` write loop with a bounded lifecycle:
  - New flow:
    1. call `dex_client.search_tokens(query=symbol, chain_indexes=chain_indexes)`
    2. normalize and exact-match `candidate.symbol`
    3. group by `_chain_id_from_okx_index(candidate.chain_index)`
    4. sort each group by `_dex_symbol_candidate_sort_key(candidate, provider_index)`
    5. retain top `DEX_SYMBOL_CANDIDATES_PER_CHAIN`
    6. write only retained candidates with `_write_dex_candidate`
    7. call `repos.registry.demote_unretained_symbol_assets(symbol=symbol, retained_asset_ids=..., now_ms=now_ms, commit=False)`
    8. commit through the existing outer lookup transaction
  - New helper signatures:
    ```python
    def _retained_symbol_candidates(
        candidates: list[Any],
        *,
        symbol: str,
        per_chain_limit: int = DEX_SYMBOL_CANDIDATES_PER_CHAIN,
    ) -> list[Any]: ...

    def _dex_symbol_candidate_sort_key(item: tuple[int, Any]) -> tuple[Any, ...]: ...

    def _dex_symbol_quality(candidate: Any) -> Decimal: ...
    ```
  - `result["search_hits"]` becomes the retained count, not raw provider exact-symbol count.
  - Add `result["search_candidates_seen"]` and `result["search_candidates_rejected"]` to the internal result dict so ops can audit the new gate.
- Lines 253-293: keep address lookup uncapped. Address lookup continues writing exact chain+address matches because address is identity, not weak symbol evidence.
- Lines 296-338: keep `_write_dex_candidate` as the single active-asset writer, but rely on `RegistryRepository.upsert_chain_asset` to reactivate `demoted_search` rows.
- Lines 372-385: extend `_lookup_result` with:
  ```python
  "search_candidates_seen": 0,
  "search_candidates_rejected": 0,
  ```
- Lines 341-349: extend `_merge_lookup_result` to add the two new counters.

### `src/parallax/storage/registry_repository.py`

- Lines 7-10: add status/source constants:
  ```python
  ACTIVE_REGISTRY_ASSET_STATUSES = ("candidate", "canonical")
  DEMOTED_SEARCH_STATUS = "demoted_search"
  EXPLICIT_ASSET_SOURCES = {"tweet_ca", "gmgn_payload"}
  SEARCH_ASSET_SOURCE = "okx_dex_search"
  ```
- Lines 42-92: update `upsert_chain_asset` so every explicit write reactivates an asset:
  - Insert status remains `candidate`.
  - On conflict:
    - `status = 'candidate'`
    - `primary_source` uses source precedence: explicit sources beat `okx_dex_search`; search may update search-owned rows but may not downgrade explicit CA/payload source.
    - `evidence_level` remains `price_observation`.
  - Add private helper:
    ```python
    def _source_precedence(source: str | None) -> int: ...
    ```
- Lines 181-224: keep resolver reads constrained to `status IN ('candidate', 'canonical')`; after the migration this automatically excludes `demoted_search`.
- Lines 268-298: keep method name `chain_assets_needing_price_refresh`, but it now only scans active assets:
  - `registry_assets.status IN ('candidate', 'canonical')`
  - no special backward-compatible inclusion for old search rows
  - ordering remains oldest observation first after the active set is bounded
- After line 298: add one repository method for lifecycle maintenance:
  ```python
  def demote_unretained_symbol_assets(
      self,
      *,
      symbol: str,
      retained_asset_ids: list[str],
      now_ms: int,
      commit: bool = True,
  ) -> int: ...
  ```
  Exact SQL:
  ```sql
  WITH protected_assets AS (
    SELECT DISTINCT target_id AS asset_id
    FROM token_intent_resolutions
    WHERE is_current = true
      AND target_type = 'Asset'
      AND target_id IS NOT NULL
    UNION
    SELECT DISTINCT jsonb_array_elements_text(candidate_ids_json) AS asset_id
    FROM token_intent_resolutions
    WHERE is_current = true
  )
  UPDATE registry_assets
  SET status = 'demoted_search',
      updated_at_ms = %s
  WHERE symbol = %s
    AND primary_source = 'okx_dex_search'
    AND status IN ('candidate', 'canonical')
    AND asset_id <> ALL(%s::text[])
    AND NOT EXISTS (
      SELECT 1
      FROM protected_assets
      WHERE protected_assets.asset_id = registry_assets.asset_id
    );
  ```
  Return affected row count.

### `src/parallax/pipeline/deterministic_token_resolver.py`

- Lines 248-304: replace symbol identity filtering so active retained candidates are the identity set:
  - Delete `active_assets = [row for row in assets if _fresh(...)]`.
  - Use `assets` directly after repository status filtering.
  - `candidate_ids = _candidate_ids(assets)`.
  - If `len(assets) == 1`, return `UNIQUE_BY_CONTEXT / SINGLE_ACTIVE_CHAIN_ASSET`.
  - Run `_market_dominant_asset(assets)` on all active retained candidates, regardless of observation age.
  - If `candidate_ids` remains non-empty but no dominance, return `AMBIGUOUS / NO_MARKET_DOMINANT_CHAIN_ASSET`.
  - If no assets, return `NIL / SYMBOL_NOT_IN_REGISTRY`.
  - Remove the `SYMBOL_CANDIDATES_STALE` branch from the symbol path.
- Lines 376-379: remove `_fresh` if no remaining call sites exist.

### `src/parallax/storage/alembic/versions/20260509_0017_demote_search_only_registry_assets.py`

- New Alembic revision:
  ```python
  revision = "20260509_0017"
  down_revision = "20260509_0016"
  ```
- Migration has no new table and no new column. It applies the new lifecycle to existing data.
- Upgrade SQL:
  ```sql
  WITH protected_assets AS (
    SELECT DISTINCT target_id AS asset_id
    FROM token_intent_resolutions
    WHERE is_current = true
      AND target_type = 'Asset'
      AND target_id IS NOT NULL
    UNION
    SELECT DISTINCT jsonb_array_elements_text(candidate_ids_json) AS asset_id
    FROM token_intent_resolutions
    WHERE is_current = true
  ),
  latest_price AS (
    SELECT DISTINCT ON (subject_id)
      subject_id AS asset_id,
      price_usd,
      market_cap_usd,
      liquidity_usd,
      holders,
      observed_at_ms
    FROM price_observations
    WHERE subject_type = 'Asset'
    ORDER BY subject_id, observed_at_ms DESC, observation_id DESC
  ),
  ranked_search_assets AS (
    SELECT
      registry_assets.asset_id,
      row_number() OVER (
        PARTITION BY registry_assets.symbol, registry_assets.chain_id
        ORDER BY
          (
            0.50 * (ln(greatest(coalesce(latest_price.market_cap_usd, 0), 0) + 1) / ln(10)) +
            0.30 * (ln(greatest(coalesce(latest_price.liquidity_usd, 0), 0) + 1) / ln(10)) +
            0.20 * (ln(greatest(coalesce(latest_price.holders, 0), 0) + 1) / ln(10))
          ) DESC,
          CASE WHEN latest_price.price_usd IS NOT NULL THEN 0 ELSE 1 END,
          registry_assets.updated_at_ms DESC,
          registry_assets.asset_id ASC
      ) AS chain_rank
    FROM registry_assets
    LEFT JOIN latest_price ON latest_price.asset_id = registry_assets.asset_id
    WHERE registry_assets.primary_source = 'okx_dex_search'
      AND registry_assets.symbol IS NOT NULL
      AND registry_assets.status IN ('candidate', 'canonical')
  )
  UPDATE registry_assets
  SET status = 'demoted_search',
      updated_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint
  FROM ranked_search_assets
  LEFT JOIN protected_assets ON protected_assets.asset_id = ranked_search_assets.asset_id
  WHERE registry_assets.asset_id = ranked_search_assets.asset_id
    AND ranked_search_assets.chain_rank > 3
    AND protected_assets.asset_id IS NULL;
  ```
- Downgrade SQL:
  ```sql
  UPDATE registry_assets
  SET status = 'candidate',
      updated_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint
  WHERE status = 'demoted_search';
  ```
  This is a mechanical rollback only; production rollback should prefer redeploying the old code plus this downgrade together.

### `tests/test_token_discovery_worker.py`

- Add `test_symbol_lookup_retains_at_most_three_candidates_per_chain`.
  - Fake OKX returns 6 Solana HANTA candidates and 4 BSC HANTA candidates.
  - Assert registry writes 3 Solana + 3 BSC only.
  - Assert discovery result `candidate_count == 6`.
  - Assert rejected candidates have no price observations.
- Add `test_symbol_lookup_quality_orders_by_market_liquidity_and_holders`.
  - Candidates are intentionally provider-ordered badly.
  - Assert retained IDs are quality top 3 per chain.
- Add `test_address_lookup_is_not_capped_by_symbol_candidate_limit`.
  - Address lookup returns exact address match.
  - Assert it writes even if many same-symbol candidates would otherwise be rejected.
- Add `test_symbol_lookup_demotes_unretained_search_assets`.
  - Preload an old `okx_dex_search` active HANTA asset.
  - New lookup retains different IDs.
  - Assert old unprotected asset becomes `demoted_search`.

### `tests/test_registry_repository.py`

- Add `test_upsert_chain_asset_reactivates_demoted_search_asset`.
  - Insert `registry_assets.status='demoted_search'`.
  - Call `upsert_chain_asset(source='okx_dex_search')`.
  - Assert status becomes `candidate`.
- Add `test_explicit_sources_are_not_downgraded_by_okx_search`.
  - Insert `tweet_ca` asset.
  - Call `upsert_chain_asset(source='okx_dex_search')`.
  - Assert `primary_source` remains `tweet_ca`.
- Add `test_demote_unretained_symbol_assets_protects_current_targets_and_candidates`.
  - Create search assets for same symbol.
  - Create current resolution target/candidate references.
  - Call `demote_unretained_symbol_assets`.
  - Assert protected rows remain active; unretained unprotected rows become `demoted_search`.
- Add `test_symbol_and_refresh_queries_ignore_demoted_search_assets`.
  - Demoted asset with high market cap must not appear in `find_assets_by_symbol_with_latest_observation`.
  - Demoted stale asset must not appear in `chain_assets_needing_price_refresh`.

### `tests/test_deterministic_token_resolver.py`

- Add `test_symbol_resolution_ignores_demoted_search_assets`.
  - Fake registry returns only active candidates, mirroring repository behavior.
  - Assert resolver picks active retained candidate and does not see demoted historical candidates.
- Add `test_cex_symbol_still_wins_over_retained_dex_candidates`.
  - Preserve existing CEX-first behavior with a DEX candidate present.
- Add `test_stale_single_retained_candidate_still_resolves_identity`.
  - Candidate observation is older than the former 20-minute freshness window.
  - Assert resolver returns `UNIQUE_BY_CONTEXT / SINGLE_ACTIVE_CHAIN_ASSET`, not `NIL / SYMBOL_CANDIDATES_STALE`.
- Update or remove tests that assert `SYMBOL_CANDIDATES_STALE`; that reason is no longer emitted by the new lifecycle.

### `tests/test_postgres_schema.py`

- Add migration text guard:
  - File `20260509_0017_demote_search_only_registry_assets.py` exists.
  - Contains `status = 'demoted_search'`.
  - Contains `row_number() OVER`.
  - Contains `PARTITION BY registry_assets.symbol, registry_assets.chain_id`.

## PR breakdown

1. **PR 1 — DEX Candidate Admission**: edits `token_discovery_worker.py`, `registry_repository.py`, adds repository and worker tests. Mergeable on its own with new candidate cap for future lookups.
2. **PR 2 — Existing Registry Demotion**: adds Alembic migration and schema tests. Depends on PR 1 because demoted rows must already be ignored/reactivatable by code.
3. **PR 3 — Verification Artefact**: adds `docs/superpowers/plans/2026-05-09-token-extraction-kiss/verification.md` after running full checks and production-read audit queries.

## Rollout order

1. Land PR 1 code so future symbol discovery writes only retained candidates and all reads ignore `demoted_search`.
2. Apply migration `20260509_0017` with `uv run parallax db migrate`.
3. Run one token discovery pass for high-collision symbols through existing ops path:
   `uv run parallax ops run-token-discovery --limit 50`
4. Reprocess recent token intents:
   `uv run parallax ops reprocess-token-intents --limit 500`
5. Rebuild token radar:
   `uv run parallax ops rebuild-token-radar --window 24h --scope all`
6. Run verification queries against HANTA/UAP/VIRUS to confirm active candidates are bounded and demoted rows are excluded.

## Rollback

1. Revert code to previous branch state.
2. Run Alembic downgrade from `20260509_0017` to `20260509_0016` only if old code is redeployed; old code does not understand `demoted_search` as active and would keep excluding those rows.
3. Re-run `uv run parallax ops run-token-discovery --limit 50` to repopulate discovery results under the old unbounded behavior if rollback is intentional.
4. Rebuild radar after rollback with `uv run parallax ops rebuild-token-radar --window 24h --scope all`.

Not safely reversible: rejected future search rows are never persisted. This is intentional; if a rejected asset later matters, explicit CA/address or a future top-3 symbol search will reintroduce it.

## Acceptance test commands

- AC1 / AC2 / AC3:
  `uv run pytest tests/test_token_discovery_worker.py::test_symbol_lookup_retains_at_most_three_candidates_per_chain`
- AC3:
  `uv run pytest tests/test_token_discovery_worker.py::test_symbol_lookup_quality_orders_by_market_liquidity_and_holders`
- AC4:
  `uv run pytest tests/test_token_discovery_worker.py::test_address_lookup_is_not_capped_by_symbol_candidate_limit`
- AC5:
  `uv run pytest tests/test_deterministic_token_resolver.py::test_cex_symbol_still_wins_over_retained_dex_candidates`
- AC6:
  `uv run pytest tests/test_registry_repository.py::test_symbol_and_refresh_queries_ignore_demoted_search_assets`
- AC7:
  `uv run parallax db migrate` then:
  ```sql
  SELECT symbol, chain_id, COUNT(*) AS active_count
  FROM registry_assets
  WHERE symbol IN ('HANTA', 'UAP', 'VIRUS')
    AND status IN ('candidate', 'canonical')
    AND primary_source = 'okx_dex_search'
  GROUP BY symbol, chain_id
  HAVING COUNT(*) > 3;
  ```
  Expected: zero rows.
- AC8:
  `uv run pytest tests/test_deterministic_token_resolver.py::test_stale_single_retained_candidate_still_resolves_identity`
- AC9:
  `uv run pytest tests/test_entity_extractor.py tests/test_token_evidence_builder.py tests/test_token_intent_builder.py`
- Full gate:
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run python -m compileall src tests`

## Verification

Implementation verification was run in the isolated worktree on 2026-05-09.

Commands:

- `uv run ruff check .` -> passed.
- `uv run pytest` -> passed: 334 passed, 132 skipped. The skipped tests are PostgreSQL-backed tests under the default local DSN.
- `uv run python -m compileall src tests` -> passed.
- `GMGN_TEST_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:56432/parallax_test uv run pytest tests/test_registry_repository.py tests/test_token_discovery_worker.py tests/test_deterministic_token_resolver.py tests/test_token_intent_resolver.py tests/test_postgres_schema.py` -> passed: 38 passed.

Diff summary:

- Token extraction files were not changed.
- `token_discovery_worker.py` now admits at most three exact-symbol OKX DEX search candidates per chain, sorted by market cap, liquidity, and holders.
- `registry_repository.py` now treats `demoted_search` as inactive, preserves stronger explicit sources over `okx_dex_search`, and exposes demotion for unretained search-only assets.
- `deterministic_token_resolver.py` no longer emits `SYMBOL_CANDIDATES_STALE`; retained identity candidates resolve regardless of price-observation freshness.
- Migration `20260509_0017_demote_search_only_registry_assets.py` demotes historical unprotected search-only tail rows without adding tables or columns.

Live HANTA/UAP/VIRUS post-migration counts were not run from this implementation worktree. The code path is covered by repository and worker integration tests against a disposable PostgreSQL container.
