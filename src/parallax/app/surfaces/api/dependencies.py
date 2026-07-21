from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from fastapi import Request

from parallax.app.runtime.worker_manifest import require_worker_manifest
from parallax.app.runtime.worker_status import effective_worker_status
from parallax.app.surfaces.api.exceptions import ApiUnauthorized

_INACTIVE_WORKER_STATUSES = {"disabled", "intentionally_not_started", "unavailable"}


def _runtime(request: Request) -> Any:
    return request.app.state.service


def _authenticated_runtime(request: Request, *, allow_query_token: bool = True) -> Any:
    runtime = _runtime(request)
    request_token = _request_token(request, allow_query_token=allow_query_token)
    if not runtime.settings.ws_token or request_token != runtime.settings.ws_token:
        raise ApiUnauthorized()
    return runtime


def _request_token(request: Request, *, allow_query_token: bool = True) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    if not allow_query_token:
        return None
    token = request.query_params.get("token")
    return token.strip() if token else None


def _worker_object(runtime: Any, worker_name: str) -> Any | None:
    require_worker_manifest(worker_name)
    scheduler = runtime.scheduler
    worker = scheduler.workers[worker_name]
    payload = _worker_status_payload(worker)
    if effective_worker_status(payload) in _INACTIVE_WORKER_STATUSES:
        return None
    return worker


def _worker_status_payload(worker: Any) -> dict[str, Any]:
    payload = worker.status_payload()
    if not isinstance(payload, Mapping):
        raise TypeError("api_worker_status_payload_must_be_dict")
    return dict(payload)


def _now_ms() -> int:
    return int(time.time() * 1000)
