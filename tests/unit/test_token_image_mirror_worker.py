from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

from parallax.domains.asset_market.runtime import token_image_mirror_worker as worker_module
from parallax.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker


def test_token_image_mirror_worker_mirrors_claimed_rows_outside_db_sessions(monkeypatch, tmp_path) -> None:
    db = FakeDB()
    settings = SimpleNamespace(
        enabled=True,
        interval_seconds=60,
        source_limit=2,
        batch_size=3,
        statement_timeout_seconds=120,
    )

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
        "selected": 4,
        "pending_upserted": 3,
        "ready_existing": 1,
        "unsupported_existing": 0,
        "claimed": 4,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "targets_loaded": 4,
        "rows_written": 3,
        "mirrored": 1,
        "error": 1,
        "unsupported": 1,
        "started_at_ms": 1_700_000_000_000,
        "finished_at_ms": 1_700_000_000_000,
    }
    assert result.processed == 4
    assert result.failed == 1
    assert db.statement_timeouts == [120, 120, 120, 120]
    assert db.repo.upserted_now_ms == 1_700_000_000_000
    assert db.dirty.claimed == {
        "now_ms": 1_700_000_000_000,
        "limit": 3,
        "lease_owner": "token_image_mirror",
        "lease_ms": 600_000,
        "commit": True,
    }
    assert db.repo.terminal_source_urls == [
        "https://gmgn.ai/external-res/ready.png",
        "https://gmgn.ai/external-res/new.png",
        "https://gmgn.ai/external-res/bad.png",
        "https://gmgn.ai/external-res/unsupported.svg",
    ]
    assert db.profile_dirty.enqueued_targets == [
        ("Asset", "asset-ready"),
        ("Asset", "asset-new"),
        ("Asset", "asset-unsupported"),
    ]


class FakeMirrorService:
    def __init__(self, *, db: FakeDB, repository, app_home) -> None:
        self.db = db
        self.repository = repository
        self.app_home = app_home

    def mirror_source(self, row, *, now_ms: int):
        assert now_ms == 1_700_000_000_000
        assert self.db.open_sessions == 0
        outcomes = {
            "https://gmgn.ai/external-res/new.png": "ready",
            "https://gmgn.ai/external-res/bad.png": "error",
            "https://gmgn.ai/external-res/unsupported.svg": "unsupported",
        }
        return {"status": outcomes[row["source_url"]], "source_url": row["source_url"]}


class FakeTokenImageRepo:
    def __init__(self) -> None:
        self.upserted_now_ms: int | None = None
        self.terminal_source_urls: list[str] = []

    def upsert_pending_sources(self, rows, *, now_ms: int, commit: bool = True):
        assert commit is False
        self.upserted_now_ms = now_ms
        return len(rows)

    def terminal_by_source_urls(self, source_urls):
        self.terminal_source_urls = list(source_urls)
        return {"https://gmgn.ai/external-res/ready.png": {"status": "ready"}}


class FakeDB:
    def __init__(self) -> None:
        self.open_sessions = 0
        self.statement_timeouts: list[float] = []
        self.repo = FakeTokenImageRepo()
        self.dirty = FakeImageSourceDirtyTargets()
        self.profile_dirty = FakeProfileDirtyTargets()

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == "token_image_mirror"
        self.statement_timeouts.append(statement_timeout_seconds)
        self.open_sessions += 1
        try:
            yield FakeRepos(self)
        finally:
            self.open_sessions -= 1


class FakeRepos:
    def __init__(self, db: FakeDB) -> None:
        self.conn = object()
        self.token_image_assets = db.repo
        self.token_image_source_dirty_targets = db.dirty
        self.token_profile_current_dirty_targets = db.profile_dirty

    def transaction(self):
        return nullcontext()


class FakeImageSourceDirtyTargets:
    def __init__(self) -> None:
        self.claimed: dict | None = None
        self.done: list[dict] = []
        self.errors: list[dict] = []

    def claim_due(self, **kwargs):
        self.claimed = dict(kwargs)
        return [
            image_claim("https://gmgn.ai/external-res/ready.png", "asset-ready", "ready"),
            image_claim("https://gmgn.ai/external-res/new.png", "asset-new", "ready"),
            image_claim("https://gmgn.ai/external-res/bad.png", "asset-bad", "error"),
            image_claim("https://gmgn.ai/external-res/unsupported.svg", "asset-unsupported", "unsupported"),
        ]

    def queue_depth(self, **kwargs):
        return 0

    def mark_done(self, claims, **kwargs):
        self.done.extend(dict(claim) for claim in claims)
        return len(claims)

    def mark_error(self, claims, *, error, **kwargs):
        self.errors.extend({**dict(claim), "error": error} for claim in claims)
        return len(claims)


class FakeProfileDirtyTargets:
    def __init__(self) -> None:
        self.enqueued_targets: list[tuple[str, str]] = []

    def enqueue_targets(self, targets, *, reason, now_ms, commit):
        self.enqueued_targets.extend((target["target_type"], target["target_id"]) for target in targets)
        return {"targets": len(targets)}


def image_claim(source_url: str, target_id: str, outcome: str) -> dict:
    return {
        "source_url": source_url,
        "source_url_hash": f"hash:{source_url}",
        "source_provider": "gmgn",
        "source_kind": "asset_profiles.logo_url",
        "target_type": "Asset",
        "target_id": target_id,
        "raw_ref_json": {"asset_id": target_id},
        "source_watermark_ms": 1_700_000_000_000,
        "payload_hash": f"payload:{source_url}",
        "lease_owner": "token_image_mirror",
        "attempt_count": 1,
        "outcome": outcome,
    }
