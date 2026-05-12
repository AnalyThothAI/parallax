from gmgn_twitter_intel.domains.token_intel.read_models.search_agent_brief import (
    build_token_agent_brief,
    build_topic_agent_brief,
)


def test_token_agent_brief_summarizes_project_propagation_and_bull_bear_views():
    posts = [
        post("ev_401", "0xLens", "CA first mention for $RKC", phase="seed"),
        post("ev_433", "ansem", "RKC looks like a Solana runtime social bet", phase="ignition", watched=True),
        post("ev_482", "toly", "Runtime narrative gets a watched-handle reply", phase="expansion", watched=True),
        post("ev_556", "apealerts", "RKC price target recap", phase="chase"),
    ]
    timeline = {
        "summary": {
            "posts": 73,
            "authors": 18,
            "watched_posts": 6,
            "phase": "expansion",
            "top_author_share": 0.22,
            "duplicate_text_share": 0.12,
        },
        "market_overlay": {"target_type": "Asset", "symbol": "RKC"},
        "stages": [
            stage("seed", "ev_401", posts=8, authors=4),
            stage("ignition", "ev_433", posts=21, authors=9),
            stage("expansion", "ev_482", posts=31, authors=14),
            stage("chase", "ev_556", posts=13, authors=7),
        ],
        "authors": [
            {"handle": "ansem", "role": "watched", "posts": 2, "first_seen_ms": 1_700_000_000_000},
            {"handle": "0xLens", "role": "amplifier", "posts": 1, "first_seen_ms": 1_699_999_000_000},
        ],
    }

    brief = build_token_agent_brief(
        target={"symbol": "RKC", "target_type": "Asset", "target_id": "asset:solana:rkc"},
        timeline=timeline,
        posts={"items": posts},
        radar_item=None,
    )

    assert brief["schema_version"] == "search_agent_brief_v1"
    assert brief["generated_by"] == "deterministic"
    assert "RKC" in brief["project_summary"]["one_liner"]
    assert "过去 24 小时" in brief["project_summary"]["summary_zh"]
    assert brief["propagation"]["phases"][0]["phase"] == "seed"
    assert len(brief["propagation"]["phases"]) == 4
    assert brief["bull_bear"]["stance"] == "watch"
    assert brief["bull_bear"]["bull"]["triggers_zh"]
    assert brief["bull_bear"]["bear"]["invalidations_zh"]
    allowed_ids = {item["event_id"] for item in posts}
    cited_ids = set(brief["project_summary"]["evidence_event_ids"])
    for phase in brief["propagation"]["phases"]:
        cited_ids.update(phase["evidence_event_ids"])
    cited_ids.update(brief["bull_bear"]["bull"]["evidence_event_ids"])
    cited_ids.update(brief["bull_bear"]["bear"]["evidence_event_ids"])
    assert cited_ids <= allowed_ids


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
