from __future__ import annotations

import re
from urllib.parse import urlsplit

URL_IDENTITY_KINDS = ("article", "live_page", "homepage", "aggregator", "unknown")

_ARTICLE_ID_RE = re.compile(r"(?:^|[-_/])(?:[0-9]{6,}|[0-9a-f]{8,})(?:$|[-_/])", re.IGNORECASE)
_DATE_SLUG_RE = re.compile(r"(?:19|20)\d{2}[-_/](?:0?[1-9]|1[0-2])[-_/](?:0?[1-9]|[12]\d|3[01])")
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)
_ROOT_LIKE_SECTIONS = {
    "article",
    "articles",
    "blog",
    "blogs",
    "business",
    "crypto",
    "economy",
    "finance",
    "latest",
    "market",
    "markets",
    "news",
    "press-release",
    "press-releases",
    "research",
    "technology",
    "tech",
    "world",
}


def url_identity_kind(canonical_url: str) -> str:
    """Return article/live_page/homepage/aggregator/unknown for a canonical URL."""

    raw_url = str(canonical_url or "").strip()
    if not raw_url:
        return "unknown"

    split = urlsplit(raw_url)
    if split.scheme.lower() not in {"http", "https"} or not split.netloc:
        return "unknown"

    path = split.path or ""
    if path in {"", "/"}:
        return "homepage"

    segments = [segment for segment in path.strip("/").split("/") if segment]
    if not segments:
        return "homepage"

    lower_segments = [segment.lower() for segment in segments]
    if _is_live_page(lower_segments):
        return "live_page"

    content_segments = _strip_locale_prefix(lower_segments)
    if _is_root_like_aggregator_path(content_segments):
        return "aggregator"

    if len(segments) >= 2 or _has_article_id_or_date_slug(path):
        return "article"

    return "unknown"


def is_article_identity(canonical_url: str, *, kind: str | None = None) -> bool:
    """True only when URL can participate in hard URL dedup by itself."""

    return (kind or url_identity_kind(canonical_url)) == "article"


def _is_live_page(lower_segments: list[str]) -> bool:
    return any(
        segment == "live"
        or segment.startswith("live-")
        or segment in {"liveblog", "live-blog"}
        or "live-updates" in segment
        for segment in lower_segments
    )


def _strip_locale_prefix(lower_segments: list[str]) -> list[str]:
    if lower_segments and _LOCALE_RE.fullmatch(lower_segments[0]):
        return lower_segments[1:]
    return lower_segments


def _is_root_like_aggregator_path(lower_segments: list[str]) -> bool:
    return len(lower_segments) == 1 and lower_segments[0] in _ROOT_LIKE_SECTIONS


def _has_article_id_or_date_slug(path: str) -> bool:
    return bool(_ARTICLE_ID_RE.search(path) or _DATE_SLUG_RE.search(path))
