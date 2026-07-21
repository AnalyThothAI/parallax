from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.surfaces.api.dependencies import _worker_object


@pytest.mark.parametrize(
    ("worker", "error_type", "message"),
    [
        (
            SimpleNamespace(status_payload=lambda: (_ for _ in ()).throw(RuntimeError("worker status failed"))),
            RuntimeError,
            "worker status failed",
        ),
        (
            SimpleNamespace(status_payload=lambda: ["not", "a", "dict"]),
            TypeError,
            "api_worker_status_payload_must_be_dict",
        ),
    ],
)
def test_worker_object_requires_formal_worker_status_payload_contract(
    worker: Any,
    error_type: type[BaseException],
    message: str,
) -> None:
    runtime = SimpleNamespace(scheduler=SimpleNamespace(workers={"live_price_gateway": worker}))

    with pytest.raises(error_type, match=message):
        _worker_object(runtime, "live_price_gateway")


def test_worker_object_returns_none_for_formal_disabled_worker() -> None:
    worker = SimpleNamespace(status_payload=lambda: {"enabled": False, "running": False})
    runtime = SimpleNamespace(scheduler=SimpleNamespace(workers={"live_price_gateway": worker}))

    assert _worker_object(runtime, "live_price_gateway") is None


def test_worker_object_returns_direct_worker_for_formal_running_worker() -> None:
    worker = SimpleNamespace(status_payload=lambda: {"enabled": True, "running": True})
    runtime = SimpleNamespace(scheduler=SimpleNamespace(workers={"live_price_gateway": worker}))

    assert _worker_object(runtime, "live_price_gateway") is worker
