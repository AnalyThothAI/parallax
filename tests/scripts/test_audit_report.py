from __future__ import annotations

from scripts.audit_dedup.candidates import AssetCandidate, DuplicateGroup
from scripts.audit_dedup.report import (
    GroupDecision,
    Phase1Result,
    Phase2Summary,
    render_markdown_report,
)


def _c(asset_id: str, *, holders=None, liq=None, mcap=None) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id, chain="solana", address=asset_id.rsplit(":", maxsplit=1)[-1],
        first_seen_at_ms=0, holders=holders, liquidity_usd=liq, market_cap_usd=mcap,
        volume_24h_usd=None, observed_at_ms=None,
    )


def test_report_renders_phase2_groups_with_keep_and_drop() -> None:
    group = DuplicateGroup(
        chain="solana", symbol="TROLL",
        candidates=(
            _c("asset:a", holders=52267, liq=3_100_000.0, mcap=51_000_000.0),
            _c("asset:b", holders=134, liq=22_883.0, mcap=94_741_531.0),
        ),
    )
    decision = GroupDecision(
        group=group, winner_id="asset:a", loser_ids=("asset:b",),
        source="in_db", external_address=None,
        reason="top1 holders=52267 liq=3100000.0 mcap=51000000.0 ≥ thresholds",
    )

    phase2 = Phase2Summary(
        groups_processed=1, in_db_winners=1, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=0,
        assets_kept=1, assets_dropped=1, decisions=(decision,),
    )

    markdown = render_markdown_report(
        mode="dry-run", phase1=Phase1Result.empty(), phase2=phase2,
    )

    assert "## solana / TROLL" in markdown
    assert "KEEP" in markdown and "asset:a" in markdown
    assert "DROP" in markdown and "asset:b" in markdown
    assert "Total assets DROPPED: 1" in markdown


def test_report_renders_group_drop_block() -> None:
    group = DuplicateGroup(
        chain="bsc", symbol="TROLL",
        candidates=(_c("asset:bsc:1", holders=972, liq=15_000.0),),
    )
    decision = GroupDecision(
        group=group, winner_id=None, loser_ids=("asset:bsc:1",),
        source="none", external_address=None,
        reason="top1 below threshold; OKX no hit; CoinGecko no hit",
    )
    phase2 = Phase2Summary(
        groups_processed=1, in_db_winners=0, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=1,
        assets_kept=0, assets_dropped=1, decisions=(decision,),
    )

    markdown = render_markdown_report(mode="dry-run", phase1=Phase1Result.empty(), phase2=phase2)

    assert "GROUP DROPPED" in markdown
    assert "No-real-token groups: 1" in markdown


def test_report_renders_phase1_merge_and_rename() -> None:
    phase1 = Phase1Result(
        venue_rows_normalized=149, assets_merged=2, assets_renamed=147,
        orphan_chains={"evm": 1, "evm_unknown": 2}, conflicts=(),
    )
    phase2 = Phase2Summary(
        groups_processed=0, in_db_winners=0, external_winners=0,
        external_okx_hits=0, external_cg_hits=0, no_real_token_groups=0,
        assets_kept=0, assets_dropped=0, decisions=(),
    )

    markdown = render_markdown_report(mode="apply", phase1=phase1, phase2=phase2)

    assert "Phase 1" in markdown
    assert "merged (same-address dup): 2" in markdown
    assert "renamed (no conflict): 147" in markdown
    assert "evm | 1" in markdown
    assert "evm_unknown | 2" in markdown
