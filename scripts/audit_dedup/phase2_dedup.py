from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scripts.audit_dedup.candidates import AssetCandidate, fetch_duplicate_groups
from scripts.audit_dedup.report import GroupDecision, Phase2Summary
from scripts.audit_dedup.winner import pick_in_db_winner


@dataclass(frozen=True, slots=True)
class Phase2Config:
    threshold_holders: int
    threshold_liq_usd: float
    chain_filter: str | None = None
    symbol_filter: str | None = None
    use_external: bool = True


class ArbiterResultProto(Protocol):
    winner_id: str | None
    source: str
    external_address: str | None


class ArbiterProto(Protocol):
    def arbitrate(
        self, *, chain: str, symbol: str, candidates: tuple[AssetCandidate, ...]
    ) -> ArbiterResultProto: ...


class _NullArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        from scripts.audit_dedup.external_arbiter import ExternalArbiterResult

        return ExternalArbiterResult(winner_id=None, source="skipped_no_external", external_address=None)


def _delete_assets(conn, asset_ids: list[str]) -> None:
    if not asset_ids:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assets WHERE asset_id = ANY(%s)", (asset_ids,))


def run_phase2(
    conn,
    *,
    config: Phase2Config,
    external_arbiter: ArbiterProto,
    apply: bool,
) -> Phase2Summary:
    arbiter = external_arbiter if config.use_external else _NullArbiter()

    groups = fetch_duplicate_groups(conn)
    if config.chain_filter:
        groups = [g for g in groups if g.chain == config.chain_filter]
    if config.symbol_filter:
        groups = [g for g in groups if g.symbol == config.symbol_filter]

    decisions: list[GroupDecision] = []
    in_db = 0
    ext_total = 0
    ext_okx = 0
    ext_cg = 0
    no_real = 0
    kept = 0
    dropped = 0

    drop_set: list[str] = []

    for group in groups:
        winner_outcome = pick_in_db_winner(
            group.candidates,
            threshold_holders=config.threshold_holders,
            threshold_liq_usd=config.threshold_liq_usd,
        )
        if not winner_outcome.needs_external and winner_outcome.winner_id is not None:
            in_db += 1
            decisions.append(
                GroupDecision(
                    group=group,
                    winner_id=winner_outcome.winner_id,
                    loser_ids=winner_outcome.loser_ids,
                    source="in_db",
                    external_address=None,
                    reason=winner_outcome.reason,
                )
            )
            kept += 1
            dropped += len(winner_outcome.loser_ids)
            drop_set.extend(winner_outcome.loser_ids)
            continue

        result = arbiter.arbitrate(chain=group.chain, symbol=group.symbol, candidates=group.candidates)
        if result.winner_id is not None:
            ext_total += 1
            if result.source == "okx_dex":
                ext_okx += 1
            elif result.source == "coingecko":
                ext_cg += 1
            losers = tuple(c.asset_id for c in group.candidates if c.asset_id != result.winner_id)
            decisions.append(
                GroupDecision(
                    group=group,
                    winner_id=result.winner_id,
                    loser_ids=losers,
                    source=result.source,
                    external_address=result.external_address,
                    reason=f"external arbitration via {result.source} matched {result.external_address}",
                )
            )
            kept += 1
            dropped += len(losers)
            drop_set.extend(losers)
        else:
            no_real += 1
            losers = tuple(c.asset_id for c in group.candidates)
            decisions.append(
                GroupDecision(
                    group=group,
                    winner_id=None,
                    loser_ids=losers,
                    source=result.source,
                    external_address=None,
                    reason=f"top1 below threshold; external {result.source}",
                )
            )
            dropped += len(losers)
            drop_set.extend(losers)

    if apply:
        _delete_assets(conn, drop_set)
        conn.commit()

    return Phase2Summary(
        groups_processed=len(groups),
        in_db_winners=in_db,
        external_winners=ext_total,
        external_okx_hits=ext_okx,
        external_cg_hits=ext_cg,
        no_real_token_groups=no_real,
        assets_kept=kept,
        assets_dropped=dropped,
        decisions=tuple(decisions),
    )
