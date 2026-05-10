# tests/e2e/conftest.py
"""Auto-mark every test under tests/e2e/ as @pytest.mark.e2e (placeholder; P5 replaces this with real fixtures)."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in str(item.path):
            item.add_marker(pytest.mark.e2e)
