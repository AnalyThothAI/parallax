from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.providers import DexTokenProfile
from gmgn_twitter_intel.domains.asset_market.runtime import asset_profile_refresh_worker as module


def test_asset_profile_refresh_worker_run_once_records_result_and_uses_session_and_provider(monkeypatch):
    calls: list[dict] = []
    provider = object()
    row = {"asset_id": "asset-1", "chain_id": "solana", "address": "abc"}
    profile = DexTokenProfile(
        chain_id="solana",
        address="abc",
        symbol="ABC",
        name="ABC",
        logo_url=None,
        banner_url=None,
        website=None,
        twitter_username=None,
        telegram=None,
        gmgn_url=None,
        geckoterminal_url=None,
        description=None,
        raw={},
    )

    def fake_fetch_asset_profile(**kwargs):
        calls.append(kwargs)
        return profile

    monkeypatch.setattr(module, "select_due_asset_profile_rows", lambda **_: [row])
    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_ready_asset_profile", lambda **_: None)
    db = FakeDB()
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(batch_size=7),
        db=db,
        telemetry=object(),
        dex_profile_market=provider,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 1
    assert result.notes["result"]["selected"] == 1
    assert result.notes["result"]["ready"] == 1
    assert calls == [
        {
            "dex_profile_market": provider,
            "row": row,
        }
    ]
    assert db.session_names == ["asset_profile_refresh", "asset_profile_refresh"]


def test_asset_profile_refresh_worker_close_does_not_close_shared_profile_provider():
    provider = ClosableProvider()
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=object(),
        dex_profile_market=provider,
    )

    asyncio.run(worker.on_close())

    assert provider.closed is False


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "batch_size": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.repos = object()
        self.session_names: list[str] = []

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


class ClosableProvider:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True
