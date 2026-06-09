from __future__ import annotations

import pytest

from parallax.platform.agent_knowledge import agent_knowledge_catalog, render_agent_instructions


def test_agent_knowledge_catalog_loads_lightweight_index_before_body() -> None:
    catalog = agent_knowledge_catalog()
    index = catalog.index()

    assert "market_research_harness" in index
    assert index["market_research_harness"]["title"] == "Market Research Harness"
    assert "body" not in index["market_research_harness"]
    assert "PostgreSQL facts and read models are the only product truth" in catalog.load(
        "market_research_harness"
    )


def test_render_agent_instructions_loads_requested_knowledge_only() -> None:
    rendered = render_agent_instructions(
        "Base prompt.",
        knowledge_refs=("market_research_harness",),
    )

    assert rendered.startswith("Base prompt.")
    assert "## Loaded Knowledge: Market Research Harness" in rendered
    assert "Do not use tools to write product state" in rendered


def test_unknown_agent_knowledge_ref_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown agent knowledge ref"):
        render_agent_instructions("Base prompt.", knowledge_refs=("missing_ref",))
