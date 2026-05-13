from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import GMGN_DEX_PROFILE_PROVIDER
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService


def test_profile_read_model_returns_ready_block_with_normalized_links_and_public_source():
    asset_profiles = FakeAssetProfiles(
        rows={
            "asset:eip155:1:erc20:0xabc": profile_row(
                asset_id="asset:eip155:1:erc20:0xabc",
                status="ready",
                symbol="ABC",
                name=" ",
                logo_url="https://assets.example/abc.png",
                banner_url="",
                website_url=" https://abc.example ",
                twitter_username="abc",
                twitter_url="",
                telegram_url="https://t.me/abc",
                gmgn_url="https://gmgn.ai/eth/token/0xabc",
                geckoterminal_url="",
                description=" project profile ",
                raw_payload_json={"ok": True},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(asset_profiles=asset_profiles)

    profile = model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")

    assert profile == {
        "status": "ready",
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "observed_at_ms": 1_000,
        "identity": {
            "symbol": "ABC",
            "name": None,
            "logo_url": "https://assets.example/abc.png",
            "banner_url": None,
            "description": "project profile",
        },
        "links": {
            "website_url": "https://abc.example",
            "twitter_url": "https://x.com/abc",
            "twitter_username": "abc",
            "telegram_url": "https://t.me/abc",
            "gmgn_url": "https://gmgn.ai/eth/token/0xabc",
            "geckoterminal_url": None,
        },
        "source": {
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "raw_available": True,
            "last_error": None,
        },
    }
    assert "raw_payload_json" not in profile


def test_profile_read_model_preserves_full_twitter_url():
    asset_profiles = FakeAssetProfiles(
        rows={
            "asset:eip155:1:erc20:0xabc": profile_row(
                asset_id="asset:eip155:1:erc20:0xabc",
                status="ready",
                twitter_username="abc",
                twitter_url="https://twitter.com/abc",
                raw_payload_json={},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(asset_profiles=asset_profiles)

    profile = model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")

    assert profile["links"]["twitter_url"] == "https://twitter.com/abc"
    assert profile["source"]["raw_available"] is False


def test_profile_read_model_returns_pending_missing_error_and_non_asset_blocks():
    asset_profiles = FakeAssetProfiles(
        rows={
            "asset:missing": profile_row(
                asset_id="asset:missing",
                status="missing",
                raw_payload_json={},
                observed_at_ms=2_000,
            ),
            "asset:error": profile_row(
                asset_id="asset:error",
                status="error",
                raw_payload_json={},
                observed_at_ms=3_000,
                last_error="provider timeout",
            ),
        }
    )
    model = TokenProfileReadModel(asset_profiles=asset_profiles)

    pending = model.profile_for_target(target_type="Asset", target_id="asset:pending")
    missing = model.profile_for_target(target_type="Asset", target_id="asset:missing")
    error = model.profile_for_target(target_type="Asset", target_id="asset:error")

    assert pending == {
        "status": "pending",
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "observed_at_ms": None,
        "source": {
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "raw_available": False,
            "last_error": None,
        },
    }
    assert missing == {
        "status": "missing",
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "observed_at_ms": 2_000,
        "source": {
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "raw_available": False,
            "last_error": None,
        },
    }
    assert error == {
        "status": "error",
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "observed_at_ms": 3_000,
        "source": {
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "raw_available": False,
            "last_error": "provider timeout",
        },
    }
    assert model.profile_for_target(target_type="CexToken", target_id="cex_token:BTC") is None
    assert model.profile_for_target(target_type="Asset", target_id=" ") is None


def test_profile_read_model_batches_targets_by_asset_id():
    asset_profiles = FakeAssetProfiles(
        rows={
            "asset:abc": profile_row(
                asset_id="asset:abc",
                status="ready",
                symbol="ABC",
                twitter_username="abc",
                raw_payload_json={"ok": True},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(asset_profiles=asset_profiles)

    profiles = model.profiles_for_targets(
        [
            {"target_type": "Asset", "target_id": "asset:abc"},
            {"target_type": "Asset", "target_id": "asset:pending"},
            {"target_type": "CexToken", "target_id": "cex_token:BTC"},
            {"target_type": "Asset", "target_id": ""},
        ]
    )

    assert asset_profiles.calls == [
        {"asset_ids": ["asset:abc", "asset:pending"], "provider": GMGN_DEX_PROFILE_PROVIDER}
    ]
    assert profiles[("Asset", "asset:abc")]["status"] == "ready"
    assert profiles[("Asset", "asset:pending")]["status"] == "pending"
    assert profiles[("CexToken", "cex_token:BTC")] is None
    assert ("Asset", "") not in profiles


def test_asset_flow_hydrates_row_profile_from_profile_batch():
    profile_block = {
        "status": "ready",
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "observed_at_ms": 1_000,
        "identity": {},
        "links": {},
        "source": {"provider": GMGN_DEX_PROFILE_PROVIDER, "raw_available": True, "last_error": None},
    }
    profiles = FakeProfiles({("Asset", "asset:abc"): profile_block})
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[radar_row(target_type="Asset", target_id="asset:abc", symbol="ABC")],
        ),
        profiles=profiles,
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["profile"] == profile_block
    assert profiles.calls[0][0]["target_type"] == "Asset"
    assert profiles.calls[0][0]["target_id"] == "asset:abc"
    assert profiles.calls[0][0]["symbol"] == "ABC"


class FakeAssetProfiles:
    def __init__(self, *, rows: dict[str, dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def profiles_for_asset_ids(
        self,
        asset_ids: list[str],
        *,
        provider: str = GMGN_DEX_PROFILE_PROVIDER,
    ) -> dict[str, dict[str, Any]]:
        self.calls.append({"asset_ids": asset_ids, "provider": provider})
        return {asset_id: self.rows[asset_id] for asset_id in asset_ids if asset_id in self.rows}


class FakeProfiles:
    def __init__(self, blocks: dict[tuple[str, str], dict[str, Any] | None]) -> None:
        self.blocks = blocks
        self.calls: list[list[dict[str, Any]]] = []

    def profiles_for_targets(self, targets: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any] | None]:
        self.calls.append(targets)
        return dict(self.blocks)


class FakeTokenRadar:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def latest_rows(self, *, window: str, scope: str, limit: int, projection_version: str) -> list[dict[str, Any]]:
        return self.rows[:limit]

    def latest_coverage(self, *, projection_version: str, windows: tuple[str, ...], scopes: tuple[str, ...]):
        return {
            (window, scope): {
                "status": "ready",
                "reason": None,
                "row_count": len(self.rows),
                "source_rows": len(self.rows),
                "computed_at_ms": max((int(row.get("computed_at_ms") or 0) for row in self.rows), default=0)
                or None,
            }
            for window in windows
            for scope in scopes
        }


def profile_row(
    *,
    asset_id: str,
    status: str,
    symbol: str | None = None,
    name: str | None = None,
    logo_url: str | None = None,
    banner_url: str | None = None,
    website_url: str | None = None,
    twitter_username: str | None = None,
    twitter_url: str | None = None,
    telegram_url: str | None = None,
    gmgn_url: str | None = None,
    geckoterminal_url: str | None = None,
    description: str | None = None,
    raw_payload_json: dict[str, Any] | None = None,
    observed_at_ms: int | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "status": status,
        "symbol": symbol,
        "name": name,
        "logo_url": logo_url,
        "banner_url": banner_url,
        "website_url": website_url,
        "twitter_username": twitter_username,
        "twitter_url": twitter_url,
        "telegram_url": telegram_url,
        "gmgn_url": gmgn_url,
        "geckoterminal_url": geckoterminal_url,
        "description": description,
        "raw_payload_json": raw_payload_json,
        "observed_at_ms": observed_at_ms,
        "last_error": last_error,
    }


def radar_row(*, target_type: str, target_id: str, symbol: str) -> dict[str, Any]:
    return {
        "row_id": f"row:{target_id}",
        "lane": "resolved",
        "target_type": target_type,
        "target_id": target_id,
        "intent_json": {"display_symbol": symbol},
        "target_json": {},
        "factor_snapshot_json": {
            "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
            "subject": {
                "target_type": target_type,
                "target_id": target_id,
                "symbol": symbol,
                "chain": "eth",
                "address": "0xabc",
                "target_market_type": "dex",
            },
            "market": {
                "event_price_readiness": {"status": "ready"},
                "provider": "okx",
                "anchor_price_usd": 1.23,
                "anchor_quote_symbol": "USD",
                "anchor_price_basis": "usd",
                "anchor_observed_at_ms": 1_700_000_000_000,
                "social_signal_start_ms": 1_700_000_000_000,
                "anchor_lag_ms": 0,
            },
            "families": {"social_heat": {"facts": {"mentions_1h": 1}}},
            "composite": {"rank_score": 80, "recommended_decision": "watch"},
            "provenance": {"source_event_ids": ["event:abc"], "computed_at_ms": 1_700_000_060_000},
        },
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "resolution_json": {"status": "EXACT", "target_type": target_type, "target_id": target_id},
        "data_health_json": {"factor_snapshot": "ready", "identity": "ready", "market": "ready"},
        "source_event_ids_json": ["event:abc"],
        "source_max_received_at_ms": 1_700_000_000_000,
        "computed_at_ms": 1_700_000_060_000,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
    }
