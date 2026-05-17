from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
    select_gmgn_stream_source,
    select_okx_dex_source,
)

ASSET_ID = "asset:eip155:1:erc20:0xabc"


def test_project_token_profile_current_prefers_gmgn_openapi_ready_profile():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(
            status="ready",
            logo_url="https://gmgn.example/logo.png",
            symbol="GMGN",
            raw_payload_json={"profile": True},
            observed_at_ms=1_000,
        ),
        gmgn_stream=gmgn_stream_row(icon_url="https://stream.example/logo.png", observed_at_ms=2_000),
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["target_type"] == "Asset"
    assert row["target_id"] == ASSET_ID
    assert row["profile_provider"] == "gmgn_dex_profile"
    assert row["source_kind"] == "asset_profiles"
    assert row["source_ref"] == f"gmgn_dex_profile:{ASSET_ID}"
    assert row["logo_url"] == "https://gmgn.example/logo.png"
    assert row["symbol"] == "GMGN"
    assert row["quality_flags"] == []
    assert row["source_payload"] == {"profile": True}
    assert row["observed_at_ms"] == 1_000
    assert row["computed_at_ms"] == 10_000


def test_project_token_profile_current_uses_gmgn_stream_when_openapi_is_missing_or_error():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="error", logo_url=None, observed_at_ms=1_000),
        gmgn_stream=gmgn_stream_row(
            icon_url="https://gmgn-stream.example/icon.png",
            symbol="ABC",
            observed_at_ms=2_000,
        ),
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "gmgn_stream_snapshot"
    assert row["source_kind"] == "asset_identity_evidence"
    assert row["source_ref"] == "gmgn-evidence-1"
    assert row["logo_url"] == "https://gmgn-stream.example/icon.png"
    assert row["symbol"] == "ABC"
    assert row["observed_at_ms"] == 2_000


def test_project_token_profile_current_skips_gmgn_openapi_profile_without_logo():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=None, symbol="GMGN", observed_at_ms=1_000),
        gmgn_stream=None,
        okx_dex=okx_row(logo_url="https://okx.example/logo.png", observed_at_ms=3_000),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["logo_url"] == "https://okx.example/logo.png"


def test_project_token_profile_current_uses_okx_exact_logo_when_gmgn_sources_are_absent():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
        gmgn_stream=None,
        okx_dex=okx_row(
            logo_url="https://static.okx.com/cdn/wallet/logo/usdt.png",
            symbol="USDT",
            name="Tether USD",
            observed_at_ms=3_000,
        ),
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["profile_provider"] == "okx_dex_evidence"
    assert row["source_kind"] == "asset_identity_evidence"
    assert row["source_ref"] == "okx-evidence-1"
    assert row["logo_url"] == "https://static.okx.com/cdn/wallet/logo/usdt.png"
    assert row["symbol"] == "USDT"
    assert row["name"] == "Tether USD"


def test_project_token_profile_current_filters_okx_default_logo_and_marks_missing():
    row = project_token_profile_current(
        target={"target_type": "Asset", "target_id": ASSET_ID},
        gmgn_openapi=None,
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


def test_project_token_profile_current_uses_cex_token_icon_source():
    row = project_token_profile_current(
        target={"target_type": "CexToken", "target_id": "cex_token:BTC"},
        gmgn_openapi=None,
        gmgn_stream=None,
        okx_dex=None,
        cex_profile={
            "cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "logo_source": "binance_marketing_symbol_list",
            "logo_observed_at_ms": 9_000,
        },
        computed_at_ms=10_000,
    )

    assert row["status"] == "ready"
    assert row["target_type"] == "CexToken"
    assert row["target_id"] == "cex_token:BTC"
    assert row["profile_provider"] == "cex_token_icon_static"
    assert row["source_kind"] == "cex_tokens"
    assert row["source_ref"] == "binance_marketing_symbol_list:cex_token:BTC"
    assert row["symbol"] == "BTC"
    assert row["logo_url"] == "https://bin.bnbstatic.com/btc.png"
    assert row["quality_flags"] == []
    assert row["observed_at_ms"] == 9_000


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


def test_select_gmgn_stream_source_requires_icon_url():
    selected = select_gmgn_stream_source(
        [
            gmgn_stream_row(evidence_id="no-icon", icon_url=None, observed_at_ms=5_000),
            gmgn_stream_row(evidence_id="with-icon", icon_url="https://gmgn.example/icon.png", observed_at_ms=4_000),
        ]
    )

    assert selected is not None
    assert selected["evidence_id"] == "with-icon"


def gmgn_openapi_row(
    *,
    status: str,
    logo_url: str | None = None,
    symbol: str | None = None,
    raw_payload_json: dict | None = None,
    observed_at_ms: int = 1_000,
) -> dict:
    return {
        "asset_id": ASSET_ID,
        "provider": "gmgn_dex_profile",
        "status": status,
        "symbol": symbol,
        "name": None,
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
