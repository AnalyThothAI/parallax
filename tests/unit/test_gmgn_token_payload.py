from parallax.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from parallax.integrations.gmgn.direct_ws import DirectGmgnWebSocketClient


def test_direct_gmgn_ws_exposes_connection_state_payload():
    client = DirectGmgnWebSocketClient(
        app_version="1.0.0",
        channels=["twitter_monitor_basic"],
        chains=["solana"],
        on_frame=lambda frame: None,
    )

    initial = client.connection_state_payload()
    client._set_connection_state("subscribed")
    changed = client.connection_state_payload()

    assert initial["state"] == "disconnected"
    assert changed["provider"] == "gmgn_direct_ws"
    assert changed["state"] == "subscribed"
    assert isinstance(changed["last_state_change_at_ms"], int)


def test_parse_gmgn_token_payload_normalizes_identity_snapshot():
    payload = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": "0xf3525965a4ad3ca0ac13f4d2f237113691194444",
                "c": "bsc",
                "i": "https://gmgn.ai/external-res/token.webp",
                "mc": "4304699.6",
                "p": "0.0043046996",
                "p1": "0.00065198877",
                "s": "熊猫头",
            },
        }
    )

    assert payload is not None
    assert payload.address == "0xf3525965a4aD3ca0AC13f4D2F237113691194444"
    assert payload.chain == "bsc"
    assert payload.symbol == "熊猫头"
    assert payload.icon_url == "https://gmgn.ai/external-res/token.webp"
    assert payload.trigger_type == "ca"
    assert payload.raw == {
        "a": "0xf3525965a4aD3ca0AC13f4D2F237113691194444",
        "c": "bsc",
        "s": "熊猫头",
        "i": "https://gmgn.ai/external-res/token.webp",
        "tt": "ca",
    }


def test_parse_gmgn_token_payload_rejects_symbol_only_without_address():
    payload = parse_gmgn_token_payload({"tt": "symbol", "t": {"c": "eth", "s": "DOG", "p": "1"}})

    assert payload is None


def test_parse_gmgn_token_payload_keeps_ca_when_symbol_is_address_like():
    address = "3iqrRNGG111111111111111111111111111111wNpump"

    payload = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": "sol",
                "s": address,
                "mc": "1000",
                "p": "0.01",
            },
        }
    )

    assert payload is not None
    assert payload.address == address
    assert payload.chain == "solana"
    assert payload.symbol is None
    assert payload.raw == {"a": address, "c": "solana", "tt": "ca"}


def test_parse_gmgn_token_payload_keeps_ca_without_symbol():
    payload = parse_gmgn_token_payload(
        {"tt": "ca", "t": {"a": "So11111111111111111111111111111111111111112", "c": "sol"}}
    )

    assert payload is not None
    assert payload.symbol is None
