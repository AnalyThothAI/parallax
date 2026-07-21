from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.app.surfaces.api.routes_cex import _public_board, _public_row


def test_cex_radar_board_public_payload_requires_repository_rows_contract() -> None:
    with pytest.raises(ValueError, match="cex_oi_radar_board_rows_required"):
        _public_board({"publication": None})


def test_cex_radar_board_public_row_requires_score_components_json() -> None:
    with pytest.raises(ValueError, match="cex_oi_radar_score_components_required"):
        _public_row({"target_id": "binance:BTCUSDT"})


def test_cex_radar_board_public_row_rejects_invalid_score_components_json() -> None:
    with pytest.raises(ValueError, match="cex_oi_radar_score_components_invalid"):
        _public_row({"target_id": "binance:BTCUSDT", "score_components_json": []})


def test_cex_detail_api_rejects_partial_target_identity_before_repository_call() -> None:
    snapshots = FakeCexDetailSnapshots()
    app = _app(snapshots)

    with TestClient(app) as client:
        response = client.get(
            "/api/cex/detail",
            params={"target_type": "CexToken"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cex_detail_query", "field": "target_id"}
    assert snapshots.calls == []


def test_cex_detail_api_rejects_missing_query_identity_before_repository_call() -> None:
    snapshots = FakeCexDetailSnapshots()
    app = _app(snapshots)

    with TestClient(app) as client:
        response = client.get(
            "/api/cex/detail",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cex_detail_query", "field": "query"}
    assert snapshots.calls == []


def test_cex_detail_api_rejects_blank_market_exchange_before_repository_call() -> None:
    snapshots = FakeCexDetailSnapshots()
    app = _app(snapshots)

    with TestClient(app) as client:
        response = client.get(
            "/api/cex/detail",
            params={"symbol": "BTCUSDT", "exchange": " "},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cex_detail_query", "field": "exchange"}
    assert snapshots.calls == []


def test_cex_detail_api_rejects_ambiguous_target_and_market_query_before_repository_call() -> None:
    snapshots = FakeCexDetailSnapshots()
    app = _app(snapshots)

    with TestClient(app) as client:
        response = client.get(
            "/api/cex/detail",
            params={
                "target_type": "CexToken",
                "target_id": "cex_token:ETH",
                "symbol": "BTCUSDT",
                "exchange": "binance",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cex_detail_query", "field": "query"}
    assert snapshots.calls == []


class FakeCexDetailSnapshots:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def latest_snapshot(self, *, target_type: str, target_id: str) -> dict[str, object]:
        self.calls.append({"method": "latest_snapshot", "target_type": target_type, "target_id": target_id})
        return {"target_type": target_type, "target_id": target_id}

    def latest_snapshot_by_market(self, *, exchange: str, native_market_id: str) -> dict[str, object]:
        self.calls.append(
            {
                "method": "latest_snapshot_by_market",
                "exchange": exchange,
                "native_market_id": native_market_id,
            }
        )
        return {"exchange": exchange, "native_market_id": native_market_id}


class FakeRepositoryContext:
    def __init__(self, snapshots: FakeCexDetailSnapshots) -> None:
        self.cex_detail_snapshots = snapshots

    def __enter__(self) -> FakeRepositoryContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(self, snapshots: FakeCexDetailSnapshots) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self._snapshots = snapshots

    def repositories(self) -> FakeRepositoryContext:
        return FakeRepositoryContext(self._snapshots)


def _app(snapshots: FakeCexDetailSnapshots) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(snapshots)
    return app
