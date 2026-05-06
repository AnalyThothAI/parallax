from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .enrichment_repository import EnrichmentRepository
from .entity_repository import EntityRepository
from .evidence_repository import EvidenceRepository
from .harness_repository import HarnessRepository
from .market_observation_repository import MarketObservationRepository
from .notification_repository import NotificationRepository
from .signal_repository import SignalRepository
from .token_repository import TokenRepository
from .token_signal_repository import TokenSignalRepository


@dataclass(frozen=True, slots=True)
class RepositorySession:
    conn: Any
    evidence: EvidenceRepository
    entities: EntityRepository
    signals: SignalRepository
    tokens: TokenRepository
    market_observations: MarketObservationRepository
    enrichment: EnrichmentRepository
    harness: HarnessRepository
    notifications: NotificationRepository
    token_signals: TokenSignalRepository


def repositories_for_connection(conn: Any) -> RepositorySession:
    return RepositorySession(
        conn=conn,
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        tokens=TokenRepository(conn),
        market_observations=MarketObservationRepository(conn),
        enrichment=EnrichmentRepository(conn),
        harness=HarnessRepository(conn),
        notifications=NotificationRepository(conn),
        token_signals=TokenSignalRepository(conn),
    )


@contextmanager
def repository_session(pool: Any) -> Iterator[RepositorySession]:
    with pool.connection() as conn:
        yield repositories_for_connection(conn)


class PooledRepository:
    def __init__(self, pool: Any, repository_type: type, *args: Any, **kwargs: Any):
        self._pool = pool
        self._repository_type = repository_type
        self._args = args
        self._kwargs = kwargs

    def __getattr__(self, name: str):
        if name == "conn":
            raise AttributeError("pooled repositories do not expose a pinned connection")

        def method(*args: Any, **kwargs: Any):
            with self._pool.connection() as conn:
                repository = self._repository_type(conn, *self._args, **self._kwargs)
                return getattr(repository, name)(*args, **kwargs)

        return method
