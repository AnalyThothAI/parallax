from __future__ import annotations

from gmgn_twitter_intel.domains.evidence.services.entity_extractor import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.pipeline.token_evidence_builder import build_token_evidence
from tests.factories_token_radar import VERSA_BASE_CA, make_gmgn_payload_event


def test_token_evidence_preserves_versa_locality():
    text = f"很不错的一个项目，挺有格局的dev， $VERSA {VERSA_BASE_CA}"
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])

    evidence = build_token_evidence(
        event_id="event-versa",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )

    cashtag = next(item for item in evidence if item.evidence_type == "cashtag")
    ca = next(item for item in evidence if item.evidence_type == "ca")
    assert cashtag.normalized_symbol == "VERSA"
    assert ca.address_hint.lower() == VERSA_BASE_CA
    assert cashtag.local_group_key == ca.local_group_key
    assert cashtag.span_start < ca.span_start


def test_gmgn_payload_creates_strong_payload_evidence():
    event = make_gmgn_payload_event(symbol="PEPE")

    evidence = build_token_evidence(
        event_id=event.event_id,
        entities=[],
        token_snapshot=event.token_snapshot,
        created_at_ms=event.received_at_ms,
    )

    assert len(evidence) == 1
    assert evidence[0].evidence_type == "gmgn_token_payload"
    assert evidence[0].strength == "strong"
    assert evidence[0].normalized_symbol == "PEPE"


def test_gmgn_payload_address_like_symbol_does_not_become_display_symbol():
    address = "3iqrRNGG111111111111111111111111111111wNpump"
    event = make_gmgn_payload_event(symbol=address, chain="sol", address=address)

    evidence = build_token_evidence(
        event_id=event.event_id,
        entities=[],
        token_snapshot=event.token_snapshot,
        created_at_ms=event.received_at_ms,
    )

    assert len(evidence) == 1
    assert evidence[0].address_hint == address
    assert evidence[0].normalized_symbol is None
