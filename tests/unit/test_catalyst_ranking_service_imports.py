"""Regression: CatalystRankingService should import the live post-quality scorer."""

from __future__ import annotations


def test_catalyst_ranking_service_imports_cleanly() -> None:
    from parallax.domains.token_intel.read_models import catalyst_ranking_service

    assert hasattr(catalyst_ranking_service, "CatalystRankingService")
    assert callable(catalyst_ranking_service.post_quality_score)
