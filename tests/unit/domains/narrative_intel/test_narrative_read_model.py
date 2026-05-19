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

    assert digest["dominant_narrative"]["title"] == "SOL 轮动"
    assert digest["dominant_narrative"]["trade_stance"] == "bullish"
    assert digest["coverage"]["source_mentions"] == 5
    assert digest["coverage"]["labeled_mentions"] == 1
    assert digest["bull_bear"]["bull"]["summary_zh"] == "多头看资金轮动"
    assert digest["data_gaps"] == [
        {"gap_type": "semantic_analysis", "concrete_reason": "coverage too low", "reason": "coverage too low"}
    ]
    assert digest["evidence_refs"] == [{"ref_id": "event:event-1", "kind": "event"}]


class FakeNarrativeRepository:
    def __init__(self, digests):
        self.digests = digests

    def current_digests_for_targets(self, targets, *, window, scope, schema_version):
        return self.digests
