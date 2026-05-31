from __future__ import annotations

import httpx

from parallax.integrations.okx.dex_client import OkxDexClient


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
