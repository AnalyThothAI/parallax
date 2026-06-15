from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.surfaces.api.dependencies import _worker_object, _worker_running


class _Task:
    def __init__(self, *, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


def test_worker_running_uses_live_scheduler_task_when_present() -> None:
    runtime = SimpleNamespace(
        scheduler=SimpleNamespace(
            tasks={"collector": _Task(done=False)},
            status_payload=lambda: (_ for _ in ()).throw(AssertionError("status should not be read")),
        )
    )

    assert _worker_running(runtime, "collector") is True


@pytest.mark.parametrize(
    ("scheduler", "error_type", "message"),
    [
        (
            SimpleNamespace(
                tasks={},
                status_payload=lambda: (_ for _ in ()).throw(RuntimeError("status failed")),
            ),
            RuntimeError,
            "status failed",
        ),
        (
            SimpleNamespace(tasks={}, status_payload=lambda: ["not", "a", "dict"]),
            TypeError,
            "api_status_payload_must_be_dict",
        ),
        (SimpleNamespace(tasks={}, status_payload=lambda: {}), KeyError, "collector"),
        (
            SimpleNamespace(tasks={}, status_payload=lambda: {"collector": ["not", "a", "dict"]}),
            TypeError,
            "api_worker_status_payload_must_be_dict",
        ),
    ],
)
def test_worker_running_requires_formal_scheduler_status_payload_contract(
    scheduler: Any,
    error_type: type[BaseException],
    message: str,
) -> None:
    runtime = SimpleNamespace(scheduler=scheduler)

    with pytest.raises(error_type, match=message):
        _worker_running(runtime, "collector")


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
