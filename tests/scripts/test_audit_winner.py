from __future__ import annotations

from scripts.audit_dedup.candidates import AssetCandidate
from scripts.audit_dedup.winner import WinnerOutcome, pick_in_db_winner


def _c(asset_id: str, *, first_seen: int = 0, holders=None, liq=None, mcap=None) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id,
        chain="solana",
        address=asset_id.rsplit(":", maxsplit=1)[-1],
        first_seen_at_ms=first_seen,
        holders=holders,
        liquidity_usd=liq,
        market_cap_usd=mcap,
        volume_24h_usd=None,
        observed_at_ms=None,
    )


def test_pick_in_db_winner_top_passes_threshold() -> None:
    candidates = (
        _c("a", holders=52267, liq=3_100_000.0, mcap=51_000_000.0, first_seen=1),
        _c("b", holders=134, liq=22_883.0, mcap=94_741_531.0, first_seen=2),
        _c("c", holders=151, liq=25_896.0, mcap=61_445_341.0, first_seen=3),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome == WinnerOutcome(
        winner_id="a",
        loser_ids=("b", "c"),
        reason="top1 holders=52267 liq=3100000.0 mcap=51000000.0 ≥ thresholds",
        needs_external=False,
    )


def test_pick_in_db_winner_top_fails_threshold_requests_external() -> None:
    candidates = (
        _c("a", holders=100, liq=10_000.0, mcap=1.0, first_seen=1),
        _c("b", holders=50, liq=50_000.0, mcap=1.0, first_seen=2),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id is None
    assert outcome.needs_external is True
    assert set(outcome.loser_ids) == set()  # losers decided only after external step


def test_pick_in_db_winner_tiebreaks_on_first_seen_ascending() -> None:
    candidates = (
        _c("newer", holders=1000, liq=10_000.0, mcap=1.0, first_seen=200),
        _c("older", holders=1000, liq=10_000.0, mcap=1.0, first_seen=100),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id == "older"
    assert outcome.loser_ids == ("newer",)


def test_pick_in_db_winner_handles_null_metrics_as_zero() -> None:
    candidates = (
        _c("a", holders=None, liq=None, mcap=None, first_seen=1),
        _c("b", holders=300, liq=10_000.0, mcap=1.0, first_seen=2),
    )

    outcome = pick_in_db_winner(candidates, threshold_holders=200, threshold_liq_usd=5000.0)

    assert outcome.winner_id == "b"
    assert outcome.loser_ids == ("a",)
