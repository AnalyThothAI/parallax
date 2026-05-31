from __future__ import annotations

from parallax.domains.token_intel.scoring.factor_cohort import (
    COHORT_DEFINITION_VERSION,
    STABLECOIN_SYMBOLS,
    is_active_cohort_member,
)


def test_stablecoin_excluded_even_with_high_quality_mentions():
    assert (
        is_active_cohort_member(
            target_id="cex_token:USDC",
            symbol="USDC",
            high_confidence_mention_count=999,
            kol_mention_count=10,
            was_first_seen_global_24h=True,
        )
        is False
    )


def test_high_confidence_mentions_qualify():
    assert (
        is_active_cohort_member(
            target_id="asset:pepe",
            symbol="PEPE",
            high_confidence_mention_count=2,
            kol_mention_count=0,
            was_first_seen_global_24h=False,
        )
        is True
    )


def test_kol_mention_alone_qualifies():
    assert (
        is_active_cohort_member(
            target_id="asset:wif",
            symbol="WIF",
            high_confidence_mention_count=0,
            kol_mention_count=1,
            was_first_seen_global_24h=False,
        )
        is True
    )


def test_first_seen_global_alone_qualifies():
    assert (
        is_active_cohort_member(
            target_id="asset:new",
            symbol="BRANDNEW",
            high_confidence_mention_count=0,
            kol_mention_count=0,
            was_first_seen_global_24h=True,
        )
        is True
    )


def test_zero_signals_does_not_qualify():
    assert (
        is_active_cohort_member(
            target_id="asset:ghost",
            symbol="GHOST",
            high_confidence_mention_count=0,
            kol_mention_count=0,
            was_first_seen_global_24h=False,
        )
        is False
    )


def test_stablecoin_symbol_match_is_case_insensitive():
    for sym in ["usdc", "USDT", "Dai", "FdUsd", "tusd"]:
        assert (
            is_active_cohort_member(
                target_id=f"cex_token:{sym.upper()}",
                symbol=sym,
                high_confidence_mention_count=10,
                kol_mention_count=10,
                was_first_seen_global_24h=True,
            )
            is False
        )


def test_cohort_definition_version_is_set():
    assert COHORT_DEFINITION_VERSION == "factor_cohort_v2"
    assert "USDC" in STABLECOIN_SYMBOLS


def test_empty_target_id_never_qualifies():
    assert (
        is_active_cohort_member(
            target_id=None,
            symbol="PEPE",
            high_confidence_mention_count=10,
            kol_mention_count=10,
            was_first_seen_global_24h=True,
        )
        is False
    )


def test_one_high_confidence_mention_no_longer_qualifies_without_other_signal():
    assert (
        is_active_cohort_member(
            target_id="asset:thin",
            symbol="THIN",
            high_confidence_mention_count=1,
            kol_mention_count=0,
            was_first_seen_global_24h=False,
        )
        is False
    )
