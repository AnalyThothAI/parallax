from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import yaml

from parallax.domains.asset_market.runtime import token_profile_current_worker as module
from parallax.platform.config.settings import WorkersSettings, default_workers_yaml

ADVISORY_LOCK_KEY = 2026051702


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
    assert db.session_kwargs == [{"statement_timeout_seconds": 45.0}]
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


def test_token_profile_current_worker_requires_formal_statement_timeout_settings_contract(monkeypatch):
    calls: list[dict] = []

    def fake_rebuild(**kwargs):
        calls.append(kwargs)
        return {"claimed": 0}

    monkeypatch.setattr(module, "rebuild_token_profile_current_once", fake_rebuild)
    settings = worker_settings()
    delattr(settings, "statement_timeout_seconds")
    db = FakeDB()
    worker = module.TokenProfileCurrentWorker(
        name="token_profile_current",
        settings=settings,
        db=db,
        telemetry=object(),
    )

    with pytest.raises(AttributeError, match="statement_timeout_seconds"):
        asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert calls == []
    assert db.session_names == []


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"batch_size": 0}, "token_profile_current_batch_size_required", id="batch-zero"),
        pytest.param({"batch_size": True}, "token_profile_current_batch_size_required", id="batch-bool"),
        pytest.param({"batch_size": "500"}, "token_profile_current_batch_size_required", id="batch-string"),
        pytest.param({"lease_ms": 0}, "token_profile_current_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "token_profile_current_lease_ms_required", id="lease-bool"),
        pytest.param({"lease_ms": "60000"}, "token_profile_current_lease_ms_required", id="lease-string"),
        pytest.param({"retry_ms": 0}, "token_profile_current_retry_ms_required", id="retry-zero"),
        pytest.param({"retry_ms": True}, "token_profile_current_retry_ms_required", id="retry-bool"),
        pytest.param({"retry_ms": "30000"}, "token_profile_current_retry_ms_required", id="retry-string"),
    ],
)
def test_token_profile_current_worker_rejects_malformed_runtime_settings(monkeypatch, overrides, error_code):
    calls: list[dict] = []

    def fake_rebuild(**kwargs):
        calls.append(kwargs)
        return {"claimed": 0}

    monkeypatch.setattr(module, "rebuild_token_profile_current_once", fake_rebuild)
    db = FakeDB()
    worker = module.TokenProfileCurrentWorker(
        name="token_profile_current",
        settings=worker_settings(**overrides),
        db=db,
        telemetry=object(),
    )

    with pytest.raises(ValueError, match=error_code):
        asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert calls == []


def test_rebuild_token_profile_current_once_projects_sources_and_writes_rows():
    ready_assets = {
        "https://gmgn.ai/external-res/logo.png": ready_image(
            "https://gmgn.ai/external-res/logo.png",
            image_id="image-gmgn",
            source_provider="gmgn_dex_profile",
        ),
        "https://bin.bnbstatic.com/static/images/binance.png": ready_image(
            "https://bin.bnbstatic.com/static/images/binance.png",
            image_id="image-binance",
            source_provider="binance_web3_profile",
        ),
        "https://gmgn.ai/external-res/stream.png": ready_image(
            "https://gmgn.ai/external-res/stream.png",
            image_id="image-stream",
            source_provider="gmgn_stream_snapshot",
        ),
        "https://bin.bnbstatic.com/static/images/btc.png": ready_image(
            "https://bin.bnbstatic.com/static/images/btc.png",
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
                "logo_url": "https://gmgn.ai/external-res/logo.png",
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
                "logo_url": "https://bin.bnbstatic.com/static/images/binance.png",
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
                "raw_payload_json": {"i": "https://gmgn.ai/external-res/stream.png"},
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
                "logo_url": "https://bin.bnbstatic.com/static/images/btc.png",
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
    assert result["image_candidates"] == 4
    assert result["image_sources_admitted"] == 0
    assert result["image_ready_existing"] == 4
    assert result["image_pending_existing"] == 0
    assert result["image_error_existing"] == 0
    assert result["image_unsupported_existing"] == 0
    assert result["image_dirty_existing"] == 0
    assert [row["target_id"] for row in repos.token_profiles.rows] == ["asset:gmgn", "asset:stream", "cex_token:BTC"]
    assert repos.token_profiles.rows[1]["profile_provider"] == "binance_web3_profile"
    assert repos.token_profiles.rows[0]["logo_url"] == "/api/token-images/image-gmgn"
    assert repos.token_profiles.rows[1]["logo_url"] == "/api/token-images/image-binance"
    assert repos.token_profiles.rows[2]["logo_url"] == "/api/token-images/image-cex"
    assert repos.token_profiles.rows[2]["logo_image_id"] == "image-cex"
    assert repos.token_image_assets.source_url_calls == [
        [
            "https://gmgn.ai/external-res/logo.png",
            "https://bin.bnbstatic.com/static/images/binance.png",
            "https://gmgn.ai/external-res/stream.png",
            "https://bin.bnbstatic.com/static/images/btc.png",
        ]
    ]
    assert repos.token_image_source_dirty_targets.enqueued == []
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


def test_rebuild_token_profile_current_once_reports_zero_rows_written_when_projection_unchanged():
    repos = FakeRepos(
        claims=[claim("Asset", "asset:gmgn")],
        gmgn_openapi={
            "asset:gmgn": {
                "asset_id": "asset:gmgn",
                "provider": "gmgn_dex_profile",
                "status": "ready",
                "symbol": "GMGN",
                "raw_payload_json": {"profile": True},
                "observed_at_ms": 1_000,
            }
        },
        binance_web3={},
        gmgn_stream={},
        okx_dex={},
    )
    repos.token_profiles.upsert_results = [False]

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["claimed"] == 1
    assert result["rows_written"] == 0
    assert result["ready"] == 1
    assert repos.token_profiles.rows[0]["target_id"] == "asset:gmgn"


def test_rebuild_token_profile_current_once_admits_missing_image_sources_before_projection():
    logo_url = "https://gmgn.ai/external-res/missing.png"
    repos = FakeRepos(
        claims=[claim("Asset", "asset:gmgn")],
        gmgn_openapi={
            "asset:gmgn": {
                "asset_id": "asset:gmgn",
                "provider": "gmgn_dex_profile",
                "status": "ready",
                "symbol": "GMGN",
                "logo_url": logo_url,
                "raw_payload_json": {"profile": True},
                "observed_at_ms": 1_000,
            }
        },
        binance_web3={},
        gmgn_stream={},
        okx_dex={},
        ready_image_assets={},
    )

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["image_candidates"] == 1
    assert result["image_sources_admitted"] == 1
    assert [row["source_url"] for row in repos.token_image_source_dirty_targets.enqueued] == [logo_url]
    assert repos.token_profiles.rows[0]["logo_url"] is None
    assert repos.token_profiles.rows[0]["quality_flags_json"] == ["logo_mirror_pending"]


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


def test_rebuild_token_profile_current_once_requires_session_source_query_contract():
    repos = FakeRepos(
        claims=[claim("Asset", "asset:gmgn")],
        gmgn_openapi={},
        gmgn_stream={},
        okx_dex={},
    )
    del repos.source_query

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
    )

    assert result["error"] == 1
    assert "source_query" in result["last_error"]
    assert "execute" not in result["last_error"]
    assert repos.dirty_targets.errors == [
        {
            **claim("Asset", "asset:gmgn"),
            "error": result["last_error"],
            "retry_ms": 30_000,
            "now_ms": 10_000,
            "commit": False,
        }
    ]


def test_worker_exposes_single_writer_advisory_lock_key() -> None:
    worker = module.TokenProfileCurrentWorker(
        name="token_profile_current",
        settings=worker_settings(),
        db=FakeDB(),
        telemetry=object(),
    )

    assert module.TokenProfileCurrentWorker.SINGLE_WRITER_KEY == ADVISORY_LOCK_KEY
    assert worker._advisory_lock_key() == ADVISORY_LOCK_KEY


def test_default_workers_yaml_includes_token_profile_current_advisory_lock() -> None:
    workers = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert workers.token_profile_current.advisory_lock_key == ADVISORY_LOCK_KEY
    assert workers.token_profile_current.retry_ms == 30_000


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "statement_timeout_seconds": 45.0,
        "batch_size": 500,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "advisory_lock_key": ADVISORY_LOCK_KEY,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.repos = object()
        self.session_names: list[str] = []
        self.session_kwargs: list[dict] = []

    def worker_session(self, name: str, **kwargs):
        self.session_names.append(name)
        self.session_kwargs.append(dict(kwargs))
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
        self.token_image_source_dirty_targets = FakeImageSourceDirtyTargets()

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
        self.upsert_results: list[bool] = []

    def upsert_current(self, row, *, commit=True):
        self.rows.append(row)
        self.commits.append(commit)
        return self.upsert_results.pop(0) if self.upsert_results else True


class FakeTokenImageAssets:
    def __init__(self, assets_by_source_url: dict[str, dict]) -> None:
        self.assets_by_source_url = assets_by_source_url
        self.source_url_calls: list[list[str]] = []

    def by_source_urls(self, source_urls):
        self.source_url_calls.append(list(source_urls))
        return {
            source_url: self.assets_by_source_url[source_url]
            for source_url in source_urls
            if source_url in self.assets_by_source_url
        }


class FakeImageSourceDirtyTargets:
    def __init__(self, rows: dict[tuple[str, str, str], dict] | None = None) -> None:
        self.rows = rows or {}
        self.identity_calls: list[list[dict]] = []
        self.enqueued: list[dict] = []
        self.enqueue_calls: list[dict] = []

    def existing_by_source_targets(self, targets):
        self.identity_calls.append([dict(target) for target in targets])
        return {
            (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            ): self.rows[
                (
                    str(target["source_url_hash"]),
                    str(target["target_type"]),
                    str(target["target_id"]),
                )
            ]
            for target in targets
            if (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            )
            in self.rows
        }

    def unresolved_terminal_by_source_targets(self, targets, *, worker_name):
        assert worker_name == "token_image_mirror"
        return {}

    def enqueue_targets(self, targets, *, reason, now_ms, commit=True):
        self.enqueue_calls.append({"reason": reason, "now_ms": now_ms, "commit": commit})
        self.enqueued.extend(dict(target) for target in targets)
        return {"targets": len(targets)}


def ready_image(source_url: str, *, image_id: str, source_provider: str) -> dict:
    return {
        "image_id": image_id,
        "source_url": source_url,
        "source_provider": source_provider,
        "source_url_hash": f"hash-{image_id}",
        "status": "ready",
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
