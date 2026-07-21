from __future__ import annotations

import pytest

from parallax.domains.evidence.services.ingest_service import _dirty_targets_for_resolutions
from parallax.domains.token_intel.services.deterministic_token_resolver import DeterministicResolution


def test_dirty_targets_for_resolutions_uses_formal_target_identity() -> None:
    rows = _dirty_targets_for_resolutions(
        [
            _decision(
                event_id="event-1",
                intent_id="intent-1",
                target_type="Asset",
                target_id="asset-1",
            )
        ]
    )

    assert rows == [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
        }
    ]


def test_dirty_targets_for_resolutions_skips_unresolved_intent_identity() -> None:
    rows = _dirty_targets_for_resolutions(
        [
            _decision(
                event_id="event-1",
                intent_id="intent-unresolved",
                target_type=None,
                target_id=None,
                resolution_status="NIL",
            )
        ]
    )

    assert rows == []


def test_dirty_targets_for_resolutions_requires_formal_resolution_decision() -> None:
    class LooseDecision:
        def __init__(self) -> None:
            self.event_id = "event-1"
            self.intent_id = "intent-1"
            self.target_type = "Asset"
            self.target_id = "asset-1"

    with pytest.raises(RuntimeError, match="ingest_resolution_decision_contract_required"):
        _dirty_targets_for_resolutions([LooseDecision()])  # type: ignore[list-item]


def _decision(
    *,
    event_id: str,
    intent_id: str,
    target_type: str | None,
    target_id: str | None,
    resolution_status: str = "EXACT",
) -> DeterministicResolution:
    return DeterministicResolution(
        intent_id=intent_id,
        event_id=event_id,
        resolution_status=resolution_status,
        target_type=target_type,
        target_id=target_id,
        pricefeed_id=None,
        resolver_policy_version="test",
        reason_codes=[],
        candidate_ids=[],
        lookup_keys=["symbol:TEST"],
        decision_time_ms=1_778_162_003_774,
        created_at_ms=1_778_162_003_774,
    )
