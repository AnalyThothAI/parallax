from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AssetCandidate:
    asset_id: str
    chain: str
    address: str
    first_seen_at_ms: int
    holders: int | None
    liquidity_usd: float | None
    market_cap_usd: float | None
    volume_24h_usd: float | None
    observed_at_ms: int | None


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    chain: str
    symbol: str
    candidates: tuple[AssetCandidate, ...] = field(default_factory=tuple)


def fetch_duplicate_groups(conn) -> list[DuplicateGroup]:
    """Return (chain, symbol) groups with >= 2 distinct assets.

    Joins assets ⨝ asset_venues, attaches latest asset_market_snapshots per asset.
    """
    sql = """
    WITH latest_snap AS (
        SELECT DISTINCT ON (asset_id) asset_id, observed_at_ms,
               holders, liquidity_usd, market_cap_usd, volume_24h_usd
        FROM asset_market_snapshots
        ORDER BY asset_id, observed_at_ms DESC
    ),
    base AS (
        SELECT
            av.chain,
            a.canonical_symbol AS symbol,
            a.asset_id,
            av.address,
            a.first_seen_at_ms,
            ls.holders, ls.liquidity_usd, ls.market_cap_usd, ls.volume_24h_usd,
            ls.observed_at_ms
        FROM assets a
        JOIN asset_venues av ON av.asset_id = a.asset_id
        LEFT JOIN latest_snap ls ON ls.asset_id = a.asset_id
        WHERE av.chain IS NOT NULL
          AND av.is_active = true
          AND a.canonical_symbol IS NOT NULL
    ),
    dup AS (
        SELECT chain, symbol
        FROM base
        GROUP BY chain, symbol
        HAVING COUNT(DISTINCT asset_id) > 1
    )
    SELECT b.chain, b.symbol, b.asset_id, b.address, b.first_seen_at_ms,
           b.holders, b.liquidity_usd, b.market_cap_usd, b.volume_24h_usd, b.observed_at_ms
    FROM base b
    JOIN dup ON dup.chain = b.chain AND dup.symbol = b.symbol
    ORDER BY b.chain, b.symbol, b.asset_id;
    """

    grouped: dict[tuple[str, str], list[AssetCandidate]] = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            chain = row["chain"]
            symbol = row["symbol"]
            asset_id = row["asset_id"]
            address = row["address"]
            first_seen = row["first_seen_at_ms"]
            holders = row["holders"]
            liq = row["liquidity_usd"]
            mcap = row["market_cap_usd"]
            vol = row["volume_24h_usd"]
            observed = row["observed_at_ms"]
            key = (chain, symbol)
            grouped.setdefault(key, []).append(
                AssetCandidate(
                    asset_id=asset_id,
                    chain=chain,
                    address=address,
                    first_seen_at_ms=int(first_seen),
                    holders=int(holders) if holders is not None else None,
                    liquidity_usd=float(liq) if liq is not None else None,
                    market_cap_usd=float(mcap) if mcap is not None else None,
                    volume_24h_usd=float(vol) if vol is not None else None,
                    observed_at_ms=int(observed) if observed is not None else None,
                )
            )

    return [DuplicateGroup(chain=k[0], symbol=k[1], candidates=tuple(v)) for k, v in sorted(grouped.items())]
