from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.domains.token_intel.queries.token_radar_rank_source_query import (
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
        def _write() -> int:
            return TokenRadarRankSourceQuery(self.conn).populate_edges_for_event_ids(
                requests,
                projected_at_ms=projected_at_ms,
            )

        return _run_repository_write(self.conn, commit, _write)

    def populate_edges_for_targets(
        self,
        targets: Sequence[Mapping[str, Any]],
        *,
        projected_at_ms: int,
        analysis_since_ms: int,
        commit: bool = True,
    ) -> int:
        def _write() -> int:
            return TokenRadarRankSourceQuery(self.conn).populate_edges_for_targets(
                targets,
                projected_at_ms=projected_at_ms,
                analysis_since_ms=analysis_since_ms,
            )

        return _run_repository_write(self.conn, commit, _write)

    def prune_edges(
        self,
        *,
        projection_version: str,
        event_received_before_ms: int,
        limit: int,
        commit: bool = True,
    ) -> int:
        def _write() -> int:
            return TokenRadarRankSourceQuery(self.conn).prune_edges(
                projection_version=projection_version,
                event_received_before_ms=event_received_before_ms,
                limit=limit,
            )

        return _run_repository_write(self.conn, commit, _write)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_radar_rank_source_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_radar_rank_source_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
