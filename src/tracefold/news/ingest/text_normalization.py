from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_URL_INVALID_CHAR_RE = re.compile(r"[\s\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")
_ALNUM_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_TAIL_BOILERPLATE_RE = re.compile(
    r"\s*(?:read\s+more|subscribe(?:\s+now)?|sign\s+up|continue\s+reading|"
    r"the\s+post\s+.+?\s+appeared\s+first)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
_TRACKING_QUERY_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
    }
)
_GENERIC_TITLE_FINGERPRINTS = frozenset(
    {
        "breaking",
        "breaking news",
        "feed",
        "home",
        "homepage",
        "latest",
        "latest news",
        "live",
        "live updates",
        "market",
        "market news",
        "market update",
        "markets",
        "news",
        "news feed",
        "rss feed",
        "updates",
    }
)
_QUALIFIED_CONTENT_MIN_CHARS = 160
_QUALIFIED_CONTENT_MIN_UNIQUE_TOKENS = 12


def clean_news_text(value: object, max_chars: int = 4000) -> str:
    text = html.unescape(str(value or ""))
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _TAIL_BOILERPLATE_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if max_chars <= 0:
        return ""
    return text[: int(max_chars)].strip()


def canonicalize_url(url: object) -> str:
    text = str(url or "")
    raw = text.strip()
    if not raw:
        return ""
    if _URL_INVALID_CHAR_RE.search(raw):
        return ""
    try:
        split = urlsplit(raw)
        scheme = split.scheme.lower()
        hostname = (split.hostname or "").lower()
        if scheme not in {"http", "https"} or not hostname:
            return ""
        netloc = hostname
        port = split.port
        if port is not None:
            netloc = f"{netloc}:{port}"
        if split.username:
            userinfo = split.username
            if split.password:
                userinfo = f"{userinfo}:{split.password}"
            netloc = f"{userinfo}@{netloc}"
    except ValueError:
        return ""
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if not _is_tracking_query_param(key)
        ),
        doseq=True,
    )
    path = split.path or ""
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def title_fingerprint(title: object) -> str:
    normalized = str(title or "").casefold()
    chars = [" " if unicodedata.category(char).startswith(("P", "S")) else char for char in normalized]
    return _WHITESPACE_RE.sub(" ", "".join(chars)).strip()


def content_hash(title: object, summary: object, *, body_text: object = "") -> str:
    payload = "\x1f".join(
        (
            title_fingerprint(title),
            clean_news_text(summary),
            clean_news_text(body_text),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def qualified_content_hash(title: object, summary: object, body_text: object) -> str:
    title_key = title_fingerprint(title)
    if not title_key or _is_generic_title_fingerprint(title_key):
        return ""

    cleaned_summary = clean_news_text(summary)
    cleaned_body = clean_news_text(body_text)
    content_text = " ".join(part for part in (cleaned_summary, cleaned_body) if part).strip()
    if len(content_text) < _QUALIFIED_CONTENT_MIN_CHARS:
        return ""

    token_text = " ".join(part for part in (title_key, cleaned_summary, cleaned_body) if part).casefold()
    unique_tokens = {token for token in _ALNUM_TOKEN_RE.findall(token_text) if token}
    if len(unique_tokens) < _QUALIFIED_CONTENT_MIN_UNIQUE_TOKENS:
        return ""

    return content_hash(title, summary, body_text=body_text)


def _is_tracking_query_param(key: str) -> bool:
    normalized = str(key or "").lower()
    return normalized.startswith("utm_") or normalized in _TRACKING_QUERY_PARAMS


def _is_generic_title_fingerprint(title_key: str) -> bool:
    if title_key in _GENERIC_TITLE_FINGERPRINTS:
        return True
    tokens = title_key.split()
    generic_tokens = {
        "breaking",
        "feed",
        "home",
        "homepage",
        "latest",
        "live",
        "market",
        "markets",
        "news",
        "updates",
    }
    return bool(tokens) and set(tokens) <= generic_tokens


__all__ = [
    "canonicalize_url",
    "clean_news_text",
    "content_hash",
    "qualified_content_hash",
    "title_fingerprint",
]
