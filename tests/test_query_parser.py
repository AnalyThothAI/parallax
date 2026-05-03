from gmgn_twitter_intel.retrieval.query_parser import parse_query


def test_parse_query_accepts_chain_prefixed_evm_ca():
    parsed = parse_query("eth:0x6982508145454ce325ddbe47a25d4ec3d2311933")

    assert parsed.kind == "ca"
    assert parsed.chain == "eth"
    assert parsed.ca == "0x6982508145454Ce325dDbE47a25d4ec3d2311933"

