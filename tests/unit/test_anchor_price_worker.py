from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.runtime import anchor_price_worker as module


def test_anchor_price_worker_wakes_projection_when_observations_are_written(monkeypatch):
    wakes: list[str] = []

    monkeypatch.setattr(
        module,
        "observe_anchor_prices",
        lambda **_: {"anchor_observations_written": 2},
    )
    worker = module.AnchorPriceWorker(
        repository_session=FakeSession,
        on_observations_written=lambda: wakes.append("wake"),
    )

    result = worker.run_once(now_ms=1_700_000_000_000)

    assert result["anchor_observations_written"] == 2
    assert wakes == ["wake"]


def test_anchor_price_worker_does_not_wake_projection_without_new_observations(monkeypatch):
    wakes: list[str] = []

    monkeypatch.setattr(
        module,
        "observe_anchor_prices",
        lambda **_: {"anchor_observations_written": 0},
    )
    worker = module.AnchorPriceWorker(
        repository_session=FakeSession,
        on_observations_written=lambda: wakes.append("wake"),
    )

    worker.run_once(now_ms=1_700_000_000_000)

    assert wakes == []


class FakeSession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False
