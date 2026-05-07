from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_projection import TokenRadarProjection
from tests.factories_token_radar_v3 import VERSA_BASE_CA, insert_base_versa_asset, make_v3_event, open_v3_runtime


def test_versa_symbol_and_ca_build_one_intent(tmp_path):
    _, repos, ingest = open_v3_runtime(tmp_path)
    insert_base_versa_asset(repos.assets, observed_at_ms=1_777_799_000_000)
    event = make_v3_event(
        text=f"很不错的一个项目，挺有格局的dev， $VERSA {VERSA_BASE_CA}",
        received_at_ms=1_777_800_000_000,
    )

    result = ingest.ingest_event(event, is_watched=True)

    intents = repos.token_intents.intents_for_event("event-versa")
    resolutions = repos.intent_resolutions.resolutions_for_event("event-versa")
    assert len(intents) == 1
    assert intents[0]["display_symbol"] == "VERSA"
    assert intents[0]["address_hint"].lower() == VERSA_BASE_CA
    assert len(resolutions) == 1
    assert resolutions[0]["identity_status"] == "resolved"
    assert resolutions[0]["primary_venue_id"] == f"venue:dex:base:{VERSA_BASE_CA}"
    assert result.token_intents[0]["intent_id"] == intents[0]["intent_id"]
    assert result.token_resolutions[0]["resolution_id"] == resolutions[0]["resolution_id"]


def test_unresolved_attention_never_projects_as_driver(tmp_path):
    _, repos, ingest = open_v3_runtime(tmp_path)
    for index in range(7):
        ingest.ingest_event(
            make_v3_event(
                event_id=f"event-hanta-{index}",
                text="$HANTA new burst",
                received_at_ms=1_777_800_000_000 + index,
                author_handle=f"voice{index}",
            ),
            is_watched=True,
        )

    TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=1_777_800_060_000)
    rows = repos.token_radar.latest_rows(window="5m", scope="all", limit=20)

    hanta = next(row for row in rows if row["intent_json"]["display_symbol"] == "HANTA")
    assert hanta["decision"] == "investigate"
    assert hanta["market_json"]["market_observation_status"] == "no_venue"
