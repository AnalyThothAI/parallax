from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.token_intel.queries.token_radar_rank_source_query import (
    TokenRadarFeatureSourceRequest,
    TokenRadarRankSourceQuery,
)
from parallax.platform.db.postgres_client import require_transaction


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

    def populate_edges_for_targets(
        self,
        targets: Sequence[Mapping[str, Any]],
        *,
        projected_at_ms: int,
        analysis_since_ms: int,
    ) -> int:
        require_transaction(self.conn, operation="populate_token_radar_rank_source_edges")
        return TokenRadarRankSourceQuery(self.conn).populate_edges_for_targets(
            targets,
            projected_at_ms=projected_at_ms,
            analysis_since_ms=analysis_since_ms,
        )

    def prune_edges(
        self,
        *,
        projection_version: str,
        event_received_before_ms: int,
        limit: int,
    ) -> int:
        require_transaction(self.conn, operation="prune_token_radar_rank_source_edges")
        return TokenRadarRankSourceQuery(self.conn).prune_edges(
            projection_version=projection_version,
            event_received_before_ms=event_received_before_ms,
            limit=limit,
        )
