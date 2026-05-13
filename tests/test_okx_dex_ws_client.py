from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from gmgn_twitter_intel.integrations.okx.dex_ws_client import (
    OkxDexWebSocketMarketProvider,
    OkxDexWsClientError,
    _login_prehash,
    _login_signature,
    _okx_timestamp,
    _price_info_update_from_row,
    _rows_from_message,
)


def test_okx_dex_ws_login_uses_expected_signature_prehash():
    timestamp = "1704876947"

    assert _login_prehash(timestamp) == "1704876947GET/users/self/verify"
    expected = base64.b64encode(
        hmac.new(
            b"test-secret",
            b"1704876947GET/users/self/verify",
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    assert _login_signature(secret_key="test-secret", timestamp=timestamp) == expected


def test_okx_dex_ws_timestamp_is_unix_seconds():
    timestamp = _okx_timestamp()

    assert timestamp.isdigit()
    assert len(timestamp) == 10


def test_okx_dex_ws_price_info_normalizes_market_fields():
    update = _price_info_update_from_row(
        {
            "chainIndex": "501",
            "tokenContractAddress": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            "time": "1700086420000",
            "price": "0.111",
            "marketCap": "110900000",
            "liquidity": "4820000",
            "volume24H": "27400000",
            "holders": "57141",
        }
    )

    assert update is not None
    assert update.chain_id == "501"
    assert update.address == "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
    assert update.observed_at_ms == 1_700_086_420_000
    assert update.price_usd == 0.111
    assert update.market_cap_usd == 110_900_000
    assert update.liquidity_usd == 4_820_000
    assert update.volume_24h_usd == 27_400_000
    assert update.holders == 57_141


def test_okx_dex_ws_price_info_merges_subscription_arg_fields():
    rows = _rows_from_message(
        {
            "arg": {
                "channel": "price-info",
                "chainIndex": "501",
                "tokenContractAddress": "8jpRiwbUXLWH4yFQaF2TBDUkWDkfKWtBMX95sibTpump",
            },
            "data": [
                {
                    "time": "1778627069103",
                    "price": "0.00001733",
                    "marketCap": "17336.16",
                    "liquidity": "10416.54",
                    "holders": "224",
                }
            ],
        }
    )

    update = _price_info_update_from_row(rows[0])

    assert update is not None
    assert update.chain_id == "501"
    assert update.address == "8jpRiwbUXLWH4yFQaF2TBDUkWDkfKWtBMX95sibTpump"
    assert update.observed_at_ms == 1_778_627_069_103


def test_okx_dex_ws_unauthenticated_error_is_surfaceable():
    with pytest.raises(OkxDexWsClientError, match="60011"):
        _price_info_update_from_row({"event": "error", "code": "60011", "msg": "Please log in"})


def test_okx_dex_ws_exposes_connection_state_payload():
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test/ws",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    initial = provider.connection_state_payload()
    provider._set_connection_state("connecting")
    changed = provider.connection_state_payload()

    assert initial["state"] == "disconnected"
    assert changed["provider"] == "okx_dex_ws"
    assert changed["state"] == "connecting"
    assert isinstance(changed["last_state_change_at_ms"], int)
