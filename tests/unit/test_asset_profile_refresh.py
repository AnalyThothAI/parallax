from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import DexProviderTemporarilyUnavailable, DexTokenProfile
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import (
    ERROR_REFRESH_MS,
    GMGN_DEX_PROFILE_PROVIDER,
    MISSING_REFRESH_MS,
    READY_REFRESH_MS,
)
from gmgn_twitter_intel.domains.asset_market.services.asset_profile_refresh import refresh_asset_profiles_once


def test_refresh_asset_profiles_writes_ready_profile_and_calls_provider_with_exact_target():
    repos = FakeRepos(
        rows=[
            {
                "asset_id": "asset:eip155:1:erc20:0xabc",
                "chain_id": "eip155:1",
                "address": "0xAbC",
                "symbol": "ABC",
                "latest_event_received_at_ms": 1_700_000_000_000,
                "profile_status": None,
                "next_refresh_at_ms": None,
            }
        ]
    )
    provider = FakeProfileProvider(
        profile=DexTokenProfile(
            chain_id="eip155:1",
            address="0xabc",
            symbol="ABC",
            name="ABC Token",
            logo_url="https://img.example/abc.png",
            banner_url=None,
            website="https://abc.example",
            twitter_username="abc",
            telegram="https://t.me/abc",
            gmgn_url="https://gmgn.ai/eth/token/0xabc",
            geckoterminal_url=None,
            description="project profile",
            raw={"link": {"website": "https://abc.example"}},
        )
    )

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=provider, now_ms=10_000, limit=5)

    assert result == {
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "selected": 1,
        "ready": 1,
        "missing": 0,
        "error": 0,
        "skipped": 0,
        "started_at_ms": 10_000,
        "finished_at_ms": 10_000,
    }
    assert provider.calls == [("eip155:1", "0xAbC")]
    assert repos.conn.params == (
        "token-radar-v13-social-attention",
        "token-radar-v13-social-attention",
        10_000 - 24 * 60 * 60 * 1000,
        50,
        "token_radar_v5_identity_resolver",
        GMGN_DEX_PROFILE_PROVIDER,
        10_000,
        5,
    )
    assert repos.asset_profiles.ready_profiles == [
        {
            "asset_id": "asset:eip155:1:erc20:0xabc",
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "symbol": "ABC",
            "name": "ABC Token",
            "logo_url": "https://img.example/abc.png",
            "banner_url": None,
            "website_url": "https://abc.example",
            "twitter_username": "abc",
            "twitter_url": None,
            "telegram_url": "https://t.me/abc",
            "gmgn_url": "https://gmgn.ai/eth/token/0xabc",
            "geckoterminal_url": None,
            "description": "project profile",
            "raw_payload": {"link": {"website": "https://abc.example"}},
            "observed_at_ms": 10_000,
            "next_refresh_at_ms": 10_000 + READY_REFRESH_MS,
        }
    ]


def test_refresh_asset_profiles_writes_missing_row_when_provider_returns_none():
    repos = FakeRepos(
        rows=[
            {
                "asset_id": "asset:solana:token:missing",
                "chain_id": "solana",
                "address": "Missing1111111111111111111111111111111111111",
            }
        ]
    )
    provider = FakeProfileProvider(profile=None)

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=provider, now_ms=20_000, limit=10)

    assert result["selected"] == 1
    assert result["missing"] == 1
    assert repos.asset_profiles.status_profiles == [
        {
            "asset_id": "asset:solana:token:missing",
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "status": "missing",
            "observed_at_ms": 20_000,
            "next_refresh_at_ms": 20_000 + MISSING_REFRESH_MS,
            "last_error": None,
        }
    ]


def test_refresh_asset_profiles_writes_error_row_and_continues_when_provider_raises():
    repos = FakeRepos(
        rows=[
            {
                "asset_id": "asset:eip155:1:erc20:0xbad",
                "chain_id": "eip155:1",
                "address": "0xbad",
            },
            {
                "asset_id": "asset:eip155:1:erc20:0xgood",
                "chain_id": "eip155:1",
                "address": "0xgood",
            },
        ]
    )
    provider = SequencedProfileProvider(
        [
            RuntimeError("rate limited " + ("x" * 600)),
            DexTokenProfile(
                chain_id="eip155:1",
                address="0xgood",
                symbol="GOOD",
                name=None,
                logo_url=None,
                banner_url=None,
                website=None,
                twitter_username=None,
                telegram=None,
                gmgn_url=None,
                geckoterminal_url=None,
                description=None,
                raw={"ok": True},
            ),
        ]
    )

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=provider, now_ms=30_000, limit=10)

    assert result["selected"] == 2
    assert result["error"] == 1
    assert result["ready"] == 1
    assert provider.calls == [("eip155:1", "0xbad"), ("eip155:1", "0xgood")]
    assert repos.asset_profiles.status_profiles[0]["asset_id"] == "asset:eip155:1:erc20:0xbad"
    assert repos.asset_profiles.status_profiles[0]["status"] == "error"
    assert repos.asset_profiles.status_profiles[0]["next_refresh_at_ms"] == 30_000 + ERROR_REFRESH_MS
    assert len(repos.asset_profiles.status_profiles[0]["last_error"]) == 500
    assert repos.asset_profiles.ready_profiles[0]["asset_id"] == "asset:eip155:1:erc20:0xgood"


def test_refresh_asset_profiles_stops_batch_without_polluting_profiles_when_provider_is_blocked():
    repos = FakeRepos(
        rows=[
            {
                "asset_id": "asset:eip155:8453:erc20:0xblocked",
                "chain_id": "eip155:8453",
                "address": "0xblocked",
            },
            {
                "asset_id": "asset:eip155:8453:erc20:0xuntried",
                "chain_id": "eip155:8453",
                "address": "0xuntried",
            },
        ]
    )
    provider = SequencedProfileProvider(
        [
            DexProviderTemporarilyUnavailable("GET /v1/token/info blocked by Cloudflare challenge HTTP 403"),
            DexTokenProfile(
                chain_id="eip155:8453",
                address="0xuntried",
                symbol="UNTRIED",
                name=None,
                logo_url=None,
                banner_url=None,
                website=None,
                twitter_username=None,
                telegram=None,
                gmgn_url=None,
                geckoterminal_url=None,
                description=None,
                raw={},
            ),
        ]
    )

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=provider, now_ms=35_000, limit=10)

    assert result["selected"] == 2
    assert result["provider_blocked"] == 1
    assert result["last_error"] == "GET /v1/token/info blocked by Cloudflare challenge HTTP 403"
    assert result["error"] == 0
    assert result["ready"] == 0
    assert provider.calls == [("eip155:8453", "0xblocked")]
    assert repos.asset_profiles.status_profiles == []
    assert repos.asset_profiles.ready_profiles == []


def test_refresh_asset_profiles_returns_skipped_when_provider_is_none_without_db_access():
    repos = FakeRepos(rows=[])

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=None, now_ms=40_000, limit=10)

    assert result == {
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "selected": 0,
        "ready": 0,
        "missing": 0,
        "error": 0,
        "skipped": 1,
        "started_at_ms": 40_000,
        "finished_at_ms": 40_000,
    }
    assert repos.conn.executed_sql == []
    assert repos.asset_profiles.ready_profiles == []
    assert repos.asset_profiles.status_profiles == []


class FakeRepos:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.conn = FakeConn(rows)
        self.asset_profiles = FakeAssetProfileRepository()


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed_sql: list[str] = []
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> FakeCursor:
        self.executed_sql.append(str(sql))
        self.params = tuple(params or ())
        return FakeCursor(self.rows)


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeAssetProfileRepository:
    def __init__(self) -> None:
        self.ready_profiles: list[dict[str, Any]] = []
        self.status_profiles: list[dict[str, Any]] = []

    def upsert_ready_profile(self, **kwargs: Any) -> None:
        self.ready_profiles.append(kwargs)

    def upsert_status(self, **kwargs: Any) -> None:
        self.status_profiles.append(kwargs)


class FakeProfileProvider:
    def __init__(self, *, profile: DexTokenProfile | None) -> None:
        self.profile = profile
        self.calls: list[tuple[str, str]] = []

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        self.calls.append((chain_id, address))
        return self.profile


class SequencedProfileProvider:
    def __init__(self, items: list[DexTokenProfile | Exception]) -> None:
        self.items = list(items)
        self.calls: list[tuple[str, str]] = []

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        self.calls.append((chain_id, address))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
