# Runtime Performance Architecture Root Fix Implementation Plan

> 2026-05-27 hard-cut update: the Macro generation stage/swap design in this
> historical active plan is retired. Do not create/read
> `macro_observation_series_active_generation` or permanent generation serving
> tables. Canonical Macro projection lifecycle is current-only, dirty-target
> driven, and unchanged refreshes write zero serving rows; see
> `docs/superpowers/plans/active/2026-05-27-next-runtime-lifecycle-hard-cut-plan-cn.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治当前 PostgreSQL runtime 性能问题：删除旧热路径，补齐 Kappa/CQRS 中间读模型，把 worker 改成 bounded state machine，并用明确性能测试证明达到 90/100 以上。

**Architecture:** PostgreSQL 仍是唯一业务真相；新增的 hot-path 表都是单 writer、可重建 read model，不引入 Redis/Kafka/Celery。Token Radar 从 compact rank-source edge 排名，Macro 使用 generation stage/swap，Equity fetch 与 evidence hydration 拆成两个可租约的 worker，News 在 DB 写入前验证 provider registry、operator config、schema constraint 一致。

**Tech Stack:** Python, psycopg, Alembic, PostgreSQL, Docker Compose, pytest, pg_stat_statements, PoWA, pgBadger.

**Owning Spec:** `docs/superpowers/specs/active/2026-05-26-runtime-performance-architecture-root-fix-cn.md`

**Working Branch:** `codex/runtime-performance-architecture-root-fix`

**Worktree:** `.worktrees/runtime-performance-architecture-root-fix`

**Policy:** Hard cut only. 不保留旧 SQL 入口、兼容 reader、双写 shadow 路径、feature flag 或 dormant compatibility code。

---

## Acceptance Targets

最终验收必须同时满足这些硬指标：

| Gate | Target | Check |
| --- | --- | --- |
| Docker + migration | app/postgres healthy，Alembic head 等于源码最新 revision，至少包含 `20260526_0105` 和本 plan 新增 revisions | `make docker-up`; `docker compose ps`; `curl -s http://127.0.0.1:8000/readyz` |
| News provider contract | `opennews` 在 registry、operator config、DB check constraint 中一致；worker 不再靠 constraint violation 报错 | `uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py -q` |
| Old Token Radar SQL | 控制刷新窗口内旧 `WITH request_targets AS (` query calls 增量为 0 | before/after `pg_stat_statements` snapshot |
| Token Radar DB time | 新 rank-source hot query p95 < 100ms；无 temp block writes；不扫描 `events.text/text_clean/reference_json` | perf script + `EXPLAIN (ANALYZE, BUFFERS)` |
| Top SQL share | Token Radar 单条 query 不超过验证窗口 Top SQL total time 的 10% | PoWA/pg_stat_statements snapshot |
| Macro projection | refresh 中断时 API 仍读到旧 active generation；不出现 empty projection | integration test |
| Equity stale running | `equity_event_fetch_runs.status='running'` 且超过 hard timeout 的行数为 0 | SQL check |
| Worker boundedness | evidence hydration 以 document job claim，不在 source fetch run 内循环 provider hydration | architecture + unit tests |
| Hot/cold lifecycle | 大 payload/audit/history 表有 retention contract 和 dry-run maintenance report | docs + CLI/script output |
| Score | rubric 90/100 以上 | plan Task 8 的 score sheet |

---

## Subagent Split

用 subagent-driver 落地时按这个顺序派发；每个 subagent 只处理自己的文件范围，完成后由主 agent review diff、运行对应测试，再派下一个。

1. **Schema + guard subagent:** migration、architecture guard、perf harness。
2. **News contract subagent:** registry/config/schema preflight 与 readyz evidence。
3. **Token Radar subagent:** rank-source edge hard cut，删除旧 batch hydrate。
4. **Macro subagent:** generation stage/swap。
5. **Equity subagent:** fetch/evidence job split 与 stale reaper。
6. **Lifecycle subagent:** hot/cold contract、maintenance dry-run、docs。
7. **Runtime wiring subagent:** worker manifest/factory/settings/ops diagnostics。
8. **Verification subagent:** Docker rebuild、live DB/log/PoWA/pgBadger evidence、score sheet。

---

## Files Map

### Create

- `src/gmgn_twitter_intel/domains/news_intel/services/news_provider_contract.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0107_macro_generation_equity_evidence_jobs.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py`
- `scripts/runtime_performance_root_fix_check.sh`
- `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- `tests/unit/domains/news_intel/test_news_provider_contract.py`
- `tests/unit/domains/token_intel/test_token_radar_rank_source_query.py`
- `tests/integration/domains/token_intel/test_token_radar_rank_source_repository.py`
- `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
- `tests/integration/domains/macro_intel/test_macro_observation_series_generation.py`
- `tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py`
- `tests/integration/domains/equity_event_intel/test_equity_event_evidence_jobs.py`

### Modify

- `AGENTS.md`
- `CLAUDE.md`
- `docs/ARCHITECTURE.md`
- `docs/references/POSTGRES_PERFORMANCE.md`
- `src/gmgn_twitter_intel/app/runtime/app.py`
- `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- `src/gmgn_twitter_intel/app/runtime/ops_diagnostics.py`
- `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- `src/gmgn_twitter_intel/app/runtime/settings.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py`
- `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`

### Delete

- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`

The deletion is intentional. If any import breaks, fix the caller to use the rank-source edge path; do not recreate the old query under a new name.

---

## Task 0: Worktree, Baseline, And No-Touch Boundary

**Files:**
- Read: `docs/superpowers/specs/active/2026-05-26-runtime-performance-architecture-root-fix-cn.md`
- Read: `AGENTS.md`
- Read: `docs/references/POSTGRES_PERFORMANCE.md`

- [ ] **Step 0.1: Create isolated worktree from latest local main**

```bash
git worktree add .worktrees/runtime-performance-architecture-root-fix -b codex/runtime-performance-architecture-root-fix main
cd .worktrees/runtime-performance-architecture-root-fix
```

Expected:

```text
Preparing worktree (new branch 'codex/runtime-performance-architecture-root-fix')
HEAD is now at 871e8ac4 feat: hard cut OpenNews signal news view
```

- [ ] **Step 0.2: Confirm runtime config paths without printing secrets**

```bash
uv run gmgn-twitter-intel config
```

Expected evidence to record in verification notes:

```text
config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml
workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

- [ ] **Step 0.3: Capture pre-change runtime SQL baseline**

```bash
docker compose exec -T postgres psql -U gmgn -d gmgn_twitter_intel -Atc "
SELECT
  queryid,
  calls,
  round(total_exec_time::numeric, 2),
  round(mean_exec_time::numeric, 2),
  shared_blks_read,
  temp_blks_written,
  left(regexp_replace(query, '\s+', ' ', 'g'), 160)
FROM pg_stat_statements
WHERE query ILIKE 'WITH request_targets AS (%'
ORDER BY calls DESC
LIMIT 5;"
```

Expected before implementation: at least one old query row may exist. Save the output as baseline; do not reset `pg_stat_statements` unless the operator explicitly approves.

- [ ] **Step 0.4: Commit baseline notes only if a new verification note file is created**

No commit is required if this task only runs commands. If a note file is created, use:

```bash
git add docs/generated/runtime-performance-root-fix-baseline.md
git commit -m "docs: record runtime performance root fix baseline"
```

---

## Task 1: Architecture Guards And Performance Harness First

**Files:**
- Create: `tests/architecture/test_runtime_performance_architecture_hard_cut.py`
- Create: `scripts/runtime_performance_root_fix_check.sh`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`

- [ ] **Step 1.1: Add architecture guard tests**

Create `tests/architecture/test_runtime_performance_architecture_hard_cut.py` with these checks:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_token_radar_old_batch_query_is_deleted() -> None:
    old_query = SRC / "domains/token_intel/queries/token_radar_target_feature_query.py"
    assert not old_query.exists()


def test_token_radar_projection_does_not_call_old_hot_sql() -> None:
    text = _read("src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py")
    forbidden = [
        "TokenRadarTargetFeatureBatchQuery",
        "source_rows_for_requests",
        "WITH request_targets AS",
        "events.text",
        "events.text_clean",
        "events.reference_json",
    ]
    for token in forbidden:
        assert token not in text


def test_token_radar_rank_source_has_single_owner_manifest_entry() -> None:
    manifest = _read("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    assert "token_radar_rank_source_events" in manifest
    assert manifest.count("token_radar_rank_source_events") == 1


def test_macro_projection_refresh_uses_generation_swap() -> None:
    repo = _read("src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py")
    assert "macro_observation_series_active_generation" in repo
    assert "DELETE FROM macro_observation_series_rows\n              WHERE projection_version" not in repo


def test_equity_fetch_worker_does_not_hydrate_document_evidence() -> None:
    fetch_worker = _read(
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py"
    )
    assert "hydrate_document_evidence" not in fetch_worker
    assert "replace_evidence_artifacts" not in fetch_worker


def test_equity_evidence_hydration_worker_exists() -> None:
    path = SRC / "domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py"
    assert path.exists()


def test_news_fetch_validates_provider_contract_before_reconcile() -> None:
    worker = _read("src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py")
    validate_at = worker.index("validate_news_provider_contract")
    reconcile_at = worker.index("reconcile_configured_sources")
    assert validate_at < reconcile_at
```

- [ ] **Step 1.2: Add read-only performance check script**

Create `scripts/runtime_performance_root_fix_check.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_USER="${DB_USER:-gmgn}"
DB_NAME="${DB_NAME:-gmgn_twitter_intel}"
APP_URL="${APP_URL:-http://127.0.0.1:8000}"

psql_cmd() {
  docker compose exec -T "${DB_SERVICE}" psql -U "${DB_USER}" -d "${DB_NAME}" "$@"
}

echo "== readyz =="
curl -fsS "${APP_URL}/readyz"
echo

echo "== migration =="
psql_cmd -Atc "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"

echo "== old token radar query calls =="
psql_cmd -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE 'WITH request_targets AS (%';"

echo "== token radar rank source p95 =="
psql_cmd -Atc "
WITH ranked AS (
  SELECT mean_exec_time, calls
  FROM pg_stat_statements
  WHERE query ILIKE '%token_radar_rank_source_events%'
  ORDER BY total_exec_time DESC
  LIMIT 20
)
SELECT COALESCE(round(max(mean_exec_time)::numeric, 2), 0)
FROM ranked;"

echo "== stale equity fetch runs =="
psql_cmd -Atc "
SELECT count(*)
FROM equity_event_fetch_runs
WHERE status = 'running'
  AND started_at_ms < ((extract(epoch FROM clock_timestamp()) * 1000)::bigint - 900000);"

echo "== token radar temp blocks =="
psql_cmd -Atc "
SELECT COALESCE(sum(temp_blks_written), 0)
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%';"

echo "== top sql token radar share =="
psql_cmd -Atc "
WITH totals AS (
  SELECT sum(total_exec_time) AS all_ms
  FROM pg_stat_statements
),
token AS (
  SELECT COALESCE(max(total_exec_time), 0) AS token_ms
  FROM pg_stat_statements
  WHERE query ILIKE '%token_radar%'
)
SELECT CASE
  WHEN totals.all_ms IS NULL OR totals.all_ms = 0 THEN 0
  ELSE round((token.token_ms / totals.all_ms * 100)::numeric, 2)
END
FROM totals, token;"
```

- [ ] **Step 1.3: Make script executable**

```bash
chmod +x scripts/runtime_performance_root_fix_check.sh
```

- [ ] **Step 1.4: Run guards and confirm they fail before implementation**

```bash
uv run pytest tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected before implementation:

```text
FAILED tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_token_radar_old_batch_query_is_deleted
```

- [ ] **Step 1.5: Commit guard and harness**

```bash
git add tests/architecture/test_runtime_performance_architecture_hard_cut.py scripts/runtime_performance_root_fix_check.sh docs/references/POSTGRES_PERFORMANCE.md
git commit -m "test: add runtime performance hard cut guards"
```

---

## Task 2: Schema Hard Cut

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0107_macro_generation_equity_evidence_jobs.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py`
- Test: `tests/unit/test_postgres_schema.py`

- [ ] **Step 2.1: Add migration `20260526_0106_runtime_rank_source_edges.py`**

Create `token_radar_rank_source_events`:

```sql
CREATE TABLE token_radar_rank_source_events (
    projection_version text NOT NULL,
    target_type_key text NOT NULL,
    identity_id text NOT NULL,
    event_id text NOT NULL,
    intent_id text NOT NULL,
    resolution_id text NOT NULL,
    resolver_policy_version text NOT NULL,
    received_at_ms bigint NOT NULL,
    score_eligible_at_ms bigint NOT NULL,
    is_watched boolean NOT NULL DEFAULT false,
    author_handle text NOT NULL,
    author_followers bigint,
    direction text,
    impact text,
    novelty text,
    confidence double precision,
    pricefeed_id text,
    market_target_type text,
    market_target_id text,
    event_price_capture_id text,
    latest_price_tick_id text,
    source_payload_hash text NOT NULL,
    source_watermark_ms bigint NOT NULL,
    created_at_ms bigint NOT NULL,
    updated_at_ms bigint NOT NULL,
    PRIMARY KEY (
        projection_version,
        target_type_key,
        identity_id,
        event_id,
        intent_id,
        resolution_id
    )
);

CREATE INDEX token_radar_rank_source_events_target_received_idx
ON token_radar_rank_source_events (
    projection_version,
    target_type_key,
    identity_id,
    received_at_ms DESC
)
INCLUDE (
    is_watched,
    author_followers,
    direction,
    impact,
    novelty,
    confidence,
    pricefeed_id,
    market_target_type,
    market_target_id,
    source_payload_hash
);

CREATE INDEX token_radar_rank_source_events_watched_idx
ON token_radar_rank_source_events (
    projection_version,
    target_type_key,
    identity_id,
    received_at_ms DESC
)
WHERE is_watched;

CREATE INDEX token_radar_rank_source_events_watermark_idx
ON token_radar_rank_source_events (
    projection_version,
    source_watermark_ms DESC
);
```

Python revision details:

```python
revision = "20260526_0106"
down_revision = "20260526_0105"
```

- [ ] **Step 2.2: Add migration `20260526_0107_macro_generation_equity_evidence_jobs.py`**

Create Macro generation control:

```sql
CREATE TABLE macro_observation_series_active_generation (
    projection_version text PRIMARY KEY,
    generation_id text NOT NULL,
    activated_at_ms bigint NOT NULL,
    row_count integer NOT NULL CHECK (row_count > 0)
);

CREATE TABLE macro_observation_series_generations (
    projection_version text NOT NULL,
    generation_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('staging', 'active', 'replaced', 'failed')),
    row_count integer NOT NULL DEFAULT 0,
    coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at_ms bigint NOT NULL,
    activated_at_ms bigint,
    PRIMARY KEY (projection_version, generation_id)
);

ALTER TABLE macro_observation_series_rows
ADD COLUMN generation_id text NOT NULL DEFAULT 'initial-active';

INSERT INTO macro_observation_series_generations (
    projection_version,
    generation_id,
    status,
    row_count,
    coverage_json,
    created_at_ms,
    activated_at_ms
)
SELECT
    projection_version,
    'initial-active',
    'active',
    count(*)::integer,
    '{}'::jsonb,
    (extract(epoch FROM clock_timestamp()) * 1000)::bigint,
    (extract(epoch FROM clock_timestamp()) * 1000)::bigint
FROM macro_observation_series_rows
GROUP BY projection_version
HAVING count(*) > 0;

INSERT INTO macro_observation_series_active_generation (
    projection_version,
    generation_id,
    activated_at_ms,
    row_count
)
SELECT projection_version, generation_id, activated_at_ms, row_count
FROM macro_observation_series_generations
WHERE status = 'active';
```

Create Equity evidence jobs:

```sql
CREATE TABLE equity_event_evidence_jobs (
    event_document_id text PRIMARY KEY,
    provider_document_id text NOT NULL,
    source_id text NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'failed', 'terminal', 'done')),
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    due_at_ms bigint NOT NULL,
    leased_until_ms bigint,
    lease_owner text,
    last_error text,
    terminal_reason text,
    payload_hash text NOT NULL,
    created_at_ms bigint NOT NULL,
    updated_at_ms bigint NOT NULL
);

CREATE INDEX equity_event_evidence_jobs_due_idx
ON equity_event_evidence_jobs (status, due_at_ms, updated_at_ms)
WHERE status IN ('pending', 'failed');

CREATE INDEX equity_event_evidence_jobs_running_idx
ON equity_event_evidence_jobs (leased_until_ms, updated_at_ms)
WHERE status = 'running';
```

Python revision details:

```python
revision = "20260526_0107"
down_revision = "20260526_0106"
```

- [ ] **Step 2.3: Add migration `20260526_0108_runtime_perf_lifecycle_indexes.py`**

Add read-path indexes and comments that codify hot/cold lifecycle:

```sql
COMMENT ON TABLE token_radar_rank_source_events IS
'Hot compact Token Radar rank-source read model. No event text, raw payload, audit snapshot, or explanation JSON belongs here.';

COMMENT ON TABLE token_radar_snapshot_audit IS
'Cold audit/history payload. Runtime ranking must not scan this table.';

COMMENT ON TABLE raw_frames IS
'Provider raw input archive. Runtime read paths must not treat raw frames as material facts.';

COMMENT ON TABLE equity_event_evidence_artifacts IS
'Cold evidence payload selected by document id only. Source fetch worker must not rewrite this table.';
```

Add supporting indexes only if absent:

```sql
CREATE INDEX IF NOT EXISTS equity_event_fetch_runs_running_started_idx
ON equity_event_fetch_runs (started_at_ms)
WHERE status = 'running';

CREATE INDEX IF NOT EXISTS macro_observation_series_rows_active_lookup_idx
ON macro_observation_series_rows (
    projection_version,
    generation_id,
    concept_key,
    observed_at DESC
);
```

Python revision details:

```python
revision = "20260526_0108"
down_revision = "20260526_0107"
```

- [ ] **Step 2.4: Add schema tests**

Extend `tests/unit/test_postgres_schema.py` with checks that migration files contain the required tables, indexes, and comments:

```python
def test_runtime_performance_migrations_define_hard_cut_tables() -> None:
    migrations = ROOT / "src/gmgn_twitter_intel/platform/db/alembic/versions"
    text = "\n".join(path.read_text() for path in migrations.glob("20260526_010*_*.py"))
    required = [
        "token_radar_rank_source_events",
        "macro_observation_series_active_generation",
        "macro_observation_series_generations",
        "equity_event_evidence_jobs",
        "equity_event_evidence_jobs_due_idx",
        "token_radar_rank_source_events_target_received_idx",
    ]
    for token in required:
        assert token in text
```

- [ ] **Step 2.5: Run migration tests**

```bash
uv run pytest tests/unit/test_postgres_schema.py tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected at this point:

```text
tests/unit/test_postgres_schema.py ... passed
tests/architecture/test_runtime_performance_architecture_hard_cut.py ... still fails on implementation guards
```

- [ ] **Step 2.6: Commit schema**

```bash
git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py \
        src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0107_macro_generation_equity_evidence_jobs.py \
        src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py \
        tests/unit/test_postgres_schema.py
git commit -m "feat: add runtime performance hard cut schema"
```

---

## Task 3: News Provider Contract Before DB Writes

**Files:**
- Create: `src/gmgn_twitter_intel/domains/news_intel/services/news_provider_contract.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- Test: `tests/unit/domains/news_intel/test_news_provider_contract.py`

- [ ] **Step 3.1: Write failing provider contract tests**

Create tests:

```python
from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.news_intel.services.news_provider_contract import (
    NewsProviderContractError,
    validate_news_provider_contract,
)


class FakeRepository:
    def __init__(self, provider_types: set[str]) -> None:
        self.provider_types = provider_types

    def news_source_provider_constraint_values(self) -> set[str]:
        return self.provider_types


def test_validate_news_provider_contract_accepts_opennews_when_schema_allows_it() -> None:
    validate_news_provider_contract(
        configured_provider_types={"opennews", "rss"},
        registry_provider_types={"atom", "cryptopanic", "json_feed", "opennews", "rss"},
        repository=FakeRepository({"atom", "cryptopanic", "json_feed", "opennews", "rss"}),
    )


def test_validate_news_provider_contract_rejects_config_before_db_write() -> None:
    with pytest.raises(NewsProviderContractError) as exc:
        validate_news_provider_contract(
            configured_provider_types={"opennews"},
            registry_provider_types={"atom", "cryptopanic", "json_feed", "opennews", "rss"},
            repository=FakeRepository({"atom", "cryptopanic", "json_feed", "rss"}),
        )
    assert exc.value.reason == "news_provider_type_missing_from_db_constraint"
    assert exc.value.provider_types == ("opennews",)
```

- [ ] **Step 3.2: Implement service**

Create `news_provider_contract.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class NewsProviderConstraintRepository(Protocol):
    def news_source_provider_constraint_values(self) -> set[str]:
        ...


@dataclass(frozen=True)
class NewsProviderContractError(RuntimeError):
    reason: str
    provider_types: tuple[str, ...]

    def __str__(self) -> str:
        providers = ", ".join(self.provider_types)
        return f"{self.reason}: {providers}"


def validate_news_provider_contract(
    *,
    configured_provider_types: set[str],
    registry_provider_types: set[str],
    repository: NewsProviderConstraintRepository,
) -> None:
    missing_from_registry = tuple(sorted(configured_provider_types - registry_provider_types))
    if missing_from_registry:
        raise NewsProviderContractError(
            reason="news_provider_type_missing_from_registry",
            provider_types=missing_from_registry,
        )
    constraint_provider_types = repository.news_source_provider_constraint_values()
    missing_from_constraint = tuple(sorted(configured_provider_types - constraint_provider_types))
    if missing_from_constraint:
        raise NewsProviderContractError(
            reason="news_provider_type_missing_from_db_constraint",
            provider_types=missing_from_constraint,
        )
```

- [ ] **Step 3.3: Add repository schema introspection**

Add to `NewsRepository`:

```python
def news_source_provider_constraint_values(self) -> set[str]:
    with self.conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'news_sources'::regclass
              AND conname = 'news_sources_provider_type_check'
            """
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return set()
    definition = str(row[0])
    values: set[str] = set()
    for value in ("atom", "cryptopanic", "json_feed", "opennews", "rss"):
        if f"'{value}'" in definition:
            values.add(value)
    return values
```

- [ ] **Step 3.4: Call validation before reconciliation**

In `NewsFetchWorker.run_once_sync`, call validation before `reconcile_configured_sources(...)`:

```python
validate_news_provider_contract(
    configured_provider_types={source.provider_type for source in self.sources},
    registry_provider_types=set(SUPPORTED_NEWS_PROVIDER_TYPES),
    repository=repos.news,
)
```

On `NewsProviderContractError`, return worker evidence with:

```python
{
    "status": "blocked",
    "reason": exc.reason,
    "provider_types": list(exc.provider_types),
}
```

Do not call `reconcile_configured_sources` after this failure.

- [ ] **Step 3.5: Surface contract in bootstrap/readyz**

In startup and `/readyz`, include:

```python
"news_provider_contract": {
    "ok": True,
    "configured_provider_types": sorted(configured),
    "supported_provider_types": sorted(SUPPORTED_NEWS_PROVIDER_TYPES),
    "schema_provider_types": sorted(schema_values),
}
```

On failure, `/readyz` must include the explicit reason rather than only a worker exception.

- [ ] **Step 3.6: Run news tests**

```bash
uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 3.7: Commit news contract**

```bash
git add src/gmgn_twitter_intel/domains/news_intel/services/news_provider_contract.py \
        src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py \
        src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py \
        src/gmgn_twitter_intel/app/runtime/app.py \
        src/gmgn_twitter_intel/app/runtime/bootstrap.py \
        tests/unit/domains/news_intel/test_news_provider_contract.py
git commit -m "fix: validate news provider schema contract"
```

---

## Task 4: Token Radar Rank-Source Edge Hard Cut

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Create: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Delete: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_rank_source_query.py`
- Test: `tests/integration/domains/token_intel/test_token_radar_rank_source_repository.py`

- [ ] **Step 4.1: Write query shape tests**

Create `test_token_radar_rank_source_query.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import (
    TOKEN_RADAR_RANK_SOURCE_SQL,
)


def test_rank_source_query_reads_compact_edge_table_only() -> None:
    sql = TOKEN_RADAR_RANK_SOURCE_SQL
    assert "token_radar_rank_source_events" in sql
    forbidden = [
        " events ",
        "events.text",
        "events.text_clean",
        "events.reference_json",
        "token_intents",
        "token_intent_resolutions",
        "WITH request_targets AS",
    ]
    for token in forbidden:
        assert token not in sql


def test_rank_source_query_has_bounded_target_filter() -> None:
    sql = TOKEN_RADAR_RANK_SOURCE_SQL
    assert "unnest(%(target_type_keys)s::text[], %(identity_ids)s::text[])" in sql
    assert "received_at_ms >= %(min_received_at_ms)s" in sql
    assert "ORDER BY e.received_at_ms DESC" in sql
```

- [ ] **Step 4.2: Implement compact rank-source query**

Create `token_radar_rank_source_query.py`:

```python
from __future__ import annotations


TOKEN_RADAR_RANK_SOURCE_SQL = """
WITH requested(target_type_key, identity_id) AS (
    SELECT *
    FROM unnest(%(target_type_keys)s::text[], %(identity_ids)s::text[])
)
SELECT
    e.projection_version,
    e.target_type_key,
    e.identity_id,
    e.event_id,
    e.intent_id,
    e.resolution_id,
    e.received_at_ms,
    e.score_eligible_at_ms,
    e.is_watched,
    e.author_handle,
    e.author_followers,
    e.direction,
    e.impact,
    e.novelty,
    e.confidence,
    e.pricefeed_id,
    e.market_target_type,
    e.market_target_id,
    e.event_price_capture_id,
    e.latest_price_tick_id,
    e.source_payload_hash,
    e.source_watermark_ms
FROM requested r
JOIN token_radar_rank_source_events e
  ON e.target_type_key = r.target_type_key
 AND e.identity_id = r.identity_id
WHERE e.projection_version = %(projection_version)s
  AND e.received_at_ms >= %(min_received_at_ms)s
  AND e.received_at_ms < %(max_received_at_ms)s
ORDER BY e.received_at_ms DESC
LIMIT %(limit)s
"""
```

- [ ] **Step 4.3: Implement rank-source repository**

Create `token_radar_rank_source_repository.py` with:

```python
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import (
    TOKEN_RADAR_RANK_SOURCE_SQL,
)


@dataclass(frozen=True)
class TokenRadarRankSourceRequest:
    target_type_key: str
    identity_id: str


class TokenRadarRankSourceRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def list_edges_for_requests(
        self,
        *,
        projection_version: str,
        requests: Sequence[TokenRadarRankSourceRequest],
        min_received_at_ms: int,
        max_received_at_ms: int,
        limit: int,
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        if not requests:
            return {}
        params = {
            "projection_version": projection_version,
            "target_type_keys": [request.target_type_key for request in requests],
            "identity_ids": [request.identity_id for request in requests],
            "min_received_at_ms": min_received_at_ms,
            "max_received_at_ms": max_received_at_ms,
            "limit": limit,
        }
        with self.conn.cursor() as cur:
            cur.execute(TOKEN_RADAR_RANK_SOURCE_SQL, params)
            rows = [dict(row) for row in cur.fetchall()]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(str(row["target_type_key"]), str(row["identity_id"]))].append(row)
        return dict(grouped)

    def upsert_edges(self, *, rows: Iterable[Mapping[str, Any]]) -> int:
        rows_list = list(rows)
        if not rows_list:
            return 0
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO token_radar_rank_source_events (
                    projection_version,
                    target_type_key,
                    identity_id,
                    event_id,
                    intent_id,
                    resolution_id,
                    resolver_policy_version,
                    received_at_ms,
                    score_eligible_at_ms,
                    is_watched,
                    author_handle,
                    author_followers,
                    direction,
                    impact,
                    novelty,
                    confidence,
                    pricefeed_id,
                    market_target_type,
                    market_target_id,
                    event_price_capture_id,
                    latest_price_tick_id,
                    source_payload_hash,
                    source_watermark_ms,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (
                    %(projection_version)s,
                    %(target_type_key)s,
                    %(identity_id)s,
                    %(event_id)s,
                    %(intent_id)s,
                    %(resolution_id)s,
                    %(resolver_policy_version)s,
                    %(received_at_ms)s,
                    %(score_eligible_at_ms)s,
                    %(is_watched)s,
                    %(author_handle)s,
                    %(author_followers)s,
                    %(direction)s,
                    %(impact)s,
                    %(novelty)s,
                    %(confidence)s,
                    %(pricefeed_id)s,
                    %(market_target_type)s,
                    %(market_target_id)s,
                    %(event_price_capture_id)s,
                    %(latest_price_tick_id)s,
                    %(source_payload_hash)s,
                    %(source_watermark_ms)s,
                    %(created_at_ms)s,
                    %(updated_at_ms)s
                )
                ON CONFLICT (
                    projection_version,
                    target_type_key,
                    identity_id,
                    event_id,
                    intent_id,
                    resolution_id
                )
                DO UPDATE SET
                    resolver_policy_version = EXCLUDED.resolver_policy_version,
                    received_at_ms = EXCLUDED.received_at_ms,
                    score_eligible_at_ms = EXCLUDED.score_eligible_at_ms,
                    is_watched = EXCLUDED.is_watched,
                    author_handle = EXCLUDED.author_handle,
                    author_followers = EXCLUDED.author_followers,
                    direction = EXCLUDED.direction,
                    impact = EXCLUDED.impact,
                    novelty = EXCLUDED.novelty,
                    confidence = EXCLUDED.confidence,
                    pricefeed_id = EXCLUDED.pricefeed_id,
                    market_target_type = EXCLUDED.market_target_type,
                    market_target_id = EXCLUDED.market_target_id,
                    event_price_capture_id = EXCLUDED.event_price_capture_id,
                    latest_price_tick_id = EXCLUDED.latest_price_tick_id,
                    source_payload_hash = EXCLUDED.source_payload_hash,
                    source_watermark_ms = EXCLUDED.source_watermark_ms,
                    updated_at_ms = EXCLUDED.updated_at_ms
                """,
                rows_list,
            )
        return len(rows_list)
```

- [ ] **Step 4.4: Replace projection source read**

In `token_radar_projection.py`:

1. Remove import of `TokenRadarTargetFeatureBatchQuery`.
2. Build `TokenRadarRankSourceRequest` objects from dirty targets.
3. Call `repos.token_radar_rank_sources.list_edges_for_requests(...)`.
4. Feed returned compact edge rows into the existing `_project_source_request` logic after renaming it to `_project_rank_source_edges`.
5. Keep selected-row wide payload hydration through `load_target_feature_payloads_for_ranked_keys(...)` only after ranking has selected rows.

Required behavior:

```python
rows_by_request = self.repos.token_radar_rank_sources.list_edges_for_requests(
    projection_version=TOKEN_RADAR_RANK_INPUT_VERSION,
    requests=source_requests,
    min_received_at_ms=window_min_ms,
    max_received_at_ms=now_ms + 1,
    limit=self.settings.rank_source_limit,
)
```

- [ ] **Step 4.5: Add edge rebuild command path inside owner repository**

Do not use the old deleted batch query. Add a bounded rebuild method that starts from recent `events` by time window, joins facts only for that rebuild batch, writes compact edge rows, and commits by chunk:

```python
def rebuild_rank_source_edges_for_window(
    self,
    *,
    projection_version: str,
    min_received_at_ms: int,
    max_received_at_ms: int,
    chunk_size: int,
) -> int:
    ...
```

The rebuild SQL must:

- filter `events.received_at_ms` before joining wider tables,
- select only scalar columns listed in `token_radar_rank_source_events`,
- omit `events.text`, `events.text_clean`, `events.reference_json`,
- write through `TokenRadarRankSourceRepository.upsert_edges(...)`.

- [ ] **Step 4.6: Wire repository container**

Where domain repositories are constructed, add:

```python
repos.token_radar_rank_sources = TokenRadarRankSourceRepository(conn)
```

Use the local repository container pattern already used for `repos.token_radar`.

- [ ] **Step 4.7: Update manifest owner**

In `worker_manifest.py`, add `token_radar_rank_source_events` to the `TokenRadarProjectionWorker` write set:

```python
writes_read_models=(
    "token_radar_rank_source_events",
    "token_radar_target_features",
    "token_radar_rows",
    ...
)
```

No other worker manifest may list `token_radar_rank_source_events`.

- [ ] **Step 4.8: Delete old query file**

```bash
git rm src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_target_feature_query.py
```

Fix any imports by moving callers to `TokenRadarRankSourceRepository`.

- [ ] **Step 4.9: Update Token Intel architecture**

In `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`, replace the old statement that projection fetches target-scoped source rows with:

```markdown
`token_radar_rank_source_events` is the compact hot-path read model for ranking.
`TokenRadarProjectionWorker` is its only runtime writer. It is rebuildable from
material facts and intentionally excludes event text, raw provider payload,
audit snapshots, and explanation JSON. Runtime ranking reads this table first,
then hydrates wide payloads only for selected published rows.
```

- [ ] **Step 4.10: Run Token Radar tests**

```bash
uv run pytest tests/unit/domains/token_intel/test_token_radar_rank_source_query.py \
              tests/integration/domains/token_intel/test_token_radar_rank_source_repository.py \
              tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected:

```text
token radar query tests passed
architecture Token Radar guards passed
```

- [ ] **Step 4.11: Commit Token Radar hard cut**

```bash
git add src/gmgn_twitter_intel/domains/token_intel \
        src/gmgn_twitter_intel/app/runtime/worker_manifest.py \
        tests/unit/domains/token_intel/test_token_radar_rank_source_query.py \
        tests/integration/domains/token_intel/test_token_radar_rank_source_repository.py \
        tests/architecture/test_runtime_performance_architecture_hard_cut.py
git commit -m "feat: hard cut token radar rank source edge path"
```

---

## Task 5: Macro Observation Series Generation Swap

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- Test: `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
- Test: `tests/integration/domains/macro_intel/test_macro_observation_series_generation.py`

- [ ] **Step 5.1: Write generation swap tests**

Create unit test for interrupted refresh:

```python
def test_refresh_observation_series_rows_keeps_old_active_generation_on_insert_failure(repo, monkeypatch):
    repo.seed_macro_observation_series_generation(
        projection_version="macro-v1",
        generation_id="old-gen",
        rows=[{"concept_key": "spx", "observed_at": 1, "value": 5000.0}],
    )

    def fail_after_staging(*args, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(repo, "_insert_observation_series_generation_rows", fail_after_staging)

    with pytest.raises(RuntimeError):
        repo.refresh_observation_series_rows(projection_version="macro-v1", now_ms=1000)

    active = repo.list_observation_series_rows(projection_version="macro-v1")
    assert [row["generation_id"] for row in active] == ["old-gen"]
    assert [row["concept_key"] for row in active] == ["spx"]
```

- [ ] **Step 5.2: Change readers to join active generation**

Every `macro_observation_series_rows` request/read method must filter through:

```sql
JOIN macro_observation_series_active_generation active
  ON active.projection_version = rows.projection_version
 AND active.generation_id = rows.generation_id
```

Do this in methods currently reading from `macro_observation_series_rows` around repository lines 103, 116, 246, and 275.

- [ ] **Step 5.3: Replace delete-all refresh with stage/swap**

Implement `refresh_observation_series_rows(...)` as one transaction:

1. Create `generation_id = f"{projection_version}-{now_ms}"`.
2. Insert generation row with `status='staging'`.
3. Insert rebuilt rows with that `generation_id`.
4. Count inserted rows.
5. If inserted row count is zero, mark generation `failed` and raise `ValueError("macro_observation_series_generation_empty")`.
6. Upsert active pointer to new generation.
7. Mark previous active generation as `replaced`.
8. Mark new generation as `active`.
9. Delete replaced generation rows only after active pointer is changed, bounded by exact `(projection_version, generation_id)`.

The refresh must not run:

```sql
DELETE FROM macro_observation_series_rows
WHERE projection_version = %(projection_version)s
```

- [ ] **Step 5.4: Update Macro architecture**

Add:

```markdown
Macro observation series refresh is stage/swap. Request paths always join
`macro_observation_series_active_generation`; a failed refresh leaves the
previous generation active.
```

- [ ] **Step 5.5: Run Macro tests**

```bash
uv run pytest tests/unit/domains/macro_intel/test_macro_generation_swap.py \
              tests/integration/domains/macro_intel/test_macro_observation_series_generation.py \
              tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected:

```text
macro generation tests passed
architecture macro guard passed
```

- [ ] **Step 5.6: Commit Macro stage/swap**

```bash
git add src/gmgn_twitter_intel/domains/macro_intel \
        tests/unit/domains/macro_intel/test_macro_generation_swap.py \
        tests/integration/domains/macro_intel/test_macro_observation_series_generation.py \
        tests/architecture/test_runtime_performance_architecture_hard_cut.py
git commit -m "fix: stage macro observation series generations"
```

---

## Task 6: Equity Fetch And Evidence Hydration Split

**Files:**
- Create: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/app/runtime/settings.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Test: `tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py`
- Test: `tests/integration/domains/equity_event_intel/test_equity_event_evidence_jobs.py`

- [ ] **Step 6.1: Write fetch worker split test**

Add a test that injects a document provider whose `hydrate_document_evidence` raises if called:

```python
class FailingEvidenceProvider:
    def hydrate_document_evidence(self, *args, **kwargs):
        raise AssertionError("fetch worker must not hydrate evidence")


def test_fetch_worker_enqueues_evidence_jobs_without_hydrating(repo, source, provider):
    worker = EquityEventFetchWorker(
        repository_factory=lambda: repo,
        feed_provider=provider,
        document_provider=FailingEvidenceProvider(),
        settings=EquityEventFetchWorkerSettings(batch_size=1),
    )

    result = worker.run_once_sync()

    assert result["documents_persisted"] == 1
    assert result["evidence_jobs_enqueued"] == 1
    assert repo.count_evidence_jobs(status="pending") == 1
```

- [ ] **Step 6.2: Add repository job methods**

Add to `EquityEventRepository`:

```python
def enqueue_evidence_jobs(self, *, documents: list[dict[str, Any]], now_ms: int) -> int:
    ...

def claim_due_evidence_jobs(self, *, now_ms: int, limit: int, lease_ms: int, lease_owner: str) -> list[dict[str, Any]]:
    ...

def mark_evidence_job_done(self, *, event_document_id: str, lease_owner: str, payload_hash: str, now_ms: int) -> None:
    ...

def mark_evidence_job_failed(
    self,
    *,
    event_document_id: str,
    lease_owner: str,
    error: str,
    due_at_ms: int,
    now_ms: int,
) -> None:
    ...

def terminalize_evidence_job(
    self,
    *,
    event_document_id: str,
    lease_owner: str,
    terminal_reason: str,
    now_ms: int,
) -> None:
    ...

def reap_stale_fetch_runs(self, *, stale_before_ms: int, now_ms: int) -> int:
    ...
```

`claim_due_evidence_jobs` must use `FOR UPDATE SKIP LOCKED` and set `status='running'`, `leased_until_ms`, `lease_owner`, `attempt_count=attempt_count+1`.

- [ ] **Step 6.3: Replace artifact delete+insert**

Delete `replace_evidence_artifacts(...)`. Add:

```python
def upsert_evidence_artifacts_for_document(
    self,
    *,
    event_document_id: str,
    evidence_artifacts: list[dict[str, Any]],
    now_ms: int,
) -> int:
    ...
```

Use deterministic artifact key:

```text
event_document_id + provider + kind + evidence_url + sha256(text)
```

Do not delete all artifacts for the document before insert. Mark superseded artifacts only when their deterministic key disappears from the new provider result.

- [ ] **Step 6.4: Strip inline hydration from fetch worker**

In `EquityEventFetchWorker`:

1. Keep source claiming.
2. Keep provider fetch.
3. Keep document persistence.
4. Enqueue evidence jobs for inserted/updated documents.
5. Finish `equity_event_fetch_runs` immediately after source/document persistence.
6. Remove `_hydrate_documents`, `_persist_evidence_results`, and any call to `hydrate_document_evidence`.

At the beginning of `run_once_sync`, call:

```python
reaped = repos.equity_events.reap_stale_fetch_runs(
    stale_before_ms=now - self.settings.hard_timeout_seconds * 1000,
    now_ms=now,
)
```

Return `stale_fetch_runs_reaped` in worker evidence.

- [ ] **Step 6.5: Add evidence hydration worker**

Create `equity_event_evidence_hydration_worker.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase


class EquityEventEvidenceHydrationWorker(WorkerBase):
    def __init__(self, *, repository_factory: Any, document_provider: Any, settings: Any, telemetry: Any = None) -> None:
        super().__init__(
            name="equity_event_evidence_hydration",
            interval_seconds=settings.interval_seconds,
            telemetry=telemetry,
        )
        self.repository_factory = repository_factory
        self.document_provider = document_provider
        self.settings = settings

    def run_once_sync(self) -> dict[str, Any]:
        now = self._now_ms()
        lease_owner = f"equity_event_evidence_hydration:{uuid.uuid4()}"
        with self.repository_factory() as repos:
            jobs = repos.equity_events.claim_due_evidence_jobs(
                now_ms=now,
                limit=self.settings.batch_size,
                lease_ms=self.settings.lease_seconds * 1000,
                lease_owner=lease_owner,
            )
            hydrated = 0
            terminal = 0
            failed = 0
            for job in jobs:
                try:
                    result = self.document_provider.hydrate_document_evidence(job)
                    repos.equity_events.upsert_evidence_artifacts_for_document(
                        event_document_id=job["event_document_id"],
                        evidence_artifacts=result.evidence_artifacts,
                        now_ms=self._now_ms(),
                    )
                    repos.equity_events.mark_evidence_job_done(
                        event_document_id=job["event_document_id"],
                        lease_owner=lease_owner,
                        payload_hash=result.payload_hash,
                        now_ms=self._now_ms(),
                    )
                    hydrated += 1
                except Exception as exc:
                    if int(job["attempt_count"]) >= int(job["max_attempts"]):
                        repos.equity_events.terminalize_evidence_job(
                            event_document_id=job["event_document_id"],
                            lease_owner=lease_owner,
                            terminal_reason=type(exc).__name__,
                            now_ms=self._now_ms(),
                        )
                        terminal += 1
                    else:
                        repos.equity_events.mark_evidence_job_failed(
                            event_document_id=job["event_document_id"],
                            lease_owner=lease_owner,
                            error=str(exc),
                            due_at_ms=self._now_ms() + self.settings.retry_backoff_seconds * 1000,
                            now_ms=self._now_ms(),
                        )
                        failed += 1
            return {
                "claimed": len(jobs),
                "hydrated": hydrated,
                "failed": failed,
                "terminal": terminal,
            }
```

Use the project’s existing worker time helper if `WorkerBase` exposes one; otherwise define a private `_now_ms()` in this worker.

- [ ] **Step 6.6: Wire settings, factory, manifest, queue health**

Add `EquityEventEvidenceHydrationWorkerSettings` with:

```python
enabled: bool = True
interval_seconds: float = 10.0
batch_size: int = 10
lease_seconds: int = 120
retry_backoff_seconds: int = 300
max_attempts: int = 5
```

In worker factory, construct:

```python
constructed["equity_event_evidence_hydration"] = EquityEventEvidenceHydrationWorker(...)
```

In manifest:

```python
WorkerManifestEntry(
    name="equity_event_evidence_hydration",
    writes_facts=("equity_event_evidence_artifacts",),
    writes_queues=("equity_event_evidence_jobs",),
    ...
)
```

In queue health, add `equity_event_evidence_jobs` with active statuses `pending`, `failed`, `running` and terminal statuses `terminal`, `done`.

- [ ] **Step 6.7: Update Equity architecture**

Add:

```markdown
`EquityEventFetchWorker` owns source fetch runs and document facts only.
`EquityEventEvidenceHydrationWorker` owns document-level evidence jobs and
evidence artifacts. A source fetch run must not perform provider evidence
hydration inline.
```

- [ ] **Step 6.8: Run Equity tests**

```bash
uv run pytest tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py \
              tests/integration/domains/equity_event_intel/test_equity_event_evidence_jobs.py \
              tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected:

```text
equity evidence job tests passed
architecture equity guards passed
```

- [ ] **Step 6.9: Commit Equity split**

```bash
git add src/gmgn_twitter_intel/domains/equity_event_intel \
        src/gmgn_twitter_intel/app/runtime/settings.py \
        src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py \
        src/gmgn_twitter_intel/app/runtime/worker_manifest.py \
        src/gmgn_twitter_intel/app/runtime/queue_health.py \
        tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py \
        tests/integration/domains/equity_event_intel/test_equity_event_evidence_jobs.py \
        tests/architecture/test_runtime_performance_architecture_hard_cut.py
git commit -m "feat: split equity event evidence hydration worker"
```

---

## Task 7: Hot/Cold Lifecycle And Docs Contract

**Files:**
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Create or modify CLI/script surface for dry-run lifecycle report.

- [ ] **Step 7.1: Document hot/cold table classes**

In `docs/references/POSTGRES_PERFORMANCE.md`, add a table:

| Class | Tables | Runtime rule |
| --- | --- | --- |
| Hot compact rank/read path | `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_rows`, `macro_observation_series_rows` active generation | no wide JSON/text scans; indexed by claimed work keys |
| Selected-row hydrate | `events`, `enriched_events`, `equity_event_evidence_artifacts` | accessed only after ranking or document selection |
| Cold audit/history | `token_radar_snapshot_audit_*`, `token_radar_rank_history_*`, `raw_frames` | partition lifecycle only; no worker loop deletes |
| Control plane | dirty targets, jobs, fetch runs | leased, bounded, terminal evidence |

- [ ] **Step 7.2: Add lifecycle dry-run command or script**

Create a read-only report command that outputs:

```text
table_name,total_bytes,live_rows,dead_rows,last_analyze,retention_class,recommended_action
```

Minimum SQL:

```sql
SELECT
  relname AS table_name,
  pg_total_relation_size(relid) AS total_bytes,
  n_live_tup AS live_rows,
  n_dead_tup AS dead_rows,
  last_analyze,
  CASE
    WHEN relname LIKE 'token_radar_snapshot_audit_%' THEN 'cold_audit_partition'
    WHEN relname LIKE 'token_radar_rank_history_%' THEN 'cold_rank_history_partition'
    WHEN relname = 'raw_frames' THEN 'raw_provider_archive'
    WHEN relname = 'token_radar_rank_source_events' THEN 'hot_compact_rank_source'
    ELSE 'other'
  END AS retention_class
FROM pg_stat_user_tables
WHERE relname IN (
  'raw_frames',
  'events',
  'equity_event_evidence_artifacts',
  'token_radar_rank_source_events'
)
OR relname LIKE 'token_radar_snapshot_audit_%'
OR relname LIKE 'token_radar_rank_history_%'
ORDER BY pg_total_relation_size(relid) DESC;
```

This task must not drop partitions automatically. Destructive detach/drop belongs in an operator-approved maintenance run.

- [ ] **Step 7.3: Update routers**

Update both `AGENTS.md` and `CLAUDE.md` with a single link if missing:

```markdown
| PostgreSQL performance & queue diagnostics | `docs/references/POSTGRES_PERFORMANCE.md` |
```

Keep them mirrored.

- [ ] **Step 7.4: Run docs/architecture checks**

```bash
uv run pytest tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
```

Expected:

```text
all architecture guards passed
```

- [ ] **Step 7.5: Commit lifecycle contract**

```bash
git add docs/references/POSTGRES_PERFORMANCE.md docs/ARCHITECTURE.md AGENTS.md CLAUDE.md scripts/runtime_performance_root_fix_check.sh
git commit -m "docs: codify postgres hot cold lifecycle"
```

---

## Task 8: Full Verification, Docker Rebuild, And 90/100 Score

**Files:**
- Read: `docs/TESTING.md`
- Read: `docs/SETUP.md`
- Produce evidence in final response; create `docs/generated/runtime-performance-root-fix-verification-2026-05-26.md` only if the run generates substantial command output worth preserving.

- [ ] **Step 8.1: Run focused backend tests**

```bash
uv run pytest tests/architecture/test_runtime_performance_architecture_hard_cut.py \
              tests/unit/test_postgres_schema.py \
              tests/unit/domains/news_intel/test_news_provider_contract.py \
              tests/unit/domains/token_intel/test_token_radar_rank_source_query.py \
              tests/integration/domains/token_intel/test_token_radar_rank_source_repository.py \
              tests/unit/domains/macro_intel/test_macro_generation_swap.py \
              tests/integration/domains/macro_intel/test_macro_observation_series_generation.py \
              tests/unit/domains/equity_event_intel/test_equity_event_evidence_hydration_worker.py \
              tests/integration/domains/equity_event_intel/test_equity_event_evidence_jobs.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8.2: Run standard quality gate**

Use the repo’s documented gates:

```bash
uv run pytest -q
```

If frontend files were not touched by this branch, do not run `npm run lint` unless existing project gates require it. If a frontend/ops route was changed to expose evidence, run:

```bash
cd web && npm run lint
```

- [ ] **Step 8.3: Rebuild Docker and apply migrations**

```bash
make docker-up
```

Expected:

```text
postgres healthy
migrate completed
app healthy
powa-web running
```

- [ ] **Step 8.4: Confirm latest migration head**

```bash
docker compose exec -T postgres psql -U gmgn -d gmgn_twitter_intel -Atc "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"
```

Expected:

```text
20260526_0108
```

- [ ] **Step 8.5: Confirm readyz**

```bash
curl -fsS http://127.0.0.1:8000/readyz
```

Expected JSON facts:

```json
{
  "ok": true,
  "db": {"migration": "20260526_0108"},
  "news_provider_contract": {"ok": true}
}
```

- [ ] **Step 8.6: Capture old Token Radar query calls before refresh**

```bash
BEFORE_OLD_TOKEN_RADAR_CALLS="$(docker compose exec -T postgres psql -U gmgn -d gmgn_twitter_intel -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE 'WITH request_targets AS (%';")"
echo "${BEFORE_OLD_TOKEN_RADAR_CALLS}"
```

- [ ] **Step 8.7: Trigger controlled live refresh window**

Let workers run for 180 seconds:

```bash
sleep 180
```

If an ops endpoint exists for worker wake-up, call it once before the sleep. Do not add synthetic facts unless the test database is empty.

- [ ] **Step 8.8: Confirm old Token Radar query calls did not increase**

```bash
AFTER_OLD_TOKEN_RADAR_CALLS="$(docker compose exec -T postgres psql -U gmgn -d gmgn_twitter_intel -Atc "
SELECT COALESCE(sum(calls), 0)
FROM pg_stat_statements
WHERE query ILIKE 'WITH request_targets AS (%';")"
test "${BEFORE_OLD_TOKEN_RADAR_CALLS}" = "${AFTER_OLD_TOKEN_RADAR_CALLS}"
```

Expected: command exits 0. If it fails, find the caller and delete the old path; do not accept the run.

- [ ] **Step 8.9: Run performance check script**

```bash
scripts/runtime_performance_root_fix_check.sh
```

Required values:

```text
old token radar query calls: unchanged from Step 8.6
token radar rank source p95: < 100
stale equity fetch runs: 0
token radar temp blocks: 0
top sql token radar share: < 10
```

- [ ] **Step 8.10: Run rank-source EXPLAIN**

```bash
docker compose exec -T postgres psql -U gmgn -d gmgn_twitter_intel -c "
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM token_radar_rank_source_events
WHERE projection_version = 'token-radar-rank-input-v1'
ORDER BY received_at_ms DESC
LIMIT 200;"
```

Required:

```text
Execution Time: < 100 ms
Buffers: no temp written
```

- [ ] **Step 8.11: Refresh PoWA and pgBadger evidence**

Use existing project commands from `docs/references/POSTGRES_PERFORMANCE.md`. Required evidence:

```text
powa_statements_history count > 0
pgBadger latest report path exists under /Users/qinghuan/.gmgn-twitter-intel/reports/pgbadger/
old Token Radar request_targets SQL absent from new top offenders
```

- [ ] **Step 8.12: Score the result**

Score out of 100:

| Category | Points | Required evidence |
| --- | ---: | --- |
| Readiness and migration | 15 | `/readyz ok=true`, Alembic `20260526_0108` |
| Token Radar hard cut | 25 | old query delta 0, p95 <100ms, no temp writes |
| Worker boundedness | 15 | evidence jobs active, stale fetch runs 0 |
| Macro generation safety | 10 | stage/swap tests pass |
| News config/schema contract | 10 | opennews contract green |
| Hot/cold lifecycle | 10 | lifecycle report and docs updated |
| Observability | 10 | PoWA + pgBadger refreshed |
| Regression tests | 5 | focused suite passes |

Minimum acceptable total:

```text
90/100
```

- [ ] **Step 8.13: Commit verification artifacts only if created**

```bash
git add docs/generated/runtime-performance-root-fix-verification-2026-05-26.md
git commit -m "docs: record runtime performance verification"
```

- [ ] **Step 8.14: Final merge procedure**

Only after all gates pass:

```bash
git checkout main
git merge --no-ff codex/runtime-performance-architecture-root-fix -m "merge: runtime performance architecture root fix"
make docker-up
scripts/runtime_performance_root_fix_check.sh
```

Expected final status:

```text
main ahead of origin
app healthy
postgres healthy
/readyz ok=true
score >= 90
```

---

## Root-Cause Coverage Matrix

| Spec issue | Plan task | Completion proof |
| --- | --- | --- |
| Source/schema drift breaks OpenNews readiness | Task 3, Task 8 | provider contract test, `/readyz` contract green |
| Token Radar replays wide facts | Task 4 | old query file deleted, pg_stat calls delta 0 |
| Hot rank scan reads wide payloads | Task 2, Task 4 | compact edge schema, query test forbids wide fields |
| Macro delete-all refresh can expose empty projection | Task 5 | generation swap tests |
| Equity source fetch hydrates evidence inline | Task 6 | fetch worker guard, new evidence job worker |
| Stale equity running rows persist | Task 6, Task 8 | reaper method, SQL stale count 0 |
| Hot/cold lifecycle missing | Task 7 | docs and lifecycle report |
| Performance score not objective | Task 1, Task 8 | script, PoWA/pgBadger, score sheet |

---

## Review Checklist Before Claiming Complete

- [ ] `rg "TokenRadarTargetFeatureBatchQuery|source_rows_for_requests|WITH request_targets AS" src tests` returns no runtime reference; historical docs may mention it only as deleted evidence.
- [ ] `rg "hydrate_document_evidence" src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py` returns nothing.
- [ ] `rg "DELETE FROM macro_observation_series_rows" src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py` returns no projection-version delete-all pattern.
- [ ] `uv run pytest -q` passes or every failure is proven unrelated to this branch and documented.
- [ ] `make docker-up` completes after merge to main.
- [ ] `/readyz` is green on rebuilt Docker.
- [ ] `scripts/runtime_performance_root_fix_check.sh` satisfies all numeric gates.
- [ ] PoWA and pgBadger are refreshed after rebuild.
- [ ] Final score is at least `90/100`.
