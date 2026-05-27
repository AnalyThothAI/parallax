from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit

router = APIRouter(prefix="/cex")


@router.get("/radar-board")
def cex_radar_board(
    request: Request,
    limit: Annotated[int, Query()] = 50,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        board = repos.cex_oi_radar.latest_board(limit=_limit(limit, maximum=500))
    return _json({"ok": True, "data": _public_board(board)})


@router.get("/detail")
def cex_detail(
    request: Request,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[str | None, Query()] = None,
    exchange: Annotated[str, Query()] = "binance",
    symbol: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        if target_type and target_id:
            snapshot = repos.cex_detail_snapshots.latest_snapshot(target_type=target_type, target_id=target_id)
        elif symbol:
            snapshot = repos.cex_detail_snapshots.latest_snapshot_by_market(
                exchange=exchange,
                native_market_id=symbol,
            )
        else:
            snapshot = None
    return _json({"ok": True, "data": snapshot})


def _public_board(board: dict) -> dict:
    publication = board.get("publication")
    return {
        "venue": "binance",
        "quote_symbol": "USDT",
        "contract_type": "PERPETUAL",
        "publication": dict(publication) if publication else None,
        "rows": [_public_row(row) for row in board.get("rows") or []],
    }


def _public_row(row: dict) -> dict:
    payload = dict(row)
    components = payload.pop("score_components_json", None)
    payload["score_components"] = components or {}
    return payload
