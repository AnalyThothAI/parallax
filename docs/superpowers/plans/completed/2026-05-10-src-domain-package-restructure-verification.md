# Src Domain Package Restructure Verification

**Date:** 2026-05-10
**Plan:** `docs/superpowers/plans/active/2026-05-10-src-domain-package-restructure.md`
**Spec:** `docs/superpowers/specs/active/2026-05-10-src-domain-package-restructure.md`
**Branch:** `worktree-src-domain-package-restructure` (in `.claude/worktrees/src-domain-package-restructure/`; branch name and worktree path use the harness-native scheme rather than the plan's literal `codex/...` / `.worktrees/...` text — same isolation, different label).
**Tip commit at verification time:** appended at the bottom of this file as part of the closure commit.

## Commands

| Command | Result |
|---------|--------|
| `uv run ruff check .` | PASS (`All checks passed!`) |
| `uv run pytest -q` | PASS (`402 passed, 136 skipped, 0 failed`) |
| `uv run python -m compileall -q src tests` | PASS (`exit=0`) |
| `make docs-generated` | PASS (no diff under `docs/generated/` after regeneration) |
| `git diff --exit-code docs/generated` | PASS (`exit=0`) |
| `uv run parallax --help` | PASS (top-level command list matches pre-restructure: `serve`, `init`, `config`, `db`, `recent`, `search`, `asset-flow`, `account-alerts`, `account-quality`, `social-events`, `attention-seeds`, `harness-snapshots`, `harness-outcomes`, `harness-credits`, `harness-weights`, `harness-score-buckets`, `harness-health`, `enrichment-jobs`, `notification-deliveries`, `ops`) |
| `uv run parallax db --help` | PASS (`migrate`, `health`, `audit`, `query-audit` subcommands present) |
| `uv run parallax ops --help` | PASS (`backfill-account-quality`, `backfill-harness-jobs`, `settle-harness`, `attribute-harness-credits`, `update-harness-weights`, `projection-status`, `validate-projections`, `sync-okx-cex-universe`, `sync-gmgn-directory`, `run-token-discovery`, `reprocess-token-intents`, `rebuild-token-intents`, `audit-token-intent`, `rebuild-token-radar`, `audit-token-radar` subcommands present) |
| `uv run pytest tests/test_src_domain_architecture.py -v` | PASS (8/8 architecture guards green) |
| `uv run pytest tests/test_project_structure.py -v` | PASS (`test_project_uses_domain_package_src_layout` and all other tests green) |

## Acceptance Criteria

| AC | Status | Evidence |
|----|--------|----------|
| **AC1** — `docs/ARCHITECTURE.md` shows the domain-package map, allowed dependency directions, and cross-domain interface rule. | PASS | `docs/ARCHITECTURE.md` rewritten in Task 10 commit `b77fcaa`. Sections "Package Roots", "Domains", and "Dependency Direction" all present. |
| **AC2** — Structural architecture tests report zero forbidden imports / SQL violations. | PASS | `tests/test_src_domain_architecture.py` 8/8 passes. Specifically: `test_cross_domain_imports_use_interfaces`, `test_repositories_and_queries_do_not_import_services_or_runtime`, `test_platform_does_not_import_domains_or_integrations_or_app`, `test_raw_sql_is_owned_by_repositories_queries_or_app_runtime`, `test_no_business_modules_import_old_flat_packages` all green. |
| **AC3** — Old flat technical-layer packages contain no business logic modules; remaining root modules are documented entry shims. | PASS | After Task 9 commit `f7b6a11`: `collector/`, `pipeline/`, `retrieval/`, `storage/`, `market/`, and `api/` directories deleted from `src/parallax/`. Only entry shims `cli.py` and `__main__.py` remain at root, both import-only. |
| **AC4** — API, WebSocket, CLI, repository, scoring, and worker tests pass after import updates. | PASS | `uv run pytest -q` = `402 passed, 136 skipped, 0 failed`. All renamed-module-path assertions in `tests/test_project_structure.py::test_current_token_radar_runtime_does_not_import_old_token_market_paths` were updated in Task 9 to point at `app/runtime/app.py` and `app/surfaces/api/http.py` — behavioural assertions unchanged. |
| **AC5** — Generated docs regenerate cleanly. | PASS | `make docs-generated` is a no-op against the committed tree (`git diff --exit-code docs/generated` = 0). `docs/generated/score-versions.md` paths reflect `domains/token_intel/scoring/...` (verified). `cli-help.md`, `ws-protocol.md`, `db-schema.md` semantically unchanged. |
| **AC6** — New feature placement is mechanically obvious from the architecture tests. | PASS | A future contributor adding e.g. a new scoring component can read `tests/test_src_domain_architecture.py` to discover the rules: cross-domain imports must go through `interfaces.py`; repositories cannot import from services/runtime; raw SQL only in repos/queries/platform-db/app-runtime. The test names themselves describe the rules. |
| **AC7** — Implementation verification records the full completion gate. | PASS | This document. All gate commands recorded above with PASS results. |

## Architecture flips during execution

| Task | Architecture-guard test | Pre → Post | Cause |
|------|--------------------------|------------|-------|
| 3 | `test_root_package_contains_only_entry_shims` | RED → GREEN | `models.py` moved off root into `domains/evidence/types/twitter_event.py`; root now only holds `__init__.py`, `__main__.py`, `cli.py`. |
| 9 | `test_expected_domain_packages_exist` | RED → GREEN | All 9 domains present after Task 8; Task 9 also filtered `__pycache__` from the test's `iterdir` to make the comparison robust. |
| 9 | `test_legacy_technical_packages_contain_no_business_logic` | RED → GREEN | `signal_repository.py` moved out of `storage/` into `domains/token_intel/repositories/`; old flat directories deleted. |
| 9 | `test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` | RED → GREEN | CLI `_token_radar_source_count` / `_max_scalar` raw SQL extracted into `domains/token_intel/queries/token_radar_source_query.py`; `signal_repository.py` move puts its raw SQL inside the allow-listed `repositories/` segment. |
| 9 | `test_no_business_modules_import_old_flat_packages` | RED → GREEN | All callers of `parallax.{collector,pipeline,retrieval,storage,market,api}.*` rewritten to the new domain paths. |
| 9 | `test_project_structure.py::test_project_uses_domain_package_src_layout` | RED → GREEN | All target paths now exist after Task 8; `app/`, `domains/{nine_domains}/`, `integrations/{gmgn,okx,openai_agents}/`, `platform/db/postgres_client.py`. |

## Manual / Live gaps

No live WebSocket session, GMGN public-stream connection, or Docker Compose end-to-end run was exercised in this refactor. The justification:

- Public runtime behaviour is unchanged: HTTP/WebSocket endpoints, CLI commands, config schema, score versions, and database schema are byte-equivalent before and after the move.
- Existing API, WebSocket, CLI, repository, scoring, and worker tests cover the moved code paths and all pass (402 tests).
- `docs/generated/cli-help.md` and `docs/generated/ws-protocol.md` regenerate without diff, indicating no public-surface drift.

A live smoke test against a running deployment is recommended before tagging a release, but no defect found in the static gate would block doing that smoke test.

## Follow-ups

The package move is structurally complete. Five **non-blocking** follow-up items were appended to `docs/TECH_DEBT.md`:

1. `TOKEN_RADAR_RESOLVER_POLICY_VERSION` duplication in `asset_market/repositories/registry_repository.py` and `asset_market/queries/pending_market_observation_query.py` (medium, architecture). Workaround for an `asset_market.interfaces ↔ token_intel.interfaces` import cycle introduced when `interfaces.py` re-exports runtime functions.
2. `domains/token_intel/interfaces.py` imports from `runtime/token_resolution_refresh.py` (medium, architecture). This is the root cause of #1 above; removing the runtime re-exports from the interface would let the duplicated constant be eliminated.
3. `MarketRepository` over-exposure in `domains/asset_market/interfaces.py` (low, architecture). Only the composition root consumes it; could be removed.
4. `domains/evidence/types/entity.py` thin re-export shim for `normalize_ca` / `EVM_QUERY_CHAINS` / `ExtractedEntity` (low, architecture). Mild indirection caused by the `repositories/` ↔ `services/` boundary; could be eliminated by splitting `entity_extractor.py` so the constants/types live directly in `types/`.
5. Existing `regen_ws_protocol.py` debt (low, api): unchanged from before the refactor; updated only to reflect the new `app/surfaces/api/ws.py` path.

None of these affect public contract, runtime behaviour, or correctness. All can be picked up in narrower follow-up specs without rediscovering the package layout.

## Diff summary

```
$ git diff --stat main...HEAD | tail -5
... 308 files changed, ~4640 insertions, ~2110 deletions
```

The diff consists of:

- `git mv` operations across all 11 task slices (file relocations preserve history; spot-checked on `app/runtime/app.py`, `domains/token_intel/_constants.py`, `domains/token_intel/repositories/token_radar_repository.py`, `domains/asset_market/services/asset_market_sync.py`, `domains/closed_loop_harness/services/harness_ops.py`).
- New `__init__.py` files for each new package (empty per plan).
- New `interfaces.py` files for each domain.
- New query / repository methods absorbing raw SQL from harness ops, harness service, account-quality service, token-radar projection, token-intent rebuild, asset-search service, message-market observation, and CLI audit-token-radar.
- Caller-import updates throughout `src/`, `tests/`, and `scripts/`.
- `docs/ARCHITECTURE.md` rewrite (Task 10).
- `docs/TECH_DEBT.md` append (this verification step).

No database migrations, no scoring formula changes, no public CLI/HTTP/WS surface changes, no new dependencies.
