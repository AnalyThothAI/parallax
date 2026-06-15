from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from parallax.domains.token_intel.read_models.asset_flow_service import AssetFlowService


def test_profile_read_model_returns_ready_block_from_current_profile_row():
    token_profiles = FakeTokenProfiles(
        rows={
            ("Asset", "asset:eip155:1:erc20:0xabc"): profile_row(
                target_type="Asset",
                target_id="asset:eip155:1:erc20:0xabc",
                status="ready",
                profile_provider="gmgn_stream_snapshot",
                source_kind="asset_identity_evidence",
                source_ref="gmgn-evidence-1",
                symbol="ABC",
                name=" ",
                logo_url="/api/token-images/image-abc",
                banner_url="",
                website_url=" https://abc.example ",
                twitter_username="abc",
                twitter_url="",
                telegram_url="https://t.me/abc",
                gmgn_url="https://gmgn.ai/eth/token/0xabc",
                geckoterminal_url="",
                description=" project profile ",
                quality_flags_json=[],
                source_payload_json={"ok": True},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(token_profiles=token_profiles)

    profile = model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")

    assert profile == {
        "status": "ready",
        "provider": "gmgn_stream_snapshot",
        "observed_at_ms": 1_000,
        "identity": {
            "symbol": "ABC",
            "name": None,
            "logo_url": "/api/token-images/image-abc",
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
            "provider": "gmgn_stream_snapshot",
            "source_kind": "asset_identity_evidence",
            "source_ref": "gmgn-evidence-1",
            "quality_flags": [],
            "raw_available": True,
            "last_error": None,
        },
    }
    assert "source_payload_json" not in profile


def test_profile_read_model_preserves_full_twitter_url():
    token_profiles = FakeTokenProfiles(
        rows={
            ("Asset", "asset:eip155:1:erc20:0xabc"): profile_row(
                target_type="Asset",
                target_id="asset:eip155:1:erc20:0xabc",
                status="ready",
                profile_provider="gmgn_dex_profile",
                twitter_username="abc",
                twitter_url="https://twitter.com/abc",
                source_payload_json={},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(token_profiles=token_profiles)

    profile = model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")

    assert profile["links"]["twitter_url"] == "https://twitter.com/abc"
    assert profile["source"]["raw_available"] is False


def test_profile_read_model_returns_pending_missing_error_and_cex_unsupported_blocks():
    token_profiles = FakeTokenProfiles(
        rows={
            ("Asset", "asset:missing"): profile_row(
                target_type="Asset",
                target_id="asset:missing",
                status="missing",
                profile_provider=None,
                source_kind="projection",
                source_payload_json={},
                observed_at_ms=2_000,
            ),
            ("Asset", "asset:error"): profile_row(
                target_type="Asset",
                target_id="asset:error",
                status="error",
                profile_provider="gmgn_stream_snapshot",
                source_kind="asset_identity_evidence",
                source_ref="gmgn-bad",
                source_payload_json={"last_error": "malformed icon"},
                quality_flags_json=["invalid_logo_url"],
                observed_at_ms=3_000,
            ),
        }
    )
    model = TokenProfileReadModel(token_profiles=token_profiles)

    pending = model.profile_for_target(target_type="Asset", target_id="asset:pending")
    missing = model.profile_for_target(target_type="Asset", target_id="asset:missing")
    error = model.profile_for_target(target_type="Asset", target_id="asset:error")
    unsupported = model.profile_for_target(target_type="CexToken", target_id="cex_token:BTC")

    assert pending == {
        "status": "pending",
        "provider": None,
        "observed_at_ms": None,
        "source": {
            "provider": None,
            "source_kind": "token_profile_current",
            "source_ref": None,
            "quality_flags": [],
            "raw_available": False,
            "last_error": None,
        },
    }
    assert missing == {
        "status": "missing",
        "provider": None,
        "observed_at_ms": 2_000,
        "source": {
            "provider": None,
            "source_kind": "projection",
            "source_ref": None,
            "quality_flags": [],
            "raw_available": False,
            "last_error": None,
        },
    }
    assert error == {
        "status": "error",
        "provider": "gmgn_stream_snapshot",
        "observed_at_ms": 3_000,
        "source": {
            "provider": "gmgn_stream_snapshot",
            "source_kind": "asset_identity_evidence",
            "source_ref": "gmgn-bad",
            "quality_flags": ["invalid_logo_url"],
            "raw_available": True,
            "last_error": "malformed icon",
        },
    }
    assert unsupported == {
        "status": "unsupported",
        "provider": None,
        "observed_at_ms": None,
        "source": {
            "provider": None,
            "source_kind": "token_profile_current",
            "source_ref": None,
            "quality_flags": ["cex_profile_unsupported"],
            "raw_available": False,
            "last_error": None,
        },
    }
    assert model.profile_for_target(target_type="Asset", target_id=" ") is None


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("status", None, "required:status"),
        ("status", " ", "invalid:status"),
        ("source_kind", None, "required:source_kind"),
        ("source_kind", " ", "invalid:source_kind"),
        ("quality_flags_json", None, "required:quality_flags_json"),
        ("quality_flags_json", {"flag": "not-list"}, "invalid:quality_flags_json"),
        ("source_payload_json", None, "required:source_payload_json"),
        ("source_payload_json", ["not-mapping"], "invalid:source_payload_json"),
    ],
)
def test_present_token_profile_current_row_requires_formal_public_fields_without_pending_fallback(
    field: str,
    value: Any,
    expected_reason: str,
) -> None:
    row = profile_row(
        target_type="Asset",
        target_id="asset:eip155:1:erc20:0xabc",
        status="missing",
        profile_provider=None,
        source_kind="projection",
        quality_flags_json=[],
        source_payload_json={},
        observed_at_ms=1_000,
    )
    row[field] = value
    token_profiles = FakeTokenProfiles(rows={("Asset", "asset:eip155:1:erc20:0xabc"): row})
    model = TokenProfileReadModel(token_profiles=token_profiles)

    with pytest.raises(ValueError, match=f"token_profile_current_public_{expected_reason}"):
        model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")


def test_profile_read_model_batches_all_targets_without_provider_argument():
    token_profiles = FakeTokenProfiles(
        rows={
            ("Asset", "asset:abc"): profile_row(
                target_type="Asset",
                target_id="asset:abc",
                status="ready",
                profile_provider="okx_dex_evidence",
                symbol="ABC",
                twitter_username="abc",
                source_payload_json={"ok": True},
                observed_at_ms=1_000,
            )
        }
    )
    model = TokenProfileReadModel(token_profiles=token_profiles)

    profiles = model.profiles_for_targets(
        [
            {"target_type": "Asset", "target_id": "asset:abc"},
            {"target_type": "Asset", "target_id": "asset:pending"},
            {"target_type": "CexToken", "target_id": "cex_token:BTC"},
            {"target_type": "Asset", "target_id": ""},
        ]
    )

    assert token_profiles.calls == [[("Asset", "asset:abc"), ("Asset", "asset:pending"), ("CexToken", "cex_token:BTC")]]
    assert profiles[("Asset", "asset:abc")]["status"] == "ready"
    assert profiles[("Asset", "asset:pending")]["status"] == "pending"
    assert profiles[("CexToken", "cex_token:BTC")]["status"] == "unsupported"
    assert ("Asset", "") not in profiles


def test_asset_flow_hydrates_row_profile_from_profile_batch():
    profile_block = {
        "status": "ready",
        "provider": "okx_dex_evidence",
        "observed_at_ms": 1_000,
        "identity": {},
        "links": {},
        "source": {
            "provider": "okx_dex_evidence",
            "source_kind": "asset_identity_evidence",
            "source_ref": "okx-1",
            "quality_flags": [],
            "raw_available": True,
            "last_error": None,
        },
    }
    profiles = FakeProfiles({("Asset", "asset:abc"): profile_block})
    service = AssetFlowService(
        token_radar=FakeTokenRadar(
            rows=[radar_row(target_type="Asset", target_id="asset:abc", symbol="ABC")],
        ),
        profiles=profiles,
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", venue="all", now_ms=1_700_000_060_000)

    assert result["targets"][0]["profile"] == profile_block
    assert profiles.calls[0][0]["target_type"] == "Asset"
    assert profiles.calls[0][0]["target_id"] == "asset:abc"
    assert profiles.calls[0][0]["symbol"] == "ABC"


class FakeTokenProfiles:
    def __init__(self, *, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[list[tuple[str, str]]] = []

    def current_for_targets(self, targets: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
        self.calls.append(targets)
        return {key: self.rows[key] for key in targets if key in self.rows}


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

    def latest_current_rows(
        self,
        *,
        window: str,
        scope: str,
        venue: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        del window, scope, venue, projection_version
        return self.rows[:limit]

    def latest_coverage(self, *, projection_version: str, windows: tuple[str, ...], scopes: tuple[str, ...]):
        return {
            (window, scope): {
                "status": "ready",
                "reason": None,
                "row_count": len(self.rows),
                "source_rows": len(self.rows),
                "computed_at_ms": max((int(row.get("computed_at_ms") or 0) for row in self.rows), default=0) or None,
            }
            for window in windows
            for scope in scopes
        }

    def latest_publication_state(
        self,
        *,
        projection_version: str,
        windows: tuple[str, ...],
        scopes: tuple[str, ...],
        venues: tuple[str, ...],
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        del projection_version
        max_computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in self.rows), default=0) or None
        return {
            (window, scope, venue): {
                "latest_attempt_status": "ready",
                "current_generation_id": "gen-default",
                "current_row_count": len(self.rows),
                "current_source_rows": len(self.rows),
                "current_source_frontier_ms": max_computed_at_ms,
                "current_published_at_ms": max_computed_at_ms,
                "latest_attempt_error": None,
            }
            for window in windows
            for scope in scopes
            for venue in venues
        }


def profile_row(
    *,
    target_type: str,
    target_id: str,
    status: str,
    profile_provider: str | None,
    source_kind: str = "asset_identity_evidence",
    source_ref: str | None = None,
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
    quality_flags_json: list[str] | None = None,
    source_payload_json: dict[str, Any] | None = None,
    observed_at_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "profile_provider": profile_provider,
        "source_kind": source_kind,
        "source_ref": source_ref,
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
        "quality_flags_json": quality_flags_json or [],
        "source_payload_json": source_payload_json or {},
        "observed_at_ms": observed_at_ms,
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
                "event_anchor": {
                    "source": "event_anchor",
                    "provider": "okx",
                    "price_usd": 1.23,
                    "quote_symbol": "USD",
                    "price_basis": "usd",
                    "observed_at_ms": 1_700_000_000_000,
                },
                "decision_latest": None,
                "readiness": {
                    "anchor_status": "ready",
                    "latest_status": "missing",
                    "dex_floor_status": "missing_fields",
                    "missing_fields": ["holders", "liquidity_usd", "market_cap_usd"],
                    "stale_fields": [],
                },
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
