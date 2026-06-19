from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_READ_ONLY_SQL_RE = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(?:SELECT|WITH)\b", re.IGNORECASE)
_MUTATING_SQL_RE = re.compile(
    r"\b(?:ALTER|CALL|COPY|CREATE|DELETE|DROP|EXECUTE|GRANT|INSERT|MERGE|REVOKE|TRUNCATE|UPDATE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ReadOnlySqlAgentTool:
    name: str
    description: str
    sql: str
    source_tables: tuple[str, ...]
    parameters_schema: Mapping[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    read_only: bool = True

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or "." not in name:
            raise ValueError("agent read tool name must be a namespaced identifier")
        if not self.description.strip():
            raise ValueError("agent read tool description is required")
        if not self.source_tables:
            raise ValueError("agent read tool source_tables must not be empty")
        if not self.read_only:
            return
        _validate_read_only_sql(self.sql)

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "source_tables": self.source_tables,
            "parameters_schema": dict(self.parameters_schema),
        }


class AgentReadToolRegistry:
    def __init__(self, tools: tuple[ReadOnlySqlAgentTool, ...] = ()) -> None:
        self._tools: dict[str, ReadOnlySqlAgentTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ReadOnlySqlAgentTool) -> None:
        if not tool.read_only:
            raise ValueError(f"agent read tool must be read_only: {tool.name}")
        if tool.name in self._tools:
            raise ValueError(f"duplicate agent read tool: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ReadOnlySqlAgentTool:
        try:
            return self._tools[str(name)]
        except KeyError as exc:
            raise KeyError(f"unknown agent read tool: {name}") from exc

    def manifest(self) -> dict[str, dict[str, Any]]:
        return {name: tool.manifest_entry() for name, tool in sorted(self._tools.items())}


def build_default_agent_read_tool_registry() -> AgentReadToolRegistry:
    return AgentReadToolRegistry(
        (
            ReadOnlySqlAgentTool(
                name="token_radar.current_rows",
                description="Read current Token Radar rows for bounded operator research.",
                source_tables=("token_radar_current_rows",),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "window": {"type": "string"},
                        "scope": {"type": "string"},
                        "venue": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "additionalProperties": False,
                },
                sql="""
                    SELECT window, scope, venue, target_type, target_id, rank, rank_score, computed_at_ms
                    FROM token_radar_current_rows
                    WHERE (%(window)s IS NULL OR window = %(window)s)
                      AND (%(scope)s IS NULL OR scope = %(scope)s)
                      AND (%(venue)s IS NULL OR venue = %(venue)s)
                    ORDER BY rank ASC
                    LIMIT %(limit)s
                """,
            ),
            ReadOnlySqlAgentTool(
                name="news.story_current_briefs",
                description="Read current News story agent briefs for bounded research context.",
                source_tables=("news_story_agent_briefs",),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "story_key": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "additionalProperties": False,
                },
                sql="""
                    SELECT story_brief_key,
                           story_key,
                           representative_news_item_id,
                           status,
                           direction,
                           decision_class,
                           brief_json ->> 'title_zh' AS title_zh,
                           brief_json ->> 'summary_zh' AS summary_zh,
                           brief_json ->> 'market_read_zh' AS market_read_zh,
                           computed_at_ms
                    FROM news_story_agent_briefs
                    WHERE (%(status)s IS NULL OR status = %(status)s)
                      AND (%(story_key)s IS NULL OR story_key = %(story_key)s)
                    ORDER BY computed_at_ms DESC
                    LIMIT %(limit)s
                """,
            ),
            ReadOnlySqlAgentTool(
                name="pulse.current_candidates",
                description="Read current Pulse candidates for bounded research context.",
                source_tables=("pulse_candidates",),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "additionalProperties": False,
                },
                sql="""
                    SELECT candidate_id, subject_key, status, confidence, updated_at_ms
                    FROM pulse_candidates
                    WHERE (%(status)s IS NULL OR status = %(status)s)
                    ORDER BY updated_at_ms DESC
                    LIMIT %(limit)s
                """,
            ),
        )
    )


def _validate_read_only_sql(sql: str) -> None:
    stripped = str(sql or "").strip()
    if not _READ_ONLY_SQL_RE.search(stripped) or _MUTATING_SQL_RE.search(stripped):
        raise ValueError("agent read tools must use a single read-only SELECT or WITH query")
    if ";" in stripped.rstrip(";"):
        raise ValueError("agent read tools must not contain multiple SQL statements")


__all__ = [
    "AgentReadToolRegistry",
    "ReadOnlySqlAgentTool",
    "build_default_agent_read_tool_registry",
]
