from __future__ import annotations

from dataclasses import dataclass

from scripts.audit_dedup.candidates import AssetCandidate


@dataclass(frozen=True, slots=True)
class WinnerOutcome:
    winner_id: str | None
    loser_ids: tuple[str, ...]
    reason: str
    needs_external: bool


def _sort_key(c: AssetCandidate) -> tuple[int, float, float, int]:
    return (
        -(c.holders or 0),
        -(c.liquidity_usd or 0.0),
        -(c.market_cap_usd or 0.0),
        c.first_seen_at_ms,
    )


def pick_in_db_winner(
    candidates: tuple[AssetCandidate, ...],
    *,
    threshold_holders: int,
    threshold_liq_usd: float,
) -> WinnerOutcome:
    if not candidates:
        return WinnerOutcome(winner_id=None, loser_ids=(), reason="empty group", needs_external=False)

    ordered = sorted(candidates, key=_sort_key)
    top = ordered[0]
    passes = (top.holders or 0) >= threshold_holders and (top.liquidity_usd or 0.0) >= threshold_liq_usd

    if passes:
        winner_id = top.asset_id
        losers = tuple(c.asset_id for c in candidates if c.asset_id != winner_id)
        return WinnerOutcome(
            winner_id=top.asset_id,
            loser_ids=losers,
            reason=(
                f"top1 holders={top.holders} liq={top.liquidity_usd} mcap={top.market_cap_usd} "
                "≥ thresholds"
            ),
            needs_external=False,
        )

    return WinnerOutcome(
        winner_id=None,
        loser_ids=(),
        reason=(
            f"top1 holders={top.holders} liq={top.liquidity_usd} below threshold "
            f"(holders≥{threshold_holders}, liq≥{threshold_liq_usd}); needs external arbitration"
        ),
        needs_external=True,
    )
