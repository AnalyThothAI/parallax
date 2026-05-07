from __future__ import annotations

from gmgn_twitter_intel.pipeline.entity_extractor import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.pipeline.token_evidence_builder import build_token_evidence
from gmgn_twitter_intel.pipeline.token_intent_builder import build_token_intents
from tests.factories_token_radar_v3 import VERSA_BASE_CA


def test_versa_cashtag_and_ca_are_one_intent():
    text = f"很不错的一个项目，挺有格局的dev， $VERSA {VERSA_BASE_CA}"
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])
    evidence = build_token_evidence(
        event_id="event-versa",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )

    intents = build_token_intents(event_id="event-versa", evidence=evidence, created_at_ms=1_777_800_000_000)

    assert len(intents) == 1
    assert intents[0].display_symbol == "VERSA"
    assert intents[0].address_hint.lower() == VERSA_BASE_CA
    assert {item.role for item in intents[0].evidence_links} == {"primary_identity", "display_alias"}
