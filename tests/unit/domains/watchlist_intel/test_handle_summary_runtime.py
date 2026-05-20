from __future__ import annotations

import json

from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_runtime import build_handle_summary_stage
from gmgn_twitter_intel.domains.watchlist_intel.types.handle_summary_agent import (
    AGENT_NAME,
    SCHEMA_VERSION,
    WatchlistHandleSummaryPayload,
)


def test_build_handle_summary_stage_is_domain_owned() -> None:
    stage = build_handle_summary_stage(
        handle="alice",
        events=[
            {
                "event_id": "e1",
                "summary_zh": "事件",
                "subject": "SOL",
                "anchor_terms": ["Firedancer"],
                "event_text": "raw text",
            }
        ],
        run_id="run-1",
        job={"handle": "alice", "attempt_count": 2},
        context={"window_days": 7},
    )

    assert stage.lane == "watchlist.handle_summary"
    assert stage.stage == "summary"
    assert stage.agent_name == AGENT_NAME
    assert stage.schema_version == SCHEMA_VERSION
    assert stage.output_type is WatchlistHandleSummaryPayload
    assert "alice" in stage.input_payload
    payload = json.loads(stage.input_payload)
    assert payload["events"][0] == {
        "event_id": "e1",
        "received_at_ms": None,
        "event_type": None,
        "subject": "SOL",
        "summary_zh": "事件",
        "anchor_terms": ["Firedancer"],
        "token_candidates": [],
        "cashtags": [],
        "hashtags": [],
        "text": "raw text",
    }
