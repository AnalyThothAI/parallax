import asyncio

from starlette.websockets import WebSocketState

from gmgn_twitter_intel.app.surfaces.api.ws import _close_if_connected


def test_close_if_connected_suppresses_uvicorn_protocol_close_race() -> None:
    websocket = _RaceyCloseWebSocket()

    asyncio.run(_close_if_connected(websocket, code=1008, reason="authentication required"))

    assert websocket.close_args == {
        "code": 1008,
        "reason": "authentication required",
    }


class _RaceyCloseWebSocket:
    client_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.close_args: dict[str, object] | None = None

    async def close(self, *, code: int, reason: str) -> None:
        self.close_args = {"code": code, "reason": reason}
        raise AttributeError("'WebSocketProtocol' object has no attribute 'transfer_data_task'")
