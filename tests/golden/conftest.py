# tests/golden/conftest.py
"""Auto-mark golden corpus tests as @pytest.mark.e2e.

These tests run a real ingest -> projection pipeline against a real Postgres,
so they belong to the e2e gate by semantics even though they live in their
own directory for organizational reasons.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/golden/" in str(item.path):
            item.add_marker(pytest.mark.e2e)
