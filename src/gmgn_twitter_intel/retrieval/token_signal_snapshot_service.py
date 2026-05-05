from __future__ import annotations

import hashlib
from typing import Any

from ..storage.token_signal_repository import TokenSignalRepository
from .token_flow_service import TokenFlowService


class TokenSignalSnapshotService:
    def __init__(self, *, token_flow: TokenFlowService, repository: TokenSignalRepository):
        self.token_flow = token_flow
        self.repository = repository

    def freeze(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        items = self.token_flow.token_flow(window=window, scope=scope, limit=limit, now_ms=now_ms)
        counts = {
            "items_scanned": len(items),
            "snapshots_written": 0,
            "skipped_unresolved": 0,
        }
        frozen: list[dict[str, Any]] = []
        for rank, item in enumerate(items, start=1):
            identity = item.get("identity") or {}
            token_id = identity.get("token_id")
            chain = identity.get("chain")
            address = identity.get("address")
            if not token_id or not chain or not address:
                counts["skipped_unresolved"] += 1
                continue
            flow = item.get("flow") or {}
            decision_time_ms = int(flow.get("window_end_ms") or now_ms or 0)
            snapshot_id = _snapshot_id(
                token_id=str(token_id),
                window=window,
                scope=scope,
                decision_time_ms=decision_time_ms,
            )
            market = item.get("market") or {}
            snapshot = self.repository.create_snapshot(
                snapshot_id=snapshot_id,
                token_id=str(token_id),
                identity_key=str(identity.get("identity_key") or token_id),
                chain=str(chain),
                address=str(address),
                symbol=str(identity.get("symbol") or ""),
                window=window,
                scope=scope,
                decision_time_ms=decision_time_ms,
                rank=rank,
                decision=str((item.get("opportunity") or {}).get("decision") or "discard"),
                opportunity_score=int((item.get("opportunity") or {}).get("score") or 0),
                score_versions=item.get("score_versions") or {},
                component_payload={
                    "social_heat": item.get("social_heat") or {},
                    "discussion_quality": item.get("discussion_quality") or {},
                    "propagation": item.get("propagation") or {},
                    "tradeability": item.get("tradeability") or {},
                    "timing": item.get("timing") or {},
                    "opportunity": item.get("opportunity") or {},
                },
                identity=identity,
                market=market,
                flow=flow,
                timeline=item.get("timeline") or {},
                source_event_ids=(item.get("timeline") or {}).get("event_ids") or [],
                market_snapshot_ids=_market_snapshot_ids(market),
                data_health=item.get("data_health") or {},
                risks=(item.get("opportunity") or {}).get("risks") or [],
                commit=False,
            )
            counts["snapshots_written"] += 1
            frozen.append(snapshot)
        if commit:
            self.repository.conn.commit()
        counts["items"] = frozen
        return counts


def _snapshot_id(*, token_id: str, window: str, scope: str, decision_time_ms: int) -> str:
    return hashlib.sha256(
        f"token_signal_snapshot|{token_id}|{window}|{scope}|{decision_time_ms}|social_opportunity_v2".encode()
    ).hexdigest()


def _market_snapshot_ids(market: dict[str, Any]) -> list[str]:
    ids = [
        market.get("before_snapshot_id"),
        market.get("start_snapshot_id"),
        market.get("snapshot_id"),
    ]
    return list(dict.fromkeys(str(value) for value in ids if value))
