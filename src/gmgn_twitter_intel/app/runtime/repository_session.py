from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import (
    AssetProfileRepository,
    CexTokenProfileRepository,
    DiscoveryRepository,
    EnrichedEventRepository,
    EventAnchorBackfillJobRepository,
    IdentityEvidenceRepository,
    MarketTickRepository,
    RegistryRepository,
    TokenCaptureTierRepository,
    TokenProfileCurrentRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.token_image_asset_repository import (
    TokenImageAssetRepository,
)
from gmgn_twitter_intel.domains.cex_market_intel.repositories.cex_derivative_series_repository import (
    CexDerivativeSeriesRepository,
)
from gmgn_twitter_intel.domains.cex_market_intel.repositories.cex_detail_snapshot_repository import (
    CexDetailSnapshotRepository,
)
from gmgn_twitter_intel.domains.cex_market_intel.repositories.cex_oi_radar_repository import CexOiRadarRepository
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_evidence_repository import PulseEvidenceRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_evidence_source_repository import (
    PulseEvidenceSourceRepository,
)
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_read_repository import PulseReadRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.domains.social_enrichment.repositories.social_event_extraction_repository import (
    SocialEventExtractionRepository,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import EventTokenProjectionQuery, SignalRepository
from gmgn_twitter_intel.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_factor_evaluation_repository import (
    TokenFactorEvaluationRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_intent_lookup_repository import (
    TokenIntentLookupRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
)
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
    cex_token_profiles: CexTokenProfileRepository
    token_profiles: TokenProfileCurrentRepository
    token_image_assets: TokenImageAssetRepository
    token_evidence: TokenEvidenceRepository
    token_intents: TokenIntentRepository
    intent_resolutions: IntentResolutionRepository
    registry: RegistryRepository
    identity_evidence: IdentityEvidenceRepository
    discovery: DiscoveryRepository
    market_ticks: MarketTickRepository
    enriched_events: EnrichedEventRepository
    event_anchor_jobs: EventAnchorBackfillJobRepository
    token_capture_tiers: TokenCaptureTierRepository
    token_intent_lookup: TokenIntentLookupRepository
    event_tokens: EventTokenProjectionQuery
    token_radar_dirty_targets: TokenRadarDirtyTargetRepository
    token_radar: TokenRadarRepository
    token_factor_evaluations: TokenFactorEvaluationRepository
    token_targets: TokenTargetRepository
    enrichment: EnrichmentRepository
    social_event_extractions: SocialEventExtractionRepository
    notifications: NotificationRepository
    pulse_jobs: PulseJobsRepository
    pulse_admission: PulseAdmissionRepository
    pulse_candidates: PulseCandidatesRepository
    pulse_evidence: PulseEvidenceRepository
    pulse_evidence_sources: PulseEvidenceSourceRepository
    pulse_runs: PulseRunsRepository
    pulse_agent_eval: PulseAgentEvalRepository
    pulse_read: PulseReadRepository
    pulse_playbooks: PulsePlaybooksRepository
    narratives: NarrativeRepository
    watchlist_intel: WatchlistIntelRepository
    news: NewsRepository
    equity_events: EquityEventRepository
    cex_derivative_series: CexDerivativeSeriesRepository
    cex_detail_snapshots: CexDetailSnapshotRepository
    cex_oi_radar: CexOiRadarRepository
    macro_intel: MacroIntelRepository

    def unit_of_work(self):
        return transaction(self.conn)


def repositories_for_connection(conn: Any) -> RepositorySession:
    return RepositorySession(
        conn=conn,
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        asset_profiles=AssetProfileRepository(conn),
        cex_token_profiles=CexTokenProfileRepository(conn),
        token_profiles=TokenProfileCurrentRepository(conn),
        token_image_assets=TokenImageAssetRepository(conn),
        token_evidence=TokenEvidenceRepository(conn),
        token_intents=TokenIntentRepository(conn),
        intent_resolutions=IntentResolutionRepository(conn),
        registry=RegistryRepository(conn),
        identity_evidence=IdentityEvidenceRepository(conn),
        discovery=DiscoveryRepository(conn),
        market_ticks=MarketTickRepository(conn),
        enriched_events=EnrichedEventRepository(conn),
        event_anchor_jobs=EventAnchorBackfillJobRepository(conn),
        token_capture_tiers=TokenCaptureTierRepository(conn),
        token_intent_lookup=TokenIntentLookupRepository(conn),
        event_tokens=EventTokenProjectionQuery(conn),
        token_radar_dirty_targets=TokenRadarDirtyTargetRepository(conn),
        token_radar=TokenRadarRepository(conn),
        token_factor_evaluations=TokenFactorEvaluationRepository(conn),
        token_targets=TokenTargetRepository(conn),
        enrichment=EnrichmentRepository(conn),
        social_event_extractions=SocialEventExtractionRepository(conn),
        notifications=NotificationRepository(conn),
        pulse_jobs=PulseJobsRepository(conn),
        pulse_admission=PulseAdmissionRepository(conn),
        pulse_candidates=PulseCandidatesRepository(conn),
        pulse_evidence=PulseEvidenceRepository(conn),
        pulse_evidence_sources=PulseEvidenceSourceRepository(conn),
        pulse_runs=PulseRunsRepository(conn),
        pulse_agent_eval=PulseAgentEvalRepository(conn),
        pulse_read=PulseReadRepository(conn),
        pulse_playbooks=PulsePlaybooksRepository(conn),
        narratives=NarrativeRepository(conn),
        watchlist_intel=WatchlistIntelRepository(conn),
        news=NewsRepository(conn),
        equity_events=EquityEventRepository(conn),
        cex_derivative_series=CexDerivativeSeriesRepository(conn),
        cex_detail_snapshots=CexDetailSnapshotRepository(conn),
        cex_oi_radar=CexOiRadarRepository(conn),
        macro_intel=MacroIntelRepository(conn),
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
