from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import (
    AGENT_NAME,
    HANDLE_SUMMARY_PAYLOAD_TYPE,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    WORKFLOW_NAME,
)
from gmgn_twitter_intel.platform.agent_execution import AgentStageSpec


@lru_cache(maxsize=1)
def handle_summary_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "handle_summary.md").read_text(encoding="utf-8")


def build_handle_summary_stage(
    *,
    model: str,
    handle: str,
    events: list[dict[str, Any]],
    run_id: str,
    job: dict[str, Any],
    context: dict[str, Any],
    max_turns: int = 1,
) -> AgentStageSpec:
    input_json = {
        "handle": handle,
        "context": context,
        "events": [_event_payload(item) for item in events],
    }
    return AgentStageSpec(
        lane="watchlist.handle_summary",
        stage="summary",
        model=model,
        instructions=handle_summary_instructions(),
        input_payload=json.dumps(input_json, ensure_ascii=False, sort_keys=True),
        output_type=HANDLE_SUMMARY_PAYLOAD_TYPE,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        workflow_name=WORKFLOW_NAME,
        agent_name=AGENT_NAME,
        group_id=handle,
        trace_metadata={
            "run_id": run_id,
            "handle": handle,
            "job_handle": str(job.get("handle") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
        },
        max_turns=max_turns,
    )


def _event_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item.get("event_id"),
        "received_at_ms": item.get("received_at_ms"),
        "event_type": item.get("event_type"),
        "subject": item.get("subject"),
        "summary_zh": item.get("summary_zh"),
        "anchor_terms": item.get("anchor_terms") or [],
        "token_candidates": item.get("token_candidates") or [],
        "cashtags": item.get("cashtags") or [],
        "hashtags": item.get("hashtags") or [],
        "text": item.get("event_text") or "",
    }


__all__ = ["build_handle_summary_stage", "handle_summary_instructions"]
