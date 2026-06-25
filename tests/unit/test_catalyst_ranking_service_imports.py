"""Regression: CatalystRankingService should import the live post-quality scorer."""

from __future__ import annotations

import pytest

from parallax.domains.token_intel.read_models.catalyst_ranking_service import CatalystRankingService


def test_catalyst_ranking_service_imports_cleanly() -> None:
    from parallax.domains.token_intel.read_models import catalyst_ranking_service

    assert hasattr(catalyst_ranking_service, "CatalystRankingService")
    assert callable(catalyst_ranking_service.post_quality_score)


def test_catalyst_ranking_allows_zero_limit_as_empty_result() -> None:
    rows = CatalystRankingService().rank(
        candidates=[{"event_id": "event-1", "received_at_ms": 1, "author_handle": "alice"}],
        pool=[],
        limit=0,
    )

    assert rows == []


@pytest.mark.parametrize("limit", [-1, True, "1"])
def test_catalyst_ranking_rejects_malformed_limit_before_scoring(limit: object) -> None:
    with pytest.raises(ValueError, match="catalyst_ranking_limit_required"):
        CatalystRankingService().rank(
            candidates=[{"event_id": "event-1", "received_at_ms": 1, "author_handle": "alice"}],
            pool=[],
            limit=limit,  # type: ignore[arg-type]
        )
