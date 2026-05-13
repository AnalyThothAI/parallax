from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.runtime import anchor_price_worker as module


def test_anchor_price_worker_notifies_market_observation_targets_when_written(monkeypatch):
    wake_bus = FakeWakeBus()

    monkeypatch.setattr(
        module,
        "observe_anchor_prices",
        lambda **_: {
            "anchor_observations_written": 2,
            "written_targets": [
                {"target_type": "Asset", "target_id": "asset-1"},
                {"target_type": "CexToken", "target_id": "cex-token-1"},
            ],
        },
    )
    worker = module.AnchorPriceWorker(
        repository_session=FakeSession,
        wake_bus=wake_bus,
    )

    result = worker.run_once(now_ms=1_700_000_000_000)

    assert result["anchor_observations_written"] == 2
    assert wake_bus.market_notifications == [
        {"target_type": "Asset", "target_id": "asset-1"},
        {"target_type": "CexToken", "target_id": "cex-token-1"},
    ]


def test_anchor_price_worker_does_not_notify_without_new_observations(monkeypatch):
    wake_bus = FakeWakeBus()

    monkeypatch.setattr(
        module,
        "observe_anchor_prices",
        lambda **_: {"anchor_observations_written": 0},
    )
    worker = module.AnchorPriceWorker(
        repository_session=FakeSession,
        wake_bus=wake_bus,
    )

    worker.run_once(now_ms=1_700_000_000_000)

    assert wake_bus.market_notifications == []


class FakeSession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeWakeBus:
    def __init__(self) -> None:
        self.market_notifications: list[dict[str, str]] = []

    def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None:
        self.market_notifications.append({"target_type": target_type, "target_id": target_id})
