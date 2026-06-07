from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.services.text_normalization import title_fingerprint

NEWS_STORY_IDENTITY_VERSION = "news_story_identity_v1"

_HOUR_MS = 60 * 60 * 1000
_STRONG_BUCKET_MS = 12 * _HOUR_MS
_MEDIUM_BUCKET_MS = 6 * _HOUR_MS
_SOURCE_PREFIX_RE = re.compile(r"^([a-z][a-z0-9&.+/-]*(?:[ -][a-z][a-z0-9&.+/-]*){0,2})[:：]\s+", re.IGNORECASE)
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•·]+|\(?\d+[.)])\s+")
_ARTICLE_KEY_RE = re.compile(r"^(?:opennews[:/_-])?([0-9]{3,})$", re.IGNORECASE)
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


@dataclass(frozen=True, slots=True)
class NewsStoryIdentity:
    story_key: str
    confidence: str
    basis: dict[str, Any]
    version: str


def build_news_story_identity(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    market_scope: Mapping[str, Any],
) -> NewsStoryIdentity:
    market_scope_basis = _market_scope_basis(market_scope)
    provider_article_key = _opennews_article_key(item)
    if provider_article_key:
        return NewsStoryIdentity(
            story_key=f"news-story:opennews-article:{provider_article_key}",
            confidence="strong",
            basis={
                "method": "opennews_article_key",
                "provider_article_key": provider_article_key,
                **market_scope_basis,
            },
            version=NEWS_STORY_IDENTITY_VERSION,
        )

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


def _opennews_article_key(item: Mapping[str, Any]) -> str:
    provider = str(_field(item, "provider_type", "")).casefold()
    raw_keys = _field(item, "provider_article_keys_json", ())
    if provider != "opennews" or isinstance(raw_keys, str) or not isinstance(raw_keys, Sequence):
        return ""

    for raw_key in raw_keys:
        text = str(raw_key).strip()
        match = _ARTICLE_KEY_RE.fullmatch(text)
        if match:
            return match.group(1)
    return ""


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
