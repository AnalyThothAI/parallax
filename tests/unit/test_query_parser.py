from parallax.domains.token_intel.services.query_parser import parse_search_query


def test_parse_search_query_treats_bare_symbol_as_symbol_probe():
    parsed = parse_search_query("btc", scope="all")

    assert parsed.kind == "symbol"
    assert parsed.symbol == "BTC"
    assert parsed.lexical_query == "btc"


def test_parse_search_query_treats_cashtag_as_same_symbol_probe():
    parsed = parse_search_query("$btc", scope="all")

    assert parsed.kind == "symbol"
    assert parsed.symbol == "BTC"


def test_parse_search_query_accepts_chain_prefixed_evm_ca():
    parsed = parse_search_query("eth:0x6982508145454ce325ddbe47a25d4ec3d2311933", scope="all")

    assert parsed.kind == "ca"
    assert parsed.chain == "eth"
    assert parsed.ca == "0x6982508145454Ce325dDbE47a25d4ec3d2311933"


def test_parse_search_query_preserves_phrase_text():
    parsed = parse_search_query('"bitcoin price"', scope="all")

    assert parsed.kind == "text"
    assert parsed.lexical_query == '"bitcoin price"'


def test_parse_search_query_preserves_or_text():
    parsed = parse_search_query("btc OR eth", scope="all")

    assert parsed.kind == "text"
    assert parsed.lexical_query == "btc OR eth"


def test_parse_search_query_does_not_treat_one_character_symbol_as_target_probe():
    parsed = parse_search_query("x", scope="all")

    assert parsed.kind == "text"
    assert parsed.symbol is None
