from __future__ import annotations

import pytest

from parallax.platform.agent_read_tools import (
    AgentReadToolRegistry,
    ReadOnlySqlAgentTool,
    build_default_agent_read_tool_registry,
)


def test_default_agent_read_tool_registry_exposes_only_read_models() -> None:
    registry = build_default_agent_read_tool_registry()
    manifest = registry.manifest()

    assert set(manifest) == {
        "news.current_briefs",
        "pulse.current_candidates",
        "token_radar.current_rows",
    }
    assert all(entry["read_only"] is True for entry in manifest.values())
    assert manifest["token_radar.current_rows"]["source_tables"] == ("token_radar_current_rows",)
    assert manifest["news.current_briefs"]["source_tables"] == ("news_item_agent_briefs",)
    assert manifest["pulse.current_candidates"]["source_tables"] == ("pulse_candidates",)


def test_agent_read_tool_registry_rejects_mutating_sql() -> None:
    with pytest.raises(ValueError, match="read-only SELECT"):
        ReadOnlySqlAgentTool(
            name="bad.delete",
            description="Bad writer.",
            sql="DELETE FROM token_radar_current_rows WHERE true",
            source_tables=("token_radar_current_rows",),
        )


def test_agent_read_tool_registry_rejects_writable_tools() -> None:
    registry = AgentReadToolRegistry()

    with pytest.raises(ValueError, match="read_only"):
        registry.register(
            ReadOnlySqlAgentTool(
                name="bad.writable",
                description="Bad writable flag.",
                sql="SELECT * FROM token_radar_current_rows",
                source_tables=("token_radar_current_rows",),
                read_only=False,
            )
        )


def test_agent_read_tool_manifest_is_serializable_and_hides_sql() -> None:
    registry = build_default_agent_read_tool_registry()

    entry = registry.manifest()["token_radar.current_rows"]

    assert "sql" not in entry
    assert entry["name"] == "token_radar.current_rows"
    assert entry["parameters_schema"]["type"] == "object"
