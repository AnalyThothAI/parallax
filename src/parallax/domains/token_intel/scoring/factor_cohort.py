"""Cohort membership for cross-sectional factor normalization."""

from __future__ import annotations

COHORT_DEFINITION_VERSION = "factor_cohort_v2"

STABLECOIN_SYMBOLS: frozenset[str] = frozenset(
    {
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "TUSD",
        "USDD",
        "USDP",
        "GUSD",
        "PYUSD",
        "USDE",
        "FRAX",
        "LUSD",
        "BUSD",
    }
)


def is_active_cohort_member(
    *,
    target_id: str | None,
    symbol: str | None,
    high_confidence_mention_count: int,
    kol_mention_count: int,
    was_first_seen_global_24h: bool,
) -> bool:
    if not str(target_id or "").strip():
        return False
    if symbol and symbol.strip().upper() in STABLECOIN_SYMBOLS:
        return False
    if high_confidence_mention_count >= 2:
        return True
    if kol_mention_count > 0:
        return True
    return bool(was_first_seen_global_24h)
