from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api.dependencies import _authenticated_runtime
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _limit

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
    target_query = _cex_detail_target_query(target_type=target_type, target_id=target_id)
    market_query = _cex_detail_market_query(exchange=exchange, symbol=symbol)
    if target_query is not None and market_query is not None:
        raise ApiBadRequest("invalid_cex_detail_query", field="query")
    with runtime.repositories() as repos:
        if target_query is not None:
            query_target_type, query_target_id = target_query
            snapshot = repos.cex_detail_snapshots.latest_snapshot(
                target_type=query_target_type,
                target_id=query_target_id,
            )
        elif market_query is not None:
            query_exchange, query_symbol = market_query
            snapshot = repos.cex_detail_snapshots.latest_snapshot_by_market(
                exchange=query_exchange,
                native_market_id=query_symbol,
            )
        else:
            snapshot = None
    return _json({"ok": True, "data": snapshot})


def _cex_detail_target_query(*, target_type: str | None, target_id: str | None) -> tuple[str, str] | None:
    if target_type is None and target_id is None:
        return None

    query_target_type = _query_text_or_none(target_type)
    query_target_id = _query_text_or_none(target_id)
    if query_target_type is None:
        raise ApiBadRequest("invalid_cex_detail_query", field="target_type")
    if query_target_id is None:
        raise ApiBadRequest("invalid_cex_detail_query", field="target_id")
    return query_target_type, query_target_id


def _cex_detail_market_query(*, exchange: str, symbol: str | None) -> tuple[str, str] | None:
    if symbol is None:
        return None

    query_symbol = _query_text_or_none(symbol)
    if query_symbol is None:
        raise ApiBadRequest("invalid_cex_detail_query", field="symbol")

    query_exchange = _query_text_or_none(exchange)
    if query_exchange is None:
        raise ApiBadRequest("invalid_cex_detail_query", field="exchange")
    return query_exchange, query_symbol


def _query_text_or_none(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _public_board(board: dict) -> dict:
    publication = board.get("publication")
    return {
        "venue": "binance",
        "quote_symbol": "USDT",
        "contract_type": "PERPETUAL",
        "publication": dict(publication) if publication else None,
        "rows": [_public_row(row) for row in _required_board_rows(board)],
    }


def _public_row(row: Mapping[str, object]) -> dict:
    payload = dict(row)
    payload["score_components"] = _required_score_components_json(row)
    del payload["score_components_json"]
    return payload


def _required_board_rows(board: Mapping[str, object]) -> list[Mapping[str, object]]:
    if "rows" not in board or board.get("rows") is None:
        raise ValueError("cex_oi_radar_board_rows_required")
    rows = board.get("rows")
    if not isinstance(rows, list | tuple):
        raise ValueError("cex_oi_radar_board_rows_invalid")
    if not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("cex_oi_radar_board_rows_invalid")
    return list(rows)


def _required_score_components_json(row: Mapping[str, object]) -> dict[str, object]:
    if "score_components_json" not in row or row.get("score_components_json") is None:
        raise ValueError("cex_oi_radar_score_components_required")
    components = row.get("score_components_json")
    if not isinstance(components, Mapping):
        raise ValueError("cex_oi_radar_score_components_invalid")
    return dict(components)
