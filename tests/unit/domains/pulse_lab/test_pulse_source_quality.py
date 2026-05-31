from __future__ import annotations

from parallax.domains.pulse_lab.services.pulse_source_quality import PulseSourceQuality


def test_source_quality_blocks_watched_only_single_author() -> None:
    decision = PulseSourceQuality().evaluate(
        factor_snapshot=_snapshot(
            unique_authors=1,
            independent_authors=1,
            watched_mentions=1,
            top_author_share=1.0,
            effective_authors=1.0,
        ),
        window="1h",
        scope="all",
    )

    assert decision.public_allowed is False
    assert decision.reasons == (
        "watched_only_source",
        "single_author_source",
        "low_effective_author_count",
        "top_author_share_high",
    )
    assert decision.metrics["watched_only"] is True


def test_source_quality_blocks_duplicate_or_concentrated_sources() -> None:
    decision = PulseSourceQuality().evaluate(
        factor_snapshot=_snapshot(
            unique_authors=3,
            independent_authors=3,
            watched_mentions=0,
            top_author_share=0.75,
            duplicate_text_share=0.5,
            effective_authors=3.0,
        ),
        window="4h",
        scope="matched",
    )

    assert decision.public_allowed is False
    assert decision.reasons == ("top_author_share_high", "duplicate_text_share_high")


def test_source_quality_allows_multi_author_broad_source() -> None:
    decision = PulseSourceQuality().evaluate(
        factor_snapshot=_snapshot(
            unique_authors=4,
            independent_authors=4,
            watched_mentions=0,
            top_author_share=0.4,
            duplicate_text_share=0.0,
            effective_authors=4.0,
        ),
        window="1h",
        scope="all",
    )

    assert decision.public_allowed is True
    assert decision.reasons == ()


def _snapshot(
    *,
    unique_authors: int,
    independent_authors: int,
    watched_mentions: int,
    top_author_share: float,
    effective_authors: float,
    duplicate_text_share: float = 0.0,
) -> dict:
    return {
        "families": {
            "social_heat": {
                "facts": {
                    "unique_authors": unique_authors,
                    "watched_mentions": watched_mentions,
                },
            },
            "social_propagation": {
                "facts": {
                    "independent_authors": independent_authors,
                    "effective_authors": effective_authors,
                    "source_weighted_effective_authors": effective_authors,
                    "top_author_share": top_author_share,
                    "duplicate_text_share": duplicate_text_share,
                },
            },
        },
    }
