from parallax.domains.asset_market.chain_identity import (
    canonical_chain_address,
    canonical_chain_id,
    chain_address_key,
)


def test_chain_identity_canonicalizes_evm_and_preserves_solana_case() -> None:
    assert canonical_chain_id("Ethereum") == "eip155:1"
    assert canonical_chain_address("ethereum", "0xAbCd") == "0xabcd"
    assert chain_address_key("SOL", "AbCd") == ("solana", "AbCd")
    assert chain_address_key("solana", "abcd") == ("solana", "abcd")
    assert chain_address_key("SOL", "AbCd") != chain_address_key("solana", "abcd")
