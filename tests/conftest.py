# tests/conftest.py
"""Root conftest: marker registration and cross-layer fixtures."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Markers are registered in pyproject.toml; this is a safety net for IDE collection."""
    # Markers are also declared in pyproject.toml [tool.pytest.ini_options].
    # Listing them here makes them discoverable when pytest is invoked without
    # the project's pyproject.toml on the active config path (e.g. some IDE plugins).
    for marker in ("unit", "integration", "e2e", "architecture", "contract"):
        config.addinivalue_line("markers", f"{marker}: tests in tests/{marker}/")
