from __future__ import annotations

import httpx

from gmgn_twitter_intel.integrations.okx.cex_client import OkxCexClient
from gmgn_twitter_intel.integrations.okx.dex_client import OkxDexClient


def test_okx_cex_client_normalizes_public_instruments():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/v5/public/instruments"
        assert request.url.params["instType"] == "SPOT"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT",
                        "instType": "SPOT",
                        "baseCcy": "BTC",
                        "quoteCcy": "USDT",
                        "state": "live",
                    }
                ],
            },
        )

    client = OkxCexClient(base_url="https://www.okx.com", transport=httpx.MockTransport(handler))
    try:
        instruments = client.instruments(inst_type="spot")
    finally:
        client.close()

    assert len(requests) == 1
    assert instruments[0].inst_id == "BTC-USDT"
    assert instruments[0].inst_type == "SPOT"
    assert instruments[0].base_symbol == "BTC"
    assert instruments[0].quote_symbol == "USDT"
    assert instruments[0].state == "live"


def test_okx_cex_client_derives_swap_base_quote_from_inst_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v5/public/instruments"
        assert request.url.params["instType"] == "SWAP"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "instType": "SWAP",
                        "ctValCcy": "BTC",
                        "settleCcy": "USDT",
                        "state": "live",
                    }
                ],
            },
        )

    client = OkxCexClient(base_url="https://www.okx.com", transport=httpx.MockTransport(handler))
    try:
        instruments = client.instruments(inst_type="swap")
    finally:
        client.close()

    assert instruments[0].base_symbol == "BTC"
    assert instruments[0].quote_symbol == "USDT"
    assert instruments[0].inst_type == "SWAP"


def test_okx_dex_client_normalizes_token_search_candidates():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/v6/dex/market/token/search"
        assert request.url.params["search"] == "MIRROR"
        assert request.url.params["chains"] == "501,1"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {
                        "chainIndex": "501",
                        "chain": "solana",
                        "tokenContractAddress": "Mirror111111111111111111111111111111111111",
                        "tokenSymbol": "MIRROR",
                        "tokenName": "Mirror",
                        "marketCap": "123456",
                        "liquidity": "45678",
                        "holders": "321",
                        "tagList": {"communityRecognized": True},
                        "price": "0.12",
                    }
                ],
            },
        )

    client = OkxDexClient(base_url="https://web3.okx.com", transport=httpx.MockTransport(handler))
    try:
        candidates = client.search_tokens(query="mirror", chain_indexes=["501", "1"])
    finally:
        client.close()

    assert len(requests) == 1
    assert candidates[0].chain_index == "501"
    assert candidates[0].chain == "solana"
    assert candidates[0].address == "Mirror111111111111111111111111111111111111"
    assert candidates[0].symbol == "MIRROR"
    assert candidates[0].market_cap_usd == 123456.0
    assert candidates[0].liquidity_usd == 45678.0
    assert candidates[0].holders == 321
    assert candidates[0].community_recognized is True


def test_okx_dex_client_preserves_contract_search_as_lowercase_address():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v6/dex/market/token/search"
        assert request.url.params["search"] == "0x8f32420f2e3728c49399b00dd0a796602d984444"
        return httpx.Response(200, json={"code": "0", "data": []})

    client = OkxDexClient(base_url="https://web3.okx.com", transport=httpx.MockTransport(handler))
    try:
        assert client.search_tokens(query="0X8F32420F2E3728C49399B00DD0A796602D984444", chain_indexes=["56"]) == []
    finally:
        client.close()


def test_okx_dex_client_fetches_batch_prices_with_lowercase_evm_addresses():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/v6/dex/market/price"
        assert request.headers["content-type"] == "application/json"
        assert request.read().decode("utf-8") == (
            '[{"chainIndex":"56","tokenContractAddress":"0x8f32420f2e3728c49399b00dd0a796602d984444"}]'
        )
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {
                        "chainIndex": "56",
                        "tokenContractAddress": "0x8f32420f2e3728c49399b00dd0a796602d984444",
                        "time": "1778085000000",
                        "price": "0.00002237",
                    }
                ],
            },
        )

    client = OkxDexClient(base_url="https://web3.okx.com", transport=httpx.MockTransport(handler))
    try:
        prices = client.token_prices(
            [
                {
                    "chainIndex": "56",
                    "tokenContractAddress": "0x8F32420F2E3728C49399b00DD0A796602d984444",
                }
            ]
        )
    finally:
        client.close()

    assert len(requests) == 1
    assert prices[0].chain_index == "56"
    assert prices[0].address == "0x8f32420f2e3728c49399b00dd0a796602d984444"
    assert prices[0].price_usd == 0.00002237
    assert prices[0].observed_at_ms == 1_778_085_000_000


def test_okx_cex_client_fetches_candles_from_market_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v5/market/candles"
        assert request.url.params["instId"] == "BONK-USDT"
        assert request.url.params["bar"] == "1H"
        assert request.url.params["limit"] == "24"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    [
                        "1778083200000",
                        "0.0000270",
                        "0.0000285",
                        "0.0000268",
                        "0.0000281",
                        "1000",
                        "0.0281",
                        "0.0281",
                        "1",
                    ]
                ],
            },
        )

    client = OkxCexClient(base_url="https://www.okx.com", transport=httpx.MockTransport(handler))
    try:
        candles = client.candles(inst_id="bonk-usdt", bar="1H", limit=24)
    finally:
        client.close()

    assert candles[0].time_ms == 1_778_083_200_000
    assert candles[0].open == 0.000027
    assert candles[0].high == 0.0000285
    assert candles[0].low == 0.0000268
    assert candles[0].close == 0.0000281
    assert candles[0].volume == 1000.0
    assert candles[0].volume_quote == 0.0281
    assert candles[0].confirmed is True


def test_okx_dex_client_fetches_token_candles_with_lowercase_evm_address():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v6/dex/market/candles"
        assert request.url.params["chainIndex"] == "56"
        assert request.url.params["tokenContractAddress"] == "0x8f32420f2e3728c49399b00dd0a796602d984444"
        assert request.url.params["bar"] == "5m"
        assert request.url.params["limit"] == "12"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    [
                        "1778085000000",
                        "0.12",
                        "0.13",
                        "0.11",
                        "0.125",
                        "5000",
                        "625",
                        "0",
                    ]
                ],
            },
        )

    client = OkxDexClient(base_url="https://web3.okx.com", transport=httpx.MockTransport(handler))
    try:
        candles = client.token_candles(
            chain_index="56",
            token_contract_address="0x8F32420F2E3728C49399b00DD0A796602d984444",
            bar="5m",
            limit=12,
        )
    finally:
        client.close()

    assert candles[0].time_ms == 1_778_085_000_000
    assert candles[0].open == 0.12
    assert candles[0].high == 0.13
    assert candles[0].low == 0.11
    assert candles[0].close == 0.125
    assert candles[0].volume == 5000.0
    assert candles[0].volume_usd == 625.0
    assert candles[0].confirmed is False


def test_okx_dex_client_signs_web3_requests_when_credentials_are_configured():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["OK-ACCESS-KEY"] == "api-key"
        assert request.headers["OK-ACCESS-PASSPHRASE"] == "passphrase"
        assert request.headers["OK-ACCESS-TIMESTAMP"]
        assert request.headers["OK-ACCESS-SIGN"]
        return httpx.Response(200, json={"code": "0", "data": []})

    client = OkxDexClient(
        base_url="https://web3.okx.com",
        api_key="api-key",
        secret_key="secret-key",
        passphrase="passphrase",
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.search_tokens(query="mirror", chain_indexes=["501"]) == []
    finally:
        client.close()


def test_okx_clients_ignore_malformed_rows_without_losing_good_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {"instId": "", "instType": "SPOT"},
                    {"instId": "TAO-USDT", "instType": "SPOT", "baseCcy": "TAO", "quoteCcy": "USDT"},
                ],
            },
        )

    client = OkxCexClient(base_url="https://www.okx.com", transport=httpx.MockTransport(handler))
    try:
        instruments = client.instruments(inst_type="SPOT")
    finally:
        client.close()

    assert [instrument.inst_id for instrument in instruments] == ["TAO-USDT"]


def test_okx_cex_tickers_fall_back_to_requested_inst_type_when_response_omits_it():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v5/market/tickers"
        assert request.url.params["instType"] == "SPOT"
        return httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT",
                        "last": "69000",
                        "volCcy24h": "1234567",
                    }
                ],
            },
        )

    client = OkxCexClient(base_url="https://www.okx.com", transport=httpx.MockTransport(handler))
    try:
        tickers = client.tickers(inst_type="spot")
    finally:
        client.close()

    assert tickers[0].inst_type == "SPOT"
    assert tickers[0].inst_id == "BTC-USDT"
    assert tickers[0].last_price == 69000.0
