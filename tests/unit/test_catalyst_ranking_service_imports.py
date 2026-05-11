"""Regression: catalyst_ranking_service had a broken `from .discussion_quality_scoring`
import (that module lives under `domains/token_intel/scoring/`, not the read_models
package). The bug was latent because nothing imports CatalystRankingService at runtime;
mypy strict surfaced it during the P3 typing pass. Lock in the corrected import path
so any future move of `discussion_quality_scoring` doesn't silently re-break it.
"""

from __future__ import annotations


def test_catalyst_ranking_service_imports_cleanly() -> None:
    from gmgn_twitter_intel.domains.token_intel.read_models import catalyst_ranking_service

    assert hasattr(catalyst_ranking_service, "CatalystRankingService")
    assert callable(catalyst_ranking_service.post_quality_score)
