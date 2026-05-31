import pytest
from pydantic import ValidationError

from parallax.domains.narrative_intel.services.evidence_ref_validator import (
    EvidenceRefValidator,
)
from parallax.domains.narrative_intel.types.discussion_digest import (
    DigestArgument,
    NarrativeCluster,
    TokenDiscussionDigest,
)
from parallax.domains.narrative_intel.types.evidence_refs import EvidenceRef
from parallax.domains.narrative_intel.types.mention_semantics import MentionSemanticLabel


def event_ref(event_id: str = "event-1") -> dict[str, object]:
    return {
        "ref_id": f"event:{event_id}",
        "kind": "event",
        "source_table": "events",
        "event_id": event_id,
    }


def test_labeled_mention_requires_evidence_and_clamps_confidence():
    label = MentionSemanticLabel(
        event_id="event-1",
        target_type="chain_token",
        target_id="solana:So111",
        trade_stance="",
        attention_valence="",
        claim_type="price-action",
        evidence_type="scanner-alert",
        semantic_confidence=2.0,
        evidence_refs=[event_ref()],
        status="labeled",
    )

    assert label.trade_stance == "unknown"
    assert label.attention_valence == "unknown"
    assert label.semantic_confidence == 1.0

    with pytest.raises(ValidationError):
        MentionSemanticLabel(
            event_id="event-1",
            target_type="chain_token",
            target_id="solana:So111",
            trade_stance="bullish",
            attention_valence="celebratory",
            claim_type="price-action",
            evidence_type="scanner-alert",
            semantic_confidence=0.8,
            evidence_refs=[],
            status="labeled",
        )


def test_ready_digest_requires_public_claim_refs():
    with pytest.raises(ValidationError):
        TokenDiscussionDigest(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            status="ready",
            headline_zh="SOL discussion turns to breakout",
            dominant_narratives=[],
            bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[]),
            bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
            semantic_coverage=0.6,
            source_event_count=5,
            labeled_event_count=3,
            independent_author_count=3,
            evidence_refs=[],
            computed_at_ms=1_000,
        )

    digest = TokenDiscussionDigest(
        target_type="chain_token",
        target_id="solana:So111",
        window="24h",
        scope="matched",
        schema_version="narrative_intel_v1",
        model_version="gpt-test",
        status="ready",
        headline_zh="SOL discussion turns to breakout",
        dominant_narratives=[
            NarrativeCluster(
                cluster_key="breakout",
                label_zh="breakout narrative",
                summary_zh="discussion concentrates on breakout and chase.",
                evidence_refs=[event_ref()],
            )
        ],
        bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[event_ref()]),
        bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
        semantic_coverage=0.6,
        source_event_count=5,
        labeled_event_count=3,
        independent_author_count=3,
        evidence_refs=[event_ref()],
        computed_at_ms=1_000,
    )

    assert digest.status == "ready"


def test_token_discussion_digest_accepts_epoch_metadata_and_source_event_ids():
    digest = TokenDiscussionDigest(
        target_type="chain_token",
        target_id="solana:So111",
        window="24h",
        scope="matched",
        schema_version="narrative_intel_v1",
        model_version="gpt-test",
        status="ready",
        epoch_id="epoch-solana-so111-1000",
        epoch_policy_version="token_narrative_epoch_v1",
        source_event_ids=["event-1", "event-2"],
        source_window_start_ms=1_000,
        source_window_end_ms=2_000,
        epoch_closed_at_ms=2_100,
        display_current_until_ms=2_400,
        refresh_reason="source_changed",
        headline_zh="SOL discussion turns to breakout",
        dominant_narratives=[
            NarrativeCluster(
                cluster_key="breakout",
                label_zh="breakout narrative",
                summary_zh="discussion concentrates on breakout and chase.",
                evidence_refs=[event_ref("event-1")],
            )
        ],
        bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[event_ref("event-1")]),
        bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
        semantic_coverage=0.6,
        source_event_count=2,
        labeled_event_count=2,
        independent_author_count=2,
        evidence_refs=[event_ref("event-1")],
        computed_at_ms=2_100,
    )

    assert digest.epoch_id == "epoch-solana-so111-1000"
    assert digest.epoch_policy_version == "token_narrative_epoch_v1"
    assert digest.source_event_ids == ["event-1", "event-2"]
    assert digest.source_window_start_ms == 1_000
    assert digest.source_window_end_ms == 2_000
    assert digest.epoch_closed_at_ms == 2_100
    assert digest.display_current_until_ms == 2_400
    assert digest.refresh_reason == "source_changed"


def test_ready_digest_with_epoch_metadata_still_requires_semantic_coverage():
    with pytest.raises(ValidationError):
        TokenDiscussionDigest(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            status="ready",
            epoch_id="epoch-solana-so111-1000",
            epoch_policy_version="token_narrative_epoch_v1",
            source_event_ids=["event-1"],
            dominant_narratives=[
                NarrativeCluster(
                    cluster_key="breakout",
                    label_zh="breakout narrative",
                    summary_zh="discussion concentrates on breakout and chase.",
                    evidence_refs=[event_ref("event-1")],
                )
            ],
            bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[event_ref("event-1")]),
            bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
            semantic_coverage=0.0,
            source_event_count=1,
            labeled_event_count=1,
            independent_author_count=1,
            evidence_refs=[event_ref("event-1")],
            computed_at_ms=1_000,
        )


def test_insufficient_digest_requires_data_gaps():
    with pytest.raises(ValidationError):
        TokenDiscussionDigest(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
            model_version="deterministic",
            status="insufficient",
            semantic_coverage=0.0,
            source_event_count=1,
            labeled_event_count=0,
            independent_author_count=1,
            data_gaps=[],
            computed_at_ms=1_000,
        )


def test_evidence_ref_validator_rejects_unknown_public_refs():
    allowed = {
        EvidenceRef(ref_id="event:event-1", kind="event", source_table="events", event_id="event-1"),
        EvidenceRef(ref_id="semantic:semantic-1", kind="semantic", source_table="token_mention_semantics"),
    }
    digest = TokenDiscussionDigest(
        target_type="chain_token",
        target_id="solana:So111",
        window="24h",
        scope="matched",
        schema_version="narrative_intel_v1",
        model_version="gpt-test",
        status="ready",
        dominant_narratives=[
            NarrativeCluster(
                cluster_key="breakout",
                label_zh="breakout narrative",
                summary_zh="discussion concentrates on breakout and chase.",
                evidence_refs=[event_ref("event-404")],
            )
        ],
        bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[event_ref("event-1")]),
        bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
        semantic_coverage=0.5,
        source_event_count=4,
        labeled_event_count=2,
        independent_author_count=2,
        evidence_refs=[event_ref("event-1")],
        computed_at_ms=1_000,
    )

    result = EvidenceRefValidator().validate_digest_refs(digest, allowed)

    assert result.ok is False
    assert result.unknown_refs == ["event:event-404"]
