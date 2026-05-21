from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.profile_source_selection import (
    select_gmgn_stream_source,
    select_okx_dex_source,
)
from gmgn_twitter_intel.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
)

ASSET_ID = "asset:eip155:1:erc20:0xabc"


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
        ready_images_by_source_url=ready_images(gmgn_logo_url),
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
        ready_images_by_source_url=ready_images(stream_logo_url),
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
    okx_logo_url = "https://okx.example/logo.png"
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=None, symbol="GMGN", observed_at_ms=1_000),
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=okx_row(logo_url=okx_logo_url, observed_at_ms=3_000),
        ready_images_by_source_url=ready_images(okx_logo_url),
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
        ready_images_by_source_url=ready_images(stream_logo_url),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["logo_url"] == "/api/token-images/image-stream"
    assert row["logo_source_provider"] == "gmgn_stream_snapshot"
    assert row["quality_flags"] == []


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
        ready_images_by_source_url=ready_images(binance_logo_url),
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
    okx_logo_url = "https://static.okx.com/cdn/wallet/logo/usdt.png"
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
        ready_images_by_source_url=ready_images(okx_logo_url),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["source_kind"] == "asset_identity_evidence"
    assert row["source_ref"] == "okx-evidence-1"
    assert row["logo_url"] == "/api/token-images/image-okx"
    assert row["symbol"] == "USDT"
    assert row["name"] == "Tether USD"


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
        ready_images_by_source_url=ready_images(cex_logo_url),
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
    assert row["quality_flags"] == ["logo_mirror_pending"]


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
        ready_images_by_source_url={},
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["logo_url"] is None
    assert row["logo_image_id"] is None
    assert row["logo_source_provider"] is None
    assert row["logo_source_url_hash"] is None
    assert row["quality_flags"] == ["logo_mirror_pending"]


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


def test_select_okx_dex_source_ignores_symbol_candidates():
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


def test_select_okx_dex_source_can_use_symbol_metadata_without_logo():
    selected = select_okx_dex_source(
        [
            okx_row(evidence_id="older-logo", logo_url="https://okx.example/exact.png", observed_at_ms=4_000),
            okx_row(evidence_id="newer-symbol", logo_url=None, symbol="NEW", name="New Token", observed_at_ms=5_000),
        ]
    )

    assert selected is not None
    assert selected["evidence_id"] == "newer-symbol"


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


def ready_images(*source_urls: str) -> dict[str, dict]:
    return {source_url: ready_image(source_url) for source_url in source_urls}


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
    elif "okx" in source_url:
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
        "public_url": f"/api/token-images/image-{slug}",
    }
