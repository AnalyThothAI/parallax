from __future__ import annotations

import pytest

from parallax.app.runtime.worker_manifest import worker_names
from parallax.app.runtime.worker_status import effective_worker_status, manifest_worker_statuses


def test_manifest_worker_statuses_rejects_unknown_worker_entries() -> None:
    with pytest.raises(ValueError, match="worker_status_manifest_mismatch"):
        manifest_worker_statuses({"legacy_worker": {"enabled": True}})


def test_manifest_worker_statuses_requires_complete_canonical_inventory() -> None:
    statuses = manifest_worker_statuses(_all_worker_statuses())

    assert tuple(statuses) == worker_names()
    assert all(status["effective_status"] == "stopped" for status in statuses.values())


def test_manifest_worker_statuses_rejects_missing_worker() -> None:
    payload = _all_worker_statuses()
    payload.pop(worker_names()[0])

    with pytest.raises(ValueError, match="worker_status_manifest_mismatch"):
        manifest_worker_statuses(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda status: status.pop("last_error"),
        lambda status: status.update({"legacy_queue_depth": 0}),
    ],
)
def test_manifest_worker_statuses_rejects_partial_or_unknown_fields(mutate) -> None:
    payload = _all_worker_statuses()
    mutate(payload[worker_names()[0]])

    with pytest.raises(ValueError, match="worker_status_fields_mismatch"):
        manifest_worker_statuses(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"effective_status": "disabled"}, "disabled"),
        ({"effective_status": "running"}, "running"),
        ({"effective_status": "stopped"}, "stopped"),
        ({"effective_status": "failed"}, "failed"),
        ({"effective_status": "degraded"}, "degraded"),
        ({"effective_status": "unavailable"}, "unavailable"),
    ],
)
def test_effective_worker_status(payload: dict[str, object], expected: str) -> None:
    assert effective_worker_status(payload) == expected


@pytest.mark.parametrize("payload", [{}, {"enabled": True}, {"effective_status": "legacy"}])
def test_effective_worker_status_rejects_incomplete_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="worker_effective_status_required"):
        effective_worker_status(payload)


def _all_worker_statuses() -> dict[str, dict[str, object]]:
    return {name: _worker_status() for name in worker_names()}


def _worker_status() -> dict[str, object]:
    return {
        "enabled": True,
        "running": False,
        "effective_status": "stopped",
        "unavailable_reason": None,
        "last_started_at_ms": None,
        "last_finished_at_ms": None,
        "last_result": None,
        "last_error": None,
        "iteration_duration_p99_ms": None,
    }
