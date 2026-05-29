from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh import (
    refresh_recent_token_state,
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


def test_reprocess_enqueues_dirty_targets_for_incremental_token_radar(monkeypatch):
    lookup = FakeLookup(
        rows=[
            {"intent_id": "intent-1", "event_id": "event-1", "primary_evidence_id": "evidence-1"},
            {"intent_id": "intent-2", "event_id": "event-2", "primary_evidence_id": "evidence-2"},
        ]
    )
    repos = FakeRepos(lookup=lookup)
    decisions = [
        SimpleNamespace(
            intent_id="intent-1",
            event_id="event-1",
            target_type="Asset",
            target_id="asset-1",
            lookup_keys=["symbol:ONE"],
        ),
        SimpleNamespace(
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
        "gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh.TokenIntentResolver",
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
    assert repos.token_radar_source_dirty_events.enqueues == [
        {
            "rows": [
                {"target_type_key": "Asset", "identity_id": "asset-1", "source_event_id": "event-1"},
            ],
            "reason": "resolution_refresh",
            "now_ms": 1_778_162_003_774,
            "commit": False,
        }
    ]
    assert repos.discovery.enqueues == [
        {
            "lookup_keys": ["symbol:TWO"],
            "reason": "resolution_refresh_unresolved",
            "now_ms": 1_778_162_003_774,
            "commit": False,
        }
    ]


def test_refresh_recent_token_state_defers_projection_to_worker(monkeypatch):
    def fake_reprocess(**kwargs):
        return {"reprocessed_intents": 1, "resolved_intents": 1}

    monkeypatch.setattr(
        "gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh.reprocess_recent_token_intents",
        fake_reprocess,
    )

    result = refresh_recent_token_state(
        repos=object(),
        lookup_keys=["symbol:HANTA"],
        now_ms=1_778_162_003_774,
    )

    assert result["reprocessed_intents"] == 1
    assert result["projection"] == {
        "status": "deferred_to_worker",
        "rows_written": 0,
        "source_rows": 0,
        "windows": {},
    }


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


class FakeRepos:
    def __init__(self, *, lookup):
        self.token_intent_lookup = lookup
        self.token_intents = lookup
        self.token_evidence = FakeTokenEvidence()
        self.registry = object()
        self.intent_resolutions = object()
        self.token_radar_source_dirty_events = FakeDirtyTargets()
        self.discovery = FakeDiscovery()
        self.conn = FakeConn()


class FakeTokenEvidence:
    def evidence_for_intent(self, intent_id):
        return []


class FakeDirtyTargets:
    def __init__(self):
        self.enqueues = []

    def enqueue_events(self, rows, *, reason, now_ms, commit):
        self.enqueues.append(
            {
                "rows": list(rows),
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )


class FakeDiscovery:
    def __init__(self):
        self.enqueues = []

    def enqueue_lookup_keys(self, lookup_keys, *, reason, now_ms, commit):
        self.enqueues.append(
            {
                "lookup_keys": list(lookup_keys),
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )


class FakeConn:
    def commit(self):
        return None
