from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.providers import DexTokenCandidate
from gmgn_twitter_intel.domains.asset_market.runtime import resolution_refresh_worker as module
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import (
    FOUND_ADDRESS_REFRESH_MS,
    FOUND_SYMBOL_REFRESH_MS,
    NOT_FOUND_ADDRESS_REFRESH_MS,
    NOT_FOUND_SYMBOL_REFRESH_MS,
    _process_dex_symbol_lookup,
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

    result = _process_dex_symbol_lookup(
        repos=repos,
        lookup_key="symbol:SPARSE",
        dex_discovery_market=FakeDexMarket(
            candidates=[
                _candidate(chain_id="eip155:1", address="0x1111111111111111111111111111111111111111"),
                _candidate(chain_id="eip155:56", address="0x2222222222222222222222222222222222222222"),
            ]
        ),
        chain_ids=("eip155:1", "eip155:56"),
        now_ms=1_778_200_000_000,
    )

    assert result["search_hits"] == 2
    by_asset_id = {item["asset_id"]: item["raw_payload"] for item in repos.identity_evidence.writes}
    assert by_asset_id["asset:eip155:1:erc20:0x1111111111111111111111111111111111111111"]["provider_rank"] == 0
    assert by_asset_id["asset:eip155:56:erc20:0x2222222222222222222222222222222222222222"]["provider_rank"] == 1


def test_resolution_refresh_notifies_without_inline_anchor_or_projection(monkeypatch):
    repos = FakeRefreshRepos()
    wake_bus = FakeWakeBus()

    monkeypatch.setattr(
        module,
        "_process_lookup",
        lambda **_: {
            **module._lookup_result(search_requests=1, search_hits=1),
            "candidate_ids": ["asset-1"],
            "affected_lookup_keys": ["symbol:ABC"],
            "assets_written": 1,
        },
    )
    monkeypatch.setattr(
        module,
        "reprocess_recent_token_intents",
        lambda **_: {"reprocessed_intents": 1, "resolved_intents": 1},
    )

    result = module.run_resolution_refresh_once(
        repos=repos,
        dex_discovery_market=object(),
        dex_quote_market=object(),
        chain_ids=("solana",),
        now_ms=1_778_200_000_000,
        wake_bus=wake_bus,
    )

    assert result["reprocessed_intents"] == 1
    assert result["affected_lookup_keys"] == ["symbol:ABC"]
    assert result["anchor"] is None
    assert result["projection"]["status"] == "deferred_to_worker"
    assert wake_bus.resolution_notifications == [["symbol:ABC"]]


def test_resolution_refresh_worker_notifies_from_workerbase_path(monkeypatch):
    repos = FakeRefreshRepos()
    db = FakeDB(repos)
    wake_bus = FakeWakeBus()

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
    monkeypatch.setattr(
        module,
        "reprocess_recent_token_intents",
        lambda **_: {"reprocessed_intents": 1, "resolved_intents": 1},
    )

    worker = module.ResolutionRefreshWorker(
        name="resolution_refresh",
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=30,
            timeout_seconds=120,
            batch_size=50,
            reprocess_limit=500,
        ),
        db=db,
        telemetry=object(),
        dex_discovery_market=object(),
        dex_quote_market=object(),
        chain_ids=("solana",),
        wake_bus=wake_bus,
    )

    result = asyncio.run(worker.run_once(now_ms=1_778_200_000_000)).notes["result"]

    assert result["reprocessed_intents"] == 1
    assert result["affected_lookup_keys"] == ["symbol:ABC"]
    assert result["anchor"] is None
    assert result["projection"]["status"] == "deferred_to_worker"
    assert wake_bus.resolution_notifications == [["symbol:ABC"]]
    assert db.session_names == [
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
        "resolution_refresh",
    ]


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


class FakeRefreshDiscovery:
    def claim_due_lookup_keys(self, **kwargs):
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

    def due_lookup_keys(self, **kwargs):
        raise AssertionError("resolution_refresh runtime must claim dirty lookup queue, not scan recent facts")

    def start_lookup(self, **kwargs):
        return {}

    def finish_lookup(self, **kwargs):
        return {}

    def fail_lookup(self, **kwargs):
        return {}

    def mark_lookup_done(self, claims, **kwargs):
        return len(list(claims))

    def reschedule_lookup_claims(self, claims, **kwargs):
        return len(list(claims))

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
