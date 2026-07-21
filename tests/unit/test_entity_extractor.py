from parallax.domains.evidence.services.entity_extractor import TextSurface, extract_entities_from_surfaces
from parallax.domains.evidence.types.entity import normalize_ca


def _extract_primary(text: str):
    return extract_entities_from_surfaces((TextSurface("primary", text),))


def test_extract_entities_returns_deterministic_structured_entities():
    text = (
        "@toly says $PEPE is on Base mainnet https://example.com/path "
        "#memecoin 0x6982508145454ce325ddbe47a25d4ec3d2311933"
    )

    first = _extract_primary(text)
    second = _extract_primary(text)

    assert first == second
    assert {
        (entity.entity_type, entity.normalized_value, entity.chain, entity.token_resolution_status) for entity in first
    } >= {
        ("ca", "0x6982508145454Ce325dDbE47a25d4ec3d2311933", "base", "resolved_ca"),
        ("symbol", "PEPE", None, "unresolved_symbol"),
        ("mention", "toly", None, "non_token_entity"),
        ("hashtag", "memecoin", None, "non_token_entity"),
        ("domain", "example.com", None, "non_token_entity"),
    }


def test_extract_entities_resolves_evm_chain_from_local_hint():
    text = "CA: 0xa4b79ddc047d301e1cfa21e1d4b524d1260e4444 Get more: BSC"

    entities = _extract_primary(text)

    ca = next(entity for entity in entities if entity.entity_type == "ca")
    assert ca.chain == "bsc"
    assert ca.token_resolution_status == "resolved_ca"


def test_extract_entities_resolves_evm_chain_from_explorer_url():
    text = (
        "Holder wallet "
        "https://etherscan.io/address/0x6801bda730124fa7661a960b9261e9bb01ef99af "
        "$SPIKE CA: 0xa949101be849184c77e5ac1405aaf3cdf41da1b2"
    )

    chains = {entity.normalized_value: entity.chain for entity in _extract_primary(text) if entity.entity_type == "ca"}

    assert chains == {
        "0x6801Bda730124FA7661a960b9261E9Bb01EF99af": "eth",
        "0xa949101Be849184c77E5ac1405Aaf3cDf41da1b2": "eth",
    }


def test_extract_entities_leaves_evm_ca_unknown_without_chain_hint():
    entities = _extract_primary("new ca 0xcfecf68e3359de205c3f0cffb00b6d488280ffff")

    ca = next(entity for entity in entities if entity.entity_type == "ca")
    assert ca.chain == "evm_unknown"
    assert ca.token_resolution_status == "unresolved_chain_ca"


def test_plain_words_do_not_become_entities_without_structural_markers():
    entities = _extract_primary("airdropper listed nothing")

    assert entities == []


def test_nan_cashtag_sentinel_is_not_a_token_symbol():
    entities = _extract_primary(
        "Detect PAID DEXScreener: $MTGA DEDUST TON CA: EQC1RZb5BF_eWrR0AYCtpUig5c4CQoupQ_v-ABsRmO5pbgQL MC: $NaN"
    )

    assert {(entity.entity_type, entity.normalized_value, entity.chain) for entity in entities} == {
        ("ca", "EQC1RZb5BF_eWrR0AYCtpUig5c4CQoupQ_v-ABsRmO5pbgQL", "ton"),
        ("symbol", "MTGA", None),
    }


def test_normalize_ca_supports_evm_and_solana():
    assert normalize_ca("0x6982508145454ce325ddbe47a25d4ec3d2311933") == (
        "evm_unknown",
        "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
    )
    assert normalize_ca("So11111111111111111111111111111111111111112") == (
        "solana",
        "So11111111111111111111111111111111111111112",
    )
