from gmgn_twitter_intel.domains.narrative_intel.read_models.narrative_read_model import (
    NarrativeReadModel,
)


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


def test_non_1h_token_radar_reuses_ready_1h_digest_as_explicit_overlay():
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
        {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}], "window": "1h"}
    ]
    assert digest["status"] == "ready"
    assert digest["analysis_window"] == "1h"
    assert digest["source_window"] == "1h"
    assert digest["surface_window"] == "24h"
    assert digest["reuse_reason"] == "target_current_1h_narrative"
    assert digest["currentness"]["display_status"] == "current"


def test_non_1h_token_radar_without_ready_1h_digest_returns_no_reusable_reason():
    repo = FakeNarrativeRepository(
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
    assert digest["analysis_window"] == "1h"
    assert digest["source_window"] == "1h"
    assert digest["surface_window"] == "4h"
    assert digest["reuse_reason"] == "no_reusable_1h_digest"
    assert digest["data_gaps_json"] == [{"reason": "no_reusable_1h_digest"}]
    assert digest["data_gaps"] == [{"reason": "no_reusable_1h_digest"}]
    assert digest["currentness"]["display_status"] == "not_ready"
    assert digest["currentness"]["reason"] == "no_reusable_1h_digest"


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


class FakeNarrativeRepository:
    def __init__(self, digests):
        self.digests = digests
        self.calls = []

    def current_narrative_snapshots_for_targets(self, targets, *, window, scope, schema_version, now_ms):
        self.calls.append({"targets": targets, "window": window})
        return self.digests
