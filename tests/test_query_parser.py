from gmgn_twitter_intel.retrieval.query_parser import parse_query


def test_parse_query_accepts_chain_prefixed_evm_ca():
    parsed = parse_query("eth:0x6982508145454ce325ddbe47a25d4ec3d2311933")

    assert parsed.kind == "ca"
    assert parsed.chain == "eth"
    assert parsed.ca == "0x6982508145454Ce325dDbE47a25d4ec3d2311933"


def test_parse_query_treats_bare_uppercase_as_text_not_token_symbol():
    parsed = parse_query("PEPE")

    assert parsed.kind == "text"
    assert parsed.text == "PEPE"
    assert parsed.symbol is None


def test_parse_query_requires_cashtag_for_symbol_intent():
    parsed = parse_query("$PEPE")

    assert parsed.kind == "symbol"
    assert parsed.symbol == "PEPE"
