from __future__ import annotations

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
    assert profiles.conn.commits == 1


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
    def __init__(self, *, existing_symbols: set[str]) -> None:
        self.conn = _Conn()
        self.existing_symbols = existing_symbols
        self.upserts: list[dict] = []

    def upsert_ready_profile_if_token_exists(self, **kwargs):
        if kwargs["base_symbol"] not in self.existing_symbols:
            return None
        self.upserts.append(kwargs)
        return {"cex_token_id": f"cex_token:{kwargs['base_symbol']}"}


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
