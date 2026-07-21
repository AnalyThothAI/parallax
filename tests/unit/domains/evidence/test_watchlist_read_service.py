from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.evidence.read_models.watchlist_read_service import (
    WatchlistReadConfig,
    WatchlistReadService,
)


@pytest.mark.parametrize("window_days", [0, -1, True, "3"])
def test_handles_overview_rejects_malformed_window_config_before_repository(window_days: object) -> None:
    query = _FakeWatchlistQuery()
    service = WatchlistReadService(
        query=query,
        config=WatchlistReadConfig(
            window_days=window_days,  # type: ignore[arg-type]
            overview_source_limit=500,
            overview_cluster_limit=500,
        ),
    )

    with pytest.raises(ValueError, match="watchlist_window_days_required"):
        service.handles_overview(configured_handles=("toly",), now_ms=1_700_000_000_000)

    assert query.calls == []


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("window_days", 0, "watchlist_window_days_required"),
        ("window_days", -1, "watchlist_window_days_required"),
        ("window_days", True, "watchlist_window_days_required"),
        ("window_days", "3", "watchlist_window_days_required"),
        ("overview_source_limit", 0, "watchlist_overview_source_limit_required"),
        ("overview_source_limit", -1, "watchlist_overview_source_limit_required"),
        ("overview_source_limit", True, "watchlist_overview_source_limit_required"),
        ("overview_source_limit", "500", "watchlist_overview_source_limit_required"),
        ("overview_cluster_limit", 0, "watchlist_overview_cluster_limit_required"),
        ("overview_cluster_limit", -1, "watchlist_overview_cluster_limit_required"),
        ("overview_cluster_limit", True, "watchlist_overview_cluster_limit_required"),
        ("overview_cluster_limit", "500", "watchlist_overview_cluster_limit_required"),
    ],
)
def test_overview_rejects_malformed_config_before_repository(field: str, value: object, error: str) -> None:
    query = _FakeWatchlistQuery()
    config_values: dict[str, Any] = {
        "window_days": 3,
        "overview_source_limit": 500,
        "overview_cluster_limit": 500,
    }
    config_values[field] = value
    service = WatchlistReadService(
        query=query,
        config=WatchlistReadConfig(**config_values),
    )

    with pytest.raises(ValueError, match=error):
        service.overview(
            handle="toly",
            configured_handles=("toly",),
            now_ms=1_700_000_000_000,
        )

    assert query.calls == []


class _FakeWatchlistQuery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def handles_overview(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("handles_overview", dict(kwargs)))
        return []

    def handle_overview(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("handle_overview", dict(kwargs)))
        return {"query": {}}
