from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel._constants import NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION


@dataclass(frozen=True, slots=True)
class NewsResearchToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler_name: str
    source_tables: list[str]
    max_rows: int
    max_chars: int
    query_version: str
    supports_confirmation: bool
    supports_source_health: bool
    requires_allowed_context_target: bool
    result_basis_values: list[str]
    concurrency_safe: bool
    tool_catalog_version: str = NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION


def build_news_research_tool_registry() -> dict[str, NewsResearchToolDefinition]:
    return {
        "get_fact_context": NewsResearchToolDefinition(
            name="get_fact_context",
            description="Fetch bounded local fact-candidate context for the current news item.",
            input_schema={
                "type": "object",
                "properties": {
                    "include_rejected": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
            handler_name="get_fact_context",
            source_tables=["news_fact_candidates", "news_items"],
            max_rows=20,
            max_chars=1_200,
            query_version="get_fact_context_v1",
            supports_confirmation=True,
            supports_source_health=False,
            requires_allowed_context_target=False,
            result_basis_values=["fact_candidate", "validation_status", "affected_target"],
            concurrency_safe=True,
        ),
        "get_observation_history": NewsResearchToolDefinition(
            name="get_observation_history",
            description="Fetch bounded local observation history for similar item-level evidence.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "additionalProperties": False,
            },
            handler_name="get_news_observation_history",
            source_tables=["news_items", "news_item_observation_edges", "news_sources"],
            max_rows=25,
            max_chars=1_400,
            query_version="get_observation_history_v1",
            supports_confirmation=True,
            supports_source_health=False,
            requires_allowed_context_target=False,
            result_basis_values=["same_source", "same_content_class", "observation_history"],
            concurrency_safe=True,
        ),
        "get_source_quality": NewsResearchToolDefinition(
            name="get_source_quality",
            description="Fetch local source authority and health context for the news item's source.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler_name="get_source_quality_context_for_item",
            source_tables=["news_sources", "news_source_quality_rows"],
            max_rows=8,
            max_chars=900,
            query_version="get_source_quality_v1",
            supports_confirmation=False,
            supports_source_health=True,
            requires_allowed_context_target=False,
            result_basis_values=["source_quality", "source_health", "trust_tier"],
            concurrency_safe=True,
        ),
        "get_target_news_context": NewsResearchToolDefinition(
            name="get_target_news_context",
            description="Fetch bounded local news context for allow-listed market targets.",
            input_schema={
                "type": "object",
                "properties": {
                    "target_refs": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_type": {"type": "string"},
                                "target_id": {"type": "string"},
                            },
                            "required": ["target_type", "target_id"],
                            "additionalProperties": False,
                        },
                    },
                    "symbol_fallbacks": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
                    "window_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "additionalProperties": False,
            },
            handler_name="get_target_news_context",
            source_tables=["news_items", "news_token_mentions", "news_page_rows", "news_item_agent_briefs"],
            max_rows=12,
            max_chars=1_600,
            query_version="get_target_news_context_v1",
            supports_confirmation=True,
            supports_source_health=False,
            requires_allowed_context_target=True,
            result_basis_values=[
                "exact_target",
                "known_symbol",
                "symbol_heuristic",
                "market_subject_heuristic",
            ],
            concurrency_safe=True,
        ),
        "search_news_archive": NewsResearchToolDefinition(
            name="search_news_archive",
            description="Search bounded local news archive context by terms and symbols.",
            input_schema={
                "type": "object",
                "properties": {
                    "query_terms": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                    "symbols": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                    "match_modes": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {"type": "string", "enum": ["title", "token", "fact", "source_title"]},
                    },
                    "window_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "additionalProperties": False,
            },
            handler_name="search_news_archive",
            source_tables=[
                "news_items",
                "news_token_mentions",
                "news_sources",
                "news_page_rows",
                "news_item_agent_briefs",
            ],
            max_rows=8,
            max_chars=1_600,
            query_version="search_news_archive_v1",
            supports_confirmation=True,
            supports_source_health=False,
            requires_allowed_context_target=False,
            result_basis_values=["similar_news", "term_match", "symbol_match"],
            concurrency_safe=True,
        ),
    }


__all__ = ["NewsResearchToolDefinition", "build_news_research_tool_registry"]
