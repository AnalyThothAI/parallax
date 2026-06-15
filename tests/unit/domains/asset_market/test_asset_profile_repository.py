from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.providers import DexTokenProfile
from parallax.domains.asset_market.repositories.asset_profile_repository import (
    GMGN_DEX_PROFILE_PROVIDER,
    AssetProfileRepository,
)
from parallax.domains.asset_market.services.asset_profile_refresh import (
    write_error_asset_profile,
    write_missing_asset_profile,
    write_ready_asset_profile,
)

NOW_MS = 1_779_000_000_000
ASSET_ID = "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108"

ProfileWrite = Callable[[AssetProfileRepository], None]


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(
            lambda repository: repository.upsert_ready_profile(
                asset_id=ASSET_ID,
                provider=GMGN_DEX_PROFILE_PROVIDER,
                symbol="SAT",
                name="Sato",
                logo_url="https://assets.example/sat.png",
                banner_url=None,
                website_url="https://sat.example",
                twitter_username="sattoken",
                twitter_url=None,
                telegram_url=None,
                gmgn_url=None,
                geckoterminal_url=None,
                description="profile",
                raw_payload={"status": "ready"},
                observed_at_ms=NOW_MS,
                next_refresh_at_ms=NOW_MS + 60_000,
            ),
            id="ready",
        ),
        pytest.param(
            lambda repository: repository.upsert_status(
                asset_id=ASSET_ID,
                provider=GMGN_DEX_PROFILE_PROVIDER,
                status="missing",
                observed_at_ms=NOW_MS,
                next_refresh_at_ms=NOW_MS + 60_000,
                last_error=None,
                raw_payload={"status": "missing"},
            ),
            id="status",
        ),
    ],
)
def test_asset_profile_mutations_require_connection_transaction_before_sql_when_committing(
    write: ProfileWrite,
) -> None:
    conn = NoTransactionAssetProfileConnection()
    repository = AssetProfileRepository(conn)

    with pytest.raises(RuntimeError, match="asset_profile_repository_transaction_required"):
        write(repository)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(
            lambda repository: repository.upsert_ready_profile(
                asset_id=ASSET_ID,
                provider=GMGN_DEX_PROFILE_PROVIDER,
                symbol="SAT",
                name="Sato",
                logo_url="https://assets.example/sat.png",
                banner_url=None,
                website_url="https://sat.example",
                twitter_username="sattoken",
                twitter_url=None,
                telegram_url=None,
                gmgn_url=None,
                geckoterminal_url=None,
                description="profile",
                raw_payload={"status": "ready"},
                observed_at_ms=NOW_MS,
                next_refresh_at_ms=NOW_MS + 60_000,
            ),
            id="ready",
        ),
        pytest.param(
            lambda repository: repository.upsert_status(
                asset_id=ASSET_ID,
                provider=GMGN_DEX_PROFILE_PROVIDER,
                status="error",
                observed_at_ms=NOW_MS,
                next_refresh_at_ms=NOW_MS + 60_000,
                last_error="provider failed",
                raw_payload={"status": "error"},
            ),
            id="status",
        ),
    ],
)
def test_asset_profile_commit_owned_writes_use_connection_transaction_without_manual_commit(
    write: ProfileWrite,
) -> None:
    conn = FakeAssetProfileConnection()
    repository = AssetProfileRepository(conn)

    write(repository)

    assert conn.transaction_commits == 1
    assert conn.commits == 0
    assert conn.sql_depths
    assert set(conn.sql_depths) == {1}


def test_asset_profile_refresh_service_writes_are_caller_owned_inside_worker_transaction() -> None:
    repos = _ServiceRepos()
    row = {"asset_id": ASSET_ID}
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
        ("ready", False, NOW_MS + 1_000),
        ("missing", False, NOW_MS + 2_000),
        ("error", False, NOW_MS + 3_000),
    ]


class FakeAssetProfileConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.sql_depths: list[int] = []
        self.commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: Any = None) -> object:
        self.sql.append(" ".join(str(sql).split()))
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        return object()

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1


class NoTransactionAssetProfileConnection(FakeAssetProfileConnection):
    transaction = None


class _Transaction:
    def __init__(self, conn: FakeAssetProfileConnection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.transaction_depth += 1

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1


class _ServiceRepos:
    def __init__(self) -> None:
        self.asset_profiles = _ServiceAssetProfiles()


class _ServiceAssetProfiles:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, int]] = []

    def upsert_ready_profile(self, **kwargs: Any) -> None:
        self.calls.append(("ready", bool(kwargs["commit"]), int(kwargs["next_refresh_at_ms"])))

    def upsert_status(self, **kwargs: Any) -> None:
        self.calls.append((str(kwargs["status"]), bool(kwargs["commit"]), int(kwargs["next_refresh_at_ms"])))
