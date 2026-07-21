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
            "max_attempts": 3,
        }
    ]
    assert db.session_names == ["token_profile_current"]


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
        max_attempts=3,
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
        ["https://gmgn.ai/external-res/logo.png"],
        [
            "https://bin.bnbstatic.com/static/images/binance.png",
            "https://gmgn.ai/external-res/stream.png",
        ],
        ["https://bin.bnbstatic.com/static/images/btc.png"],
    ]
    assert repos.token_image_source_dirty_targets.enqueued == []
    assert repos.dirty_targets.claim_calls == [
        {
            "now_ms": 10_000,
            "limit": 100,
            "lease_owner": "profile-worker",
            "lease_ms": 60_000,
        }
    ]
    assert repos.dirty_targets.done == [
        claim("Asset", "asset:gmgn"),
        claim("Asset", "asset:stream"),
        claim("CexToken", "cex_token:BTC"),
    ]
    assert repos.transactions == 5


@pytest.mark.parametrize("failure_stage", ["admission", "upsert"])
def test_rebuild_token_profile_current_once_isolates_bad_target_from_valid_claims(
    monkeypatch,
    failure_stage: str,
) -> None:
    bad_claim = claim("Asset", "asset:bad")
    good_claim = claim("Asset", "asset:good")
    repos = FakeRepos(
        claims=[bad_claim, good_claim],
        gmgn_openapi={
            target_id: {
                "asset_id": target_id,
                "provider": "gmgn_dex_profile",
                "status": "ready",
                "symbol": target_id.rsplit(":", maxsplit=1)[-1].upper(),
                "logo_url": f"https://gmgn.ai/external-res/{target_id.rsplit(':', maxsplit=1)[-1]}.png",
                "raw_payload_json": {"profile": True},
                "observed_at_ms": 1_000,
            }
            for target_id in ("asset:bad", "asset:good")
        },
        gmgn_stream={},
        okx_dex={},
    )
    upsert_current = repos.token_profiles.upsert_current

    def fail_one_target(row):
        if row["target_id"] == "asset:bad":
            raise ValueError("malformed profile row")
        return upsert_current(row)

    if failure_stage == "upsert":
        repos.token_profiles.upsert_current = fail_one_target
    else:
        admit_sources = module.admit_token_image_sources

        def fail_one_admission(*, repos, candidates, now_ms):
            materialized = list(candidates)
            if any(candidate.target_id == "asset:bad" for candidate in materialized):
                raise ValueError("malformed image candidate")
            return admit_sources(repos=repos, candidates=materialized, now_ms=now_ms)

        monkeypatch.setattr(module, "admit_token_image_sources", fail_one_admission)

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
        max_attempts=3,
    )

    assert result["ready"] == 1
    assert result["error"] == 1
    assert repos.dirty_targets.done == [good_claim]
    assert [error["target_id"] for error in repos.dirty_targets.errors] == ["asset:bad"]


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
        max_attempts=3,
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
        max_attempts=3,
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
        max_attempts=3,
    )

    assert result["reason"] == "no_due_token_profile_current_targets"
    assert result["claimed"] == 0
    assert result["source_rows_scanned"] == 0
    assert result["targets_loaded"] == 0
    assert result["rows_written"] == 0
    assert repos.source_query.profile_loader_calls == []
    assert repos.token_profiles.rows == []
    assert repos.transactions == 1


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
        max_attempts=3,
    )

    assert result["error"] == 1
    assert "profile source boom" in result["last_error"]
    assert repos.dirty_targets.errors == [
        {
            **claim("Asset", "asset:gmgn"),
            "error": "RuntimeError: profile source boom",
            "retry_ms": 30_000,
            "max_attempts": 3,
            "worker_name": "profile-worker",
            "now_ms": 10_000,
        }
    ]


def test_rebuild_token_profile_current_once_isolates_target_specific_source_load_failure():
    bad = claim("Asset", "asset:bad")
    good = claim("Asset", "asset:good")
    repos = FakeRepos(
        claims=[bad, good],
        gmgn_openapi={},
        gmgn_stream={},
        okx_dex={},
    )
    repos.source_query.fail_target_ids.add("asset:bad")

    result = module.rebuild_token_profile_current_once(
        repos=repos,
        now_ms=10_000,
        limit=100,
        lease_owner="profile-worker",
        lease_ms=60_000,
        retry_ms=30_000,
        max_attempts=3,
    )

    assert result["error"] == 1
    assert result["targets_loaded"] == 1
    assert repos.dirty_targets.done == [good]
    assert [row["target_id"] for row in repos.dirty_targets.errors] == ["asset:bad"]


def test_rebuild_token_profile_current_once_does_not_let_malformed_claim_poison_valid_peer():
    valid = claim("Asset", "asset:valid")
    malformed = {**claim("Asset", "asset:bad"), "target_id": ""}
    repos = FakeRepos(
        claims=[malformed, valid],
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
        max_attempts=3,
    )

    assert result["error"] == 1
    assert result["targets_loaded"] == 1
    assert repos.dirty_targets.done == [valid]
    assert repos.dirty_targets.errors == [
        {
            **malformed,
            "error": "ValueError: token_profile_current_dirty_target_identity_required",
            "retry_ms": 30_000,
            "max_attempts": 3,
            "worker_name": "profile-worker",
            "now_ms": 10_000,
        }
    ]


def test_rebuild_token_profile_current_once_isolates_malformed_claim_cas_contract():
    valid = claim("Asset", "asset:valid")
    malformed = {**claim("Asset", "asset:bad"), "payload_hash": ""}
    repos = FakeRepos(
        claims=[malformed, valid],
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
        max_attempts=3,
    )

    assert result["error"] == 1
    assert repos.dirty_targets.done == [valid]
    assert [row["target_id"] for row in repos.dirty_targets.errors] == ["asset:bad"]


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
        max_attempts=3,
    )

    assert result["error"] == 1
    assert "source_query" in result["last_error"]
    assert "execute" not in result["last_error"]
    assert repos.dirty_targets.errors == [
        {
            **claim("Asset", "asset:gmgn"),
            "error": result["last_error"],
            "retry_ms": 30_000,
            "max_attempts": 3,
            "worker_name": "profile-worker",
            "now_ms": 10_000,
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
        "max_attempts": 3,
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

    def mark_done(self, claims, *, now_ms):
        self.done.extend(dict(claim) for claim in claims)
        return len(claims)

    def mark_error(self, claims, *, error, retry_ms, max_attempts, worker_name, now_ms):
        self.errors.extend(
            {
                **dict(claim),
                "error": error,
                "retry_ms": retry_ms,
                "max_attempts": max_attempts,
                "worker_name": worker_name,
                "now_ms": now_ms,
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
        self.fail_target_ids: set[str] = set()

    def gmgn_openapi_profiles(self, asset_ids):
        self._record_loader("gmgn_openapi_profiles", asset_ids)
        return {asset_id: self.gmgn_openapi[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_openapi}

    def binance_web3_profiles(self, asset_ids):
        self._record_loader("binance_web3_profiles", asset_ids)
        return {asset_id: self.binance_web3[asset_id] for asset_id in asset_ids if asset_id in self.binance_web3}

    def gmgn_stream_profiles(self, asset_ids):
        self._record_loader("gmgn_stream_profiles", asset_ids)
        return {asset_id: self.gmgn_stream[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_stream}

    def okx_dex_profiles(self, asset_ids):
        self._record_loader("okx_dex_profiles", asset_ids)
        return {asset_id: self.okx_dex[asset_id] for asset_id in asset_ids if asset_id in self.okx_dex}

    def cex_token_profiles(self, cex_token_ids):
        self._record_loader("cex_token_profiles", cex_token_ids)
        return {
            cex_token_id: self.cex_profiles[cex_token_id]
            for cex_token_id in cex_token_ids
            if cex_token_id in self.cex_profiles
        }

    def _record_loader(self, name, target_ids):
        self.profile_loader_calls.append(name)
        if self.fail_loader is not None:
            raise self.fail_loader
        if self.fail_target_ids.intersection(target_ids):
            raise ValueError("malformed persisted profile source")


class FakeTokenProfiles:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.upsert_results: list[bool] = []

    def upsert_current(self, row):
        self.rows.append(row)
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

    def enqueue_targets(self, targets, *, reason, now_ms):
        self.enqueue_calls.append({"reason": reason, "now_ms": now_ms})
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
