# Token Identity Evidence Hard Cut Verification

**Date**: 2026-05-10  
**Worktree**: `.worktrees/token-identity-freshness-hard-cut`  
**Branch**: `codex/token-identity-freshness-hard-cut`

## Result

The hard cut is implemented in runtime code. Canonical asset identity now flows through `asset_identity_evidence` -> `asset_identity_current`; `registry_assets` owns address identity only. Token Radar projection and frontend mapping no longer fall back from resolved target identity to tweet mention symbol.

## Commands

| Command | Result |
|---|---|
| `uv run pytest -q` | Pass: 416 passed, 141 skipped |
| `uv run python -m compileall src tests` | Pass |
| `uv run ruff check src tests` | Pass |
| `npm ci` | Pass |
| `npm test -- --run` | Pass: 15 files, 86 tests |
| `npm run build` | Pass |
| `uv run pytest tests/test_asset_identity_policy.py tests/test_asset_identity_repository.py tests/test_token_radar_projection.py tests/test_asset_market_sync.py -q` | Pass: 30 passed |
| `uv run parallax db health` | Expected stale: real local DB is still on `20260509_0020`; code head is `20260510_0021` |
| `rg -n "_SOURCE_PRECEDENCE|DEX_SEARCH_SOURCE|DEX_ADDRESS_SEARCH_SOURCE|ADDRESS_VERIFIED_SOURCES|market_hydrator|preflight_hydration|radar_projection_preflight|demote_unretained|demote_symbol" src/parallax web/src --glob '!**/platform/db/alembic/versions/*.py'` | Pass: no runtime hits |
| `rg -n "registry_assets\\.symbol|registry_assets\\.name|registry_assets\\.decimals|registry_assets\\.primary_source" src/parallax web/src --glob '!**/platform/db/alembic/versions/*.py'` | Pass: no runtime hits |

## Real Local DB Dry-Run

The real local production DB was not migrated in place because `20260510_0021`
drops legacy `registry_assets` identity columns. Instead, verification ran the
`0021` upgrade SQL in a single PostgreSQL transaction, queried the migrated
schema with production data, exercised `TokenRadarSourceQuery` and projection
grouping for SHIT/SLOP/SATO samples, then rolled the transaction back.

- Before dry-run: `alembic_version = 20260509_0020`.
- In transaction: `asset_identity_evidence` and `asset_identity_current` existed; `registry_assets.symbol/name/decimals/primary_source/evidence_level` were gone.
- After rollback: `asset_identity_evidence` and `asset_identity_current` did not exist; `alembic_version` stayed `20260509_0020`.

Sample current identity after migration backfill:

| Address | Current identity | Confidence | Evidence kind |
|---|---|---|---|
| `0x829f4b62eebe12af653b4dd4ffc480966f7d7f09` | `SATO` / `sato` | `provider_exact` | `okx_dex_exact_address` |
| `0x999b49c0d1612e619a4a4f6280733184da025108` | `SLOP` / `SLOP` | `provider_exact` | `okx_dex_exact_address` |
| `0xaf1e52927d724fd34773bd53ada57f4c2b742069` | `SHIT` / `Dogeshit` | `provider_exact` | `okx_dex_exact_address` |
| `ShitJuMfPKCQU7LedLERFYapDta7CCdKExPWX2gETRH` | `SHIT` / `****` | `provider_candidate` | `okx_dex_symbol_candidate` |

Important mismatch samples remain visible as mention-vs-target evidence instead
of being written into registry identity:

| Mention | Canonical target | Address | Current resolutions |
|---|---|---|---:|
| `SLOP` | `SHIT` | `0xaf1e52927d724fd34773bd53ada57f4c2b742069` | 33 |
| `SATO` | `SLOP` | `0x999b49c0d1612e619a4a4f6280733184da025108` | 2 |
| `SHIT` | `SATO` | `0x829f4b62eebe12af653b4dd4ffc480966f7d7f09` | 1 |

Projection dry-run on the migrated transaction:

- Source rows read: 58,080.
- Source rows for the four samples: 1,941.
- Projected sample rows were all `resolved`.
- Projected target symbols came from `asset_identity_current`, not the latest
  tweet mention symbol.

Repository/read-model dry-run on the migrated transaction:

- 24h source rows read: 14,754.
- 24h source rows for the four samples: 517.
- Sample rows projected: 4.
- `TokenRadarRepository.replace_rows(...)` inserted the sample projection rows
  in transaction.
- `AssetFlowService.asset_flow(...)` read them back through the public read
  model with projection version `token-radar-v8-identity-evidence`.
- Public read model market hydration: 3 fresh, 1 stale, 0 missing.
- Public target identities read back as:
  - `SATO` -> `SATO` / `provider_exact`.
  - `SLOP` -> `SLOP` / `provider_exact`.
  - EVM `SHIT` -> `SHIT` / `provider_exact`.
  - Solana `SHIT` -> `SHIT` / `provider_candidate`.
- The transaction was rolled back after the read-model check.

Price freshness from the same dry-run:

| Target | Market status | Snapshot age |
|---|---|---:|
| `SATO` EVM | `fresh` | 0.8m |
| `SLOP` EVM | `fresh` | 1.5m |
| `SHIT` EVM / Dogeshit | `stale` | 3.9h |
| `SHIT` Solana | `stale` | 6.2m |

## Migration

- Added `20260510_0021_asset_identity_evidence_hard_cut.py`.
- Creates `asset_identity_evidence` and `asset_identity_current`.
- Backfills legacy registry identity once into evidence rows.
- Drops `registry_assets.symbol`, `registry_assets.name`, `registry_assets.decimals`, `registry_assets.primary_source`, and `registry_assets.evidence_level`.

## Code Path Checks

- Ingest writes tweet CA mentions as `tweet_contract_mention` and GMGN payload identity as `gmgn_payload_exact`.
- OKX symbol discovery writes `okx_dex_symbol_candidate`.
- OKX exact address verification writes `okx_dex_exact_address`.
- Market sync triggers exact identity verification from `identity_confidence`, not market field completeness.
- Token Radar source queries join `asset_identity_current`.
- Projection version is `token-radar-v8-identity-evidence`.
- Frontend resolved target display uses `target.symbol` only; unresolved rows may still show `intent.display_symbol`.

## Remaining Risks

- Real local DB verification was a transaction dry-run and intentionally did not persist migration/projection rows.
- Historical Alembic migrations before `0021` still reference old registry columns because they run before the hard-cut migration drops those columns.
