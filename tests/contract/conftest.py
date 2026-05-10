# tests/contract/conftest.py
"""Auto-mark every test under tests/contract/ as @pytest.mark.contract."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/contract/" in str(item.fspath):
            item.add_marker(pytest.mark.contract)
