from typing import get_args

import pytest

from parallax.domains.news_intel.types.source_classification import (
    PROVIDER_TYPES,
    SOURCE_ROLES,
    ProviderType,
    SourceRole,
    normalize_string_tuple,
)


def test_source_classification_literals_match_supported_taxonomy() -> None:
    assert PROVIDER_TYPES == (
        "rss",
        "atom",
        "json_feed",
        "cryptopanic",
        "opennews",
        "openbb",
        "telegram_public",
        "twitter_profile",
        "twitter_thread_context",
        "reddit",
        "hackernews",
        "github",
        "ossinsight",
        "manual_api",
    )
    assert SOURCE_ROLES == (
        "official_exchange",
        "official_regulator",
        "official_protocol",
        "official_issuer",
        "specialist_media",
        "aggregator",
        "social",
        "community",
        "developer_signal",
        "observed_source",
    )
    assert get_args(ProviderType) == PROVIDER_TYPES
    assert get_args(SourceRole) == SOURCE_ROLES


def test_normalize_string_tuple_accepts_none_strings_and_iterables() -> None:
    assert normalize_string_tuple(None) == ()
    assert normalize_string_tuple(" btc, eth ,, sol ") == ("btc", "eth", "sol")
    assert normalize_string_tuple([" btc ", "eth", "", None, 123]) == ("btc", "eth", "123")


def test_normalize_string_tuple_handles_bytes_as_comma_separated_text() -> None:
    assert normalize_string_tuple(b"btc, eth") == ("btc", "eth")
    assert normalize_string_tuple(bytearray("sol, base", encoding="utf-8")) == ("sol", "base")


def test_normalize_string_tuple_falls_back_for_invalid_bytes() -> None:
    assert normalize_string_tuple(b"\xff") == ("b'\\xff'",)


def test_normalize_string_tuple_rejects_mappings() -> None:
    with pytest.raises(TypeError, match="mappings are not valid string tuples"):
        normalize_string_tuple({"btc": True})


def test_normalize_string_tuple_accepts_scalar_values() -> None:
    assert normalize_string_tuple(123) == ("123",)
