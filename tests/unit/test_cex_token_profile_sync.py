from __future__ import annotations

import pytest

from parallax.domains.asset_market.services.cex_token_profile_sync import sync_cex_token_profiles


def test_sync_cex_token_profiles_writes_source_cache_for_existing_cex_tokens_only():
    profiles = _CexTokenProfiles(existing_symbols={"BTC"})
    result = sync_cex_token_profiles(
        repos=_Repos(profiles),
        profiles=_profiles(),
        observed_at_ms=1_778_000_000_000,
    )

    assert result == {
        "profiles_seen": 2,
        "profiles_updated": 1,
        "missing_cex_tokens": 1,
        "affected_lookup_keys": ["cex_token:BTC", "project_symbol:BTC", "symbol:BTC"],
        "provider": "binance_cex_profile",
    }
    assert profiles.upserts == [
        {
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "symbol": "BTC",
            "name": "Bitcoin",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source_ref": "binance_marketing_symbol_list:BTC",
            "raw_payload": {"rank": 1},
            "observed_at_ms": 1_778_000_000_000,
        }
    ]
    assert profiles.conn.events == ["enter", "exit"]
    assert profiles.conn.commits == 0


def test_sync_cex_token_profiles_requires_transaction_before_writes():
    profiles = _CexTokenProfiles(existing_symbols={"BTC"}, conn=object())

    with pytest.raises(AttributeError, match="transaction"):
        sync_cex_token_profiles(
            repos=_Repos(profiles),
            profiles=_profiles(),
            observed_at_ms=1_778_000_000_000,
        )

    assert profiles.upserts == []


def test_sync_cex_token_profiles_rejects_object_profile_compatibility_before_transaction():
    profiles = _CexTokenProfiles(existing_symbols={"BTC"})

    with pytest.raises(TypeError, match="cex_token_profile_sync_profile_mapping_required"):
        sync_cex_token_profiles(
            repos=_Repos(profiles),
            profiles=[_ObjectProfile()],  # type: ignore[list-item]
            observed_at_ms=1_778_000_000_000,
        )

    assert profiles.upserts == []
    assert profiles.conn.events == []


@pytest.mark.parametrize(
    ("profile", "error"),
    [
        pytest.param(
            {
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload": {"rank": 1},
            },
            "cex_token_profile_sync_base_symbol_required",
            id="missing-base-symbol",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload": {"rank": 1},
            },
            "cex_token_profile_sync_provider_required",
            id="missing-provider",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload": {"rank": 1},
            },
            "cex_token_profile_sync_symbol_required",
            id="missing-symbol",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "not-a-url",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload": {"rank": 1},
            },
            "cex_token_profile_sync_logo_url_invalid",
            id="bad-logo-url",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "raw_payload": {"rank": 1},
            },
            "cex_token_profile_sync_source_ref_required",
            id="missing-source-ref",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
            },
            "cex_token_profile_sync_raw_payload_required",
            id="missing-raw-payload",
        ),
        pytest.param(
            {
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
                "raw_payload": [],
            },
            "cex_token_profile_sync_raw_payload_invalid",
            id="bad-raw-payload",
        ),
    ],
)
def test_sync_cex_token_profiles_requires_formal_provider_profile_before_transaction(
    profile,
    error,
):
    profiles = _CexTokenProfiles(existing_symbols={"BTC"})

    with pytest.raises((TypeError, ValueError), match=error):
        sync_cex_token_profiles(
            repos=_Repos(profiles),
            profiles=[profile],
            observed_at_ms=1_778_000_000_000,
        )

    assert profiles.upserts == []
    assert profiles.conn.events == []


def _profiles() -> list[dict[str, object]]:
    return [
        {
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "symbol": "BTC",
            "name": "Bitcoin",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source_ref": "binance_marketing_symbol_list:BTC",
            "raw_payload": {"rank": 1},
        },
        {
            "base_symbol": "NOTROUTED",
            "provider": "binance_cex_profile",
            "symbol": "NOTROUTED",
            "name": "Missing",
            "logo_url": "https://bin.bnbstatic.com/notrouted.png",
            "source_ref": "binance_marketing_symbol_list:NOTROUTED",
            "raw_payload": {"rank": 2},
        },
    ]


class _ObjectProfile:
    def __init__(self) -> None:
        self.base_symbol = "BTC"
        self.provider = "binance_cex_profile"
        self.symbol = "BTC"
        self.name = "Bitcoin"
        self.logo_url = "https://bin.bnbstatic.com/btc.png"
        self.source_ref = "binance_marketing_symbol_list:BTC"
        self.raw_payload = {"rank": 1}


class _CexTokenProfiles:
    def __init__(self, *, existing_symbols: set[str], conn=None) -> None:
        self.conn = conn or _Conn()
        self.existing_symbols = existing_symbols
        self.upserts: list[dict] = []

    def upsert_ready_profile_if_token_exists(self, **kwargs):
        assert self.conn.transaction_depth == 1
        if kwargs["base_symbol"] not in self.existing_symbols:
            return None
        self.upserts.append(kwargs)
        return {"cex_token_id": f"cex_token:{kwargs['base_symbol']}"}


class _Repos:
    def __init__(self, cex_token_profiles) -> None:
        self.cex_token_profiles = cex_token_profiles

    def transaction(self):
        return self.cex_token_profiles.conn.transaction()


class _Conn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_depth = 0
        self.events: list[str] = []

    def transaction(self):
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("sync_cex_token_profiles must use repos.transaction(), not conn.commit()")


class _Transaction:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        self.conn.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.events.append("rollback" if exc_type is not None else "exit")
        self.conn.transaction_depth -= 1
        return False
