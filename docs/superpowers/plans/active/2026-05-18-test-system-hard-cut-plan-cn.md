# Test System Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治后端测试体系：删除旧 hard-cut 后遗留测试和假 integration，重新整理测试目录，让测试明确锁住 PostgreSQL-first、worker 生命周期、异步 wake/catch-up、provider 协议和完整热路径。

**Architecture:** 保留现有 Kappa/CQRS 主干：PostgreSQL material facts 是业务真相，derived read models 可重建且单 runtime writer，`NOTIFY` 只是 wake hint。测试体系按 lane 分工：unit 锁纯逻辑，integration 锁真实 PostgreSQL 行为，architecture 锁边界和目录纪律，contract 锁 public/provider 协议，e2e 锁完整热路径。不保留旧路径、不保留旧字段 fallback、不新增兼容性代码。

**Tech Stack:** Python 3.13, pytest, testcontainers PostgreSQL, psycopg, FastAPI, Alembic, Makefile gates, React/Vitest/Playwright for frontend-adjacent verification when needed.

---

## Current Baseline

Observed during the 2026-05-18 audit:

- `uv run pytest --collect-only -q`: 1433 Python tests collected.
- `tests/unit`: 125 files, roughly 1003 collected tests.
- `tests/integration`: 35 files, roughly 273 collected tests.
- `tests/architecture`: 8 files, 92 collected tests.
- `tests/contract`: 1 file, 6 collected tests.
- `tests/e2e`: 1 file, 4 collected tests.
- `tests/golden`: 1 file, 4 collected tests.
- Root `tests/test_*.py`: 4 files, 51 collected tests.

Known red baseline that this plan owns:

- `tests/architecture/test_event_anchor_capture_redesign_contracts.py::test_old_price_observation_runtime_is_removed`
  fails because `docs/generated/backend-architecture-audit-2026-05-17.md` still contains old `price_observations` text.
- `tests/architecture/test_harness_structure.py::test_lane_roots_have_no_loose_files`
  fails because `docs/superpowers/plans/2026-05-18-event-anchor-backfill-decoupling-plan-cn.md`
  is loose at the plans lane root.

Known red baseline that should remain documented until fixed in the relevant branch:

- Any existing user worktree or untracked implementation file not listed here is out of scope and must not be reverted.

## Hard-Cut Rules

- No compatibility code: no `_compat_*`, no `legacy_*_fallback`, no dual read of old and new schema, no "if old field exists then use it".
- A test that describes a deleted runtime path must be deleted or rewritten to the current model.
- A skipped business test is not an acceptable long-term state. Environment skips are allowed only for unavailable external infrastructure and must say they cannot count as verification evidence.
- Unit tests must not touch PostgreSQL, real network, real `~/.parallax`, or production DSNs.
- Integration tests must hit real PostgreSQL/testcontainers when asserting storage, repository, worker, API read-model, or query behavior.
- Fake provider tests are allowed only when they exercise the current adapter boundary and are named as unit/contract tests, not as production integration coverage.
- Provider live drift checks must be opt-in or scheduled; CI must use captured, redacted protocol fixtures.

## Target Test Directory Shape

```text
tests/
  architecture/
    test_completion_gates.py
    test_event_anchor_capture_redesign_contracts.py
    test_harness_structure.py
    test_project_structure.py
    test_public_event_token_projection.py
    test_src_domain_architecture.py
    test_test_lane_contracts.py              # new
    test_token_profile_current_hard_cut.py
    test_worker_inventory_contract.py        # new
    test_worker_runtime_contracts.py
  contract/
    provider_frames/
      gmgn_public_tw_complete.json
      gmgn_public_tw_partial_then_complete.json
      okx_dex_price_info.json
      okx_dex_search_result.json
    test_openapi_drift.py
    test_provider_protocol_fixtures.py       # new
    test_provider_drift_live.py              # new, opt-in
  e2e/
    _uvicorn_entry.py
    _writer_entry.py
    conftest.py
    test_backend_hot_path.py                 # new
    test_golden_path.py
  golden/
    conftest.py
    test_token_radar_corpus.py
  integration/
    test_worker_missed_wake_recovery.py      # new
    test_worker_advisory_lock_single_writer.py # new
    test_market_tick_wake_idempotency.py     # new
    ...
  support/
    db_seeds.py                              # new
    fake_providers.py                        # new
    hot_path_runtime.py                      # new
    provider_fixtures.py                     # new
  unit/
    test_factor_snapshot.py                  # moved from root
    test_okx_dex_ws_client.py                # moved from root
    test_pulse_decision_agent_client.py      # moved from root
    ...
```

Root `tests/test_*.py` must be empty after this plan.

## File-Level Edits

### Test Governance And Gates

- Modify: `docs/TESTING.md`
  - Define unit/integration/architecture/contract/e2e/golden lanes.
  - State that integration must use real PostgreSQL for storage/query behavior.
  - State that business skips are not allowed after this hard cut.
  - State that provider drift live checks are opt-in and not a CI dependency.
- Modify: `docs/WORKFLOW.md`
  - Clarify verification evidence when `make check-all` is blocked by external infrastructure.
  - Keep `make check-all` as the only final evidence command.
- Modify: `Makefile`
  - Update `test-e2e` to include both `tests/e2e` and `tests/golden`, or add a separate `test-golden` target and call it from `check-all`.
  - Keep `check` limited to fast lanes: lint/type/unit/architecture/contract.
  - Keep `check-all` as full verification: `check`, integration, e2e, golden, coverage.
- Create: `tests/architecture/test_test_lane_contracts.py`
  - Ban root `tests/test_*.py`.
  - Ban `GMGN_PROD_POSTGRES_DSN` under `tests/unit`.
  - Ban direct live DSN writes outside explicit operational tests.
  - Ban `@pytest.mark.skip` in business tests unless allowlisted as environment-only.
  - Ban FakeRuntime/FakeRepository in `tests/integration` unless the file name is explicitly a public-surface contract.
- Modify: `tests/architecture/test_harness_structure.py`
  - Ensure `docs/superpowers/plans/active/` and `completed/` are the only plan file lanes.
  - Keep root lane loose-file failure strict.

### Existing Red Governance Cleanup

- Modify or regenerate: `docs/generated/backend-architecture-audit-2026-05-17.md`
  - Remove stale `price_observations` wording from the generated audit, or regenerate it from current architecture inputs.
  - Do not weaken `test_old_price_observation_runtime_is_removed`.
- Move: `docs/superpowers/plans/2026-05-18-event-anchor-backfill-decoupling-plan-cn.md`
  - Target: `docs/superpowers/plans/active/2026-05-18-event-anchor-backfill-decoupling-plan-cn.md`
  - Preserve content exactly unless a separate owner asks for edits.

### Root Test Migration

- Move: `tests/test_factor_snapshot.py`
  - Target: `tests/unit/test_factor_snapshot.py`
  - Keep as unit if it is pure schema/factor validation.
- Move: `tests/test_no_factor_snapshot_fallback.py`
  - Target: `tests/architecture/test_no_factor_snapshot_fallback.py`
  - Keep only architecture-hard-cut assertions; delete any behavior-shaped test that is only grep.
- Move: `tests/test_okx_dex_ws_client.py`
  - Target: `tests/unit/test_okx_dex_ws_client.py`
  - Move protocol-shape fixtures into `tests/contract/provider_frames/` when they represent real provider frames.
- Move: `tests/test_pulse_decision_agent_client.py`
  - Target: `tests/unit/test_pulse_decision_agent_client.py`
  - Keep fake LLM/client behavior as unit-level adapter tests.

### Obsolete Or Monkey Tests

- Rewrite: `tests/integration/test_resolution_refresh_worker.py`
  - Replace skipped pre-hard-cut `registry_assets.symbol/name/decimals` tests with current `asset_identity_evidence/current` seeds.
  - Assert `ResolutionRefreshWorker` updates `token_intent_resolutions`, identity evidence/current rows, discovery rows, and emits `resolution_updated` only through the injected wake bus.
- Rewrite: `tests/integration/test_enrichment_worker.py`
  - Replace skipped harness materializer tests with current identity + market tick seeds.
  - Assert non-signal and signal paths write current enrichment/harness rows without old asset registry fields.
- Rewrite: `tests/integration/test_enrichment_repository.py`
  - Replace skipped Agents SDK audit shape test with current audit row schema.
  - Assert model run/audit facts are written even when downstream materialization abstains.
- Rewrite: `tests/integration/test_harness_ops.py`
  - Replace skipped `pass` test with a real seed: market-ready harness snapshot plus entry tick.
  - Assert terminal states: ready, insufficient market data, expired.
- Move/rewrite: `tests/unit/test_token_radar_idempotency.py`
  - Target: `tests/integration/test_token_radar_idempotency.py`
  - Remove use of `GMGN_PROD_POSTGRES_DSN`.
  - Remove monkeypatch of `_source_rows`.
  - Seed facts in a disposable test database and call the real projection worker/repository path.

### Worker And Async Runtime Semantics

- Create: `tests/integration/test_worker_missed_wake_recovery.py`
  - Seed `market_ticks` or `token_intent_resolutions` without calling `WakeBus`.
  - Run `TokenRadarProjectionWorker.run_once()` or a bounded scheduler loop.
  - Assert `token_radar_rows` / coverage catches up from DB state alone.
  - Repeat for `pulse_candidate` with `token_radar_rows` seeded without `token_radar_updated`.
- Create: `tests/integration/test_worker_advisory_lock_single_writer.py`
  - Use real PostgreSQL advisory locks.
  - Start two same-key projection workers or directly acquire through `WorkerBase`.
  - Assert only one worker processes and the other records `advisory_lock_unavailable`.
  - Assert lock release allows the second worker to process afterward.
- Create: `tests/architecture/test_worker_inventory_contract.py`
  - Parse the worker inventory table in `docs/WORKERS.md`.
  - Compare worker keys with `worker_registry.py`.
  - Compare `WakeBus` notify method channel names with documented wake-out.
  - Compare `WorkersSettings.wakes_on` with documented wake-in.
  - Compare documented writes with the existing single-writer allowlist for read models.
- Create: `tests/integration/test_market_tick_wake_idempotency.py`
  - Insert duplicate deterministic `MarketTick` rows.
  - Assert repository returns actual inserted count or inserted ids.
  - Assert market tick workers emit wake only for actual inserted rows or coalesced changed targets.
  - If the current repository returns attempted count, write this as a failing test first and fix production behavior without compatibility code.

### Provider Protocol Drift

- Create: `tests/contract/provider_frames/gmgn_public_tw_complete.json`
  - Redacted real GMGN public Twitter frame with complete snapshot marker.
- Create: `tests/contract/provider_frames/gmgn_public_tw_partial_then_complete.json`
  - Redacted pair or list of frames showing partial snapshot then complete snapshot.
- Create: `tests/contract/provider_frames/okx_dex_price_info.json`
  - Redacted OKX DEX WS price info payload.
- Create: `tests/contract/provider_frames/okx_dex_search_result.json`
  - Redacted OKX discovery/search response.
- Create: `tests/contract/test_provider_protocol_fixtures.py`
  - Assert GMGN frame parser produces normalized event(s), snapshot gate outcomes, token snapshot identity, and raw frame persistence input.
  - Assert OKX parser maps exact provider fields into `DexMarketFactUpdate` / `DexTokenCandidate`.
  - Assert unknown optional fields are retained only in raw payload, not promoted into business facts without code changes.
- Create: `tests/contract/test_provider_drift_live.py`
  - Skip unless `GMGN_PROVIDER_DRIFT=1`.
  - Fetch a small sample from configured providers without printing secrets.
  - Validate shape against strict parser expectations.
  - Write only a summarized mismatch report to stdout; do not update fixtures automatically.

### Complete Hot Path E2E

- Create: `tests/support/fake_providers.py`
  - `FakeGmgnUpstreamClient`: emits captured frame fixtures into `CollectorService.handle_frame`.
  - `FakeDexQuoteProvider`: deterministic DEX quote/profile/search behavior.
  - `FakeCexQuoteProvider`: deterministic CEX ticker behavior.
  - `FakePulseDecisionProvider`: deterministic decision response without LLM network.
  - `RecordingNotificationProvider`: captures outbound delivery attempts in memory or DB-backed log channel.
- Create: `tests/support/db_seeds.py`
  - Helpers for current facts only: `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_evidence/current`, `market_ticks`, `enriched_events`, `token_radar_rows`, `pulse_agent_jobs`.
  - No helpers for old `price_observations`, old asset registry symbol/name/decimals fields, or old fallback payloads.
- Create: `tests/e2e/test_backend_hot_path.py`
  - Start app/runtime with real test PostgreSQL and fake providers.
  - Feed one GMGN public WS frame.
  - Run bounded worker convergence loop.
  - Assert DB facts: raw frame, event, token intent, resolution, market tick, enriched event.
  - Assert read models: token radar row, pulse candidate/job/run, notification row/delivery row when route policy triggers.
  - Assert HTTP: `/readyz`, `/api/recent`, token radar endpoint, signal pulse endpoint.
  - Assert WS: replay includes event, live market update only for subscribed target, notification only for subscribed channel.
  - Assert no correctness dependency on `NOTIFY`: disable wake emission or skip manual wake and rely on bounded run loop.

## PR Breakdown

1. **PR 1 — Test Lane Governance**
   - Files: `docs/TESTING.md`, `docs/WORKFLOW.md`, `Makefile`, `tests/architecture/test_test_lane_contracts.py`, `tests/architecture/test_harness_structure.py`.
   - Outcome: directory and skip rules are executable.
   - Verify: `uv run pytest tests/architecture/test_test_lane_contracts.py tests/architecture/test_harness_structure.py -q`.

2. **PR 2 — Remove Obsolete Test Debt**
   - Files: generated audit doc, loose plan move, root test moves, skipped integration rewrites/deletions.
   - Outcome: no root tests, no pre-hard-cut skipped business tests.
   - Verify: `rg '@pytest.mark.skip|pytest.skip|GMGN_PROD_POSTGRES_DSN|_source_rows' tests`.

3. **PR 3 — Worker Runtime Semantics**
   - Files: new worker missed-wake/advisory-lock/idempotent-wake tests, minimal source fixes if tests expose false metrics/wake behavior.
   - Outcome: worker correctness no longer relies on delivered `NOTIFY`.
   - Verify: `uv run pytest tests/integration/test_worker_missed_wake_recovery.py tests/integration/test_worker_advisory_lock_single_writer.py tests/integration/test_market_tick_wake_idempotency.py -q`.

4. **PR 4 — Provider Protocol Contracts**
   - Files: `tests/contract/provider_frames/*`, `tests/contract/test_provider_protocol_fixtures.py`, `tests/contract/test_provider_drift_live.py`.
   - Outcome: provider drift is caught by strict fixture contracts and optional live checks.
   - Verify: `uv run pytest tests/contract -q` and optional `GMGN_PROVIDER_DRIFT=1 uv run pytest tests/contract/test_provider_drift_live.py -q`.

5. **PR 5 — Complete Backend Hot Path**
   - Files: `tests/support/*`, `tests/e2e/test_backend_hot_path.py`, any necessary e2e fixtures.
   - Outcome: one deterministic end-to-end path proves collector -> facts -> market workers -> radar -> pulse -> notifications -> HTTP/WS.
   - Verify: `uv run pytest tests/e2e tests/golden -q`.

6. **PR 6 — Final Gate And Documentation**
   - Files: verification artifact under `docs/superpowers/plans/active/` or move plan to completed with verification.
   - Outcome: `make check-all` is trustworthy and documented.
   - Verify: `make check-all`.

## Detailed Tasks

### Task 1: Add Test Lane Contract Guard

**Files:**
- Create: `tests/architecture/test_test_lane_contracts.py`
- Modify: `docs/TESTING.md`
- Modify: `Makefile`

- [ ] Write `test_no_root_pytest_files()` that fails if any `tests/test_*.py` exists.
- [ ] Write `test_unit_tests_do_not_reference_live_dsns()` that scans `tests/unit/**/*.py` for `GMGN_PROD_POSTGRES_DSN`, `GMGN_TEST_POSTGRES_DSN`, and `connect_postgres_test`.
- [ ] Write `test_business_skips_are_not_left_in_place()` that fails for `@pytest.mark.skip` and `pytest.skip(` outside allowlisted environment fixtures:
  - `tests/integration/conftest.py`
  - `tests/e2e/conftest.py`
  - `tests/postgres_test_utils.py`
  - `tests/contract/test_provider_drift_live.py`
- [ ] Write `test_integration_tests_do_not_use_fake_runtime_repositories()` that scans `tests/integration/**/*.py` for `FakeRuntime`, `FakeRepository`, and `without_postgres`; allow only files moved to unit/contract.
- [ ] Run: `uv run pytest tests/architecture/test_test_lane_contracts.py -q`.
- [ ] Expected before cleanup: failures naming root tests, skipped tests, fake integration offenders.
- [ ] Update `docs/TESTING.md` with the lane definitions and no-business-skip rule.
- [ ] Update `Makefile` so `test-e2e` includes golden coverage or `check-all` calls a new `test-golden` target.

### Task 2: Clean Existing Governance Red

**Files:**
- Modify: `docs/generated/backend-architecture-audit-2026-05-17.md`
- Move: `docs/superpowers/plans/2026-05-18-event-anchor-backfill-decoupling-plan-cn.md`

- [ ] Move the loose plan file into `docs/superpowers/plans/active/`.
- [ ] Remove or regenerate stale generated audit text that mentions `price_observations`.
- [ ] Run: `uv run pytest tests/architecture/test_event_anchor_capture_redesign_contracts.py::test_old_price_observation_runtime_is_removed tests/architecture/test_harness_structure.py::test_lane_roots_have_no_loose_files -q`.
- [ ] Expected after cleanup: both tests pass.

### Task 3: Move Root Tests Into Lanes

**Files:**
- Move: `tests/test_factor_snapshot.py` -> `tests/unit/test_factor_snapshot.py`
- Move: `tests/test_no_factor_snapshot_fallback.py` -> `tests/architecture/test_no_factor_snapshot_fallback.py`
- Move: `tests/test_okx_dex_ws_client.py` -> `tests/unit/test_okx_dex_ws_client.py`
- Move: `tests/test_pulse_decision_agent_client.py` -> `tests/unit/test_pulse_decision_agent_client.py`

- [ ] Move each file with `git mv`.
- [ ] Update any imports or pytest node references in docs/plans if they point to old paths.
- [ ] Run moved tests directly:
  - `uv run pytest tests/unit/test_factor_snapshot.py -q`
  - `uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py -q`
  - `uv run pytest tests/unit/test_okx_dex_ws_client.py -q`
  - `uv run pytest tests/unit/test_pulse_decision_agent_client.py -q`
- [ ] Run: `uv run pytest tests/architecture/test_test_lane_contracts.py::test_no_root_pytest_files -q`.
- [ ] Expected: no root `tests/test_*.py` offenders.

### Task 4: Rewrite Pre-Hard-Cut Integration Skips

**Files:**
- Modify: `tests/integration/test_resolution_refresh_worker.py`
- Modify: `tests/integration/test_enrichment_worker.py`
- Modify: `tests/integration/test_enrichment_repository.py`
- Modify: `tests/integration/test_harness_ops.py`
- Modify: `docs/TECH_DEBT.md`

- [ ] Replace old registry symbol/name/decimals fixtures with current identity evidence/current seed helpers.
- [ ] Replace skipped `pass` harness test with a real market-ready snapshot test.
- [ ] Delete tech debt rows that only justify skipped tests after the tests are rewritten.
- [ ] Run each rewritten file:
  - `uv run pytest tests/integration/test_resolution_refresh_worker.py -q`
  - `uv run pytest tests/integration/test_enrichment_worker.py -q`
  - `uv run pytest tests/integration/test_enrichment_repository.py -q`
  - `uv run pytest tests/integration/test_harness_ops.py -q`
- [ ] Run: `rg '@pytest.mark.skip|pytest.skip' tests/integration tests/unit`.
- [ ] Expected: only environment skip locations remain.

### Task 5: Promote Token Radar Idempotency To Real Integration

**Files:**
- Move: `tests/unit/test_token_radar_idempotency.py` -> `tests/integration/test_token_radar_idempotency.py`
- Modify: test body to seed current facts and call real projection path.

- [ ] Remove `GMGN_PROD_POSTGRES_DSN` support.
- [ ] Remove monkeypatch of `_source_rows`.
- [ ] Seed source facts through repositories in a disposable PostgreSQL database.
- [ ] Run `TokenRadarProjectionWorker.rebuild_once()` twice with the same `now_ms`.
- [ ] Assert `token_radar_rows` latest result is stable and no duplicate active rows are introduced.
- [ ] Run: `uv run pytest tests/integration/test_token_radar_idempotency.py -q`.

### Task 6: Lock Missed Wake Recovery

**Files:**
- Create: `tests/integration/test_worker_missed_wake_recovery.py`
- Potential source fixes only if test exposes a real correctness bug.

- [ ] Seed a resolved token, identity evidence/current, market tick, and enriched event without calling `WakeBus`.
- [ ] Instantiate `TokenRadarProjectionWorker` with no wake waiter or an inert wake waiter.
- [ ] Run `run_once(now_ms=...)`.
- [ ] Assert `token_radar_projection_coverage.status == "ready"` and expected `token_radar_rows` exist.
- [ ] Seed `token_radar_rows` without calling `notify_token_radar_updated`.
- [ ] Run `PulseCandidateWorker.run_once_async(now_ms=...)` with fake decision provider.
- [ ] Assert due pulse work is scanned from DB state.
- [ ] Run: `uv run pytest tests/integration/test_worker_missed_wake_recovery.py -q`.

### Task 7: Lock Advisory-Lock Single Writer

**Files:**
- Create: `tests/integration/test_worker_advisory_lock_single_writer.py`

- [ ] Use real `DBPoolBundle.acquire_advisory_lock_connection()` against test PostgreSQL.
- [ ] Acquire the same advisory key twice from two worker instances.
- [ ] Assert the second worker reports `WorkerResult(skipped=1, notes.reason="advisory_lock_unavailable")`.
- [ ] Release the first lock.
- [ ] Assert the second worker can acquire and process after release.
- [ ] Run: `uv run pytest tests/integration/test_worker_advisory_lock_single_writer.py -q`.

### Task 8: Lock Market Tick Idempotency And Wake Noise

**Files:**
- Create: `tests/integration/test_market_tick_wake_idempotency.py`
- Potentially modify: `src/parallax/domains/asset_market/repositories/market_tick_repository.py`
- Potentially modify: `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py`
- Potentially modify: `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py`
- Potentially modify: `src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py`

- [ ] Write failing test proving duplicate deterministic ticks do not count as newly inserted.
- [ ] Write failing test proving duplicate ticks do not emit repeated `market_tick_written` wakes.
- [ ] If needed, change repository API to return actual inserted count or inserted tick ids.
- [ ] If needed, change workers to emit wake only for actual inserted/coalesced changed targets.
- [ ] Run: `uv run pytest tests/integration/test_market_tick_wake_idempotency.py tests/unit/test_market_tick_repository.py tests/unit/test_market_tick_poll_worker.py tests/unit/test_market_tick_stream_worker.py tests/unit/test_event_anchor_backfill_worker.py -q`.

### Task 9: Parse Worker Inventory Semantics

**Files:**
- Create: `tests/architecture/test_worker_inventory_contract.py`
- Modify: `docs/WORKERS.md` only if the new parser exposes real drift.

- [ ] Parse the Markdown table rows under `<!-- worker-inventory-keys: ... -->`.
- [ ] Assert every `WorkersSettings` key appears exactly once.
- [ ] Assert every `wakes_on` setting appears in the documented wake-in cell.
- [ ] Assert every `WakeBus.notify_*` method appears in at least one documented wake-out cell.
- [ ] Assert documented read-model writes match the single-writer allowlist in `test_worker_runtime_contracts.py`.
- [ ] Run: `uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py -q`.

### Task 10: Add Provider Protocol Fixture Contracts

**Files:**
- Create: `tests/contract/provider_frames/gmgn_public_tw_complete.json`
- Create: `tests/contract/provider_frames/gmgn_public_tw_partial_then_complete.json`
- Create: `tests/contract/provider_frames/okx_dex_price_info.json`
- Create: `tests/contract/provider_frames/okx_dex_search_result.json`
- Create: `tests/contract/test_provider_protocol_fixtures.py`
- Create: `tests/contract/test_provider_drift_live.py`

- [ ] Add redacted provider fixtures with no secrets, tokens, or private account identifiers.
- [ ] Test GMGN parser output: frame accepted, raw frame persist input exists, snapshot gate outcome correct, event normalized.
- [ ] Test OKX WS parser output: price, liquidity, market cap, holders, observed time, raw payload retained.
- [ ] Test OKX discovery parser output: chain/address/symbol/name/profile fields map to current provider candidate type.
- [ ] Add live drift test guarded by `GMGN_PROVIDER_DRIFT=1`.
- [ ] Run: `uv run pytest tests/contract/test_provider_protocol_fixtures.py -q`.
- [ ] Optional manual command: `GMGN_PROVIDER_DRIFT=1 uv run pytest tests/contract/test_provider_drift_live.py -q`.

### Task 11: Add Complete Backend Hot Path E2E

**Files:**
- Create: `tests/support/fake_providers.py`
- Create: `tests/support/db_seeds.py`
- Create: `tests/support/hot_path_runtime.py`
- Create: `tests/e2e/test_backend_hot_path.py`
- Modify: `tests/e2e/conftest.py` if shared runtime fixture is needed.

- [ ] Build fake providers that implement the current provider protocols without network.
- [ ] Bootstrap runtime against test PostgreSQL with fake providers and fake Pulse decision provider.
- [ ] Feed a captured GMGN frame through `CollectorService.handle_frame`.
- [ ] Run bounded worker convergence: market tick stream/poll or backfill, token radar projection, pulse candidate, notification rule/delivery.
- [ ] Assert DB facts and read models at each step.
- [ ] Assert HTTP endpoints read the resulting state.
- [ ] Assert WS replay/subscription behavior for event, live market update, and notification.
- [ ] Run: `uv run pytest tests/e2e/test_backend_hot_path.py -q`.

### Task 12: Final Verification And Documentation

**Files:**
- Modify: `docs/TESTING.md`
- Modify: this plan or create verification artifact under `docs/superpowers/plans/active/`.
- Modify: `docs/TECH_DEBT.md` only for real remaining risks.

- [ ] Run: `uv run pytest --collect-only -q`.
- [ ] Run: `uv run ruff check .`.
- [ ] Run: `uv run ruff format --check .`.
- [ ] Run: `uv run mypy src`.
- [ ] Run: `make check-all`.
- [ ] Run: `rg '@pytest.mark.skip|pytest.skip|GMGN_PROD_POSTGRES_DSN|_source_rows|FakeRuntime|FakeRepository|without_postgres' tests`.
- [ ] Record full verification output, skipped-test count, coverage, and e2e/golden result.
- [ ] Move this plan to `docs/superpowers/plans/completed/` only after verification is recorded.

## Acceptance Criteria

- AC1: `find tests -maxdepth 1 -name 'test_*.py'` returns no files.
- AC2: `rg '@pytest.mark.skip|pytest.skip' tests` returns only environment skip locations explicitly allowlisted in architecture tests.
- AC3: `rg 'GMGN_PROD_POSTGRES_DSN|_source_rows' tests` returns no matches.
- AC4: `uv run pytest tests/architecture -q` passes.
- AC5: `uv run pytest tests/contract -q` passes using captured provider fixtures.
- AC6: `uv run pytest tests/integration/test_worker_missed_wake_recovery.py tests/integration/test_worker_advisory_lock_single_writer.py -q` passes.
- AC7: `uv run pytest tests/e2e/test_backend_hot_path.py tests/golden -q` passes.
- AC8: `make check-all` exits 0 and its output is recorded in verification.
- AC9: No production code added for old schema or old payload compatibility.

## Rollback

This is a hard-cut test-system change. Rollback should revert the plan PRs in reverse order, not reintroduce old runtime behavior:

1. Revert hot-path e2e if it blocks unrelated emergency work.
2. Revert provider contract fixtures only with a replacement fixture strategy.
3. Revert lane guards only if they are proven wrong; do not restore root tests or business skips.
4. Never rollback by adding production compatibility code for old fields.

## Review Checklist

- Does every kept test state which production semantic it locks?
- Does every integration test use real PostgreSQL for storage/query behavior?
- Are all fake providers scoped to unit/contract/e2e test harnesses?
- Does full hot path prove correctness without relying on delivered `NOTIFY`?
- Does provider drift testing detect schema changes without requiring live network in CI?
- Are old hard-cut names absent from runtime tests except historical migration allowlists?
