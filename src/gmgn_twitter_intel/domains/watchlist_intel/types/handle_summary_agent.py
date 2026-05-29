from __future__ import annotations

from pydantic import BaseModel, Field

BACKEND = "litellm_sdk"
WORKFLOW_NAME = "gmgn-twitter-intel.watchlist_handle_summary"
AGENT_NAME = "WatchlistHandleSummaryAgent"
PROMPT_VERSION = "watchlist-handle-summary-v1"
SCHEMA_VERSION = "watchlist_handle_summary_v1"


class WatchlistTopicPayload(BaseModel):
    title: str
    description: str
    event_count: int = Field(ge=0)
    top_event_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class WatchlistHandleSummaryPayload(BaseModel):
    summary_zh: str
    topics: list[WatchlistTopicPayload] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)


HANDLE_SUMMARY_PAYLOAD_TYPE = WatchlistHandleSummaryPayload


__all__ = [
    "AGENT_NAME",
    "BACKEND",
    "HANDLE_SUMMARY_PAYLOAD_TYPE",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "WORKFLOW_NAME",
    "WatchlistHandleSummaryPayload",
    "WatchlistTopicPayload",
]
