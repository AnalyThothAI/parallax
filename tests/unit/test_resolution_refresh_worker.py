from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.asset_market.providers import DexProviderTemporarilyUnavailable, DexTokenCandidate
from parallax.domains.asset_market.runtime import resolution_refresh_worker as module
from parallax.domains.asset_market.runtime.resolution_refresh_worker import (
    FOUND_ADDRESS_REFRESH_MS,
    FOUND_SYMBOL_REFRESH_MS,
    NOT_FOUND_ADDRESS_REFRESH_MS,
    NOT_FOUND_SYMBOL_REFRESH_MS,
    _claim_retry_budget_exhausted,
    _fetch_lookup_provider_result,
    _persist_lookup_provider_result,
    _refresh_ms,
)


def test_discovery_error_refresh_uses_exponential_backoff_by_error_count():
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=0) == 30_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=1) == 60_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=3) == 1_800_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=10) == 3_600_000


def test_discovery_refresh_keeps_found_and_not_found_cadences():
    assert _refresh_ms(lookup_key="symbol:UPEG", status="found", error_count=10) == FOUND_SYMBOL_REFRESH_MS
    assert _refresh_ms(lookup_key="symbol:UPEG", status="not_found", error_count=10) == NOT_FOUND_SYMBOL_REFRESH_MS
    assert _refresh_ms(lookup_key="address:eip155:1:0xabc", status="found", error_count=10) == FOUND_ADDRESS_REFRESH_MS
    assert (
        _refresh_ms(lookup_key="address:eip155:1:0xabc", status="not_found", error_count=10)
        == NOT_FOUND_ADDRESS_REFRESH_MS
    )


def test_symbol_lookup_writes_provider_rank_to_identity_payload():
    repos = FakeRepos()

    result = _fetch_lookup_provider_result(
        lookup_key="symbol:SPARSE",
        lookup_type="dex_symbol_lookup",
        dex_discovery_market=FakeDexMarket(
            candidates=[
                _candidate(chain_id="eip155:1", address="0x1111111111111111111111111111111111111111"),
                _candidate(chain_id="eip155:56", address="0x2222222222222222222222222222222222222222"),
            ]
        ),
        chain_ids=("eip155:1", "eip155:56"),
    )
    _persist_lookup_provider_result(repos=repos, lookup_result=result, now_ms=1_778_200_000_000)

    assert result["search_hits"] == 2
    by_asset_id = {item["asset_id"]: item["raw_payload"] for item in repos.identity_evidence.writes}
    assert by_asset_id["asset:eip155:1:erc20:0x1111111111111111111111111111111111111111"]["provider_rank"] == 0
    assert by_asset_id["asset:eip155:56:erc20:0x2222222222222222222222222222222222222222"]["provider_rank"] == 1


def test_resolution_refresh_worker_notifies_from_workerbase_path(monkeypatch):
    repos = FakeRefreshRepos()
    db = FakeDB(repos)
    wake_bus = FakeWakeBus()
    reprocess_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        module,
        "_fetch_lookup_provider_result",
        lambda **_: {
            **module._lookup_result(search_requests=1, search_hits=1),
            "candidate_ids": ["asset-1"],
            "affected_lookup_keys": ["symbol:ABC"],
            "assets_written": 1,
        },
    )

    def fake_reprocess_recent_token_intents(**kwargs):
        reprocess_calls.append(kwargs)
        return {"reprocessed_intents": 1, "resolved_intents": 1}

    monkeypatch.setattr(module, "reprocess_recent_token_intents", fake_reprocess_recent_token_intents)

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
        wake_emitter=wake_bus,
    )

    result = asyncio.run(worker.run_once(now_ms=1_778_200_000_000)).notes["result"]

    assert result["reprocessed_intents"] == 1
    assert result["affected_lookup_keys"] == ["symbol:ABC"]
    assert result["anchor"] is None
    assert result["projection"]["status"] == "deferred_to_worker"
    assert wake_bus.resolution_notifications == [["symbol:ABC"]]
    assert repos.discovery.claim_calls[0]["limit"] == 50
    assert reprocess_calls[0]["limit"] == 500
    assert db.session_names == [
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
    ]


def test_resolution_refresh_terminalizes_provider_error_after_retry_budget(monkeypatch):
    repos = FakeRefreshRepos()
    db = FakeDB(repos)

    def raise_provider_error(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "_fetch_lookup_provider_result", raise_provider_error)

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(max_attempts=1),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_778_200_000_000)).notes["result"]

    assert result["lookups_failed"] == 1
    assert result["lookups_terminalized"] == 1
    assert repos.discovery.rescheduled == []
    assert repos.discovery.terminalized == [
        {
            "claims": [
                {
                    "lookup_key": "symbol:ABC",
                    "lookup_type": "dex_symbol_lookup",
                    "error_count": 0,
                    "payload_hash": "hash-abc",
                    "lease_owner": "resolution_refresh",
                    "attempt_count": 1,
                    "latest_seen_ms": 1_778_200_000_000,
                }
            ],
            "worker_name": "resolution_refresh",
            "final_status": "error",
            "final_reason": "provider_error_retry_budget_exhausted",
            "now_ms": 1_778_200_000_000,
            "commit": False,
        }
    ]


def test_resolution_refresh_provider_unavailable_reschedules_batch_without_failed_result(monkeypatch):
    repos = FakeRefreshRepos()
    db = FakeDB(repos)
    claims = [
        {
            "lookup_key": "symbol:ABC",
            "lookup_type": "dex_symbol_lookup",
            "error_count": 0,
            "payload_hash": "hash-abc",
            "lease_owner": "resolution_refresh",
            "attempt_count": 3,
            "latest_seen_ms": 1_778_200_000_000,
        },
        {
            "lookup_key": "symbol:DEF",
            "lookup_type": "dex_symbol_lookup",
            "error_count": 0,
            "payload_hash": "hash-def",
            "lease_owner": "resolution_refresh",
            "attempt_count": 3,
            "latest_seen_ms": 1_778_200_000_000,
        },
    ]

    def claim_due_lookup_keys(**kwargs):
        repos.discovery.claim_calls.append(kwargs)
        return list(claims)

    def raise_provider_unavailable(**_kwargs):
        raise DexProviderTemporarilyUnavailable("OKX token search returned x402 payment required")

    repos.discovery.claim_due_lookup_keys = claim_due_lookup_keys
    monkeypatch.setattr(module, "_fetch_lookup_provider_result", raise_provider_unavailable)

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(max_attempts=1),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )

    worker_result = asyncio.run(worker.run_once(now_ms=1_778_200_000_000))
    result = worker_result.notes["result"]

    assert worker_result.failed == 0
    assert worker_result.notes["status"] == "degraded"
    assert worker_result.notes["degraded"] is True
    assert result["provider_unavailable"] == 2
    assert result["lookups_failed"] == 0
    assert result["lookups_terminalized"] == 0
    assert repos.discovery.terminalized == []
    assert repos.discovery.rescheduled == [
        {
            "claims": claims,
            "due_at_ms": 1_778_200_030_000,
            "now_ms": 1_778_200_000_000,
            "last_error": "provider_unavailable: OKX token search returned x402 payment required",
            "commit": False,
        }
    ]


def test_resolution_refresh_terminalizes_hot_not_found_after_retry_budget(monkeypatch):
    repos = FakeRefreshRepos()
    db = FakeDB(repos)

    monkeypatch.setattr(module, "_fetch_lookup_provider_result", lambda **_: module._lookup_result(search_requests=1))

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(max_attempts=1),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )
    result = asyncio.run(worker.run_once(now_ms=1_778_200_000_000)).notes["result"]

    assert result["lookups_done"] == 1
    assert result["lookups_terminalized"] == 1
    assert repos.discovery.rescheduled == []
    assert repos.discovery.terminalized[0]["final_status"] == "not_found"
    assert repos.discovery.terminalized[0]["final_reason"] == "not_found_retry_budget_exhausted"


def test_resolution_refresh_retry_budget_requires_claim_attempt_field_without_default() -> None:
    claim = {
        "lookup_key": "symbol:ABC",
        "lookup_type": "dex_symbol_lookup",
        "payload_hash": "hash-abc",
        "lease_owner": "resolution_refresh",
    }

    with pytest.raises(ValueError, match="resolution_refresh_claim_attempt_count_required") as exc_info:
        _claim_retry_budget_exhausted(claim, max_attempts=1)

    assert isinstance(exc_info.value.__cause__, KeyError)


def test_resolution_refresh_requires_session_transaction_before_start_lookup(monkeypatch):
    repos = FakeRefreshReposWithoutTransaction()
    db = FakeDB(repos)
    provider_called = False

    def provider_should_not_be_called(**_kwargs):
        nonlocal provider_called
        provider_called = True
        return module._lookup_result(search_requests=1)

    monkeypatch.setattr(module, "_fetch_lookup_provider_result", provider_should_not_be_called)

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )

    with pytest.raises(RuntimeError, match="resolution_refresh_session_transaction_required"):
        asyncio.run(worker.run_once(now_ms=1_778_200_000_000))

    assert provider_called is False
    assert repos.discovery.started == []


def test_resolution_refresh_worker_reads_formal_settings_contract() -> None:
    repos = FakeRefreshRepos()
    db = FakeDB(repos)
    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(batch_size=7, reprocess_limit=11, max_attempts=2, chain_ids=(" solana ", "")),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )

    assert worker.chain_ids == ("solana",)
    assert worker.max_attempts == 2


def test_resolution_refresh_worker_uses_formal_queue_timing_settings(monkeypatch) -> None:
    repos = FakeRefreshRepos()
    db = FakeDB(repos)
    now_ms = 1_778_200_000_000

    monkeypatch.setattr(module, "_fetch_lookup_provider_result", lambda **_: module._lookup_result(search_requests=1))

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=worker_settings(lease_ms=45_000, hot_not_found_retry_ms=7_000),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
    )

    result = asyncio.run(worker.run_once(now_ms=now_ms)).notes["result"]

    assert result["lookups_done"] == 1
    assert repos.discovery.claim_calls[0]["lease_ms"] == 45_000
    assert repos.discovery.claim_calls[0]["running_timeout_ms"] == 45_000
    assert repos.discovery.claim_calls[0]["hot_not_found_retry_ms"] == 7_000
    assert repos.discovery.started[0]["running_timeout_ms"] == 45_000
    assert repos.discovery.rescheduled[0]["due_at_ms"] == now_ms + 7_000


def test_resolution_refresh_worker_requires_formal_chain_settings_contract() -> None:
    repos = FakeRefreshRepos()
    settings = worker_settings()
    delattr(settings, "chain_ids")

    with pytest.raises(AttributeError, match="chain_ids"):
        module.ResolutionRefreshWorker(
            name="resolution_refresh",
            settings=settings,
            db=FakeDB(repos),
            telemetry=object(),
            dex_discovery_market=object(),
        )


def test_resolution_refresh_worker_requires_discovery_provider_contract() -> None:
    repos = FakeRefreshRepos()

    with pytest.raises(RuntimeError, match="resolution_refresh_provider_required"):
        module.ResolutionRefreshWorker(
            name="resolution_refresh",
            settings=worker_settings(),
            db=FakeDB(repos),
            telemetry=object(),
            dex_discovery_market=None,
        )


def worker_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 30,
        "timeout_seconds": 120,
        "batch_size": 50,
        "lease_ms": 300_000,
        "hot_not_found_retry_ms": 60_000,
        "reprocess_limit": 500,
        "max_attempts": 3,
        "chain_ids": ("solana",),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _candidate(*, chain_id: str, address: str, symbol: str = "SPARSE") -> DexTokenCandidate:
    return DexTokenCandidate(
        chain_id=chain_id,
        address=address,
        symbol=symbol,
        name=symbol,
        price_usd=None,
        market_cap_usd=None,
        liquidity_usd=None,
        holders=None,
        community_recognized=None,
        raw={"chain_id": chain_id, "tokenContractAddress": address, "tokenSymbol": symbol},
    )


class FakeDexMarket:
    def __init__(self, *, candidates: list[DexTokenCandidate]) -> None:
        self.candidates = candidates

    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]) -> list[DexTokenCandidate]:
        return list(self.candidates)


class FakeRepos:
    def __init__(self) -> None:
        self.registry = FakeRegistry()
        self.identity_evidence = FakeIdentityEvidence()


class FakeRefreshRepos:
    def __init__(self) -> None:
        self.conn = FakeRefreshConn()
        self.discovery = FakeRefreshDiscovery()
        self.transactions: list[FakeTransaction] = []

    def transaction(self):
        transaction = FakeTransaction()
        self.transactions.append(transaction)
        return transaction


class FakeRefreshReposWithoutTransaction:
    def __init__(self) -> None:
        self.conn = FakeRefreshConn()
        self.discovery = FakeRefreshDiscovery()


class FakeDB:
    def __init__(self, repos: FakeRefreshRepos) -> None:
        self.repos = repos
        self.session_names: list[str] = []

    def worker_session(self, name: str):
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos: FakeRefreshRepos) -> None:
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRefreshConn:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeTransaction(AbstractContextManager[Any]):
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> None:
        self.entered = True

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True


class FakeRefreshDiscovery:
    def __init__(self) -> None:
        self.claim_calls: list[dict[str, object]] = []
        self.started: list[dict[str, object]] = []
        self.rescheduled: list[dict[str, object]] = []
        self.terminalized: list[dict[str, object]] = []

    def claim_due_lookup_keys(self, **kwargs):
        self.claim_calls.append(kwargs)
        return [
            {
                "lookup_key": "symbol:ABC",
                "lookup_type": "dex_symbol_lookup",
                "error_count": 0,
                "payload_hash": "hash-abc",
                "lease_owner": kwargs.get("lease_owner", "resolution_refresh"),
                "attempt_count": 1,
                "latest_seen_ms": 1_778_200_000_000,
            }
        ]

    def start_lookup(self, **kwargs):
        self.started.append(kwargs)
        return {}

    def finish_lookup(self, **kwargs):
        return {}

    def fail_lookup(self, **kwargs):
        return {}

    def mark_lookup_done(self, claims, **kwargs):
        return len(list(claims))

    def reschedule_lookup_claims(self, claims, **kwargs):
        rows = list(claims)
        self.rescheduled.append({"claims": rows, **kwargs})
        return len(rows)

    def terminalize_lookup_claims(self, claims, **kwargs):
        rows = list(claims)
        self.terminalized.append({"claims": rows, **kwargs})
        return {"terminalized": len(rows), "deleted": len(rows)}

    def counts(self):
        return {"found": 1}


class FakeWakeBus:
    def __init__(self) -> None:
        self.resolution_notifications: list[list[str]] = []

    def notify_resolution_updated(self, *, lookup_keys):
        self.resolution_notifications.append(list(lookup_keys))


class FakeRegistry:
    def upsert_chain_asset(self, *, chain_id: str, address: str, observed_at_ms: int, commit: bool = False):
        standard = "erc20" if chain_id.startswith("eip155:") else "token"
        return {
            "asset_id": f"asset:{chain_id}:{standard}:{address}",
            "chain_id": chain_id,
            "address": address,
        }


class FakeIdentityEvidence:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def upsert_identity_evidence(self, **kwargs):
        self.writes.append(kwargs)

    def recompute_current_identity(self, asset_id: str, *, now_ms: int, commit: bool = False):
        return {}
