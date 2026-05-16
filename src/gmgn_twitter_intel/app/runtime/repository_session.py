from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import (
    AssetProfileRepository,
    DiscoveryRepository,
    EnrichedEventRepository,
    IdentityEvidenceRepository,
    MarketTickRepository,
    RegistryRepository,
    TokenCaptureTierRepository,
)
from gmgn_twitter_intel.domains.closed_loop_harness.repositories.harness_repository import HarnessRepository
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_repository import PulseRepository
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import EventTokenProjectionQuery, SignalRepository
from gmgn_twitter_intel.domains.token_intel.repositories.asset_signal_repository import AssetSignalRepository
from gmgn_twitter_intel.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_factor_evaluation_repository import (
    TokenFactorEvaluationRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_intent_lookup_repository import (
    TokenIntentLookupRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_target_repository import TokenTargetRepository
from gmgn_twitter_intel.domains.watchlist_intel.repositories.watchlist_intel_repository import WatchlistIntelRepository
from gmgn_twitter_intel.platform.db.postgres_client import transaction


@dataclass(frozen=True, slots=True)
class RepositorySession:
    conn: Any
    evidence: EvidenceRepository
    entities: EntityRepository
    signals: SignalRepository
    asset_profiles: AssetProfileRepository
    token_evidence: TokenEvidenceRepository
    token_intents: TokenIntentRepository
    intent_resolutions: IntentResolutionRepository
    registry: RegistryRepository
    identity_evidence: IdentityEvidenceRepository
    discovery: DiscoveryRepository
    market_ticks: MarketTickRepository
    enriched_events: EnrichedEventRepository
    token_capture_tiers: TokenCaptureTierRepository
    token_intent_lookup: TokenIntentLookupRepository
    event_tokens: EventTokenProjectionQuery
    token_radar: TokenRadarRepository
    token_factor_evaluations: TokenFactorEvaluationRepository
    token_targets: TokenTargetRepository
    asset_signals: AssetSignalRepository
    enrichment: EnrichmentRepository
    harness: HarnessRepository
    notifications: NotificationRepository
    pulse: PulseRepository
    watchlist_intel: WatchlistIntelRepository

    def unit_of_work(self):
        return transaction(self.conn)


def repositories_for_connection(conn: Any) -> RepositorySession:
    return RepositorySession(
        conn=conn,
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        asset_profiles=AssetProfileRepository(conn),
        token_evidence=TokenEvidenceRepository(conn),
        token_intents=TokenIntentRepository(conn),
        intent_resolutions=IntentResolutionRepository(conn),
        registry=RegistryRepository(conn),
        identity_evidence=IdentityEvidenceRepository(conn),
        discovery=DiscoveryRepository(conn),
        market_ticks=MarketTickRepository(conn),
        enriched_events=EnrichedEventRepository(conn),
        token_capture_tiers=TokenCaptureTierRepository(conn),
        token_intent_lookup=TokenIntentLookupRepository(conn),
        event_tokens=EventTokenProjectionQuery(conn),
        token_radar=TokenRadarRepository(conn),
        token_factor_evaluations=TokenFactorEvaluationRepository(conn),
        token_targets=TokenTargetRepository(conn),
        asset_signals=AssetSignalRepository(conn),
        enrichment=EnrichmentRepository(conn),
        harness=HarnessRepository(conn),
        notifications=NotificationRepository(conn),
        pulse=PulseRepository(conn),
        watchlist_intel=WatchlistIntelRepository(conn),
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
