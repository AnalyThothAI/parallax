from parallax.domains.narrative_intel.read_models.narrative_read_model import (
    NarrativeReadModel,
)
from parallax.domains.narrative_intel.types.narrative_currentness import unsupported_digest_sentinel


def test_hydrate_token_radar_projects_digest_storage_fields_to_public_contract():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "status": "insufficient",
                "headline_zh": "SOL 讨论升温",
                "dominant_narratives_json": [
                    {
                        "cluster_key": "sol-rotation",
                        "label_zh": "SOL 轮动",
                        "summary_zh": "交易员讨论 SOL beta 回流。",
                        "stance_mix": {"bullish": 0.7, "neutral": 0.3},
                        "evidence_refs": [{"ref_id": "event:event-1", "kind": "event"}],
                    }
                ],
                "bull_view_json": {"summary_zh": "多头看资金轮动", "strength": "medium"},
                "bear_view_json": {"summary_zh": "空头担心追高", "strength": "weak"},
                "stance_mix_json": {"bullish": 0.7, "neutral": 0.3},
                "attention_valence_mix_json": {"celebratory": 0.6},
                "propagation_read_json": {"primary_channel": "trader_replies"},
                "data_gaps_json": [{"gap_type": "semantic_analysis", "concrete_reason": "coverage too low"}],
                "semantic_coverage": 0.2,
                "source_event_count": 5,
                "labeled_event_count": 1,
                "independent_author_count": 3,
                "evidence_refs_json": [{"ref_id": "event:event-1", "kind": "event"}],
                "currentness": {
                    "display_status": "updating",
                    "reason": "digest_updating",
                    "delta_source_event_count": 1,
                },
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["dominant_narrative"]["title"] == "SOL 轮动"
    assert digest["dominant_narrative"]["trade_stance"] == "bullish"
    assert digest["coverage"]["source_mentions"] == 5
    assert digest["coverage"]["labeled_mentions"] == 1
    assert digest["bull_bear"]["bull"]["summary_zh"] == "多头看资金轮动"
    assert digest["data_gaps"] == [
        {"gap_type": "semantic_analysis", "concrete_reason": "coverage too low", "reason": "coverage too low"}
    ]
    assert digest["evidence_refs"] == [{"ref_id": "event:event-1", "kind": "event"}]
    assert digest["currentness"]["display_status"] == "updating"


def test_hydrate_token_radar_does_not_expose_digest_runtime_or_storage_fields():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "window": "1h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "status": "ready",
                "headline_zh": "SOL 讨论升温",
                "dominant_narratives_json": [{"label_zh": "SOL 轮动"}],
                "bull_view_json": {"summary_zh": "多头看资金轮动"},
                "bear_view_json": {"summary_zh": "空头担心追高"},
                "stance_mix_json": {"bullish": 0.7},
                "attention_valence_mix_json": {"celebratory": 0.6},
                "propagation_read_json": {"primary_channel": "trader_replies"},
                "data_gaps_json": [],
                "evidence_refs_json": [{"ref_id": "event:event-1"}],
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
                "model_run_id": "run-1",
                "payload_hash": "hash-1",
                "source_fingerprint": "source:fingerprint",
                "label_fingerprint": "label:fingerprint",
                "raw_response_json": {"raw": True},
                "raw_request_json": {"raw": True},
                "_current_admission": {
                    "admission_id": "admission-1",
                    "admission_generation": "1h:all:123",
                    "payload_hash": "admission-hash",
                },
                "currentness": {"display_status": "current", "reason": "fingerprint_match"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["headline_zh"] == "SOL 讨论升温"
    assert digest["dominant_narratives"] == [{"label_zh": "SOL 轮动"}]
    assert digest["evidence_refs"] == [{"ref_id": "event:event-1"}]
    assert (
        not {
            "digest_id",
            "model_run_id",
            "payload_hash",
            "source_fingerprint",
            "label_fingerprint",
            "dominant_narratives_json",
            "bull_view_json",
            "bear_view_json",
            "stance_mix_json",
            "attention_valence_mix_json",
            "propagation_read_json",
            "data_gaps_json",
            "evidence_refs_json",
            "raw_response_json",
            "raw_request_json",
            "_current_admission",
            "admission_id",
            "admission_generation",
        }
        & digest.keys()
    )


def test_hydrate_token_radar_adds_compact_processing_backlog_without_rewriting_status_truth():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "status": "pending",
                "data_gaps_json": [{"reason": "semantic_labeling_pending"}],
                "semantic_coverage": 0.25,
                "source_event_count": 8,
                "labeled_event_count": 2,
                "independent_author_count": 5,
                "semantic_backlog_pending": 6,
                "semantic_backlog_retryable": 2,
                "semantic_backlog_unavailable": 1,
                "semantic_backlog_oldest_due_at_ms": 7_000,
                "currentness": {"display_status": "not_ready", "reason": "semantic_labeling_pending"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=10_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["status"] == "pending"
    assert digest["data_gaps"] == [{"reason": "semantic_labeling_pending"}]
    assert digest["processing"] == {
        "backlog": {
            "semantic": 6,
            "retryable": 2,
            "unavailable": 1,
            "oldest_due_age_ms": 3_000,
        }
    }
    assert digest["currentness"]["display_status"] == "not_ready"


def test_hydrate_token_radar_projects_repository_missing_digest_reason():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "status": "pending",
                "is_current": False,
                "data_gaps_json": [{"reason": "no_ready_digest"}],
                "semantic_coverage": 0,
                "source_event_count": 0,
                "labeled_event_count": 0,
                "independent_author_count": 0,
                "evidence_refs_json": [],
                "currentness": {"display_status": "not_ready", "reason": "no_ready_digest"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["status"] == "pending"
    assert digest["data_gaps"] == [{"reason": "no_ready_digest"}]
    assert digest["coverage"]["source_mentions"] == 0
    assert digest["currentness"]["display_status"] == "not_ready"


def test_hydrate_token_radar_missing_repository_row_uses_current_missing_digest_reason():
    result = NarrativeReadModel(FakeNarrativeRepository({})).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["status"] == "pending"
    assert digest["data_gaps"] == [{"reason": "no_ready_digest"}]
    assert digest["currentness"]["display_status"] == "not_ready"
    assert digest["currentness"]["reason"] == "no_ready_digest"


def test_hydrate_token_case_adds_narrative_delta_from_digest_currentness():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "status": "ready",
                "headline_zh": "SOL 讨论升温",
                "semantic_coverage": 0.8,
                "source_event_count": 10,
                "labeled_event_count": 8,
                "independent_author_count": 4,
                "evidence_refs_json": [],
                "currentness": {
                    "display_status": "updating",
                    "reason": "digest_updating",
                    "ready_source_event_count": 8,
                    "current_source_event_count": 10,
                    "delta_source_event_count": 2,
                    "delta_independent_author_count": 1,
                    "last_ready_computed_at_ms": 900,
                },
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_case(
        {"target": {"target_type": "Asset", "target_id": "asset:solana:token:So111"}},
        window="24h",
        scope="all",
        now_ms=1_000,
    )

    assert result["discussion_digest"]["currentness"]["display_status"] == "updating"
    assert result["narrative_delta"]["delta_source_event_count"] == 2
    assert result["narrative_delta"]["last_ready_computed_at_ms"] == 900


def test_non_1h_token_radar_returns_unsupported_without_reusing_ready_1h_digest():
    repo = WindowAwareNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "window": "1h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "status": "ready",
                "headline_zh": "SOL 讨论升温",
                "semantic_coverage": 0.9,
                "source_event_count": 5,
                "labeled_event_count": 5,
                "independent_author_count": 3,
                "evidence_refs_json": [],
                "currentness": {"display_status": "current", "reason": "fingerprint_match"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="24h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]
    assert repo.calls == [
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}], "window": "24h"}
    ]
    assert digest["status"] == "pending"
    assert digest["data_gaps"] == [{"reason": "narrative_not_supported_for_window"}]
    assert digest["currentness"]["display_status"] == "unsupported_window"
    assert "analysis_window" not in digest
    assert "source_window" not in digest
    assert "surface_window" not in digest
    assert "reuse_reason" not in digest


def test_non_1h_token_radar_without_ready_digest_returns_unsupported_reason():
    repo = WindowAwareNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "window": "1h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "status": "pending",
                "data_gaps_json": [{"reason": "semantic_labeling_pending"}],
                "semantic_coverage": 0.0,
                "source_event_count": 0,
                "labeled_event_count": 0,
                "independent_author_count": 0,
                "evidence_refs_json": [],
                "currentness": {"display_status": "not_ready", "reason": "semantic_labeling_pending"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="4h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]

    assert digest["status"] == "pending"
    assert digest["data_gaps"] == [{"reason": "narrative_not_supported_for_window"}]
    assert digest["currentness"]["display_status"] == "unsupported_window"
    assert digest["currentness"]["reason"] == "unsupported_window"
    assert "analysis_window" not in digest
    assert "source_window" not in digest
    assert "surface_window" not in digest
    assert "reuse_reason" not in digest


def test_1h_token_radar_uses_exact_1h_snapshot_without_overlay():
    repo = FakeNarrativeRepository(
        {
            ("Asset", "asset:solana:token:So111"): {
                "digest_id": "digest-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:So111",
                "window": "1h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "status": "ready",
                "semantic_coverage": 0.8,
                "source_event_count": 4,
                "labeled_event_count": 4,
                "independent_author_count": 2,
                "evidence_refs_json": [],
                "currentness": {"display_status": "current", "reason": "fingerprint_match"},
            }
        }
    )

    result = NarrativeReadModel(repo).hydrate_token_radar(
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    digest = result["targets"][0]["discussion_digest"]
    assert repo.calls == [
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}], "window": "1h"}
    ]
    assert "analysis_window" not in digest
    assert "source_window" not in digest
    assert "surface_window" not in digest
    assert "reuse_reason" not in digest


def test_hydrate_target_posts_does_not_expose_semantic_runtime_or_storage_fields():
    repo = FakeNarrativeRepository(
        {},
        semantics={
            ("event-1", "chain_token", "solana:So111"): {
                "semantic_id": "semantic-1",
                "event_id": "event-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "schema_version": "narrative_intel_v1",
                "model_version": "gpt-test",
                "text_fingerprint": "text-hash",
                "language": "en",
                "status": "labeled",
                "trade_stance": "bullish",
                "attention_valence": "celebratory",
                "narrative_cluster_key": "sol-rotation",
                "claim_type": "price-action",
                "evidence_type": "scanner-alert",
                "semantic_confidence": 0.8,
                "co_mentioned_targets_json": [{"target_id": "asset:other"}],
                "evidence_refs_json": [{"ref_id": "event:event-1"}],
                "raw_label_json": {"raw": True},
                "model_run_id": "run-1",
                "source_received_at_ms": 900,
                "queued_at_ms": 901,
                "computed_at_ms": 902,
                "retry_count": 2,
                "next_retry_at_ms": 903,
                "leased_until_ms": 904,
                "lease_owner": "mention_semantics",
                "attempt_count": 3,
                "claimed_at_ms": 905,
                "last_error": "boom",
            }
        },
    )

    result = NarrativeReadModel(repo).hydrate_target_posts(
        {
            "items": [
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                }
            ]
        },
        window="1h",
        scope="all",
        now_ms=1_000,
    )

    semantic = result["items"][0]["semantic"]

    assert semantic == {
        "status": "labeled",
        "trade_stance": "bullish",
        "attention_valence": "celebratory",
        "narrative_cluster_key": "sol-rotation",
        "claim_type": "price-action",
        "evidence_type": "scanner-alert",
        "semantic_confidence": 0.8,
        "language": "en",
        "co_mentioned_targets": [{"target_id": "asset:other"}],
        "evidence_refs": [{"ref_id": "event:event-1"}],
    }


class FakeNarrativeRepository:
    def __init__(self, digests, *, semantics=None):
        self.digests = digests
        self.semantics = semantics or {}
        self.calls = []

    def current_narrative_snapshots_for_targets(self, targets, *, window, scope, schema_version, now_ms):
        self.calls.append({"targets": targets, "window": window})
        return self.digests

    def semantics_for_posts(self, posts, *, schema_version):
        return {
            key: semantic
            for key, semantic in self.semantics.items()
            if any(
                key
                == (
                    str(post.get("event_id")),
                    str(post.get("target_type")),
                    str(post.get("target_id")),
                )
                for post in posts
            )
        }


class WindowAwareNarrativeRepository(FakeNarrativeRepository):
    def current_narrative_snapshots_for_targets(self, targets, *, window, scope, schema_version, now_ms):
        self.calls.append({"targets": targets, "window": window})
        if window == "1h":
            return self.digests
        return {
            (str(target["target_type"]), str(target["target_id"])): unsupported_digest_sentinel(
                target_type=str(target["target_type"]),
                target_id=str(target["target_id"]),
                window=window,
                scope=scope,
                schema_version=schema_version,
            )
            for target in targets
        }
