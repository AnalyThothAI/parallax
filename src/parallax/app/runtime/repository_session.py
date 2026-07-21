from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

from parallax.domains.asset_market.interfaces import (
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
from parallax.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery
from parallax.domains.asset_market.repositories.asset_profile_refresh_target_repository import (
    AssetProfileRefreshTargetRepository,
)
from parallax.domains.asset_market.repositories.market_tick_current_dirty_target_repository import (
    MarketTickCurrentDirtyTargetRepository,
)
from parallax.domains.asset_market.repositories.market_tick_current_repository import (
    MarketTickCurrentRepository,
)
from parallax.domains.asset_market.repositories.token_capture_tier_dirty_target_repository import (
    TokenCaptureTierDirtyTargetRepository,
)
from parallax.domains.asset_market.repositories.token_image_asset_repository import (
    TokenImageAssetRepository,
)
from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    TokenImageSourceDirtyTargetRepository,
)
from parallax.domains.asset_market.repositories.token_profile_current_dirty_target_repository import (
    TokenProfileCurrentDirtyTargetRepository,
)
from parallax.domains.cex_market_intel.repositories.cex_detail_snapshot_repository import (
    CexDetailSnapshotRepository,
)
from parallax.domains.cex_market_intel.repositories.cex_oi_radar_repository import CexOiRadarRepository
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from parallax.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository import (
    NarrativeAdmissionDirtyTargetRepository,
)
from parallax.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from parallax.domains.news_intel.repositories.news_projection_dirty_target_repository import (
    NewsProjectionDirtyTargetRepository,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from parallax.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository
from parallax.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository
from parallax.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from parallax.domains.pulse_lab.repositories.pulse_evidence_repository import PulseEvidenceRepository
from parallax.domains.pulse_lab.repositories.pulse_evidence_source_repository import (
    PulseEvidenceSourceRepository,
)
from parallax.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from parallax.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository
from parallax.domains.pulse_lab.repositories.pulse_read_repository import PulseReadRepository
from parallax.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from parallax.domains.pulse_lab.repositories.pulse_trigger_dirty_target_repository import (
    PulseTriggerDirtyTargetRepository,
)
from parallax.domains.token_intel.interfaces import EventTokenProjectionQuery, SignalRepository
from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import (
    TokenIntentLookupRepository,
)
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
)
from parallax.domains.token_intel.repositories.token_radar_rank_source_repository import (
    TokenRadarRankSourceRepository,
)
from parallax.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from parallax.domains.token_intel.repositories.token_radar_source_dirty_event_repository import (
    TokenRadarSourceDirtyEventRepository,
)
from parallax.domains.token_intel.repositories.token_target_repository import TokenTargetRepository
from parallax.domains.watchlist_intel.repositories.watchlist_intel_repository import WatchlistIntelRepository
from parallax.platform.db.postgres_client import require_transaction, transaction


@dataclass(frozen=True, slots=True)
class RepositorySession:
    conn: Any
    evidence: EvidenceRepository
    entities: EntityRepository
    signals: SignalRepository
    asset_profiles: AssetProfileRepository
    asset_profile_refresh_targets: AssetProfileRefreshTargetRepository
    source_query: TokenProfileSourceQuery
    cex_token_profiles: CexTokenProfileRepository
    token_profiles: TokenProfileCurrentRepository
    token_profile_current_dirty_targets: TokenProfileCurrentDirtyTargetRepository
    token_image_assets: TokenImageAssetRepository
    token_image_source_dirty_targets: TokenImageSourceDirtyTargetRepository
    token_evidence: TokenEvidenceRepository
    token_intents: TokenIntentRepository
    intent_resolutions: IntentResolutionRepository
    registry: RegistryRepository
    identity_evidence: IdentityEvidenceRepository
    discovery: DiscoveryRepository
    market_ticks: MarketTickRepository
    market_tick_current: MarketTickCurrentRepository
    market_tick_current_dirty_targets: MarketTickCurrentDirtyTargetRepository
    enriched_events: EnrichedEventRepository
    event_anchor_jobs: EventAnchorBackfillJobRepository
    token_capture_tier_dirty_targets: TokenCaptureTierDirtyTargetRepository
    token_capture_tiers: TokenCaptureTierRepository
    token_intent_lookup: TokenIntentLookupRepository
    event_tokens: EventTokenProjectionQuery
    token_radar_dirty_targets: TokenRadarDirtyTargetRepository
    token_radar_source_dirty_events: TokenRadarSourceDirtyEventRepository
    token_radar_rank_sources: TokenRadarRankSourceRepository
    token_radar: TokenRadarRepository
    token_targets: TokenTargetRepository
    notifications: NotificationRepository
    pulse_jobs: PulseJobsRepository
    pulse_admission: PulseAdmissionRepository
    pulse_candidates: PulseCandidatesRepository
    pulse_evidence: PulseEvidenceRepository
    pulse_evidence_sources: PulseEvidenceSourceRepository
    pulse_runs: PulseRunsRepository
    pulse_trigger_dirty_targets: PulseTriggerDirtyTargetRepository
    pulse_agent_eval: PulseAgentEvalRepository
    pulse_read: PulseReadRepository
    pulse_playbooks: PulsePlaybooksRepository
    narratives: NarrativeRepository
    narrative_admission_dirty_targets: NarrativeAdmissionDirtyTargetRepository
    watchlist_intel: WatchlistIntelRepository
    news: NewsRepository
    news_projection_dirty_targets: NewsProjectionDirtyTargetRepository
    cex_detail_snapshots: CexDetailSnapshotRepository
    cex_oi_radar: CexOiRadarRepository
    macro_intel: MacroIntelRepository

    def unit_of_work(self) -> AbstractContextManager[None]:
        return transaction(self.conn)

    def transaction(self) -> AbstractContextManager[None]:
        return self.unit_of_work()

    def require_transaction(self, *, operation: str) -> None:
        require_transaction(self.conn, operation=operation)


def repositories_for_connection(
    conn: Any,
    *,
    pulse_job_running_timeout_ms: int,
    notification_delivery_running_timeout_ms: int,
    notification_delivery_stale_running_terminalization_batch_size: int,
) -> RepositorySession:
    return RepositorySession(
        conn=conn,
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        asset_profiles=AssetProfileRepository(conn),
        asset_profile_refresh_targets=AssetProfileRefreshTargetRepository(conn),
        source_query=TokenProfileSourceQuery(conn),
        cex_token_profiles=CexTokenProfileRepository(conn),
        token_profiles=TokenProfileCurrentRepository(conn),
        token_profile_current_dirty_targets=TokenProfileCurrentDirtyTargetRepository(conn),
        token_image_assets=TokenImageAssetRepository(conn),
        token_image_source_dirty_targets=TokenImageSourceDirtyTargetRepository(conn),
        token_evidence=TokenEvidenceRepository(conn),
        token_intents=TokenIntentRepository(conn),
        intent_resolutions=IntentResolutionRepository(conn),
        registry=RegistryRepository(conn),
        identity_evidence=IdentityEvidenceRepository(conn),
        discovery=DiscoveryRepository(conn),
        market_ticks=MarketTickRepository(conn),
        market_tick_current=MarketTickCurrentRepository(conn),
        market_tick_current_dirty_targets=MarketTickCurrentDirtyTargetRepository(conn),
        enriched_events=EnrichedEventRepository(conn),
        event_anchor_jobs=EventAnchorBackfillJobRepository(conn),
        token_capture_tier_dirty_targets=TokenCaptureTierDirtyTargetRepository(conn),
        token_capture_tiers=TokenCaptureTierRepository(conn),
        token_intent_lookup=TokenIntentLookupRepository(conn),
        event_tokens=EventTokenProjectionQuery(conn),
        token_radar_dirty_targets=TokenRadarDirtyTargetRepository(conn),
        token_radar_source_dirty_events=TokenRadarSourceDirtyEventRepository(conn),
        token_radar_rank_sources=TokenRadarRankSourceRepository(conn),
        token_radar=TokenRadarRepository(conn),
        token_targets=TokenTargetRepository(conn),
        notifications=NotificationRepository(
            conn,
            running_timeout_ms=notification_delivery_running_timeout_ms,
            stale_running_terminalization_batch_size=notification_delivery_stale_running_terminalization_batch_size,
        ),
        pulse_jobs=PulseJobsRepository(conn, running_timeout_ms=pulse_job_running_timeout_ms),
        pulse_admission=PulseAdmissionRepository(conn),
        pulse_candidates=PulseCandidatesRepository(conn),
        pulse_evidence=PulseEvidenceRepository(conn),
        pulse_evidence_sources=PulseEvidenceSourceRepository(conn),
        pulse_runs=PulseRunsRepository(conn),
        pulse_trigger_dirty_targets=PulseTriggerDirtyTargetRepository(conn),
        pulse_agent_eval=PulseAgentEvalRepository(conn),
        pulse_read=PulseReadRepository(conn),
        pulse_playbooks=PulsePlaybooksRepository(conn),
        narratives=NarrativeRepository(conn),
        narrative_admission_dirty_targets=NarrativeAdmissionDirtyTargetRepository(conn),
        watchlist_intel=WatchlistIntelRepository(conn),
        news=NewsRepository(conn),
        news_projection_dirty_targets=NewsProjectionDirtyTargetRepository(conn),
        cex_detail_snapshots=CexDetailSnapshotRepository(conn),
        cex_oi_radar=CexOiRadarRepository(conn),
        macro_intel=MacroIntelRepository(conn),
    )


@contextmanager
def repository_session(
    pool: Any,
    *,
    pulse_job_running_timeout_ms: int,
    notification_delivery_running_timeout_ms: int,
    notification_delivery_stale_running_terminalization_batch_size: int,
) -> Iterator[RepositorySession]:
    with pool.connection() as conn:
        yield repositories_for_connection(
            conn,
            pulse_job_running_timeout_ms=pulse_job_running_timeout_ms,
            notification_delivery_running_timeout_ms=notification_delivery_running_timeout_ms,
            notification_delivery_stale_running_terminalization_batch_size=(
                notification_delivery_stale_running_terminalization_batch_size
            ),
        )


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
