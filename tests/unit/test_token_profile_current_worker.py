from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.runtime import token_profile_current_worker as module


def test_token_profile_current_worker_run_once_records_result_and_uses_one_db_session(monkeypatch):
    calls: list[dict] = []
    result_payload = {
        "selected": 3,
        "ready": 1,
        "missing": 1,
        "unsupported": 1,
        "error": 0,
        "with_logo": 1,
        "source_provider": {"gmgn_stream_snapshot": 1},
        "started_at_ms": 1_700_000_000_000,
        "finished_at_ms": 1_700_000_000_000,
    }

    def fake_rebuild(**kwargs):
        calls.append(kwargs)
        return dict(result_payload)

    monkeypatch.setattr(module, "rebuild_token_profile_current_once", fake_rebuild)
    db = FakeDB()
    worker = module.TokenProfileCurrentWorker(
        name="token_profile_current",
        settings=worker_settings(batch_size=7),
        db=db,
        telemetry=object(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 3
    assert result.failed == 0
    assert result.notes["result"] == result_payload
    assert calls == [
        {
            "repos": db.repos,
            "now_ms": 1_700_000_000_000,
            "limit": 7,
            "lease_owner": "token_profile_current",
            "lease_ms": 60_000,
            "retry_ms": 30_000,
        }
    ]
    assert db.session_names == ["token_profile_current"]


def test_rebuild_token_profile_current_once_projects_sources_and_writes_rows():
    ready_assets = {
        "https://gmgn.example/logo.png": ready_image(
            "https://gmgn.example/logo.png",
            image_id="image-gmgn",
            source_provider="gmgn_dex_profile",
        ),
        "https://binance.example/logo.png": ready_image(
            "https://binance.example/logo.png",
            image_id="image-binance",
            source_provider="binance_web3_profile",
        ),
        "https://stream.example/logo.png": ready_image(
            "https://stream.example/logo.png",
            image_id="image-stream",
            source_provider="gmgn_stream_snapshot",
        ),
        "https://bin.bnbstatic.com/btc.png": ready_image(
            "https://bin.bnbstatic.com/btc.png",
            image_id="image-cex",
            source_provider="binance_cex_profile",
        ),
    }
    repos = FakeRepos(
        claims=[
            claim("Asset", "asset:gmgn"),
            claim("Asset", "asset:stream"),
            claim("CexToken", "cex_token:BTC"),
        ],
        gmgn_openapi={
            "asset:gmgn": {
                "asset_id": "asset:gmgn",
                "provider": "gmgn_dex_profile",
                "status": "ready",
                "symbol": "GMGN",
                "logo_url": "https://gmgn.example/logo.png",
                "raw_payload_json": {"profile": True},
                "observed_at_ms": 1_000,
            }
        },
        binance_web3={
            "asset:stream": {
                "asset_id": "asset:stream",
                "provider": "binance_web3_profile",
                "status": "ready",
                "symbol": "BN",
                "logo_url": "https://binance.example/logo.png",
                "raw_payload_json": {"source_provider": "binance_web3_profile"},
                "observed_at_ms": 1_500,
            }
        },
        gmgn_stream={
            "asset:stream": {
                "asset_id": "asset:stream",
                "provider": "gmgn",
                "evidence_kind": "gmgn_payload_exact",
                "evidence_id": "stream-1",
                "raw_payload_json": {"i": "https://stream.example/logo.png"},
                "observed_at_ms": 2_000,
            }
        },
        okx_dex={},
        cex_profiles={
            "cex_token:BTC": {
                "cex_token_id": "cex_token:BTC",
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload_json": {"rank": 1},
                "observed_at_ms": 9_000,
            }
        },
        ready_image_assets=ready_assets,
    )

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["selected"] == 3
    assert result["claimed"] == 3
    assert result["source_rows_scanned"] == 0
    assert result["targets_loaded"] == 3
    assert result["rows_written"] == 3
    assert result["ready"] == 3
    assert result["unsupported"] == 0
    assert result["with_logo"] == 3
    assert result["source_provider"] == {
        "binance_cex_profile": 1,
        "binance_web3_profile": 1,
        "gmgn_dex_profile": 1,
    }
    assert [row["target_id"] for row in repos.token_profiles.rows] == ["asset:gmgn", "asset:stream", "cex_token:BTC"]
    assert repos.token_profiles.rows[1]["profile_provider"] == "binance_web3_profile"
    assert repos.token_profiles.rows[0]["logo_url"] == "/api/token-images/image-gmgn"
    assert repos.token_profiles.rows[1]["logo_url"] == "/api/token-images/image-binance"
    assert repos.token_profiles.rows[2]["logo_url"] == "/api/token-images/image-cex"
    assert repos.token_profiles.rows[2]["logo_image_id"] == "image-cex"
    assert repos.token_image_assets.source_url_calls == [
        [
            "https://gmgn.example/logo.png",
            "https://binance.example/logo.png",
            "https://stream.example/logo.png",
            "https://bin.bnbstatic.com/btc.png",
        ]
    ]
    assert repos.token_profiles.commits == [False, False, False]
    assert repos.dirty_targets.claim_calls == [
        {
            "now_ms": 10_000,
            "limit": 100,
            "lease_owner": "profile-worker",
            "lease_ms": 60_000,
            "commit": True,
        }
    ]
    assert repos.dirty_targets.done == [
        claim("Asset", "asset:gmgn"),
        claim("Asset", "asset:stream"),
        claim("CexToken", "cex_token:BTC"),
    ]
    assert repos.transactions == 1


def test_rebuild_token_profile_current_once_empty_queue_does_not_load_profile_sources():
    repos = FakeRepos(
        claims=[],
        gmgn_openapi={},
        gmgn_stream={},
        okx_dex={},
    )

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["reason"] == "no_due_token_profile_current_targets"
    assert result["claimed"] == 0
    assert result["source_rows_scanned"] == 0
    assert result["targets_loaded"] == 0
    assert result["rows_written"] == 0
    assert repos.source_query.profile_loader_calls == []
    assert repos.token_profiles.rows == []
    assert repos.transactions == 0


def test_rebuild_token_profile_current_once_marks_claim_error_when_exact_load_fails():
    repos = FakeRepos(
        claims=[claim("Asset", "asset:gmgn")],
        gmgn_openapi={},
        gmgn_stream={},
        okx_dex={},
    )
    repos.source_query.fail_loader = RuntimeError("profile source boom")

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["error"] == 1
    assert "profile source boom" in result["last_error"]
    assert repos.dirty_targets.errors == [
        {
            **claim("Asset", "asset:gmgn"),
            "error": "RuntimeError: profile source boom",
            "retry_ms": 30_000,
            "now_ms": 10_000,
            "commit": False,
        }
    ]


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "batch_size": 500,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.repos = object()
        self.session_names: list[str] = []

    def worker_session(self, name: str, **kwargs):
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepos:
    def __init__(
        self,
        *,
        claims,
        gmgn_openapi,
        gmgn_stream,
        okx_dex,
        binance_web3=None,
        cex_profiles=None,
        ready_image_assets=None,
    ) -> None:
        self.conn = FakeConn()
        self.transactions = 0
        self.dirty_targets = FakeDirtyTargets(claims)
        self.token_profile_current_dirty_targets = self.dirty_targets
        self.source_query = FakeSourceQuery(
            gmgn_openapi=gmgn_openapi,
            binance_web3=binance_web3 or {},
            gmgn_stream=gmgn_stream,
            okx_dex=okx_dex,
            cex_profiles=cex_profiles or {},
        )
        self.token_profiles = FakeTokenProfiles()
        self.token_image_assets = FakeTokenImageAssets(ready_image_assets or {})

    def transaction(self):
        return FakeTransaction(self)


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeTransaction:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        self.repos.transactions += 1
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDirtyTargets:
    def __init__(self, claims):
        self.claims = list(claims)
        self.claim_calls: list[dict] = []
        self.done: list[dict] = []
        self.errors: list[dict] = []

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claims)

    def queue_depth(self, **kwargs):
        return 0

    def mark_done(self, claims, *, now_ms, commit=True):
        self.done.extend(dict(claim) for claim in claims)
        return len(claims)

    def mark_error(self, claims, *, error, retry_ms, now_ms, commit=True):
        self.errors.extend(
            {
                **dict(claim),
                "error": error,
                "retry_ms": retry_ms,
                "now_ms": now_ms,
                "commit": commit,
            }
            for claim in claims
        )
        return len(claims)


class FakeSourceQuery:
    def __init__(self, *, gmgn_openapi, binance_web3, gmgn_stream, okx_dex, cex_profiles) -> None:
        self.gmgn_openapi = gmgn_openapi
        self.binance_web3 = binance_web3
        self.gmgn_stream = gmgn_stream
        self.okx_dex = okx_dex
        self.cex_profiles = cex_profiles
        self.profile_loader_calls: list[str] = []
        self.fail_loader: BaseException | None = None

    def gmgn_openapi_profiles(self, asset_ids):
        self._record_loader("gmgn_openapi_profiles")
        return {asset_id: self.gmgn_openapi[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_openapi}

    def binance_web3_profiles(self, asset_ids):
        self._record_loader("binance_web3_profiles")
        return {asset_id: self.binance_web3[asset_id] for asset_id in asset_ids if asset_id in self.binance_web3}

    def gmgn_stream_profiles(self, asset_ids):
        self._record_loader("gmgn_stream_profiles")
        return {asset_id: self.gmgn_stream[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_stream}

    def okx_dex_profiles(self, asset_ids):
        self._record_loader("okx_dex_profiles")
        return {asset_id: self.okx_dex[asset_id] for asset_id in asset_ids if asset_id in self.okx_dex}

    def cex_token_profiles(self, cex_token_ids):
        self._record_loader("cex_token_profiles")
        return {
            cex_token_id: self.cex_profiles[cex_token_id]
            for cex_token_id in cex_token_ids
            if cex_token_id in self.cex_profiles
        }

    def _record_loader(self, name):
        self.profile_loader_calls.append(name)
        if self.fail_loader is not None:
            raise self.fail_loader


class FakeTokenProfiles:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.commits: list[bool] = []

    def upsert_current(self, row, *, commit=True):
        self.rows.append(row)
        self.commits.append(commit)


class FakeTokenImageAssets:
    def __init__(self, assets_by_source_url: dict[str, dict]) -> None:
        self.assets_by_source_url = assets_by_source_url
        self.source_url_calls: list[list[str]] = []

    def ready_by_source_urls(self, source_urls):
        self.source_url_calls.append(list(source_urls))
        return {
            source_url: self.assets_by_source_url[source_url]
            for source_url in source_urls
            if source_url in self.assets_by_source_url
        }


def ready_image(source_url: str, *, image_id: str, source_provider: str) -> dict:
    return {
        "image_id": image_id,
        "source_url": source_url,
        "source_provider": source_provider,
        "source_url_hash": f"hash-{image_id}",
        "public_url": f"/api/token-images/{image_id}",
    }


def claim(target_type: str, target_id: str) -> dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "payload_hash": f"hash:{target_type}:{target_id}",
        "lease_owner": "profile-worker",
        "attempt_count": 1,
    }
