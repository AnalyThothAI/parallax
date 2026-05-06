from __future__ import annotations

from ..storage.asset_repository import AssetRepository
from .asset_resolver import AssetResolutionDecision


def persist_asset_decision(
    repo: AssetRepository,
    decision: AssetResolutionDecision,
    *,
    decision_time_ms: int,
    created_at_ms: int | None = None,
    commit: bool = True,
) -> dict:
    return repo.insert_attribution(
        event_id=decision.event_id,
        mention_id=decision.mention_id,
        asset_id=decision.asset_id,
        venue_id=decision.venue_id,
        attribution_status=decision.attribution_status,
        attribution_weight=decision.attribution_weight,
        confidence=decision.confidence,
        identity_status=decision.identity_status,
        reasons=decision.reasons,
        risks=decision.risks,
        decision_time_ms=decision_time_ms,
        created_at_ms=created_at_ms if created_at_ms is not None else decision_time_ms,
        commit=commit,
    )


def persist_asset_decisions(
    repo: AssetRepository,
    decisions: list[AssetResolutionDecision],
    *,
    decision_time_ms: int,
    created_at_ms: int | None = None,
    commit: bool = True,
) -> list[dict]:
    rows = [
        persist_asset_decision(
            repo,
            decision,
            decision_time_ms=decision_time_ms,
            created_at_ms=created_at_ms,
            commit=False,
        )
        for decision in decisions
    ]
    if commit:
        repo.conn.commit()
    return rows
