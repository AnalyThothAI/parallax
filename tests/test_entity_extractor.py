from gmgn_twitter_intel.pipeline.entity_extractor import extract_entities, normalize_ca


def test_extract_entities_returns_deterministic_structured_entities():
    text = (
        "@toly says $PEPE is on Base mainnet https://example.com/path "
        "#memecoin 0x6982508145454ce325ddbe47a25d4ec3d2311933"
    )

    first = extract_entities(text, watch_keywords=("mainnet", "airdrop"))
    second = extract_entities(text, watch_keywords=("mainnet", "airdrop"))

    assert first == second
    assert {
        (entity.entity_type, entity.normalized_value, entity.chain, entity.token_resolution_status)
        for entity in first
    } >= {
        ("ca", "0x6982508145454Ce325dDbE47a25d4ec3d2311933", "eth", "resolved_ca"),
        ("symbol", "PEPE", None, "unresolved_symbol"),
        ("mention", "toly", None, "non_token_entity"),
        ("hashtag", "memecoin", None, "non_token_entity"),
        ("domain", "example.com", None, "non_token_entity"),
        ("keyword", "mainnet", None, "non_token_entity"),
    }


def test_keyword_matching_does_not_match_word_fragments():
    entities = extract_entities("airdropper listed nothing", watch_keywords=("airdrop", "list"))

    assert ("keyword", "airdrop") not in {(entity.entity_type, entity.normalized_value) for entity in entities}
    assert ("keyword", "list") not in {(entity.entity_type, entity.normalized_value) for entity in entities}


def test_normalize_ca_supports_evm_and_solana():
    assert normalize_ca("0x6982508145454ce325ddbe47a25d4ec3d2311933") == (
        "eth",
        "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
    )
    assert normalize_ca("So11111111111111111111111111111111111111112") == (
        "solana",
        "So11111111111111111111111111111111111111112",
    )
