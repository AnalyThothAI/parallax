from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.surfaces.cli.commands import ops


def test_rebuild_narrative_intel_reports_cleanup_and_final_health(monkeypatch) -> None:
    db = _FakeDB()
    settings = SimpleNamespace(
        workers=SimpleNamespace(
            narrative_admission=SimpleNamespace(),
            mention_semantics=SimpleNamespace(),
            token_discussion_digest=SimpleNamespace(),
        )
    )
    monkeypatch.setattr(ops.DBPoolBundle, "create", lambda *_args, **_kwargs: db)
    monkeypatch.setattr(ops.LLMGateway, "create", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ops, "build_agent_execution_gateway", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        ops,
        "wire_providers",
        lambda *_args, **_kwargs: SimpleNamespace(
            narrative_intel=SimpleNamespace(narrative_provider=object())
        ),
    )
    monkeypatch.setattr(ops, "_cleanup_provider_roots_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ops, "NarrativeAdmissionWorker", _FakeWorker)
    monkeypatch.setattr(ops, "MentionSemanticsWorker", _FakeWorker)
    monkeypatch.setattr(ops, "TokenDiscussionDigestWorker", _FakeWorker)
    monkeypatch.setattr(ops, "NarrativeBacklogHealthQuery", _FakeHealthQuery, raising=False)

    data = ops._run_narrative_intel_rebuild(
        settings,
        window="24h",
        scope="matched",
        semantic_limit=10,
        digest_limit=5,
        cycles=1,
        drain=False,
        now_ms=100,
    )

    assert data["cleanup"] == {
        "deleted_obsolete_pending_semantics": 2,
        "stale_suppressed_digests": 1,
        "stale_fingerprint_mismatch_digests": 3,
    }
    assert data["results"][0]["cleanup"] == data["cleanup"]
    assert data["final_health"]["semantic_backlog"]["missing_semantic_rows"] == 4
    assert db.cleanup_called_while_locks == [
        "narrative_admission",
        "mention_semantics",
        "token_discussion_digest",
    ]


def test_cleanup_narrative_backlog_prefers_hard_cut_repository_method() -> None:
    db = _FakeDB()

    cleanup = ops._cleanup_narrative_backlog(db, window="24h", scope="matched", now_ms=100)

    assert cleanup == {
        "deleted_obsolete_pending_semantics": 2,
        "stale_suppressed_digests": 1,
        "stale_fingerprint_mismatch_digests": 3,
    }
    assert db.repos.narratives.calls == [
        {
            "method": "cleanup_narrative_current_hard_cut",
            "schema_version": "narrative_intel_v1",
            "window": "24h",
            "scope": "matched",
            "now_ms": 100,
        }
    ]


class _FakeWorker:
    SINGLE_WRITER_KEY = 42

    def __init__(self, *, name: str, **_kwargs: Any) -> None:
        self.name = name

    async def run_once(self, *, now_ms: int) -> SimpleNamespace:
        return SimpleNamespace(processed=1, failed=0, dead=0, skipped=0, notes={"now_ms": now_ms})

    async def aclose(self) -> None:
        return None


class _FakeDB:
    def __init__(self) -> None:
        self.repos = SimpleNamespace(conn=object(), narratives=_FakeNarratives(self))
        self.locked: list[str] = []
        self.cleanup_called_while_locks: list[str] = []
        self.api_pool = self.worker_pool = self.lock_pool = self.tool_pool = self.wake_pool = _FakePool()

    def acquire_advisory_lock_connection(self, worker_name: str, _lock_key: int) -> _FakeLock:
        self.locked.append(worker_name)
        return _FakeLock(self, worker_name)

    def wake_emitter(self) -> object:
        return object()

    @contextmanager
    def worker_session(self, _name: str):
        yield self.repos


class _FakeLock:
    def __init__(self, db: _FakeDB, worker_name: str) -> None:
        self.db = db
        self.worker_name = worker_name

    def release(self) -> None:
        if self.worker_name in self.db.locked:
            self.db.locked.remove(self.worker_name)


class _FakePool:
    def close(self) -> None:
        return None


class _FakeNarratives:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db
        self.calls: list[dict[str, Any]] = []

    def cleanup_narrative_current_hard_cut(self, **kwargs: Any) -> dict[str, int]:
        self.db.cleanup_called_while_locks = list(self.db.locked)
        self.calls.append({"method": "cleanup_narrative_current_hard_cut", **kwargs})
        return {
            "deleted_obsolete_pending_semantics": 2,
            "stale_suppressed_digests": 1,
            "stale_fingerprint_mismatch_digests": 3,
        }


class _FakeHealthQuery:
    def __init__(self, _conn: object) -> None:
        pass

    def health(self, *, now_ms: int, since_hours: int) -> dict[str, Any]:
        return {
            "now_ms": now_ms,
            "since_hours": since_hours,
            "semantic_backlog": {"missing_semantic_rows": 4},
        }
