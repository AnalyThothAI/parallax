# Token Radar / Equity Event / WorkerSpace Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved hard cut so Token Radar unchanged projections write zero hot rows, Equity Event processing is driven by durable narrow jobs instead of fact-table polling, and WorkerSpace contracts are enforced on production worker paths.

**Architecture:** Keep PostgreSQL as the single material truth store, but split facts, control rows, and read models cleanly. Token Radar separates source-edge state from latest market context; Equity Event introduces a leased process queue and narrow process packets; WorkerSpace becomes a thin runtime guard around claim, payload load, DB session/transaction depth, provider IO, and current read-model publishing.

**Tech Stack:** Python 3.13, PostgreSQL 18, psycopg, Alembic, pytest, Docker Compose, project WorkerBase/WorkerScheduler runtime.

**Owning Spec:** `docs/superpowers/specs/active/2026-05-28-token-radar-equity-workerspace-root-fix-cn.md`

**Working Branch:** `codex/token-radar-equity-workerspace-root-fix`

**Worktree:** `.worktrees/token-radar-equity-workerspace-root-fix`

**Status:** Draft plan for approval.

---

## Non-Negotiable Constraints

- Do not handle News in this plan.
- Do not keep old runtime compatibility readers, fallback flags, dual paths, or shadow writers.
- Do not hide load by increasing intervals or lowering concurrency as the primary fix.
- Do not put provider IO inside open DB sessions or DB transactions.
- Do not treat `commit=False` as a transaction on autocommit worker connections; use `repos.unit_of_work()`.
- Do not let `dirty_at_ms`, run ids, generation ids, attempt ids, lease owners, publication timestamps, or freshness-only nested fields drive payload hashes.
- Real-data diagnostics must first confirm `uv run gmgn-twitter-intel config` reports operator-owned paths under `~/.gmgn-twitter-intel/`, and must not print secrets.

## Target File Map

Create:

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py`
- `src/gmgn_twitter_intel/app/runtime/runtime_worker_context.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py`
- `tests/unit/domains/token_intel/test_token_radar_payload_hash.py`
- `tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py`
- `tests/unit/domains/token_intel/test_token_radar_market_only_projection.py`
- `tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py`
- `tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py`
- `tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py`
- `tests/unit/test_runtime_worker_context.py`
- `tests/architecture/test_token_equity_workerspace_root_fix_contract.py`

Modify:

- `src/gmgn_twitter_intel/app/runtime/worker_base.py`
- `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- `src/gmgn_twitter_intel/app/runtime/worker_space.py`
- `src/gmgn_twitter_intel/app/runtime/current_read_model_publisher.py`
- `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
- `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/services/event_classifier.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_submission_normalizer.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/references/POSTGRES_PERFORMANCE.md`

## Task 0: Worktree And Runtime Baseline Gate

**Files:**
- Read: `docs/WORKFLOW.md`
- Read: `docs/references/POSTGRES_PERFORMANCE.md`
- Read: `docs/superpowers/specs/active/2026-05-28-token-radar-equity-workerspace-root-fix-cn.md`

- [ ] **Step 1: Create isolated worktree**

Run from repo root:

```bash
git worktree add .worktrees/token-radar-equity-workerspace-root-fix -b codex/token-radar-equity-workerspace-root-fix main
cd .worktrees/token-radar-equity-workerspace-root-fix
```

Expected: worktree is created on branch `codex/token-radar-equity-workerspace-root-fix`.

- [ ] **Step 2: Verify clean worktree state**

Run:

```bash
git worktree list
git branch --show-current
git status --short
```

Expected:

```text
codex/token-radar-equity-workerspace-root-fix
```

`git status --short` should be empty. If it is not empty, inspect every file before continuing.

- [ ] **Step 3: Confirm live runtime config paths**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected:

- `config_path` points at `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path` points at `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`
- Do not copy secret values into plan, logs, commits, or PR text.

- [ ] **Step 4: Capture pre-change PostgreSQL baseline**

Run:

```bash
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -X -q -P pager=off -c "
SELECT now() - pg_postmaster_start_time() AS uptime;

SELECT relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE relname IN (
  'token_radar_dirty_targets',
  'token_radar_rank_source_events',
  'token_radar_target_features',
  'token_radar_current_rows',
  'equity_event_documents',
  'equity_event_evidence_artifacts',
  'equity_provider_documents',
  'event_anchor_backfill_jobs'
)
ORDER BY relname;

SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%'
   OR query ILIKE '%list_event_documents_for_processing%'
   OR query ILIKE '%equity_event_documents%'
ORDER BY total_exec_time DESC
LIMIT 20;
"
```

Expected: command exits `0`. Save the output into the eventual verification artefact, not this plan.

- [ ] **Step 5: Commit nothing**

This task is read-only. Do not commit.

## Task 1: Add Failing Architecture And Schema Guards

**Files:**
- Create: `tests/architecture/test_token_equity_workerspace_root_fix_contract.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Test: `tests/architecture/test_token_equity_workerspace_root_fix_contract.py`

- [ ] **Step 1: Add architecture guard for Token Radar volatile identities and dirty kinds**

Create `tests/architecture/test_token_equity_workerspace_root_fix_contract.py` with:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


def _text(path: str) -> str:
    return (ROOT / path).read_text()


def test_token_rank_source_manifest_identity_matches_runtime_key() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    rank_identity = manifest.split('"token_radar_rank_source_events"', 1)[1].split(")", 1)[0]

    assert '"intent_id"' not in rank_identity
    for column in (
        '"projection_version"',
        '"window"',
        '"scope"',
        '"lane"',
        '"target_type_key"',
        '"identity_id"',
        '"source_kind"',
        '"source_id"',
    ):
        assert column in rank_identity


def test_token_dirty_targets_preserve_source_and_market_dirty_kinds() -> None:
    repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_dirty_target_repository.py"
    )

    assert "source_dirty" in repo
    assert "market_dirty" in repo
    assert "dirty_at_ms" not in repo.split("def _payload_hash", 1)[1].split("return", 1)[0]


def test_token_hashes_use_shared_canonicalizer() -> None:
    repo = _text("src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py")
    helper = _text("src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py")

    assert "canonical_token_radar_payload" in helper
    assert "provenance.computed_at_ms" in helper
    assert "canonical_token_radar_payload" in repo
```

- [ ] **Step 2: Add architecture guard for Equity process queue and raw payload boundaries**

Append:

```python
def test_equity_process_worker_uses_process_jobs_not_document_scan() -> None:
    worker = _text(
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/"
        "equity_event_process_worker.py"
    )

    assert "claim_due_process_jobs" in worker
    assert "load_process_packets_for_claims" in worker
    assert "list_event_documents_for_processing" not in worker
    assert "unit_of_work()" in worker


def test_equity_process_and_page_hot_paths_do_not_select_raw_payload() -> None:
    repo = _text(
        "src/gmgn_twitter_intel/domains/equity_event_intel/repositories/"
        "equity_event_repository.py"
    )
    process_loader = repo.split("def load_process_packets_for_claims", 1)[1].split("\n    def ", 1)[0]
    page_loader = repo.split("def _list_event_documents", 1)[1].split("\n    def ", 1)[0]

    assert "raw_payload_json" not in process_loader
    assert "raw_payload_json" not in page_loader
```

- [ ] **Step 3: Add architecture guard for WorkerSpace production enforcement**

Append:

```python
def test_enforcement_workers_use_runtime_context_not_raw_worker_session() -> None:
    enforcement_files = [
        "src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py",
        "src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py",
    ]

    for path in enforcement_files:
        text = _text(path)
        assert "runtime_context" in text
        assert "self.db.worker_session" not in text


def test_event_anchor_and_equity_process_manifests_declare_leased_queues() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    event_anchor = manifest.split('name="event_anchor_backfill"', 1)[1].split("WorkerManifest(", 1)[0]
    equity_process = manifest.split('name="equity_event_process"', 1)[1].split("WorkerManifest(", 1)[0]

    assert "uses_provider_io=True" in event_anchor
    assert 'queue_depth_table="event_anchor_backfill_jobs"' in event_anchor
    assert 'queue_depth_table="equity_event_process_jobs"' in equity_process
    assert '"equity_event_process_jobs"' in equity_process
```

- [ ] **Step 4: Add schema migration guard**

Append to `tests/unit/test_postgres_schema.py`:

```python
def test_token_equity_workerspace_root_fix_migration_contract() -> None:
    text = _migration_text("20260528_0121_token_equity_workerspace_root_fix.py")

    assert "source_payload_hash" in text
    assert "source_dirty" in text
    assert "market_dirty" in text
    assert "equity_event_process_jobs" in text
    assert "artifact_payload_hash" in text
    assert "lease_owner" in text
    assert "leased_until_ms" in text
    assert "event_anchor_backfill_jobs" in text
    assert "queue_depth_table" not in text
```

- [ ] **Step 5: Run failing guards**

Run:

```bash
uv run pytest \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py \
  tests/unit/test_postgres_schema.py::test_token_equity_workerspace_root_fix_migration_contract \
  -q
```

Expected before implementation: failures mention missing migration, missing runtime context, raw payload still selected, `intent_id` still in rank-source identity, or missing dirty kind columns.

- [ ] **Step 6: Commit failing guards**

Run:

```bash
git add tests/architecture/test_token_equity_workerspace_root_fix_contract.py tests/unit/test_postgres_schema.py
git commit -m "test: add token equity workerspace root fix guards"
```

Expected: commit succeeds with only tests changed.

## Task 2: Schema Hard Cut Migration

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Test: `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Create Alembic migration with hard-cut schema**

Create `src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py` with these operations:

```python
"""Hard cut Token Radar, Equity Event, and WorkerSpace runtime schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260528_0121"
down_revision = "20260528_0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "token_radar_rank_source_events",
        sa.Column("source_payload_hash", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("token_radar_rank_source_events", "source_payload_hash", server_default=None)

    op.add_column("token_radar_dirty_targets", sa.Column("source_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("token_radar_dirty_targets", sa.Column("market_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("token_radar_dirty_targets", sa.Column("repair_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.alter_column("token_radar_dirty_targets", "source_dirty", server_default=None)
    op.alter_column("token_radar_dirty_targets", "market_dirty", server_default=None)
    op.alter_column("token_radar_dirty_targets", "repair_dirty", server_default=None)

    op.create_table(
        "equity_event_process_jobs",
        sa.Column("event_document_id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("leased_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("input_payload_hash", sa.Text(), nullable=False),
        sa.Column("started_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("finished_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "idx_equity_event_process_jobs_due",
        "equity_event_process_jobs",
        ["due_at_ms", "event_document_id"],
        postgresql_where=sa.text("status IN ('pending', 'failed_retryable')"),
    )
    op.create_index(
        "idx_equity_event_process_jobs_running",
        "equity_event_process_jobs",
        ["leased_until_ms", "event_document_id"],
        postgresql_where=sa.text("status = 'running'"),
    )

    op.add_column("equity_event_documents", sa.Column("provider_title", sa.Text(), nullable=True))
    op.add_column("equity_event_documents", sa.Column("provider_summary", sa.Text(), nullable=True))
    op.add_column("equity_event_documents", sa.Column("primary_document_url", sa.Text(), nullable=True))

    op.add_column(
        "equity_event_evidence_artifacts",
        sa.Column("artifact_payload_hash", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("equity_event_evidence_artifacts", "artifact_payload_hash", server_default=None)

    op.add_column("event_anchor_backfill_jobs", sa.Column("lease_owner", sa.Text(), nullable=True))
    op.add_column("event_anchor_backfill_jobs", sa.Column("leased_until_ms", sa.BigInteger(), nullable=True))
    op.create_index(
        "idx_event_anchor_backfill_jobs_due",
        "event_anchor_backfill_jobs",
        ["next_run_at_ms", "created_at_ms", "event_id", "intent_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_event_anchor_backfill_jobs_running",
        "event_anchor_backfill_jobs",
        ["leased_until_ms", "event_id", "intent_id"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    raise RuntimeError("20260528_0121 token/equity/WorkerSpace hard cut is not reversible")
```

This branch includes the News `20260528_0117` through `20260528_0120`
migrations from current `main`; the Token/Equity/WorkerSpace migration follows
`20260528_0120`.

- [ ] **Step 2: Run schema guard**

Run:

```bash
uv run pytest tests/unit/test_postgres_schema.py::test_token_equity_workerspace_root_fix_migration_contract -q
```

Expected: pass.

- [ ] **Step 3: Run migration syntax check**

Run:

```bash
uv run python -m py_compile src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py
```

Expected: exit `0`.

- [ ] **Step 4: Commit schema hard cut**

Run:

```bash
git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py tests/unit/test_postgres_schema.py
git commit -m "feat: add token equity workerspace hard cut schema"
```

Expected: commit succeeds.

## Task 3: Token Radar Stable Hash Helpers

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_payload_hash.py`

- [ ] **Step 1: Write payload canonicalizer tests**

Create `tests/unit/domains/token_intel/test_token_radar_payload_hash.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.services.token_radar_payload_hash import (
    canonical_token_radar_payload,
    token_radar_payload_hash,
)


def test_canonical_token_payload_excludes_nested_computed_at_ms() -> None:
    payload = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "provenance": {
                "source_event_ids": ["event-1"],
                "computed_at_ms": 111,
            },
        },
        "computed_at_ms": 111,
        "published_at_ms": 111,
        "score": 5,
    }

    changed_time = {
        **payload,
        "factor_snapshot_json": {
            **payload["factor_snapshot_json"],
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 222},
        },
        "computed_at_ms": 222,
        "published_at_ms": 222,
    }

    assert canonical_token_radar_payload(payload) == canonical_token_radar_payload(changed_time)
    assert token_radar_payload_hash(payload) == token_radar_payload_hash(changed_time)


def test_canonical_token_payload_keeps_business_changes() -> None:
    base = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "factor_snapshot_json": {
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 111},
            "composite": {"rank_score": 10},
        },
    }
    changed = {
        **base,
        "factor_snapshot_json": {
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 111},
            "composite": {"rank_score": 11},
        },
    }

    assert token_radar_payload_hash(base) != token_radar_payload_hash(changed)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/token_intel/test_token_radar_payload_hash.py -q
```

Expected: fails because `token_radar_payload_hash.py` does not exist.

- [ ] **Step 3: Implement canonicalizer**

Create `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py`:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

VOLATILE_TOP_LEVEL_KEYS = frozenset(
    {
        "row_id",
        "computed_at_ms",
        "generation_id",
        "published_at_ms",
        "source_frontier_ms",
        "payload_hash",
        "listed_at_ms",
        "created_at_ms",
        "updated_at_ms",
        "last_scored_at_ms",
    }
)


def canonical_token_radar_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _strip_nested_freshness(value)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if str(key) not in VOLATILE_TOP_LEVEL_KEYS
    }


def token_radar_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        canonical_token_radar_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _strip_nested_freshness(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key == "computed_at_ms":
                continue
            out[key] = _strip_nested_freshness(raw_value)
        return out
    if isinstance(value, tuple | list):
        return [_strip_nested_freshness(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_strip_nested_freshness(item) for item in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
```

- [ ] **Step 4: Wire helper into Token Radar repository hashes**

Modify `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`:

```python
from gmgn_twitter_intel.domains.token_intel.services.token_radar_payload_hash import token_radar_payload_hash
```

Change `_payload_hash(...)` and `_target_feature_hash(...)` so both call `token_radar_payload_hash(...)` after preserving their existing top-level exclusions through the shared helper:

```python
def _payload_hash(row: dict[str, Any]) -> str:
    return token_radar_payload_hash({column: row.get(column) for column in RADAR_ROW_COLUMNS})


def _target_feature_hash(row: dict[str, Any]) -> str:
    return token_radar_payload_hash(row)
```

Keep `_json_ready(...)` if other functions still use it.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/token_intel/test_token_radar_payload_hash.py \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_token_hashes_use_shared_canonicalizer \
  -q
```

Expected: pass.

- [ ] **Step 6: Commit Token Radar hash helper**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py \
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py \
  tests/unit/domains/token_intel/test_token_radar_payload_hash.py
git commit -m "feat: stabilize token radar payload hashes"
```

Expected: commit succeeds.

## Task 4: Token Radar Dirty Kinds And Source-Edge No-Op Gate

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py`

- [ ] **Step 1: Write dirty-kind coalescing tests**

Create `tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    dirty_kind_flags,
    dirty_payload_hash,
)


def test_dirty_kind_flags_classify_source_and_market_reasons() -> None:
    assert dirty_kind_flags("intent_written") == {
        "source_dirty": True,
        "market_dirty": False,
        "repair_dirty": False,
    }
    assert dirty_kind_flags("market_tick_current_updated") == {
        "source_dirty": False,
        "market_dirty": True,
        "repair_dirty": False,
    }
    assert dirty_kind_flags("ops_repair") == {
        "source_dirty": True,
        "market_dirty": True,
        "repair_dirty": True,
    }


def test_dirty_payload_hash_excludes_dirty_at_ms() -> None:
    first = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "source_event_ids": ["event-1"],
        "dirty_at_ms": 111,
    }
    second = {**first, "dirty_at_ms": 222}

    assert dirty_payload_hash(first) == dirty_payload_hash(second)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py -q
```

Expected: fails because helper functions do not exist.

- [ ] **Step 3: Implement dirty-kind helpers**

Modify `token_radar_dirty_target_repository.py`:

```python
SOURCE_DIRTY_REASONS = frozenset(
    {
        "intent_written",
        "resolution_updated",
        "identity_updated",
        "source_event_written",
        "event_anchor_updated",
        "ops_repair",
    }
)
MARKET_DIRTY_REASONS = frozenset(
    {
        "market_tick_current_updated",
        "market_tick_written",
        "ops_repair",
    }
)


def dirty_kind_flags(reason: str) -> dict[str, bool]:
    normalized = str(reason or "").strip()
    return {
        "source_dirty": normalized in SOURCE_DIRTY_REASONS or normalized not in MARKET_DIRTY_REASONS,
        "market_dirty": normalized in MARKET_DIRTY_REASONS,
        "repair_dirty": normalized == "ops_repair",
    }


def dirty_payload_hash(payload: Mapping[str, Any]) -> str:
    stable = {
        str(key): postgres_safe_json(value)
        for key, value in payload.items()
        if str(key)
        not in {
            "dirty_at_ms",
            "due_at_ms",
            "leased_until_ms",
            "lease_owner",
            "attempt_count",
            "updated_at_ms",
            "first_dirty_at_ms",
            "last_error",
        }
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

Change existing `_payload_hash(...)` to call `dirty_payload_hash(...)`.

- [ ] **Step 4: Preserve dirty kinds by union on enqueue**

In `enqueue_targets(...)`, extend the insert/select arrays with `source_dirty`, `market_dirty`, and `repair_dirty`. Change the conflict update to:

```sql
source_dirty = token_radar_dirty_targets.source_dirty OR EXCLUDED.source_dirty,
market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty,
repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty,
dirty_reason = CASE
  WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
  THEN token_radar_dirty_targets.dirty_reason
  ELSE 'mixed'
END,
payload_hash = EXCLUDED.payload_hash,
```

Apply the same flag handling to `enqueue_market_targets(...)`, with `source_dirty=false`, `market_dirty=true`, `repair_dirty=false`.

- [ ] **Step 5: Add source payload hash to rank-source SQL**

In `token_radar_rank_source_query.py`, add `source_payload_hash` to the insert column list and SELECT. Compute it from source-edge business columns with a SHA-256 expression over a canonical JSON/text payload. The hash input must exclude:

```text
projected_at_ms
latest_price_tick_id
latest_price_provider
latest_price_source_tier
latest_price_pricefeed_id
latest_price_observed_at_ms
latest_price_received_at_ms
latest_price_usd
latest_price_market_cap_usd
latest_price_liquidity_usd
latest_price_volume_24h_usd
latest_price_open_interest_usd
latest_price_holders
```

Change the conflict update to include:

```sql
source_payload_hash = excluded.source_payload_hash
WHERE token_radar_rank_source_events.source_payload_hash IS DISTINCT FROM excluded.source_payload_hash
```

No-op conflict must not update `projected_at_ms`.

- [ ] **Step 6: Fix manifest identity mismatch**

In `worker_manifest.py`, remove `"intent_id"` from `token_radar_rank_source_events` current identity so it matches the SQL conflict key:

```python
(
    "token_radar_rank_source_events",
    (
        "projection_version",
        "window",
        "scope",
        "lane",
        "target_type_key",
        "identity_id",
        "source_kind",
        "source_id",
    ),
),
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_token_rank_source_manifest_identity_matches_runtime_key \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_token_dirty_targets_preserve_source_and_market_dirty_kinds \
  -q
```

Expected: pass.

- [ ] **Step 8: Commit dirty target and source-edge no-op gate**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py \
  src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py \
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py \
  src/gmgn_twitter_intel/app/runtime/worker_manifest.py \
  tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py
git commit -m "feat: add token radar dirty kinds and source no-op gate"
```

Expected: commit succeeds.

## Task 5: Token Radar Market-Only Projection Path

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_market_only_projection.py`

- [ ] **Step 1: Write market-only projection tests**

Create `tests/unit/domains/token_intel/test_token_radar_market_only_projection.py` with fakes proving market-only claims skip population:

```python
from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import _claim_requires_source_rebuild


def test_market_only_claim_does_not_require_source_rebuild() -> None:
    claim = {"source_dirty": False, "market_dirty": True, "repair_dirty": False}

    assert _claim_requires_source_rebuild(claim) is False


def test_source_or_repair_claim_requires_source_rebuild() -> None:
    assert _claim_requires_source_rebuild({"source_dirty": True, "market_dirty": False}) is True
    assert _claim_requires_source_rebuild({"repair_dirty": True, "market_dirty": True}) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/token_intel/test_token_radar_market_only_projection.py -q
```

Expected: fails because `_claim_requires_source_rebuild` does not exist.

- [ ] **Step 3: Add source-rebuild classifier**

In `token_radar_projection.py`, add:

```python
def _claim_requires_source_rebuild(claim: Mapping[str, Any]) -> bool:
    if bool(claim.get("repair_dirty")):
        return True
    if bool(claim.get("source_dirty")):
        return True
    if "source_dirty" not in claim and "market_dirty" not in claim:
        return True
    return False
```

- [ ] **Step 4: Split claims before source-edge population**

In `rebuild_dirty_targets(...)`, split:

```python
source_claims = [claim for claim in claims if _claim_requires_source_rebuild(claim)]
market_only_claims = [claim for claim in claims if not _claim_requires_source_rebuild(claim)]
```

Only call `populate_edges_for_requests(...)` for `source_claims`. For `market_only_claims`, load existing rank-source rows for the target/window/scope request without repopulating edges, then recompute target features/current rows.

- [ ] **Step 5: Add narrow latest market loader**

In `TokenRadarRankSourceRepository`, add `latest_market_context_for_targets(self, *, targets: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]`. It maps claimed target keys to latest market context from `market_tick_current` and returns scalar latest fields only:

```sql
SELECT
  requested.target_type_key,
  requested.identity_id,
  market_tick_current.tick_id,
  market_tick_current.source_provider,
  market_tick_current.source_tier,
  market_tick_current.pricefeed_id,
  market_tick_current.tick_observed_at_ms,
  market_tick_current.updated_at_ms,
  market_tick_current.price_usd,
  market_tick_current.market_cap_usd,
  market_tick_current.liquidity_usd,
  market_tick_current.volume_24h_usd,
  market_tick_current.open_interest_usd,
  market_tick_current.holders
FROM requested
JOIN market_tick_current
  ON market_tick_current.target_type = requested.market_target_type
 AND market_tick_current.target_id = requested.market_target_id
```

Patch `_market_context(...)` call sites so latest decision context is supplied from this loader instead of `latest_price_*` columns on every source row.

- [ ] **Step 6: Keep stale/readiness semantics explicit**

If `market.readiness.latest_status` changes solely because wall clock moved, compute it during target scoring but exclude it from payload hashes through `canonical_token_radar_payload(...)`. Bounded recalculation is triggered by market dirty targets and normal worker interval, not by rewriting source edges.

- [ ] **Step 7: Run focused Token tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/token_intel/test_token_radar_market_only_projection.py \
  tests/unit/domains/token_intel/test_token_radar_payload_hash.py \
  tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py \
  -q
```

Expected: pass.

- [ ] **Step 8: Commit market-only path**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py \
  src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py \
  tests/unit/domains/token_intel/test_token_radar_market_only_projection.py
git commit -m "feat: skip source-edge rebuild for token market-only claims"
```

Expected: commit succeeds.

## Task 6: Equity Event Process Job Repository

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py`

- [ ] **Step 1: Write process-job repository tests**

Create `tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py` with repository-level tests using the project DB test fixture:

- `test_enqueue_process_job_uses_stable_input_payload_hash`: insert one provider document, one event document, and two artifacts; enqueue twice with different `now_ms`; assert one process job row and same `input_payload_hash`.
- `test_process_input_payload_hash_changes_when_artifact_hash_changes`: update one artifact `artifact_payload_hash`; enqueue/reset the job; assert `input_payload_hash` changes.
- `test_claim_due_process_jobs_moves_pending_to_running`: enqueue one due job; claim it; assert status `running`, `lease_owner`, `leased_until_ms`, and `attempt_count=1`.
- `test_finish_process_job_success_requires_matching_lease_attempt_and_hash`: call finish with wrong hash and assert `False`; call finish with returned claim hash and assert `True` plus status `done`.
- `test_expire_stale_process_jobs_reschedules_retryable_jobs`: create running stale job under max attempts; expire; assert status `failed_retryable`, lease cleared, and `due_at_ms` advanced.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py -q
```

Expected: fails because process-job methods do not exist.

- [ ] **Step 3: Implement input payload hash**

In `equity_event_repository.py`, add a private helper:

```python
def _process_input_payload_hash(
    *,
    document: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
) -> str:
    payload = {
        "event_document_id": document.get("event_document_id"),
        "provider_document_id": document.get("provider_document_id"),
        "company_id": document.get("company_id"),
        "ticker": document.get("ticker"),
        "cik": document.get("cik"),
        "source_id": document.get("source_id"),
        "source_role": document.get("source_role"),
        "document_type": document.get("document_type"),
        "form_type": document.get("form_type"),
        "accession_number": document.get("accession_number"),
        "fiscal_period": document.get("fiscal_period"),
        "document_url": document.get("document_url"),
        "content_hash": document.get("content_hash"),
        "evidence_status": document.get("evidence_status"),
        "evidence_reason": document.get("evidence_reason"),
        "artifacts": sorted(
            {
                "evidence_artifact_id": artifact.get("evidence_artifact_id"),
                "artifact_kind": artifact.get("artifact_kind"),
                "content_hash": artifact.get("content_hash"),
                "extraction_status": artifact.get("extraction_status"),
                "artifact_payload_hash": artifact.get("artifact_payload_hash"),
            }
            for artifact in artifacts
        ),
    }
    encoded = json.dumps(postgres_safe_json(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement enqueue/claim/finish/fail/expire APIs**

Add repository methods with these exact signatures:

```text
enqueue_process_job_for_document(self, *, event_document_id: str, due_at_ms: int, now_ms: int, commit: bool = True) -> dict[str, Any]
claim_due_process_jobs(self, *, now_ms: int, limit: int, lease_owner: str, lease_ms: int = 60_000, commit: bool = True) -> list[dict[str, Any]]
finish_process_job_success(self, *, event_document_id: str, lease_owner: str, attempt_count: int, input_payload_hash: str, now_ms: int, commit: bool = True) -> bool
finish_process_job_failure(self, *, event_document_id: str, lease_owner: str, attempt_count: int, input_payload_hash: str, error: str, now_ms: int, retry_ms: int, commit: bool = True) -> bool
expire_stale_process_jobs(self, *, now_ms: int, limit: int, commit: bool = True) -> list[dict[str, Any]]
```

Use the evidence-job repository style:

- claim uses `WITH due AS (...) UPDATE equity_event_process_jobs AS jobs SET status='running', started_at_ms=COALESCE(started_at_ms, %(now_ms)s), attempt_count=attempt_count+1, lease_owner=%(lease_owner)s, leased_until_ms=%(leased_until_ms)s, updated_at_ms=%(now_ms)s FROM due RETURNING jobs.*`
- finish/fail `WHERE status='running' AND lease_owner=%s AND attempt_count=%s AND input_payload_hash=%s`
- retryable failure sets `status='failed_retryable'`, clears lease fields, sets `due_at_ms=now_ms+retry_ms`
- terminal failure sets `status='failed_terminal'`, `finished_at_ms`, `terminal_reason`

- [ ] **Step 5: Run process-job tests**

Run:

```bash
uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py -q
```

Expected: pass.

- [ ] **Step 6: Commit process-job repository**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py \
  tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py
git commit -m "feat: add equity event process job repository"
```

Expected: commit succeeds.

## Task 7: Equity Process Worker Queue And Atomic Persist

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py`

- [ ] **Step 1: Write process worker queue tests**

Create `tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py` with fake repositories:

- `test_process_worker_returns_idle_without_document_scan`: fake `claim_due_process_jobs` returns `[]`; fake `list_event_documents_for_processing` raises `AssertionError`; assert result has `processed=0`.
- `test_process_worker_loads_only_claimed_packets`: fake claim returns one row; assert `load_process_packets_for_claims` receives that exact claim and no broad document method is called.
- `test_process_worker_persists_inside_unit_of_work`: fake repository session records `unit_of_work_entered=True`; assert company event writes happen while the flag is true.
- `test_process_worker_finishes_job_with_lease_attempt_and_hash`: fake finish method asserts the worker passes `event_document_id`, `lease_owner`, `attempt_count`, and `input_payload_hash` from the claim.

The fake repository must raise if `list_event_documents_for_processing(...)` is called.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py -q
```

Expected: fails because worker still calls `list_event_documents_for_processing(...)`.

- [ ] **Step 3: Add narrow process packet loader**

In `equity_event_repository.py`, add `load_process_packets_for_claims(self, *, claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]`.

The SELECT must use claimed `event_document_id`s only and must not select `provider.raw_payload_json`. It should return:

```text
document scalar fields
provider_title
provider_summary
primary_document_url
evidence artifacts with id, kind, source_url, content_hash, excerpt_text, content_text, extraction_status, artifact_payload_hash
job lease fields
```

- [ ] **Step 4: Rewrite process worker flow**

Change `EquityEventProcessWorker.run_once_sync(...)` to:

1. expire stale process jobs;
2. claim due process jobs;
3. return idle if none;
4. load exact packets for claims;
5. process packets in Python;
6. persist per packet inside `with repos.unit_of_work():`;
7. finish job success/failure with `event_document_id`, `lease_owner`, `attempt_count`, and `input_payload_hash`.

The persist block must include company event upsert, evidence status update, spans, fact candidates, fact extraction status, document processed/failed, dirty target enqueue, and process job finish/fail.

- [ ] **Step 5: Enqueue process jobs from evidence terminal transition**

In `equity_event_evidence_hydration_worker.py`, after terminal evidence status is written, enqueue/reset `equity_event_process_jobs` in the same `repos.unit_of_work()`:

```python
repos.equity_events.enqueue_process_job_for_document(
    event_document_id=document.event_document_id,
    due_at_ms=now_ms,
    now_ms=now_ms,
    commit=False,
)
```

- [ ] **Step 6: Update manifest and queue health**

In `worker_manifest.py`, change `equity_event_process`:

```python
input_contract=("equity_event_process_jobs due rows",)
writes_control_plane=("equity_event_process_jobs", "equity_event_projection_dirty_targets")
queue_depth_table="equity_event_process_jobs"
queue_health_tables=("equity_event_process_jobs",)
```

In `queue_health.py`, include `equity_event_process_jobs` in queue status collection using the existing queue-table pattern.

- [ ] **Step 7: Remove old process discovery path**

Delete `list_event_documents_for_processing(...)` and any `list_unprocessed_event_documents(...)` equivalent from production repository code. Update tests to use process jobs.

- [ ] **Step 8: Run focused Equity process tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py \
  tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_equity_process_worker_uses_process_jobs_not_document_scan \
  -q
```

Expected: pass.

- [ ] **Step 9: Commit process worker queue**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py \
  src/gmgn_twitter_intel/app/runtime/worker_manifest.py \
  src/gmgn_twitter_intel/app/runtime/queue_health.py \
  tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py
git commit -m "feat: drive equity event processing from leased jobs"
```

Expected: commit succeeds.

## Task 8: Equity Raw Payload Removal And Idempotent Artifact/Provider Writes

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_submission_normalizer.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/event_classifier.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py`

- [ ] **Step 1: Write artifact/provider idempotency tests**

Create `tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py` with tests:

- `test_upsert_evidence_artifacts_skips_unchanged_payload`: insert one artifact through `upsert_evidence_artifacts`, run the same call again, and assert returned `updated` count is `0`.
- `test_upsert_evidence_artifacts_deletes_stale_after_success`: insert two artifacts, run with one artifact, and assert only the missing stable id is deleted.
- `test_upsert_provider_document_skips_unchanged_raw_payload`: upsert the same provider document twice with the same `payload_hash`; assert second status is `duplicate` and raw payload row is not updated.
- `test_process_and_page_document_loaders_do_not_select_raw_payload`: read repository source text and assert `raw_payload_json` is absent from `load_process_packets_for_claims` and `_list_event_documents`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py -q
```

Expected: fails because artifact upsert/no-op and raw payload removal are not implemented.

- [ ] **Step 3: Normalize classifier-needed fields**

Extend SEC normalization and event-document upsert so `equity_event_documents` receives:

```text
provider_title
provider_summary
primary_document_url
```

Update `classify_equity_event(...)` to read these normalized document fields instead of `raw_payload_json`.

- [ ] **Step 4: Make provider document upsert idempotent**

In `upsert_provider_document(...)`:

- replace `SELECT *` with select of identity/hash/scalar fields only;
- use CTE/fallback shape like `upsert_event_document(...)`;
- add conflict `WHERE` gate so unchanged `payload_hash` does not rewrite `raw_payload_json` or `fetched_at_ms`;
- keep fetch freshness in fetch runs/source state.

- [ ] **Step 5: Replace artifact delete-all writer**

Replace `replace_evidence_artifacts(...)` with `upsert_evidence_artifacts(self, *, event_document_id: str, artifacts: Sequence[Mapping[str, Any]], now_ms: int, commit: bool = True) -> dict[str, int]`.

Rules:

- compute `artifact_payload_hash` from small artifact fields;
- `ON CONFLICT(evidence_artifact_id) DO UPDATE SET artifact_payload_hash=excluded.artifact_payload_hash, updated_at_ms=excluded.updated_at_ms WHERE equity_event_evidence_artifacts.artifact_payload_hash IS DISTINCT FROM excluded.artifact_payload_hash`;
- delete stale rows for `event_document_id` only after successful upserts and only when `evidence_artifact_id NOT IN incoming ids`;
- do not write companyfacts raw JSON into per-event artifacts.

- [ ] **Step 6: Update evidence hydration worker**

Change hydration persistence from `replace_evidence_artifacts(...)` to `upsert_evidence_artifacts(...)`. Keep raw provider payload use only inside the evidence hydration claimed job path.

- [ ] **Step 7: Remove raw payload from page/document hot read path**

In repository read methods used by page/brief/process projections, remove `provider.raw_payload_json` from SELECT payloads. Keep raw payload only in `load_evidence_hydration_input(...)`, guarded in later WorkerSpace task.

- [ ] **Step 8: Run focused Equity idempotency tests**

Run:

```bash
uv run pytest \
  tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_equity_process_and_page_hot_paths_do_not_select_raw_payload \
  -q
```

Expected: pass.

- [ ] **Step 9: Commit Equity idempotency hard cut**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_submission_normalizer.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/services/event_classifier.py \
  tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py
git commit -m "feat: make equity event document and artifact writes idempotent"
```

Expected: commit succeeds.

## Task 9: WorkerSpace Runtime Context And Enforcement Set

**Files:**
- Create: `src/gmgn_twitter_intel/app/runtime/runtime_worker_context.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_space.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_base.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py`
- Modify: enforcement-set worker files
- Test: `tests/unit/test_runtime_worker_context.py`

- [ ] **Step 1: Write runtime context tests**

Create `tests/unit/test_runtime_worker_context.py`:

```python
from __future__ import annotations

import pytest

from gmgn_twitter_intel.app.runtime.worker_space import WorkerSpaceViolation


def test_provider_io_fails_inside_db_session(runtime_context_factory) -> None:
    context = runtime_context_factory(worker_name="event_anchor_backfill", uses_provider_io=True)

    with pytest.raises(WorkerSpaceViolation, match="provider IO inside DB session"):
        with context.claim_session():
            with context.provider_io():
                pass


def test_payload_load_requires_claim(runtime_context_factory) -> None:
    context = runtime_context_factory(worker_name="equity_event_process", claim_required=True)

    with pytest.raises(WorkerSpaceViolation, match="payload loaded before claim"):
        context.require_claimed_payload()

    context.mark_claimed(count=1)
    context.require_claimed_payload()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_runtime_worker_context.py -q
```

Expected: fails because `runtime_worker_context.py` does not exist and `WorkerSpace` does not track session depth.

- [ ] **Step 3: Extend WorkerSpace with DB session depth**

In `worker_space.py`, add:

```python
@contextmanager
def db_session(self) -> Iterator[None]:
    self._db_session_depth += 1
    try:
        yield
    finally:
        self._db_session_depth -= 1
```

Update `provider_io()`:

```python
if self._db_session_depth > 0:
    raise WorkerSpaceViolation(f"{self.contract.worker_name}: provider IO inside DB session")
```

Initialize `_db_session_depth = 0`.

- [ ] **Step 4: Implement RuntimeWorkerContext**

Create `runtime_worker_context.py`:

```python
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_space import WorkerSpace, WorkerSpaceContract


class RuntimeWorkerContext:
    def __init__(self, *, contract: WorkerSpaceContract, db: Any, statement_timeout_seconds: float | None = None) -> None:
        self.worker_name = contract.worker_name
        self.space = WorkerSpace(contract)
        self._db = db
        self._statement_timeout_seconds = statement_timeout_seconds

    @contextmanager
    def claim_session(self) -> Iterator[Any]:
        with self.space.db_session():
            with self._db.worker_session(self.worker_name, statement_timeout_seconds=self._statement_timeout_seconds) as repos:
                yield repos

    @contextmanager
    def payload_session(self) -> Iterator[Any]:
        self.space.require_claim_before_payload_load()
        with self.space.db_session():
            with self._db.worker_session(self.worker_name, statement_timeout_seconds=self._statement_timeout_seconds) as repos:
                yield repos

    @contextmanager
    def persist_session(self) -> Iterator[Any]:
        with self.space.db_session():
            with self._db.worker_session(self.worker_name, statement_timeout_seconds=self._statement_timeout_seconds) as repos:
                yield repos

    def mark_claimed(self, *, count: int) -> None:
        self.space.mark_claimed(count=count)

    def require_claimed_payload(self) -> None:
        self.space.require_claim_before_payload_load()

    def provider_io(self):
        return self.space.provider_io()
```

- [ ] **Step 5: Inject per-iteration context from WorkerBase**

Modify `WorkerBase` to accept an optional `worker_space_contract`. Add:

```python
def _runtime_context(self) -> RuntimeWorkerContext:
    if self.worker_space_contract is None:
        raise RuntimeError(f"worker:{self.name}:missing_workerspace_contract")
    return RuntimeWorkerContext(
        contract=self.worker_space_contract,
        db=self.db,
        statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
    )
```

Keep non-enforcement legacy workers running until converted by allowing `worker_space_contract=None` outside the enforcement set.

- [ ] **Step 6: Convert enforcement-set workers to context sessions**

For each enforcement-set worker:

```text
token_radar_projection
equity_event_fetch
equity_event_evidence_hydration
equity_event_process
event_anchor_backfill
```

Replace raw `_repository_session()` usage with this sequence:

1. Create `context = self._runtime_context()`.
2. Use `context.claim_session()` only for claim/expire operations.
3. Call `context.mark_claimed(count=len(claims))` immediately after a durable claim.
4. Use `context.payload_session()` only for exact claimed payload loading.
5. Close all DB sessions before `with context.provider_io():`.
6. Use `context.persist_session()` for final fact/control/read-model writes.

Do not wrap provider calls with an open session.

- [ ] **Step 7: Guard evidence hydration payload loader**

Change `load_evidence_hydration_input(...)` to require lease owner and attempt count. The method signature must be:

```python
def load_evidence_hydration_input(
    self,
    *,
    evidence_job_id: str,
    lease_owner: str,
    attempt_count: int,
) -> dict[str, Any]:
```

The SQL predicate must include:

```sql
WHERE jobs.evidence_job_id = %s
  AND jobs.status = 'running'
  AND jobs.lease_owner = %s
  AND jobs.attempt_count = %s
```

- [ ] **Step 8: Run runtime context tests**

Run:

```bash
uv run pytest \
  tests/unit/test_runtime_worker_context.py \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_enforcement_workers_use_runtime_context_not_raw_worker_session \
  -q
```

Expected: pass.

- [ ] **Step 9: Commit WorkerSpace runtime context**

Run:

```bash
git add \
  src/gmgn_twitter_intel/app/runtime/runtime_worker_context.py \
  src/gmgn_twitter_intel/app/runtime/worker_space.py \
  src/gmgn_twitter_intel/app/runtime/worker_base.py \
  src/gmgn_twitter_intel/app/runtime/db_pool_bundle.py \
  src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py \
  src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py \
  tests/unit/test_runtime_worker_context.py
git commit -m "feat: enforce workerspace on token and equity workers"
```

Expected: commit succeeds.

## Task 10: Event Anchor Backfill Durable Lease Claim

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Test: existing event anchor tests plus new focused tests if absent

- [ ] **Step 1: Add event-anchor lease tests**

Create or extend event-anchor repository tests to cover:

- `test_event_anchor_claim_due_moves_pending_to_running`: enqueue a pending job, claim it, and assert status `running`, lease fields, and incremented attempt count.
- `test_event_anchor_mark_done_requires_lease_owner_and_attempt`: assert wrong lease owner returns `False`; assert matching lease owner and attempt transitions to `done`.
- `test_event_anchor_provider_not_called_without_claim`: fake worker provider raises if called; run with no claimed jobs and assert provider was not called.

- [ ] **Step 2: Implement `claim_due(...)`**

Replace `list_due(...)` runtime usage with `claim_due(self, *, limit: int, now_ms: int, min_age_ms: int, lease_owner: str, lease_ms: int) -> list[dict[str, Any]]`.

Use `WITH due AS (...) UPDATE event_anchor_backfill_jobs AS jobs SET status='running', attempt_count=attempt_count+1, lease_owner=%(lease_owner)s, leased_until_ms=%(leased_until_ms)s, updated_at_ms=%(now_ms)s FROM due RETURNING jobs.*` and set:

```text
status='running'
attempt_count=attempt_count+1
lease_owner
leased_until_ms
updated_at_ms
```

- [ ] **Step 3: Guard terminal/reschedule updates by lease**

Update `mark_done`, `mark_terminal`, and reschedule methods to require:

```text
status='running'
lease_owner=:lease_owner
attempt_count=:attempt_count
```

Clear lease fields on terminal statuses.

- [ ] **Step 4: Convert worker provider flow**

In `EventAnchorBackfillWorker.run_once(...)`:

1. expire stale running jobs;
2. claim due jobs;
3. mark WorkerSpace claimed;
4. close claim session;
5. call provider under `runtime_context.provider_io()`;
6. persist results with lease guards.

- [ ] **Step 5: Update manifest**

In `worker_manifest.py`, set:

```python
uses_provider_io=True
queue_depth_table="event_anchor_backfill_jobs"
queue_health_tables=("event_anchor_backfill_jobs",)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py::test_event_anchor_and_equity_process_manifests_declare_leased_queues \
  -q
```

Also run the event-anchor unit test file found by:

```bash
rg -n "EventAnchorBackfill|event_anchor_backfill" tests
```

Expected: pass.

- [ ] **Step 7: Commit event-anchor lease hard cut**

Run:

```bash
git add \
  src/gmgn_twitter_intel/domains/asset_market/repositories/event_anchor_backfill_job_repository.py \
  src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py \
  src/gmgn_twitter_intel/app/runtime/worker_manifest.py
git commit -m "feat: lease event anchor backfill before provider io"
```

Expected: commit succeeds.

## Task 11: Docs, Reset Commands, And Operational Verification Artefact

**Files:**
- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Create: `docs/superpowers/plans/active/2026-05-28-token-radar-equity-workerspace-root-fix-verification-cn.md`

- [ ] **Step 1: Update worker/domain docs**

Document:

- Token Radar source edges are stable source packets, latest market context is target-level scoring input.
- `token_radar_dirty_targets` carries source/market/repair dirty kinds.
- Equity process consumes `equity_event_process_jobs`.
- Evidence hydration may exact-load raw provider payload after claim; process/page/public read paths may not.
- Event anchor backfill is a leased provider worker.
- WorkerSpace provider IO guard tracks DB session and transaction depth.

- [ ] **Step 2: Add hard reset runbook to PostgreSQL performance docs**

Add a section with operator-reviewed commands:

```sql
TRUNCATE token_radar_dirty_targets;
TRUNCATE token_radar_rank_source_events;
TRUNCATE token_radar_target_features;
TRUNCATE token_radar_current_rows;
DELETE FROM token_radar_publication_state WHERE projection_version = 'token-radar-v13-social-attention';

TRUNCATE equity_event_process_jobs;
TRUNCATE equity_event_evidence_artifacts;
TRUNCATE equity_event_source_spans;
TRUNCATE equity_event_fact_candidates;
```

Include warning: run only after migration and code deploy, with service workers stopped or in maintenance mode, and then enqueue bounded repair targets.

- [ ] **Step 3: Create verification artefact skeleton**

Create `docs/superpowers/plans/active/2026-05-28-token-radar-equity-workerspace-root-fix-verification-cn.md` with sections:

```markdown
# Token Radar / Equity Event / WorkerSpace Root Fix Verification

## Config Paths

## Migration

## Unit And Architecture Tests

## make check-all

## Live PostgreSQL Before/After

## Coverage

## Skipped Tests

## E2E Golden Path

## Other Commands Run

## Remaining Risks
```

- [ ] **Step 4: Commit docs/runbook**

Run:

```bash
git add \
  docs/WORKERS.md \
  docs/WORKER_FLOW.md \
  src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md \
  src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md \
  docs/references/POSTGRES_PERFORMANCE.md \
  docs/superpowers/plans/active/2026-05-28-token-radar-equity-workerspace-root-fix-verification-cn.md
git commit -m "docs: document token equity workerspace hard cut"
```

Expected: commit succeeds.

## Task 12: Final Verification

**Files:**
- Update: `docs/superpowers/plans/active/2026-05-28-token-radar-equity-workerspace-root-fix-verification-cn.md`

- [ ] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest \
  tests/architecture/test_token_equity_workerspace_root_fix_contract.py \
  tests/unit/domains/token_intel/test_token_radar_payload_hash.py \
  tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py \
  tests/unit/domains/token_intel/test_token_radar_market_only_projection.py \
  tests/unit/domains/equity_event_intel/test_equity_event_process_jobs.py \
  tests/unit/domains/equity_event_intel/test_equity_event_process_worker_queue.py \
  tests/unit/domains/equity_event_intel/test_equity_event_artifact_upsert.py \
  tests/unit/test_runtime_worker_context.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run full gate**

Run:

```bash
make check-all
```

Expected: exit `0`. Paste full output into the verification artefact.

- [ ] **Step 3: Run migration in Docker test/runtime environment**

Run:

```bash
docker compose up -d postgres
uv run alembic upgrade head
```

Expected: migration applies cleanly. If this project uses a wrapped migration command instead of raw Alembic, use the documented project command and record it in verification.

- [ ] **Step 4: Verify no old production paths remain**

Run:

```bash
rg -n "list_event_documents_for_processing|list_unprocessed_event_documents|replace_evidence_artifacts|self\\.db\\.worker_session" \
  src/gmgn_twitter_intel/domains/token_intel \
  src/gmgn_twitter_intel/domains/equity_event_intel \
  src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py
```

Expected:

- no `list_event_documents_for_processing`
- no `list_unprocessed_event_documents`
- no production `replace_evidence_artifacts`
- no raw `self.db.worker_session` in enforcement-set workers

- [ ] **Step 5: Verify live/steady-state SQL behavior after deploy**

After Docker rebuild and service start, run:

```bash
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -X -q -P pager=off -c "
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%'
   OR query ILIKE '%equity_event_process_jobs%'
   OR query ILIKE '%equity_event_documents%'
ORDER BY total_exec_time DESC
LIMIT 20;

SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE relname IN (
  'token_radar_rank_source_events',
  'token_radar_target_features',
  'token_radar_current_rows',
  'equity_event_process_jobs',
  'equity_event_evidence_artifacts'
)
ORDER BY relname;
"
```

Expected:

- Token rank-source population is not a top steady-state CPU query when no source facts changed.
- Equity process idle loop reads process jobs, not document/provider/artifact hot path.
- Evidence artifact TOAST stops growing after repeated hydration no-op runs.

- [ ] **Step 6: Record remaining risks**

Update verification with:

- any skipped tests;
- any live diagnostic gaps;
- whether artifact physical reclaim still requires `VACUUM FULL` or `pg_repack`;
- follow-up for unrelated `events` / `market_ticks` lifecycle work.

- [ ] **Step 7: Commit verification**

Run:

```bash
git add docs/superpowers/plans/active/2026-05-28-token-radar-equity-workerspace-root-fix-verification-cn.md
git commit -m "docs: record token equity workerspace verification"
```

Expected: commit succeeds.

## Execution Notes

- Preferred execution split:
  1. Token Radar tasks 2-5.
  2. Equity Event tasks 6-8.
  3. WorkerSpace/Event Anchor tasks 9-10.
  4. Docs and verification tasks 11-12.
- Each split should pass its focused tests before moving on.
- Do not run hard reset SQL against live data until migration, code deploy, and operator approval are in place.
- If any task uncovers a product behavior change, stop and update the spec before implementation.
