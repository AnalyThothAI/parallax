from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

from scripts.audit_dedup.candidates import DuplicateGroup


@dataclass(frozen=True, slots=True)
class GroupDecision:
    group: DuplicateGroup
    winner_id: str | None
    loser_ids: tuple[str, ...]
    source: str
    external_address: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class Phase1Result:
    venue_rows_normalized: int
    assets_merged: int
    assets_renamed: int
    orphan_chains: dict[str, int]
    conflicts: tuple[str, ...]

    @classmethod
    def empty(cls) -> Phase1Result:
        return cls(0, 0, 0, {}, ())


@dataclass(frozen=True, slots=True)
class Phase2Summary:
    groups_processed: int
    in_db_winners: int
    external_winners: int
    external_okx_hits: int
    external_cg_hits: int
    no_real_token_groups: int
    assets_kept: int
    assets_dropped: int
    decisions: tuple[GroupDecision, ...]


def _fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.0f}"
    return f"{value:,}"


def render_markdown_report(*, mode: str, phase1: Phase1Result, phase2: Phase2Summary) -> str:
    buf = StringIO()
    buf.write(f"# Duplicate Token Audit Report ({mode})\n\n")

    buf.write("## Phase 1 — Chain normalization\n\n")
    buf.write(f"- venue rows normalized: {phase1.venue_rows_normalized}\n")
    buf.write(f"  - merged (same-address dup): {phase1.assets_merged}\n")
    buf.write(f"  - renamed (no conflict): {phase1.assets_renamed}\n")
    if phase1.orphan_chains:
        buf.write("- orphan chains skipped (manual review needed):\n\n")
        buf.write("  | chain | venue_count |\n  |---|---:|\n")
        for chain, count in sorted(phase1.orphan_chains.items()):
            buf.write(f"  | {chain} | {count} |\n")
    if phase1.conflicts:
        buf.write("- merge conflicts:\n")
        for c in phase1.conflicts:
            buf.write(f"  - {c}\n")
    buf.write("\n")

    buf.write("## Phase 2 — (chain, symbol) dedup\n\n")
    for decision in phase2.decisions:
        group = decision.group
        if decision.winner_id is None:
            header = f"GROUP DROPPED via {decision.source}"
        else:
            header = f"winner via {decision.source}"
        buf.write(f"### {group.chain} / {group.symbol}  ({len(group.candidates)} candidates, {header})\n\n")
        if decision.source in {"okx_dex", "coingecko", "none"}:
            buf.write(f"External arbitration: source={decision.source} address={decision.external_address}\n\n")
        buf.write("| status | asset_id | address | holders | liq_usd | mcap_usd | reason |\n")
        buf.write("|---|---|---|---:|---:|---:|---|\n")
        for c in group.candidates:
            status = "KEEP" if c.asset_id == decision.winner_id else "DROP"
            reason_cell = decision.reason if status == "KEEP" else ""
            buf.write(
                f"| {status} | {c.asset_id} | {c.address} | {_fmt(c.holders)} | "
                f"{_fmt(c.liquidity_usd)} | {_fmt(c.market_cap_usd)} | {reason_cell} |\n"
            )
        buf.write("\n")

    buf.write("## Summary\n\n")
    buf.write(f"- Groups processed: {phase2.groups_processed}\n")
    buf.write(f"- In-db winners: {phase2.in_db_winners}\n")
    buf.write(
        f"- External-arbitration winners: {phase2.external_winners} "
        f"(OKX: {phase2.external_okx_hits}, CoinGecko: {phase2.external_cg_hits})\n"
    )
    buf.write(f"- No-real-token groups: {phase2.no_real_token_groups}\n")
    buf.write(f"- Total assets KEPT: {phase2.assets_kept}\n")
    buf.write(f"- Total assets DROPPED: {phase2.assets_dropped}\n")

    return buf.getvalue()
