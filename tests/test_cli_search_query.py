from __future__ import annotations

import argparse

from gmgn_twitter_intel.cli import _search_query


def test_search_query_preserves_chain_hint_for_ca_option():
    args = argparse.Namespace(
        ca="0X8F32420F2E3728C49399B00DD0A796602D984444",
        chain="bsc",
        symbol="",
        handle="",
        query="",
    )

    assert _search_query(args) == "bsc:0X8F32420F2E3728C49399B00DD0A796602D984444"
