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
    assert len(request.mentions[0]["text_clean"]) <= 603
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

