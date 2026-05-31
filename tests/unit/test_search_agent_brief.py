from parallax.domains.token_intel.read_models.search_agent_brief import (
    build_topic_agent_brief,
)


def test_topic_agent_brief_summarizes_keyword_corpus_without_project_claims():
    items = [
        {"event": {"event_id": "ev_701", "author_handle": "minerwatch", "text_clean": "DePIN 挖矿 讨论"}},
        {"event": {"event_id": "ev_744", "author_handle": "aiinfra", "text_clean": "AI compute mining"}},
        {"event": {"event_id": "ev_769", "author_handle": "onchainchef", "text_clean": "挖矿 farming mixed"}},
    ]

    brief = build_topic_agent_brief(query="挖矿", items=items)

    assert brief["schema_version"] == "search_agent_brief_v1"
    assert "挖矿" in brief["project_summary"]["one_liner"]
    assert brief["propagation"]["phases"][0]["tweets"] == 3
    assert brief["bull_bear"]["stance"] == "research"
    assert brief["bull_bear"]["bull"]["evidence_event_ids"] == ["ev_701", "ev_744", "ev_769"]


def post(event_id: str, handle: str, text: str, *, phase: str, watched: bool = False) -> dict:
    return {
        "event_id": event_id,
        "handle": handle,
        "author_handle": handle,
        "text": text,
        "stage_phase": phase,
        "is_watched": watched,
        "received_at_ms": 1_700_000_000_000,
    }


def stage(phase: str, event_id: str, *, posts: int, authors: int) -> dict:
    return {
        "stage_id": f"{phase}:1",
        "phase": phase,
        "start_ms": 1_700_000_000_000,
        "end_ms": 1_700_000_100_000,
        "people": {
            "posts": posts,
            "authors": authors,
            "watched_posts": 1 if phase in {"ignition", "expansion"} else 0,
            "top_author_share": 0.22,
        },
        "representative_event_ids": [event_id],
    }
