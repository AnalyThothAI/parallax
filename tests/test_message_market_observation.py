from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxCexTicker, OkxDexTokenPrice
from gmgn_twitter_intel.pipeline.message_market_observation import observe_message_market
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_RESOLVER_POLICY_VERSION


def test_message_market_observation_writes_cex_message_quote():
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
    result = observe_message_market(
        repos=repos,
        cex_client=FakeCexClient(
            {
                "BTC-USDT": OkxCexTicker(
                    inst_id="BTC-USDT",
                    inst_type="SPOT",
                    last_price=70_000.0,
                    volume_24h=1_000_000.0,
                    open_interest=None,
                    raw={"instId": "BTC-USDT"},
                )
            }
        ),
        dex_client=None,
        now_ms=1_700_000_001_000,
        limit=10,
    )

    assert result["rows_selected"] == 1
    assert result["observations_written"] == 1
    observation = repos.price_observations.observations[0]
    assert observation["observation_kind"] == "message_quote"
    assert observation["source_event_id"] == "event-1"
    assert observation["source_intent_id"] == "intent-1"
    assert observation["source_resolution_id"] == "resolution-1"
    assert observation["observation_lag_ms"] == 1_000
    assert observation["price_usd"] == 70_000.0
    assert "po.source_resolution_id = tir.resolution_id" in repos.conn.sql
    assert "po.source_intent_id = tir.intent_id" not in repos.conn.sql
    assert "tir.resolver_policy_version = %s" in repos.conn.sql
    assert repos.conn.params[0] == TOKEN_RADAR_RESOLVER_POLICY_VERSION


def test_message_market_observation_writes_dex_message_quote_per_message():
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
            },
        ]
    )
    result = observe_message_market(
        repos=repos,
        cex_client=None,
        dex_client=FakeDexClient(
            [
                OkxDexTokenPrice(
                    chain_index="1",
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
    assert result["observations_written"] == 2
    assert [item["source_event_id"] for item in repos.price_observations.observations] == ["event-1", "event-2"]
    assert {item["source_resolution_id"] for item in repos.price_observations.observations} == {
        "resolution-1",
        "resolution-2",
    }


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


class FakeCexClient:
    def __init__(self, tickers):
        self.tickers = tickers
        self.calls = []

    def ticker(self, *, inst_id):
        self.calls.append(inst_id)
        return self.tickers.get(inst_id)


class FakeDexClient:
    def __init__(self, prices):
        self.prices = prices
        self.calls = []

    def token_prices(self, tokens):
        self.calls.append(tokens)
        return self.prices
