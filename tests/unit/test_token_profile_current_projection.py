from __future__ import annotations

from hashlib import sha256

import pytest

from parallax.domains.asset_market.profile_source_selection import (
    select_gmgn_stream_source,
    select_okx_dex_source,
)
from parallax.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
)

ASSET_ID = "asset:eip155:1:erc20:0xabc"


def test_project_token_profile_current_requires_target_identity():
    with pytest.raises(
        ValueError,
        match="token profile current projection target_type and target_id are required",
    ):
        project_token_profile_current(
            target={"target_type": "Asset", "target_id": " "},
            gmgn_openapi=gmgn_openapi_row(
                status="ready",
                logo_url="https://gmgn.example/logo.png",
                symbol="GMGN",
                observed_at_ms=1_000,
            ),
            binance_web3=None,
            gmgn_stream=None,
            okx_dex=None,
            computed_at_ms=10_000,
        )


def test_project_token_profile_current_prefers_gmgn_openapi_ready_profile():
    gmgn_logo_url = "https://gmgn.example/logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(
            status="ready",
            logo_url=gmgn_logo_url,
            symbol="GMGN",
            raw_payload_json={"profile": True},
            observed_at_ms=1_000,
        ),
        binance_web3=asset_profile_row(
            provider="binance_web3_profile",
            logo_url="https://binance.example/logo.png",
            symbol="BN",
            observed_at_ms=1_500,
        ),
        gmgn_stream=gmgn_stream_row(icon_url="https://stream.example/logo.png", observed_at_ms=2_000),
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        image_states_by_source_key=ready_image_states((gmgn_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["target_type"] == "Asset"
    assert row["target_id"] == ASSET_ID
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["source_kind"] == "asset_profiles"
    assert row["source_ref"] == f"gmgn_dex_profile:{ASSET_ID}"
    assert row["logo_url"] == "/api/token-images/image-gmgn"
    assert row["logo_image_id"] == "image-gmgn"
    assert row["logo_source_provider"] == "gmgn_dex_profile"
    assert row["logo_source_url_hash"] == "hash-gmgn"
    assert row["symbol"] == "GMGN"
    assert row["quality_flags"] == []
    assert row["source_payload"] == {"profile": True}
    assert row["observed_at_ms"] == 1_000
    assert row["computed_at_ms"] == 10_000


def test_project_token_profile_current_uses_gmgn_stream_when_openapi_is_missing_or_error():
    stream_logo_url = "https://gmgn-stream.example/icon.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="error", logo_url=None, observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=gmgn_stream_row(
            icon_url=stream_logo_url,
            symbol="ABC",
            observed_at_ms=2_000,
        ),
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        image_states_by_source_key=ready_image_states((stream_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_stream_snapshot"
    assert row["source_kind"] == "asset_identity_evidence"
    assert row["source_ref"] == "gmgn-evidence-1"
    assert row["logo_url"] == "/api/token-images/image-stream"
    assert row["logo_image_id"] == "image-stream"
    assert row["logo_source_provider"] == "gmgn_stream_snapshot"
    assert row["logo_source_url_hash"] == "hash-stream"
    assert row["symbol"] == "ABC"
    assert row["observed_at_ms"] == 2_000


def test_project_token_profile_current_keeps_gmgn_openapi_metadata_without_logo():
    okx_logo_url = (
        "https://static.oklink.com/cdn/web3/currency/token/large/"
        "1-0xdac17f958d2ee523a2206206994597c13d831ec7-106/type=default_90_0?v=1"
    )
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=None, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(logo_url=okx_logo_url, observed_at_ms=3_000),
        image_states_by_source_key=ready_image_states((okx_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["symbol"] == "GMGN"
    assert row["logo_url"] == "/api/token-images/image-okx"
    assert row["logo_image_id"] == "image-okx"
    assert row["logo_source_provider"] == "okx_dex_evidence"
    assert row["logo_source_url_hash"] == "hash-okx"
    assert row["quality_flags"] == []


def test_project_token_profile_current_uses_lower_priority_ready_logo_when_metadata_logo_is_pending():
    gmgn_logo_url = "https://gmgn.example/logo.png"
    stream_logo_url = "https://gmgn-stream.example/icon.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=gmgn_logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=gmgn_stream_row(icon_url=stream_logo_url, observed_at_ms=2_000),
        okx_dex=None,
        image_states_by_source_key=ready_image_states((stream_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["logo_url"] == "/api/token-images/image-stream"
    assert row["logo_source_provider"] == "gmgn_stream_snapshot"
    assert row["quality_flags"] == []


def test_project_token_profile_current_uses_selected_candidate_provider_for_logo_provenance():
    shared_logo_url = "https://cdn.example/shared-logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=gmgn_stream_row(icon_url=shared_logo_url, observed_at_ms=2_000),
        okx_dex=None,
        image_states_by_source_key={
            source_key(shared_logo_url, "Asset", ASSET_ID): {
                "image_id": "image-shared",
                "source_url": shared_logo_url,
                "source_provider": "gmgn_dex_profile",
                "source_url_hash": "hash-shared",
                "status": "ready",
                "public_url": "/api/token-images/image-shared",
            }
        },
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_stream_snapshot"
    assert row["logo_url"] == "/api/token-images/image-shared"
    assert row["logo_image_id"] == "image-shared"
    assert row["logo_source_provider"] == "gmgn_stream_snapshot"
    assert row["logo_source_url_hash"] == "hash-shared"


def test_project_token_profile_current_uses_binance_web3_before_stream_and_okx_when_gmgn_openapi_missing():
    binance_logo_url = "https://bin.bnbstatic.com/images/web3-data/public/token/logos/usdt.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        binance_web3=asset_profile_row(
            provider="binance_web3_profile",
            logo_url=binance_logo_url,
            symbol="USDT",
            name="Tether USD",
            raw_payload_json={"source_provider": "binance_web3_profile"},
            observed_at_ms=1_500,
        ),
        gmgn_stream=gmgn_stream_row(icon_url="https://gmgn-stream.example/icon.png", observed_at_ms=2_000),
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        image_states_by_source_key=ready_image_states((binance_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "binance_web3_profile"
    assert row["source_kind"] == "asset_profiles"
    assert row["source_ref"] == f"binance_web3_profile:{ASSET_ID}"
    assert row["symbol"] == "USDT"
    assert row["name"] == "Tether USD"
    assert row["logo_url"] == "/api/token-images/image-binance-web3"
    assert row["observed_at_ms"] == 1_500


def test_project_token_profile_current_uses_okx_exact_logo_when_gmgn_sources_are_absent():
    okx_logo_url = (
        "https://static.oklink.com/cdn/web3/currency/token/large/"
        "1-0xdac17f958d2ee523a2206206994597c13d831ec7-106/type=default_90_0?v=1"
    )
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(
            logo_url=okx_logo_url,
            symbol="USDT",
            name="Tether USD",
            observed_at_ms=3_000,
        ),
        image_states_by_source_key=ready_image_states((okx_logo_url, "Asset", ASSET_ID)),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["source_kind"] == "asset_identity_evidence"
    assert row["source_ref"] == "okx-evidence-1"
    assert row["logo_url"] == "/api/token-images/image-okx"
    assert row["symbol"] == "USDT"
    assert row["name"] == "Tether USD"


def test_project_token_profile_current_uses_okx_exact_metadata_without_logo():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(
            logo_url=None,
            symbol="USDT",
            name="Tether USD",
            observed_at_ms=3_000,
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["symbol"] == "USDT"
    assert row["name"] == "Tether USD"
    assert row["logo_url"] is None
    assert row["logo_image_id"] is None
    assert row["logo_source_provider"] is None
    assert row["logo_source_url_hash"] is None
    assert row["quality_flags"] == ["source_without_logo"]


def test_project_token_profile_current_filters_okx_default_logo_and_marks_missing():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(
            logo_url="https://static.okx.com/cdn/wallet/logo/default-logo/0.png",
            symbol="ABC",
            observed_at_ms=3_000,
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "missing"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["okx_placeholder_logo", "source_without_logo"]


def test_project_token_profile_current_returns_cex_unsupported_without_symbol_matching():
    row = project_token_profile_current(
        target={"target_type": "CexToken", "target_id": "cex_token:BTC"},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(logo_url="https://okx.example/btc.png", symbol="BTC", observed_at_ms=3_000),
        cex_profile=None,
        computed_at_ms=10_000,
    )

    assert row["status"] == "unsupported"
    assert row["target_type"] == "CexToken"
    assert row["target_id"] == "cex_token:BTC"
    assert row["profile_provider"] is None
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["cex_profile_unsupported"]


def test_project_token_profile_current_uses_binance_cex_profile_source_cache():
    cex_logo_url = "https://bin.bnbstatic.com/btc.png"
    row = project_token_profile_current(
        target={"target_type": "CexToken", "target_id": "cex_token:BTC"},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        cex_profile={
            "cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "symbol": "BTC",
            "name": "Bitcoin",
            "logo_url": cex_logo_url,
            "source_ref": "binance_marketing_symbol_list:BTC",
            "raw_payload_json": {"rank": 1},
            "observed_at_ms": 9_000,
        },
        image_states_by_source_key=ready_image_states((cex_logo_url, "CexToken", "cex_token:BTC")),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["target_type"] == "CexToken"
    assert row["target_id"] == "cex_token:BTC"
    assert row["profile_provider"] == "binance_cex_profile"
    assert row["source_kind"] == "cex_token_profiles"
    assert row["source_ref"] == "binance_marketing_symbol_list:BTC"
    assert row["symbol"] == "BTC"
    assert row["name"] == "Bitcoin"
    assert row["logo_url"] == "/api/token-images/image-cex"
    assert row["logo_image_id"] == "image-cex"
    assert row["logo_source_provider"] == "binance_cex_profile"
    assert row["logo_source_url_hash"] == "hash-cex"
    assert row["source_payload"] == {"rank": 1}
    assert row["quality_flags"] == []
    assert row["observed_at_ms"] == 9_000


def test_project_token_profile_current_falls_back_to_specific_cex_source_ref():
    row = project_token_profile_current(
        target={"target_type": "CexToken", "target_id": "cex_token:BTC"},
        gmgn_openapi=None,
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        cex_profile={
            "cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "symbol": "BTC",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "raw_payload_json": {},
            "observed_at_ms": 9_000,
        },
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["source_ref"] == "binance_cex_profile:cex_token:BTC"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["source_not_admitted"]


def test_project_token_profile_current_sets_pending_flag_without_remote_logo_fallback():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(
            status="ready",
            logo_url="https://gmgn.example/logo.png",
            symbol="GMGN",
            observed_at_ms=1_000,
        ),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        image_states_by_source_key={},
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["logo_image_id"] is None
    assert row["logo_source_provider"] is None
    assert row["logo_source_url_hash"] is None
    assert row["quality_flags"] == ["source_not_admitted"]


def test_project_token_profile_current_marks_unsupported_lifecycle_without_pending_flag():
    logo_url = "https://gmgn.example/logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        image_states_by_source_key=image_states(
            (logo_url, "Asset", ASSET_ID, {"status": "unsupported", "source_url_hash": "hash-unsupported"})
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["logo_mirror_unsupported"]


def test_project_token_profile_current_marks_error_lifecycle_without_pending_flag():
    logo_url = "https://gmgn.example/logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        image_states_by_source_key=image_states(
            (logo_url, "Asset", ASSET_ID, {"status": "error", "source_url_hash": "hash-error"})
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["logo_mirror_failed"]


def test_project_token_profile_current_marks_usable_source_without_state_as_not_admitted():
    logo_url = "https://gmgn.example/logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        image_states_by_source_key={},
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["source_not_admitted"]


def test_project_token_profile_current_does_not_reuse_ready_image_state_from_other_target():
    logo_url = "https://gmgn.example/shared-logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        image_states_by_source_key=ready_image_states((logo_url, "Asset", "asset:other")),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["source_not_admitted"]


def test_project_token_profile_current_lower_priority_ready_logo_wins_over_higher_priority_pending():
    gmgn_logo_url = "https://gmgn.example/logo.png"
    stream_logo_url = "https://gmgn-stream.example/icon.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=gmgn_logo_url, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=gmgn_stream_row(icon_url=stream_logo_url, observed_at_ms=2_000),
        okx_dex=None,
        image_states_by_source_key={
            source_key(gmgn_logo_url, "Asset", ASSET_ID): {
                "status": "mirror_pending",
                "source_url": gmgn_logo_url,
                "source_url_hash": "hash-gmgn",
            },
            source_key(stream_logo_url, "Asset", ASSET_ID): ready_image(stream_logo_url),
        },
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] == "/api/token-images/image-stream"
    assert row["logo_source_provider"] == "gmgn_stream_snapshot"
    assert row["quality_flags"] == []


def test_project_token_profile_current_marks_source_without_logo_when_no_provider_logo_candidates():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=None, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["quality_flags"] == ["source_without_logo"]


def test_project_token_profile_current_keeps_first_unusable_logo_fallback_flags():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=None, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(
            logo_url="https://static.okx.com/cdn/wallet/logo/default-logo/0.png",
            symbol="GMGN",
            observed_at_ms=3_000,
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["quality_flags"] == ["source_without_logo"]


def test_select_okx_dex_source_prefers_exact_address_over_symbol_candidates():
    selected = select_okx_dex_source(
        [
            okx_row(
                evidence_id="symbol-candidate",
                evidence_kind="okx_dex_symbol_candidate",
                logo_url="https://okx.example/symbol.png",
                observed_at_ms=5_000,
            ),
            okx_row(
                evidence_id="exact",
                evidence_kind="okx_dex_exact_address",
                logo_url="https://okx.example/exact.png",
                observed_at_ms=4_000,
            ),
        ]
    )

    assert selected is not None
    assert selected["evidence_id"] == "exact"


def test_select_okx_dex_source_uses_symbol_candidate_when_exact_address_is_absent():
    selected = select_okx_dex_source(
        [
            okx_row(
                evidence_id="symbol-candidate",
                evidence_kind="okx_dex_symbol_candidate",
                logo_url="https://okx.example/symbol.png",
                observed_at_ms=5_000,
            ),
        ]
    )

    assert selected is not None
    assert selected["evidence_id"] == "symbol-candidate"


def test_select_gmgn_stream_source_can_use_symbol_metadata_without_icon_url():
    selected = select_gmgn_stream_source(
        [
            gmgn_stream_row(evidence_id="no-icon", icon_url=None, symbol="GMGN", observed_at_ms=5_000),
            gmgn_stream_row(evidence_id="with-icon", icon_url="https://gmgn.example/icon.png", observed_at_ms=4_000),
        ]
    )

    assert selected is not None
    assert selected["evidence_id"] == "no-icon"


def asset_profile_row(
    *,
    provider: str = "gmgn_dex_profile",
    status: str = "ready",
    logo_url: str | None = None,
    symbol: str | None = None,
    name: str | None = None,
    raw_payload_json: dict | None = None,
    observed_at_ms: int = 1_000,
) -> dict:
    return {
        "asset_id": ASSET_ID,
        "provider": provider,
        "status": status,
        "symbol": symbol,
        "name": name,
        "logo_url": logo_url,
        "banner_url": None,
        "website_url": None,
        "twitter_username": None,
        "twitter_url": None,
        "telegram_url": None,
        "gmgn_url": None,
        "geckoterminal_url": None,
        "description": None,
        "raw_payload_json": raw_payload_json or {},
        "observed_at_ms": observed_at_ms,
    }


def gmgn_openapi_row(
    *,
    status: str,
    logo_url: str | None = None,
    symbol: str | None = None,
    raw_payload_json: dict | None = None,
    observed_at_ms: int = 1_000,
) -> dict:
    return asset_profile_row(
        provider="gmgn_dex_profile",
        status=status,
        logo_url=logo_url,
        symbol=symbol,
        raw_payload_json=raw_payload_json,
        observed_at_ms=observed_at_ms,
    )


def gmgn_stream_row(
    *,
    evidence_id: str = "gmgn-evidence-1",
    icon_url: str | None,
    symbol: str | None = "ABC",
    observed_at_ms: int = 2_000,
) -> dict:
    raw_payload = {"a": "0xabc", "c": "eth"}
    if icon_url:
        raw_payload["i"] = icon_url
    if symbol:
        raw_payload["s"] = symbol
    return {
        "evidence_id": evidence_id,
        "asset_id": ASSET_ID,
        "provider": "gmgn",
        "evidence_kind": "gmgn_payload_exact",
        "symbol": symbol,
        "name": None,
        "raw_payload_json": raw_payload,
        "observed_at_ms": observed_at_ms,
        "source_event_id": "event-1",
    }


def okx_row(
    *,
    evidence_id: str = "okx-evidence-1",
    evidence_kind: str = "okx_dex_exact_address",
    logo_url: str | None,
    symbol: str | None = "ABC",
    name: str | None = None,
    observed_at_ms: int = 3_000,
) -> dict:
    raw_payload = {"tokenContractAddress": "0xabc"}
    if logo_url:
        raw_payload["tokenLogoUrl"] = logo_url
    if symbol:
        raw_payload["tokenSymbol"] = symbol
    if name:
        raw_payload["tokenName"] = name
    return {
        "evidence_id": evidence_id,
        "asset_id": ASSET_ID,
        "provider": "okx",
        "evidence_kind": evidence_kind,
        "symbol": symbol,
        "name": name,
        "raw_payload_json": raw_payload,
        "observed_at_ms": observed_at_ms,
    }


def source_key(source_url: str, target_type: str, target_id: str) -> tuple[str, str, str]:
    return (sha256(source_url.encode("utf-8")).hexdigest(), target_type, target_id)


def ready_image_states(*source_targets: tuple[str, str, str]) -> dict[tuple[str, str, str], dict]:
    return {
        source_key(source_url, target_type, target_id): ready_image(source_url)
        for source_url, target_type, target_id in source_targets
    }


def image_states(*states: tuple[str, str, str, dict]) -> dict[tuple[str, str, str], dict]:
    return {
        source_key(source_url, target_type, target_id): {"source_url": source_url, **state}
        for source_url, target_type, target_id, state in states
    }


def ready_image(source_url: str) -> dict:
    if "gmgn-stream" in source_url:
        slug = "stream"
        provider = "gmgn_stream_snapshot"
    elif "bnbstatic.com/images/web3-data" in source_url:
        slug = "binance-web3"
        provider = "binance_web3_profile"
    elif "bnbstatic.com/btc" in source_url:
        slug = "cex"
        provider = "binance_cex_profile"
    elif "oklink.com" in source_url:
        slug = "okx"
        provider = "okx_dex_evidence"
    else:
        slug = "gmgn"
        provider = "gmgn_dex_profile"
    return {
        "image_id": f"image-{slug}",
        "source_url": source_url,
        "source_provider": provider,
        "source_url_hash": f"hash-{slug}",
        "status": "ready",
        "public_url": f"/api/token-images/image-{slug}",
    }
