from __future__ import annotations

RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES = ("atom", "cryptopanic", "json_feed", "opennews", "rss")
OPENNEWS_FETCH_POLICY_KEYS = frozenset(
    {
        "coins",
        "engineTypes",
        "hasCoin",
        "max_catchup_age_ms",
        "max_initial_fetch_age_ms",
        "max_rest_pages",
        "q",
        "rest_limit",
        "rest_overlap_ms",
        "score",
    }
)

__all__ = ["OPENNEWS_FETCH_POLICY_KEYS", "RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES"]
