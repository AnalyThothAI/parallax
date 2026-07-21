from __future__ import annotations

from typing import Any

from parallax.domains.asset_market.providers import DexTokenProfile
from parallax.domains.asset_market.repositories.asset_profile_repository import (
    GMGN_DEX_PROFILE_PROVIDER,
)
from parallax.domains.asset_market.services.asset_profile_refresh import (
    write_error_asset_profile,
    write_missing_asset_profile,
    write_ready_asset_profile,
)

NOW_MS = 1_779_000_000_000
ASSET_ID = "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108"


def test_asset_profile_refresh_service_writes_are_caller_owned() -> None:
    repos = _ServiceRepos()
    row = {"target_id": ASSET_ID}
    profile = DexTokenProfile(
        chain_id="eip155:1",
        address="0x999b49c0d1612e619a4a4f6280733184da025108",
        symbol="SAT",
        name="Sato",
        logo_url="https://assets.example/sat.png",
        banner_url=None,
        website="https://sat.example",
        twitter_username="sattoken",
        telegram=None,
        gmgn_url=None,
        geckoterminal_url=None,
        description="profile",
        raw={"status": "ready"},
    )

    write_ready_asset_profile(
        repos=repos,
        provider=GMGN_DEX_PROFILE_PROVIDER,
        row=row,
        profile=profile,
        now_ms=NOW_MS,
        next_refresh_at_ms=NOW_MS + 1_000,
    )
    write_missing_asset_profile(
        repos=repos,
        provider=GMGN_DEX_PROFILE_PROVIDER,
        row=row,
        now_ms=NOW_MS,
        next_refresh_at_ms=NOW_MS + 2_000,
    )
    write_error_asset_profile(
        repos=repos,
        provider=GMGN_DEX_PROFILE_PROVIDER,
        row=row,
        exc=RuntimeError("provider failed"),
        now_ms=NOW_MS,
        next_refresh_at_ms=NOW_MS + 3_000,
    )

    assert repos.asset_profiles.calls == [
        ("ready", NOW_MS + 1_000),
        ("missing", NOW_MS + 2_000),
        ("error", NOW_MS + 3_000),
    ]


class _ServiceRepos:
    def __init__(self) -> None:
        self.asset_profiles = _ServiceAssetProfiles()


class _ServiceAssetProfiles:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def upsert_ready_profile(self, **kwargs: Any) -> None:
        self.calls.append(("ready", int(kwargs["next_refresh_at_ms"])))

    def upsert_status(self, **kwargs: Any) -> None:
        self.calls.append((str(kwargs["status"]), int(kwargs["next_refresh_at_ms"])))
