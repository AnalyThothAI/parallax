from __future__ import annotations

import time
from typing import Any

from fastapi import Request

from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiUnauthorized


def _runtime(request: Request) -> Any:
    return request.app.state.service


def _authenticated_runtime(request: Request) -> Any:
    runtime = _runtime(request)
    if not runtime.settings.ws_token or _request_token(request) != runtime.settings.ws_token:
        raise ApiUnauthorized()
    return runtime


def _request_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    token = request.query_params.get("token")
    return token.strip() if token else None


def _worker_running(runtime: Any, worker_name: str) -> bool:
    scheduler = getattr(runtime, "scheduler", None)
    if scheduler is None:
        return False
    task = getattr(scheduler, "tasks", {}).get(worker_name)
    if task is not None:
        return not task.done()
    status_payload = getattr(scheduler, "status_payload", None)
    if status_payload is None:
        return False
    try:
        payload = status_payload()
    except Exception:
        return False
    return bool(payload.get(worker_name, {}).get("running"))


def _worker_object(runtime: Any, worker_name: str) -> Any | None:
    workers = getattr(runtime, "workers", {})
    worker = workers.get(worker_name)
    if worker is None:
        return None
    status_payload = getattr(worker, "status_payload", None)
    if status_payload is not None:
        try:
            if not status_payload().get("enabled", False):
                return None
        except Exception:
            return None
    return getattr(worker, "worker", worker)


def _now_ms() -> int:
    return int(time.time() * 1000)
