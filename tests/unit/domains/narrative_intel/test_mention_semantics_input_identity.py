from __future__ import annotations

from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import (
    _hash_json,
    _mention_semantics_input_rows,
)


def test_mention_semantics_input_hash_ignores_claim_metadata() -> None:
    row = {
        "event_id": "event-1",
        "target_type": "asset",
        "target_id": "asset:btc",
        "text_clean": "BTC ETF flows accelerated.",
        "text_fingerprint": "text-hash",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }
    changed_claim = {**row, "lease_owner": "worker-b", "attempt_count": 4}

    assert _hash_json(_mention_semantics_input_rows([row])) == _hash_json(
        _mention_semantics_input_rows([changed_claim])
    )
