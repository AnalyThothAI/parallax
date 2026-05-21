from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.runtime import token_image_mirror_worker as worker_module
from gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker


def test_token_image_mirror_worker_mirrors_claimed_rows_outside_db_sessions(monkeypatch, tmp_path) -> None:
    db = FakeDB()
    settings = SimpleNamespace(
        enabled=True,
        interval_seconds=60,
        source_limit=2,
        batch_size=3,
        statement_timeout_seconds=120,
    )

    monkeypatch.setattr(worker_module, "TokenImageSourceQuery", FakeSourceQuery)
    monkeypatch.setattr(worker_module, "TokenImageMirrorService", lambda **kwargs: FakeMirrorService(db=db, **kwargs))

    worker = TokenImageMirrorWorker(
        name="token_image_mirror",
        settings=settings,
        db=db,
        telemetry=object(),
        app_home=tmp_path,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.notes["result"] == {
        "selected": 2,
        "pending_upserted": 2,
        "ready_existing": 1,
        "claimed": 3,
        "mirrored": 1,
        "error": 1,
        "unsupported": 1,
        "started_at_ms": 1_700_000_000_000,
        "finished_at_ms": 1_700_000_000_000,
    }
    assert result.processed == 3
    assert result.failed == 1
    assert db.statement_timeouts == [120]
    assert db.repo.upserted_now_ms == 1_700_000_000_000
    assert db.repo.claimed == (1_700_000_000_000, 3)
    assert db.repo.ready_source_urls == ["https://gmgn.ai/external-res/ready.png", "https://gmgn.ai/external-res/new.png"]


class FakeSourceQuery:
    def __init__(self, conn) -> None:
        self.conn = conn

    def candidate_sources(self, *, now_ms: int, source_limit: int):
        assert now_ms == 1_700_000_000_000
        assert source_limit == 2
        return [
            {"source_url": "https://gmgn.ai/external-res/ready.png", "source_provider": "gmgn", "source_kind": "x"},
            {"source_url": "https://gmgn.ai/external-res/new.png", "source_provider": "gmgn", "source_kind": "x"},
        ]


class FakeMirrorService:
    def __init__(self, *, db: FakeDB, repository, app_home) -> None:
        self.db = db
        self.repository = repository
        self.app_home = app_home

    def mirror_source(self, row, *, now_ms: int):
        assert now_ms == 1_700_000_000_000
        assert self.db.open_sessions == 0
        return {"status": row["outcome"], "source_url": row["source_url"]}


class FakeTokenImageRepo:
    def __init__(self) -> None:
        self.upserted_now_ms: int | None = None
        self.claimed: tuple[int, int] | None = None
        self.ready_source_urls: list[str] = []

    def upsert_pending_sources(self, rows, *, now_ms: int, commit: bool = True):
        assert commit is True
        self.upserted_now_ms = now_ms
        return len(rows)

    def ready_by_source_urls(self, source_urls):
        self.ready_source_urls = list(source_urls)
        return {"https://gmgn.ai/external-res/ready.png": {"status": "ready"}}

    def claim_due_sources(self, *, now_ms: int, limit: int):
        self.claimed = (now_ms, limit)
        return [
            {"source_url": "https://gmgn.ai/external-res/new.png", "outcome": "ready"},
            {"source_url": "https://gmgn.ai/external-res/bad.png", "outcome": "error"},
            {"source_url": "https://gmgn.ai/external-res/unsupported.svg", "outcome": "unsupported"},
        ]


class FakeDB:
    def __init__(self) -> None:
        self.open_sessions = 0
        self.statement_timeouts: list[float] = []
        self.repo = FakeTokenImageRepo()

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == "token_image_mirror"
        self.statement_timeouts.append(statement_timeout_seconds)
        self.open_sessions += 1
        try:
            yield SimpleNamespace(conn=object(), token_image_assets=self.repo)
        finally:
            self.open_sessions -= 1
