from __future__ import annotations

from parallax.domains.news_intel._constants import NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION
from parallax.domains.news_intel.services.news_item_research_tools import build_news_research_tool_registry


def test_registry_exposes_only_five_p0_tools() -> None:
    registry = build_news_research_tool_registry()

    assert list(registry) == [
        "get_fact_context",
        "get_observation_history",
        "get_source_quality",
        "get_target_news_context",
        "search_news_archive",
    ]


def test_registry_definitions_have_explicit_metadata() -> None:
    registry = build_news_research_tool_registry()

    for name, tool in registry.items():
        assert tool.name == name
        assert tool.description
        assert tool.input_schema["type"] == "object"
        assert tool.handler_name
        assert tool.source_tables
        assert tool.max_rows > 0
        assert tool.max_chars > 0
        assert tool.query_version.endswith("_v1")
        assert tool.tool_catalog_version == NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION
        assert isinstance(tool.supports_confirmation, bool)
        assert isinstance(tool.supports_source_health, bool)
        assert isinstance(tool.requires_allowed_context_target, bool)
        assert tool.result_basis_values
        assert tool.concurrency_safe is True


def test_registry_semantic_capability_metadata_is_explicit() -> None:
    registry = build_news_research_tool_registry()

    assert registry["get_source_quality"].supports_confirmation is False
    assert registry["get_source_quality"].supports_source_health is True
    assert registry["get_target_news_context"].requires_allowed_context_target is True
    assert {
        "symbol_heuristic",
        "market_subject_heuristic",
    }.issubset(set(registry["get_target_news_context"].result_basis_values))
