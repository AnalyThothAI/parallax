# tests/golden/conftest.py
"""Auto-mark golden corpus tests as @pytest.mark.e2e.

These tests run a real ingest -> projection pipeline against a real Postgres,
so they belong to the e2e gate by semantics even though they live in their
own directory for organizational reasons.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator

import psycopg
import pytest

DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:55432/parallax_test"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/golden/" in str(item.path):
            item.add_marker(pytest.mark.e2e)


def _dsn_reachable(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            return True
    except Exception:
        return False


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=False).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def _ensure_golden_postgres_dsn() -> Iterator[None]:
    existing = os.environ.get("GMGN_TEST_POSTGRES_DSN", DEFAULT_DSN)

    if _dsn_reachable(existing):
        os.environ["GMGN_TEST_POSTGRES_DSN"] = existing
        yield
        return

    if os.environ.get("SKIP_GOLDEN") == "1":
        pytest.skip(
            "SKIP_GOLDEN=1 set; golden tests skipped (this run cannot serve as verification evidence)",
            allow_module_level=True,
        )

    if not _docker_available():
        pytest.fail(
            "Golden tests require a reachable Postgres but none was found. Fix options:\n"
            f"  1. Start your local test DB at {existing}.\n"
            "  2. Provide GMGN_TEST_POSTGRES_DSN=postgresql://...\n"
            "  3. Start Docker Desktop / colima / OrbStack and rerun.\n"
            "  4. If this is intentional, set SKIP_GOLDEN=1, but that run is not final verification.",
            pytrace=False,
        )

    from testcontainers.postgres import PostgresContainer

    from parallax.platform.db.postgres_migrations import upgrade_head
    from tests.postgres_observability_container import observability_postgres_container

    with observability_postgres_container(PostgresContainer) as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        try:
            upgrade_head(dsn)
        except Exception as exc:
            pytest.fail(
                f"alembic upgrade head failed against golden testcontainers PG ({dsn}): {exc}",
                pytrace=False,
            )
        os.environ["GMGN_TEST_POSTGRES_DSN"] = dsn
        yield
