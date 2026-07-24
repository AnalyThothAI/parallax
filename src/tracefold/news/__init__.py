"""Public news capability interface."""

from .ingest.feed_item_normalizer import normalize_feed_entry
from .ingest.item_repository import NewsItemRepository
from .ingest.news_provider_contract import (
    NewsProviderContractError,
    configured_news_provider_types,
    validate_news_provider_contract,
)
from .ingest.opennews_provider_signal import (
    provider_signal_from_opennews_payload,
    provider_token_impacts_from_opennews_payload,
)
from .ingest.provider_models import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from .ingest.source_repository import NewsSourceRepository
from .operations import PROJECTION_CHOICES, enqueue_projection_dirty_targets
from .projection.dirty_target_repository import NewsProjectionDirtyTargetRepository
from .projection.repository import NewsPageRepository
from .provider_contracts import NewsSourceProvider, NewsSourceProviderError
from .views.page_query import NewsPageQuery
from .views.research_evidence import (
    NewsResearchCatalog,
    NewsResearchEvidence,
    NewsResearchEvidenceReader,
)
from .workers import construct_news_workers

__all__ = [
    "PROJECTION_CHOICES",
    "NewsItemRepository",
    "NewsPageQuery",
    "NewsPageRepository",
    "NewsProjectionDirtyTargetRepository",
    "NewsProviderContractError",
    "NewsProviderFetchResult",
    "NewsProviderObservation",
    "NewsResearchCatalog",
    "NewsResearchEvidence",
    "NewsResearchEvidenceReader",
    "NewsSourceHttpCache",
    "NewsSourceProvider",
    "NewsSourceProviderError",
    "NewsSourceRepository",
    "NewsSourceSnapshot",
    "configured_news_provider_types",
    "construct_news_workers",
    "enqueue_projection_dirty_targets",
    "normalize_feed_entry",
    "provider_signal_from_opennews_payload",
    "provider_token_impacts_from_opennews_payload",
    "validate_news_provider_contract",
]
