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


def _public_board(board: dict) -> dict:
    run = board.get("run")
    return {
        "venue": "binance",
        "quote_symbol": "USDT",
        "contract_type": "PERPETUAL",
        "run": dict(run) if run else None,
        "rows": [_public_row(row) for row in board.get("rows") or []],
    }


def _public_row(row: dict) -> dict:
    payload = dict(row)
    components = payload.pop("score_components_json", None)
    payload["score_components"] = components or {}
    return payload
