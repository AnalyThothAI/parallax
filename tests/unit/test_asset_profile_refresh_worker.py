from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.providers import (
    DexProfileSource,
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
)
from gmgn_twitter_intel.domains.asset_market.runtime import asset_profile_refresh_worker as module


def test_asset_profile_refresh_worker_run_once_records_result_and_uses_session_and_provider(monkeypatch):
    calls: list[dict] = []
    provider = object()
    source = DexProfileSource(provider="gmgn_dex_profile", market=provider)
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
        dex_profile_sources=(source,),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 1
    assert result.notes["result"]["selected"] == 1
    assert result.notes["result"]["ready"] == 1
    assert calls == [
        {
            "profile_source": source,
            "row": row,
        }
    ]
    assert db.session_names == ["asset_profile_refresh", "asset_profile_refresh"]


def test_asset_profile_refresh_worker_reports_provider_block_without_writing_token_error(monkeypatch):
    row = {"asset_id": "asset-1", "chain_id": "solana", "address": "abc"}
    writes: list[str] = []

    def fake_fetch_asset_profile(**kwargs):
        raise DexProviderTemporarilyUnavailable("GET /v1/token/info blocked by Cloudflare challenge HTTP 403")

    monkeypatch.setattr(module, "select_due_asset_profile_rows", lambda **_: [row])
    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_error_asset_profile", lambda **_: writes.append("error"))
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=object(),
        dex_profile_sources=(DexProfileSource(provider="gmgn_dex_profile", market=object()),),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.failed == 1
    assert result.notes["result"]["provider_blocked"] == 1
    assert result.notes["result"]["error"] == 0
    assert writes == []


def test_asset_profile_refresh_worker_close_does_not_close_shared_profile_provider():
    provider = ClosableProvider()
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=object(),
        dex_profile_sources=(DexProfileSource(provider="gmgn_dex_profile", market=provider),),
    )

    asyncio.run(worker.on_close())

    assert provider.closed is False


def test_asset_profile_refresh_worker_continues_to_binance_when_gmgn_is_blocked(monkeypatch):
    gmgn_provider = object()
    binance_provider = object()
    gmgn_source = DexProfileSource(provider="gmgn_dex_profile", market=gmgn_provider)
    binance_source = DexProfileSource(provider="binance_web3_profile", market=binance_provider)
    row = {"asset_id": "asset-1", "chain_id": "eip155:56", "address": "0xabc"}
    calls: list[tuple[str, str]] = []

    def fake_select_due_asset_profile_rows(**kwargs):
        calls.append(("select", kwargs["provider"]))
        return [row]

    def fake_fetch_asset_profile(**kwargs):
        provider = kwargs["profile_source"].provider
        calls.append(("fetch", provider))
        if provider == "gmgn_dex_profile":
            raise DexProviderTemporarilyUnavailable("gmgn blocked")
        return DexTokenProfile(
            chain_id="eip155:56",
            address="0xabc",
            symbol="ABC",
            name=None,
            logo_url="https://binance.example/abc.png",
            banner_url=None,
            website=None,
            twitter_username=None,
            telegram=None,
            gmgn_url=None,
            geckoterminal_url=None,
            description=None,
            raw={},
        )

    monkeypatch.setattr(module, "select_due_asset_profile_rows", fake_select_due_asset_profile_rows)
    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_ready_asset_profile", lambda **_: None)
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=object(),
        dex_profile_sources=(gmgn_source, binance_source),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 1
    assert result.failed == 1
    assert result.notes["result"]["ready"] == 1
    assert result.notes["result"]["provider_blocked"] == 1
    assert result.notes["result"]["sources"]["gmgn_dex_profile"]["provider_blocked"] == 1
    assert result.notes["result"]["sources"]["binance_web3_profile"]["ready"] == 1
    assert calls == [
        ("select", "gmgn_dex_profile"),
        ("fetch", "gmgn_dex_profile"),
        ("select", "binance_web3_profile"),
        ("fetch", "binance_web3_profile"),
    ]


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
