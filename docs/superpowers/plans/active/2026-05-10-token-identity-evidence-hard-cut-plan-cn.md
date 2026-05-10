# Token Identity Evidence Hard Cut Implementation Plan

**Status**: Implemented in `codex/token-identity-freshness-hard-cut`; verification passed
**Date**: 2026-05-10  
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-token-identity-evidence-hard-cut-spec-cn.md`  
**Branch**: `codex/token-identity-freshness-hard-cut`
**Core rule**: hard cut only. No dual write, no runtime compatibility shim, no frontend correction map.

## Intent

Replace token identity selection based on `registry_assets.symbol/name/primary_source` with an explicit identity evidence ledger plus one deterministic current-identity policy. The implementation must make every Token Radar row explainable from stored evidence and must delete the runtime source-precedence model that caused SHIT/SLOP/SATO identity drift.

## Implementation Note

Implemented against the current domain layout, not the older `storage/` / `pipeline/` paths used in early planning text.

- Policy: `src/gmgn_twitter_intel/domains/asset_market/identity_evidence_policy.py`
- Repository: `src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py`
- Migration: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py`
- Verification artifact: `docs/superpowers/plans/active/2026-05-10-token-identity-evidence-hard-cut-verification.md`

Final verification:

- `uv run pytest -q` -> 416 passed, 141 skipped.
- `uv run ruff check src tests` -> passed.
- `npm test -- --run` -> 15 files passed, 86 tests passed.
- `npm run build` -> passed.
- Runtime deletion grep for old source precedence, old registry identity reads, and projection preflight hydration -> no hits outside historical migrations.
- Real local production DB SHIT/SLOP/SATO samples were rerun in a transaction dry-run of migration `20260510_0021`: schema/backfill, `TokenRadarSourceQuery`, sample projection grouping, `token_radar_rows` repository write/read, public read-model output, and price freshness checks all executed against real data, then rolled back without mutating the DB.

Task status summary:

- Tasks 3-9 are implemented on the current code layout.
- Task 10's required frontend hard-cut behavior is implemented: resolved targets no longer fall back to mention symbols.
- The early plan's speculative batch helpers (`recompute_current_identity_many`, `current_identities`, `assets_needing_identity_verification`) were not added because runtime call sites did not need them; the landed implementation keeps the repository API smaller and verifies the production path directly.
- Local production DB sample queries were rerun safely in this worktree; see the verification artifact for exact mismatch samples, projected rows, price freshness, and rollback confirmation.

## Scope

### In

- Add `asset_identity_evidence` and `asset_identity_current`.
- Move canonical asset display identity out of `registry_assets`.
- Implement one `IdentityEvidencePolicy`.
- Rewrite ingest/discovery/market sync to write evidence and recompute current identity.
- Rewrite projection/API/frontend to consume current identity and show mention symbol only as mention context.
- Add migration/backfill/reverify/rebuild commands.
- Add golden SHIT/SLOP/SATO regression coverage.
- Delete old runtime source precedence and old identity fallback behavior.

### Out

- No ML/LLM identity resolver.
- No chain risk engine.
- No token-specific correction tables.
- No compatibility API version for old token radar identity fields.
- No permanent adapter that maps old `primary_source` to new evidence kinds at runtime.

## Pre-flight

- [ ] Create a short-lived branch if not working directly on `main`.
- [ ] Confirm current DB migration head is `20260509_0020_sweep_symbol_search_tail_assets.py`.
- [ ] Record baseline commands:
  - `uv run pytest -q`
  - `uv run ruff check src tests`
  - `uv run python -m compileall src tests`
  - `npm test -- --run`
  - `npm run build`
- [ ] Snapshot current problem rows from local Postgres:
  - `0x999b49c0d1612e619a4a4f6280733184da025108`
  - `0xaf1e52927d724fd34773bd53ada57f4c2b742069`
  - `0x829f4b62eebe12af653b4dd4ffc480966f7d7f09`
  - `ShitJuMfPKCQU7LedLERFYapDta7CCdKExPWX2gETRH`
- [ ] Add failing tests first for the new model before editing runtime writers.

## File Structure

### New files

- `src/gmgn_twitter_intel/pipeline/asset_identity_policy.py`
  - owns evidence enums, confidence enums, selection order, reason-code generation.
- `src/gmgn_twitter_intel/storage/asset_identity_repository.py`
  - writes evidence, recomputes current identity, reads current identity by asset id/list.
- `src/gmgn_twitter_intel/storage/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py`
  - creates evidence/current tables, performs one-time old-source conversion, backfills current identity.
- `docs/generated/token_identity_golden.json`
  - golden corpus for SHIT/SLOP/SATO and Solana SHIT.

### Files to modify

- `src/gmgn_twitter_intel/storage/registry_repository.py`
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_rebuild.py`
- `src/gmgn_twitter_intel/pipeline/token_discovery_worker.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- `src/gmgn_twitter_intel/storage/token_target_repository.py`
- `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
- `src/gmgn_twitter_intel/api/http.py` or the current token-radar route owner
- `src/gmgn_twitter_intel/cli.py`
- `web/src/api/types.ts`
- `web/src/lib/tokenRadar.ts`
- `web/src/components/TokenTargetPage.tsx`
- Token radar / registry / market sync / frontend tests.

## Architecture Rules For Implementation

- `registry_assets` stores address identity only: chain, token standard, address, status, timestamps.
- `asset_identity_evidence` stores provider/user identity claims.
- `asset_identity_current` stores selected canonical display identity.
- Only `IdentityEvidencePolicy` can decide canonical `symbol/name/decimals`.
- Repositories may write evidence and current rows, but must not embed source precedence logic.
- Projection reads current identity and mention context separately.
- Frontend renders target identity from API and never fixes it locally.
- Migration may read old `primary_source`; runtime must not.

## Task 1: Add Golden Corpus And Policy Tests First

**Files**

- Add `docs/generated/token_identity_golden.json`
- Add `tests/test_asset_identity_policy.py`
- Add `tests/golden/test_token_identity_evidence_corpus.py`

**Steps**

- [ ] Add golden cases:
  - `0x999b...`: tweet may mention SATO/SLOP, exact identity is SLOP.
  - `0xaf1e...`: exact identity is SHIT / Dogeshit.
  - `0x829f...`: exact identity is SATO / sato.
  - `ShitJu...`: Solana SHIT is distinct from EVM SHIT.
- [ ] Add failing unit tests for policy order:
  - manual repair wins and records manual reason.
  - GMGN openapi exact wins over GMGN payload exact.
  - GMGN exact wins over OKX exact.
  - OKX exact address wins over tweet mention.
  - OKX symbol candidate cannot win over any exact evidence.
  - tweet mention cannot set canonical symbol when provider evidence exists.
  - newest evidence wins only inside the same evidence kind.
  - conflict evidence increments `conflict_count`.
  - `MENTION_NOT_CANONICAL` is emitted when mention symbol differs from selected symbol.
- [ ] Run focused tests and confirm they fail because policy does not exist yet:
  - `uv run pytest tests/test_asset_identity_policy.py -q`
  - `uv run pytest tests/golden/test_token_identity_evidence_corpus.py -q`

**Acceptance**

- Tests define expected behavior without depending on old `primary_source`.
- Golden cases include target id, mention symbol, selected evidence kind, selected canonical symbol/name, and expected reason codes.

## Task 2: Add Evidence Policy Module

**Files**

- Add `src/gmgn_twitter_intel/pipeline/asset_identity_policy.py`
- Update tests from Task 1.

**Steps**

- [ ] Define string constants in one place:
  - evidence kinds:
    - `manual_identity_repair`
    - `gmgn_openapi_exact`
    - `gmgn_payload_exact`
    - `okx_dex_exact_address`
    - `okx_dex_symbol_candidate`
    - `okx_cex_instrument`
    - `tweet_contract_mention`
  - lookup modes:
    - `exact_address`
    - `provider_payload`
    - `cex_universe`
    - `symbol_search`
    - `tweet_mention`
    - `manual_repair`
  - confidence values:
    - `manual`
    - `provider_exact`
    - `provider_candidate`
    - `mention_only`
    - `unknown`
- [ ] Implement `select_current_identity(asset_id, evidence_rows, now_ms)`.
- [ ] Keep the policy simple:
  - fixed ordered evidence kinds.
  - no weights.
  - no provider-specific custom scoring.
  - newest wins only within same evidence kind.
- [ ] Return a plain dict compatible with repository insert:
  - `asset_id`
  - `canonical_symbol`
  - `canonical_name`
  - `decimals`
  - `identity_confidence`
  - `selected_evidence_id`
  - `selection_reason_codes`
  - `conflict_count`
  - `verified_at_ms`
  - `updated_at_ms`
- [ ] Run:
  - `uv run pytest tests/test_asset_identity_policy.py -q`

**Acceptance**

- All policy tests pass.
- There is no import from storage or API into policy.
- Policy has no SQL and no provider client calls.

## Task 3: Add Schema Migration And Repository

**Files**

- Add `src/gmgn_twitter_intel/storage/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py`
- Add `src/gmgn_twitter_intel/storage/asset_identity_repository.py`
- Modify `tests/test_postgres_schema.py`
- Add `tests/test_asset_identity_repository.py`

**Steps**

- [ ] Add `asset_identity_evidence`.
- [ ] Add `asset_identity_current`.
- [ ] Add indexes:
  - evidence by `asset_id`.
  - evidence by `evidence_kind`.
  - evidence by `provider, lookup_mode`.
  - current by `identity_confidence`.
  - current by `canonical_symbol`.
- [ ] Implement deterministic `evidence_id` helper:
  - `sha256(asset_id + evidence_kind + provider + lookup_mode + payload_hash)`.
- [ ] Add repository methods:
  - `ensure_asset(chain_id, token_standard, address, observed_at_ms, status="candidate")`
  - `upsert_identity_evidence(...)`
  - `list_identity_evidence(asset_id)`
  - `recompute_current_identity(asset_id, now_ms)`
  - `recompute_current_identity_many(asset_ids, now_ms)`
  - `current_identity(asset_id)`
  - `current_identities(asset_ids)`
  - `assets_needing_identity_verification(limit, confidence_values, stale_before_ms=None)`
- [ ] Migration converts old rows into evidence once:
  - `gmgn_openapi` -> `gmgn_openapi_exact`
  - `gmgn_payload` / `gmgn_token_payload` -> `gmgn_payload_exact`
  - `okx_dex_address_search` -> `okx_dex_exact_address`
  - `okx_dex_search` -> `okx_dex_symbol_candidate`
  - `tweet_ca` -> `tweet_contract_mention`
- [ ] Migration computes `asset_identity_current` for all existing assets.
- [ ] Do not remove old columns in the same first migration if it makes deploy risky; instead stop runtime reads/writes immediately and add a final deletion migration in Task 11.
- [ ] Add repository tests:
  - idempotent evidence upsert.
  - changed payload creates new evidence row.
  - recompute selects exact evidence over tweet mention.
  - current identity for unknown evidence is `unknown`.
- [ ] Run:
  - `uv run pytest tests/test_asset_identity_repository.py tests/test_postgres_schema.py -q`

**Acceptance**

- Migration is one-way.
- Old-source mapping exists only in migration code/tests.
- Runtime repository has no old-source compatibility adapter.

## Task 4: Refactor Registry Repository To Address Identity Only

**Files**

- Modify `src/gmgn_twitter_intel/storage/registry_repository.py`
- Modify `tests/test_registry_repository.py`

**Steps**

- [ ] Replace `upsert_chain_asset(... symbol, name, decimals, source ...)` with address-only asset upsert:
  - `chain_id`
  - `address`
  - `token_standard`
  - `project_id`
  - `observed_at_ms`
  - `status`
- [ ] Remove runtime constants:
  - `DEX_SEARCH_SOURCE`
  - `DEX_ADDRESS_SEARCH_SOURCE`
  - `_SOURCE_PRECEDENCE`
  - `_source_precedence`
  - `_source_precedence_sql`
- [ ] Remove SQL that updates `registry_assets.symbol/name/primary_source`.
- [ ] Remove or rewrite demotion helpers that partition by `registry_assets.symbol`.
  - If still needed, move symbol candidate cleanup to evidence/current identity semantics.
- [ ] Rewrite selectors that currently return `registry_assets.symbol` to join `asset_identity_current`.
- [ ] Rewrite tests:
  - stop asserting `primary_source`.
  - assert current identity repository results.
  - assert address identity is stable independent of mention symbol.
- [ ] Run:
  - `uv run pytest tests/test_registry_repository.py tests/test_asset_identity_repository.py -q`

**Acceptance**

- `rg -n "_SOURCE_PRECEDENCE|primary_source|registry_assets\\.symbol|registry_assets\\.name" src/gmgn_twitter_intel/storage/registry_repository.py` returns no runtime hits.
- Registry repository no longer decides canonical identity.

## Task 5: Rewrite Ingest And Token Intent Rebuild Writers

**Files**

- Modify `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify `src/gmgn_twitter_intel/pipeline/token_intent_rebuild.py`
- Modify `tests/test_asset_ingest_flow.py`
- Modify token intent rebuild tests if present.

**Steps**

- [ ] In ingest, when a CA/address appears:
  - call address-only `registry.ensure_asset`.
  - write `tweet_contract_mention` evidence with mention `display_symbol/name/address_hint`.
  - recompute current identity.
- [ ] Ensure tweet mention evidence has confidence `mention_only` unless provider evidence already exists.
- [ ] Ensure ingest never writes canonical `symbol/name` directly to `registry_assets`.
- [ ] In token intent rebuild, mirror ingest behavior:
  - no direct canonical symbol write.
  - rebuild mention evidence only.
  - recompute current identity after evidence write.
- [ ] Update assertions:
  - old: asset `primary_source == tweet_ca`.
  - new: evidence row `evidence_kind == tweet_contract_mention`, current identity confidence is `mention_only` or provider-selected if exact evidence exists.
- [ ] Run:
  - `uv run pytest tests/test_asset_ingest_flow.py tests/test_token_intent_builder.py -q`

**Acceptance**

- Tweet text remains intent context, not canonical identity.
- No ingest path can directly mutate canonical target symbol.

## Task 6: Rewrite Discovery Worker For Evidence Kinds

**Files**

- Modify `src/gmgn_twitter_intel/pipeline/token_discovery_worker.py`
- Modify `tests/test_token_discovery_worker.py`

**Steps**

- [ ] Replace `_write_dex_candidate(... source=...)` with two explicit write paths:
  - `_write_symbol_candidate_evidence(...)`
  - `_write_exact_address_evidence(...)`
- [ ] Symbol lookup:
  - ensure asset.
  - write `okx_dex_symbol_candidate`.
  - recompute current identity.
  - never mark identity `provider_exact`.
- [ ] Address lookup:
  - accept candidate only when chain index and normalized address match exactly.
  - write `okx_dex_exact_address`.
  - recompute current identity.
- [ ] Remove `DEX_SEARCH_SOURCE` / `DEX_ADDRESS_SEARCH_SOURCE` imports.
- [ ] Rewrite demotion logic if still needed:
  - demote stale symbol candidates by evidence/current identity, not by `primary_source`.
  - keep KISS: if not critical, remove demotion until evidence-based candidate retention is needed.
- [ ] Add regression:
  - symbol search for SHIT cannot overwrite exact SLOP identity for `0x999b...`.
  - address search for `0x999b...` corrects tweet mention SATO to current SLOP.
- [ ] Run:
  - `uv run pytest tests/test_token_discovery_worker.py tests/test_asset_identity_policy.py -q`

**Acceptance**

- Discovery writes evidence only.
- Symbol search and exact address lookup have visibly different evidence kinds.

## Task 7: Rewrite Market Sync Identity Verification Trigger

**Files**

- Modify `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Modify `tests/test_asset_market_sync.py`

**Steps**

- [ ] Replace `ADDRESS_VERIFIED_SOURCES` with `identity_confidence` checks from `asset_identity_current`.
- [ ] Candidate assets needing market refresh should carry:
  - asset address identity.
  - current canonical symbol/name.
  - identity confidence.
- [ ] Exact address verification should trigger when confidence is:
  - `mention_only`
  - `provider_candidate`
  - `unknown`
  - stale `provider_exact` if a future freshness policy is explicitly defined.
- [ ] Exact address verification writes `okx_dex_exact_address` evidence and recomputes current identity.
- [ ] Price observations continue to bind to `asset_id`.
- [ ] Keep provider pricefeed semantics separate from identity evidence.
- [ ] Add tests:
  - mention-only asset with complete market fields still triggers exact address search.
  - provider-candidate asset triggers exact address search.
  - provider-exact asset does not search just because market fields are missing.
  - address exact mismatch does not write evidence.
- [ ] Run:
  - `uv run pytest tests/test_asset_market_sync.py -q`

**Acceptance**

- Market freshness does not stand in for identity confidence.
- Sync result counters include identity verification counts clearly:
  - `identity_verification_requests`
  - `identity_verification_hits`
  - `identity_verification_errors`

## Task 8: Rewrite Projection To Consume Current Identity

**Files**

- Modify `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify `src/gmgn_twitter_intel/pipeline/token_radar_contract.py`
- Modify `tests/test_token_radar_projection.py`
- Modify `tests/golden/test_token_radar_corpus.py`

**Steps**

- [ ] Bump projection version to a hard-cut identity evidence version, for example:
  - `token-radar-v8-identity-evidence`
- [ ] Rewrite source SQL:
  - join `asset_identity_current` for asset target symbol/name/identity confidence.
  - stop selecting `registry_assets.symbol AS asset_symbol`.
  - keep `token_intents.display_symbol` as intent context.
- [ ] Projection target contract:
  - `target.symbol = asset_identity_current.canonical_symbol`
  - `target.name = asset_identity_current.canonical_name`
  - `intent.display_symbol = original mention symbol`
  - `identity.confidence = asset_identity_current.identity_confidence`
  - `identity.reason_codes = asset_identity_current.selection_reason_codes`
- [ ] Delete projection fallback where resolved target symbol can fall back to mention symbol.
- [ ] Add projection tests:
  - resolved target SLOP remains SLOP when mention says SATO.
  - mention-only target has identity confidence `mention_only`.
  - unresolved row may display mention symbol, but resolved row may not use mention as target symbol.
  - SHIT/SLOP/SATO golden rows align target/address/price.
- [ ] Run:
  - `uv run pytest tests/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py -q`

**Acceptance**

- `rg -n "registry_assets\\.symbol AS asset_symbol|row\\.get\\(\"display_symbol\"\\).*target|target.*display_symbol" src/gmgn_twitter_intel/pipeline/token_radar_projection.py` shows no resolved-target fallback.
- Radar rows carry identity explainability metadata.

## Task 9: Rewrite Token Target / Message Observation Reads

**Files**

- Modify `src/gmgn_twitter_intel/storage/token_target_repository.py`
- Modify `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
- Modify related tests.

**Steps**

- [ ] Replace any `registry_assets.symbol/name` reads with `asset_identity_current`.
- [ ] Ensure token target timelines display current identity and still preserve intent display symbol separately.
- [ ] Ensure message market observation uses `asset_id` and pricefeed subject id, not symbol, for binding.
- [ ] Add tests:
  - timeline for `0x999b...` title is SLOP even if mention says SATO.
  - message observation does not change identity fields.
- [ ] Run focused tests for target/timeline/message observation.

**Acceptance**

- No read model outside migration reads old registry canonical symbol/name.

## Task 10: Update HTTP API And Frontend Contract

**Files**

- Modify token radar API owner.
- Modify `web/src/api/types.ts`
- Modify `web/src/lib/tokenRadar.ts`
- Modify `web/src/components/TokenTargetPage.tsx`
- Modify `web/src/App.test.tsx`
- Modify frontend component tests.

**Steps**

- [ ] Add compact identity metadata to token radar API rows:
  - `identity.confidence`
  - `identity.selected_evidence_kind`
  - `identity.selected_provider`
  - `identity.reason_codes`
  - `identity.conflict_count`
- [ ] Update frontend types.
- [ ] Rewrite `tokenRadarRowToTokenItem`:
  - resolved target label comes from `row.target`.
  - mention display symbol is separate context.
  - no `target.symbol ?? row.intent.display_symbol` fallback for resolved rows.
- [ ] Update TokenTargetPage:
  - title from target identity.
  - show identity confidence/reason codes in audit area.
  - no token-specific correction map.
- [ ] Add frontend tests:
  - row with target SLOP + mention SATO displays SLOP as token title and SATO only in evidence/context.
  - route key remains target ref.
  - identity metadata renders in score/audit details.
- [ ] Run:
  - `npm test -- --run`
  - `npm run build`

**Acceptance**

- Frontend never guesses canonical identity from mention symbol.
- UI can explain identity confidence without opening database.

## Task 11: Add Ops Commands For Recompute, Verify, Repair, Rebuild

**Files**

- Modify `src/gmgn_twitter_intel/cli.py`
- Add ops implementation module if needed.
- Add CLI tests.

**Steps**

- [ ] Add `ops rebuild-asset-identity-current`.
  - recomputes current identity from evidence for all or selected assets.
- [ ] Add `ops verify-token-identity --golden docs/generated/token_identity_golden.json`.
  - checks current identity, radar projection, and price subject alignment for golden corpus.
- [ ] Add `ops repair-token-identity --chain ... --address ... --symbol ... --name ... --reason ...`.
  - writes `manual_identity_repair` evidence.
  - recomputes current identity.
  - does not mutate current table directly.
- [ ] Add command tests:
  - verify returns non-zero on mismatch.
  - repair writes evidence and policy selects manual with reason.
- [ ] Run:
  - `uv run gmgn-twitter-intel ops --help`
  - `uv run pytest tests/test_cli*.py -q` if CLI tests exist.

**Acceptance**

- Operators have a transparent repair path.
- Manual repair is not a hidden override.

## Task 12: Final Runtime Deletion Migration And Code Sweep

**Files**

- Add final migration, likely `20260510_0022_drop_legacy_registry_identity_columns.py`.
- Update docs/tests that assert old schema.
- Sweep runtime code.

**Steps**

- [ ] Drop or fully retire these `registry_assets` columns:
  - `symbol`
  - `name`
  - `decimals`
  - `primary_source`
- [ ] If Postgres migration cannot drop immediately because old migrations/tests introspect them, update tests and generated docs in same PR.
- [ ] Remove old source-precedence tests.
- [ ] Remove migrations/tests that enforce old demotion SQL as current behavior.
- [ ] Run deletion grep:
  - `rg -n "_SOURCE_PRECEDENCE|DEX_SEARCH_SOURCE|DEX_ADDRESS_SEARCH_SOURCE" src tests`
  - `rg -n "primary_source|registry_assets\\.symbol|registry_assets\\.name" src tests`
  - expected: no runtime hits; migration history/docs may still contain historical text.
- [ ] Run:
  - `uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q`

**Acceptance**

- Runtime cannot silently fall back to old identity model because the old fields are gone or unreadable.

## Task 13: Backfill, Reverify, And Rebuild Local Data

**Commands**

- `uv run gmgn-twitter-intel ops rebuild-asset-identity-current`
- `uv run gmgn-twitter-intel ops verify-token-identity --golden docs/generated/token_identity_golden.json`
- `uv run gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 1000`
- `uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all --limit 1000`
- `uv run gmgn-twitter-intel ops rebuild-token-radar --window 4h --scope all --limit 1000`
- `uv run gmgn-twitter-intel ops rebuild-token-radar --window 24h --scope all --limit 2000`
- repeat for `scope matched`.

**Steps**

- [ ] Run migration locally.
- [ ] Recompute all current identities.
- [ ] Queue/run exact-address verification for:
  - `mention_only`
  - `provider_candidate`
  - `unknown`
  - conflicts.
- [ ] Verify golden corpus.
- [ ] Rebuild radar windows/scopes.
- [ ] Query API for SHIT/SLOP/SATO rows and record evidence in verification doc.

**Acceptance**

- Golden corpus passes against local Postgres.
- `5m/1h/4h/24h` all have non-empty current radar rows.
- SHIT/SLOP/SATO target/address/price alignment is correct after rebuild.

## Task 14: Full Verification And Browser Smoke

**Commands**

- `uv run pytest -q`
- `uv run ruff check src tests`
- `uv run python -m compileall src tests`
- `npm test -- --run`
- `npm run build`
- `docker compose build app`
- `docker compose up -d app`
- `curl -sS http://localhost:8765/healthz`

**Browser checks**

- Open `http://localhost:8765/`.
- Confirm token radar loads.
- Open target detail for:
  - SLOP `0x999b...`
  - SHIT `0xaf1e...`
  - SATO `0x829f...`
  - Solana SHIT `ShitJu...`
  - CEX ZEC route.
- Confirm:
  - route target id matches detail page target.
  - title symbol matches target identity.
  - mention symbol appears only as evidence/context.
  - identity confidence/reason codes are visible or inspectable.
  - console has no new runtime errors after clean reload.

**Acceptance**

- All command checks pass.
- Browser smoke confirms the product-visible symptom is gone.
- Verification evidence is recorded.

## PR Breakdown

### PR 1: Schema + Policy Foundation

- Add evidence/current tables.
- Add identity policy.
- Add repository.
- Add golden corpus.
- No runtime cutover yet except tests for new model.

Merge condition:

- New policy/repository tests pass.
- No runtime dual write added.

### PR 2: Writer Cutover

- Ingest writes tweet mention evidence.
- Discovery writes symbol candidate vs exact address evidence.
- Market sync verifies by identity confidence.
- Registry no longer decides canonical identity.

Merge condition:

- Writer tests pass.
- Old source precedence runtime code removed from touched paths.

### PR 3: Projection/API/Frontend Cutover

- Projection reads `asset_identity_current`.
- API exposes identity metadata.
- Frontend consumes target identity only.

Merge condition:

- Token radar golden projection passes.
- Frontend tests/build pass.

### PR 4: Migration Cleanup + Ops + Full Verification

- Drop old registry identity columns or make them unreachable then delete.
- Add ops commands.
- Rebuild local data.
- Add verification artifact.

Merge condition:

- Full verification passes.
- Deletion grep passes.
- Golden corpus passes against local Postgres.

## Rollout Order

1. Land schema/policy in branch.
2. Run migration on local Postgres.
3. Cut writers to evidence.
4. Cut readers/projection/frontend to current identity.
5. Run backfill/reverify/rebuild locally.
6. Delete old runtime identity paths.
7. Run full verification.
8. Merge to `main`.
9. Rebuild Docker app.
10. Verify local app at `http://localhost:8765/`.

## Rollback

Hard cut means rollback is code + DB restore, not runtime fallback.

- Before migration, take a DB snapshot.
- If migration fails before app cutover, restore DB snapshot and revert branch.
- If cutover lands and data is wrong, do not re-enable old `primary_source`; instead:
  - stop app.
  - restore DB snapshot.
  - revert merge commit.
  - rerun previous known-good Docker image.

No compatibility toggle will be introduced.

## Acceptance Test Commands

```bash
uv run pytest tests/test_asset_identity_policy.py -q
uv run pytest tests/test_asset_identity_repository.py -q
uv run pytest tests/test_registry_repository.py -q
uv run pytest tests/test_asset_ingest_flow.py -q
uv run pytest tests/test_token_discovery_worker.py -q
uv run pytest tests/test_asset_market_sync.py -q
uv run pytest tests/test_token_radar_projection.py -q
uv run pytest tests/golden/test_token_identity_evidence_corpus.py -q
uv run pytest -q
uv run ruff check src tests
uv run python -m compileall src tests
npm test -- --run
npm run build
```

Local Postgres:

```bash
uv run gmgn-twitter-intel ops rebuild-asset-identity-current
uv run gmgn-twitter-intel ops verify-token-identity --golden docs/generated/token_identity_golden.json
uv run gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 1000
uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all --limit 1000
uv run gmgn-twitter-intel ops rebuild-token-radar --window 4h --scope all --limit 1000
uv run gmgn-twitter-intel ops rebuild-token-radar --window 24h --scope all --limit 2000
```

Deletion grep:

```bash
rg -n "_SOURCE_PRECEDENCE|DEX_SEARCH_SOURCE|DEX_ADDRESS_SEARCH_SOURCE" src tests
rg -n "primary_source|registry_assets\\.symbol|registry_assets\\.name" src tests
rg -n "intent\\.display_symbol.*target|target.*display_symbol" web/src src/gmgn_twitter_intel/pipeline/token_radar_projection.py
```

Expected:

- no runtime source precedence hits.
- no runtime old registry identity reads.
- no resolved-target mention-symbol fallback.
- historical migration/doc hits are acceptable only outside runtime code.

## Verification Artifact

Create after implementation:

`docs/superpowers/plans/active/2026-05-10-token-identity-evidence-hard-cut-verification.md`

Required sections:

- command table with pass/fail.
- migration result.
- golden corpus result.
- local API SHIT/SLOP/SATO samples.
- browser screenshots or DOM excerpts for representative token pages.
- deletion grep output.
- remaining risks, if any.

## Acceptance Checklist

- [x] `asset_identity_evidence` exists and stores identity claims.
- [x] `asset_identity_current` exists and stores selected current identity.
- [x] `IdentityEvidencePolicy` is the only canonical identity selector.
- [x] `registry_assets` no longer owns canonical `symbol/name/primary_source`.
- [x] Tweet mentions cannot directly set canonical target symbol.
- [x] Symbol search cannot overwrite exact evidence.
- [x] Exact address evidence corrects tweet alias pollution.
- [x] Market sync identity verification uses confidence, not field completeness.
- [x] Projection target symbol/name comes from current identity.
- [x] API exposes compact identity reason metadata.
- [x] Frontend renders identity from target/current identity and keeps mention separate.
- [x] SHIT/SLOP/SATO golden corpus passes through backend test coverage.
- [x] Old runtime source-precedence paths are deleted.
- [x] Full backend and frontend verification passes.

## Done Means

For any future wrong-looking Token Radar row, an engineer can answer with data only:

- what the tweet mentioned.
- what target was resolved.
- what evidence selected the current identity.
- what conflicting evidence lost.
- why price is attached to that target.
- why the next sync will not flip identity back.

If the answer requires reading frontend fallback logic, remembering a source precedence number, or patching one token manually, this plan is not complete.
