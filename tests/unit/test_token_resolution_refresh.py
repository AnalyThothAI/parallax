from __future__ import annotations

import pytest

from parallax.domains.token_intel.services.deterministic_token_resolver import DeterministicResolution
from parallax.domains.token_intel.services.token_resolution_refresh import (
    reprocess_recent_token_intents,
)


def test_lookup_key_reprocess_uses_all_recent_matching_intents_not_only_unresolved():
    lookup = FakeLookup()
    repos = FakeRepos(lookup=lookup)

    result = reprocess_recent_token_intents(
        repos=repos,
        lookup_keys=["symbol:SLOP"],
        now_ms=1_778_162_003_774,
        window="24h",
        limit=500,
    )

    assert lookup.calls == [{"keys": ["symbol:SLOP"], "since_ms": 1_778_075_603_774, "limit": 500}]
    assert result["reprocessed_intents"] == 0
    assert repos.transaction_entries == 1
    assert repos.required_operations == ["token_resolution_refresh"]


def test_reprocess_enqueues_dirty_targets_for_incremental_token_radar(monkeypatch):
    lookup = FakeLookup(
        rows=[
            {"intent_id": "intent-1", "event_id": "event-1", "primary_evidence_id": "evidence-1"},
            {"intent_id": "intent-2", "event_id": "event-2", "primary_evidence_id": "evidence-2"},
        ]
    )
    repos = FakeRepos(lookup=lookup)
    decisions = [
        _decision(
            intent_id="intent-1",
            event_id="event-1",
            target_type="Asset",
            target_id="asset-1",
            lookup_keys=["symbol:ONE"],
        ),
        _decision(
            intent_id="intent-2",
            event_id="event-2",
            target_type=None,
            target_id=None,
            lookup_keys=["symbol:TWO"],
        ),
    ]

    class FakeResolver:
        def __init__(self, **kwargs):
            self.decisions = list(decisions)

        def resolve(self, *args, **kwargs):
            return self.decisions.pop(0)

    monkeypatch.setattr(
        "parallax.domains.token_intel.services.token_resolution_refresh.TokenIntentResolver",
        FakeResolver,
    )

    result = reprocess_recent_token_intents(
        repos=repos,
        lookup_keys=["symbol:ONE", "symbol:TWO"],
        now_ms=1_778_162_003_774,
        window="24h",
        limit=500,
    )

    assert result["reprocessed_intents"] == 2
    assert result["resolved_intents"] == 1
    assert result["dirty_targets"] == 1
    assert repos.token_radar_dirty_targets.enqueues == [
        {
            "rows": [
                {"target_type_key": "Asset", "identity_id": "asset-1"},
            ],
            "reason": "resolution_refresh",
            "now_ms": 1_778_162_003_774,
        }
    ]
    assert repos.discovery.enqueues == [
        {
            "lookup_keys": ["symbol:TWO"],
            "reason": "resolution_refresh_unresolved",
            "now_ms": 1_778_162_003_774,
        }
    ]
    assert repos.transaction_entries == 1
    assert repos.required_operations == ["token_resolution_refresh"]


def test_reprocess_batches_evidence_for_recent_intents(monkeypatch):
    lookup = FakeLookup(
        rows=[
            {"intent_id": "intent-1", "event_id": "event-1", "primary_evidence_id": "evidence-1"},
            {"intent_id": "intent-2", "event_id": "event-2", "primary_evidence_id": "evidence-2"},
        ]
    )
    repos = FakeRepos(lookup=lookup)
    repos.token_evidence = FakeTokenEvidence(
        evidence_by_intent={
            "intent-1": [{"evidence_id": "evidence-1", "raw_value": "$ONE"}],
            "intent-2": [{"evidence_id": "evidence-2", "raw_value": "$TWO"}],
        }
    )
    seen_evidence: list[tuple[str, list[dict[str, object]]]] = []

    class FakeResolver:
        def __init__(self, **kwargs):
            pass

        def resolve(self, intent, evidence, **kwargs):
            seen_evidence.append((str(intent["intent_id"]), list(evidence)))
            return _decision(
                intent_id=str(intent["intent_id"]),
                event_id=str(intent["event_id"]),
                target_type="Asset",
                target_id=f"asset-{intent['intent_id']}",
                lookup_keys=[f"symbol:{intent['intent_id'].upper()}"],
            )

    monkeypatch.setattr(
        "parallax.domains.token_intel.services.token_resolution_refresh.TokenIntentResolver",
        FakeResolver,
    )

    result = reprocess_recent_token_intents(
        repos=repos,
        lookup_keys=["symbol:ONE", "symbol:TWO"],
        now_ms=1_778_162_003_774,
        window="24h",
        limit=500,
    )

    assert result["reprocessed_intents"] == 2
    assert repos.token_evidence.batch_calls == [("intent-1", "intent-2")]
    assert repos.token_evidence.single_calls == []
    assert seen_evidence == [
        ("intent-1", [{"evidence_id": "evidence-1", "raw_value": "$ONE"}]),
        ("intent-2", [{"evidence_id": "evidence-2", "raw_value": "$TWO"}]),
    ]


def test_reprocess_requires_token_radar_dirty_target_repository(monkeypatch):
    lookup = FakeLookup(rows=[{"intent_id": "intent-1", "event_id": "event-1", "primary_evidence_id": "evidence-1"}])
    repos = FakeReposWithoutDirtyTargets(lookup=lookup)

    class FakeResolver:
        def __init__(self, **kwargs):
            pass

        def resolve(self, *args, **kwargs):
            return _decision(
                intent_id="intent-1",
                event_id="event-1",
                target_type="Asset",
                target_id="asset-1",
                lookup_keys=["symbol:ONE"],
            )

    monkeypatch.setattr(
        "parallax.domains.token_intel.services.token_resolution_refresh.TokenIntentResolver",
        FakeResolver,
    )

    with pytest.raises(AttributeError, match="token_radar_dirty_targets"):
        reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=["symbol:ONE"],
            now_ms=1_778_162_003_774,
            window="24h",
            limit=500,
        )

    assert repos.conn.commits == 0
    assert repos.transaction_entries == 1
    assert repos.transaction_exits == ["AttributeError"]


def test_reprocess_requires_formal_resolution_decision_before_dirty_enqueue(monkeypatch):
    lookup = FakeLookup(rows=[{"intent_id": "intent-1", "event_id": "event-1", "primary_evidence_id": "evidence-1"}])
    repos = FakeRepos(lookup=lookup)

    class LooseDecision:
        def __init__(self) -> None:
            self.intent_id = "intent-1"
            self.event_id = "event-1"
            self.target_type = "Asset"
            self.target_id = "asset-1"
            self.lookup_keys = ["symbol:ONE"]

    class FakeResolver:
        def __init__(self, **kwargs):
            pass

        def resolve(self, *args, **kwargs):
            return LooseDecision()

    monkeypatch.setattr(
        "parallax.domains.token_intel.services.token_resolution_refresh.TokenIntentResolver",
        FakeResolver,
    )

    with pytest.raises(RuntimeError, match="token_resolution_refresh_decision_contract_required"):
        reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=["symbol:ONE"],
            now_ms=1_778_162_003_774,
            window="24h",
            limit=500,
        )

    assert repos.token_radar_dirty_targets.enqueues == []
    assert repos.transaction_entries == 1
    assert repos.transaction_exits == ["RuntimeError"]


def test_reprocess_requires_session_transaction_before_lookup_query() -> None:
    lookup = FakeLookup()
    repos = FakeReposWithoutTransaction(lookup=lookup)

    with pytest.raises(AttributeError, match="transaction"):
        reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=["symbol:ONE"],
            now_ms=1_778_162_003_774,
            window="24h",
            limit=500,
        )

    assert lookup.calls == []


def test_reprocess_requires_explicit_window_and_limit_contract() -> None:
    lookup = FakeLookup()
    repos = FakeRepos(lookup=lookup)

    with pytest.raises(TypeError, match="window"):
        reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=["symbol:ONE"],
            now_ms=1_778_162_003_774,
            limit=500,
        )
    with pytest.raises(TypeError, match="limit"):
        reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=["symbol:ONE"],
            now_ms=1_778_162_003_774,
            window="24h",
        )

    assert lookup.calls == []
    assert repos.transaction_entries == 0


class FakeLookup:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = list(rows or [])

    def recent_intents_for_lookup_keys(self, keys, *, since_ms, limit):
        self.calls.append({"keys": list(keys), "since_ms": since_ms, "limit": limit})
        return list(self.rows)

    def recent_unresolved(self, *, since_ms, limit):
        self.calls.append({"keys": None, "since_ms": since_ms, "limit": limit})
        return list(self.rows)

    def replace_lookup_keys(self, **kwargs):
        return None


def _decision(
    *,
    intent_id: str,
    event_id: str,
    target_type: str | None,
    target_id: str | None,
    lookup_keys: list[str],
) -> DeterministicResolution:
    return DeterministicResolution(
        intent_id=intent_id,
        event_id=event_id,
        resolution_status="resolved" if target_type and target_id else "nil",
        target_type=target_type,
        target_id=target_id,
        pricefeed_id=None,
        resolver_policy_version="test",
        reason_codes=[],
        candidate_ids=[],
        lookup_keys=lookup_keys,
        decision_time_ms=1_778_162_003_774,
        created_at_ms=1_778_162_003_774,
    )


class FakeRepos:
    def __init__(self, *, lookup):
        self.token_intent_lookup = lookup
        self.token_intents = lookup
        self.token_evidence = FakeTokenEvidence()
        self.registry = object()
        self.intent_resolutions = object()
        self.token_radar_dirty_targets = FakeDirtyTargets()
        self.discovery = FakeDiscovery()
        self.conn = FakeConn()
        self.required_operations = []
        self.transaction_depth = 0
        self.transaction_entries = 0
        self.transaction_exits = []

    def transaction(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation):
        if self.transaction_depth < 1:
            raise AssertionError(f"{operation} ran outside session transaction")
        self.required_operations.append(operation)


class FakeReposWithoutDirtyTargets(FakeRepos):
    def __init__(self, *, lookup):
        super().__init__(lookup=lookup)
        del self.token_radar_dirty_targets


class FakeReposWithoutTransaction:
    def __init__(self, *, lookup):
        self.token_intent_lookup = lookup
        self.token_intents = lookup
        self.token_evidence = FakeTokenEvidence()
        self.registry = object()
        self.intent_resolutions = object()
        self.token_radar_dirty_targets = FakeDirtyTargets()
        self.discovery = FakeDiscovery()
        self.conn = FakeConn()


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


class FakeTokenEvidence:
    def __init__(self, evidence_by_intent=None):
        self.evidence_by_intent = {str(intent_id): list(rows) for intent_id, rows in (evidence_by_intent or {}).items()}
        self.batch_calls: list[tuple[str, ...]] = []
        self.single_calls: list[str] = []

    def evidence_for_intents(self, intent_ids):
        requested = tuple(str(intent_id) for intent_id in intent_ids)
        self.batch_calls.append(requested)
        return {intent_id: list(self.evidence_by_intent.get(intent_id, [])) for intent_id in requested}

    def evidence_for_intent(self, intent_id):
        self.single_calls.append(str(intent_id))
        return []


class FakeDirtyTargets:
    def __init__(self):
        self.enqueues = []

    def enqueue_targets(self, rows, *, reason, now_ms):
        self.enqueues.append(
            {
                "rows": list(rows),
                "reason": reason,
                "now_ms": now_ms,
            }
        )


class FakeDiscovery:
    def __init__(self):
        self.enqueues = []

    def enqueue_lookup_keys(self, lookup_keys, *, reason, now_ms):
        self.enqueues.append(
            {
                "lookup_keys": list(lookup_keys),
                "reason": reason,
                "now_ms": now_ms,
            }
        )


class FakeConn:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1
