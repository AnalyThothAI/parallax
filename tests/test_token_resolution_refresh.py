from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_resolution_refresh import reprocess_recent_token_intents


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


class FakeLookup:
    def __init__(self):
        self.calls = []

    def recent_intents_for_lookup_keys(self, keys, *, since_ms, limit):
        self.calls.append({"keys": list(keys), "since_ms": since_ms, "limit": limit})
        return []


class FakeRepos:
    def __init__(self, *, lookup):
        self.token_intent_lookup = lookup
        self.registry = object()
        self.intent_resolutions = object()
        self.conn = FakeConn()


class FakeConn:
    def commit(self):
        return None
