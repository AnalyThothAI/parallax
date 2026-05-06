# PostgreSQL Production Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SQLite runtime with a PostgreSQL-only production storage layer, started by Docker Compose, without dual runtime compatibility.

**Architecture:** PostgreSQL becomes the sole source-of-truth database. The app uses psycopg 3 connection pooling and Alembic migrations; runtime code removes SQLite connection/schema paths. Existing business services keep their public contracts while repository SQL, FTS, queue claiming, and test fixtures are rewritten for PostgreSQL.

**Tech Stack:** Python 3.13, FastAPI, psycopg 3, psycopg_pool, Alembic, PostgreSQL 18 Docker image, pytest, Docker Compose.

---

## File Structure

Create:

- `src/gmgn_twitter_intel/storage/postgres_client.py` — psycopg pool, connection context managers, transactions, liveness checks.
- `src/gmgn_twitter_intel/storage/postgres_migrations.py` — Alembic command entrypoint wrapper for CLI.
- `alembic.ini` — Alembic configuration.
- `src/gmgn_twitter_intel/storage/alembic/env.py` — Alembic environment that reads the app settings.
- `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0001_initial_postgresql.py` — initial PostgreSQL schema.
- `scripts/sqlite_to_postgres.py` — one-shot offline importer from SQLite backup to PostgreSQL.
- `tests/postgres_fixtures.py` — PostgreSQL test DB/pool fixture helpers.
- `tests/test_postgres_schema.py` — schema and migration assertions.
- `tests/test_postgres_repositories.py` — migrated repository smoke tests.
- `tests/test_postgres_api_health.py` — readiness/liveness PostgreSQL behavior.
- `tests/test_compose_postgres.py` — Compose config assertions.

Modify:

- `pyproject.toml` — add `psycopg[binary,pool]`, `alembic`, and test helper dependencies.
- `compose.yaml` — add `postgres` and `migrate`, switch app dependency and volume layout.
- `README.md` — replace SQLite operations with PostgreSQL operations.
- `src/gmgn_twitter_intel/settings.py` — replace `sqlite_path` with PostgreSQL config.
- `src/gmgn_twitter_intel/api/app.py` — build runtime from PostgreSQL pool/repositories.
- `src/gmgn_twitter_intel/cli.py` — add `db migrate/version/audit/import-sqlite`; update repository wiring.
- `src/gmgn_twitter_intel/storage/*.py` — remove sqlite type imports, update SQL and exception handling.
- `src/gmgn_twitter_intel/retrieval/*.py` — update direct connection typing, FTS, window query syntax and deterministic ordering.
- `tests/*.py` — replace `connect_sqlite`/`migrate` fixtures with PostgreSQL fixtures.

Delete after migration:

- `src/gmgn_twitter_intel/storage/sqlite_client.py`
- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- SQLite-specific tests after their PostgreSQL replacements exist.

---

## Task 1: Dependencies And Compose

**Files:**

- Modify: `pyproject.toml`
- Modify: `compose.yaml`
- Test: `tests/test_compose_postgres.py`

- [ ] Add dependencies to `pyproject.toml`.

Use these runtime dependencies:

```toml
"alembic>=1.18.0",
"psycopg[binary,pool]>=3.2.0",
```

Keep pytest/ruff dev dependencies as-is.

- [ ] Add a failing Compose test.

Create `tests/test_compose_postgres.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_runs_postgres_and_migration_before_app() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    services = compose["services"]

    assert "postgres" in services
    assert "migrate" in services
    assert services["postgres"]["image"].startswith("postgres:")
    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "pg_isready" in services["postgres"]["healthcheck"]["test"][1]

    app_depends = services["app"]["depends_on"]
    assert app_depends["postgres"]["condition"] == "service_healthy"
    assert app_depends["migrate"]["condition"] == "service_completed_successfully"
    assert services["app"]["healthcheck"]["test"][2] == "-c"
    assert "/healthz" in services["app"]["healthcheck"]["test"][3]


def test_compose_no_longer_mounts_sqlite_data_volume_into_app() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    app_volumes = compose["services"]["app"].get("volumes", [])
    assert all("/root/.gmgn-twitter-intel/data" not in volume for volume in app_volumes)
    assert "gmgn-twitter-intel-postgres" in compose["volumes"]
```

- [ ] Run the failing test.

Run:

```bash
uv run pytest tests/test_compose_postgres.py -q
```

Expected: FAIL because `postgres` and `migrate` do not exist.

- [ ] Update `compose.yaml`.

Use this target shape:

```yaml
name: gmgn-twitter-intel

services:
  postgres:
    image: postgres:18-bookworm
    restart: unless-stopped
    shm_size: 256mb
    environment:
      POSTGRES_DB: gmgn_twitter_intel
      POSTGRES_USER: gmgn_app
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256 --data-checksums"
    secrets:
      - postgres_password
    volumes:
      - gmgn-twitter-intel-postgres:/var/lib/postgresql/18/docker
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gmgn_app -d gmgn_twitter_intel"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

  migrate:
    build: .
    restart: "no"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ${HOME}/.gmgn-twitter-intel:/root/.gmgn-twitter-intel
    command: ["gmgn-twitter-intel", "db", "migrate"]

  app:
    build: .
    init: true
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    ports:
      - "8765:8765"
    volumes:
      - ${HOME}/.gmgn-twitter-intel:/root/.gmgn-twitter-intel
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/healthz', timeout=10).read()",
        ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

volumes:
  gmgn-twitter-intel-postgres:

secrets:
  postgres_password:
    file: ${HOME}/.gmgn-twitter-intel/postgres_password
```

- [ ] Run the Compose test again.

Run:

```bash
uv run pytest tests/test_compose_postgres.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add pyproject.toml compose.yaml tests/test_compose_postgres.py
git commit -m "build: add postgres compose topology"
```

---

## Task 2: PostgreSQL Settings

**Files:**

- Modify: `src/gmgn_twitter_intel/settings.py`
- Modify: `tests/test_settings.py`

- [ ] Add failing settings tests.

Add tests that assert:

```python
def test_postgres_storage_config_replaces_sqlite_path(tmp_path, monkeypatch):
    home = tmp_path / ".gmgn-twitter-intel"
    home.mkdir()
    (home / "config.yaml").write_text(
        """
ws_token: token
storage:
  postgres:
    dsn: "postgresql://gmgn_app:secret@postgres:5432/gmgn_twitter_intel"
    pool_min_size: 2
    pool_max_size: 12
    connect_timeout_seconds: 4
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    settings = load_settings()

    assert settings.postgres_dsn == "postgresql://gmgn_app:secret@postgres:5432/gmgn_twitter_intel"
    assert settings.postgres_pool_min_size == 2
    assert settings.postgres_pool_max_size == 12
    assert settings.postgres_connect_timeout_seconds == 4
    assert not hasattr(settings, "sqlite_path")
```

Also update config output expectations in `tests/test_cli.py` later under Task 6.

- [ ] Implement settings model.

Replace `StorageConfig.sqlite_path` with:

```python
class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dsn: str = "postgresql://gmgn_app:gmgn_app@postgres:5432/gmgn_twitter_intel"
    password_file: str | None = None
    pool_min_size: int = 1
    pool_max_size: int = 10
    connect_timeout_seconds: float = 5.0


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
```

Add properties:

```python
@property
def postgres_dsn(self) -> str:
    return self.storage.postgres.dsn

@property
def postgres_password_file(self) -> Path | None:
    value = self.storage.postgres.password_file
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else self.config_dir / path

@property
def postgres_pool_min_size(self) -> int:
    return self.storage.postgres.pool_min_size

@property
def postgres_pool_max_size(self) -> int:
    return self.storage.postgres.pool_max_size

@property
def postgres_connect_timeout_seconds(self) -> float:
    return self.storage.postgres.connect_timeout_seconds
```

Update default config template to use `storage.postgres`.

- [ ] Run settings tests.

Run:

```bash
uv run pytest tests/test_settings.py -q
```

Expected: PASS after updating SQLite assertions to PostgreSQL assertions.

- [ ] Commit.

```bash
git add src/gmgn_twitter_intel/settings.py tests/test_settings.py
git commit -m "config: replace sqlite storage settings with postgres"
```

---

## Task 3: PostgreSQL Client

**Files:**

- Create: `src/gmgn_twitter_intel/storage/postgres_client.py`
- Test: `tests/test_postgres_client.py`

- [ ] Write client tests.

Create `tests/test_postgres_client.py` with tests for DSN password file application and health payload shape. Use a fake connection object for health check so this test does not require a live database:

```python
from __future__ import annotations

from gmgn_twitter_intel.storage.postgres_client import postgres_health_check, with_password_from_file


class FakeCursor:
    def __init__(self):
        self.last_sql = ""

    def execute(self, sql, params=None):
        self.last_sql = str(sql)
        return self

    def fetchone(self):
        if "alembic_version" in self.last_sql:
            return {"version_num": "20260506_0001"}
        return {"ok": 1}


class FakeConn:
    def execute(self, sql, params=None):
        return FakeCursor().execute(sql, params)


def test_with_password_from_file_replaces_password(tmp_path):
    password_file = tmp_path / "pg_password"
    password_file.write_text("secret-pass\n", encoding="utf-8")

    dsn = with_password_from_file(
        "postgresql://gmgn_app:old-pass@postgres:5432/gmgn_twitter_intel",
        password_file,
    )

    assert "secret-pass" in dsn
    assert "old-pass" not in dsn


def test_postgres_health_check_reports_liveness_and_migration_version():
    payload = postgres_health_check(FakeConn())

    assert payload == {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": "20260506_0001",
    }
```

- [ ] Implement `postgres_client.py`.

Use psycopg pool and dict rows:

```python
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from psycopg import Connection, conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def with_password_from_file(dsn: str, password_file: Path | None) -> str:
    if password_file is None:
        return dsn
    password = password_file.read_text(encoding="utf-8").strip()
    parts = conninfo.conninfo_to_dict(dsn)
    parts["password"] = password
    return conninfo.make_conninfo(**parts)


def create_pool(
    dsn: str,
    *,
    min_size: int,
    max_size: int,
    connect_timeout_seconds: float,
) -> ConnectionPool:
    return ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={
            "autocommit": False,
            "connect_timeout": int(connect_timeout_seconds),
            "row_factory": dict_row,
        },
        open=True,
    )


@contextmanager
def transaction(conn: Connection) -> Iterator[None]:
    with conn.transaction():
        yield


def postgres_health_check(conn) -> dict[str, object]:
    row = conn.execute("SELECT 1 AS ok").fetchone()
    if row is None or int(row["ok"]) != 1:
        return {"ok": False, "probe": "postgres_liveness", "detail": "missing_select_result"}
    version_row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": version_row["version_num"] if version_row else None,
    }
```

- [ ] Run tests.

Run:

```bash
uv run pytest tests/test_postgres_client.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add src/gmgn_twitter_intel/storage/postgres_client.py tests/test_postgres_client.py
git commit -m "storage: add postgres client"
```

---

## Task 4: Alembic Initial Schema

**Files:**

- Create: `alembic.ini`
- Create: `src/gmgn_twitter_intel/storage/alembic/env.py`
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0001_initial_postgresql.py`
- Create: `src/gmgn_twitter_intel/storage/postgres_migrations.py`
- Test: `tests/test_postgres_schema.py`

- [ ] Add schema tests that inspect migration file text.

Create `tests/test_postgres_schema.py`:

```python
from __future__ import annotations

from pathlib import Path


MIGRATION = Path("src/gmgn_twitter_intel/storage/alembic/versions/20260506_0001_initial_postgresql.py")


def test_initial_postgres_schema_uses_jsonb_boolean_and_tsvector() -> None:
    text = MIGRATION.read_text()

    assert "jsonb" in text
    assert "boolean" in text
    assert "tsvector" in text
    assert "USING GIN" in text
    assert "websearch_to_tsquery" not in text


def test_initial_postgres_schema_has_no_sqlite_pragmas_or_fts5() -> None:
    text = MIGRATION.read_text().lower()

    assert "pragma" not in text
    assert "fts5" not in text
    assert "virtual table" not in text
```

- [ ] Create Alembic files.

`alembic.ini` should point at `src/gmgn_twitter_intel/storage/alembic`.

`postgres_migrations.py` should expose:

```python
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    return cfg


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")


def current_version() -> str | None:
    cfg = alembic_config()
    # Implement via command.current capture in CLI task or direct SQL through postgres_client.
    return None
```

`env.py` should load `Settings`, apply password file if set, and configure Alembic URL.

- [ ] Write initial PostgreSQL schema.

The migration must create all current tables except `event_fts`. It must add `events.search_tsv` generated column and a GIN index.

Use PostgreSQL types:

```sql
CREATE TABLE events (
  event_id text PRIMARY KEY,
  logical_dedup_key text NOT NULL UNIQUE,
  canonical_url text,
  source_provider text NOT NULL,
  source_transport text NOT NULL,
  coverage text NOT NULL,
  channel text NOT NULL,
  action text NOT NULL,
  original_action text,
  tweet_id text,
  internal_id text,
  timestamp_ms bigint NOT NULL,
  received_at_ms bigint NOT NULL,
  author_handle text,
  author_name text,
  author_avatar text,
  author_followers bigint,
  author_tags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  text text,
  text_raw text,
  text_clean text,
  search_text text,
  urls_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  cashtags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  hashtags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  mentions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  media_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  reference_json jsonb,
  matched_handles_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  is_watched boolean NOT NULL DEFAULT false,
  matched_at_ms bigint NOT NULL DEFAULT 0,
  raw_json jsonb NOT NULL,
  event_json jsonb NOT NULL,
  search_tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(author_handle, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(search_text, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(text_clean, '')), 'C')
  ) STORED,
  created_at_ms bigint NOT NULL,
  updated_at_ms bigint NOT NULL
);
```

Create equivalent indexes with deterministic sort columns.

- [ ] Run schema text tests.

Run:

```bash
uv run pytest tests/test_postgres_schema.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add alembic.ini src/gmgn_twitter_intel/storage/alembic src/gmgn_twitter_intel/storage/postgres_migrations.py tests/test_postgres_schema.py
git commit -m "db: add initial postgres schema migration"
```

---

## Task 5: Repository SQL Migration

**Files:**

- Modify: `src/gmgn_twitter_intel/storage/evidence_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/entity_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/signal_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/token_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/market_observation_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/harness_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/notification_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/account_quality_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/token_signal_repository.py`
- Test: PostgreSQL repository tests.

- [ ] Convert imports.

Replace:

```python
import sqlite3
```

with:

```python
from psycopg import errors
```

Where type hints are needed:

```python
from typing import Any, Protocol


class DbConnection(Protocol):
    def execute(self, query: str, params: object | None = None): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

This protocol is not a dual-database compatibility layer; it describes the psycopg connection surface used by repositories.

- [ ] Convert placeholders.

Rules:

| Current | PostgreSQL |
|---|---|
| `?` | `%s` |
| `:event_id` | `%(event_id)s` |
| `INSERT OR IGNORE` | `ON CONFLICT DO NOTHING` |
| `excluded.col` | unchanged |

- [ ] Convert duplicate handling.

Replace:

```python
except sqlite3.IntegrityError:
```

with:

```python
except errors.UniqueViolation:
```

For psycopg, failed transactions require rollback before reuse when the exception escapes. Repository methods that swallow duplicate errors must call `self.conn.rollback()` only when operating outside an explicit transaction. Prefer `ON CONFLICT DO NOTHING RETURNING key` to avoid exception-driven duplicates.

- [ ] Convert JSON writes.

Use psycopg Jsonb adapter:

```python
from psycopg.types.json import Jsonb


def _jsonb(value: Any) -> Jsonb:
    return Jsonb(value)
```

For columns still named `*_json`, pass Python dict/list through `Jsonb`.

- [ ] Convert row decode helpers.

Update `_json_loads` helpers:

```python
def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value
```

- [ ] Remove `event_fts` writes.

In `EvidenceRepository.insert_event_without_commit`, delete the explicit insert into `event_fts`. PostgreSQL generated `search_tsv` handles FTS.

- [ ] Add deterministic ordering.

Every query ordered by `received_at_ms` must include a stable tie-breaker:

```sql
ORDER BY received_at_ms DESC, event_id DESC
```

or a table-specific primary key.

- [ ] Commit repositories in batches.

Use small commits:

```bash
git add src/gmgn_twitter_intel/storage/evidence_repository.py src/gmgn_twitter_intel/storage/entity_repository.py
git commit -m "storage: migrate evidence repositories to postgres"

git add src/gmgn_twitter_intel/storage/signal_repository.py src/gmgn_twitter_intel/storage/token_repository.py
git commit -m "storage: migrate token repositories to postgres"

git add src/gmgn_twitter_intel/storage/enrichment_repository.py src/gmgn_twitter_intel/storage/market_observation_repository.py src/gmgn_twitter_intel/storage/notification_repository.py
git commit -m "storage: migrate job repositories to postgres"

git add src/gmgn_twitter_intel/storage/harness_repository.py src/gmgn_twitter_intel/storage/account_quality_repository.py src/gmgn_twitter_intel/storage/token_signal_repository.py
git commit -m "storage: migrate analytics repositories to postgres"
```

---

## Task 6: Runtime And CLI Wiring

**Files:**

- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_postgres_api_health.py`
- Test: `tests/test_cli.py`

- [ ] Add health tests.

Test expectations:

```python
def test_readyz_reports_postgres_liveness_without_integrity_scan():
    payload = {"ok": True, "probe": "postgres_liveness", "migration_version": "20260506_0001"}
    assert payload["probe"] == "postgres_liveness"
```

Update existing health tests to assert no SQLite probe names remain.

- [ ] Build runtime from pool.

In `api/app.py`:

- Create one `ConnectionPool`.
- Use pool connections per request/worker operation or scoped repository sets.
- Remove `read_conn = connect_sqlite(...)`.
- Remove `write_lock` from simple DB serialization. Keep locks only for in-process non-DB shared structures if any.
- Replace `sqlite_health_check` with `postgres_health_check`.
- Change readiness `"store"` to not print a password-bearing DSN. Return host/db/user without password or return `"postgres"`.

- [ ] Add CLI db commands.

Add parser:

```python
db = subcommands.add_parser("db", help="database operations")
db_subcommands = db.add_subparsers(dest="db_command", required=True)
db_subcommands.add_parser("migrate", help="run PostgreSQL migrations")
db_subcommands.add_parser("version", help="print PostgreSQL migration version")
db_subcommands.add_parser("audit", help="run PostgreSQL count and integrity audit")
```

Implement:

- `db migrate` calls Alembic upgrade head.
- `db version` prints current Alembic version.
- `db audit` checks counts and FK orphan queries.

- [ ] Update `_repositories`.

Replace `_repositories(sqlite_path)` with `_repositories(settings)` that uses PostgreSQL pool/connection.

- [ ] Run CLI/API tests.

Run:

```bash
uv run pytest tests/test_postgres_api_health.py tests/test_cli.py -q
```

Expected: PASS after test updates.

- [ ] Commit.

```bash
git add src/gmgn_twitter_intel/api/app.py src/gmgn_twitter_intel/cli.py tests/test_postgres_api_health.py tests/test_cli.py
git commit -m "runtime: wire app and cli to postgres"
```

---

## Task 7: Retrieval SQL Migration

**Files:**

- Modify: `src/gmgn_twitter_intel/retrieval/search_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/rolling_token_flow.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_posts_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/harness_service.py`
- Test: migrated retrieval tests.

- [ ] Replace FTS query.

`EvidenceRepository.search_fts()` should use:

```sql
WITH query AS (SELECT websearch_to_tsquery('simple', %s) AS tsq)
SELECT e.*, ts_rank_cd(e.search_tsv, query.tsq) AS score
FROM events e, query
WHERE e.search_tsv @@ query.tsq
  AND (%s = false OR e.is_watched = true)
ORDER BY score DESC, e.received_at_ms DESC, e.event_id DESC
LIMIT %s
```

`count_fts()` should use the same `tsq`.

- [ ] Convert direct SQL placeholders and bool checks.

Examples:

```sql
eta.is_watched = true
```

instead of:

```sql
eta.is_watched = 1
```

- [ ] Preserve no-lookahead.

Tests in `tests/test_token_flow_no_lookahead.py` must still pass. Any market snapshot query must keep `received_at_ms <= reference_ms`.

- [ ] Run retrieval tests.

Run:

```bash
uv run pytest tests/test_sqlite_retrieval_services.py tests/test_token_rolling_flow.py tests/test_token_posts_service.py tests/test_token_social_timeline_service.py tests/test_account_quality_service.py tests/test_token_flow_no_lookahead.py -q
```

Expected: PASS after renaming SQLite-specific test module names or updating imports.

- [ ] Commit.

```bash
git add src/gmgn_twitter_intel/retrieval tests
git commit -m "retrieval: migrate analytical queries to postgres"
```

---

## Task 8: PostgreSQL Job Claiming

**Files:**

- Modify: `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/market_observation_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/notification_repository.py`
- Modify: worker tests.

- [ ] Replace queue claim read/update pairs with atomic CTE claims.

Use this pattern for each queue:

```sql
WITH picked AS (
  SELECT job_id
  FROM enrichment_jobs
  WHERE status IN ('pending', 'failed')
    AND next_run_at_ms <= %s
  ORDER BY priority ASC, next_run_at_ms ASC, created_at_ms ASC
  LIMIT %s
  FOR UPDATE SKIP LOCKED
)
UPDATE enrichment_jobs j
SET status = 'running',
    attempt_count = attempt_count + 1,
    updated_at_ms = %s
FROM picked
WHERE j.job_id = picked.job_id
RETURNING j.*
```

Use equivalent primary key names for observations and deliveries.

- [ ] Add tests for double claiming.

Test that two connections cannot claim the same pending job when one transaction holds the row lock.

- [ ] Run worker tests.

Run:

```bash
uv run pytest tests/test_enrichment_worker.py tests/test_market_observation_worker.py tests/test_notification_worker.py tests/test_notification_delivery.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add src/gmgn_twitter_intel/storage/enrichment_repository.py src/gmgn_twitter_intel/storage/market_observation_repository.py src/gmgn_twitter_intel/storage/notification_repository.py tests
git commit -m "workers: use postgres row locking for job claims"
```

---

## Task 9: One-Shot SQLite Importer

**Files:**

- Create: `scripts/sqlite_to_postgres.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_sqlite_to_postgres_importer.py`

- [ ] Write importer unit tests for conversion helpers.

Test:

- `0/1` converts to bool for boolean columns.
- JSON text converts to Python dict/list.
- invalid JSON raises an importer error with table/column context.
- `event_fts` is skipped.

- [ ] Implement importer.

Importer inputs:

```bash
uv run python scripts/sqlite_to_postgres.py \
  --sqlite-path /backup/twitter_intel.sqlite3 \
  --batch-size 1000 \
  --truncate-target
```

Table order:

1. `raw_frames`
2. `events`
3. `event_entities`
4. `tokens`
5. `token_aliases`
6. `token_market_snapshots`
7. `account_token_alerts`
8. `event_token_mentions`
9. `event_token_attributions`
10. queue/audit/read model tables in foreign-key order

Skip:

- `event_fts`
- SQLite internal FTS shadow tables.

- [ ] Add audit output.

Importer must print:

```json
{
  "ok": true,
  "data": {
    "tables": {
      "events": {"sqlite_count": 97173, "postgres_count": 97173}
    }
  }
}
```

- [ ] Run importer tests.

Run:

```bash
uv run pytest tests/test_sqlite_to_postgres_importer.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add scripts/sqlite_to_postgres.py src/gmgn_twitter_intel/cli.py tests/test_sqlite_to_postgres_importer.py
git commit -m "ops: add one-shot sqlite to postgres importer"
```

---

## Task 10: Remove SQLite Runtime

**Files:**

- Delete: `src/gmgn_twitter_intel/storage/sqlite_client.py`
- Delete: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Modify: tests and docs references.

- [ ] Add guard test.

Create/update `tests/test_project_structure.py`:

```python
from pathlib import Path


def test_runtime_no_longer_contains_sqlite_storage_modules() -> None:
    assert not Path("src/gmgn_twitter_intel/storage/sqlite_client.py").exists()
    assert not Path("src/gmgn_twitter_intel/storage/sqlite_schema.py").exists()


def test_runtime_source_has_no_sqlite_imports() -> None:
    offenders = []
    for path in Path("src/gmgn_twitter_intel").rglob("*.py"):
        text = path.read_text()
        if "sqlite3" in text or "connect_sqlite" in text or "sqlite_schema" in text:
            offenders.append(str(path))
    assert offenders == []
```

- [ ] Delete SQLite modules.

Remove the two runtime files and update imports.

- [ ] Rename SQLite-specific tests.

Rename tests to PostgreSQL names where they still apply:

- `tests/test_sqlite_repositories.py` -> `tests/test_postgres_repositories.py`
- `tests/test_sqlite_schema.py` -> `tests/test_postgres_schema.py`
- `tests/test_sqlite_retrieval_services.py` -> `tests/test_postgres_retrieval_services.py`

- [ ] Run structure tests.

Run:

```bash
uv run pytest tests/test_project_structure.py -q
```

Expected: PASS.

- [ ] Commit.

```bash
git add -A src/gmgn_twitter_intel/storage tests
git commit -m "storage: remove sqlite runtime"
```

---

## Task 11: Documentation

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md` if present in repository root.
- Modify: docs that explicitly prescribe SQLite runtime.

- [ ] Replace runtime docs.

Update README sections:

- Docker now starts PostgreSQL.
- Config uses `storage.postgres`.
- Backup uses `pg_dump`.
- Restore uses `psql` or `pg_restore`.
- Query Docker data through API/WS/CLI against PostgreSQL.

- [ ] Add PostgreSQL ops commands.

Document:

```bash
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d app
docker compose exec app gmgn-twitter-intel db version
docker compose exec app gmgn-twitter-intel db audit
docker compose exec postgres pg_dump -U gmgn_app -d gmgn_twitter_intel -Fc > backup.dump
```

- [ ] Remove SQLite operational instructions.

Remove `.backup`, `sqlite3`, WAL notes, and named SQLite data volume notes from production docs.

- [ ] Commit.

```bash
git add README.md docs AGENTS.md
git commit -m "docs: document postgres runtime"
```

---

## Task 12: Full Verification

**Files:**

- No code changes expected.

- [ ] Sync dependencies.

Run:

```bash
uv sync
```

Expected: dependencies resolve.

- [ ] Run static checks.

Run:

```bash
uv run ruff check .
uv run python -m compileall src tests
```

Expected: both pass.

- [ ] Run tests.

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] Run Docker Compose verification.

Create local secret if missing:

```bash
mkdir -p "$HOME/.gmgn-twitter-intel"
test -f "$HOME/.gmgn-twitter-intel/postgres_password" || openssl rand -base64 32 > "$HOME/.gmgn-twitter-intel/postgres_password"
```

Start:

```bash
docker compose up -d --build postgres
docker compose run --rm migrate
docker compose up -d --build app
```

Verify:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/readyz
docker compose exec app gmgn-twitter-intel db version
docker compose exec app gmgn-twitter-intel db audit
```

Expected:

- `postgres` healthy.
- `migrate` exits 0.
- `app` healthy.
- `/healthz` returns `ok`.
- `/readyz` includes `"probe":"postgres_liveness"`.
- `db audit` returns `ok: true`.

- [ ] Run live smoke queries.

Run:

```bash
docker compose exec app gmgn-twitter-intel recent --limit 5
docker compose exec app gmgn-twitter-intel search --symbol PEPE --limit 5
docker compose exec app gmgn-twitter-intel token-flow --window 5m --limit 20
docker compose exec app gmgn-twitter-intel account-alerts --window 24h --limit 20
docker compose exec app gmgn-twitter-intel enrichment-jobs --limit 20
docker compose exec app gmgn-twitter-intel market-observations --limit 20
```

Expected: each command returns JSON with `"ok":true`.

- [ ] Commit verification-only doc/test updates if any.

```bash
git status --short
```

Expected: no uncommitted code changes except intentionally generated local data.

---

## Cutover Runbook

Use this when moving an existing live SQLite deployment to PostgreSQL with history preserved.

1. Stop app:

```bash
docker compose stop app
```

2. Backup SQLite from old volume:

```bash
docker compose run --rm app python - <<'PY'
import sqlite3
from pathlib import Path
src = Path("/root/.gmgn-twitter-intel/data/twitter_intel.sqlite3")
dst = Path("/root/.gmgn-twitter-intel/twitter_intel-cutover.sqlite3")
conn = sqlite3.connect(src)
backup = sqlite3.connect(dst)
conn.backup(backup)
backup.close()
conn.close()
print(dst)
PY
```

3. Start PostgreSQL and migrate schema:

```bash
docker compose up -d postgres
docker compose run --rm migrate
```

4. Import SQLite backup:

```bash
docker compose run --rm app uv run python scripts/sqlite_to_postgres.py \
  --sqlite-path /root/.gmgn-twitter-intel/twitter_intel-cutover.sqlite3 \
  --batch-size 1000 \
  --truncate-target
```

5. Audit:

```bash
docker compose run --rm app gmgn-twitter-intel db audit
```

6. Start app:

```bash
docker compose up -d app
```

7. Verify:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/readyz
```

Rollback before new data accumulates:

```bash
docker compose stop app postgres
git revert <postgres-migration-commit-range>
docker compose up -d --build app
```

After PostgreSQL app has accepted new live events, rollback requires either accepting data loss after cutover or exporting the delta from PostgreSQL. Do not treat rollback as free after live writes resume.

---

## Final Gate

The migration is complete only when:

- Runtime source contains no `sqlite3`, `connect_sqlite`, `sqlite_schema`, `PRAGMA`, or FTS5 references.
- `uv run pytest`, `uv run ruff check .`, and `uv run python -m compileall src tests` pass.
- Docker Compose starts `postgres`, runs `migrate`, and starts healthy `app`.
- `/readyz` reports PostgreSQL liveness and Alembic version.
- Ingest, replay, search, token flow, account alerts, enrichment jobs, market observations, harness queries, and notifications all pass smoke tests.
- One-shot importer has either migrated historical SQLite data with counts matching, or the product owner explicitly accepted starting from an empty PostgreSQL database.
