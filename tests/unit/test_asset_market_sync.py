from __future__ import annotations

import asyncio
import time

from gmgn_twitter_intel.domains.asset_market.providers import CexTicker, DexTokenCandidate, DexTokenPrice
from gmgn_twitter_intel.domains.asset_market.runtime.asset_market_sync_worker import AssetMarketSyncWorker
from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import (
    sync_cex_universe,
    sync_dex_prices,
)


def test_sync_cex_universe_writes_instruments_and_market_snapshots():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    cex_market = FakeCexMarket()

    result = sync_cex_universe(
        registry=registry,
        price_observations=price_observations,
        cex_market=cex_market,
        inst_types=("SPOT",),
        observed_at_ms=1_700_000_000_000,
    )

    assert result == {
        "inst_types": ["SPOT"],
        "cex_tokens_written": 1,
        "pricefeeds_written": 1,
        "price_observations_written": 1,
        "affected_lookup_keys": ["cex_token:BTC", "project_symbol:BTC", "symbol:BTC"],
    }
    assert cex_market.instrument_requests == []
    assert cex_market.ticker_requests == ["SPOT"]
    assert registry.cex_tokens == [{"base_symbol": "BTC"}]
    assert registry.pricefeeds == [
        {
            "feed_type": "cex_spot",
            "provider": "okx",
            "subject_type": "CexToken",
            "subject_id": "cex_token:BTC",
            "native_market_id": "BTC-USDT",
            "base_cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
        }
    ]
    assert price_observations.observations == [
        {
            "provider": "okx_cex",
            "pricefeed_id": "pricefeed:cex:okx:spot:BTC-USDT",
            "subject_type": "CexToken",
            "subject_id": "cex_token:BTC",
            "price_usd": 69000.0,
            "price_quote": 69000.0,
            "quote_symbol": "USDT",
            "price_basis": "quote_as_usd",
            "volume_24h_usd": 1234567.0,
            "open_interest_usd": None,
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
        }
    ]


def test_asset_market_sync_worker_runs_one_cex_sync_cycle():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    cex_market = FakeCexMarket()
    session = FakeRepositorySession(registry, price_observations)
    worker = AssetMarketSyncWorker(
        cex_market=cex_market,
        repository_session=lambda: session,
        inst_types=("SPOT",),
        interval_seconds=300,
    )

    result = worker.sync_once(now_ms=1_700_000_000_000)

    assert result["price_observations_written"] == 1
    assert result["resolution_refresh"]["reprocessed_intents"] == 0
    assert worker.last_result is None
    assert price_observations.observations[0]["price_usd"] == 69000.0


def test_asset_market_sync_worker_runs_dex_before_cex():
    events = []
    registry = FakeRegistry(events=events)
    registry.dex_refresh_rows = [
        {
            "asset_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
            "identity_confidence": "provider_exact",
        }
    ]
    session = FakeRepositorySession(registry, FakePriceObservations())
    worker = AssetMarketSyncWorker(
        cex_market=FakeCexMarket(events=events),
        dex_market=FakeDexMarket(events=events),
        repository_session=lambda: session,
        inst_types=("SPOT",),
        interval_seconds=300,
    )

    result = worker.sync_once(now_ms=1_778_085_100_000)

    assert list(result) == ["dex", "cex"]
    assert events[:2] == ["dex_prices", "cex_tickers:SPOT"]


def test_asset_market_sync_worker_records_cex_while_dex_is_still_running():
    async def scenario():
        events = []
        registry = FakeRegistry(events=events)
        registry.dex_refresh_rows = [
            {
                "asset_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
                "chain_id": "eip155:56",
                "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
                "identity_confidence": "provider_exact",
            }
        ]
        price_observations = FakePriceObservations()
        worker = AssetMarketSyncWorker(
            cex_market=FakeCexMarket(events=events),
            dex_market=FakeDexMarket(events=events, delay_seconds=0.2),
            repository_session=lambda: FakeRepositorySession(registry, price_observations),
            inst_types=("SPOT",),
            interval_seconds=1,
        )
        task = asyncio.create_task(worker.run())
        try:
            deadline = time.monotonic() + 1
            while worker.provider_states["cex"]["last_run_at_ms"] is None and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert worker.provider_states["cex"]["last_result"]["price_observations_written"] == 1
            assert worker.provider_states["dex"]["running"] is True
            assert worker.last_run_at_ms == worker.provider_states["cex"]["last_run_at_ms"]
        finally:
            worker.stop()
            await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())


def test_sync_dex_prices_refreshes_active_dex_venues_in_batches():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    registry.dex_refresh_rows = [
        {
            "asset_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
            "symbol": "TEST",
            "identity_confidence": "provider_exact",
            "market_cap_usd": 22_000.0,
            "liquidity_usd": 9_000.0,
            "holders": 123,
        }
    ]
    dex_market = FakeDexMarket()

    result = sync_dex_prices(
        registry=registry,
        identity_evidence=FakeIdentityEvidence(),
        price_observations=price_observations,
        dex_market=dex_market,
        observed_at_ms=1_778_085_100_000,
        stale_after_ms=300_000,
        limit=100,
    )

    assert result == {
        "assets_scanned": 1,
        "refresh_universe": "radar_candidates",
        "refresh_candidates_selected": 1,
        "refresh_candidates_hot": 0,
        "refresh_candidates_stale": 0,
        "refresh_candidates_missing": 1,
        "identity_verification_requests": 0,
        "identity_verification_hits": 0,
        "identity_verification_errors": 0,
        "price_requests": 1,
        "pricefeeds_written": 1,
        "price_observations_written": 1,
        "affected_lookup_keys": [
            "address:eip155:56:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "project_symbol:TEST",
            "symbol:TEST",
        ],
    }
    assert registry.radar_refresh_calls == [
        {
            "stale_before_ms": 1_778_084_800_000,
            "radar_since_ms": 1_777_998_700_000,
            "hot_since_ms": 1_778_081_500_000,
            "limit": 500,
        }
    ]
    assert registry.global_refresh_calls == []
    assert [(item.chain_id, item.address) for item in dex_market.price_requests[0]] == [
        ("eip155:56", "0x8f32420f2e3728c49399b00dd0a796602d984444")
    ]
    dex_price_observation = [item for item in price_observations.observations if item["provider"] == "okx_dex_price"][
        -1
    ]
    assert dex_price_observation == {
        "provider": "okx_dex_price",
        "pricefeed_id": "pricefeed:dex-token:okx_dex_price:eip155:56:0x8f32420f2e3728c49399b00dd0a796602d984444",
        "subject_type": "Asset",
        "subject_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
        "price_usd": 0.00002237,
        "price_quote": None,
        "quote_symbol": None,
        "price_basis": "usd",
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "holders": None,
    }


def test_sync_dex_prices_prioritizes_hot_stale_radar_candidate():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    registry.dex_refresh_rows = [
        {
            "asset_id": "warm-old",
            "chain_id": "eip155:56",
            "address": "0xwarm",
            "identity_confidence": "provider_exact",
            "latest_candidate_received_at_ms": 1_777_990_000_000,
            "candidate_event_count": 10,
            "latest_price_observed_at_ms": 1_777_990_000_000,
        },
        {
            "asset_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8f32420f2e3728c49399b00dd0a796602d984444",
            "identity_confidence": "provider_exact",
            "latest_candidate_received_at_ms": 1_778_000_050_000,
            "candidate_event_count": 2,
            "latest_price_observed_at_ms": 1_777_999_900_000,
        },
    ]
    dex_market = FakeDexMarket()

    result = sync_dex_prices(
        registry=registry,
        identity_evidence=FakeIdentityEvidence(),
        price_observations=price_observations,
        dex_market=dex_market,
        observed_at_ms=1_778_000_060_000,
        stale_after_ms=300_000,
        hot_stale_after_ms=90_000,
        warm_stale_after_ms=300_000,
        limit=1,
        radar_since_ms=1_777_900_000_000,
        hot_since_ms=1_778_000_000_000,
    )

    assert result["price_observations_written"] == 1
    assert result["refresh_candidates_selected"] == 1
    assert result["refresh_candidates_hot"] == 1
    assert result["refresh_candidates_stale"] == 1
    assert [(item.chain_id, item.address) for item in dex_market.price_requests[0]] == [
        ("eip155:56", "0x8f32420f2e3728c49399b00dd0a796602d984444")
    ]


def test_asset_market_sync_worker_uses_dex_refresh_knobs():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    registry.dex_refresh_rows = [
        {
            "asset_id": f"asset:eip155:56:erc20:0x{i:040x}",
            "chain_id": "eip155:56",
            "address": f"0x{i:040x}",
            "symbol": f"T{i}",
            "identity_confidence": "provider_exact",
            "latest_candidate_received_at_ms": 1_778_000_050_000,
            "candidate_event_count": i,
            "latest_price_observed_at_ms": None,
        }
        for i in range(1, 5)
    ]
    session = FakeRepositorySession(registry, price_observations)
    worker = AssetMarketSyncWorker(
        dex_market=FakeDexMarket(),
        repository_session=lambda: session,
        inst_types=(),
        interval_seconds=300,
        dex_stale_after_ms=600_000,
        dex_hot_stale_after_ms=90_000,
        dex_warm_stale_after_ms=300_000,
        dex_refresh_limit=3,
    )

    result = worker.sync_once(now_ms=1_778_000_060_000)

    assert result["refresh_candidates_selected"] == 3
    assert result["price_observations_written"] == 3
    assert registry.radar_refresh_calls[0]["stale_before_ms"] == 1_777_999_970_000


def test_sync_dex_prices_enriches_address_search_metadata():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    address = "0x44b28991b167582f18ba0259e0173176ca125505"
    registry.dex_refresh_rows = [
        {
            "asset_id": f"asset:eip155:1:erc20:{address}",
            "chain_id": "eip155:1",
            "address": address,
            "symbol": None,
            "identity_confidence": "unknown",
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
        }
    ]
    dex_market = FakeDexMarket(
        search_candidates=[
            DexTokenCandidate(
                chain_id="eip155:1",
                address=address,
                symbol="UPEG",
                name="Unipeg",
                price_usd=1055.71,
                market_cap_usd=10_557_123.48,
                liquidity_usd=921_926.63,
                holders=4_885,
                community_recognized=True,
                raw={"tokenSymbol": "uPEG"},
            )
        ]
    )

    result = sync_dex_prices(
        registry=registry,
        identity_evidence=FakeIdentityEvidence(),
        price_observations=price_observations,
        dex_market=dex_market,
        observed_at_ms=1_778_085_100_000,
        stale_after_ms=300_000,
        limit=100,
    )

    assert result["identity_verification_requests"] == 1
    assert result["identity_verification_errors"] == 0
    assert result["affected_lookup_keys"] == [
        f"address:eip155:1:{address}",
        "project_symbol:UPEG",
        "symbol:UPEG",
    ]
    assert registry.chain_assets[-1] == {
        "chain_id": "eip155:1",
        "address": address,
    }
    assert price_observations.observations[0]["market_cap_usd"] == 10_557_123.48
    assert price_observations.observations[0]["liquidity_usd"] == 921_926.63
    assert price_observations.observations[0]["holders"] == 4_885


def test_sync_dex_prices_rechecks_tweet_source_address_metadata():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    address = "0x999b49c0d1612e619a4a4f6280733184da025108"
    registry.dex_refresh_rows = [
        {
            "asset_id": f"asset:eip155:1:erc20:{address}",
            "chain_id": "eip155:1",
            "address": address,
            "symbol": "SATO",
            "identity_confidence": "mention_only",
            "market_cap_usd": 28_000_000.0,
            "liquidity_usd": 1_000_000.0,
            "holders": 500,
        }
    ]
    dex_market = FakeDexMarket(
        search_candidates=[
            DexTokenCandidate(
                chain_id="eip155:1",
                address=address,
                symbol="SLOP",
                name="SLOP",
                price_usd=3.45,
                market_cap_usd=2_864_323.71,
                liquidity_usd=728_561.21,
                holders=1_234,
                community_recognized=False,
                raw={"tokenSymbol": "SLOP"},
            )
        ]
    )

    result = sync_dex_prices(
        registry=registry,
        identity_evidence=FakeIdentityEvidence(),
        price_observations=price_observations,
        dex_market=dex_market,
        observed_at_ms=1_778_085_100_000,
        stale_after_ms=300_000,
        limit=100,
    )

    assert result["identity_verification_requests"] == 1
    assert registry.chain_assets[-1] == {
        "chain_id": "eip155:1",
        "address": address,
    }
    assert result["affected_lookup_keys"] == [
        f"address:eip155:1:{address}",
        "project_symbol:SLOP",
        "symbol:SLOP",
    ]


def test_sync_dex_prices_continues_when_address_search_fails():
    registry = FakeRegistry()
    price_observations = FakePriceObservations()
    registry.dex_refresh_rows = [
        {
            "asset_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
            "symbol": None,
            "identity_confidence": "unknown",
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
        }
    ]
    dex_market = FakeDexMarket(search_error=RuntimeError("rate limited"))

    result = sync_dex_prices(
        registry=registry,
        identity_evidence=FakeIdentityEvidence(),
        price_observations=price_observations,
        dex_market=dex_market,
        observed_at_ms=1_778_085_100_000,
        stale_after_ms=300_000,
        limit=100,
    )

    assert result["identity_verification_requests"] == 1
    assert result["identity_verification_hits"] == 0
    assert result["identity_verification_errors"] == 1
    assert result["price_requests"] == 1
    assert result["affected_lookup_keys"] == ["address:eip155:56:0x8f32420f2e3728c49399b00dd0a796602d984444"]
    assert price_observations.observations[-1]["provider"] == "okx_dex_price"


class FakeCexMarket:
    def __init__(self, *, events=None):
        self.events = events
        self.instrument_requests = []
        self.ticker_requests = []

    def tickers(self, *, inst_type):
        self.ticker_requests.append(inst_type)
        if self.events is not None:
            self.events.append(f"cex_tickers:{inst_type}")
        return [
            CexTicker(
                inst_id="BTC-USDT",
                inst_type=inst_type,
                last_price=69000.0,
                volume_24h=1234567.0,
                open_interest=None,
                raw={"instId": "BTC-USDT"},
            )
        ]


class FakeDexMarket:
    def __init__(self, *, events=None, delay_seconds=0, search_candidates=None, search_error=None):
        self.events = events
        self.delay_seconds = delay_seconds
        self.price_requests = []
        self.search_requests = []
        self.search_candidates = search_candidates or []
        self.search_error = search_error

    def search_tokens(self, *, query, chain_ids):
        if self.search_error is not None:
            raise self.search_error
        self.search_requests.append({"query": query, "chain_ids": tuple(chain_ids)})
        return list(self.search_candidates)

    def token_prices(self, tokens):
        if self.events is not None:
            self.events.append("dex_prices")
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.price_requests.append(tokens)
        return [
            DexTokenPrice(
                chain_id=item.chain_id,
                address=item.address,
                observed_at_ms=1_778_085_000_000,
                price_usd=0.00002237,
                raw={"price": "0.00002237"},
            )
            for item in tokens
        ]


class FakeRegistry:
    def __init__(self, *, events=None):
        self.events = events
        self.cex_tokens = []
        self.pricefeeds = []
        self.chain_assets = []
        self.dex_refresh_rows = []
        self.radar_refresh_calls = []
        self.global_refresh_calls = []
        self.conn = FakeConn()

    def upsert_cex_token(self, *, base_symbol, project_id, source, observed_at_ms, commit=False):
        self.cex_tokens.append({"base_symbol": base_symbol})
        return {"cex_token_id": f"cex_token:{base_symbol}", "base_symbol": base_symbol}

    def upsert_pricefeed(self, **kwargs):
        if kwargs["feed_type"].startswith("cex_"):
            pricefeed_id = f"pricefeed:cex:{kwargs['provider']}:{kwargs['feed_type'][4:]}:{kwargs['native_market_id']}"
        else:
            address = str(kwargs["address"])
            address = address.lower() if address.lower().startswith("0x") else address
            pricefeed_id = f"pricefeed:dex-token:{kwargs['provider']}:{kwargs['chain_id']}:{address}"
        self.pricefeeds.append(
            {
                "feed_type": kwargs["feed_type"],
                "provider": kwargs["provider"],
                "subject_type": kwargs["subject_type"],
                "subject_id": kwargs["subject_id"],
                "native_market_id": kwargs.get("native_market_id"),
                "base_cex_token_id": kwargs.get("base_cex_token_id"),
                "base_symbol": kwargs.get("base_symbol"),
                "quote_symbol": kwargs.get("quote_symbol"),
            }
        )
        return {"pricefeed_id": pricefeed_id, **kwargs}

    def upsert_chain_asset(self, **kwargs):
        self.chain_assets.append(
            {
                "chain_id": kwargs["chain_id"],
                "address": kwargs["address"],
            }
        )
        return {
            "asset_id": f"asset:{kwargs['chain_id']}:erc20:{kwargs['address']}",
            "chain_id": kwargs["chain_id"],
            "address": kwargs["address"],
        }

    def chain_assets_needing_price_refresh(self, *, stale_before_ms, limit):
        self.global_refresh_calls.append({"stale_before_ms": stale_before_ms, "limit": limit})
        return self.dex_refresh_rows[:limit]

    def chain_assets_needing_radar_price_refresh(
        self,
        *,
        stale_before_ms,
        radar_since_ms,
        hot_since_ms,
        limit,
    ):
        self.radar_refresh_calls.append(
            {
                "stale_before_ms": stale_before_ms,
                "radar_since_ms": radar_since_ms,
                "hot_since_ms": hot_since_ms,
                "limit": limit,
            }
        )
        return self.dex_refresh_rows[:limit]


class FakePriceObservations:
    def __init__(self):
        self.observations = []

    def insert_observation(self, **kwargs):
        self.observations.append(
            {
                "provider": kwargs["provider"],
                "pricefeed_id": kwargs["pricefeed_id"],
                "subject_type": kwargs["subject_type"],
                "subject_id": kwargs["subject_id"],
                "price_usd": kwargs.get("price_usd"),
                "price_quote": kwargs.get("price_quote"),
                "quote_symbol": kwargs.get("quote_symbol"),
                "price_basis": kwargs.get("price_basis"),
                "volume_24h_usd": kwargs.get("volume_24h_usd"),
                "open_interest_usd": kwargs.get("open_interest_usd"),
                "market_cap_usd": kwargs.get("market_cap_usd"),
                "liquidity_usd": kwargs.get("liquidity_usd"),
                "holders": kwargs.get("holders"),
            }
        )
        return kwargs


class FakeIdentityEvidence:
    def __init__(self):
        self.evidence = []

    def upsert_identity_evidence(self, **kwargs):
        self.evidence.append(kwargs)
        return kwargs

    def recompute_current_identity(self, asset_id, *, now_ms, commit=False):
        selected = next(
            (item for item in reversed(self.evidence) if item["asset_id"] == asset_id),
            {},
        )
        return {
            "asset_id": asset_id,
            "canonical_symbol": selected.get("symbol"),
            "canonical_name": selected.get("name"),
            "decimals": selected.get("decimals"),
            "identity_confidence": selected.get("confidence", "unknown"),
            "updated_at_ms": now_ms,
        }


class FakeConn:
    def commit(self):
        return None


class FakeRepositorySession:
    def __init__(self, registry, price_observations):
        self.registry = registry
        self.identity_evidence = FakeIdentityEvidence()
        self.price_observations = price_observations
        self.token_intent_lookup = FakeTokenIntentLookup()
        self.token_intents = FakeTokenIntents()
        self.intent_resolutions = object()
        self.token_evidence = object()
        self.conn = FakeConn()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class FakeTokenIntentLookup:
    def recent_intents_for_lookup_keys(self, *_args, **_kwargs):
        return []


class FakeTokenIntents:
    def recent_unresolved(self, *_args, **_kwargs):
        return []
