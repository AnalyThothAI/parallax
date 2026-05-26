# Runtime Worker Constraint Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented through Phase 9 for listed runtime scope; Phase 10 Docker/live verification pending  
**Date:** 2026-05-25  
**Owning spec:** `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`  
**Recommended worktree:** `.worktrees/runtime-worker-constraint-hard-cut`  
**Recommended branch:** `codex/runtime-worker-constraint-hard-cut`

**Goal:** Turn every listed runtime broad-scan worker into an explicit control-plane consumer: dirty target or leased job claim first, exact target payload load second, no fallback scan path.

**Architecture:** Keep facts as business truth and move runtime work discovery into durable control-plane tables. Producers enqueue target rows in the same transaction as the fact/read-model mutation that creates downstream work. Workers claim leased targets with stale-completion protection, process only those exact targets, and expose idle-cost counters. Bounded ops repair owns historical discovery; runtime code does not.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3, existing `WorkerBase` runtime, domain repositories, pytest architecture/unit/integration tests, Docker Compose live verification.

## Driver Pass 1 Progress — 2026-05-25

- Landed Phase 0 brief-tail fixes and Phase 1 architecture guardrails.
- Landed Phase 2 `pulse_candidate` dirty-trigger control plane, including same-transaction Token Radar enqueue, claim-first worker processing, bounded repair, and matched/all scope coverage.
- Landed Phase 3 `narrative_admission` control plane, including admission and discussion digest dirty target tables, same-transaction Token Radar enqueue, target-scoped stale handling, bounded repair, and deletion of the old production broad frontier methods.
- Fixed re-review blockers found by subagents: explicit worker transactions, per-target savepoints, stale completion protection, no claim metadata fallback, incomplete dirty target fail-fast, Pulse `matched` support, and transactional Pulse side effects.
- Not complete yet: Phase 4 `mention_semantics`, Phase 5 `token_discussion_digest`, Phase 6 asset-market/profile/image/capture/live workers, Phase 7 generalized repair hardening, Phase 8 diagnostics/tail-worker constraints, Phase 9 docs, and Phase 10 live verification.

Verification from this pass:

- `uv run ruff check src/gmgn_twitter_intel tests` — passed.
- Narrative targeted integration set — `8 passed`.
- Runtime worker hard-cut focused regression — `231 passed`.
- Pulse dirty-trigger regression — `91 passed`.
- Projection/narrative worker/architecture targeted regression after import cleanup — `186 passed`.
- `git diff --check` — passed.
- `rg` over converted runtime files found no `latest_current_rows`, `admitted_radar_rows`, `admissions_for_window_scope`, `delete_admissions_outside_frontier`, `fallback_scan`, `compat`, `audit loop`, or `catch-up scan`.

Known verification caveat:

- Full `tests/architecture -q` still fails on pre-existing architecture debt outside this pass, plus the expected active-plan tail that is not yet converted. The new cross-domain import introduced in pass 1 was removed by exporting `NARRATIVE_SCHEMA_VERSION` through `narrative_intel.interfaces`; remaining cross-domain offenders are existing `pulse_policy_evaluator` and `evidence/asset_market` imports.

## Driver Pass 2 Progress — 2026-05-26

- Landed Phase 4 `mention_semantics` hard cut: runtime no longer scans admissions or missing source rows; it claims leased `token_mention_semantics` rows first, releases no-start backpressure without burning attempts, and completes rows with `semantic_id` + `text_fingerprint` + `lease_owner` + `attempt_count`.
- Landed Phase 5 `token_discussion_digest` runtime hard cut: worker now claims `discussion_digest_dirty_targets`, filters unsupported windows/scopes at claim time, exact-loads only claimed targets, and reschedules/error-completes dirty rows with claim completion tokens.
- Closed the Phase 5 semantics -> digest data-flow edge: semantic completion now enqueues affected discussion digest dirty targets in the same repository transaction as model-run and semantic-row completion.
- Added `discussion_digest` to bounded ops repair (`enqueue-runtime-worker-dirty-targets --work discussion_digest`) so historical digest targets are repaired through control rows, not by running the worker or calling providers.
- Extended architecture enforcement so `mention_semantics` and `token_discussion_digest` are now checked converted workers, and changed `token_discussion_digest` classification to `dirty_target_consumer`.

Verification from this pass:

- `uv run ruff check src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py src/gmgn_twitter_intel/app/ops/runtime_worker_dirty_targets.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/integration/test_narrative_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/test_ops_runtime_worker_dirty_targets.py tests/unit/test_cli.py` — passed.
- `uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q` — `36 passed`.
- `uv run pytest tests/integration/test_narrative_repository.py::test_repository_enqueues_completes_and_hydrates_semantics -q` — `1 passed`.
- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py -q` — `16 passed`.
- `uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py -q` — `9 passed`.
- `uv run pytest tests/integration/test_narrative_admission_dirty_targets.py -q` — `4 passed`.
- `uv run pytest tests/unit/test_ops_runtime_worker_dirty_targets.py tests/unit/test_cli.py::test_ops_enqueue_runtime_worker_dirty_targets_parser_accepts_discussion_digest_work tests/unit/test_cli.py::test_ops_enqueue_runtime_worker_dirty_targets_parser_accepts_narrative_admission_work tests/unit/test_cli.py::test_ops_enqueue_runtime_worker_dirty_targets_parser_defaults_to_dry_run -q` — `17 passed`.

Remaining after this pass:

- Phase 5.2 market-threshold enqueue edge remains tied to the asset-market/market-tick producer path and should be handled with Phase 6 rather than adding a broad digest wake scan.
- Phase 6 asset-market/profile/image/capture/live workers, Phase 7 generalized repair hardening, Phase 8 diagnostics/tail-worker constraints, Phase 9 docs, and Phase 10 live verification remain open.

## Driver Pass 3 Progress — 2026-05-26

- Landed Phase 6 asset-market hard cuts: `token_profile_current`, `token_image_mirror`, `asset_profile_refresh`, and `token_capture_tier` now claim dirty/control rows before exact payload load or provider work. `live_price_gateway` now reads the bounded live target set from `token_capture_tier`.
- Removed old runtime compatibility/discovery entrypoints rather than keeping wrappers: `recent_profile_targets`, `candidate_sources`, `PendingAssetProfileQuery`, `select_due_asset_profile_rows`, `active_live_market_targets`, and `demote_absent_hot_rows`.
- Extended bounded ops repair for `profile_current`, `image_source`, `asset_profile_refresh`, `capture_tier`, and `live_market_targets`. The command remains dry-run by default, refuses unbounded selectors, enqueues dirty targets only, and never calls providers/agents/workers.
- Landed Phase 8 tail constraints: `handle_summary` no longer reconciles missing jobs in runtime and is now enforced as a leased-job consumer; `cex_oi_radar_board` and `macro_view_projection` expose compact cost counters; worker status compacts large `last_result.notes`.
- Updated architecture and operator docs for the new control-plane queues and no-fallback runtime shape.

Verification from this pass:

- Phase 6 targeted regression — `63 passed`.
- No-compat cleanup targeted regression — `14 passed`.
- Runtime repair/CLI targeted regression — `21 passed`.
- Tail-worker/diagnostics targeted regression — `68 passed`.
- Watchlist hard-cut/architecture targeted regression — `68 passed`.
- Focused ruff checks for touched worker, repair, CLI, docs-test, and architecture files — passed.

Remaining after this pass:

- Phase 10 full-suite and Docker/live verification still need to run against the local runtime/database.

---

## Spec Review Coverage

- [ ] **Lines 16-25: Kappa/CQRS background and local brief fix**
  - Implementation binding: use `news_projection_dirty_targets` / `equity_projection_dirty_targets` and `market_tick_current_dirty_targets` as the pattern, not a new generic queue framework.
  - Plan binding: Phase 0 fixes the remaining test tail from the `brief_input` hard cut before starting new families.

- [ ] **Lines 27-30: Remaining broad-scan worker list**
  - Implementation binding: every named worker gets an explicit migration/repository/producer/worker/test task.
  - Plan binding: P0 covers `pulse_candidate`, `narrative_admission`, `mention_semantics`; P1 covers `token_discussion_digest`, `token_profile_current`, `token_image_mirror`, `asset_profile_refresh`, `token_capture_tier`; P2 covers diagnostics/readiness.

- [ ] **Lines 34-48: Idle-cost problem is architectural**
  - Implementation binding: do not tune intervals/concurrency as the fix.
  - Plan binding: architecture tests assert no converted worker uses broad discovery in `run_once()`.

- [ ] **Lines 52-63: Runtime discovery is mixed with payload loading and repair**
  - Implementation binding: split each family into:
    - producer enqueue;
    - dirty target repository claim/mark;
    - exact payload loader;
    - bounded ops repair.
  - Plan binding: every family task explicitly deletes the old mixed broad method after the worker no longer calls it.

- [ ] **Lines 67-78: First principles**
  - Implementation binding: control-plane rows are never product truth; missed enqueue is repaired by ops, not hidden runtime scans.
  - Plan binding: no-work tests inspect query paths/counters and require `claimed=0`, `source_rows_scanned=0`, and `targets_loaded=0`.

- [ ] **Lines 80-101: Required runtime shape**
  - Implementation binding: claim due target with lease before exact payload SQL; no source fact/read-model queries on empty queue.
  - Plan binding: repository tests verify `FOR UPDATE SKIP LOCKED` or atomic `UPDATE ... RETURNING`; worker unit tests verify empty queues do not call payload loaders.

- [ ] **Lines 103-130: Hard constraints C1-C10**
  - Implementation binding: C1/C7/C8/C9 become architecture tests; C2/C5/C6 become repository and worker unit tests; C3/C4 become producer integration tests; C10 becomes worker result notes.
  - Plan binding: `tests/architecture/test_runtime_worker_constraint_hard_cut.py` is the cross-family gate.

- [ ] **Lines 132-146: No compatibility code**
  - Implementation binding: delete old runtime scan methods or move bounded scans to ops-only modules with architecture allowlist.
  - Plan binding: no flags, no fallback calls, no low-frequency audit loop, no dual-read compatibility.

- [ ] **Lines 148-174: Business capability impact and primary risk**
  - Implementation binding: public contracts, scoring, prompts, output schemas, and ledgers stay unchanged.
  - Plan binding: existing product tests must keep passing; new tests focus on enqueue coverage so missed producers are caught before production.

- [ ] **Lines 178-287: Target families**
  - Implementation binding: each target family has its own section below with table shape, producer edges, worker hard cut, repair, and tests.

- [ ] **Lines 288-298: Diagnostics/readiness**
  - Implementation binding: `/readyz` and worker notes expose compact counters only; expensive aggregate diagnostics move to ops commands.

- [ ] **Lines 300-323: Control-plane model**
  - Implementation binding: new tables use the standard dirty target fields unless an existing job table is already equivalent.
  - Plan binding: completion token must include key, payload hash, lease owner, and attempt count.

- [ ] **Lines 325-338: Repair command requirements**
  - Implementation binding: every converted domain exposes bounded enqueue-only repair.
  - Plan binding: repair commands are dry-run by default and refuse unbounded agent/LLM work.

- [ ] **Lines 340-350: Architecture tests**
  - Implementation binding: tests ban old broad method names in runtime and allow scans only in explicit ops repair.

- [ ] **Lines 352-372: Acceptance criteria**
  - Implementation binding: each phase has a verification checklist tied to AC1-AC10.

- [ ] **Lines 374-389: Verification plan**
  - Implementation binding: red tests first, then migrations/repositories/producers/workers/deletion/repair/tests/live checks.

- [ ] **Lines 390-395: Completion bar**
  - Implementation binding: do not call the whole system root-fixed until P0 and P1 are complete and live idle SQL no longer shows converted-domain scans.

---

## Source Audit Corrections

Parallel source audit on 2026-05-25 found several plan gaps that must be treated as implementation requirements, not optional follow-ups:

- [ ] The plan must be registry-aware. In addition to the eight spec examples, classify every worker in `src/gmgn_twitter_intel/app/runtime/worker_registry.py` as one of:
  - dirty-target/leased-job consumer;
  - bounded provider/source scheduler with documented finite universe and explicit limits;
  - target-scoped expansion from already claimed/changed ids;
  - candidate for this hard cut.
- [ ] `live_price_gateway` is not exempt. It currently calls `active_live_market_targets` every cycle and must move with `token_capture_tier` into the live-market target control plane.
- [ ] `handle_summary`, `cex_oi_radar_board`, and `macro_view_projection` are not part of the immediate P0 root-fix path, but Phase 1 must classify them explicitly and add architecture tests so they cannot hide unbounded runtime discovery.
- [ ] Phase 3 cannot enqueue digest targets before the digest dirty table/repository exists. Create narrative admission, mention semantics lease columns, and discussion digest dirty targets in the first narrative-control migration before hard-cutting admission.
- [ ] Token Radar producers must enqueue downstream work for `entered`, `changed`, `exited`, `frontier_rank_changed`, `visibility_changed`, and source watermark changes. A plan that only enqueues on current-row upsert will preserve CPU while losing business updates.
- [ ] `token_capture_tier` cannot be converted to exact-target projection. Its business semantics are global top-N/rank-set allocation, so the hard cut must use dirty triggers to recompute bounded rank sets or partitions, not single-target independent tier assignment.
- [ ] Capacity/backpressure deferral is not business suppression. Dirty targets deferred because of queue budgets, provider capacity, or LLM capacity must be released/rescheduled, not marked done.
- [ ] Digest epoch deferral is a scheduled future due state. It must reschedule a dirty/control row with `due_at_ms`, not simply mark the target done.
- [ ] `token_image_assets` may be reused as the image-source job table only if it gains equivalent lease owner, attempt count, payload/source hash, and stale-completion protection. Otherwise create `token_image_source_dirty_targets`.
- [ ] Repair execution must be harder than "bounded by window/scope". Agent-adjacent repairs require explicit `--execute`, `--limit`, queue-depth checks, downstream backlog checks, and a capped `--since-hours` unless target ids are supplied.

---

## Non-Negotiables

- [ ] No runtime compatibility flag such as `use_dirty_targets`, `enable_old_scan`, or `fallback_scan_on_empty_queue`.
- [ ] No worker fallback from empty queue to historical discovery.
- [ ] No periodic audit loop inside runtime workers.
- [ ] No provider/agent call before durable claim or explicit capacity reservation.
- [ ] No source-fact scan in `NOTIFY` handlers.
- [ ] No old broad-scan method left reachable from converted `runtime/*.py` files.
- [ ] Bounded ops repair may scan facts, but it must enqueue dirty targets only.

## Standard Dirty Target Contract

Every new dirty-target table in this plan must follow this contract unless the section explicitly says it is a scheduled partition table or an existing durable job table with equivalent semantics:

- [ ] Lower numeric `priority` means more urgent. Repositories use `priority ASC`, `due_at_ms ASC`, and `updated_at_ms ASC`; conflict updates use `priority = LEAST(existing.priority, incoming.priority)`.
- [ ] Standard fields are required: `dirty_reason`, `payload_hash`, `source_watermark_ms`, `priority`, `due_at_ms`, `leased_until_ms`, `lease_owner`, `attempt_count`, `last_error`, `first_dirty_at_ms`, and `updated_at_ms`.
- [ ] `attempt_count` is incremented only by claim. It means claim attempts, not provider failures.
- [ ] `mark_done` and `mark_error` use the completion token returned by claim: full key, `payload_hash`, `lease_owner`, and `attempt_count`.
- [ ] Standard dirty queues do not terminalize by `max_attempts`. Terminal states belong in domain job/status tables such as semantic rows, image assets, or Pulse agent jobs.
- [ ] `mark_error` returns an integer row count, releases the lease, writes bounded `last_error`, and sets the next `due_at_ms`.
- [ ] If a claimed target is enqueued again with a newer source watermark or changed payload hash, the lease may be cleared. Identical duplicate enqueue must not churn attempts or leases.
- [ ] Every repository gets tests for duplicate coalescing, lease claim, stale completion, changed-payload lease clearing, and error reschedule.

---

## Phase 0: Baseline And Current Brief Tail

- [ ] **Step 0.1: Confirm worktree and dirty files**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected:

- Branch is known.
- User-owned changes are noted and left untouched.
- The spec file `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md` is present.

- [ ] **Step 0.2: Fix current test expectations from the agent brief hard cut**

Modify:

- `tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py`
- `tests/integration/test_equity_event_workers.py`

Required changes:

- The processing/enqueue test must now expect `("brief_input", "company_event", event_id)` in the same transaction dirty target set.
- The brief worker integration test must seed an `equity_projection_dirty_targets` row with `projection_name="brief_input"` before expecting the worker to process a specific event.
- Do not add a worker fallback to `list_events_for_brief`.

Run:

```bash
uv run pytest \
  tests/unit/domains/equity_event_intel/test_equity_page_projection_dirty_targets.py \
  tests/integration/test_equity_event_workers.py \
  tests/architecture/test_projection_worker_idle_cost_contract.py -q
```

Expected:

- Current brief dirty-target tests pass.
- Architecture still bans `list_items_for_brief` and `list_events_for_brief`.

---

## Phase 1: Shared Guardrails For Converted Runtime Families

- [ ] **Step 1.1: Add cross-family architecture gate**

Create:

- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

The test must inspect runtime files with AST/string guards and fail on these broad discovery calls inside converted worker files:

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - banned after conversion: `latest_current_rows`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
  - banned after conversion: `admitted_radar_rows`, `admissions_for_window_scope`, `delete_admissions_outside_frontier`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
  - banned after conversion: `_enqueue_missing_from_admissions_sync`, `due_admissions_for_semantics`, `missing_source_rows_for_mention_semantics`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - banned after conversion: `due_digest_targets`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_profile_current_worker.py`
  - banned after conversion: `recent_profile_targets`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_image_mirror_worker.py`
  - banned after conversion: `candidate_sources`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`
  - banned after conversion: `select_due_asset_profile_rows`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_capture_tier_worker.py`
  - banned after conversion: `active_live_market_targets`, `demote_absent_hot_rows`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
  - banned after conversion: `active_live_market_targets`
- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
  - banned unless explicitly classified as bounded repair-only: `handles_missing_summary_jobs`, `reconcile_missing_jobs_once`

The same file must also assert:

- converted workers call a `claim_*` or `claim_due` method before exact payload loaders;
- converted workers expose notes keys for `claimed`, `queue_depth` when available, `source_rows_scanned`, `targets_loaded`, and `rows_written`;
- broad scan SQL is allowed only inside the specific `enqueue-runtime-worker-dirty-targets` repair handler or domain `services/*repair*.py`, and that code path must enqueue control rows only.
- repair tests assert the handler does not call any worker `run_once()`, does not call providers/agents, and does not write read-model/business-output tables.

- [ ] **Step 1.2: Extend control-plane table ownership allowlist**

Modify:

- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

Add allowlist entries for the new tables created in Phase 2/3/4/5/6:

- `pulse_trigger_dirty_targets`
- `narrative_admission_dirty_targets`
- `discussion_digest_dirty_targets`
- `token_profile_current_dirty_targets`
- `token_image_source_dirty_targets`
- `asset_profile_refresh_targets`
- `token_capture_tier_dirty_targets`
- `token_radar_dirty_targets`
- `watchlist_handle_summary_jobs`

Expected:

- SQL writes to those tables are owned by their repository and migration files only.
- Runtime workers consume through repositories, not inline SQL.

- [ ] **Step 1.3: Add registry-wide worker classification gate**

Create or extend:

- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `tests/architecture/test_worker_runtime_contracts.py`

Required classification source:

- `src/gmgn_twitter_intel/app/runtime/worker_registry.py`

The test must fail when a registered worker is not classified. Initial classification must include:

- `market_tick_current_projection`, `resolution_refresh`, `news_*_projection`, `equity_event_*_projection`, `news_item_brief`, `equity_event_brief`, `event_anchor_backfill`, `enrichment`, `notification_delivery`: already claim durable dirty/job/control rows before expensive payload/provider work.
- `pulse_candidate`, `narrative_admission`, `mention_semantics`, `token_discussion_digest`, `token_profile_current`, `token_image_mirror`, `asset_profile_refresh`, `token_capture_tier`, `live_price_gateway`: converted by this plan.
- `market_tick_stream`, `market_tick_poll`: bounded consumers of `token_capture_tier`; keep as control-plane tier consumers.
- `handle_summary`: agent-adjacent broad reconcile risk; convert or explicitly move reconcile to bounded ops repair in Phase 8.
- `cex_oi_radar_board`, `macro_view_projection`: scheduled snapshot/projection workers; document finite universe/limit and add idle-cost counters, or split into bounded scheduler partitions if source size grows.

- [ ] **Step 1.4: Add standard dirty target test helpers**

Create only if duplication becomes significant:

- `tests/helpers/dirty_target_contract.py`

Required helper behavior:

- Seed one target.
- Claim it with a lease owner.
- Verify duplicate enqueue with same payload coalesces.
- Verify changed payload/source watermark clears stale lease.
- Verify stale completion cannot delete changed payload.
- Verify `mark_error` reschedules with bounded cooldown and terminal max-attempt behavior where relevant.

Do not create a production abstraction unless the implementation proves the repositories are diverging in unsafe ways. Prefer the existing local repository pattern from:

- `src/gmgn_twitter_intel/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`

Run:

```bash
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected:

- The new architecture test is red until each phase removes the corresponding broad scan.

---

## Phase 2: P0 Pulse Candidate Trigger Discovery

- [ ] **Step 2.1: Add Pulse trigger dirty target table**

Create migration:

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py`

Add table:

- `pulse_trigger_dirty_targets`

Columns:

- `target_type text not null`
- `target_id text not null`
- `window text not null`
- `scope text not null`
- `dirty_reason text not null`
- `payload_hash text not null`
- `source_watermark_ms bigint not null default 0`
- `priority integer not null default 100`
- `due_at_ms bigint not null`
- `leased_until_ms bigint`
- `lease_owner text`
- `attempt_count integer not null default 0`
- `last_error text`
- `first_dirty_at_ms bigint not null`
- `updated_at_ms bigint not null`

Indexes and constraints:

- Primary key: `(target_type, target_id, window, scope)`
- Due index: `(priority, due_at_ms, updated_at_ms)` or `(due_at_ms, priority, updated_at_ms)` only if the query still orders by `priority ASC, due_at_ms ASC`.
- Lease index: `(leased_until_ms)` where leased.
- `attempt_count >= 0`.

- [ ] **Step 2.2: Add Pulse trigger repository**

Create:

- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/__init__.py`
- `tests/architecture/test_worker_runtime_contracts.py`

Required repository methods:

- `enqueue_targets(targets, reason, now_ms, due_at_ms=None, commit=True) -> dict[str, int]`
- `claim_due(now_ms, limit, lease_owner, lease_ms) -> list[dict[str, Any]]`
- `mark_done(claims, now_ms, commit=True) -> int`
- `mark_error(claims, error, now_ms, retry_ms, commit=True) -> int`
- `reschedule(claims, due_at_ms, now_ms, reason=None, commit=True) -> int`
- `queue_depth(now_ms) -> int | dict[str, int]`

Claim must use `FOR UPDATE SKIP LOCKED` or atomic `UPDATE ... RETURNING` and return:

- full target key;
- `payload_hash`;
- `lease_owner`;
- `attempt_count`;
- `source_watermark_ms`;
- `dirty_reason`.

- [ ] **Step 2.3: Enqueue Pulse triggers from Token Radar projection writes**

Modify likely write edges:

- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`

Required behavior:

- When Token Radar publishes a target/window/scope `entered`, `changed`, `exited`, `rank_changed`, `visibility_changed`, or source-watermark change, enqueue `pulse_trigger_dirty_targets` in the same transaction.
- Payload hash must include the trigger signature used by Pulse admission: target key, window, scope, rank score, edge state, visibility/exit state, factor snapshot hash, source event ids or source fingerprint, and source watermark.
- Enqueue windows/scopes from the material Token Radar change set, filtered by product-supported Pulse windows/scopes, not by reading worker runtime settings inside repository code. Current product windows remain `1h` and `4h`.
- Exit targets must be enqueued so Pulse admission state and pending trigger decisions can be suppressed or terminalized target-scoped without a later broad scan.
- Duplicate enqueue with unchanged payload hash must not churn leases or attempts.

Tests:

- Add or modify unit tests around Token Radar current row replacement to assert Pulse dirty targets are enqueued in the same transaction.
- Add failure-injection test: current row write rolls back, Pulse trigger enqueue rolls back too.

- [ ] **Step 2.4: Hard-cut `PulseCandidateWorker.scan_triggers_once`**

Modify:

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`

Required behavior:

- Replace `repos.token_radar.latest_current_rows(...)` discovery with `repos.pulse_trigger_dirty_targets.claim_due(...)`.
- If claim returns empty, return notes:
  - `reason="no_due_pulse_triggers"`
  - `claimed=0`
  - `source_rows_scanned=0`
  - `targets_loaded=0`
  - `queue_depth` when practical.
- Load exact target context only for claimed `(target_type, target_id, window, scope)` rows.
- Keep existing `pulse_agent_jobs` claim/execution queue unchanged.
- Mark claimed trigger done only after a business policy decision is recorded, such as `suppressed_by_policy` or job enqueued.
- Capacity, pending-job budget, LLM/provider capacity, and global/window queue budget are not business suppression. They must call `reschedule`/`mark_error` with a bounded cooldown and must not burn Pulse job attempts.
- On provider/agent backpressure before execution start, release/reschedule the trigger without burning Pulse job attempts.
- Do not call `latest_current_rows` anywhere in the worker.

Delete or move to ops-only:

- `TokenRadarRepository.latest_current_rows` if it has no non-runtime bounded use.
- Any test fake that only exists to support broad trigger scans.

- [ ] **Step 2.5: Add Pulse bounded repair**

Modify:

- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`

Add command:

```bash
uv run gmgn-twitter-intel ops enqueue-runtime-worker-dirty-targets \
  --work pulse_trigger \
  --window 1h \
  --scope all \
  --since-hours 4 \
  --dry-run
```

Required guardrails:

- `--work pulse_trigger` is required.
- At least one of `--target-id`, `--since-hours`, or bounded partition selector is required.
- Dry-run by default.
- Reports candidate count and enqueue count.
- Does not enqueue `pulse_agent_jobs`.
- Does not call agents/providers.

- [ ] **Step 2.6: Pulse tests and verification**

Create/modify:

- `tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py`
- `tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py`
- `tests/integration/test_pulse_candidate_dirty_triggers.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

Run:

```bash
uv run pytest \
  tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py \
  tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py \
  tests/integration/test_pulse_candidate_dirty_triggers.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  tests/architecture/test_pulse_no_compat.py -q
```

Expected:

- Empty Pulse trigger queue does not query Token Radar current rows.
- Claimed trigger loads exact context and enqueues/suppresses the existing Pulse job exactly as before.
- `latest_current_rows` is absent from `pulse_candidate_worker.py`.

---

## Phase 3: P0 Narrative Control Plane Foundation And Admission

- [ ] **Step 3.1: Add narrative control-plane tables before hard-cutting admission**

Use the Phase 2 migration if still open; otherwise create one narrative-control migration. Do not split the digest dirty target table into a later phase, because admission processing must enqueue digest targets in the same transaction from the first hard-cut commit.

Add tables:

- `narrative_admission_dirty_targets`
- `discussion_digest_dirty_targets`

Both tables follow the standard dirty target contract with key:

- `(target_type, target_id, window, scope)`

Additional fields:

- `projection_version text not null`
- `schema_version text not null`

Also alter:

- `token_mention_semantics`

Add lease/control fields if missing:

- `leased_until_ms bigint`
- `lease_owner text`
- `attempt_count integer not null default 0`
- `claimed_at_ms bigint`
- `last_error text`

Add due/lease indexes over semantic status and `next_retry_at_ms` or the existing due field.

- [ ] **Step 3.2: Add narrative admission and digest dirty target repositories**

Create:

- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/discussion_digest_dirty_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/__init__.py`

Required methods mirror Phase 2:

- `enqueue_targets`
- `claim_due`
- `mark_done`
- `mark_error`
- `reschedule`
- `queue_depth`

- [ ] **Step 3.3: Enqueue admission targets from source mutations**

Modify producer edges:

- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/intent_resolution_repository.py`
- Any runtime path that mutates target identity/resolution used by narrative admission.

Required behavior:

- Token Radar target/window/scope `entered`, `changed`, `exited`, `frontier_rank_changed`, `visibility_changed`, and source-watermark changes enqueue `narrative_admission_dirty_targets`.
- Resolution updates enqueue the affected target/window/scope dirty targets.
- Enqueue happens inside the same transaction as the mutation.
- Exit targets must be enqueued for targets leaving the admitted frontier, rank threshold, scope, or window coverage.
- No admission work is triggered by `NOTIFY` except waking queue consumers.

- [ ] **Step 3.4: Hard-cut `NarrativeAdmissionWorker`**

Modify:

- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_admission.py`

Required behavior:

- `run_once_sync()` claims `narrative_admission_dirty_targets` first.
- Empty queue returns:
  - `reason="no_due_narrative_admission_targets"`
  - `claimed=0`
  - `source_rows_scanned=0`
  - `targets_loaded=0`
- For each claim, load exact current Radar/admission context by `(target_type, target_id, window, scope)`.
- Recompute source set only for that target.
- Write or mark stale only target-scoped admission rows. Stale behavior must be business-equivalent to the old frontier cleanup for that target:
  - if target is no longer admitted, mark/delete that target's `narrative_admissions` for the window/scope;
  - remove or mark stale current digests for that target/window/scope according to existing public currentness semantics;
  - remove obsolete pending semantics rows for that target only when they no longer belong to a current admission/source set.
- Enqueue mention semantics input rows and discussion digest dirty targets from the same target-scoped processing transaction when admission/source set changes.
- Remove runtime global cleanup through `delete_admissions_outside_frontier`.

Delete or move to bounded ops-only:

- `admitted_radar_rows`
- `admissions_for_window_scope` as a runtime frontier source
- `delete_admissions_outside_frontier` from runtime

- [ ] **Step 3.5: Add explicit narrative admission repair/rebuild**

Modify:

- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`

Add bounded dry-run command shape:

```bash
uv run gmgn-twitter-intel ops enqueue-runtime-worker-dirty-targets \
  --work narrative_admission \
  --window 1h \
  --scope all \
  --since-hours 4 \
  --dry-run
```

Required behavior:

- Scan facts/current rows only for bounded selector.
- Enqueue `narrative_admission_dirty_targets`.
- Do not write `narrative_admissions`.
- Do not delete digests/semantics in repair.

- [ ] **Step 3.6: Narrative admission tests**

Create/modify:

- `tests/unit/domains/narrative_intel/test_narrative_admission_dirty_target_repository.py`
- `tests/unit/domains/narrative_intel/test_narrative_admission_worker_dirty_targets.py`
- `tests/integration/test_narrative_admission_dirty_targets.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

Run:

```bash
uv run pytest \
  tests/unit/domains/narrative_intel/test_narrative_admission_dirty_target_repository.py \
  tests/unit/domains/narrative_intel/test_narrative_admission_worker_dirty_targets.py \
  tests/integration/test_narrative_admission_dirty_targets.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected:

- Empty admission queue does not scan Radar current rows.
- Target-scoped stale/removal behavior matches previous product semantics for the changed target.
- Exit/visibility-loss tests prove stale admissions, digests, and semantics do not remain public.
- Global cleanup is absent from runtime.

---

## Phase 4: P0 Mention Semantics

- [x] **Step 4.1: Convert semantic rows into leased jobs**

Use the narrative-control migration from Phase 3.1. Do not create a second migration unless Phase 3 has already landed.

Alter table:

- `token_mention_semantics`

Add fields if missing:

- `leased_until_ms bigint`
- `lease_owner text`
- `attempt_count integer not null default 0`
- `claimed_at_ms bigint`
- `last_error text`

Migration behavior:

- Initialize `attempt_count` from existing retry state when present.
- Keep historical semantic labels and unavailable rows intact.
- Add due/lease index over status and `next_retry_at_ms` or equivalent due field.

- [x] **Step 4.2: Make semantic enqueue owned by admission processing**

Modify:

- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`

Required behavior:

- Admission target processing writes/enqueues normalized semantic rows for exact source rows.
- The `mention_semantics` worker no longer discovers missing semantic rows from admissions.
- JSON source-set membership is not part of the hot due-claim predicate.

Delete from runtime:

- `_enqueue_missing_from_admissions_sync`
- `_missing_source_rows_for_semantics`
- calls to `due_admissions_for_semantics`
- calls to `missing_source_rows_for_mention_semantics`

- [x] **Step 4.3: Hard-cut semantic claim path**

Modify:

- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`

Required repository method:

- `claim_due_mention_semantics(now_ms, limit, lease_owner, lease_ms, max_per_target, windows, scopes) -> list[dict[str, Any]]`

Required behavior:

- Claim rows with atomic update and lease before provider request.
- Completion uses `semantic_id`, `payload_hash` or `text_fingerprint`, `lease_owner`, and `attempt_count`.
- No-start provider backpressure releases/reschedules rows without incrementing provider attempt budget.
- Provider failure records failure state and reschedules through the leased semantic row. Terminalization after max attempts is a semantic-row state transition such as `semantic_unavailable`; it is not standard dirty-target `mark_error` behavior.
- Successful completion clears lease and writes labels/run audit exactly as before.
- Delete the no-token completion fallback that updates by event/target/text alone, or move it to an explicit ops-only repair path. Normal runtime completion must verify the lease token.
- Worker notes include:
  - `claimed`
  - `source_rows_scanned=0`
  - `targets_loaded`
  - `labeled`
  - `semantic_unavailable`
  - backpressure reason counters.

- [x] **Step 4.4: Mention semantics tests**

Create/modify:

- `tests/unit/domains/narrative_intel/test_mention_semantics_leased_claims.py`
- `tests/unit/domains/narrative_intel/test_mention_semantics_worker_no_admission_scan.py`
- `tests/integration/test_mention_semantics_dirty_inputs.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

Run:

```bash
uv run pytest \
  tests/unit/domains/narrative_intel/test_mention_semantics_leased_claims.py \
  tests/unit/domains/narrative_intel/test_mention_semantics_worker_no_admission_scan.py \
  tests/integration/test_mention_semantics_dirty_inputs.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected:

- Empty semantics queue does not scan admissions.
- Concurrent claims do not double-process the same semantic row.
- No-start backpressure does not burn domain attempts.

---

## Phase 5: P1 Token Discussion Digest

- [x] **Step 5.1: Verify discussion digest dirty target table and repository are already wired**

The table/repository are created in Phase 3.1/3.2 because admission must enqueue digest dirty targets immediately. This step verifies wiring and adds any digest-specific tests that were not covered by admission.

- `discussion_digest_dirty_targets`

Key:

- `(target_type, target_id, window, scope)`

Verify:

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

- [ ] **Step 5.2: Enqueue digest targets from changed inputs**

Driver pass 2 completed the admission/source-set and semantics-completion producer edges. The market-threshold edge remains open and should be implemented with the Phase 6 asset-market/market-tick producer conversion so it stays target-scoped.

Modify:

- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- Market threshold enqueue edge in the asset market/token radar producer path that can change digest freshness.

Required behavior:

- Admission/source set change enqueues digest target.
- Semantics completion enqueues digest target.
- Market changes enqueue digest only when the visible market threshold used by `NarrativeEpochPolicy` can matter.
- High-frequency `market_tick_written` wakes do not run full digest readiness scans.

- [x] **Step 5.3: Hard-cut `TokenDiscussionDigestWorker`**

Modify:

- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`

Required behavior:

- Replace `_due_targets_sync()` broad due admission selection with dirty target claim.
- Exact-load digest context for claimed target only.
- Mark target done when digest/status is written and no scheduled refresh remains due.
- Epoch policy deferral, LLM cycle budget exhaustion, provider backpressure, semantic-pending retry, and TTL refresh must reschedule the dirty/control row with a future `due_at_ms`; do not simply mark done.
- Mark target error/retry on provider failures using claim completion token.
- Empty queue returns `no_due_digest_targets` with zero source scans.
- Remove runtime dependency on `due_digest_targets`.

- [x] **Step 5.4: Digest repair and tests**

Add repair work selector:

- `--work discussion_digest`

Create/modify tests:

- `tests/unit/domains/narrative_intel/test_discussion_digest_dirty_target_repository.py`
- `tests/unit/domains/narrative_intel/test_token_discussion_digest_worker_dirty_targets.py`
- `tests/integration/test_discussion_digest_dirty_targets.py`

Run:

```bash
uv run pytest \
  tests/unit/domains/narrative_intel/test_discussion_digest_dirty_target_repository.py \
  tests/unit/domains/narrative_intel/test_token_discussion_digest_worker_dirty_targets.py \
  tests/integration/test_discussion_digest_dirty_targets.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  tests/architecture/test_worker_runtime_contracts.py -q
```

Expected:

- No digest broad due target scan in runtime.
- Product digest output schemas and prompt behavior are unchanged.

---

## Phase 6: P1 Asset Market Profile, Image, Capture, And Live Target Workers

### Token Profile Current

- [x] **Step 6.1: Add profile current dirty targets**

Add table:

- `token_profile_current_dirty_targets`

Key:

- `(target_type, target_id)`

Create:

- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_profile_current_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/services/token_profile_current_projection.py`
- `src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/cex_token_profile_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_image_asset_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`

Producer edges:

- asset profile ready/missing/error changes;
- CEX token profile changes;
- identity evidence changes that affect exact profile selection;
- token image ready/unsupported changes;
- resolution/visibility/exit changes from Token Radar.

Required behavior:

- Worker claims target ids, loads exact profile sources, writes only when projected payload hash changes.
- If `computed_at_ms` is public-facing freshness, preserve the existing freshness semantics with an explicit `source_updated_at_ms` / payload hash test instead of silently stopping timestamp refreshes.
- Remove `TokenProfileSourceQuery.recent_profile_targets` from runtime.

Tests:

- `tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py`
- `tests/unit/domains/asset_market/test_token_profile_current_worker_dirty_targets.py`

### Token Image Mirror

- [x] **Step 6.2: Convert image source discovery to dirty target enqueue**

Add table or use existing `token_image_assets` as the durable job table only if it is upgraded to equivalent due/lease/completion protection:

- preferred new source table: `token_image_source_dirty_targets`

Create if new table is used:

- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_image_mirror_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/queries/token_image_source_query.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_image_asset_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/cex_token_profile_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py`

Producer edges:

- profile source logo URL created/changed;
- identity evidence exact logo URL created/changed;
- CEX profile logo URL created/changed.

Required behavior:

- Producers upsert image source targets when URLs change.
- Worker claims image source rows directly.
- Equivalent existing-table claim requires `lease_owner`, `attempt_count`, payload/source URL hash, stale-completion checks on `mark_ready`/`mark_error`/`mark_unsupported`, and due/lease indexes.
- Existing terminal states remain terminal unless a new source URL or payload hash is enqueued.
- Remove `TokenImageSourceQuery.candidate_sources` from normal runtime.

Tests:

- `tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py`
- `tests/unit/domains/asset_market/test_token_image_mirror_worker_dirty_sources.py`

### Asset Profile Refresh

- [x] **Step 6.3: Convert profile refresh discovery to provider-scoped targets**

Add table:

- `asset_profile_refresh_targets`

Key:

- `(provider, target_type, target_id)`

Create:

- `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_refresh_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/discovery_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`

Producer edges:

- resolution target becomes refresh-eligible;
- Token Radar visibility/exit changes into or out of the refresh-eligible set;
- bounded ops repair enqueues provider/asset targets.

Required behavior:

- Worker claims provider/asset target before provider call.
- Backoff lives on refresh target or provider source cache row.
- Provider unavailable writes provider-level cooldown or reschedules claimed targets without burning target attempts. Rows not yet attempted remain due or are delayed by the provider cooldown; they must not hot-loop every interval.
- Remove `select_due_asset_profile_rows` as runtime discovery.

Tests:

- `tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py`
- `tests/unit/domains/asset_market/test_asset_profile_refresh_worker_claims_before_provider.py`

### Token Capture Tier And Live Price Gateway

- [x] **Step 6.4: Convert capture tier projection to dirty-triggered rank-set recompute**

Add table:

- `token_capture_tier_dirty_targets`

Key:

- `(work_name, partition_key)` or `(window, scope, partition_key)`

Create:

- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py`

Modify:

- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_capture_tier_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_capture_tier_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py`

Producer edges:

- Token Radar projection material visibility/score changes;
- Token Radar target `entered`, `changed`, `exited`, and rank changes that can affect top-N membership;
- identity/resolution changes that alter `chain_token` or `cex_symbol` mapping;
- bounded ops repair.

Required behavior:

- Worker claims rank-set/partition dirty rows, then recomputes a bounded top-N rank set for the affected market universe.
- Preserve existing business semantics: global ordering by score, Tier 1 `ws_limit`, Tier 2 `poll_limit`, Tier 3 fallback, and OKX DEX Tier 1 eligibility.
- Do not project tiers independently per target; that would change Tier 1/2 competition.
- Demotion is scoped to the recomputed rank set or explicit bounded partition. Full active-target demotion is not a runtime loop; it moves to bounded ops partitions.
- Remove `repos.registry.active_live_market_targets(...)` and `demote_absent_hot_rows(...)` from normal `TokenCaptureTierWorker`.

Tests:

- `tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py`
- `tests/unit/domains/asset_market/test_token_capture_tier_worker_dirty_rank_sets.py`
- tests proving the old and new projection produce identical Tier 1/2/3 assignments for a seeded ranked universe, including exits.

- [x] **Step 6.5: Convert `LivePriceGateway` to consume live-market control rows**

Modify:

- `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/token_capture_tier_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`

Required behavior:

- `LivePriceGateway` no longer calls `active_live_market_targets`.
- It consumes the bounded live target set produced by `token_capture_tier` or a dedicated `live_market_targets_current` read/control table.
- Empty target set returns quickly with `source_rows_scanned=0`.
- Architecture tests ban `active_live_market_targets` in both `token_capture_tier_worker.py` and `live_price_gateway.py`.

Tests:

- `tests/unit/domains/asset_market/test_live_price_gateway_control_targets.py`

### Phase 6 Verification

Run:

```bash
uv run pytest \
  tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py \
  tests/unit/domains/asset_market/test_token_profile_current_worker_dirty_targets.py \
  tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py \
  tests/unit/domains/asset_market/test_token_image_mirror_worker_dirty_sources.py \
  tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py \
  tests/unit/domains/asset_market/test_asset_profile_refresh_worker_claims_before_provider.py \
  tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py \
  tests/unit/domains/asset_market/test_token_capture_tier_worker_dirty_rank_sets.py \
  tests/unit/domains/asset_market/test_live_price_gateway_control_targets.py \
  tests/architecture/test_runtime_worker_constraint_hard_cut.py \
  tests/architecture/test_worker_runtime_contracts.py -q
```

Expected:

- Empty queues/control target sets for all converted workers return quickly.
- No broad profile/image/capture/live-gateway source discovery remains in runtime.

---

## Phase 7: Bounded Ops Repair Surface

- [x] **Step 7.1: Generalize runtime dirty target repair command**

Modify:

- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- `docs/generated/cli-help.md`
- `docs/CONTRACTS.md` if CLI contract docs list ops commands.

Command shape:

```bash
uv run gmgn-twitter-intel ops enqueue-runtime-worker-dirty-targets \
  --work <pulse_trigger|narrative_admission|mention_semantics|discussion_digest|profile_current|image_source|asset_profile_refresh|capture_tier|live_market_targets> \
  --since-hours <N> \
  --window <window> \
  --scope <scope> \
  --target-id <id> \
  --limit <N> \
  --dry-run
```

Rules:

- Dry-run by default.
- Any mutation requires explicit `--execute`; absence of `--execute` never writes.
- Requires `--work`.
- Requires bounded selector:
  - `--target-id`, or
  - `--since-hours` plus `--limit`, or
  - an explicit bounded partition selector plus `--limit`.
- Agent/provider-adjacent work (`pulse_trigger`, `mention_semantics`, `discussion_digest`) must not accept window/scope alone. It requires `--target-id` or capped `--since-hours` plus `--limit`.
- `--since-hours` has a per-work maximum. Start with 24h for deterministic non-agent projections and 4h for agent/provider-adjacent work unless product owners explicitly approve a lower-risk cap.
- Reports candidate count, would-enqueue count, current queue depth, due queue depth, and downstream job depth before enqueueing.
- Refuses execution when candidate count, would-enqueue count, current queue depth, or downstream job depth exceeds configured guardrails.
- Refuses unbounded agent/LLM work repairs.
- Reports candidate count before enqueueing and again after enqueueing.
- Enqueues dirty targets only.
- Does not call providers or agents.
- Does not call worker `run_once()`.
- Does not write read models or product/business output tables.

- [x] **Step 7.2: Add repair command tests**

Create/modify:

- `tests/unit/app/surfaces/cli/test_runtime_worker_dirty_target_repair.py`
- `tests/integration/test_runtime_worker_dirty_target_repair.py`

Run:

```bash
uv run pytest \
  tests/unit/app/surfaces/cli/test_runtime_worker_dirty_target_repair.py \
  tests/integration/test_runtime_worker_dirty_target_repair.py -q
```

Expected:

- Unbounded repair refuses to run.
- Dry-run does not enqueue.
- Execute mode without `--execute` refuses to write.
- Execute mode with `--execute` enqueues only dirty targets.
- Agent-adjacent repairs refuse window/scope-only selectors and over-cap `--since-hours`.

---

## Phase 8: Diagnostics And Idle-Cost Visibility

- [x] **Step 8.1: Add compact worker notes consistently**

Modify converted workers:

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_profile_current_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_image_mirror_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_capture_tier_worker.py`

Required notes:

- `claimed`
- `queue_depth` where cheap
- `source_rows_scanned`
- `targets_loaded`
- `rows_written`
- provider/agent backpressure reason counts where relevant.

- [x] **Step 8.2: Bound `/readyz` and diagnostics**

Modify:

- `src/gmgn_twitter_intel/app/surfaces/api/routes_health.py` or the current health route file found by `rg "readyz"`
- any diagnostics command or worker status serializer that emits large payloads.

Required behavior:

- Health endpoints use compact queue summaries.
- Expensive aggregate diagnostics are sampled, cached, or moved to explicit ops command.
- Health output must not serialize large source payloads.

Run:

```bash
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/unit/app -q
```

Expected:

- Worker status is enough to distinguish idle, backlog, and provider backpressure.

- [x] **Step 8.3: Classify and constrain registry tail workers**

Modify or document:

- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- `src/gmgn_twitter_intel/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py`
- `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `docs/WORKERS.md`

Required decisions:

- `handle_summary` is agent-adjacent. Move `reconcile_missing_jobs_once` broad discovery to bounded ops repair or convert it to dirty/job enqueue from watchlist signal writes. Runtime must claim existing summary jobs before provider execution.
- `cex_oi_radar_board` is a scheduled source snapshot. It may remain scheduled only if its universe query is explicitly bounded by configured `universe_limit`, exposes `source_rows_scanned`, and has an architecture test proving it does not grow with local historical facts. Otherwise split into bounded provider partitions.
- `macro_view_projection` is a scheduled projection. It may remain scheduled only if `observations_for_concepts` is bounded by configured concepts/window/limit, exposes `source_rows_scanned`, and does not scan unbounded historical observations every interval.
- All three must be classified in the registry-wide architecture test; unclassified new workers fail the test.

Tests:

- `tests/unit/domains/watchlist_intel/test_handle_summary_dirty_jobs.py` or an explicit bounded-repair test if moved to ops-only.
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py` asserts tail-worker classifications and required counters.

---

## Phase 9: Documentation Updates

- [x] **Step 9.1: Update architecture docs**

Modify:

- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`

Required doc changes:

- State that converted workers are dirty-target/leased-job consumers.
- State that `NOTIFY` is only a wake hint.
- State that repair is explicit, bounded, enqueue-only.
- List the owner repository/table for each converted control-plane queue.
- Do not document an old runtime scan fallback.

- [x] **Step 9.2: Update active spec status only after implementation**

Modify:

- `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`

Only after P0/P1 are complete:

- Set status to implemented or move to completed according to project workflow.
- Add verification evidence.

---

## Phase 10: Full Verification

- [ ] **Step 10.1: Static and targeted tests**

Run:

```bash
uv run ruff check src/gmgn_twitter_intel tests
uv run pytest tests/architecture -q
uv run pytest \
  tests/unit/domains/pulse_lab \
  tests/unit/domains/narrative_intel \
  tests/unit/domains/asset_market \
  tests/integration/test_pulse_candidate_dirty_triggers.py \
  tests/integration/test_narrative_admission_dirty_targets.py \
  tests/integration/test_mention_semantics_dirty_inputs.py \
  tests/integration/test_discussion_digest_dirty_targets.py \
  tests/integration/test_runtime_worker_dirty_target_repair.py -q
```

Expected:

- No architecture broad-scan violations.
- Converted workers pass empty queue and claim-first tests.

- [ ] **Step 10.2: Full changed-area suite**

Run the same changed-area suite used for the recent brief fix, expanding with new files:

```bash
uv run pytest tests -q
```

If the full suite is too slow, record the reason and run all architecture tests plus every touched domain's unit/integration tests.

- [ ] **Step 10.3: Live runtime verification**

Before live checks, confirm real config paths without printing secrets:

```bash
uv run gmgn-twitter-intel config
```

Expected:

- `config_path` and `workers_config_path` point to `~/.gmgn-twitter-intel/`.
- Report only paths/redacted booleans, not secret values.

Rebuild and migrate:

```bash
docker compose build app
docker compose up -d app
docker compose exec app uv run alembic current
```

Health:

```bash
curl -s http://127.0.0.1:8000/readyz
```

Queue depth sample:

```sql
SELECT 'pulse_trigger' AS queue, COUNT(*) AS total,
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000) AS due
FROM pulse_trigger_dirty_targets
UNION ALL
SELECT 'narrative_admission', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM narrative_admission_dirty_targets
UNION ALL
SELECT 'discussion_digest', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM discussion_digest_dirty_targets
UNION ALL
SELECT 'profile_current', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM token_profile_current_dirty_targets
UNION ALL
SELECT 'image_source', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM token_image_source_dirty_targets
UNION ALL
SELECT 'asset_profile_refresh', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM asset_profile_refresh_targets
UNION ALL
SELECT 'capture_tier', COUNT(*),
       COUNT(*) FILTER (WHERE due_at_ms <= EXTRACT(EPOCH FROM clock_timestamp()) * 1000)
FROM token_capture_tier_dirty_targets;
```

Active SQL sample:

```sql
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS age,
       left(query, 500) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Container CPU:

```bash
docker stats --no-stream
```

Expected:

- `/readyz` ok.
- Empty or low due queues do not correspond to repeating converted-domain scan SQL.
- No repeating active SQL against converted fact/read-model domains when dirty queues are empty.
- App/Postgres idle CPU is not dominated by converted worker discovery.

---

## Phase 11: Completion And Commit

- [ ] **Step 11.1: Self-review hard-cut constraints**

Run:

```bash
rg -n "latest_current_rows|admitted_radar_rows|admissions_for_window_scope|delete_admissions_outside_frontier|_enqueue_missing_from_admissions_sync|_missing_source_rows_for_semantics|due_admissions_for_semantics|missing_source_rows_for_mention_semantics|due_digest_targets|recent_profile_targets|candidate_sources|PendingAssetProfileQuery|select_due_asset_profile_rows|active_live_market_targets|demote_absent_hot_rows|handles_missing_summary_jobs|fallback_source_rows|fallback_scan|compat|audit loop|catch-up scan" src/gmgn_twitter_intel tests
```

Expected:

- Any remaining references are:
  - bounded ops repair;
  - architecture tests banning old runtime methods;
  - docs describing removed shape;
  - non-converted contexts explicitly outside this spec.

- [ ] **Step 11.2: Record verification evidence**

Update:

- this plan file with final test commands and results;
- the owning spec if implementation is complete;
- `docs/WORKERS.md` / `docs/RELIABILITY.md` with any live operational notes discovered during verification.

- [ ] **Step 11.3: Commit**

Run:

```bash
git status --short
git diff --stat
git add \
  docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md \
  docs/superpowers/plans/active/2026-05-25-runtime-worker-constraint-hard-cut-plan-cn.md \
  src/gmgn_twitter_intel \
  tests \
  docs
git commit -m "Hard-cut runtime worker discovery to dirty targets"
```

Expected:

- Commit includes no compatibility fallback.
- Commit includes migrations, repositories, workers, repair, architecture tests, and docs.

---

## Implementation Order Recommendation

1. Phase 0 and Phase 1 first, because they prevent the current brief fix from drifting and make future broad scans visible.
2. Phase 2 next, because `pulse_candidate` is the clearest remaining expensive trigger-discovery scan and has an existing job queue after trigger admission.
3. Phase 3 creates the whole narrative control-plane foundation, including digest dirty targets and semantic lease columns, before admission is hard-cut.
4. Phase 4 and Phase 5 then hard-cut semantic execution and digest execution on top of that existing control plane.
5. Phase 6 after P0 is green, because profile/image/capture/live-target work has the broadest producer coverage and includes rank-set semantics.
6. Phase 7 and Phase 8 after the first converted workers, then backfill any missing repair/status fields and registry-tail classifications.

## Review Checklist

- [ ] Every converted worker has an empty-queue test proving no source facts/read models are loaded.
- [ ] Every producer write edge has a same-transaction enqueue test.
- [ ] Every registered worker is classified in architecture tests.
- [ ] Every dirty target repository has stale completion protection.
- [ ] Rank/global workers such as capture tier preserve top-N business semantics rather than projecting exact targets independently.
- [ ] Exit/removal producer edges enqueue downstream stale work.
- [ ] Provider/agent backpressure before execution start does not burn attempts.
- [ ] Runtime code has no broad-scan fallback.
- [ ] Bounded repair commands enqueue dirty targets only.
- [ ] Public API/WebSocket/CLI product contracts are unchanged.
- [ ] Live idle verification checks CPU, `pg_stat_activity`, and queue depths after migration.
