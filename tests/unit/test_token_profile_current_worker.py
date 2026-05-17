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
        }
    ]
    assert db.session_names == ["token_profile_current"]


def test_rebuild_token_profile_current_once_projects_sources_and_writes_rows():
    repos = FakeRepos(
        targets=[
            {"target_type": "Asset", "target_id": "asset:gmgn"},
            {"target_type": "Asset", "target_id": "asset:stream"},
            {"target_type": "CexToken", "target_id": "cex_token:BTC"},
        ],
        gmgn_openapi={
            "asset:gmgn": {
                "asset_id": "asset:gmgn",
                "status": "ready",
                "symbol": "GMGN",
                "logo_url": "https://gmgn.example/logo.png",
                "raw_payload_json": {"profile": True},
                "observed_at_ms": 1_000,
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
    )

    result = module.rebuild_token_profile_current_once(repos=repos, now_ms=10_000, limit=100)

    assert result["selected"] == 3
    assert result["ready"] == 2
    assert result["unsupported"] == 1
    assert result["with_logo"] == 2
    assert result["source_provider"] == {"gmgn_dex_profile": 1, "gmgn_stream_snapshot": 1}
    assert [row["target_id"] for row in repos.token_profiles.rows] == ["asset:gmgn", "asset:stream", "cex_token:BTC"]
    assert repos.token_profiles.commits == [False, False, False]
    assert repos.conn.commits == 1


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "batch_size": 500,
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


class FakeRepos:
    def __init__(self, *, targets, gmgn_openapi, gmgn_stream, okx_dex) -> None:
        self.conn = FakeConn()
        self.source_query = FakeSourceQuery(
            targets=targets,
            gmgn_openapi=gmgn_openapi,
            gmgn_stream=gmgn_stream,
            okx_dex=okx_dex,
        )
        self.token_profiles = FakeTokenProfiles()


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeSourceQuery:
    def __init__(self, *, targets, gmgn_openapi, gmgn_stream, okx_dex) -> None:
        self.targets = targets
        self.gmgn_openapi = gmgn_openapi
        self.gmgn_stream = gmgn_stream
        self.okx_dex = okx_dex

    def recent_profile_targets(self, **kwargs):
        return self.targets

    def gmgn_openapi_profiles(self, asset_ids):
        return {asset_id: self.gmgn_openapi[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_openapi}

    def gmgn_stream_profiles(self, asset_ids):
        return {asset_id: self.gmgn_stream[asset_id] for asset_id in asset_ids if asset_id in self.gmgn_stream}

    def okx_dex_profiles(self, asset_ids):
        return {asset_id: self.okx_dex[asset_id] for asset_id in asset_ids if asset_id in self.okx_dex}


class FakeTokenProfiles:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.commits: list[bool] = []

    def upsert_current(self, row, *, commit=True):
        self.rows.append(row)
        self.commits.append(commit)
