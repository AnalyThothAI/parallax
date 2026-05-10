# tests/integration/conftest.py
"""Auto-mark every test under tests/integration/ as @pytest.mark.integration."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration/" in str(item.path):
            item.add_marker(pytest.mark.integration)
