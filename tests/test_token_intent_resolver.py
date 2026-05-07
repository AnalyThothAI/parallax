from __future__ import annotations

from gmgn_twitter_intel.pipeline.entity_extractor import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.pipeline.token_evidence_builder import build_token_evidence
from gmgn_twitter_intel.pipeline.token_intent_builder import build_token_intents
from gmgn_twitter_intel.pipeline.token_intent_resolver import TokenIntentResolver
from tests.factories_token_radar_v3 import VERSA_BASE_CA, insert_base_versa_asset, open_v3_runtime


def test_no_chain_ca_uses_local_exact_venue_before_provider(tmp_path):
    _, repos, _ = open_v3_runtime(tmp_path)
    insert_base_versa_asset(repos.assets, observed_at_ms=1_777_799_000_000)
    text = f"$VERSA {VERSA_BASE_CA}"
    entities = extract_entities_from_surfaces([TextSurface("primary", text)])
    evidence = build_token_evidence(
        event_id="event-versa",
        entities=entities,
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )
    intent = build_token_intents(event_id="event-versa", evidence=evidence, created_at_ms=1_777_800_000_000)[0]

    decision = TokenIntentResolver(assets=repos.assets, resolutions=repos.intent_resolutions).resolve(intent, evidence)

    assert decision.identity_status == "resolved"
    assert decision.asset_id == f"asset:dex:base:{VERSA_BASE_CA}"
    assert decision.primary_venue_id == f"venue:dex:base:{VERSA_BASE_CA}"
    assert decision.reasons == ["local_exact_ca_match"]
