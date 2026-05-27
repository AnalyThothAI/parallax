# Macro Sync Worker Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft  
**Date:** 2026-05-27  
**Owning spec:** `docs/superpowers/specs/active/2026-05-27-macro-sync-worker-hard-cut-cn.md`  
**Recommended worktree:** `.worktrees/macro-sync-worker-hard-cut`  
**Recommended branch:** `codex/macro-sync-worker-hard-cut`

**Goal:** Add `macro_sync` as the normal runtime Macro Intel fact-ingest worker so `/macro` freshness is owned by Kappa/CQRS runtime state, not manual `macro sync` or `import-bundle` runs.

**Architecture:** `macro_sync` owns bounded sync-window control state, runs the packaged macrodata `macro-core` history bundle outside DB transactions, and writes only `macro_observations`, `macro_import_runs`, and sync audit/control rows. `macro_view_projection` remains the only writer of `macro_observation_series_rows`, active generation pointers, and `macro_view_snapshots`. API and frontend paths remain provider-free. Runtime deletes the `uv run macrodata` assumption instead of preserving it as a compatibility fallback.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3, existing `WorkerBase`, `WakeBus`/`WakeWaiter`, macrodata packaged console script, pytest architecture/unit/integration tests, Docker Compose live verification.

---

## Spec Review Coverage

- [ ] **G1 / AC1 / AC2:** Create a registered `macro_sync` worker that claims bounded windows and imports facts across cycles.
- [ ] **G2 / AC10:** Enforce single-writer boundaries: `macro_sync` writes facts/control only; `macro_view_projection` writes read models only.
- [ ] **G3 / AC5:** Make macrodata execution container-native: no `uv`, no host-local checkout requirement, valid configured cwd or packaged runtime.
- [ ] **G4 / AC7:** Expose fact freshness, latest sync attempt, provider/source health, and projection lag separately.
- [ ] **G5 / AC1:** Bootstrap missing history automatically through finite date windows.
- [ ] **G6 / AC6:** Re-sync a steady overlap window idempotently and keep FRED secrets out of argv/logs/DB/API.
- [ ] **G7 / AC8 / AC9:** CLI sync delegates to the same sync use case; HTTP/React never call providers.

## Pre-flight

- [ ] Confirm the spec is approved or explicitly accepted for implementation:

```bash
sed -n '1,260p' docs/superpowers/specs/active/2026-05-27-macro-sync-worker-hard-cut-cn.md
```

- [ ] Create an isolated worktree before code changes:

```bash
git worktree add .worktrees/macro-sync-worker-hard-cut -b codex/macro-sync-worker-hard-cut main
cd .worktrees/macro-sync-worker-hard-cut
git status --short --branch
```

- [ ] Confirm real runtime config paths before any live-data debugging, redacting secrets:

```bash
uv run gmgn-twitter-intel config
```

Expected:

- `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`.
- Only env var names and booleans are reported for macrodata/FRED.

- [ ] Baseline tests in the worktree:

```bash
uv run ruff check src/gmgn_twitter_intel tests
uv run pytest tests/unit/domains/macro_intel tests/unit/test_cli_macro_commands.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Known-failing baseline tests: none expected in the clean worktree. If failures exist, record exact test ids before changing code.

## Non-Negotiables

- [ ] No runtime fallback to `uv run macrodata`.
- [ ] No runtime dependency on a host-local `macrodata-cli` checkout.
- [ ] No provider call before a durable sync-window claim.
- [ ] No provider IO in `/api/macro`, `/api/macro/modules/{module_id}`, `/api/macro/series`, or React code.
- [ ] No path where `macro_view_projection` imports macrodata bundles or calls providers.
- [ ] No secret values in argv, logs, DB JSON, CLI/API payloads, fixtures, docs, or tests.
- [ ] No compatibility flag such as `use_legacy_macro_sync`, `fallback_uv`, or `manual_import_freshness`.

## Execution Review Adjustments

Execution-prep subagents reviewed this plan against the `main` worktree on
2026-05-27. Treat these as binding implementation details:

- [ ] `MacroSyncWorker` must define its own `__init__(..., settings_root, wake_bus, ...)`
  and pass only `WorkerBase`-accepted kwargs to `super().__init__`. Do not pass
  `settings_root` or `wake_bus` through to `WorkerBase`.
- [ ] `construct_macro_intel_workers` must use `constructed = {}` and evaluate
  `macro_sync` and `macro_view_projection` independently. Do not keep the
  current projection-disabled early return.
- [ ] `MacroViewProjectionWorkerSettings` must define
  `wakes_on: tuple[str, ...] = ("macro_observations_imported",)` with the same
  string/list validator style used by other worker settings.
- [ ] `tests/architecture/test_runtime_worker_constraint_hard_cut.py` must
  classify `macro_sync` explicitly so all manifest workers remain covered.
- [ ] `macro_sync_windows` must add numeric constraints for attempts, priority,
  and timestamps. The claim query must include `attempt_count < max_attempts`.
- [ ] `idx_macro_sync_windows_due` must follow claim ordering:
  `(priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)` with a
  partial predicate on due statuses.
- [ ] `macro_sync_runs.import_run_id` should be a nullable foreign key to
  `macro_import_runs(run_id)`.
- [ ] `write_macrodata_bundle_import(...)` must not open or commit its own
  transaction. The caller owns the unit of work so import audit, sync audit, and
  window completion are atomic.
- [ ] CLI `macro sync` tests must patch `MacroSyncService`, not
  `MacrodataBundleRunner`, and must remove fake `["uv", "run", "macrodata"]`
  diagnostics from the sync command tests.
- [ ] CLI sync handler must parse `start` / `end` with `date.fromisoformat`,
  validate `start <= end`, and test invalid date/range failures.
- [ ] Macro API/module provenance must expose latest sync attempt, fact
  freshness, and projection lag from PostgreSQL read/audit state only.
- [ ] Add `tests/unit/test_worker_settings.py` to targeted verification.
- [ ] Update `SINGLE_WRITER_READ_MODELS` for
  `macro_observation_series_rows` and `macro_observation_series_active_generation`
  if the manifest declares them as projection-owned read models.
- [ ] Test snippets should use current public manifest APIs such as
  `all_worker_manifests()`, not a nonexistent `WORKER_MANIFESTS` symbol.
- [ ] If CLI help text changes, regenerate `docs/generated/cli-help.md`.

## Root Cause Binding

The plan fixes these observed facts from the 2026-05-27 investigation:

- Runtime manifest has only `macro_view_projection` for Macro Intel at `src/gmgn_twitter_intel/app/runtime/worker_manifest.py:633`.
- Macro factory constructs only `MacroViewProjectionWorker` at `src/gmgn_twitter_intel/app/runtime/worker_factories/macro_intel.py:13`.
- Projection recomputes snapshots from existing facts at `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py:33`; it does not fetch providers.
- CLI sync directly invokes `MacrodataBundleRunner` at `src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py:63`.
- Runner currently shells `uv run macrodata` at `src/gmgn_twitter_intel/integrations/macrodata/runner.py:25`.
- Current Docker app has packaged `/app/.venv/bin/macrodata`, but no `uv` on runtime `PATH`, and a host-local `cli_project_dir` is invalid inside the container.

## Phase 0: Red Tests First

- [ ] **Step 0.1: Add architecture tests for the new worker ownership**

Modify `tests/architecture/test_worker_runtime_contracts.py` and `tests/architecture/test_runtime_worker_constraint_hard_cut.py`.

Required assertions:

```python
def test_macro_sync_is_fact_ingest_and_projection_remains_read_model_writer() -> None:
    manifests = {manifest.name: manifest for manifest in WORKER_MANIFESTS}
    assert manifests["macro_sync"].domain == "macro_intel"
    assert manifests["macro_sync"].kind is WorkerKind.FACT_INGEST
    assert "macro_observations" in manifests["macro_sync"].writes_facts
    assert "macro_view_snapshots" not in manifests["macro_sync"].writes_read_models
    assert "macro_observation_series_rows" in manifests["macro_view_projection"].writes_read_models
```

Also assert:

- `macro_sync` lists control-plane writes for `macro_sync_windows` and `macro_sync_runs`.
- `macro_view_projection.input_contract` is persisted macro facts/read models, not providers.
- `macro_view_projection.wakes_on` includes `macro_observations_imported`.

- [ ] **Step 0.2: Add runner tests that fail on `uv`**

Modify `tests/unit/test_cli_macro_commands.py`.

Required assertions:

```python
assert calls[0]["command"][0] != "uv"
assert "uv" not in calls[0]["command"]
assert calls[0]["command"][1:] == ["bundle", "history", "macro-core", "--start", "2026-01-01", "--end", "2026-05-21"]
```

Add a missing configured cwd test:

```python
def test_macrodata_runner_rejects_missing_configured_cli_project_dir(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing"
    class Settings:
        macrodata_cli_project_dir = str(missing)
        macrodata_fred_api_key_env = None

    with pytest.raises(MacrodataRunnerError) as excinfo:
        MacrodataBundleRunner(settings=Settings()).history_bundle(bundle="macro-core", start="2026-01-01", end="2026-01-02")

    assert excinfo.value.diagnostics["cli_project_dir"] == str(missing)
    assert excinfo.value.diagnostics["error_code"] == "macrodata_cli_project_dir_missing"
```

- [ ] **Step 0.3: Add sync service and worker tests before implementation**

New files:

- `tests/unit/domains/macro_intel/test_macro_sync_scheduler.py`
- `tests/unit/domains/macro_intel/test_macro_sync_worker.py`
- `tests/unit/domains/macro_intel/test_macro_sync_service.py`

Required test cases:

- `test_scheduler_bootstrap_partitions_missing_history_into_bounded_windows`
- `test_scheduler_steady_state_enqueues_overlap_when_due`
- `test_worker_idle_claims_no_window_and_does_not_call_runner`
- `test_worker_claims_window_before_provider_io`
- `test_worker_import_success_writes_facts_completes_window_and_wakes_projection`
- `test_worker_provider_failure_records_retry_without_fabricating_facts`
- `test_sync_service_redacts_secret_from_run_payload_and_diagnostics`

- [ ] **Step 0.4: Add repository/migration tests**

Modify `tests/unit/test_postgres_schema.py`; add `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`.

Required assertions:

- Migration creates `macro_sync_windows`.
- Migration creates `macro_sync_runs`.
- Claim SQL uses `FOR UPDATE SKIP LOCKED` or atomic `UPDATE ... RETURNING`.
- No query in the idle claim path scans `macro_observations`.
- Run audit JSON fields use diagnostics and redacted booleans only.

## Phase 1: Storage And Repository Control Plane

- [ ] **Step 1.1: Add migration**

New file: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_macro_sync_worker.py`

Revision:

```python
revision = "20260527_0111"
down_revision = "20260526_0110"
```

Upgrade SQL:

```sql
CREATE TABLE IF NOT EXISTS macro_sync_windows (
  sync_window_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  bundle_name TEXT NOT NULL,
  window_start DATE NOT NULL,
  window_end DATE NOT NULL,
  trigger_reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  payload_hash TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 8,
  last_error_code TEXT,
  last_error_message TEXT,
  last_run_id TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  completed_at_ms BIGINT,
  CONSTRAINT chk_macro_sync_windows_range CHECK (window_start <= window_end),
  CONSTRAINT chk_macro_sync_windows_attempt_count CHECK (attempt_count >= 0),
  CONSTRAINT chk_macro_sync_windows_max_attempts CHECK (max_attempts > 0),
  CONSTRAINT chk_macro_sync_windows_priority CHECK (priority >= 0),
  CONSTRAINT chk_macro_sync_windows_due_at_ms CHECK (due_at_ms >= 0),
  CONSTRAINT chk_macro_sync_windows_status CHECK (
    status IN ('pending', 'running', 'retryable', 'done', 'failed')
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_sync_windows_identity
  ON macro_sync_windows(source_name, bundle_name, window_start, window_end, trigger_reason);

CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_due
  ON macro_sync_windows(priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)
  WHERE status IN ('pending', 'retryable');

CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_lease
  ON macro_sync_windows(leased_until_ms)
  WHERE status = 'running';

CREATE TABLE IF NOT EXISTS macro_sync_runs (
  sync_run_id TEXT PRIMARY KEY,
  sync_window_id TEXT REFERENCES macro_sync_windows(sync_window_id) ON DELETE SET NULL,
  source_name TEXT NOT NULL,
  bundle_name TEXT NOT NULL,
  requested_start DATE NOT NULL,
  requested_end DATE NOT NULL,
  status TEXT NOT NULL,
  import_run_id TEXT REFERENCES macro_import_runs(run_id) ON DELETE SET NULL,
  asof_date DATE,
  max_observed_at DATE,
  observations_count INTEGER NOT NULL DEFAULT 0,
  imported_observation_count INTEGER NOT NULL DEFAULT 0,
  coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  missing_series_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  series_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  fred_api_key_env TEXT,
  fred_api_key_configured BOOLEAN NOT NULL DEFAULT false,
  error_code TEXT,
  error_message TEXT,
  started_at_ms BIGINT NOT NULL,
  completed_at_ms BIGINT NOT NULL,
  duration_ms BIGINT NOT NULL,
  CONSTRAINT chk_macro_sync_runs_observations_count CHECK (observations_count >= 0),
  CONSTRAINT chk_macro_sync_runs_imported_observation_count CHECK (imported_observation_count >= 0),
  CONSTRAINT chk_macro_sync_runs_duration_ms CHECK (duration_ms >= 0),
  CONSTRAINT chk_macro_sync_runs_status CHECK (
    status IN ('ok', 'partial', 'retryable_error', 'failed', 'config_error')
  )
);

CREATE INDEX IF NOT EXISTS idx_macro_sync_runs_latest
  ON macro_sync_runs(completed_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_macro_sync_runs_window
  ON macro_sync_runs(sync_window_id, completed_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_macro_observations_max_observed
  ON macro_observations(observed_at DESC);
```

Downgrade drops the new indexes and tables only. It must not drop `macro_observations`, `macro_import_runs`, projected series rows, or snapshots.

- [ ] **Step 1.2: Add sync data types**

New file: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_sync_types.py`

Required dataclasses:

```python
@dataclass(frozen=True, slots=True)
class MacroSyncWindow:
    sync_window_id: str
    source_name: str
    bundle_name: str
    window_start: date
    window_end: date
    trigger_reason: str
    status: str
    attempt_count: int
    max_attempts: int
    payload_hash: str

@dataclass(frozen=True, slots=True)
class MacroSyncRunSummary:
    sync_run_id: str
    import_run_id: str | None
    status: str
    observations_count: int
    imported_observation_count: int
    asof_date: date | None
    max_observed_at: date | None
    diagnostics: Mapping[str, Any]
```

- [ ] **Step 1.3: Extend macro repository**

Modify `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py:14`.

Add methods:

```python
def enqueue_macro_sync_window(
    self,
    *,
    source_name: str,
    bundle_name: str,
    window_start: date,
    window_end: date,
    trigger_reason: str,
    priority: int,
    due_at_ms: int,
    max_attempts: int,
    now_ms: int,
) -> str: ...

def claim_macro_sync_window(
    self,
    *,
    lease_owner: str,
    lease_ms: int,
    now_ms: int,
) -> dict[str, Any] | None: ...

def record_macro_sync_run(self, run: Mapping[str, Any]) -> None: ...

def complete_macro_sync_window(
    self,
    *,
    sync_window_id: str,
    lease_owner: str,
    attempt_count: int,
    sync_run_id: str,
    completed_at_ms: int,
) -> bool: ...

def retry_macro_sync_window(
    self,
    *,
    sync_window_id: str,
    lease_owner: str,
    attempt_count: int,
    sync_run_id: str | None,
    error_code: str,
    error_message: str,
    retry_delay_ms: int,
    now_ms: int,
) -> bool: ...

def fail_macro_sync_window(
    self,
    *,
    sync_window_id: str,
    lease_owner: str,
    attempt_count: int,
    sync_run_id: str | None,
    error_code: str,
    error_message: str,
    now_ms: int,
) -> bool: ...

def latest_macro_sync_run(self) -> dict[str, Any] | None: ...

def macro_sync_queue_summary(self, *, now_ms: int) -> dict[str, Any]: ...

def macro_observations_max_observed_at(self) -> date | None: ...
```

Claim SQL shape:

```sql
WITH candidate AS (
  SELECT sync_window_id
  FROM macro_sync_windows
  WHERE status IN ('pending', 'retryable')
    AND due_at_ms <= %s
    AND (leased_until_ms IS NULL OR leased_until_ms <= %s)
    AND attempt_count < max_attempts
  ORDER BY priority ASC, due_at_ms ASC, updated_at_ms ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE macro_sync_windows AS window
SET status = 'running',
    lease_owner = %s,
    leased_until_ms = %s,
    attempt_count = window.attempt_count + 1,
    updated_at_ms = %s
FROM candidate
WHERE window.sync_window_id = candidate.sync_window_id
RETURNING window.*;
```

Stale completion protection must match `sync_window_id`, `lease_owner`, and `attempt_count`.

- [ ] **Step 1.4: Split macrodata bundle importer into parse/write primitives**

Modify `src/gmgn_twitter_intel/domains/macro_intel/services/macrodata_bundle_importer.py:19`.

Keep public `import_macrodata_bundle(...)` for `import-bundle`, but add a lower-level function so worker/service can write facts, import audit, sync audit, and window completion inside one unit of work:

```python
def parse_macrodata_bundle(envelope: Mapping[str, Any], *, now_ms: int) -> MacrodataBundleImport: ...

def write_macrodata_bundle_import(
    parsed: MacrodataBundleImport,
    *,
    repos: RepositorySession,
) -> dict[str, Any]: ...
```

Required return summary additions:

- `max_observed_at`
- `asof`
- `import_run_id`
- `imported_observation_count`

Preserve validation-before-write behavior from existing tests.

## Phase 2: Scheduler And Sync Use Case

- [ ] **Step 2.1: Add bounded window scheduler**

New file: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_sync_scheduler.py`

Required public function:

```python
def ensure_due_macro_sync_windows(
    *,
    repos: RepositorySession,
    source_name: str,
    bundle_name: str,
    now: date,
    now_ms: int,
    bootstrap_lookback_days: int,
    max_window_days: int,
    steady_overlap_days: int,
    steady_interval_seconds: float,
    max_bootstrap_windows_per_cycle: int,
    max_attempts: int,
) -> dict[str, Any]: ...
```

Rules:

- Use `repos.macro_intel.macro_observations_max_observed_at()` as the only fact freshness probe.
- If no facts exist, enqueue bootstrap windows from `now - bootstrap_lookback_days` to `now`, split by `max_window_days`, capped by `max_bootstrap_windows_per_cycle`.
- If facts exist but are behind `now`, enqueue the gap from `max_observed_at + 1 day` through `now`, split by `max_window_days`.
- Always enqueue a steady overlap window from `now - steady_overlap_days` through `now` when due.
- Duplicate windows coalesce by unique identity and do not churn leases.
- No provider calls in the scheduler.

- [ ] **Step 2.2: Add sync service shared by worker and CLI**

New file: `src/gmgn_twitter_intel/domains/macro_intel/services/macro_sync_service.py`

Required class:

```python
class MacroSyncService:
    def __init__(
        self,
        *,
        settings: object,
        db: Any | None = None,
        repository_factory: Callable[[], AbstractContextManager[RepositorySession]] | None = None,
        runner: MacrodataBundleRunner | None = None,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None: ...

    def enqueue_due_windows(self, *, now_ms: int | None = None) -> dict[str, Any]: ...

    def run_claimed_window_once(self, *, lease_owner: str, now_ms: int | None = None) -> MacroSyncRunSummary | None: ...

    def run_explicit_window_once(
        self,
        *,
        bundle_name: str,
        window_start: date,
        window_end: date,
        trigger_reason: str = "operator_sync",
        lease_owner: str = "macro_cli_sync",
        now_ms: int | None = None,
    ) -> MacroSyncRunSummary: ...
```

Run flow:

1. Claim or enqueue+claim a bounded window inside a short repository session.
2. Close DB session.
3. Execute `MacrodataBundleRunner.history_bundle(...)`.
4. Validate/parse envelope.
5. Open a new repository session and one transaction.
6. Upsert observations, record `macro_import_runs`, record `macro_sync_runs`, and complete/retry/fail the claimed window with stale-completion protection.
7. After commit, call `wake_bus.notify_macro_observations_imported(...)` only when imported observation count is greater than zero.

Failure rules:

- Runner failure records `retryable_error` unless max attempts is reached.
- Missing configured cwd records `config_error` and does not fabricate facts.
- Invalid macrodata envelope records `failed` for that attempt and leaves facts unchanged.
- Secrets are redacted before any run payload reaches repository, logs, CLI, or API.

## Phase 3: Container-Native Macrodata Runner

- [ ] **Step 3.1: Replace `uv run macrodata` with executable resolution**

Modify `src/gmgn_twitter_intel/integrations/macrodata/runner.py:20`.

Add:

```python
def resolve_macrodata_executable(*, environ: Mapping[str, str] | None = None) -> str:
    executable = shutil.which("macrodata", path=(environ or os.environ).get("PATH"))
    if executable:
        return executable
    sibling = Path(sys.executable).parent / "macrodata"
    if sibling.exists() and os.access(sibling, os.X_OK):
        return str(sibling)
    raise MacrodataRunnerError("macrodata executable not found", diagnostics={"error_code": "macrodata_executable_missing"})
```

Runner command:

```python
command = [
    resolve_macrodata_executable(environ=self.environ),
    "bundle",
    "history",
    bundle,
    "--start",
    start,
    "--end",
    end,
]
```

Do not keep the old `["uv", "run", "macrodata", ...]` branch.

- [ ] **Step 3.2: Treat invalid configured cwd as config error**

Modify `_configured_cli_project_dir(...)` or add `_resolve_cli_project_dir(...)`.

Rules:

- `None` means use installed package and no cwd override.
- Existing directory means pass it as `cwd`.
- Missing directory raises `MacrodataRunnerError` with `error_code="macrodata_cli_project_dir_missing"`.

- [ ] **Step 3.3: Keep FRED secret in child env only**

Preserve existing behavior:

- Parent `FRED_API_KEY` is removed before injecting the configured key.
- Configured env var name defaults to `FINANCE_FRED_API_KEY`.
- Diagnostics include `fred_api_key_env` and `fred_api_key_configured`, never the key value.

Add one test where the secret appears in fake stderr and assert it is not copied into diagnostics.

## Phase 4: Runtime Worker Registration And Wake Flow

- [ ] **Step 4.1: Add worker settings**

Modify `src/gmgn_twitter_intel/platform/config/settings.py:1081` and `src/gmgn_twitter_intel/platform/config/settings.py:1434`.

New settings:

```python
class MacroSyncWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=900.0, ge=0)
    soft_timeout_seconds: float = Field(default=180.0, ge=0)
    hard_timeout_seconds: float = Field(default=300.0, ge=0)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026052711
    bundle_name: str = "macro-core"
    source_name: str = "macrodata-cli"
    bootstrap_lookback_days: int = Field(default=1095, ge=1)
    max_window_days: int = Field(default=31, ge=1)
    steady_overlap_days: int = Field(default=7, ge=1)
    max_bootstrap_windows_per_cycle: int = Field(default=1, ge=1)
    lease_ms: int = Field(default=300_000, ge=1)
    retry_delay_ms: int = Field(default=900_000, ge=1)
    max_attempts: int = Field(default=8, ge=1)
```

Add `macro_sync: MacroSyncWorkerSettings = Field(default_factory=MacroSyncWorkerSettings)` to `WorkersSettings`.

Modify default workers YAML at `src/gmgn_twitter_intel/platform/config/settings.py:2146`:

```yaml
macro_sync:
  enabled: true
  interval_seconds: 900.0
  soft_timeout_seconds: 180.0
  hard_timeout_seconds: 300.0
  statement_timeout_seconds: 30.0
  advisory_lock_key: 2026052711
  bundle_name: "macro-core"
  source_name: "macrodata-cli"
  bootstrap_lookback_days: 1095
  max_window_days: 31
  steady_overlap_days: 7
  max_bootstrap_windows_per_cycle: 1
  lease_ms: 300000
  retry_delay_ms: 900000
  max_attempts: 8
macro_view_projection:
  enabled: true
  interval_seconds: 300.0
  batch_size: 250
  statement_timeout_seconds: 30.0
  advisory_lock_key: 2026052109
  wakes_on: ["macro_observations_imported"]
```

Also add `wakes_on` parsing to `MacroViewProjectionWorkerSettings`.

- [ ] **Step 4.2: Add wake bus method**

Modify `src/gmgn_twitter_intel/app/runtime/wake_bus.py:79`.

Add:

```python
def notify_macro_observations_imported(
    self,
    *,
    count: int,
    max_observed_at: str | None,
    asof_date: str | None,
) -> None:
    self._notify(
        "macro_observations_imported",
        {
            "count": int(count),
            "max_observed_at": max_observed_at,
            "asof_date": asof_date,
        },
    )
```

- [ ] **Step 4.3: Add runtime worker**

New file: `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_sync_worker.py`

Required shape:

```python
class MacroSyncWorker(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        service = self._service()
        enqueue_summary = service.enqueue_due_windows(now_ms=now_ms)
        result = service.run_claimed_window_once(lease_owner=self.name, now_ms=now_ms)
        if result is None:
            return WorkerResult(
                processed=0,
                skipped=1,
                notes={
                    "claimed": 0,
                    "provider_calls": 0,
                    "imported_observation_count": 0,
                    **enqueue_summary,
                },
            )
        return WorkerResult(
            processed=1 if result.imported_observation_count else 0,
            failed=0 if result.status in {"ok", "partial"} else 1,
            notes={
                "claimed": 1,
                "provider_calls": 1,
                "sync_run_id": result.sync_run_id,
                "import_run_id": result.import_run_id,
                "status": result.status,
                "imported_observation_count": result.imported_observation_count,
                "max_observed_at": str(result.max_observed_at) if result.max_observed_at else None,
                "asof_date": str(result.asof_date) if result.asof_date else None,
            },
        )
```

Notes must stay compact for worker status.

- [ ] **Step 4.4: Register manifest**

Modify `src/gmgn_twitter_intel/app/runtime/worker_manifest.py:633`.

Add before `macro_view_projection`:

```python
WorkerManifest(
    name="macro_sync",
    domain="macro_intel",
    factory="macro_intel.py",
    lane=WorkerLane.INGEST,
    kind=WorkerKind.FACT_INGEST,
    worker_class="gmgn_twitter_intel.domains.macro_intel.runtime.macro_sync_worker.MacroSyncWorker",
    start_priority=80,
    input_contract=("macro_sync_windows", "macrodata macro-core history bundle"),
    ordering_keys=("source_name", "bundle_name", "window_start", "window_end"),
    writes_facts=("macro_observations",),
    writes_control_plane=("macro_import_runs", "macro_sync_windows", "macro_sync_runs"),
    idempotency_evidence=("macro observation concept/source/series/date identity", "sync window identity"),
    advisory_lock_key="2026052711",
    wakes_out=("macro_observations_imported",),
)
```

Update `macro_view_projection`:

- `input_contract=("macro_observations", "macro_observation_series_rows active generation")`
- `ordering_keys=("concept_key", "series_key", "observed_at")`
- `writes_read_models=("macro_observation_series_rows", "macro_observation_series_active_generation", "macro_view_snapshots")`
- `wakes_on=("macro_observations_imported",)`

- [ ] **Step 4.5: Construct both workers**

Modify `src/gmgn_twitter_intel/app/runtime/worker_factories/macro_intel.py:13`.

Required construction:

```python
if workers.macro_sync.enabled and ctx.settings.macrodata_enabled:
    worker_name = "macro_sync"
    constructed[worker_name] = MacroSyncWorker(
        name=worker_name,
        settings=workers.macro_sync,
        db=ctx.db,
        telemetry=ctx.telemetry,
        settings_root=ctx.settings,
        wake_bus=ctx.wake_bus,
    )

if workers.macro_view_projection.enabled:
    worker_name = "macro_view_projection"
    constructed[worker_name] = MacroViewProjectionWorker(
        name=worker_name,
        settings=workers.macro_view_projection,
        db=ctx.db,
        telemetry=ctx.telemetry,
        wake_waiter=ctx.db.wake_listener(worker_name, workers.macro_view_projection.wakes_on),
    )
```

If `macrodata_enabled` is false, skip `macro_sync` and expose a clear worker factory test that no provider worker is constructed.

## Phase 5: CLI And Status Hard Cut

- [ ] **Step 5.1: Replace CLI sync direct runner branch**

Modify `src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py:63`.

Required behavior:

- `_handle_sync` creates `MacroSyncService`.
- It calls `run_explicit_window_once(...)`.
- It does not instantiate `MacrodataBundleRunner` directly.
- It does not call `import_macrodata_bundle` directly.
- `--project` may still call `_project_once` after sync success for operator repair, but normal runtime freshness must not depend on it.

Expected payload:

```json
{
  "ok": true,
  "data": {
    "fred_api_key_env": "FINANCE_FRED_API_KEY",
    "fred_api_key_configured": false,
    "sync": {
      "sync_run_id": "...",
      "status": "ok",
      "window_start": "2026-05-24",
      "window_end": "2026-05-27",
      "imported_observation_count": 123,
      "max_observed_at": "2026-05-27",
      "asof_date": "2026-05-27"
    },
    "projection": null
  }
}
```

- [ ] **Step 5.2: Expand macro status**

Modify `src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py:117`.

Add repository fields:

- `latest_sync_run`
- `sync_queue`
- `facts_max_observed_at`
- `projection_lag_days`
- `projection_behind_facts`

Required logic:

```python
facts_max = repos.macro_intel.macro_observations_max_observed_at()
latest_snapshot = repos.macro_intel.latest_snapshot(projection_version=MACRO_VIEW_PROJECTION_VERSION)
snapshot_asof = latest_snapshot.get("asof_date") if latest_snapshot else None
projection_behind_facts = facts_max is not None and snapshot_asof is not None and snapshot_asof < facts_max
```

Do not include raw provider output or secrets.

- [ ] **Step 5.3: Keep `import-bundle` as offline replay only**

Keep `macro import-bundle` but document and test that it is not the normal freshness path. It continues using `import_macrodata_bundle(...)` for saved envelopes and never calls providers.

## Phase 6: API Provider-Free Currentness

- [ ] **Step 6.1: Add repository-backed currentness payloads only where already needed**

Modify `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py:105` only if module provenance needs richer status.

Allowed reads:

- `latest_snapshot(...)`
- `latest_observations(...)`
- `latest_import_run()`
- `latest_macro_sync_run()`
- `macro_observations_max_observed_at()`

Forbidden imports/calls in API route files:

- `MacrodataBundleRunner`
- `macrodata`
- `fred`
- provider clients

- [ ] **Step 6.2: Add architecture guard for macro API**

Modify or add `tests/architecture/test_api_read_paths_provider_free.py`.

Required assertion:

```python
route_text = Path("src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py").read_text()
assert "MacrodataBundleRunner" not in route_text
assert "history_bundle" not in route_text
assert "providers.macrodata" not in route_text
```

## Phase 7: Docker Runtime Truth

- [ ] **Step 7.1: Pass env var name without storing secret**

Modify `compose.yaml:95`.

Add to app service environment:

```yaml
FINANCE_FRED_API_KEY: ${FINANCE_FRED_API_KEY:-}
```

Do not add any real key, `.env` assumption, or repository fixture.

- [ ] **Step 7.2: Ensure package runtime path works**

No Dockerfile change should be needed if `macrodata-cli` remains a packaged dependency from `uv.lock`. Keep architecture test `tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source` passing.

Add a smoke verification command to this plan's acceptance section:

```bash
docker compose exec app /app/.venv/bin/macrodata --help
```

## Phase 8: Documentation

- [ ] **Step 8.1: Update Macro Intel domain architecture**

Modify `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md:3`.

Replace batch-first language with:

- `macro_sync` is the normal runtime fact-ingest owner.
- `import-bundle` is offline replay/seed only.
- `macro_view_projection` remains read-model writer.
- Docker runtime uses packaged macrodata executable, not `uv run`.

- [ ] **Step 8.2: Update worker inventory**

Modify `docs/WORKERS.md`.

Add `macro_sync` to Macro Intel:

- lane: fact ingest
- owned writes: `macro_observations`, `macro_import_runs`, `macro_sync_windows`, `macro_sync_runs`
- wake out: `macro_observations_imported`
- idle behavior: claim no due window, no provider IO, no broad fact scan

Update `macro_view_projection` entry:

- input: facts/projected rows
- wake on: `macro_observations_imported`
- writes read models only

- [ ] **Step 8.3: Update setup/contracts docs**

Modify:

- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/SETUP.md`
- `docs/RELIABILITY.md`

Required notes:

- `~/.gmgn-twitter-intel/config.yaml` stores macrodata env var names, not secrets.
- Docker operators must provide `FINANCE_FRED_API_KEY` through environment or deployment secret manager.
- Macro status distinguishes sync freshness, fact freshness, and projection freshness.
- API read paths are provider-free.

## Phase 9: Verification And Acceptance

- [ ] **AC1: Bootstrap windows are bounded and automatic**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_scheduler.py::test_scheduler_bootstrap_partitions_missing_history_into_bounded_windows -q
```

Expected: enqueues finite windows no larger than `max_window_days`, capped by `max_bootstrap_windows_per_cycle`.

- [ ] **AC2: New upstream observations are imported without manual import**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py::test_worker_import_success_writes_facts_completes_window_and_wakes_projection -q
```

Expected: fake runner envelope advances `macro_observations`; no `macro import-bundle` command is invoked.

- [ ] **AC3: Projection wakes or catches up after fact import**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py::test_worker_import_success_writes_facts_completes_window_and_wakes_projection tests/unit/test_bootstrap_worker_runtime_wiring.py -q
```

Expected: `WakeBus.notify_macro_observations_imported` called and `macro_view_projection` constructed with `wake_waiter`.

- [ ] **AC4: Idle cycle has no provider IO or broad fact scan**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py::test_worker_idle_claims_no_window_and_does_not_call_runner tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py -q
```

Expected: `provider_calls=0`, `claimed=0`, claim query touches `macro_sync_windows`, not `macro_observations`.

- [ ] **AC5: Docker path does not use `uv` or host checkout**

```bash
uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runner_injects_fred_env_without_exposing_secret tests/unit/test_cli_macro_commands.py::test_macrodata_runner_rejects_missing_configured_cli_project_dir -q
rg -n '"uv"|uv run macrodata|macrodata-cli' src/gmgn_twitter_intel/integrations/macrodata src/gmgn_twitter_intel/domains/macro_intel/runtime
```

Expected: tests pass; `rg` finds no runtime `uv run macrodata` branch.

- [ ] **AC6: Secrets stay out of argv/logs/DB/API**

```bash
uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runner_injects_fred_env_without_exposing_secret tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_redacts_secret_from_run_payload_and_diagnostics -q
```

Expected: secret appears only in fake child env, never in diagnostics or JSON output.

- [ ] **AC7: Provider/config failure records source health**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py::test_worker_provider_failure_records_retry_without_fabricating_facts -q
```

Expected: retry/config error audit exists; observations list unchanged.

- [ ] **AC8: Macro HTTP routes remain provider-free**

```bash
uv run pytest tests/architecture/test_api_read_paths_provider_free.py -q
```

Expected: macro routes contain no provider runner/import path.

- [ ] **AC9: CLI sync uses same sync use case**

```bash
uv run pytest tests/unit/test_cli_macro_commands.py::test_macro_sync_imports_runner_envelope_without_projection tests/unit/test_cli_macro_commands.py::test_macro_sync_optionally_projects_after_import -q
```

Expected: tests patch `MacroSyncService`, not `MacrodataBundleRunner`, in CLI command module.

- [ ] **AC10: Worker ownership is enforced**

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
```

Expected: `macro_sync` is fact ingest; `macro_view_projection` is read-model projection only.

- [ ] **Full targeted regression**

```bash
uv run ruff check src/gmgn_twitter_intel tests
uv run pytest tests/unit/domains/macro_intel tests/unit/test_cli_macro_commands.py tests/unit/test_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_api_read_paths_provider_free.py -q
```

- [ ] **Docker/live smoke**

```bash
docker compose build app
docker compose up -d postgres migrate app
docker compose exec app /app/.venv/bin/macrodata --help
docker compose exec app /app/.venv/bin/gmgn-twitter-intel config
docker compose exec app /app/.venv/bin/gmgn-twitter-intel macro status
curl -s http://localhost:8765/api/macro | jq '.ok, .data.snapshot.asof_date, .data.source_coverage'
```

Expected:

- Config reports `/root/.gmgn-twitter-intel/...` paths inside container.
- `macro status` includes `latest_sync_run`, `facts_max_observed_at`, and `projection_behind_facts`.
- No secret value appears in stdout.
- `/api/macro` responds from read models.

## PR Breakdown

1. **PR 1 — Macro sync control plane:** migration, repository methods, importer split, red/green repository tests. Mergeable with no worker enabled if manifest registration is held until PR 2.
2. **PR 2 — Runtime worker hard cut:** container-native runner, sync scheduler/service, `MacroSyncWorker`, wake bus method, settings, factory, manifest. Depends on PR 1.
3. **PR 3 — CLI/status/API contracts:** CLI sync delegates to service, status shows sync/fact/projection freshness, macro routes stay provider-free, docs updated. Depends on PR 2.
4. **PR 4 — Docker/live verification:** compose env passthrough, generated CLI docs if required, Docker smoke evidence, final verification artefact. Depends on PR 3.

## Rollout Order

1. Merge and apply migration.
2. Deploy code with `macro_sync.enabled=true` but with conservative `max_bootstrap_windows_per_cycle=1`.
3. Confirm `macro_sync` status shows claimed/imported windows or explicit source-health errors.
4. Confirm `macro_view_projection` wakes or catches up and `projection_behind_facts=false`.
5. Confirm `/api/macro` `asof_date` advances after fact import.
6. Increase `max_bootstrap_windows_per_cycle` only if provider rate and DB load are healthy.

## Rollback

- Disable `workers.macro_sync.enabled` to stop provider ingestion. Existing facts and read models remain usable.
- Leave migration tables in place during rollback; they are control/audit state and do not affect API read paths.
- If a bad sync imported incorrect facts, use a targeted operator repair migration or SQL delete by `source_name`, `series_key`, and `observed_at` range, then rerun `macro_view_projection`. Do not add a runtime fallback.
- Downgrade migration is safe only before relying on sync audit history. After production sync runs exist, prefer disabling the worker over dropping audit tables.

## Verification Artefact

Before declaring complete, create:

`docs/superpowers/plans/active/2026-05-27-macro-sync-worker-hard-cut-verification-cn.md`

It must include:

- exact commit/branch/worktree
- all commands from Phase 9 with pass/fail output
- Docker smoke output with secrets redacted
- latest `macro status` summary showing sync/fact/projection freshness separately
- any known provider data gaps such as naturally lagged monthly/quarterly series
