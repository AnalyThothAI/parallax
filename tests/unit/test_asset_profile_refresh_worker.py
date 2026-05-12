from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.runtime import asset_profile_refresh_worker as module


def test_asset_profile_refresh_worker_run_once_records_result_and_uses_session_and_provider(monkeypatch):
    calls: list[dict] = []
    provider = object()

    def fake_refresh_asset_profiles_once(**kwargs):
        calls.append(kwargs)
        return {"selected": 1, "ready": 1, "started_at_ms": kwargs["now_ms"]}

    monkeypatch.setattr(module, "refresh_asset_profiles_once", fake_refresh_asset_profiles_once)
    worker = module.AssetProfileRefreshWorker(
        repository_session=FakeSession,
        dex_profile_market=provider,
        limit=7,
    )

    result = worker.run_once(now_ms=1_700_000_000_000)

    assert result == {"selected": 1, "ready": 1, "started_at_ms": 1_700_000_000_000}
    assert calls == [
        {
            "repos": FakeSession.repos,
            "dex_profile_market": provider,
            "now_ms": 1_700_000_000_000,
            "limit": 7,
        }
    ]
    assert worker.last_started_at_ms == 1_700_000_000_000
    assert worker.last_run_at_ms is not None
    assert worker.last_result == result
    assert worker.last_error is None


def test_asset_profile_refresh_worker_close_closes_profile_provider():
    provider = ClosableProvider()
    worker = module.AssetProfileRefreshWorker(
        repository_session=FakeSession,
        dex_profile_market=provider,
    )

    worker.close()

    assert provider.closed is True


class FakeSession:
    repos = object()

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class ClosableProvider:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True
