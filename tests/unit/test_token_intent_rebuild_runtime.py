from __future__ import annotations

from types import SimpleNamespace

import pytest

from parallax.domains.token_intel.runtime import token_intent_rebuild
from parallax.domains.token_intel.runtime.token_intent_rebuild import (
    rebuild_event_token_intents,
    rebuild_recent_token_intents,
)


def test_rebuild_recent_token_intents_uses_session_transaction(monkeypatch) -> None:
    now_ms = 1_778_162_003_774
    event_row = _event_row(received_at_ms=now_ms - 1_000)
    query_calls: list[dict[str, int]] = []

    class FakeEventRebuildQuery:
        def __init__(self, conn):
            self.conn = conn

        def recent_events(self, *, since_ms, limit):
            query_calls.append({"since_ms": since_ms, "limit": limit})
            return [event_row]

    _install_rebuild_fakes(monkeypatch, FakeEventRebuildQuery)
    repos = FakeIntentRebuildRepos()

    result = rebuild_recent_token_intents(
        repos=repos,
        now_ms=now_ms,
        window="5m",
        limit=7,
        projection_limit=11,
    )

    assert query_calls == [{"since_ms": now_ms - token_intent_rebuild.WINDOW_MS["5m"], "limit": 7}]
    assert result["events_rebuilt"] == 1
    assert result["intents_written"] == 1
    assert result["resolved_intents"] == 1
    assert result["projection_limit"] == 11
    assert repos.transaction_entries == 1
    assert repos.transaction_exits == ["ok"]
    assert repos.required_operations == ["token_intent_rebuild"]
    assert repos.token_intents.deleted_event_ids == ["event-1"]
    assert repos.token_evidence.deleted_event_ids == ["event-1"]
    assert repos.token_intents.insert_commits == [False]
    assert repos.token_evidence.insert_commits == [False]
    assert repos.token_intent_lookup.replacements == [
        {
            "intent_id": "intent-1",
            "event_id": "event-1",
            "keys": ["address:solana:asset-1"],
            "source_evidence_id": "evidence-1",
            "created_at_ms": now_ms - 1_000,
            "commit": False,
        }
    ]


def test_rebuild_event_token_intents_requires_session_transaction_before_writes(monkeypatch) -> None:
    _install_rebuild_fakes(monkeypatch, object)
    repos = FakeIntentRebuildReposWithoutTransaction()

    with pytest.raises(AttributeError, match="transaction"):
        rebuild_event_token_intents(repos=repos, event_row=_event_row())

    assert repos.token_intents.deleted_event_ids == []
    assert repos.token_evidence.deleted_event_ids == []


def _install_rebuild_fakes(monkeypatch, query_cls) -> None:
    monkeypatch.setattr(token_intent_rebuild, "EventRebuildQuery", query_cls)
    monkeypatch.setattr(token_intent_rebuild, "extract_entities_from_surfaces", lambda surfaces: ["entity"])
    monkeypatch.setattr(token_intent_rebuild, "build_token_evidence", _fake_build_token_evidence)
    monkeypatch.setattr(token_intent_rebuild, "build_token_intents", _fake_build_token_intents)
    monkeypatch.setattr(token_intent_rebuild, "TokenIntentResolver", FakeResolver)


def _fake_build_token_evidence(**kwargs):
    return [
        SimpleNamespace(
            evidence_id="evidence-1",
            event_id=kwargs["event_id"],
        )
    ]


def _fake_build_token_intents(**kwargs):
    return [
        SimpleNamespace(
            intent_id="intent-1",
            event_id=kwargs["event_id"],
            primary_evidence_id="evidence-1",
            chain_hint=None,
            address_hint=None,
            display_symbol="AAA",
        )
    ]


class FakeResolver:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def resolve(self, intent, evidence, **kwargs):
        assert kwargs["persist"] is True
        assert "commit" not in kwargs
        return SimpleNamespace(
            intent_id=intent.intent_id,
            event_id=intent.event_id,
            target_type="Asset",
            target_id="asset-1",
            lookup_keys=["address:solana:asset-1"],
        )


class FakeIntentRebuildRepos:
    def __init__(self):
        self.conn = object()
        self.token_intents = FakeIntentWrites()
        self.token_evidence = FakeEvidenceWrites()
        self.registry = object()
        self.intent_resolutions = object()
        self.token_intent_lookup = FakeLookupWrites()
        self.identity_evidence = object()
        self.required_operations: list[str] = []
        self.transaction_depth = 0
        self.transaction_entries = 0
        self.transaction_exits: list[str] = []

    def transaction(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation):
        if self.transaction_depth < 1:
            raise AssertionError(f"{operation} ran outside session transaction")
        self.required_operations.append(operation)


class FakeIntentRebuildReposWithoutTransaction:
    def __init__(self):
        self.conn = object()
        self.token_intents = FakeIntentWrites()
        self.token_evidence = FakeEvidenceWrites()
        self.registry = object()
        self.intent_resolutions = object()
        self.token_intent_lookup = FakeLookupWrites()
        self.identity_evidence = object()


class FakeTransaction:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        self.repos.transaction_depth += 1
        self.repos.transaction_entries += 1

    def __exit__(self, exc_type, exc, tb):
        self.repos.transaction_depth -= 1
        self.repos.transaction_exits.append(exc_type.__name__ if exc_type else "ok")
        return False


class FakeIntentWrites:
    def __init__(self):
        self.deleted_event_ids: list[str] = []
        self.insert_commits: list[bool] = []

    def delete_by_event_id(self, event_id):
        self.deleted_event_ids.append(event_id)

    def insert_many(self, intents, *, commit):
        self.insert_commits.append(commit)
        return list(intents)


class FakeEvidenceWrites(FakeIntentWrites):
    pass


class FakeLookupWrites:
    def __init__(self):
        self.replacements: list[dict[str, object]] = []

    def replace_lookup_keys(self, **kwargs):
        self.replacements.append(dict(kwargs))


def _event_row(*, received_at_ms: int = 1_778_162_002_774) -> dict[str, object]:
    return {
        "event_id": "event-1",
        "received_at_ms": received_at_ms,
        "text": "$AAA is moving",
        "reference_json": None,
        "event_json": None,
    }
