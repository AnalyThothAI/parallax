from __future__ import annotations

from scripts.audit_dedup.report import Phase1Result

ORPHAN_CHAINS = {"evm", "evm_unknown", "tron", "monad"}


def _eth_rows(conn) -> list[tuple[str, str, str]]:
    """Return [(asset_id, venue_id, address)] for chain='eth'."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT av.asset_id, av.venue_id, av.address
               FROM asset_venues av
               WHERE av.chain = 'eth'
               ORDER BY av.asset_id"""
        )
        return [(r["asset_id"], r["venue_id"], r["address"]) for r in cur.fetchall()]


def _ethereum_asset_for(conn, address_lower: str) -> str | None:
    """Return the existing ethereum-side asset_id for this address, if any."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT asset_id FROM asset_venues
               WHERE chain = 'ethereum' AND lower(address) = lower(%s)
               LIMIT 1""",
            (address_lower,),
        )
        row = cur.fetchone()
        return row["asset_id"] if row else None


def _orphan_chains(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT chain, COUNT(*) AS cnt FROM asset_venues
               WHERE chain = ANY(%s)
               GROUP BY chain""",
            (list(ORPHAN_CHAINS),),
        )
        return {r["chain"]: int(r["cnt"]) for r in cur.fetchall()}


_FK_TABLES_ASSET = (
    "asset_aliases",
    "asset_market_snapshots",
    "token_intent_resolutions",
    "token_intent_resolution_candidates",
    "token_radar_rows",
    "asset_signal_snapshots",
)

_FK_TABLES_VENUE = (
    ("asset_market_snapshots", "venue_id"),
    ("token_intent_resolutions", "primary_venue_id"),
    ("token_intent_resolution_candidates", "venue_id"),
    ("token_radar_rows", "primary_venue_id"),
    ("asset_signal_snapshots", "primary_venue_id"),
)


def _merge_one(conn, *, eth_asset_id: str, eth_venue_id: str, address: str) -> str:
    """Return 'merged' or 'renamed' depending on whether ethereum target existed."""
    target_asset_id = f"asset:dex:ethereum:{address.lower()}"
    target_venue_id = f"venue:dex:ethereum:{address.lower()}"
    existing = _ethereum_asset_for(conn, address)

    with conn.cursor() as cur:
        if existing is None:
            # No conflict: insert target asset + venue, then reassign + delete eth
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, display_name,
                       identity_status, confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   SELECT %s, asset_type, canonical_symbol, display_name, identity_status,
                          confidence, primary_source, first_seen_at_ms, updated_at_ms
                   FROM assets WHERE asset_id = %s""",
                (target_asset_id, eth_asset_id),
            )
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, exchange,
                       chain, address, inst_id, base_symbol, quote_symbol, inst_type, is_active,
                       confidence, source_payload_hash, created_at_ms, updated_at_ms)
                   SELECT %s, %s, venue_type, provider, exchange, 'ethereum', address, inst_id,
                          base_symbol, quote_symbol, inst_type, is_active, confidence,
                          source_payload_hash, created_at_ms, updated_at_ms
                   FROM asset_venues WHERE venue_id = %s""",
                (target_venue_id, target_asset_id, eth_venue_id),
            )
            outcome = "renamed"
        else:
            # Conflict: keep existing ethereum asset; pick older first_seen_at_ms / higher confidence
            cur.execute(
                """UPDATE assets
                   SET first_seen_at_ms = LEAST(first_seen_at_ms,
                       (SELECT first_seen_at_ms FROM assets WHERE asset_id = %s)),
                       confidence = GREATEST(confidence,
                       (SELECT confidence FROM assets WHERE asset_id = %s))
                   WHERE asset_id = %s""",
                (eth_asset_id, eth_asset_id, target_asset_id),
            )
            target_asset_id = existing
            outcome = "merged"

        # Reassign asset_id-keyed FKs
        for table in _FK_TABLES_ASSET:
            cur.execute(
                f"UPDATE {table} SET asset_id = %s WHERE asset_id = %s",
                (target_asset_id, eth_asset_id),
            )
        # Reassign venue_id-keyed FKs
        for table, col in _FK_TABLES_VENUE:
            cur.execute(
                f"UPDATE {table} SET {col} = %s WHERE {col} = %s",
                (target_venue_id, eth_venue_id),
            )

        # Drop eth venue + asset
        cur.execute("DELETE FROM asset_venues WHERE venue_id = %s", (eth_venue_id,))
        cur.execute("DELETE FROM assets WHERE asset_id = %s", (eth_asset_id,))

    return outcome


def run_phase1(conn, *, apply: bool) -> Phase1Result:
    eth_rows = _eth_rows(conn)
    if not apply:
        # Compute counts only; nothing mutated
        existing_count = sum(1 for _, _, addr in eth_rows if _ethereum_asset_for(conn, addr.lower()) is not None)
        return Phase1Result(
            venue_rows_normalized=len(eth_rows),
            assets_merged=existing_count,
            assets_renamed=len(eth_rows) - existing_count,
            orphan_chains=_orphan_chains(conn),
            conflicts=(),
        )

    merged = 0
    renamed = 0
    for asset_id, venue_id, address in eth_rows:
        outcome = _merge_one(conn, eth_asset_id=asset_id, eth_venue_id=venue_id, address=address)
        if outcome == "merged":
            merged += 1
        else:
            renamed += 1
    conn.commit()

    return Phase1Result(
        venue_rows_normalized=len(eth_rows),
        assets_merged=merged,
        assets_renamed=renamed,
        orphan_chains=_orphan_chains(conn),
        conflicts=(),
    )
