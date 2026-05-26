from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_TAIL_BOILERPLATE_RE = re.compile(
    r"\s*(?:read\s+more|subscribe(?:\s+now)?|sign\s+up|continue\s+reading|"
    r"the\s+post\s+.+?\s+appeared\s+first)\b.*$",
    re.IGNORECASE | re.DOTALL,
)


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
    raw = str(url or "").strip()
    if not raw:
        return ""
    split = urlsplit(raw)
    scheme = split.scheme.lower()
    hostname = (split.hostname or "").lower()
    netloc = hostname
    if split.port is not None:
        netloc = f"{netloc}:{split.port}"
    if split.username:
        userinfo = split.username
        if split.password:
            userinfo = f"{userinfo}:{split.password}"
        netloc = f"{userinfo}@{netloc}"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
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


def content_hash(title: object, summary: object, canonical_url: object, *, body_text: object = "") -> str:
    payload = "\x1f".join(
        (
            title_fingerprint(title),
            clean_news_text(summary),
            clean_news_text(body_text),
            canonicalize_url(canonical_url),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
