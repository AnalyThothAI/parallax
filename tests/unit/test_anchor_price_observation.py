from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.providers import CexTicker, DexTokenPrice
from gmgn_twitter_intel.domains.asset_market.services.anchor_price_observation import observe_anchor_prices
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION


def test_anchor_price_observation_writes_cex_message_anchor():
    repos = FakeRepos(
        rows=[
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": "CexToken",
                "target_id": "cex-token:BTC",
                "pricefeed_id": "pricefeed:okx:BTC-USDT",
                "event_received_at_ms": 1_700_000_000_000,
                "native_market_id": "BTC-USDT",
                "pricefeed_quote_symbol": "USDT",
            }
        ]
    )
    result = observe_anchor_prices(
        repos=repos,
        cex_market=FakeCexMarket(
            {
                "BTC-USDT": CexTicker(
                    inst_id="BTC-USDT",
                    inst_type="SPOT",
                    last_price=70_000.0,
                    volume_24h=1_000_000.0,
                    open_interest=None,
                    raw={"instId": "BTC-USDT"},
                )
            }
        ),
        dex_market=None,
        now_ms=1_700_000_001_000,
        limit=10,
    )

    assert result["rows_selected"] == 1
    assert result["anchor_observations_written"] == 1
    observation = repos.price_observations.observations[0]
    assert observation["provider"] == "okx"
    assert observation["observation_kind"] == "message_anchor"
    assert observation["source_event_id"] == "event-1"
    assert observation["source_intent_id"] == "intent-1"
    assert observation["source_resolution_id"] == "resolution-1"
    assert observation["observation_lag_ms"] == 1_000
    assert observation["price_usd"] == 70_000.0
    assert "po.source_resolution_id = tir.resolution_id" in repos.conn.sql
    assert "po.source_intent_id = tir.intent_id" not in repos.conn.sql
    assert "tir.resolver_policy_version = %s" in repos.conn.sql
    assert repos.conn.params[0] == TOKEN_RADAR_RESOLVER_POLICY_VERSION
    assert "CASE WHEN events.received_at_ms >= %s THEN 0 ELSE 1 END" in repos.conn.sql
    assert "events.received_at_ms DESC" in repos.conn.sql
    assert repos.conn.params[-2] == 1_700_000_001_000 - 60 * 60 * 1000
    assert repos.conn.params[-1] == 10


def test_anchor_price_observation_writes_dex_message_anchor_per_message():
    repos = FakeRepos(
        rows=[
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xabc",
                "pricefeed_id": None,
                "event_received_at_ms": 1_700_000_000_000,
                "asset_chain_id": "eip155:1",
                "asset_address": "0xabc",
                "asset_symbol": "ABC",
                "asset_market_cap_usd": 22_000.0,
                "asset_liquidity_usd": 9_000.0,
                "asset_holders": 123,
            },
            {
                "event_id": "event-2",
                "intent_id": "intent-2",
                "resolution_id": "resolution-2",
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xabc",
                "pricefeed_id": None,
                "event_received_at_ms": 1_700_000_000_500,
                "asset_chain_id": "eip155:1",
                "asset_address": "0xabc",
                "asset_symbol": "ABC",
                "asset_market_cap_usd": 23_000.0,
                "asset_liquidity_usd": 10_000.0,
                "asset_holders": 124,
            },
        ]
    )
    result = observe_anchor_prices(
        repos=repos,
        cex_market=None,
        dex_market=FakeDexMarket(
            [
                DexTokenPrice(
                    chain_id="eip155:1",
                    address="0xabc",
                    observed_at_ms=1_700_000_001_000,
                    price_usd=1.23,
                    raw={"price": "1.23"},
                )
            ]
        ),
        now_ms=1_700_000_001_000,
        limit=10,
    )

    assert result["rows_selected"] == 2
    assert result["dex_price_requests"] == 1
    assert result["anchor_observations_written"] == 2
    assert [item["source_event_id"] for item in repos.price_observations.observations] == ["event-1", "event-2"]
    assert {item["source_resolution_id"] for item in repos.price_observations.observations} == {
        "resolution-1",
        "resolution-2",
    }
    dex_quote_observations = [
        item
        for item in repos.price_observations.observations
        if item["provider"] == "okx" and item["observation_kind"] == "message_anchor"
    ]
    assert len(dex_quote_observations) == 2
    assert all(item["price_usd"] == 1.23 for item in dex_quote_observations)
    assert [
        (item.get("market_cap_usd"), item.get("liquidity_usd"), item.get("holders")) for item in dex_quote_observations
    ] == [(None, None, None), (None, None, None)]


class FakeRepos:
    def __init__(self, rows):
        self.conn = FakeConn(rows)
        self.price_observations = FakePriceObservations()
        self.registry = FakeRegistry()


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()
        self.commits = 0

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = tuple(params or ())
        return self

    def fetchall(self):
        return self.rows

    def commit(self):
        self.commits += 1


class FakePriceObservations:
    def __init__(self):
        self.observations = []

    def insert_observation(self, **kwargs):
        if kwargs.get("event_received_at_ms") is not None:
            kwargs["observation_lag_ms"] = kwargs["observed_at_ms"] - kwargs["event_received_at_ms"]
        self.observations.append(kwargs)
        return kwargs


class FakeRegistry:
    def upsert_pricefeed(self, **kwargs):
        return {"pricefeed_id": kwargs.get("pricefeed_id") or "pricefeed:dex:ABC"}


class FakeCexMarket:
    def __init__(self, tickers):
        self.tickers = tickers
        self.calls = []

    def ticker(self, *, inst_id):
        self.calls.append(inst_id)
        return self.tickers.get(inst_id)


class FakeDexMarket:
    def __init__(self, prices):
        self.prices = prices
        self.calls = []

    def token_prices(self, tokens):
        self.calls.append(tokens)
        return self.prices
