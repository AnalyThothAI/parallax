# Earnings Hard Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the unfinished earnings/equity-event product completely: backend runtime, frontend surface, API contracts, tests, config, and live PostgreSQL tables/data.

**Architecture:** Treat `equity_event_intel` as a product-owned vertical and remove it by ownership boundary. Preserve shared stock/equity infrastructure that is not owned by the earnings route, especially `us_equity_symbol_universe` and `/stocks`. Use one destructive Alembic migration at the current head to drop the historical tables after runtime references are removed.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic settings, Alembic/PostgreSQL, React/Vite/TypeScript, OpenAPI generated via `make regen-contract`, pytest, Vitest.

---

## File Structure

### Create

- `tests/architecture/test_earnings_hard_delete_contracts.py`: absence guard for deleted product/runtime/config/docs references.
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0124_drop_equity_event_intel.py`: destructive schema cleanup.

### Delete

- `src/gmgn_twitter_intel/domains/equity_event_intel/`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py`
- `src/gmgn_twitter_intel/integrations/equity_events/`
- `src/gmgn_twitter_intel/integrations/openai_agents/equity_event_brief_agent_client.py`
- `web/src/features/equity-events/`
- `web/src/routes/equity-events.route.tsx`
- `web/tests/routes/equity-events.route.test.tsx`
- `web/tests/unit/lib/apiClient.equityEvents.test.ts`
- `web/tests/unit/features/equity-events/`
- `tests/unit/domains/equity_event_intel/`
- `tests/integration/domains/equity_event_intel/`
- `tests/integration/test_equity_event_workers.py`
- `tests/integration/test_equity_event_repository.py`
- `tests/unit/test_api_equity_events_contract.py`
- `tests/unit/test_equity_event_provider_wiring.py`
- `tests/architecture/test_equity_event_intel_boundaries.py`
- `tests/architecture/test_equity_event_hard_cut_contracts.py`

### Modify

- Backend runtime/API/config: `src/gmgn_twitter_intel/app/runtime/app.py`, `src/gmgn_twitter_intel/app/surfaces/api/http.py`, `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`, `src/gmgn_twitter_intel/app/runtime/repository_session.py`, `src/gmgn_twitter_intel/app/runtime/provider_wiring/__init__.py`, `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`, `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`, `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`, `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`, `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`, `src/gmgn_twitter_intel/app/runtime/queue_health.py`, `src/gmgn_twitter_intel/app/runtime/wake_bus.py`, `src/gmgn_twitter_intel/platform/config/settings.py`, `config.example.yaml`.
- Frontend: `web/src/routes/router.tsx`, `web/src/features/cockpit/ui/appNavigation.ts`, `web/src/shared/routing/paths.ts`, `web/src/shared/query/queryKeys.ts`, `web/src/lib/api/client.ts`, `web/tests/e2e/support/mockApi.ts`, any equity-event fixtures imported by remaining tests.
- Architecture/unit/integration tests that reference the removed runtime: `tests/architecture/test_src_domain_architecture.py`, `tests/architecture/test_worker_runtime_contracts.py`, `tests/architecture/test_runtime_worker_constraint_hard_cut.py`, `tests/architecture/test_workerspace_runtime_contracts.py`, `tests/architecture/test_projection_worker_idle_cost_contract.py`, `tests/architecture/test_runtime_lifecycle_hard_cut.py`, `tests/architecture/test_runtime_performance_architecture_hard_cut.py`, `tests/architecture/test_token_equity_workerspace_root_fix_contract.py`, `tests/architecture/test_project_structure.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_providers_wiring.py`, `tests/unit/test_provider_wiring_agent_execution_gateway.py`, `tests/unit/test_bootstrap_worker_runtime_wiring.py`, `tests/unit/test_worker_status.py`, `tests/unit/test_ops_projection_dirty_targets.py`, `tests/unit/test_pulse_agent_routing.py`, `tests/integration/test_api_static.py`, `tests/integration/test_postgres_schema_runtime.py`.
- Docs/generated: `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/WORKERS.md`, `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`, `docs/generated/db-schema.md` if Postgres schema regeneration is available.

---

### Task 1: Add Hard-Delete Guard Tests

**Files:**
- Create: `tests/architecture/test_earnings_hard_delete_contracts.py`

- [ ] **Step 1: Write the failing architecture guard**

Create `tests/architecture/test_earnings_hard_delete_contracts.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DELETED_PATHS = (
    ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel",
    ROOT / "src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py",
    ROOT / "src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py",
    ROOT / "src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py",
    ROOT / "src/gmgn_twitter_intel/integrations/equity_events",
    ROOT / "src/gmgn_twitter_intel/integrations/openai_agents/equity_event_brief_agent_client.py",
    ROOT / "web/src/features/equity-events",
    ROOT / "web/src/routes/equity-events.route.tsx",
)

SOURCE_SCAN_ROOTS = (
    ROOT / "src/gmgn_twitter_intel/app",
    ROOT / "src/gmgn_twitter_intel/platform",
    ROOT / "src/gmgn_twitter_intel/integrations",
    ROOT / "web/src",
)

CANONICAL_DOCS = (
    ROOT / "config.example.yaml",
    ROOT / "docs/ARCHITECTURE.md",
    ROOT / "docs/CONTRACTS.md",
    ROOT / "docs/FRONTEND.md",
    ROOT / "docs/WORKERS.md",
)

FORBIDDEN_RUNTIME_TOKENS = (
    "equity_event_intel",
    "routes_equity_events",
    "EquityEventIntel",
    "EquityEventBrief",
    "EquityEventDocument",
    "equity_event.brief",
    "equity_event_source_reconcile",
    "equity_event_fetch",
    "equity_event_evidence_hydration",
    "equity_event_process",
    "equity_event_story_projection",
    "equity_event_page_projection",
    "equity_event_brief",
    "/api/equity-events",
    "/earnings",
)

FORBIDDEN_DOC_TOKENS = (
    "equity_event_intel",
    "/api/equity-events",
    "/earnings",
    "equity_event.brief",
    "equity_event_",
)


def test_deleted_earnings_product_paths_are_absent() -> None:
    assert [str(path.relative_to(ROOT)) for path in DELETED_PATHS if path.exists()] == []


def test_runtime_and_frontend_no_longer_reference_earnings_product() -> None:
    offenders: list[str] = []
    for path in _text_files(SOURCE_SCAN_ROOTS):
        if "/platform/db/alembic/versions/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert offenders == []


def test_canonical_docs_and_example_config_do_not_advertise_earnings_product() -> None:
    offenders: list[str] = []
    for path in CANONICAL_DOCS:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_DOC_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert offenders == []


def _text_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".css", ".yaml", ".yml"}:
                files.append(path)
    return files
```

- [ ] **Step 2: Run the guard and verify it fails on current code**

Run:

```bash
uv run python -m pytest tests/architecture/test_earnings_hard_delete_contracts.py -q
```

Expected: FAIL. The failure should list existing `equity_event_intel`, `/earnings`, and `/api/equity-events` references.

- [ ] **Step 3: Commit the failing guard only if this branch uses TDD commits**

Run:

```bash
git add tests/architecture/test_earnings_hard_delete_contracts.py
git commit -m "test: guard earnings hard delete"
```

Expected: commit succeeds. If the implementation branch prefers only passing commits, leave the file unstaged until Task 8 makes it pass.

---

### Task 2: Clean Operator Runtime Config Before Schema Removal

**Files:**
- Modify outside repo: `~/.gmgn-twitter-intel/config.yaml`
- Modify outside repo: `~/.gmgn-twitter-intel/workers.yaml`

- [ ] **Step 1: Confirm active config paths while old schema still loads**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected: command prints `config_path` and `workers_config_path` under `~/.gmgn-twitter-intel/`. Do not copy secret values into notes or commits.

- [ ] **Step 2: Remove only deleted earnings keys with backups**

Run this structured YAML cleanup:

```bash
uv run python - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import yaml

home = Path.home() / ".gmgn-twitter-intel"
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
targets = {
    home / "config.yaml": ("equity_event_intel",),
    home / "workers.yaml": (
        "equity_event_source_reconcile",
        "equity_event_fetch",
        "equity_event_evidence_hydration",
        "equity_event_process",
        "equity_event_story_projection",
        "equity_event_brief",
        "equity_event_page_projection",
    ),
}

for path, keys in targets.items():
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not a YAML mapping")
    removed = [key for key in keys if key in data]
    if not removed:
        print(f"{path}: removed=0 backup=none")
        continue
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    for key in removed:
        data.pop(key, None)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    print(f"{path}: removed={len(removed)} backup={backup}")
PY
```

Expected: prints only paths, removal counts, and backup paths. It must not print YAML contents.

- [ ] **Step 3: Re-run config command**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected: PASS with the same config paths. The output should not include `equity_event_intel` or `equity_event_*` worker sections.

---

### Task 3: Remove Backend Runtime, Provider, Repository, and API References

**Files:**
- Delete: backend files listed in File Structure
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/__init__.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/wake_bus.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`

- [ ] **Step 1: Delete backend product-owned files**

Run:

```bash
rm -rf \
  src/gmgn_twitter_intel/domains/equity_event_intel \
  src/gmgn_twitter_intel/integrations/equity_events
rm -f \
  src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py \
  src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py \
  src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py \
  src/gmgn_twitter_intel/integrations/openai_agents/equity_event_brief_agent_client.py
```

Expected: files/directories are removed.

- [ ] **Step 2: Remove API route registration**

Edit `src/gmgn_twitter_intel/app/surfaces/api/http.py` so the import block and router include list no longer mention `routes_equity_events`. The final include sequence should keep the remaining routes:

```python
router.include_router(routes_status.create_router(readiness_payload))
router.include_router(routes_token_images.router)
router.include_router(routes_events.router)
router.include_router(routes_watchlist.router)
router.include_router(routes_search.router)
router.include_router(routes_radar.router)
router.include_router(routes_cex.router)
router.include_router(routes_macro.router)
router.include_router(routes_news.router)
router.include_router(routes_notifications.router)
router.include_router(routes_ops.router)
router.include_router(routes_social_enrichment.router)
router.include_router(routes_pulse.router)
```

- [ ] **Step 3: Remove backend SPA fallback for `/earnings`**

Edit `src/gmgn_twitter_intel/app/runtime/app.py` and remove only these two registrations:

```python
app.add_api_route("/earnings", frontend_index, include_in_schema=False)
app.add_api_route("/earnings/{path:path}", frontend_index, include_in_schema=False)
```

- [ ] **Step 4: Remove repository session dependency**

Edit `src/gmgn_twitter_intel/app/runtime/repository_session.py`:

```python
# Remove these imports:
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_projection_dirty_target_repository import (
    EquityProjectionDirtyTargetRepository,
)
```

Remove the `equity_events` field from the repository bundle dataclass and remove `equity_events=EquityEventRepository(conn)` from repository construction. Remove any equity-event dirty-target repository field if present. After the edit, no code in `repository_session.py` should contain `equity_event` or `equity_events`.

- [ ] **Step 5: Remove provider wiring types**

Edit `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py` so there is no import from `gmgn_twitter_intel.domains.equity_event_intel.providers`, no `EquityEventIntelProviders` dataclass, no `equity_event_intel` field in `WiredProviders`, and no `EquityEventIntelProviders` entry in `__all__`.

Edit `src/gmgn_twitter_intel/app/runtime/provider_wiring/__init__.py` so `wire_providers` no longer imports `equity_events`, no longer passes `equity_event_intel=...`, and no longer calls `openai.openai_equity_event_brief_provider`.

Edit `src/gmgn_twitter_intel/app/runtime/providers_wiring.py` and remove `EquityEventIntelProviders` from imports and `__all__`.

- [ ] **Step 6: Remove OpenAI equity brief provider**

Edit `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`:

```python
# Remove this import:
from gmgn_twitter_intel.integrations.openai_agents.equity_event_brief_agent_client import (
    OpenAIAgentsEquityEventBriefClient,
)

# Remove this function:
def openai_equity_event_brief_provider(...):
    ...

# Remove these __all__ entries:
"OpenAIAgentsEquityEventBriefClient",
"openai_equity_event_brief_provider",
```

- [ ] **Step 7: Remove worker factory registration**

Edit `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py` and remove imports of `WORKER_KEYS as EQUITY_EVENT_INTEL_KEYS`, `construct_equity_event_intel_workers`, and the `WorkerFactorySpec("equity_event_intel.py", ...)` tuple entry.

- [ ] **Step 8: Remove worker manifests, queue health, and wake methods**

Edit `src/gmgn_twitter_intel/app/runtime/worker_manifest.py` and delete all seven `WorkerManifest(...)` entries whose names start with `equity_event_`.

Edit `src/gmgn_twitter_intel/app/runtime/queue_health.py` and remove:

```python
"equity_event_evidence_jobs"
"equity_event_process_jobs"
"equity_event_projection_dirty_targets"
("equity_event_projection_dirty_targets", "equity_event_story_projection")
("equity_event_projection_dirty_targets", "equity_event_brief")
("equity_event_projection_dirty_targets", "equity_event_page_projection")
```

Edit `src/gmgn_twitter_intel/app/runtime/wake_bus.py` and remove the seven `notify_equity_event_*` methods. After the edit, `wake_bus.py` should not contain `equity_event`.

- [ ] **Step 9: Remove API schema classes**

Edit `src/gmgn_twitter_intel/app/surfaces/api/schemas.py` and delete:

```python
class EquityEventsData(ApiSchema): ...
class EquityEventObjectData(ApiSchema): ...
class EquityEventCalendarData(ApiSchema): ...
class EquityEventTimelineData(ApiSchema): ...
class EquityEventSourceStatusData(ApiSchema): ...
class EquityEventSummaryData(ApiSchema): ...
```

- [ ] **Step 10: Run backend import checks**

Run:

```bash
uv run python -m compileall src/gmgn_twitter_intel/app src/gmgn_twitter_intel/platform src/gmgn_twitter_intel/integrations
uv run python -m pytest tests/architecture/test_earnings_hard_delete_contracts.py -q
```

Expected: compileall may still fail later because settings/frontend/tests are not cleaned yet. The guard should have fewer failures than in Task 1 and no failures from deleted backend paths.

- [ ] **Step 11: Commit backend runtime removal**

Run:

```bash
git add src/gmgn_twitter_intel
git commit -m "refactor: remove earnings backend runtime"
```

Expected: commit succeeds if the branch uses incremental commits. If tests are still intentionally failing pending frontend/config cleanup, include that status in the commit body or defer the commit until Task 8.

---

### Task 4: Remove Config Schema, Defaults, and Example YAML

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `config.example.yaml`
- Modify tests that construct or assert worker settings.

- [ ] **Step 1: Remove config model classes**

Edit `src/gmgn_twitter_intel/platform/config/settings.py` and delete the following classes:

```python
class EquityEventCompanySettings(BaseModel): ...
class EquityExpectedEventSettings(BaseModel): ...
class EquityEventAgentSettings(BaseModel): ...
class EquityEventIntelSettings(BaseModel): ...
class EquityEventSourceReconcileWorkerSettings(PerWorkerSettings): ...
class EquityEventFetchWorkerSettings(PerWorkerSettings): ...
class EquityEventEvidenceHydrationWorkerSettings(PerWorkerSettings): ...
class EquityEventProcessWorkerSettings(PerWorkerSettings): ...
class EquityEventStoryProjectionWorkerSettings(PerWorkerSettings): ...
class EquityEventBriefWorkerSettings(PerWorkerSettings): ...
class EquityEventPageProjectionWorkerSettings(PerWorkerSettings): ...
```

- [ ] **Step 2: Remove config fields and computed property**

In `Settings`, remove:

```python
equity_event_intel: EquityEventIntelSettings = Field(default_factory=EquityEventIntelSettings)

@property
def equity_event_brief_configured(self) -> bool:
    return bool(self.llm_api_key and self.agent_runtime_model_for_lane(self.equity_event_intel.agent.lane))
```

In `WorkersSettings`, remove all seven fields whose names start with `equity_event_`.

In the default agent runtime lane map, remove:

```python
"equity_event.brief": AgentLaneSettings(priority="low", max_concurrency=1, timeout_seconds=180.0),
```

- [ ] **Step 3: Remove generated YAML sections**

In `default_config_yaml()`, remove this entire block:

```yaml
equity_event_intel:
  enabled: false
  default_universe: "nasdaq_tech"
  sec_user_agent:
  companies: []
  expected_events: []
  agent:
    enabled: true
    lane: "equity_event.brief"
```

In `default_workers_yaml()`, remove all blocks from `equity_event_source_reconcile:` through `equity_event_page_projection:`.

In `config.example.yaml`, remove the same `equity_event_intel` and `equity_event_*` worker blocks.

- [ ] **Step 4: Remove validators that only serve deleted config**

At the bottom of `settings.py`, remove helper validators that mention `equity_event_intel.companies.cik` if no remaining setting calls them. Keep `_parse_optional_cik` only if another config class still uses it.

- [ ] **Step 5: Update config tests**

Edit `tests/unit/test_worker_settings.py`:

- Remove tests that assert `expected_event_id`, `event_type="earnings_release"`, `source_id="config:earnings"`, or `equity_event_*` worker settings.
- Add this assertion to an existing default-config test or create a small new test in the same file:

```python
def test_default_config_excludes_deleted_earnings_settings() -> None:
    config_yaml = default_config_yaml()
    workers_yaml = default_workers_yaml()

    assert "equity_event_intel" not in config_yaml
    assert "equity_event.brief" not in config_yaml
    assert "equity_event_" not in workers_yaml
```

Ensure the test imports `default_config_yaml` and `default_workers_yaml` from `gmgn_twitter_intel.platform.config.settings`.

- [ ] **Step 6: Run config tests**

Run:

```bash
uv run python -m pytest tests/unit/test_worker_settings.py -q
uv run gmgn-twitter-intel config
```

Expected: tests pass; config command succeeds after Task 2 cleaned operator YAML.

- [ ] **Step 7: Commit config cleanup**

Run:

```bash
git add src/gmgn_twitter_intel/platform/config/settings.py config.example.yaml tests/unit/test_worker_settings.py
git commit -m "refactor: remove earnings runtime config"
```

Expected: commit succeeds.

---

### Task 5: Add Destructive Database Migration

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0124_drop_equity_event_intel.py`
- Modify: schema tests only if they assert old equity-event tables exist.

- [ ] **Step 1: Create drop migration**

Create `src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0124_drop_equity_event_intel.py`:

```python
"""Drop retired equity event intel schema."""

from __future__ import annotations

from alembic import op

revision = "20260529_0124"
down_revision = "20260529_0123"
branch_labels = None
depends_on = None

DROP_TABLES = (
    "equity_event_process_jobs",
    "equity_event_evidence_jobs",
    "equity_event_projection_dirty_targets",
    "equity_event_brief_states",
    "equity_event_evidence_artifacts",
    "equity_company_timeline_rows",
    "equity_event_alert_candidates",
    "equity_event_calendar_rows",
    "equity_event_page_rows",
    "equity_event_agent_briefs",
    "equity_event_agent_runs",
    "equity_event_story_members",
    "equity_event_story_groups",
    "equity_event_fact_candidates",
    "equity_event_source_spans",
    "equity_company_events",
    "equity_section_diffs",
    "equity_document_revisions",
    "equity_event_documents",
    "equity_provider_documents",
    "equity_expected_events",
    "equity_event_universe_members",
    "equity_event_fetch_runs",
    "equity_event_sources",
)


def upgrade() -> None:
    for table in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    """This hard delete is intentionally non-restorative."""
```

- [ ] **Step 2: Update schema/runtime tests**

Edit tests that assert equity-event schema ownership or runtime tables:

- `tests/architecture/test_worker_runtime_contracts.py`: remove equity-event table ownership entries and `equity_event_intel.py` worker factory expectations.
- `tests/integration/test_postgres_schema_runtime.py`: remove expected equity-event table/index assertions.
- `tests/unit/test_ops_projection_dirty_targets.py`: remove `equity_event_projection_dirty_targets` expectations and fake cursor branches.

Do not remove assertions for `us_equity_symbol_universe`.

- [ ] **Step 3: Run migration on the local configured database**

Run:

```bash
uv run gmgn-twitter-intel db migrate
```

Expected: migration reaches head `20260529_0124`.

- [ ] **Step 4: Verify dropped tables are absent**

Run:

```bash
uv run python - <<'PY'
from __future__ import annotations

from gmgn_twitter_intel.platform.config.settings import load_settings
from gmgn_twitter_intel.platform.db.postgres_client import connect_sync, with_password_from_file

settings = load_settings(require_ws_token=False)
dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
with connect_sync(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND (
                table_name LIKE 'equity_event_%'
                OR table_name IN (
                    'equity_expected_events',
                    'equity_company_events',
                    'equity_company_timeline_rows',
                    'equity_provider_documents',
                    'equity_document_revisions',
                    'equity_section_diffs'
                )
              )
            ORDER BY table_name
            """
        )
        rows = [row[0] for row in cur.fetchall()]
print(rows)
raise SystemExit(1 if rows else 0)
PY
```

Expected: prints `[]` and exits 0.

- [ ] **Step 5: Regenerate DB schema docs if the local database is available**

Run:

```bash
uv run python scripts/regen_db_schema.py
```

Expected: `docs/generated/db-schema.md` no longer lists dropped equity-event tables. If this command cannot connect to Postgres, record the exact connection failure in the implementation summary and rely on the migration verification from Step 4.

- [ ] **Step 6: Commit DB cleanup**

Run:

```bash
git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0124_drop_equity_event_intel.py docs/generated/db-schema.md tests/architecture/test_worker_runtime_contracts.py tests/integration/test_postgres_schema_runtime.py tests/unit/test_ops_projection_dirty_targets.py
git commit -m "db: drop earnings event schema"
```

Expected: commit succeeds. If `docs/generated/db-schema.md` did not change because regeneration was unavailable, omit it from `git add`.

---

### Task 6: Remove Frontend Route, API Client, Fixtures, and Tests

**Files:**
- Delete frontend files listed in File Structure
- Modify frontend files listed in File Structure

- [ ] **Step 1: Delete equity-event frontend files and tests**

Run:

```bash
rm -rf \
  web/src/features/equity-events \
  web/tests/unit/features/equity-events
rm -f \
  web/src/routes/equity-events.route.tsx \
  web/tests/routes/equity-events.route.test.tsx \
  web/tests/unit/lib/apiClient.equityEvents.test.ts
```

Expected: files/directories are removed.

- [ ] **Step 2: Remove React route and nav entry**

Edit `web/src/routes/router.tsx` and delete:

```tsx
{
  path: "earnings/*",
  lazy: () => import("./equity-events.route"),
},
```

Edit `web/src/features/cockpit/ui/appNavigation.ts` and delete the `Earnings` navigation item:

```tsx
{
  icon: CalendarDays,
  label: "Earnings",
  matchPath: "/earnings/*",
  to: "/earnings",
},
```

Remove the `CalendarDays` import if no remaining nav item uses it.

- [ ] **Step 3: Remove routing helpers and query keys**

Edit `web/src/shared/routing/paths.ts` and delete:

```ts
export function earningsPath(): string {
  return "/earnings";
}

export function earningsCalendarPath(): string {
  return "/earnings/calendar";
}

export function equityEventDetailPath(eventId: string): string {
  return `/earnings/events/${encodeURIComponent(eventId)}`;
}
```

Edit `web/src/shared/query/queryKeys.ts` and remove the `equityEvents` key factory and any `"equity-events"` literals.

- [ ] **Step 4: Remove API client functions and normalizers**

Edit `web/src/lib/api/client.ts`:

- Remove imports from `@features/equity-events`.
- Delete `fetchEquityEvents`, `fetchEquityEventDetail`, `fetchEquityEventCalendar`, and `fetchEquityEventSummary`.
- Delete all normalizers whose names start with `normalizeEquityEvent` or `normalizeEquityCalendar`.

After the edit, this command should print nothing:

```bash
rg -n "EquityEvent|equity-events|/api/equity-events|normalizeEquity" web/src/lib/api/client.ts
```

- [ ] **Step 5: Remove mock API equity-event handlers**

Edit `web/tests/e2e/support/mockApi.ts` and remove routes for:

```ts
"/api/equity-events"
"/api/equity-events/calendar"
"/api/equity-events/summary"
path.startsWith("/api/equity-events/")
```

Remove equity-event fixture builders in that file if no remaining tests import them.

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd web && npm run typecheck && npm run lint && npm run test -- --run
```

Expected: PASS. If failures mention deleted `equity-events` imports, remove the stale import or stale test expectation and rerun the same command.

- [ ] **Step 7: Commit frontend cleanup**

Run:

```bash
git add web
git commit -m "refactor: remove earnings frontend"
```

Expected: commit succeeds.

---

### Task 7: Remove or Rewrite Stale Tests and Architecture Contracts

**Files:**
- Delete stale tests listed in File Structure
- Modify architecture/unit/integration tests listed in File Structure

- [ ] **Step 1: Delete backend tests owned entirely by equity-event product**

Run:

```bash
rm -rf \
  tests/unit/domains/equity_event_intel \
  tests/integration/domains/equity_event_intel
rm -f \
  tests/integration/test_equity_event_workers.py \
  tests/integration/test_equity_event_repository.py \
  tests/unit/test_api_equity_events_contract.py \
  tests/unit/test_equity_event_provider_wiring.py \
  tests/architecture/test_equity_event_intel_boundaries.py \
  tests/architecture/test_equity_event_hard_cut_contracts.py
```

Expected: product-owned tests are removed.

- [ ] **Step 2: Update domain architecture tests**

Edit `tests/architecture/test_src_domain_architecture.py`:

- Remove `"equity_event_intel"` from `DOMAINS`.
- Remove `"equity_event_intel"` from `PROVIDER_DOMAINS`.

Do not remove `"asset_market"` or any US equity symbol test.

- [ ] **Step 3: Update worker/runtime architecture tests**

For each file below, remove only expectations tied to deleted equity-event workers, tables, dirty-target queues, and provider I/O:

- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- `tests/architecture/test_workerspace_runtime_contracts.py`
- `tests/architecture/test_projection_worker_idle_cost_contract.py`
- `tests/architecture/test_runtime_lifecycle_hard_cut.py`
- `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- `tests/architecture/test_token_equity_workerspace_root_fix_contract.py`
- `tests/architecture/test_project_structure.py`

Use this check after editing:

```bash
rg -n "equity_event|equity-event|equity_events|earnings" tests/architecture
```

Expected: only `tests/architecture/test_earnings_hard_delete_contracts.py` should remain, plus unrelated English `earnings` text if any.

- [ ] **Step 4: Update runtime and provider unit tests**

Edit these files and remove equity-event-specific setup/assertions:

- `tests/unit/test_providers_wiring.py`
- `tests/unit/test_provider_wiring_agent_execution_gateway.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/unit/test_worker_status.py`
- `tests/unit/test_pulse_agent_routing.py`

For provider wiring tests, the expected `WiredProviders` shape should no longer include `equity_event_intel`. Keep assertions for news, pulse, watchlist, macrodata, asset market, and ingestion providers.

- [ ] **Step 5: Update static API/frontend integration tests**

Edit `tests/integration/test_api_static.py`:

- Remove `earnings_route = client.get("/earnings")`.
- Remove `/earnings/calendar` and `/earnings/events/event-1` requests.
- Remove assertions that those responses are 200 HTML.

Do not change `/news`, `/macro`, `/watchlist`, `/stocks`, `/token`, or `/signal-lab` assertions.

- [ ] **Step 6: Run backend non-DB tests**

Run:

```bash
uv run python -m pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract" -q
```

Expected: PASS or no tests selected only for a deleted marker subset. Fix stale imports until this command passes.

- [ ] **Step 7: Commit test cleanup**

Run:

```bash
git add tests
git commit -m "test: remove earnings product expectations"
```

Expected: commit succeeds.

---

### Task 8: Update Docs and Generated Contracts

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/generated/openapi.json`
- Modify: `web/src/lib/types/openapi.ts`

- [ ] **Step 1: Remove canonical docs references**

Edit docs:

- `docs/ARCHITECTURE.md`: remove `domains/equity_event_intel` from architecture map and remove equity-event tables from facts/control/read-model lists.
- `docs/CONTRACTS.md`: remove equity-event workers from public worker lists and remove the `/api/equity-events*` API section.
- `docs/FRONTEND.md`: remove the Earnings route ownership section and remove `/earnings`, `/earnings/calendar`, `/earnings/events/:eventId` from reload checklist.
- `docs/WORKERS.md`: remove equity-event worker inventory rows, queue/control-plane references, wake channel rows, and `equity_event.brief` agent lane text.

- [ ] **Step 2: Regenerate OpenAPI and TypeScript contracts**

Run:

```bash
make regen-contract
```

Expected:

- `docs/generated/openapi.json` no longer contains `/api/equity-events`.
- `web/src/lib/types/openapi.ts` no longer contains `EquityEvent`.

- [ ] **Step 3: Verify docs and generated contracts do not advertise the deleted surface**

Run:

```bash
rg -n "equity_event_intel|/api/equity-events|/earnings|equity_event\\.brief|equity_event_" docs/ARCHITECTURE.md docs/CONTRACTS.md docs/FRONTEND.md docs/WORKERS.md docs/generated/openapi.json web/src/lib/types/openapi.ts config.example.yaml
```

Expected: no output.

- [ ] **Step 4: Run contract tests**

Run:

```bash
uv run python -m pytest tests/contract -m contract -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs and generated contracts**

Run:

```bash
git add docs/ARCHITECTURE.md docs/CONTRACTS.md docs/FRONTEND.md docs/WORKERS.md docs/generated/openapi.json web/src/lib/types/openapi.ts
git commit -m "docs: remove earnings product contracts"
```

Expected: commit succeeds.

---

### Task 9: Final Sweep and Verification

**Files:**
- All touched files

- [ ] **Step 1: Run product deletion search**

Run:

```bash
rg -n "equity_event_intel|equity-events|/api/equity-events|/earnings|equity_event\\.brief|equity_event_" src web tests docs config.example.yaml
```

Expected remaining hits:

- Historical Alembic migrations before `20260529_0124`.
- The new drop migration.
- The approved spec and this plan under `docs/superpowers`.
- `tests/architecture/test_earnings_hard_delete_contracts.py`.

Any other hit must be removed or explicitly justified in the final implementation summary.

- [ ] **Step 2: Run Python lint, typing, and architecture gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract"
uv run python -m compileall src tests
```

Expected: PASS.

- [ ] **Step 3: Run frontend gates**

Run:

```bash
cd web && npm run typecheck && npm run lint && npm run format:check && npm run test -- --run
```

Expected: PASS.

- [ ] **Step 4: Run integration checks that cover app routes and DB schema**

Run:

```bash
uv run python -m pytest tests/integration/test_api_static.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected: PASS. `/earnings` should not be asserted as a served SPA route.

- [ ] **Step 5: Verify app config and DB health**

Run:

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel db health
```

Expected: both PASS. Output should report paths and health only; do not paste secret values into the PR/summary.

- [ ] **Step 6: Review git diff for accidental shared-equity deletion**

Run:

```bash
git diff --stat
git diff -- src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0124_drop_equity_event_intel.py
rg -n "us_equity_symbol_universe|stocks-radar|/stocks" src web tests docs
```

Expected: the migration drops only product-owned equity-event tables. Shared `/stocks` and US equity symbol references still exist where they existed before.

- [ ] **Step 7: Commit final sweep if needed**

Run:

```bash
git add .
git commit -m "chore: finish earnings hard delete"
```

Expected: commit succeeds only if there are remaining uncommitted fixes from verification. If the working tree is already clean, do not create an empty commit.

---

## Rollback Notes

- Code rollback is normal git revert of the implementation commits.
- Database rollback is non-restorative. The migration intentionally drops data. Restoring dropped tables/data requires restoring from a database backup taken before `20260529_0124`.
- Operator config backups are created as `config.yaml.bak-<timestamp>` and `workers.yaml.bak-<timestamp>` in `~/.gmgn-twitter-intel/`.

## Completion Criteria

The work is complete when:

- `uv run gmgn-twitter-intel config` succeeds with cleaned operator config.
- `uv run gmgn-twitter-intel db migrate` applies the drop migration.
- The final `rg` sweep has only historical migration/spec/plan/guard-test hits.
- Backend unit/architecture/contract gates pass.
- Frontend typecheck/lint/test gates pass.
- `/earnings` and `/api/equity-events*` are absent from router, nav, OpenAPI, generated TS types, docs, and tests.
