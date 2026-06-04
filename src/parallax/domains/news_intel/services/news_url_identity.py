from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from parallax.domains.news_intel.services.text_normalization import canonicalize_url

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
_SOCIAL_STATUS_HOSTS = {
    "mobile.twitter.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
}
_PREVIEW_SEGMENTS = {"preview", "preview_article", "preview-article"}
_FEED_INDEX_SEGMENTS = {"atom", "feed", "feeds", "rss"}
_FEED_INDEX_FILENAMES = {"atom.xml", "feed.xml", "index.xml", "rss.xml"}
_GENERIC_INDEX_FILENAMES = {"index", "index.html"}


def url_identity_kind(canonical_url: str) -> str:
    """Return article/live_page/homepage/aggregator/unknown for a canonical URL."""

    raw_url = str(canonical_url or "").strip()
    if not raw_url:
        return "unknown"

    try:
        split = urlsplit(raw_url)
    except ValueError:
        return "unknown"
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


@dataclass(frozen=True, slots=True)
class PublicUrlIdentityPolicy:
    normalized_url: str
    identity_key: str
    identity_kind: str
    blocked_reason: str

    @property
    def allowed(self) -> bool:
        return bool(self.identity_key)


def public_url_identity_policy(canonical_url: object) -> PublicUrlIdentityPolicy:
    """Return the single public URL admission policy for hard URL identity."""

    normalized_url = canonicalize_url(canonical_url)
    if not normalized_url:
        return PublicUrlIdentityPolicy("", "", "unknown", "not_public_url")

    split = urlsplit(normalized_url)
    if split.scheme.lower() not in {"http", "https"} or not split.netloc:
        return PublicUrlIdentityPolicy(normalized_url, "", "unknown", "not_public_url")

    social_status_key = _social_status_identity_key(split.hostname or "", split.path or "")
    if social_status_key:
        return PublicUrlIdentityPolicy(normalized_url, social_status_key, "article", "")

    lower_segments = _path_segments(split.path or "")
    if _is_preview_path(lower_segments):
        return PublicUrlIdentityPolicy(normalized_url, "", url_identity_kind(normalized_url), "preview")
    if _is_generic_announcement_path(lower_segments):
        return PublicUrlIdentityPolicy(
            normalized_url,
            "",
            url_identity_kind(normalized_url),
            "generic_announcement",
        )
    if _is_feed_index_path(lower_segments):
        return PublicUrlIdentityPolicy(normalized_url, "", url_identity_kind(normalized_url), "feed_index")

    identity_kind = url_identity_kind(normalized_url)
    if identity_kind in {"homepage", "aggregator", "live_page"}:
        return PublicUrlIdentityPolicy(normalized_url, "", identity_kind, identity_kind)
    return PublicUrlIdentityPolicy(normalized_url, f"canonical-url:{normalized_url}", identity_kind, "")


def hard_public_url_identity_key(canonical_url: object) -> str:
    """Return a trusted hard public URL key, or an empty string for generic URLs."""

    return public_url_identity_policy(canonical_url).identity_key


def qualified_content_identity_url_allowed(canonical_url: object, *, kind: str | None = None) -> bool:
    """True when URL shape is safe for global qualified-content identity."""

    raw_url = str(canonical_url or "").strip()
    if not raw_url:
        return True

    policy = public_url_identity_policy(raw_url)
    if kind and policy.identity_kind != kind:
        return False
    return policy.allowed


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


def _path_segments(path: str) -> list[str]:
    return [segment.lower() for segment in str(path or "").strip("/").split("/") if segment]


def _is_preview_path(lower_segments: list[str]) -> bool:
    return any(segment in _PREVIEW_SEGMENTS or segment.startswith("preview") for segment in lower_segments)


def _is_feed_index_path(lower_segments: list[str]) -> bool:
    content_segments = _strip_locale_prefix(lower_segments)
    if not content_segments:
        return False
    last_segment = content_segments[-1]
    if last_segment in _FEED_INDEX_FILENAMES:
        return True
    if len(content_segments) <= 2 and last_segment in _FEED_INDEX_SEGMENTS:
        return True
    return len(content_segments) <= 2 and last_segment in _GENERIC_INDEX_FILENAMES


def _is_generic_announcement_path(lower_segments: list[str]) -> bool:
    content_segments = _strip_locale_prefix(lower_segments)
    return content_segments in (["support", "announcement"], ["support", "announcements"])


def _social_status_identity_key(hostname: str, path: str) -> str:
    normalized_host = str(hostname or "").lower()
    if normalized_host not in _SOCIAL_STATUS_HOSTS:
        return ""

    segments = _path_segments(path)
    for index, segment in enumerate(segments[:-1]):
        if segment == "status" and segments[index + 1].isdigit():
            return f"social-status:twitter:{segments[index + 1]}"
    return ""
