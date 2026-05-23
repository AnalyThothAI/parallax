from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)
from gmgn_twitter_intel.domains.asset_market.queries.token_image_source_query import TokenImageSourceQuery
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import (
    BINANCE_WEB3_PROFILE_PROVIDER,
    GMGN_DEX_PROFILE_PROVIDER,
    AssetProfileRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_token_image_source_query_reads_current_and_recent_sources_without_old_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        radar_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-radar-asset",
            intent_id="intent-radar-asset",
            resolution_id="resolution-radar-asset",
            chain_id="eip155:1",
            address="0x1111111111111111111111111111111111111111",
            received_at_ms=NOW_MS - 60_000,
        )
        recent_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-recent-asset",
            intent_id="intent-recent-asset",
            resolution_id="resolution-recent-asset",
            chain_id="eip155:1",
            address="0x2222222222222222222222222222222222222222",
            received_at_ms=NOW_MS - 30_000,
        )
        stale_asset_id = _insert_resolved_asset(
            conn,
            event_id="event-stale-asset",
            intent_id="intent-stale-asset",
            resolution_id="resolution-stale-asset",
            chain_id="eip155:1",
            address="0x3333333333333333333333333333333333333333",
            received_at_ms=NOW_MS - (25 * 60 * 60 * 1000),
        )
        cex_token_id = "cex_token:BTC"
        unrelated_cex_token_id = "cex_token:ETH"
        _insert_cex_token(conn, cex_token_id=cex_token_id, base_symbol="BTC")
        _insert_cex_token(conn, cex_token_id=unrelated_cex_token_id, base_symbol="ETH")
        _insert_radar_row(
            conn,
            row_id="radar-asset",
            event_id="event-radar-asset",
            intent_id="intent-radar-asset",
            target_type="Asset",
            target_id=radar_asset_id,
            rank=1,
            computed_at_ms=NOW_MS - 10_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-cex",
            event_id="event-radar-asset",
            intent_id="intent-radar-asset",
            target_type="CexToken",
            target_id=cex_token_id,
            rank=2,
            computed_at_ms=NOW_MS - 10_000,
        )
        _insert_radar_coverage(conn, window="24h", scope="all", computed_at_ms=NOW_MS - 10_000)
        _insert_asset_profile(
            conn,
            asset_id=radar_asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            logo_url="https://gmgn.ai/external-res/radar-profile.png",
        )
        _insert_asset_profile(
            conn,
            asset_id=radar_asset_id,
            provider=BINANCE_WEB3_PROFILE_PROVIDER,
            logo_url="https://bin.bnbstatic.com/static/images/radar-web3.png",
        )
        _insert_identity_evidence(
            conn,
            evidence_id="evidence-gmgn-radar",
            asset_id=radar_asset_id,
            provider="gmgn",
            evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
            raw_payload={"i": "https://gmgn.ai/external-res/radar-stream.gif"},
        )
        _insert_identity_evidence(
            conn,
            evidence_id="evidence-okx-radar",
            asset_id=radar_asset_id,
            provider="okx",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            raw_payload={"tokenLogoUrl": "https://static.okx.com/cdn/radar-okx.webp"},
        )
        _insert_asset_profile(
            conn,
            asset_id=recent_asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            logo_url="https://gmgn.ai/external-res/recent-profile.png",
        )
        _insert_asset_profile(
            conn,
            asset_id=stale_asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            logo_url="https://gmgn.ai/external-res/stale-profile.png",
        )
        _insert_identity_evidence(
            conn,
            evidence_id="evidence-gmgn-stale",
            asset_id=stale_asset_id,
            provider="gmgn",
            evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
            raw_payload={"i": "https://gmgn.ai/external-res/stale-stream.png"},
        )
        _insert_identity_evidence(
            conn,
            evidence_id="evidence-okx-stale",
            asset_id=stale_asset_id,
            provider="okx",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            raw_payload={"tokenLogoUrl": "https://static.okx.com/cdn/stale-okx.png"},
        )
        _insert_cex_profile(
            conn,
            cex_token_id=cex_token_id,
            logo_url="https://bin.bnbstatic.com/static/images/btc.png",
        )
        _insert_cex_profile(
            conn,
            cex_token_id=unrelated_cex_token_id,
            logo_url="https://bin.bnbstatic.com/static/images/eth.png",
        )
        conn.commit()

        rows = TokenImageSourceQuery(conn).candidate_sources(now_ms=NOW_MS, source_limit=20)
        limited_rows = TokenImageSourceQuery(conn).candidate_sources(now_ms=NOW_MS, source_limit=2)
    finally:
        conn.close()

    by_url = {row["source_url"]: row for row in rows}
    assert set(by_url) == {
        "https://gmgn.ai/external-res/radar-profile.png",
        "https://bin.bnbstatic.com/static/images/radar-web3.png",
        "https://gmgn.ai/external-res/radar-stream.gif",
        "https://static.okx.com/cdn/radar-okx.webp",
        "https://gmgn.ai/external-res/recent-profile.png",
        "https://bin.bnbstatic.com/static/images/btc.png",
    }
    assert by_url["https://gmgn.ai/external-res/radar-profile.png"]["source_provider"] == GMGN_DEX_PROFILE_PROVIDER
    assert by_url["https://gmgn.ai/external-res/radar-profile.png"]["source_kind"] == "asset_profiles.logo_url"
    assert by_url["https://gmgn.ai/external-res/radar-profile.png"]["raw_ref_json"] == {
        "asset_id": radar_asset_id,
        "provider": GMGN_DEX_PROFILE_PROVIDER,
    }
    assert by_url["https://gmgn.ai/external-res/radar-stream.gif"]["source_provider"] == "gmgn_stream_snapshot"
    assert by_url["https://gmgn.ai/external-res/radar-stream.gif"]["source_kind"] == (
        "asset_identity_evidence.raw_payload_json.i"
    )
    assert by_url["https://gmgn.ai/external-res/radar-stream.gif"]["raw_ref_json"] == {
        "asset_id": radar_asset_id,
        "evidence_id": "evidence-gmgn-radar",
        "evidence_kind": EVIDENCE_GMGN_PAYLOAD_EXACT,
        "provider": "gmgn",
    }
    assert by_url["https://bin.bnbstatic.com/static/images/btc.png"]["raw_ref_json"] == {
        "cex_token_id": cex_token_id,
        "provider": "binance_cex_profile",
        "source_ref": "binance_marketing_symbol_list:BTC",
    }
    assert "https://gmgn.ai/external-res/stale-profile.png" not in by_url
    assert "https://gmgn.ai/external-res/stale-stream.png" not in by_url
    assert "https://static.okx.com/cdn/stale-okx.png" not in by_url
    assert "https://bin.bnbstatic.com/static/images/eth.png" not in by_url
    assert len(limited_rows) == 2


def _insert_resolved_asset(
    conn: Any,
    *,
    event_id: str,
    intent_id: str,
    resolution_id: str,
    chain_id: str,
    address: str,
    received_at_ms: int,
) -> str:
    _insert_event(conn, event_id=event_id, received_at_ms=received_at_ms)
    _insert_intent(conn, intent_id=intent_id, event_id=event_id, observed_at_ms=received_at_ms)
    asset = RegistryRepository(conn).upsert_chain_asset(
        chain_id=chain_id,
        address=address,
        observed_at_ms=received_at_ms,
        commit=False,
    )
    asset_id = str(asset["asset_id"])
    _insert_resolution(
        conn,
        resolution_id=resolution_id,
        intent_id=intent_id,
        event_id=event_id,
        target_type="Asset",
        target_id=asset_id,
        observed_at_ms=received_at_ms,
    )
    return asset_id


def _insert_event(conn: Any, *, event_id: str, received_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO events(
          event_id, logical_dedup_key, source_provider, source_transport, coverage,
          channel, action, timestamp_ms, received_at_ms, author_tags_json, urls_json,
          cashtags_json, hashtags_json, mentions_json, media_json, matched_handles_json,
          is_watched, matched_at_ms, raw_json, event_json, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, 'gmgn', 'websocket', 'public', 'twitter', 'tweet', %s, %s,
          %s, %s, %s, %s, %s, %s, %s, false, 0, %s, %s, %s, %s
        )
        """,
        (
            event_id,
            f"dedupe:{event_id}",
            received_at_ms,
            received_at_ms,
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            Jsonb({}),
            Jsonb({"event_id": event_id}),
            received_at_ms,
            received_at_ms,
        ),
    )


def _insert_intent(conn: Any, *, intent_id: str, event_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'unit-test', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, f"intent-key:{intent_id}", observed_at_ms, observed_at_ms),
    )


def _insert_resolution(
    conn: Any,
    *,
    resolution_id: str,
    intent_id: str,
    event_id: str,
    target_type: str,
    target_id: str,
    observed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
          target_type, target_id, reason_codes_json, candidate_ids_json, lookup_keys_json,
          record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'UNIQUE_BY_CONTEXT', 'token_radar_v5_identity_resolver',
          %s, %s, %s, %s, %s, 'current', true, %s, %s
        )
        """,
        (
            resolution_id,
            intent_id,
            event_id,
            target_type,
            target_id,
            Jsonb(["UNIT_TEST"]),
            Jsonb([target_id]),
            Jsonb([f"{target_type}:{target_id}"]),
            observed_at_ms,
            observed_at_ms,
        ),
    )


def _insert_radar_row(
    conn: Any,
    *,
    row_id: str,
    event_id: str,
    intent_id: str,
    target_type: str,
    target_id: str,
    rank: int,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_current_rows(
          row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
          lane, rank, intent_id, event_id, intent_json, asset_json, primary_venue_json,
          attention_json, resolution_json, market_json, score_json, decision, data_health_json,
          source_event_ids_json, listed_at_ms, created_at_ms, target_type, target_id, pricefeed_id, target_json,
          price_json, factor_snapshot_json, factor_version
        )
        VALUES (
          %s, 'token-radar-v13-social-attention', '24h', 'all', %s, %s,
          'all', %s, %s, %s, %s, %s, NULL,
          %s, %s, %s, %s, 'watch', %s,
          %s, %s, %s, %s, %s, NULL, %s,
          %s, %s, 'token_factor_snapshot_v3_social_attention'
        )
        """,
        (
            row_id,
            computed_at_ms,
            computed_at_ms,
            rank,
            intent_id,
            event_id,
            Jsonb({"intent_id": intent_id}),
            Jsonb({"target_id": target_id}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({"rank_score": max(0, 100 - rank)}),
            Jsonb({"alpha": "ready"}),
            Jsonb([event_id]),
            computed_at_ms,
            computed_at_ms,
            target_type,
            target_id,
            Jsonb({"target_type": target_type, "target_id": target_id}),
            Jsonb({}),
            Jsonb({}),
        ),
    )


def _insert_radar_coverage(conn: Any, *, window: str, scope: str, computed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_projection_coverage(
          projection_version, "window", scope, status, reason, source_rows, row_count,
          computed_at_ms, started_at_ms, finished_at_ms, error, updated_at_ms
        )
        VALUES (
          'token-radar-v13-social-attention', %s, %s, 'ready', NULL, 2, 2,
          %s, %s, %s, NULL, %s
        )
        """,
        (window, scope, computed_at_ms, computed_at_ms, computed_at_ms, computed_at_ms),
    )


def _insert_asset_profile(conn: Any, *, asset_id: str, provider: str, logo_url: str) -> None:
    AssetProfileRepository(conn).upsert_ready_profile(
        asset_id=asset_id,
        provider=provider,
        symbol="UNIT",
        name="Unit Token",
        logo_url=logo_url,
        banner_url=None,
        website_url=None,
        twitter_username=None,
        twitter_url=None,
        telegram_url=None,
        gmgn_url=None,
        geckoterminal_url=None,
        description=None,
        raw_payload={},
        observed_at_ms=NOW_MS,
        next_refresh_at_ms=NOW_MS + 1_000,
        commit=False,
    )


def _insert_identity_evidence(
    conn: Any,
    *,
    evidence_id: str,
    asset_id: str,
    provider: str,
    evidence_kind: str,
    raw_payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO asset_identity_evidence(
          evidence_id, asset_id, evidence_kind, provider, lookup_mode, chain_id, address,
          symbol, name, decimals, confidence, raw_payload_json, observed_at_ms, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, %s, %s, 'exact_address', 'eip155:1', '0x1111111111111111111111111111111111111111',
          'UNIT', 'Unit Token', NULL, 'provider_exact', %s, %s, %s, %s
        )
        """,
        (evidence_id, asset_id, evidence_kind, provider, Jsonb(raw_payload), NOW_MS, NOW_MS, NOW_MS),
    )


def _insert_cex_token(conn: Any, *, cex_token_id: str, base_symbol: str) -> None:
    conn.execute(
        """
        INSERT INTO cex_tokens(
          cex_token_id, base_symbol, status, evidence_level, first_seen_at_ms, updated_at_ms
        )
        VALUES (%s, %s, 'canonical', 'provider_exact', %s, %s)
        """,
        (cex_token_id, base_symbol, NOW_MS, NOW_MS),
    )


def _insert_cex_profile(conn: Any, *, cex_token_id: str, logo_url: str) -> None:
    conn.execute(
        """
        INSERT INTO cex_token_profiles(
          cex_token_id, provider, status, symbol, name, logo_url, source_ref,
          raw_payload_json, observed_at_ms, last_error, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, 'binance_cex_profile', 'ready', 'BTC', 'Bitcoin', %s,
          'binance_marketing_symbol_list:BTC', %s, %s, NULL, %s, %s
        )
        """,
        (cex_token_id, logo_url, Jsonb({}), NOW_MS, NOW_MS, NOW_MS),
    )
