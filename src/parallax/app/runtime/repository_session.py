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
    TokenProfileCurrentRepository,
)
from parallax.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery
from parallax.domains.asset_market.repositories.asset_profile_refresh_target_repository import (
    AssetProfileRefreshTargetRepository,
)
from parallax.domains.asset_market.repositories.market_tick_current_repository import (
    MarketTickCurrentRepository,
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
from parallax.domains.evidence.queries.watchlist_query import WatchlistQuery
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from parallax.domains.news_intel.repositories.news_item_repository import NewsItemRepository
from parallax.domains.news_intel.repositories.news_page_repository import NewsPageRepository
from parallax.domains.news_intel.repositories.news_projection_dirty_target_repository import (
    NewsProjectionDirtyTargetRepository,
)
from parallax.domains.news_intel.repositories.news_source_repository import NewsSourceRepository
from parallax.domains.news_intel.repositories.news_story_agent_repository import NewsStoryAgentRepository
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
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
from parallax.domains.token_intel.repositories.token_target_repository import TokenTargetRepository
from parallax.platform.db.postgres_client import (
    connect_postgres,
    require_transaction,
    transaction,
    with_password_from_file,
)


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
    enriched_events: EnrichedEventRepository
    event_anchor_jobs: EventAnchorBackfillJobRepository
    token_intent_lookup: TokenIntentLookupRepository
    event_tokens: EventTokenProjectionQuery
    token_radar_dirty_targets: TokenRadarDirtyTargetRepository
    token_radar_rank_sources: TokenRadarRankSourceRepository
    token_radar: TokenRadarRepository
    token_targets: TokenTargetRepository
    notifications: NotificationRepository
    watchlist: WatchlistQuery
    news_sources: NewsSourceRepository
    news_items: NewsItemRepository
    news_story_agents: NewsStoryAgentRepository
    news_pages: NewsPageRepository
    news_projection_dirty_targets: NewsProjectionDirtyTargetRepository
    macro_intel: MacroIntelRepository

    def transaction(self) -> AbstractContextManager[None]:
        return transaction(self.conn)

    def require_transaction(self, *, operation: str) -> None:
        require_transaction(self.conn, operation=operation)


def repositories_for_connection(
    conn: Any,
    *,
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
        enriched_events=EnrichedEventRepository(conn),
        event_anchor_jobs=EventAnchorBackfillJobRepository(conn),
        token_intent_lookup=TokenIntentLookupRepository(conn),
        event_tokens=EventTokenProjectionQuery(conn),
        token_radar_dirty_targets=TokenRadarDirtyTargetRepository(conn),
        token_radar_rank_sources=TokenRadarRankSourceRepository(conn),
        token_radar=TokenRadarRepository(conn),
        token_targets=TokenTargetRepository(conn),
        notifications=NotificationRepository(
            conn,
            running_timeout_ms=notification_delivery_running_timeout_ms,
            stale_running_terminalization_batch_size=notification_delivery_stale_running_terminalization_batch_size,
        ),
        watchlist=WatchlistQuery(conn),
        news_sources=NewsSourceRepository(conn),
        news_items=NewsItemRepository(conn),
        news_story_agents=NewsStoryAgentRepository(conn),
        news_pages=NewsPageRepository(conn),
        news_projection_dirty_targets=NewsProjectionDirtyTargetRepository(conn),
        macro_intel=MacroIntelRepository(conn),
    )


@contextmanager
def postgres_connection(settings: Any) -> Iterator[Any]:
    """Open the short-lived PostgreSQL connection used by application operations."""
    postgres = settings.storage.postgres
    dsn = with_password_from_file(postgres.dsn, settings.postgres_password_file)
    conn = connect_postgres(dsn, connect_timeout_seconds=postgres.connect_timeout_seconds)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def repositories(settings: Any) -> Iterator[RepositorySession]:
    """Open one short-lived repository session for a CLI/application operation."""
    with postgres_connection(settings) as conn:
        yield repositories_for_connection(
            conn,
            notification_delivery_running_timeout_ms=int(settings.workers.notification_delivery.running_timeout_ms),
            notification_delivery_stale_running_terminalization_batch_size=int(
                settings.workers.notification_delivery.stale_running_terminalization_batch_size
            ),
        )


@contextmanager
def repository_session(
    pool: Any,
    *,
    notification_delivery_running_timeout_ms: int,
    notification_delivery_stale_running_terminalization_batch_size: int,
) -> Iterator[RepositorySession]:
    with pool.connection() as conn:
        yield repositories_for_connection(
            conn,
            notification_delivery_running_timeout_ms=notification_delivery_running_timeout_ms,
            notification_delivery_stale_running_terminalization_batch_size=(
                notification_delivery_stale_running_terminalization_batch_size
            ),
        )
