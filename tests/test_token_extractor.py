from gmgn_twitter_cli.pipeline.token_extractor import extract_token_entities


def test_extract_token_entities_resolves_valid_evm_ca_and_cashtag():
    text = "$PEPE 0x6982508145454ce325ddbe47a25d4ec3d2311933"

    entities = extract_token_entities(text)

    ca = [entity for entity in entities if entity.entity_type == "ca"][0]
    symbol = [entity for entity in entities if entity.entity_type == "symbol"][0]
    assert ca.chain == "eth"
    assert ca.normalized_value == "0x6982508145454Ce325dDbE47a25d4ec3d2311933"
    assert ca.token_resolution_status == "resolved"
    assert symbol.normalized_value == "PEPE"
    assert symbol.token_resolution_status == "unresolved"


def test_extract_token_entities_resolves_valid_solana_ca():
    entities = extract_token_entities("SOL CA EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    assert entities[0].chain == "solana"
    assert entities[0].normalized_value == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert entities[0].token_resolution_status == "resolved"


def test_extract_token_entities_returns_empty_for_tokenless_text():
    assert extract_token_entities("gm chart looks interesting") == []
