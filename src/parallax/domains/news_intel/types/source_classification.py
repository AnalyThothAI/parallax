from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

PROVIDER_TYPES = (
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
SOURCE_ROLES = (
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

ProviderType = Literal[
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
]
SourceRole = Literal[
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
]


def normalize_string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _normalize_parts(value.split(","))
    if isinstance(value, bytes | bytearray):
        try:
            return normalize_string_tuple(bytes(value).decode("utf-8"))
        except UnicodeDecodeError:
            return _normalize_parts((str(value).strip(),))
    if isinstance(value, Mapping):
        raise TypeError("mappings are not valid string tuples")
    if isinstance(value, Iterable):
        return _normalize_parts(value)
    return _normalize_parts((value,))


def _normalize_parts(parts: Iterable[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        item = str(part or "").strip()
        if item:
            normalized.append(item)
    return tuple(normalized)
