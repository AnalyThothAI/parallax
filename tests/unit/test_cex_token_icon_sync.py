from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.services.cex_token_icon_sync import sync_cex_token_icons


def test_sync_cex_token_icons_updates_existing_cex_tokens_only():
    registry = _Registry(existing_symbols={"BTC"})
    result = sync_cex_token_icons(
        registry=registry,
        icon_source=_IconSource(),
        observed_at_ms=1_778_000_000_000,
    )

    assert result == {
        "icons_seen": 2,
        "icons_updated": 1,
        "missing_cex_tokens": 1,
        "affected_lookup_keys": ["cex_token:BTC", "project_symbol:BTC", "symbol:BTC"],
        "source": "binance_marketing_symbol_list",
    }
    assert registry.icon_updates == [
        {
            "base_symbol": "BTC",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source": "binance_marketing_symbol_list",
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
    ]
    assert registry.conn.commits == 1


class _IconSource:
    def token_icons(self):
        return [
            {
                "base_symbol": "BTC",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source": "binance_marketing_symbol_list",
            },
            {
                "base_symbol": "NOTROUTED",
                "logo_url": "https://bin.bnbstatic.com/notrouted.png",
                "source": "binance_marketing_symbol_list",
            },
        ]


class _Registry:
    def __init__(self, *, existing_symbols: set[str]) -> None:
        self.conn = _Conn()
        self.existing_symbols = existing_symbols
        self.icon_updates: list[dict] = []

    def update_cex_token_icon(self, **kwargs):
        if kwargs["base_symbol"] not in self.existing_symbols:
            return None
        self.icon_updates.append(kwargs)
        return {"cex_token_id": f"cex_token:{kwargs['base_symbol']}"}


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
