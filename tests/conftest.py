# tests/conftest.py
"""Root conftest: marker registration and cross-layer fixtures."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register lane markers for strict-marker collection and IDE discovery."""
    for marker in ("unit", "integration", "e2e", "golden", "architecture", "contract"):
        config.addinivalue_line("markers", f"{marker}: tests in tests/{marker}/")
