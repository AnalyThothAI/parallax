from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .asset_repository import AssetRepository
from .asset_signal_repository import AssetSignalRepository
from .discovery_repository import DiscoveryRepository
from .enrichment_repository import EnrichmentRepository
from .entity_repository import EntityRepository
from .evidence_repository import EvidenceRepository
from .harness_repository import HarnessRepository
from .intent_resolution_repository import IntentResolutionRepository
from .market_repository import MarketRepository
from .notification_repository import NotificationRepository
from .price_observation_repository import PriceObservationRepository
from .pulse_repository import PulseRepository
from .registry_repository import RegistryRepository
from .signal_repository import SignalRepository
from .token_evidence_repository import TokenEvidenceRepository
from .token_intent_lookup_repository import TokenIntentLookupRepository
from .token_intent_repository import TokenIntentRepository
from .token_radar_repository import TokenRadarRepository
from .token_target_repository import TokenTargetRepository


@dataclass(frozen=True, slots=True)
class RepositorySession:
    conn: Any
    evidence: EvidenceRepository
    entities: EntityRepository
    signals: SignalRepository
    assets: AssetRepository
    token_evidence: TokenEvidenceRepository
    token_intents: TokenIntentRepository
    intent_resolutions: IntentResolutionRepository
    registry: RegistryRepository
    discovery: DiscoveryRepository
    price_observations: PriceObservationRepository
    token_intent_lookup: TokenIntentLookupRepository
    market: MarketRepository
    token_radar: TokenRadarRepository
    token_targets: TokenTargetRepository
    asset_signals: AssetSignalRepository
    enrichment: EnrichmentRepository
    harness: HarnessRepository
    notifications: NotificationRepository
    pulse: PulseRepository


def repositories_for_connection(conn: Any) -> RepositorySession:
    return RepositorySession(
        conn=conn,
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        assets=AssetRepository(conn),
        token_evidence=TokenEvidenceRepository(conn),
        token_intents=TokenIntentRepository(conn),
        intent_resolutions=IntentResolutionRepository(conn),
        registry=RegistryRepository(conn),
        discovery=DiscoveryRepository(conn),
        price_observations=PriceObservationRepository(conn),
        token_intent_lookup=TokenIntentLookupRepository(conn),
        market=MarketRepository(conn),
        token_radar=TokenRadarRepository(conn),
        token_targets=TokenTargetRepository(conn),
        asset_signals=AssetSignalRepository(conn),
        enrichment=EnrichmentRepository(conn),
        harness=HarnessRepository(conn),
        notifications=NotificationRepository(conn),
        pulse=PulseRepository(conn),
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
