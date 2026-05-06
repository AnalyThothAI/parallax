from __future__ import annotations

import httpx

from gmgn_twitter_intel.market.okx_cex_client import OkxCexClient
from gmgn_twitter_intel.market.okx_dex_client import OkxDexClient


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
