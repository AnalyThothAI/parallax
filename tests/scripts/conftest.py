# tests/scripts/conftest.py
"""Re-export the integration-suite session fixture so scripts/ tests get a usable Postgres DSN."""

from __future__ import annotations

from tests.integration.conftest import _ensure_postgres_dsn  # noqa: F401  pytest discovers via conftest
