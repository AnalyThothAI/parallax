# tests/unit/conftest.py
"""Auto-mark every test under tests/unit/ as @pytest.mark.unit."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/unit/" in str(item.path):
            item.add_marker(pytest.mark.unit)
