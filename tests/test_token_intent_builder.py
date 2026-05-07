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


def test_symbol_and_ca_split_by_price_decimals_are_one_intent():
    text = "$MOONCLUB result: 4.1xX 90K -> 371K Time: 3h 69PzM2hDa3MCo7cvKPgiPxhr1FdGdMV3S7h6wpRkpump Source: SOLANA"
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])
    evidence = build_token_evidence(
        event_id="event-moonclub",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )

    intents = build_token_intents(event_id="event-moonclub", evidence=evidence, created_at_ms=1_777_800_000_000)

    assert len(intents) == 1
    assert intents[0].display_symbol == "MOONCLUB"
    assert intents[0].chain_hint == "solana"
    assert intents[0].address_hint == "69PzM2hDa3MCo7cvKPgiPxhr1FdGdMV3S7h6wpRkpump"


def test_single_cross_surface_cashtag_and_ca_are_one_intent():
    primary = "You’ll own $NOTHING and be happy."
    reference = "Could be something, but you will own solana:F7pB3ZdfBnyFw2LRHydWEn9BmhEa5XihXLjhySFRpump"
    entities = extract_entities_from_surfaces(
        [
            TextSurface("primary", primary),
            TextSurface("reference", reference),
        ]
    )
    evidence = build_token_evidence(
        event_id="event-nothing",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )

    intents = build_token_intents(event_id="event-nothing", evidence=evidence, created_at_ms=1_777_800_000_000)

    assert len(intents) == 1
    assert intents[0].display_symbol == "NOTHING"
    assert intents[0].chain_hint == "solana"
    assert intents[0].address_hint == "F7pB3ZdfBnyFw2LRHydWEn9BmhEa5XihXLjhySFRpump"


def test_multiple_cashtags_and_cas_pair_by_nearest_identity_without_symbol_only_intents():
    text = (
        "$ALPHA 0x1111111111111111111111111111111111111111 "
        "and $BETA 0x2222222222222222222222222222222222222222"
    )
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])
    evidence = build_token_evidence(
        event_id="event-multi",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )

    intents = build_token_intents(event_id="event-multi", evidence=evidence, created_at_ms=1_777_800_000_000)

    assert len(intents) == 2
    by_symbol = {intent.display_symbol: intent for intent in intents}
    assert set(by_symbol) == {"ALPHA", "BETA"}
    assert by_symbol["ALPHA"].address_hint == "0x1111111111111111111111111111111111111111"
    assert by_symbol["BETA"].address_hint == "0x2222222222222222222222222222222222222222"
    assert all(intent.intent_key.startswith("ca:") for intent in intents)
