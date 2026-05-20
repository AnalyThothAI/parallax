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
            "semantic_row_count": 2,
            "missing_semantic_count": 0,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 0,
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
        "semantic_row_count": 2,
        "missing_semantic_count": 0,
        "pending_semantic_count": 0,
        "retryable_semantic_count": 0,
        "terminal_unavailable_count": 0,
        "labeled_event_count": 1,
        "independent_author_count": 1,
        "semantic_coverage": 0.5,
        "mention_count_sent": 1,
        "mention_limit": 1,
        "prompt_mention_count": 1,
        "prompt_mention_limit": 1,
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
    assert request.context["prompt_mention_limit"] == 24
    assert request.context["prompt_mention_count"] == 24
    assert max(len(mention["text_clean"]) for mention in request.mentions) <= 363
    assert len(request.allowed_refs) == 24


def test_refresh_decision_waits_for_pending_semantics_instead_of_insufficient():
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 10,
            "semantic_row_count": 4,
            "missing_semantic_count": 0,
            "pending_semantic_count": 1,
            "retryable_semantic_count": 1,
            "terminal_unavailable_count": 0,
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
            "semantic_row_count": 0,
            "missing_semantic_count": 10,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 0,
            "labeled_event_count": 0,
            "independent_author_count": 5,
            "semantic_rows": [],
        }
    )

    assert decision.should_refresh is False
    assert decision.reason == "semantic_labeling_pending"
    assert decision.status_if_not_refresh == "pending"


def test_refresh_decision_pending_uses_explicit_missing_count_not_prompt_sample_size() -> None:
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 82,
            "independent_author_count": 12,
            "semantic_row_count": 82,
            "missing_semantic_count": 0,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 25,
            "labeled_event_count": 57,
            "mentions": [{"status": "labeled"} for _ in range(24)],
            "semantic_rows": [{"status": "labeled"} for _ in range(24)],
        }
    )

    assert decision.should_refresh is True
    assert decision.reason == "thresholds_met"


def test_refresh_decision_reports_semantic_pending_when_source_rows_are_missing_semantics() -> None:
    service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)

    decision = service.refresh_decision(
        {
            "source_event_count": 10,
            "independent_author_count": 4,
            "semantic_row_count": 4,
            "missing_semantic_count": 6,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 0,
            "labeled_event_count": 4,
            "mentions": [{"status": "labeled"} for _ in range(4)],
            "semantic_rows": [{"status": "labeled"} for _ in range(4)],
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
            "semantic_row_count": 2,
            "missing_semantic_count": 0,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 0,
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
            "semantic_row_count": 3,
            "missing_semantic_count": 0,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 3,
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


def test_status_digest_carries_source_fingerprint_from_context() -> None:
    service = DiscussionDigestService()

    digest = service.build_status_digest(
        target_type="chain_token",
        target_id="solana:So111",
        window="24h",
        scope="all",
        context={
            "source_event_count": 3,
            "labeled_event_count": 0,
            "independent_author_count": 2,
            "source_fingerprint": "source-current",
            "epoch_id": "epoch-1",
            "epoch_policy_version": "token-narrative-epoch-v1",
            "source_event_ids": ["event-1", "event-2", "event-3"],
            "source_window_start_ms": 100,
            "source_window_end_ms": 900,
            "epoch_closed_at_ms": 1000,
            "display_current_until_ms": 2000,
            "refresh_reason": "semantic_pending",
        },
        reason="semantic_labeling_pending",
        now_ms=1000,
        status="pending",
    )

    assert digest.source_fingerprint == "source-current"
    assert digest.epoch_id == "epoch-1"
    assert digest.epoch_policy_version == "token-narrative-epoch-v1"
    assert digest.source_event_ids == ["event-1", "event-2", "event-3"]
    assert digest.source_window_start_ms == 100
    assert digest.source_window_end_ms == 900
    assert digest.epoch_closed_at_ms == 1000
    assert digest.display_current_until_ms == 2000
    assert digest.refresh_reason == "semantic_pending"


def test_ready_digest_carries_source_fingerprint_from_context() -> None:
    service = DiscussionDigestService()

    digest = service.publish_ready_digest(
        {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "window": "24h",
            "scope": "all",
            "schema_version": "narrative_intel_v1",
            "model_version": "gpt-test",
            "status": "ready",
            "dominant_narratives": [
                {
                    "cluster_key": "main",
                    "summary_zh": "主线",
                    "evidence_refs": [{"ref_id": "event:e1"}],
                }
            ],
            "bull_view": {"summary_zh": "多头", "evidence_refs": [{"ref_id": "event:e1"}]},
            "bear_view": {"summary_zh": "空头", "evidence_refs": [{"ref_id": "event:e2"}]},
            "evidence_refs": [{"ref_id": "event:e1"}],
        },
        context={
            "source_event_count": 3,
            "labeled_event_count": 3,
            "independent_author_count": 2,
            "source_fingerprint": "source-current",
            "epoch_id": "epoch-1",
            "epoch_policy_version": "token-narrative-epoch-v1",
            "source_event_ids": ["e1", "e2", "e3"],
            "source_window_start_ms": 100,
            "source_window_end_ms": 900,
            "epoch_closed_at_ms": 1000,
            "display_current_until_ms": 2000,
            "refresh_reason": "initial_ready",
            "mentions": [{"event_id": "e1"}, {"event_id": "e2"}, {"event_id": "e3"}],
            "semantic_rows": [{"status": "labeled"}, {"status": "labeled"}, {"status": "labeled"}],
        },
        now_ms=1000,
    )

    assert digest.source_fingerprint == "source-current"
    assert digest.epoch_id == "epoch-1"
    assert digest.epoch_policy_version == "token-narrative-epoch-v1"
    assert digest.source_event_ids == ["e1", "e2", "e3"]
    assert digest.source_window_start_ms == 100
    assert digest.source_window_end_ms == 900
    assert digest.epoch_closed_at_ms == 1000
    assert digest.display_current_until_ms == 2000
    assert digest.refresh_reason == "initial_ready"
