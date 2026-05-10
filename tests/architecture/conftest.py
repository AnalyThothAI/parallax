# tests/architecture/conftest.py
"""Auto-mark every test under tests/architecture/ as @pytest.mark.architecture."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/architecture/" in str(item.fspath):
            item.add_marker(pytest.mark.architecture)
