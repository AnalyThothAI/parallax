# Plan — Backend KISS whole-chain simplification

**Status**: Review
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/spec.md`
**Worktree**: `.worktrees/backend-kiss-deep-audit/`
**Branch**: `codex/backend-kiss-deep-audit`
**Approved by**: delegated `/goal` for whole-architecture KISS review and implementation
**Approved at**: 2026-07-22

## Pre-flight

- [x] Spec is approved by the delegated autonomous goal.
- [x] Worktree exists at `.worktrees/backend-kiss-deep-audit/` and the branch is `codex/backend-kiss-deep-audit`.
- [x] Baseline `uv run ruff check .` passes.
- [x] Baseline non-live pytest lanes pass: `3467 passed, 1 skipped`.

Known-failing baseline diagnostics:

- `uv run ruff check --select C90 src tests` reports 36 functions above complexity 10. C90 is an audit signal, not a configured completion gate; each finding requires semantic review.

## File-level edits

### Audit evidence and SDD coordination

- `docs/generated/subagent-reports/backend-kiss-deep-audit-task-1.md`: capture the validated runtime/composition/data-flow audit.
- `docs/generated/subagent-reports/backend-kiss-deep-audit-task-2.md`: capture the validated fact/projection domain audit.
- `docs/generated/subagent-reports/backend-kiss-deep-audit-task-3.md`: capture the validated News/Macro/test-architecture audit.
- `docs/generated/subagent-reports/backend-kiss-deep-audit-task-4.md`: capture the validated provider-adapter/PostgreSQL execution-plane audit.
- `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/{spec,plan,tasks,verification}.md`: keep decisions, exact touch sets, TDD order, and evidence current.
- `docs/reviews/backend-kiss-hard-cut-implementation-audit-zh-2026-07-22.md`: append the verified continuation review, implemented cuts, and remaining evidence boundaries after code verification.

### Production and test hard cuts

- `src/parallax/platform/runtime/worker_base.py`: replace the duplicated loop/maintenance iteration body with one private iteration path and one `running` re-entry guard; preserve start/stop, interval, backoff, status, and telemetry semantics.
- `src/parallax/platform/config/settings.py`: keep only `enabled`, `interval_seconds`, and `backoff` on `PerWorkerSettings`; move operational fields to the concrete worker settings that consume them, and delete unused `BackoffPolicy.kind` plus the dead `write_default_workers_config()` entry point. Current `~/.parallax/workers.yaml` was structurally checked without printing secrets and does not set removed inherited fields.
- `src/parallax/app/runtime/provider_wiring/{asset_market,binance,gmgn,okx,types}.py`: reuse `domains.asset_market.chain_identity` rather than local chain/address regex and alias maps; remove the internal malformed-`OkxProviderBundle` cleanup fiction and the unused `dex_candle_market` field. Preserve partial close, close de-duplication, original-error notes, fallback quotes, provider health, and unavailable semantics.
- `src/parallax/app/runtime/{repository_session,job_queue}.py`, `src/parallax/app/operations/{diagnostics,news,token_intel,queue_health}.py`, `src/parallax/app/surfaces/{api/routes_ops.py,cli/commands/ops.py}`, `Makefile`: delete the unused pooled `repository_session()` helper and single-instance `JobQueueDescriptor`; move operational queries out of runtime, remove News repair's fake `domain` branch/nested result, reuse queue-health facts for notification diagnostics, and delete the stale `token-radar-cex-recover` target. No compatibility re-export is retained.
- `src/parallax/domains/{ingestion,asset_market,token_intel,news_intel}`: publish the `IngestedEvent.token_resolutions` already returned by the ingest transaction rather than re-read PostgreSQL; delete placeholder `anchor`/`projection` results and the unused rebuild `projection_limit`; remove Token Radar's duplicate missing-work pass; call the required News repository method directly.
- `src/parallax/domains/asset_market/providers.py`, `src/parallax/integrations/{binance,gmgn,okx}`: atomically remove the provider Candle protocol, capability, DTOs, wiring, and adapter methods because no runtime consumer exists. The public `MarketCandlesService` remains and continues to report explicit unsupported status.
- `src/parallax/integrations/binance/usdm_futures_client.py`: remove zero-consumer `premium_index`, `open_interest_hist`, and simple `ticker` endpoints and their DTO/parsers; retain `exchange_info` and current production `ticker_24hr`.
- `src/parallax/integrations/news_feeds/{opennews_client,provider_registry,feed_client}.py`: make typed `fetch_policy_json` the only OpenNews subscription policy, use the generic RSS-like wrapper for CryptoPanic, and delete zero-consumer registry/context-manager methods. Preserve cursor recovery, partial-patch merge, feed retries, and explicit unsupported-provider failure.
- `src/parallax/platform/db/{queue_terminal,postgres_audit}.py`: remove terminal-history's fake `active` status and the unused audit `token_factor_version` binding; preserve terminal evidence, arbitrary reason buckets, current classifiers, and immutable migrations.
- Tests in the directly corresponding unit/contract/integration files will be rewritten around current positive behavior or removed when they only freeze deleted private/source/retired shapes. Confirmed-unused doubles and redundant Macro migration/runtime emulators are deleted; real PostgreSQL News page coverage absorbs the low-score inclusion assertion.
- `docs/DESIGN_DISCIPLINE.md` and `docs/references/POSTGRES_PERFORMANCE.md`: correct stale architecture language and retire the old machine-specific performance snapshot as current guidance while retaining the operational checklist.

The implementation only consolidates or deletes existing paths. It introduces no worker, table, service process, compatibility adapter, public response field, or generic framework.

### Explicit keep / defer decisions

- Keep the static worker manifest/factories/scheduler, `InactiveWorker`, runtime snapshot, split PostgreSQL pools, zero-SQL status path, exact public schemas, fallback quote provider, terminal/model/delivery ledgers, and large cohesive News/Macro repositories.
- Keep current terminal reason classifiers; their few branches are an open triage policy, not a duplicate lifecycle.
- Defer the News model pre-call ledger, token-image atomic completion, discovery in-flight recovery, and notification stale-CAS outcome because they require correctness-specific state-machine designs.
- Defer OKX external payload aliases, provider-local retry policy, provider fallback removal, event raw-payload cleanup, and PostgreSQL tables/indexes/hot queries until sealed live-provider or current physical-database evidence exists.

### Storage / migrations

- Revisions `20260721_0185`, `20260722_0186`, and `20260722_0187` remain unchanged.
- Post-merge real-data validation found that `0186` introduced the strict
  `normalization.cohort_status` producer/validator contract without invalidating
  the already-persisted private `token_radar_target_features` cache. Add
  `20260722_0188_token_radar_factor_cache_hard_cut.py` to requeue every identity
  present in feature/current/rank-source state, clear leases/errors, and truncate
  only the rebuildable feature cache. Material facts, current rows, publication
  state, first-seen state, rank-source edges, and the existing dirty queue remain.
  No malformed JSON backfill, compatibility default, or validator weakening is
  permitted.

### Tests

- Keep `tests/architecture/test_kiss_runtime_invariants.py` as the compact root architecture contract.
- Exact positive behavior tests and redundant test removals will be listed after the audit gate; no source-shape test is removed without proving equivalent current behavior elsewhere.

## PR breakdown

1. **PR 1 — evidence-backed backend KISS continuation**: audit, exact plan revision, production/test hard cuts, canonical documentation, and verification as one coherent change. Splitting is allowed only if a discovered cut has an independently deployable ownership boundary.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: four validated audits were cross-checked against current callers; Tasks 6–10 name the implementation and verification slices. |
| Plan preserves canonical architecture boundaries. | Pass: no new arrow, writer, table, worker, or public contract is authorized. |
| Compatibility code or old files are not retained. | Pass: each accepted cut must remove all callers in the same slice, and no compatibility implementation is authorized. |
| Parallel touch/conflict sets are explicit. | Pass: Tasks 6–8 have disjoint owned production/test sets; parent owns cross-cutting operations, documentation, integration, and final repair. |

## Rollout order

1. Validate read-only audit reports and cross-check every proposed cut against current consumers.
2. Apply worker/config, domain-flow, and provider/DB hard cuts in disjoint bounded slices.
3. Apply cross-cutting operations/directory moves and focused test cleanup.
4. Run targeted checks after each slice and a diff audit; record the user-authorized stop of full `make check-all` without weakening it.
5. Merge the reviewed hard cut to `main`, build/start the real Docker stack, probe the real chain, run an independent implementation validation, and close only after all executed and omitted evidence is explicit.

## Rollback

Before commit, each code slice is recoverable by reverting only this feature's diff; unrelated work is never touched. Revision `0188` is deliberately irreversible because it truncates only a rebuildable private feature cache after first enqueuing every affected identity. Material facts and serving rows are preserved, and rollback is forward repair rather than migration downgrade. If another cut changes a released public or persistence contract unexpectedly, stop and revise the spec rather than add a compatibility path.

## Acceptance test commands

- AC1: `uv run python scripts/validate_sdd_artifacts.py`
- AC2: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py`
- AC3: `uv run pytest -q tests/unit tests/architecture tests/contract`
- AC4: `make docker-status`
- AC5: `uv run python scripts/regen_sdd_work_index.py --check`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/verification.md`. The feature remains in Review because the user explicitly omitted the complete `check-all` lane; executed and omitted evidence is recorded exactly.
