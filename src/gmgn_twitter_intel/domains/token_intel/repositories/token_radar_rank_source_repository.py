from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import (
    TokenRadarFeatureSourceRequest,
    TokenRadarRankSourceQuery,
    TokenRadarSourceEdgeRequest,
)


class TokenRadarRankSourceRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def load_rows_for_requests(
        self,
        requests: Sequence[TokenRadarFeatureSourceRequest],
    ) -> dict[str, list[dict[str, Any]]]:
        return TokenRadarRankSourceQuery(self.conn).load_rows_for_requests(requests)

    def latest_market_context_for_targets(
        self,
        targets: Sequence[Mapping[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        return TokenRadarRankSourceQuery(self.conn).latest_market_context_for_targets(targets)

    def affected_targets_for_event_ids(
        self,
        requests: Sequence[TokenRadarSourceEdgeRequest | str],
    ) -> list[dict[str, str]]:
        return TokenRadarRankSourceQuery(self.conn).affected_targets_for_event_ids(requests)

    def populate_edges_for_event_ids(
        self,
        requests: Sequence[TokenRadarSourceEdgeRequest | str],
        *,
        projected_at_ms: int,
        commit: bool = True,
    ) -> int:
        return TokenRadarRankSourceQuery(self.conn).populate_edges_for_event_ids(
            requests,
            projected_at_ms=projected_at_ms,
            commit=commit,
        )

    def populate_edges_for_targets(
        self,
        targets: Sequence[Mapping[str, Any]],
        *,
        projected_at_ms: int,
        commit: bool = True,
    ) -> int:
        return TokenRadarRankSourceQuery(self.conn).populate_edges_for_targets(
            targets,
            projected_at_ms=projected_at_ms,
            commit=commit,
        )

    def prune_edges(
        self,
        *,
        projection_version: str,
        event_received_before_ms: int,
        commit: bool = True,
    ) -> int:
        return TokenRadarRankSourceQuery(self.conn).prune_edges(
            projection_version=projection_version,
            event_received_before_ms=event_received_before_ms,
            commit=commit,
        )
