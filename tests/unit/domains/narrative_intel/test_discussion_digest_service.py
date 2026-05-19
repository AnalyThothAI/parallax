import json

from gmgn_twitter_intel.domains.narrative_intel.services.discussion_digest_service import (
    DiscussionDigestService,
)


def test_digest_request_uses_compact_agent_payload():
    service = DiscussionDigestService(max_mentions_per_digest=1)
    request = service.build_digest_request(
        run_id="run-1",
        target_type="Asset",
        target_id="asset:solana:token:So111",
        window="24h",
        scope="all",
        context={
            "mentions": [
                {
                    "event_id": "event-1",
                    "semantic_id": "semantic-1",
                    "target_type": "Asset",
                    "target_id": "asset:solana:token:So111",
                    "source_received_at_ms": 1_800_000,
                    "author_handle": "trader",
                    "tweet_id": "tweet-1",
                    "text_clean": "x" * 900,
                    "status": "labeled",
                    "trade_stance": "bullish",
                    "attention_valence": "celebratory",
                    "narrative_cluster_key": "sol-rotation",
                    "claim_type": "price-action",
                    "evidence_type": "opinion",
                    "semantic_confidence": 0.86,
                    "evidence_refs_json": [{"ref_id": "event:event-1", "kind": "event"}],
                    "co_mentioned_targets_json": [{"target_id": "asset:solana:token:Bonk"}],
                    "reference_json": {"raw": "not for agent" * 1000},
                    "raw_label_json": {"raw": "not for agent" * 1000},
                },
                {
                    "event_id": "event-2",
                    "semantic_id": "semantic-2",
                    "text_clean": "second mention should be outside the cap",
                },
            ],
            "semantic_rows": [{"raw": "duplicated DB rows should not be in request context"}],
            "allowed_refs": [
                {"ref_id": "event:event-1", "kind": "event", "source_table": "events", "extra": "ignored"},
                {
                    "ref_id": "semantic:semantic-1",
                    "kind": "semantic",
                    "source_table": "token_mention_semantics",
                },
                {"ref_id": "event:event-2", "kind": "event", "source_table": "events"},
            ],
            "source_event_count": 2,
            "labeled_event_count": 1,
            "independent_author_count": 1,
        },
    )

    payload = request.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=False)

    assert len(request.mentions) == 1
    assert request.mentions[0]["text_clean"].endswith("...")
    assert len(request.mentions[0]["text_clean"]) <= 363
    assert "reference_json" not in request.mentions[0]
    assert "raw_label_json" not in request.mentions[0]
    assert "semantic_rows" not in request.context
    assert "allowed_refs" not in request.context
    assert request.context == {
        "source_event_count": 2,
        "labeled_event_count": 1,
        "independent_author_count": 1,
        "semantic_coverage": 0.5,
        "mention_count_sent": 1,
        "mention_limit": 1,
    }
    assert {ref["ref_id"] for ref in request.allowed_refs} == {"event:event-1", "semantic:semantic-1"}
    assert "not for agent" not in encoded


def test_digest_request_default_prompt_budget_stays_small_for_realtime_latency():
    service = DiscussionDigestService()
    mentions = [
        {
            "event_id": f"event-{index}",
            "semantic_id": f"semantic-{index}",
            "target_type": "Asset",
            "target_id": "asset:solana:token:So111",
            "text_clean": "x" * 500,
            "status": "labeled",
            "author_handle": f"author-{index}",
            "evidence_refs_json": [{"ref_id": f"event:event-{index}", "kind": "event"}],
        }
        for index in range(40)
    ]

    request = service.build_digest_request(
        run_id="run-1",
        target_type="Asset",
        target_id="asset:solana:token:So111",
        window="24h",
        scope="all",
        context={
            "mentions": mentions,
            "allowed_refs": [
                {"ref_id": f"event:event-{index}", "kind": "event", "source_table": "events"}
                for index in range(40)
            ],
            "source_event_count": 40,
            "labeled_event_count": 40,
            "independent_author_count": 40,
        },
    )

    assert len(request.mentions) == 24
    assert request.context["mention_limit"] == 24
    assert max(len(mention["text_clean"]) for mention in request.mentions) <= 363
    assert len(request.allowed_refs) == 24


def test_refresh_decision_waits_for_pending_semantics_instead_of_insufficient():
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 10,
            "labeled_event_count": 2,
            "independent_author_count": 5,
            "semantic_rows": [
                {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                {"event_id": "event-3", "author_handle": "c", "status": "queued"},
                {"event_id": "event-4", "author_handle": "d", "status": "retryable_error"},
            ],
        }
    )

    assert decision.should_refresh is False
    assert decision.reason == "semantic_labeling_pending"
    assert decision.status_if_not_refresh == "pending"


def test_refresh_decision_uses_source_set_count_when_semantic_rows_are_missing():
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 10,
            "labeled_event_count": 0,
            "independent_author_count": 5,
            "semantic_rows": [],
        }
    )

    assert decision.should_refresh is False
    assert decision.reason == "semantic_labeling_pending"
    assert decision.status_if_not_refresh == "pending"


def test_refresh_decision_reports_low_source_volume_only_from_source_set_count():
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 2,
            "labeled_event_count": 2,
            "independent_author_count": 2,
            "semantic_rows": [
                {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
            ],
        }
    )

    assert decision.should_refresh is False
    assert decision.reason == "low_source_volume"
    assert decision.status_if_not_refresh == "insufficient"


def test_refresh_decision_reports_terminal_semantic_unavailable_after_all_sources_attempted():
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 3,
            "labeled_event_count": 0,
            "independent_author_count": 3,
            "semantic_rows": [
                {"event_id": "event-1", "author_handle": "a", "status": "semantic_unavailable"},
                {"event_id": "event-2", "author_handle": "b", "status": "semantic_unavailable"},
                {"event_id": "event-3", "author_handle": "c", "status": "semantic_unavailable"},
            ],
        }
    )

    assert decision.should_refresh is False
    assert decision.reason == "semantic_provider_unavailable"
    assert decision.status_if_not_refresh == "semantic_unavailable"


def test_digest_request_sends_only_labeled_mentions():
    service = DiscussionDigestService(max_mentions_per_digest=10)

    request = service.build_digest_request(
        run_id="run-1",
        target_type="Asset",
        target_id="asset:solana:token:So111",
        window="24h",
        scope="all",
        context={
            "mentions": [
                {
                    "event_id": "event-queued",
                    "semantic_id": "semantic-queued",
                    "target_type": "Asset",
                    "target_id": "asset:solana:token:So111",
                    "text_clean": "queued row should not be sent",
                    "status": "queued",
                    "author_handle": "queued",
                },
                {
                    "event_id": "event-labeled",
                    "semantic_id": "semantic-labeled",
                    "target_type": "Asset",
                    "target_id": "asset:solana:token:So111",
                    "text_clean": "SOL rotation claim",
                    "status": "labeled",
                    "trade_stance": "bullish",
                    "attention_valence": "celebratory",
                    "author_handle": "labeled",
                    "evidence_refs_json": [{"ref_id": "event:event-labeled", "kind": "event"}],
                },
            ],
            "allowed_refs": [
                {"ref_id": "event:event-queued", "kind": "event", "source_table": "events"},
                {
                    "ref_id": "semantic:semantic-queued",
                    "kind": "semantic",
                    "source_table": "token_mention_semantics",
                },
                {"ref_id": "event:event-labeled", "kind": "event", "source_table": "events"},
                {
                    "ref_id": "semantic:semantic-labeled",
                    "kind": "semantic",
                    "source_table": "token_mention_semantics",
                },
            ],
            "source_event_count": 2,
            "labeled_event_count": 1,
            "independent_author_count": 2,
        },
    )

    assert [mention["event_id"] for mention in request.mentions] == ["event-labeled"]
    assert {ref["ref_id"] for ref in request.allowed_refs} == {
        "event:event-labeled",
        "semantic:semantic-labeled",
    }
