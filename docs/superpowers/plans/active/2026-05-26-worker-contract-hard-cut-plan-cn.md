# Worker Contract Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the implicit worker inventory with an explicit
`WorkerManifest v1`, lane-level status, and architecture tests that enforce
worker ownership, idempotency evidence, and side-effect ledgers.

**Architecture:** Keep the existing Kappa/CQRS runtime and `WorkerBase`
execution loop. Add a read-only manifest as the worker contract source of
truth, hard-cut the registry/status/config/tests/docs to that contract, and
delete legacy compatibility aliases instead of preserving old payload or config
shapes.

**Tech Stack:** Python 3.13, Pydantic settings, FastAPI readyz surface,
PostgreSQL, pytest architecture tests, Docker Compose production runtime.

---

**Status:** Implemented in `codex/worker-contract-hard-cut`
**Date:** 2026-05-26
**Owning analysis:**
`docs/generated/postgres-observability/worker-contract-spec-review-2026-05-26-cn.md`
**Related blueprint:**
`docs/generated/postgres-observability/worker-architecture-refactor-blueprint-2026-05-26-cn.md`
**Worktree:** `.worktrees/worker-contract-hard-cut/`
**Branch:** `codex/worker-contract-hard-cut`

## Confirmed Scope Decisions

- Production `~/.parallax/workers.yaml` may be changed in the same
  deployment as this hard cut.
- `/readyz` payload shape may change; no old readyz contract needs to be kept.
- PostgreSQL SQL/index optimization is intentionally out of this plan.
- No compatibility code: no old worker key aliases, deprecated settings,
  fallback payloads, dual-read config, dual-write state, or legacy route shape.
- Do not print secrets. Runtime config diagnostics may report paths, booleans,
  worker names, and redacted status only.

## Target Worker Kinds

`WorkerKind` is a contract label, not a new execution framework.

| Kind | Meaning | Allowed writes |
|---|---|---|
| `FACT_INGEST` | Ingest external/provider facts into material fact tables. | Owned append/upsert fact tables and fanout dirty targets. |
| `FACT_LIFECYCLE` | Resolve, refresh, mirror, reconcile, or backfill fact state. | Owned fact lifecycle tables and related control-plane targets. |
| `PROJECTION` | Build rebuildable read models from facts and dirty targets. | Owned read models, projection run metadata, and downstream dirty targets. |
| `AGENT_SIDE_EFFECT` | Execute LLM/provider side effects with durable ledgers. | Agent job/run/brief/digest ledgers and owned output facts/read models. |
| `NOTIFICATION_RULE` | Convert internal candidate facts into notification and delivery rows. | `notifications` and `notification_deliveries`; no external delivery call. |
| `NOTIFICATION_DELIVERY` | Deliver outbound notifications through delivery rows. | Notification delivery state only. |
| `CACHE_FANOUT` | Maintain ephemeral local cache/fanout state. | Cache/control-plane tables only. |
| `MAINTENANCE` | Runtime maintenance, repair, or ops-only bounded tasks. | Explicit maintenance tables or repair target queues only. |

## Target Worker Lanes

Lanes are operator grouping and budget units. They must not become a second
runtime framework.

| Lane | Workers |
|---|---|
| `ingest` | `collector`, `market_tick_stream`, `market_tick_poll`, `news_fetch`, `equity_event_fetch` |
| `identity_market_fact` | `resolution_refresh`, `asset_profile_refresh`, `token_image_mirror`, `event_anchor_backfill`, `equity_event_source_reconcile`, `equity_event_process`, `news_item_process` |
| `projection` | `token_capture_tier`, `market_tick_current_projection`, `token_profile_current`, `token_radar_projection`, `narrative_admission`, `news_story_projection`, `news_page_projection`, `news_source_quality_projection`, `equity_event_story_projection`, `equity_event_page_projection`, `macro_view_projection`, `cex_oi_radar_board` |
| `agent` | `enrichment`, `mention_semantics`, `token_discussion_digest`, `news_item_brief`, `equity_event_brief`, `pulse_candidate`, `handle_summary` |
| `notification` | `notification_rule`, `notification_delivery` |
| `maintenance_cache` | `live_price_gateway` |

## Hard-Cut Rules

- A worker exists only if it appears in `WorkerManifest v1`.
- `workers.yaml` keys must match manifest names exactly.
- `/readyz` and CLI status emit new lane-aware payloads only.
- Tests must not carry `OLD_*`, `legacy`, `compat`, or alias allowlists for
  runtime contracts.
- Old names can remain only in historical Alembic revisions or immutable audit
  docs where changing history would be misleading.
- Unknown worker config keys fail startup instead of being ignored.
- Missing manifest idempotency evidence fails architecture tests.
- Missing side-effect ledger for an agent/notification worker fails
  architecture tests.
- `CANONICAL_WORKER_CLASSES`, `CANONICAL_WORKER_NAMES`,
  `WORKER_START_PRIORITY`, per-factory `WORKER_KEYS`, and
  `WORKER_QUEUE_TABLES` must stop being hand-maintained sources. Delete them
  or derive them mechanically from `WorkerManifest v1`.
- `watchlist_summary_jobs` and `watchlist_summary_dirty_targets` are not valid
  runtime contract names. Use `watchlist_handle_summary_jobs`,
  `watchlist_handle_summary_runs`, and the `handle_summary` worker contract.

## Pre-flight

- [ ] Confirm current runtime config paths.

  Run:

  ```bash
  uv run parallax config
  ```

  Expected: `config_path` and `workers_config_path` point at
  `~/.parallax/`. Record paths only; do not print credentials.

- [ ] Create and enter the implementation worktree.

  Run:

  ```bash
  git worktree add .worktrees/worker-contract-hard-cut -b codex/worker-contract-hard-cut main
  cd .worktrees/worker-contract-hard-cut
  git branch --show-current
  git status --short
  ```

  Expected: branch is `codex/worker-contract-hard-cut`; status contains only
  worktree-local generated changes, or is clean.

- [ ] Capture baseline test health.

  Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py -q
  ```

  Expected: both commands pass before the first implementation edit.

## File-level Edits

### Create `src/parallax/app/runtime/worker_manifest.py`

Responsibility: own the worker contract model and static manifest data.

Add these contract types:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkerKind(StrEnum):
    FACT_INGEST = "fact_ingest"
    FACT_LIFECYCLE = "fact_lifecycle"
    PROJECTION = "projection"
    AGENT_SIDE_EFFECT = "agent_side_effect"
    NOTIFICATION_RULE = "notification_rule"
    NOTIFICATION_DELIVERY = "notification_delivery"
    CACHE_FANOUT = "cache_fanout"
    MAINTENANCE = "maintenance"


class WorkerLane(StrEnum):
    INGEST = "ingest"
    IDENTITY_MARKET_FACT = "identity_market_fact"
    PROJECTION = "projection"
    AGENT = "agent"
    NOTIFICATION = "notification"
    MAINTENANCE_CACHE = "maintenance_cache"


@dataclass(frozen=True, slots=True)
class WorkerManifest:
    name: str
    domain: str
    factory: str
    lane: WorkerLane
    kind: WorkerKind
    worker_class: str
    start_priority: int
    input_contract: tuple[str, ...]
    ordering_keys: tuple[str, ...]
    writes_facts: tuple[str, ...] = ()
    writes_read_models: tuple[str, ...] = ()
    writes_control_plane: tuple[str, ...] = ()
    idempotency_evidence: tuple[str, ...] = ()
    side_effect_ledgers: tuple[str, ...] = ()
    queue_depth_table: str | None = None
    advisory_lock_key: str | None = None
    wakes_on: tuple[str, ...] = ()
    wakes_out: tuple[str, ...] = ()
```

Add helper functions:

```python
def all_worker_manifests() -> tuple[WorkerManifest, ...]: ...
def manifest_by_name() -> dict[str, WorkerManifest]: ...
def require_worker_manifest(name: str) -> WorkerManifest: ...
def manifests_by_lane() -> dict[WorkerLane, tuple[WorkerManifest, ...]]: ...
def manifest_names_for_factory(factory: str) -> frozenset[str]: ...
def worker_class_by_name() -> dict[str, str]: ...
def worker_start_priority() -> dict[str, int]: ...
def worker_queue_depth_tables() -> dict[str, str]: ...
```

Runtime knobs such as interval, batch size, timeout, enabled state, retry
limits, and model choice do not belong in this file. Stable contract metadata
such as factory owner, start priority, and queue-depth table does belong here
because those are currently duplicate runtime sources.

### Modify `src/parallax/app/runtime/worker_registry.py`

Responsibility: use manifest names as the source of truth for registered
runtime workers.

Required changes:

- Import `worker_class_by_name` and `worker_start_priority`.
- Validate every registered worker name exists in the manifest.
- Validate every manifest worker name is registered unless it is explicitly
  documented as non-`WorkerBase` cache/fanout runtime.
- Fail fast with `ValueError` on unknown names.
- Delete hand-maintained `CANONICAL_WORKER_CLASSES`,
  `CANONICAL_WORKER_NAMES`, and literal `WORKER_START_PRIORITY`.
- Replace internal imports of those constants with manifest helper imports in
  the same PR. Do not keep compatibility constants for old callers.
- Delete any legacy allowlist or implicit registry fallback.

### Modify `src/parallax/app/runtime/worker_scheduler.py`

Responsibility: order startup from manifest start priority.

Required changes:

- Replace `from parallax.app.runtime.worker_registry import
  WORKER_START_PRIORITY` with a manifest-derived helper.
- Keep `_SCHEDULER_CONCURRENT_WORKERS = {"enrichment"}` unless a later plan
  adds concurrency budget to manifest; do not mix that change into this plan.
- Add a test that `asset_profile_refresh < token_image_mirror <
  token_profile_current` still holds through manifest start priority.

### Modify `src/parallax/app/runtime/worker_factories/*.py`

Responsibility: keep factory names aligned to manifest names.

Required changes:

- Ensure each factory returns workers keyed by exact manifest name.
- Delete per-file literal `WORKER_KEYS` sets, or replace them with
  `manifest_names_for_factory("<factory>.py")`.
- Remove any old alias key generation.
- Remove any compatibility constructor branch that accepts old setting names.
- Keep business construction unchanged.

Files expected to change:

- `src/parallax/app/runtime/worker_factories/ingestion.py`
- `src/parallax/app/runtime/worker_factories/asset_market.py`
- `src/parallax/app/runtime/worker_factories/token_intel.py`
- `src/parallax/app/runtime/worker_factories/narrative_intel.py`
- `src/parallax/app/runtime/worker_factories/news_intel.py`
- `src/parallax/app/runtime/worker_factories/equity_event_intel.py`
- `src/parallax/app/runtime/worker_factories/pulse.py`
- `src/parallax/app/runtime/worker_factories/enrichment.py`
- `src/parallax/app/runtime/worker_factories/watchlist.py`
- `src/parallax/app/runtime/worker_factories/notifications.py`
- `src/parallax/app/runtime/worker_factories/cex_market_intel.py`
- `src/parallax/app/runtime/worker_factories/macro_intel.py`

### Modify `src/parallax/platform/config/settings.py`

Responsibility: hard-cut worker settings.

Required changes:

- Reject unknown worker config keys.
- Remove deprecated worker setting aliases.
- Remove compatibility keys such as old enrichment interval names, old
  notification interval names, old anchor price names, and old watchlist summary
  names.
- Keep only current manifest names under `settings.workers`.
- Ensure default workers config generated by `write_default_workers_config`
  contains manifest names only.

No SQL/index changes in this plan.

### Modify `src/parallax/app/runtime/worker_status.py`

Responsibility: emit lane-aware status without old payload compatibility.

Add a lane status shape:

```python
@dataclass(frozen=True, slots=True)
class WorkerLaneStatus:
    lane: str
    enabled_workers: int
    running_workers: int
    failed_workers: int
    soft_timed_out_workers: int
    hard_timed_out_workers: int
    oldest_active_run_once_age_ms: int | None
    iteration_duration_p99_ms: float | None
    queue_depth: int | None
```

Required behavior:

- `workers` remains keyed by exact worker name.
- `lanes` is keyed by lane name.
- No old readyz field aliases.
- Unknown worker status entries fail tests instead of being hidden.
- Delete literal `WORKER_QUEUE_TABLES`; source queue-depth tables from
  `WorkerManifest.queue_depth_table`.
- Keep collector details under `workers["collector"]["details"]`, but do not
  create a fake collector status if the scheduler/runtime no longer contains
  the manifest collector.

### Modify `src/parallax/app/runtime/job_queue.py`

Responsibility: remove stale watchlist summary queue naming.

Required changes:

- Rename `WATCHLIST_SUMMARY_JOBS` to `WATCHLIST_HANDLE_SUMMARY_JOBS`.
- Change descriptor `name` from `watchlist_summary_jobs` to
  `watchlist_handle_summary_jobs`.
- Update `JOB_QUEUE_DESCRIPTORS`, `tests/unit/test_job_queue.py`, and any
  queue diagnostics to use the handle-summary name.
- Do not keep a descriptor alias for `watchlist_summary_jobs`.

### Modify `src/parallax/app/runtime/ops_diagnostics.py`

Responsibility: remove stale queue-to-worker mapping.

Required changes:

- Replace the literal `"watchlist_summary_jobs": "handle_summary"` mapping
  with `"watchlist_handle_summary_jobs": "handle_summary"`.
- Prefer deriving queue-to-worker mapping from manifest queue metadata where
  practical.
- Add/adjust `tests/unit/test_ops_diagnostics.py` coverage so old
  `watchlist_summary_jobs` does not appear in diagnostics output.

### Modify `src/parallax/app/surfaces/api/dependencies.py`

Responsibility: make API dependency helpers use manifest names.

Required changes:

- Replace string-only worker lookup assumptions with manifest-backed validation.
- Keep health behavior simple: absent manifest worker is an error, disabled
  manifest worker is reported disabled.
- Do not preserve old dependency behavior for old worker keys.

### Modify readyz API surface

Likely files:

- `src/parallax/app/surfaces/api/routes_health.py` if present.
- `src/parallax/app/runtime/app.py` if readyz is assembled there.
- Any health serializer that currently reads `WorkerBase.status_payload()`.

Required changes:

- Add lane status to `/readyz`.
- Remove old readyz worker compatibility payload.
- Keep existing database/provider/agent health sections unless they directly
  depend on old worker key names.
- Update `src/parallax/app/surfaces/api/schemas.py` so `StatusData`
  declares `worker_lanes`. The route currently returns `JSONResponse`, so tests
  must assert the actual JSON body, not only the Pydantic response model.

Expected new top-level shape:

```json
{
  "ok": true,
  "db": {},
  "provider_states": {},
  "agent_execution": {},
  "workers": {
    "token_radar_projection": {}
  },
  "worker_lanes": {
    "projection": {
      "enabled_workers": 12,
      "running_workers": 12,
      "failed_workers": 0
    }
  }
}
```

### Modify CLI worker status

Likely files:

- `src/parallax/app/surfaces/cli/commands/*.py`
- `tests/unit/test_cli_worker_status_contract.py`

Required changes:

- Show lane grouping.
- Print exact worker names from manifest.
- Delete support for old worker names.
- Ensure CLI output does not expose secrets.

### Modify docs

Files:

- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md` if readyz contract is documented there.

Required changes:

- State that `WorkerManifest v1` is the worker contract source of truth.
- Replace flat worker inventory prose with lane/kind ownership.
- Document the hard-cut rule: old worker keys are invalid.
- Document side-effect ledger requirement.
- Document that runtime knobs remain in `workers.yaml`, not in manifest.

### Modify production runtime config

File outside repo:

- `~/.parallax/workers.yaml`

Required changes:

- Backup once before editing:

  ```bash
  cp ~/.parallax/workers.yaml ~/.parallax/workers.yaml.pre-worker-contract-hard-cut
  ```

- Replace old keys with exact manifest keys.
- Remove unused/deprecated keys instead of commenting them out.
- Do not print credential values from adjacent config files.

## PR Breakdown

### PR 1 — Manifest Contract

Files:

- Create `src/parallax/app/runtime/worker_manifest.py`
- Modify `tests/architecture/test_worker_runtime_contracts.py`
- Modify `tests/architecture/test_worker_inventory_contract.py`
- Modify `docs/WORKERS.md`

Acceptance:

- Manifest contains all current workers.
- Architecture tests import manifest instead of maintaining a duplicate
  `EXPECTED_WORKERS`.
- No runtime behavior changes yet except failing tests for missing manifest
  entries.

### PR 2 — Registry and Config Hard Cut

Files:

- Modify `src/parallax/app/runtime/worker_registry.py`
- Modify `src/parallax/app/runtime/worker_factories/*.py`
- Modify `src/parallax/platform/config/settings.py`
- Modify `tests/unit/test_settings.py`
- Modify `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Modify `tests/unit/test_job_queue.py`
- Modify `tests/unit/test_ops_diagnostics.py`

Acceptance:

- Unknown worker keys fail startup/config parsing.
- Old worker setting aliases are deleted.
- Default generated `workers.yaml` contains manifest names only.
- Stale `watchlist_summary_jobs` queue descriptor is deleted, not aliased.

### PR 3 — Lane Status and Readyz Hard Cut

Files:

- Modify `src/parallax/app/runtime/worker_status.py`
- Modify readyz serializer files under `src/parallax/app/`
- Modify CLI status command files under `src/parallax/app/surfaces/cli/`
- Modify `tests/unit/test_cli_worker_status_contract.py`
- Modify `tests/integration/test_api_health.py`

Acceptance:

- `/readyz` returns `worker_lanes`.
- `/readyz` no longer preserves old worker payload aliases.
- CLI worker status groups by lane and exact worker name.

### PR 4 — Ownership and Side-effect Guards

Files:

- Modify `tests/architecture/test_worker_runtime_contracts.py`
- Modify `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- Modify `tests/architecture/test_projection_worker_idle_cost_contract.py`
- Modify docs that explain ownership rules.

Acceptance:

- Projection workers cannot write fact tables.
- Read models have a single runtime writer.
- Agent/notification workers must declare ledgers.
- Manifest idempotency evidence is required for every worker.

### PR 5 — Production Config and Operational Verification

Files:

- Modify `~/.parallax/workers.yaml`
- Add verification artifact:
  `docs/superpowers/plans/active/2026-05-26-worker-contract-hard-cut-verification-cn.md`

Acceptance:

- Docker runtime starts with hard-cut config.
- `/readyz` is healthy with new payload.
- PoWA/pgBadger remain available.
- No old worker config keys remain in production config.

## Implementation Tasks

### Task 1: Add failing manifest inventory tests

**Files:**

- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `tests/architecture/test_worker_inventory_contract.py`

- [ ] Add a test that imports `all_worker_manifests`.

  Test intent:

  ```python
  def test_worker_manifest_contains_every_runtime_worker() -> None:
      manifest_names = {manifest.name for manifest in all_worker_manifests()}
      from parallax.app.runtime.worker_registry import CANONICAL_WORKER_CLASSES

      assert manifest_names == set(CANONICAL_WORKER_CLASSES)
  ```

- [ ] Add a test that every manifest has non-empty `domain`, `lane`, `kind`,
  `factory`, `worker_class`, `start_priority`, and `idempotency_evidence`.

- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: fails because `worker_manifest.py` does not exist.

### Task 2: Implement `WorkerManifest v1`

**Files:**

- Create: `src/parallax/app/runtime/worker_manifest.py`

- [ ] Add `WorkerKind`, `WorkerLane`, `WorkerManifest`, and helper functions.

- [ ] Populate all 34 workers using the lane table in this plan.

- [ ] Use exact class paths already listed in the current architecture tests.

- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: manifest existence tests pass; registry/config tests may still fail.

### Task 3: Replace duplicate expected worker inventory in tests

**Files:**

- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `tests/architecture/test_worker_inventory_contract.py`

- [ ] Delete `EXPECTED_WORKERS` as a hand-maintained source of truth.

- [ ] Build expected names/classes from `all_worker_manifests()`.

- [ ] Replace tests importing `CANONICAL_WORKER_NAMES` with manifest helper
  imports, including:

  - `tests/support/hot_path_runtime.py`
  - `tests/integration/test_api_http.py`
  - `tests/unit/test_cli_worker_status_contract.py`
  - `tests/unit/test_worker_settings.py`

- [ ] Delete `OLD_READYZ_WORKER_KEYS`, `OLD_RUNTIME_SETTINGS`, and
  `_legacy_anchor_worker_key()`.

- [ ] Add a string scan test that rejects runtime compatibility names:

  ```python
  FORBIDDEN_RUNTIME_COMPAT_TOKENS = (
      "OLD_READYZ_WORKER_KEYS",
      "OLD_RUNTIME_SETTINGS",
      "_legacy_anchor_worker_key",
      "deprecated_worker",
      "legacy_worker_key",
  )
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py -q
  ```

  Expected: tests fail only where production code still has old compatibility
  paths.

### Task 4: Hard-cut registry and factory validation

**Files:**

- Modify: `src/parallax/app/runtime/worker_registry.py`
- Modify: `src/parallax/app/runtime/worker_factories/*.py`
- Modify: `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Modify: `tests/unit/test_worker_scheduler.py`

- [ ] Add registry validation against `manifest_by_name()`.

- [ ] Ensure every factory key is a manifest key.

- [ ] Remove any old alias or fallback factory output.

- [ ] Delete literal per-factory `WORKER_KEYS` sources or derive each from
  `manifest_names_for_factory`.

- [ ] Delete the `_worker_settings()` special-case branch
  `config_name = "handle_summary" if name == "handle_summary" else name`;
  it is redundant and becomes a suspicious compatibility hook after the hard
  cut.

- [ ] Add tests:

  ```python
  def test_worker_registry_rejects_unknown_worker_name() -> None: ...
  def test_worker_factories_only_emit_manifest_workers() -> None: ...
  def test_worker_start_priority_is_manifest_derived() -> None: ...
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_worker_scheduler.py -q
  ```

  Expected: pass after registry/factory hard cut.

### Task 5: Hard-cut worker settings

**Files:**

- Modify: `src/parallax/platform/config/settings.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/test_worker_settings.py`

- [ ] Add or verify strict unknown-key rejection for `workers.yaml`.

- [ ] Add manifest parity:

  ```python
  worker_fields = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}
  assert worker_fields == {manifest.name for manifest in all_worker_manifests()}
  ```

- [ ] Delete old worker setting aliases.

- [ ] Update default worker config writer to use manifest names only.

- [ ] Add tests:

  ```python
  def test_workers_config_rejects_unknown_worker_key() -> None: ...
  def test_default_workers_config_contains_only_manifest_workers() -> None: ...
  def test_old_worker_setting_aliases_are_rejected() -> None: ...
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py -q
  ```

  Expected: pass with old alias keys rejected.

### Task 6: Add lane status

**Files:**

- Modify: `src/parallax/app/runtime/worker_status.py`
- Modify: `tests/unit/test_worker_base_runtime.py`
- Modify: `tests/unit/test_worker_scheduler.py`

- [ ] Add lane aggregation using manifest lane membership.

- [ ] Compute counts from existing `WorkerBase.status_payload()` values.

- [ ] Source queue depths from `WorkerManifest.queue_depth_table`; delete
  literal `WORKER_QUEUE_TABLES`.

- [ ] Do not change `WorkerBase.run_once()` semantics.

- [ ] Add tests:

  ```python
  def test_worker_status_groups_workers_by_manifest_lane() -> None: ...
  def test_worker_status_rejects_status_for_unknown_worker() -> None: ...
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py -q
  ```

  Expected: pass.

### Task 7: Hard-cut `/readyz`

**Files:**

- Modify: readyz serializer under `src/parallax/app/`
- Modify: `tests/integration/test_api_health.py`

- [ ] Add `worker_lanes` to readyz.

- [ ] Remove old readyz worker compatibility assertions.

- [ ] Add tests:

  ```python
  def test_readyz_returns_lane_status_contract() -> None: ...
  def test_readyz_uses_manifest_worker_names_only() -> None: ...
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/integration/test_api_health.py -q
  ```

  Expected: pass with new readyz shape.

### Task 8: Hard-cut CLI worker status

**Files:**

- Modify: CLI worker/status command files under
  `src/parallax/app/surfaces/cli/`
- Modify: `tests/unit/test_cli_worker_status_contract.py`

- [ ] Print lane groups and exact worker names.

- [ ] Remove old worker name support from CLI parsing/output.

- [ ] Add tests:

  ```python
  def test_cli_worker_status_prints_lane_groups() -> None: ...
  def test_cli_worker_status_does_not_print_legacy_worker_keys() -> None: ...
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_cli_worker_status_contract.py -q
  ```

  Expected: pass.

### Task 9: Add ownership and side-effect manifest guards

**Files:**

- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- Modify: `tests/architecture/test_projection_worker_idle_cost_contract.py`

- [ ] Replace static single-writer allowlists with manifest-owned write sets
  where possible.

- [ ] Add guard: `PROJECTION` workers must not write fact tables.

- [ ] Add guard: `AGENT_SIDE_EFFECT` and `NOTIFICATION_DELIVERY` workers must
  declare `side_effect_ledgers`.

- [ ] Add guard: `NOTIFICATION_RULE` may write notification/delivery control
  rows but must not call external providers.

- [ ] Add guard: every worker has `idempotency_evidence`.

- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_projection_worker_idle_cost_contract.py -q
  ```

  Expected: pass.

### Task 10: Update docs to new contract

**Files:**

- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`

- [ ] Document manifest fields.

- [ ] Document lane/kind taxonomy.

- [ ] Document that runtime knobs stay in `workers.yaml`.

- [ ] Document hard-cut behavior for unknown worker keys.

- [ ] Document new `/readyz.worker_lanes` shape.

- [ ] Run:

  ```bash
  rg -n "OLD_READYZ_WORKER_KEYS|OLD_RUNTIME_SETTINGS|_legacy_anchor_worker_key|watchlist_summary_jobs|watchlist_summary_dirty_targets|CANONICAL_WORKER_CLASSES = \\{|WORKER_START_PRIORITY = \\{|WORKER_QUEUE_TABLES = \\{" \
    src/parallax/app/runtime \
    src/parallax/platform/config/settings.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_worker_constraint_hard_cut.py \
    tests/architecture/test_worker_inventory_contract.py \
    tests/unit/test_worker_settings.py \
    tests/unit/test_cli_worker_status_contract.py \
    docs/WORKERS.md docs/WORKER_FLOW.md docs/CONTRACTS.md
  ```

  Expected: no matches. Do not use a broad `legacy|fallback` scan over the full
  repo here; many unrelated tests intentionally contain those words.

### Task 11: Update production `workers.yaml`

**Files:**

- Modify outside repo: `~/.parallax/workers.yaml`

- [ ] Backup the file once:

  ```bash
  cp ~/.parallax/workers.yaml ~/.parallax/workers.yaml.pre-worker-contract-hard-cut
  ```

- [ ] Remove old worker keys and aliases.

- [ ] Keep enabled/interval/batch values under exact manifest keys.

- [ ] Validate without printing secrets:

  ```bash
  uv run parallax config
  ```

  Expected: paths are correct and config parses.

### Task 12: Docker runtime verification

**Files:**

- No code edits unless verification exposes a hard-cut bug.

- [ ] Rebuild and restart the app image only if code changed.

  Run the repo's existing Docker workflow from `docs/SETUP.md`.

- [ ] Check readyz:

  ```bash
  curl -fsS http://127.0.0.1:8765/readyz
  ```

  Expected: `ok=true`; response includes `worker_lanes`; response does not
  include old worker aliases.

- [ ] Check providers:

  Expected: GMGN and OKX provider states remain streaming when enabled.

- [ ] Check PoWA/pgBadger availability remains unchanged.

  Expected: PoWA Web still serves login page on `127.0.0.1:8888`; pgBadger
  report generation still works.

## Acceptance Test Commands

- Architecture contract:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_projection_worker_idle_cost_contract.py -q
  ```

- Worker runtime:

  ```bash
  uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_job_queue.py tests/unit/test_ops_diagnostics.py -q
  ```

- Settings:

  ```bash
  uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py -q
  ```

- API/CLI contract:

  ```bash
  uv run pytest tests/integration/test_api_health.py tests/unit/test_cli_worker_status_contract.py -q
  ```

- Lint:

  ```bash
  uv run ruff check src/parallax tests
  ```

- Full gate:

  ```bash
  make check-all
  ```

- Production smoke:

  ```bash
  curl -fsS http://127.0.0.1:8765/readyz
  ```

## Rollout Order

1. Merge manifest and tests.
2. Merge registry/config hard cut.
3. Merge lane status and readyz hard cut.
4. Backup and update production `~/.parallax/workers.yaml`.
5. Rebuild/restart Docker app.
6. Run `/readyz` smoke test.
7. Run PoWA/pgBadger availability checks.
8. Record verification artifact.

## Rollback

- Code rollback: revert the branch/commit that introduced manifest hard cut.
- Config rollback: restore
  `~/.parallax/workers.yaml.pre-worker-contract-hard-cut`.
- Runtime rollback: restart Docker app after restoring code/config.
- Data rollback: no database migration or SQL/index change is part of this
  plan, so no table rollback is expected.

## Risks and Controls

- Risk: production fails startup because `workers.yaml` contains unknown old
  keys.
  Control: validate config before restart and keep the backup file.

- Risk: downstream scripts rely on old `/readyz` payload shape.
  Control: hard-cut is intentional; update in-repo tests and docs in the same
  change. No runtime compatibility payload.

- Risk: manifest duplicates stale docs.
  Control: architecture tests import manifest and forbid a second worker source
  of truth.

- Risk: this grows `WorkerBase`.
  Control: do not add lane, manifest, or side-effect logic to `WorkerBase`
  beyond status data it already owns.

- Risk: SQL performance work gets mixed into contract work.
  Control: no SQL/index changes in this plan; performance tuning gets a
  separate plan.

## Verification Artifact

Create after implementation:

`docs/superpowers/plans/active/2026-05-26-worker-contract-hard-cut-verification-cn.md`

It must include:

- Exact commands run and full outputs for `make check-all`.
- `/readyz` sample with secrets redacted.
- Confirmation that `worker_lanes` exists.
- Confirmation that old worker keys are absent from runtime config/status.
- Remaining risks and any `docs/TECH_DEBT.md` additions.

## Completion Bar

This work is complete only when:

- `WorkerManifest v1` is the sole worker inventory source.
- Production `workers.yaml` contains only manifest worker keys.
- `/readyz` uses the new lane-aware contract.
- Architecture tests enforce ownership, idempotency evidence, and side-effect
  ledger requirements.
- No runtime compatibility code remains for old worker keys, old settings, or
  old readyz shape.
- Full verification is recorded.
