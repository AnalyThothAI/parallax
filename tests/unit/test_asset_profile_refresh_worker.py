from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from parallax.domains.asset_market.providers import (
    DexProfileSource,
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
)
from parallax.domains.asset_market.runtime import asset_profile_refresh_worker as module


def test_asset_profile_refresh_worker_run_once_records_result_and_uses_session_and_provider(monkeypatch):
    calls: list[dict] = []
    provider = object()
    source = DexProfileSource(provider="gmgn_dex_profile", market=provider)
    row = claim_row("gmgn_dex_profile")
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

    write_calls: list[dict] = []
    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_ready_asset_profile", lambda **kwargs: write_calls.append(kwargs))
    db = FakeDB(claims_by_provider={"gmgn_dex_profile": [row]})
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(batch_size=7, ready_refresh_ms=1_000),
        db=db,
        telemetry=object(),
        dex_profile_sources=(source,),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 1
    assert result.notes["result"]["selected"] == 1
    assert result.notes["result"]["claimed"] == 1
    assert result.notes["result"]["source_rows_scanned"] == 0
    assert result.notes["result"]["rows_written"] == 1
    assert result.notes["result"]["ready"] == 1
    assert calls == [
        {
            "profile_source": source,
            "row": row,
        }
    ]
    assert db.session_names == ["asset_profile_refresh", "asset_profile_refresh"]
    assert db.session_kwargs == [
        {"statement_timeout_seconds": 120.0},
        {"statement_timeout_seconds": 120.0},
    ]
    assert db.refresh_targets.claim_calls == [
        {
            "provider": "gmgn_dex_profile",
            "now_ms": 1_700_000_000_000,
            "limit": 7,
            "lease_owner": "asset_profile_refresh",
            "lease_ms": 120_000,
        }
    ]
    assert db.refresh_targets.rescheduled[0]["reason"] == "profile_ready_written"
    assert db.refresh_targets.rescheduled[0]["due_at_ms"] == 1_700_000_001_000
    assert write_calls[0]["next_refresh_at_ms"] == 1_700_000_001_000


@pytest.mark.parametrize("outcome", ("ready", "missing", "error"))
def test_asset_profile_refresh_writes_use_formal_claim_target_id(outcome: str) -> None:
    row = claim_row("gmgn_dex_profile")
    assert "asset_id" not in row
    asset_profiles = RecordingAssetProfiles()
    repos = SimpleNamespace(asset_profiles=asset_profiles)
    common = {
        "repos": repos,
        "provider": "gmgn_dex_profile",
        "row": row,
        "now_ms": 1_700_000_000_000,
        "next_refresh_at_ms": 1_700_000_001_000,
    }

    if outcome == "ready":
        module.write_ready_asset_profile(
            **common,
            profile=DexTokenProfile(
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
            ),
        )
    elif outcome == "missing":
        module.write_missing_asset_profile(**common)
    else:
        module.write_error_asset_profile(**common, exc=RuntimeError("provider failed"))

    assert asset_profiles.calls[0]["asset_id"] == row["target_id"]


def test_asset_profile_refresh_worker_uses_formal_ready_missing_and_error_refresh_policies(monkeypatch):
    now_ms = 1_700_000_000_000
    ready_row = claim_row("gmgn_dex_profile", target_id="asset-ready")
    missing_row = claim_row("gmgn_dex_profile", target_id="asset-missing")
    error_row = claim_row("gmgn_dex_profile", target_id="asset-error")
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
    writes: list[tuple[str, int, str]] = []

    def fake_fetch_asset_profile(**kwargs):
        row = kwargs["row"]
        if row["target_id"] == "asset-ready":
            return profile
        if row["target_id"] == "asset-missing":
            return None
        raise RuntimeError("provider row failed")

    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(
        module,
        "write_ready_asset_profile",
        lambda **kwargs: writes.append(("ready", kwargs["next_refresh_at_ms"], kwargs["row"]["target_id"])),
    )
    monkeypatch.setattr(
        module,
        "write_missing_asset_profile",
        lambda **kwargs: writes.append(("missing", kwargs["next_refresh_at_ms"], kwargs["row"]["target_id"])),
    )
    monkeypatch.setattr(
        module,
        "write_error_asset_profile",
        lambda **kwargs: writes.append(("error", kwargs["next_refresh_at_ms"], kwargs["row"]["target_id"])),
    )
    db = FakeDB(claims_by_provider={"gmgn_dex_profile": [ready_row, missing_row, error_row]})
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(ready_refresh_ms=1_000, missing_refresh_ms=2_000, error_refresh_ms=3_000),
        db=db,
        telemetry=object(),
        dex_profile_sources=(DexProfileSource(provider="gmgn_dex_profile", market=object()),),
    )

    result = asyncio.run(worker.run_once(now_ms=now_ms))

    assert result.processed == 2
    assert result.failed == 1
    assert writes == [
        ("ready", now_ms + 1_000, "asset-ready"),
        ("missing", now_ms + 2_000, "asset-missing"),
        ("error", now_ms + 3_000, "asset-error"),
    ]
    assert db.refresh_targets.rescheduled == [
        {
            "claims": [ready_row],
            "due_at_ms": now_ms + 1_000,
            "now_ms": now_ms,
            "reason": "profile_ready_written",
        },
        {
            "claims": [missing_row],
            "due_at_ms": now_ms + 2_000,
            "now_ms": now_ms,
            "reason": "profile_missing_written",
        },
        {
            "claims": [error_row],
            "due_at_ms": now_ms + 3_000,
            "now_ms": now_ms,
            "reason": "profile_error_written",
        },
    ]


def test_asset_profile_refresh_worker_reports_provider_block_without_writing_token_error(monkeypatch):
    row = claim_row("gmgn_dex_profile")
    writes: list[str] = []

    def fake_fetch_asset_profile(**kwargs):
        raise DexProviderTemporarilyUnavailable("GET /v1/token/info blocked by Cloudflare challenge HTTP 403")

    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_error_asset_profile", lambda **_: writes.append("error"))
    db = FakeDB(claims_by_provider={"gmgn_dex_profile": [row]})
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        dex_profile_sources=(DexProfileSource(provider="gmgn_dex_profile", market=object()),),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.failed == 1
    assert result.notes["result"]["provider_blocked"] == 1
    assert result.notes["result"]["error"] == 0
    assert writes == []
    assert db.refresh_targets.rescheduled == [
        {
            "claims": [row],
            "due_at_ms": 1_700_000_300_000,
            "now_ms": 1_700_000_000_000,
            "reason": "provider_blocked",
        }
    ]


def test_asset_profile_refresh_worker_empty_queue_does_not_run_read_model_discovery(monkeypatch):
    now_ms = 1_700_000_000_000
    monkeypatch.setattr(
        module,
        "fetch_asset_profile",
        lambda **_: pytest.fail("provider IO must not run without a claimed target"),
    )
    db = FakeDB()
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(batch_size=7),
        db=db,
        telemetry=object(),
        dex_profile_sources=(DexProfileSource(provider="gmgn_dex_profile", market=object()),),
    )

    result = asyncio.run(worker.run_once(now_ms=now_ms))

    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["result"]["source_rows_scanned"] == 0
    assert result.notes["result"]["sources"]["gmgn_dex_profile"]["reason"] == ("no_due_asset_profile_refresh_targets")
    assert db.refresh_targets.claim_calls == [
        {
            "provider": "gmgn_dex_profile",
            "now_ms": now_ms,
            "limit": 7,
            "lease_owner": "asset_profile_refresh",
            "lease_ms": 120_000,
        }
    ]


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
    calls: list[tuple[str, str]] = []

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

    monkeypatch.setattr(module, "fetch_asset_profile", fake_fetch_asset_profile)
    monkeypatch.setattr(module, "write_ready_asset_profile", lambda **_: None)
    db = FakeDB(
        claims_by_provider={
            "gmgn_dex_profile": [claim_row("gmgn_dex_profile")],
            "binance_web3_profile": [claim_row("binance_web3_profile")],
        }
    )
    worker = module.AssetProfileRefreshWorker(
        name="asset_profile_refresh",
        settings=worker_settings(),
        db=db,
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
        ("fetch", "gmgn_dex_profile"),
        ("fetch", "binance_web3_profile"),
    ]


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "statement_timeout_seconds": 120.0,
        "batch_size": 50,
        "lease_ms": 120_000,
        "provider_retry_ms": 300_000,
        "ready_refresh_ms": 21_600_000,
        "missing_refresh_ms": 900_000,
        "error_refresh_ms": 900_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(
        self,
        claims_by_provider: dict[str, list[dict]] | None = None,
    ) -> None:
        self.session_names: list[str] = []
        self.session_kwargs: list[dict] = []
        self.refresh_targets = FakeRefreshTargets(claims_by_provider or {})
        self.profile_dirty = FakeProfileDirtyTargets()

    def worker_session(self, name: str, **kwargs):
        self.session_names.append(name)
        self.session_kwargs.append(dict(kwargs))
        return FakeSession(FakeRepos(self))


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepos:
    def __init__(self, db: FakeDB) -> None:
        self.asset_profile_refresh_targets = db.refresh_targets
        self.token_profile_current_dirty_targets = db.profile_dirty

    def transaction(self):
        return nullcontext()


class FakeRefreshTargets:
    def __init__(self, claims_by_provider: dict[str, list[dict]]) -> None:
        self.claims_by_provider = claims_by_provider
        self.claim_calls: list[dict] = []
        self.rescheduled: list[dict] = []

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claims_by_provider.get(kwargs["provider"], []))

    def queue_depth(self, **kwargs):
        return 0

    def reschedule(self, claims, *, due_at_ms, now_ms, reason=None):
        self.rescheduled.append(
            {
                "claims": list(claims),
                "due_at_ms": due_at_ms,
                "now_ms": now_ms,
                "reason": reason,
            }
        )
        return len(claims)


class FakeProfileDirtyTargets:
    def enqueue_targets(self, targets, *, reason, now_ms):
        return {"targets": len(list(targets))}


class ClosableProvider:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class RecordingAssetProfiles:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upsert_ready_profile(self, **kwargs):
        self.calls.append(dict(kwargs))

    def upsert_status(self, **kwargs):
        self.calls.append(dict(kwargs))


def claim_row(provider: str, *, target_id: str = "asset-1") -> dict:
    return {
        "provider": provider,
        "target_type": "Asset",
        "target_id": target_id,
        "chain_id": "solana",
        "address": "abc",
        "payload_hash": f"hash:{provider}:asset-1",
        "source_watermark_ms": 1_700_000_000_000,
        "lease_owner": "asset_profile_refresh",
        "attempt_count": 1,
        "due_at_ms": 1_700_000_000_000,
    }
