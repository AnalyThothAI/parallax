from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.runtime import anchor_price_worker as module


def test_anchor_price_worker_notifies_market_observation_targets_when_written(monkeypatch):
    wake_bus = FakeWakeBus()
    db = FakeDB()

    rows = [{"target_type": "Asset", "target_id": "asset-1"}]
    result_payload = {
        "anchor_observations_written": 2,
        "written_targets": [
            {"target_type": "Asset", "target_id": "asset-1"},
            {"target_type": "CexToken", "target_id": "cex-token-1"},
        ],
    }
    monkeypatch.setattr(module, "select_pending_anchor_price_rows", lambda **_: rows)
    monkeypatch.setattr(module, "anchor_price_empty_result", lambda **_: {"rows_selected": 1})
    monkeypatch.setattr(module, "fetch_anchor_price_quotes", lambda **_: ({}, {}))
    monkeypatch.setattr(module, "write_anchor_price_observations", lambda **_: result_payload)
    worker = module.AnchorPriceWorker(
        name="anchor_price",
        settings=worker_settings(batch_size=7),
        db=db,
        telemetry=object(),
        wake_bus=wake_bus,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert isinstance(result, WorkerResult)
    assert result.processed == 2
    assert result.notes["result"]["anchor_observations_written"] == 2
    assert db.session_names == ["anchor_price", "anchor_price"]
    assert wake_bus.market_notifications == [
        {"target_type": "Asset", "target_id": "asset-1"},
        {"target_type": "CexToken", "target_id": "cex-token-1"},
    ]


def test_anchor_price_worker_does_not_notify_without_new_observations(monkeypatch):
    wake_bus = FakeWakeBus()
    db = FakeDB()

    monkeypatch.setattr(module, "select_pending_anchor_price_rows", lambda **_: [])
    monkeypatch.setattr(module, "anchor_price_empty_result", lambda **_: {"rows_selected": 0})
    monkeypatch.setattr(module, "fetch_anchor_price_quotes", lambda **_: ({}, {}))
    monkeypatch.setattr(module, "write_anchor_price_observations", lambda **_: {"anchor_observations_written": 0})
    worker = module.AnchorPriceWorker(
        name="anchor_price",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        wake_bus=wake_bus,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 0
    assert wake_bus.market_notifications == []


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "timeout_seconds": 120.0,
        "batch_size": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.session_names: list[str] = []
        self.repos = object()

    def worker_session(self, name: str):
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeWakeBus:
    def __init__(self) -> None:
        self.market_notifications: list[dict[str, str]] = []

    def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None:
        self.market_notifications.append({"target_type": target_type, "target_id": target_id})
