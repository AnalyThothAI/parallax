import asyncio

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from parallax.app.surfaces.api.ws import PublicWebSocketHub, _close_if_connected


def test_close_if_connected_suppresses_uvicorn_protocol_close_race() -> None:
    websocket = _RaceyCloseWebSocket()

    asyncio.run(_close_if_connected(websocket, code=1008, reason="authentication required"))

    assert websocket.close_args == {
        "code": 1008,
        "reason": "authentication required",
    }


@pytest.mark.parametrize(
    "message",
    [
        '[{"type":"auth","token":"secret"}]',
        '{"type":"auth","token":"secret","legacy":true}',
        '{"type":"auth","token":123}',
    ],
)
def test_websocket_authentication_requires_exact_message_shape(message: str) -> None:
    websocket = _AuthWebSocket(message)
    hub = PublicWebSocketHub(token="secret", repository_session=lambda: None)

    with pytest.raises(WebSocketDisconnect):
        asyncio.run(hub._authenticate(websocket))

    assert websocket.close_args == {"code": 1008, "reason": "authentication failed"}


class _RaceyCloseWebSocket:
    client_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.close_args: dict[str, object] | None = None

    async def close(self, *, code: int, reason: str) -> None:
        self.close_args = {"code": code, "reason": reason}
        raise AttributeError("'WebSocketProtocol' object has no attribute 'transfer_data_task'")


class _AuthWebSocket:
    client_state = WebSocketState.CONNECTED

    def __init__(self, message: str) -> None:
        self.message = message
        self.close_args: dict[str, object] | None = None

    async def receive_text(self) -> str:
        return self.message

    async def close(self, *, code: int, reason: str) -> None:
        self.close_args = {"code": code, "reason": reason}
