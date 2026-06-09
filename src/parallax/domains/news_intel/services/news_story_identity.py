from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from parallax.domains.news_intel.types.news_story_identity import NEWS_STORY_IDENTITY_VERSION, NewsStoryIdentity
from parallax.domains.news_intel.types.text_normalization import title_fingerprint

_HOUR_MS = 60 * 60 * 1000
_STRONG_BUCKET_MS = 12 * _HOUR_MS
_MEDIUM_BUCKET_MS = 6 * _HOUR_MS
_LISTING_BUCKET_MS = 24 * _HOUR_MS
_SOURCE_PREFIX_RE = re.compile(r"^([a-z][a-z0-9&.+/-]*(?:[ -][a-z][a-z0-9&.+/-]*){0,2})[:：]\s+", re.IGNORECASE)
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•·]+|\(?\d+[.)])\s+")
_PAREN_TICKER_RE = re.compile(r"[\(（]([A-Z][A-Z0-9]{1,11})[\)）]")
_SOURCE_PREFIXES = frozenset(
    {
        "afp",
        "bloomberg",
        "coindesk",
        "coin desk",
        "financefeeds",
        "finance feeds",
        "forbes",
        "new",
        "reuters",
        "tass",
        "wsj",
        "zerohedge",
    }
)
_WEAK_STOPWORDS = frozenset(
    {
        "a",
        "after",
        "amid",
        "an",
        "and",
        "around",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "latest",
        "market",
        "markets",
        "move",
        "news",
        "of",
        "on",
        "said",
        "says",
        "see",
        "the",
        "to",
        "update",
        "weigh",
        "weighs",
        "with",
    }
)
_STRONG_SUBJECT_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("jpmorgan-citi-tokenized-deposit", frozenset({"jpmorgan", "citi", "tokenized", "deposit"})),
    ("zcash-orchard", frozenset({"zcash", "orchard"})),
    ("ukraine-russia-sanctions", frozenset({"ukraine", "russia", "sanctions"})),
)
_SPACEX_VALUATION_TOKENS = frozenset({"sale", "share", "shares", "tender", "valuation", "valuing"})
_TRUMP_IRAN_TALKS_TOKENS = frozenset({"negotiation", "negotiations", "talk", "talks"})
_EXCHANGE_LISTING_ACTION_TOKENS = frozenset(
    {
        "add",
        "added",
        "addition",
        "adds",
        "list",
        "listed",
        "listing",
        "market",
        "support",
        "trade",
        "trading",
    }
)
_EXCHANGE_LISTING_ACTION_TEXT_MARKERS = (
    "交易",
    "上线",
    "上新",
    "市场",
    "支撑",
    "마켓",
    "상장",
    "추가",
)
_EXCHANGE_VENUE_TOKENS = frozenset(
    {
        "binance",
        "bithumb",
        "bybit",
        "coinbase",
        "gate",
        "kraken",
        "kucoin",
        "mexc",
        "okx",
        "upbit",
    }
)
_EXCHANGE_HOST_VENUES: tuple[tuple[str, str], ...] = (
    ("upbit.com", "upbit"),
    ("bithumb.com", "bithumb"),
    ("binance.com", "binance"),
    ("coinbase.com", "coinbase"),
    ("okx.com", "okx"),
    ("bybit.com", "bybit"),
    ("kraken.com", "kraken"),
    ("kucoin.com", "kucoin"),
    ("mexc.com", "mexc"),
    ("gate.io", "gate"),
)
_QUOTE_ASSET_TOKENS = frozenset(
    {
        "btc",
        "eth",
        "eur",
        "krw",
        "try",
        "usd",
        "usdc",
        "usdt",
    }
)
_QUOTE_TEXT_MARKERS: dict[str, tuple[str, ...]] = {
    "krw": ("원화", "韩元", "韓元"),
}


def build_news_story_identity(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    market_scope: Mapping[str, Any],
) -> NewsStoryIdentity:
    market_scope_basis = _market_scope_basis(market_scope)

    title = _field(item, "title", "") or _field(item, "headline", "")
    subject_text = " ".join(
        part
        for part in (
            title,
            _field(item, "summary", ""),
            _field(item, "body_text", ""),
            _joined_mention_text(token_mentions),
            _joined_fact_text(fact_candidates),
        )
        if part
    )
    normalized_title = _normalized_material_title(title)
    tokens = _material_tokens(subject_text or normalized_title)
    published_at_ms = _published_at_ms(item)

    exchange_listing_subject = _exchange_listing_subject(
        item=item,
        title=title,
        subject_text=subject_text,
        token_mentions=token_mentions,
        tokens=tokens,
    )
    if exchange_listing_subject:
        bucket = _shifted_time_bucket(published_at_ms, _LISTING_BUCKET_MS)
        return NewsStoryIdentity(
            story_key=f"news-story:event:{exchange_listing_subject}:t{bucket}",
            confidence="strong",
            basis={
                "method": "exchange_listing_event_key",
                "subject": exchange_listing_subject,
                "time_bucket_ms": _LISTING_BUCKET_MS,
                "bucket_offset_ms": _LISTING_BUCKET_MS // 2,
                "bucket": bucket,
                "normalized_title": normalized_title,
                **market_scope_basis,
            },
            version=NEWS_STORY_IDENTITY_VERSION,
        )

    strong_subject = _strong_subject(tokens)
    if strong_subject:
        bucket = _shifted_time_bucket(published_at_ms, _STRONG_BUCKET_MS)
        return NewsStoryIdentity(
            story_key=f"news-story:subject:{strong_subject}:t{bucket}",
            confidence="strong",
            basis={
                "method": "strong_subject_shifted_time_bucket",
                "subject": strong_subject,
                "time_bucket_ms": _STRONG_BUCKET_MS,
                "bucket_offset_ms": _STRONG_BUCKET_MS // 2,
                "bucket": bucket,
                "normalized_title": normalized_title,
                **market_scope_basis,
            },
            version=NEWS_STORY_IDENTITY_VERSION,
        )

    material_tokens = _material_tokens(normalized_title)
    if len(material_tokens) >= 5:
        fingerprint = "-".join(material_tokens[:8])
        bucket = _shifted_time_bucket(published_at_ms, _MEDIUM_BUCKET_MS)
        return NewsStoryIdentity(
            story_key=f"news-story:title:{fingerprint}:t{bucket}",
            confidence="medium",
            basis={
                "method": "material_title_shifted_time_bucket",
                "fingerprint": fingerprint,
                "time_bucket_ms": _MEDIUM_BUCKET_MS,
                "bucket_offset_ms": _MEDIUM_BUCKET_MS // 2,
                "bucket": bucket,
                "normalized_title": normalized_title,
                **market_scope_basis,
            },
            version=NEWS_STORY_IDENTITY_VERSION,
        )

    item_key = _item_level_key(item, normalized_title)
    return NewsStoryIdentity(
        story_key=f"news-story:item:{item_key}",
        confidence="weak",
        basis={
            "method": "weak_item_level",
            "normalized_title": normalized_title,
            **market_scope_basis,
        },
        version=NEWS_STORY_IDENTITY_VERSION,
    )


def _normalized_material_title(title: object) -> str:
    text = str(title or "").strip()
    for _ in range(3):
        stripped = _BULLET_PREFIX_RE.sub("", text).strip()
        match = _SOURCE_PREFIX_RE.match(stripped)
        if match and match.group(1).strip().casefold() in _SOURCE_PREFIXES:
            stripped = stripped[match.end() :].strip()
        if stripped == text:
            break
        text = stripped
    return title_fingerprint(text)


def _material_tokens(text: object) -> list[str]:
    fingerprint = title_fingerprint(_normalized_material_title(text))
    return [_canonical_subject_token(token) for token in fingerprint.split() if token and token not in _WEAK_STOPWORDS]


def _strong_subject(tokens: Sequence[str]) -> str:
    token_set = set(tokens)
    if "spacex" in token_set and token_set & _SPACEX_VALUATION_TOKENS:
        return "spacex-valuation"
    if {"trump", "iran"} <= token_set and token_set & _TRUMP_IRAN_TALKS_TOKENS:
        return "trump-iran-nuclear-talks"
    for subject, required_tokens in _STRONG_SUBJECT_RULES:
        if required_tokens <= token_set:
            return subject
    return ""


def _exchange_listing_subject(
    *,
    item: Mapping[str, Any],
    title: object,
    subject_text: str,
    token_mentions: Sequence[Mapping[str, Any]],
    tokens: Sequence[str],
) -> str:
    token_set = set(tokens)
    venue = _exchange_venue(item=item, token_set=token_set)
    if not venue:
        return ""
    if not _has_exchange_listing_action(subject_text=subject_text, token_set=token_set):
        return ""
    asset = _listing_asset(title=title, subject_text=subject_text, token_mentions=token_mentions)
    if not asset:
        return ""
    quote_assets = _quote_assets(subject_text=subject_text, token_set=token_set, asset=asset)
    quote_key = "-".join(quote_assets) if quote_assets else "spot"
    return f"exchange-listing:{venue}:{asset}:{quote_key}"


def _has_exchange_listing_action(*, subject_text: str, token_set: set[str]) -> bool:
    if token_set & _EXCHANGE_LISTING_ACTION_TOKENS:
        return True
    return any(marker in subject_text for marker in _EXCHANGE_LISTING_ACTION_TEXT_MARKERS)


def _exchange_venue(*, item: Mapping[str, Any], token_set: set[str]) -> str:
    for venue in sorted(_EXCHANGE_VENUE_TOKENS):
        if venue in token_set:
            return venue
    for field in ("provider_canonical_url", "provider_observation_url", "source_url"):
        venue = _exchange_venue_from_url(_field(item, field, ""))
        if venue:
            return venue
    return ""


def _exchange_venue_from_url(value: object) -> str:
    try:
        host = (urlparse(str(value or "")).hostname or "").casefold()
    except ValueError:
        return ""
    if not host:
        return ""
    for suffix, venue in _EXCHANGE_HOST_VENUES:
        if host == suffix or host.endswith(f".{suffix}"):
            return venue
    return ""


def _listing_asset(
    *,
    title: object,
    subject_text: str,
    token_mentions: Sequence[Mapping[str, Any]],
) -> str:
    for match in _PAREN_TICKER_RE.finditer(str(title or "")):
        ticker = match.group(1).casefold()
        if ticker and ticker not in _QUOTE_ASSET_TOKENS:
            return ticker
    for match in _PAREN_TICKER_RE.finditer(subject_text):
        ticker = match.group(1).casefold()
        if ticker and ticker not in _QUOTE_ASSET_TOKENS:
            return ticker
    for mention in token_mentions:
        for field in ("display_symbol", "observed_symbol"):
            symbol = str(_field(mention, field, "") or "").strip().casefold()
            if symbol and symbol not in _QUOTE_ASSET_TOKENS:
                return symbol
    return ""


def _quote_assets(*, subject_text: str, token_set: set[str], asset: str) -> list[str]:
    upper_text = subject_text.upper()
    quotes = {
        quote
        for quote in _QUOTE_ASSET_TOKENS
        if quote != asset
        and (
            quote in token_set
            or _contains_upper_token(upper_text, quote.upper())
            or _contains_quote_text_marker(subject_text, quote)
        )
    }
    return sorted(quotes)


def _contains_quote_text_marker(subject_text: str, quote: str) -> bool:
    return any(marker in subject_text for marker in _QUOTE_TEXT_MARKERS.get(quote, ()))


def _contains_upper_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", text))


def _canonical_subject_token(token: str) -> str:
    if token == "jpm":
        return "jpmorgan"
    if token == "deposits":
        return "deposit"
    return token


def _shifted_time_bucket(published_at_ms: int, bucket_ms: int) -> int:
    if published_at_ms <= 0:
        return 0
    return (published_at_ms + (bucket_ms // 2)) // bucket_ms


def _published_at_ms(item: Mapping[str, Any]) -> int:
    value = _field(item, "published_at_ms", 0) or _field(item, "published_ms", 0)
    if not value:
        value = _field(item, "created_at_ms", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _item_level_key(item: Mapping[str, Any], normalized_title: str) -> str:
    item_id = str(_field(item, "news_item_id", "") or _field(item, "id", "")).strip()
    if item_id:
        return _slug(item_id)
    digest = hashlib.sha256(normalized_title.encode("utf-8")).hexdigest()[:16]
    return f"h{digest}"


def _joined_mention_text(token_mentions: Sequence[Mapping[str, Any]]) -> str:
    values: list[str] = []
    for mention in token_mentions:
        for field in ("display_symbol", "observed_symbol", "display_name"):
            value = _field(mention, field, "")
            if value:
                values.append(str(value))
    return " ".join(values)


def _joined_fact_text(fact_candidates: Sequence[Mapping[str, Any]]) -> str:
    values: list[str] = []
    for candidate in fact_candidates:
        for field in ("event_type", "claim", "evidence_quote"):
            value = _field(candidate, field, "")
            if value:
                values.append(str(value))
    return " ".join(values)


def _field(obj: Mapping[str, Any] | None, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return obj.get(name, default)


def _market_scope_basis(market_scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "market_scope": _market_scope_list(_field(market_scope, "scope", ())),
        "market_scope_primary": str(_field(market_scope, "primary", "") or "").strip(),
    }


def _market_scope_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(scope).strip() for scope in value if str(scope).strip()]
    return []


def _slug(value: str) -> str:
    text = title_fingerprint(value)
    return "-".join(text.split()) or "unknown"
