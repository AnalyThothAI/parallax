from __future__ import annotations

import pytest

from parallax.domains.asset_market.services.cex_token_profile_sync import sync_cex_token_profiles


def test_sync_cex_token_profiles_writes_source_cache_for_existing_cex_tokens_only():
    profiles = _CexTokenProfiles(existing_symbols={"BTC"})
    result = sync_cex_token_profiles(
        cex_token_profiles=profiles,
        profile_source=_ProfileSource(),
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
            "commit": False,
        }
    ]
    assert profiles.conn.events == ["enter", "exit"]
    assert profiles.conn.commits == 0


def test_sync_cex_token_profiles_requires_transaction_before_writes():
    profiles = _CexTokenProfiles(existing_symbols={"BTC"}, conn=object())

    with pytest.raises(RuntimeError, match="cex_token_profile_sync_transaction_required"):
        sync_cex_token_profiles(
            cex_token_profiles=profiles,
            profile_source=_ProfileSource(),
            observed_at_ms=1_778_000_000_000,
        )

    assert profiles.upserts == []


class _ProfileSource:
    def token_profiles(self):
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


class _Conn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_depth = 0
        self.events: list[str] = []

    def transaction(self):
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("sync_cex_token_profiles must use conn.transaction(), not conn.commit()")


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
