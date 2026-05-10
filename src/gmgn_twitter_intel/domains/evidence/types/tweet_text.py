from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z][A-Za-z0-9_]{1,15})")
HASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])#([A-Za-z][A-Za-z0-9_]{1,63})")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{1,20})")


@dataclass(frozen=True, slots=True)
class TextProjection:
    text_raw: str | None
    text_clean: str | None
    search_text: str | None
    urls: list[str]
    cashtags: list[str]
    hashtags: list[str]
    mentions: list[str]


def build_text_projection(text: str | None, *, reference_text: str | None = None) -> TextProjection:
    raw = text if text and text.strip() else None
    clean = _clean_text(raw)
    reference_clean = _clean_text(reference_text)
    parts = [part for part in (clean, reference_clean) if part]
    search_text = "\n".join(parts) if parts else None
    return TextProjection(
        text_raw=raw,
        text_clean=clean,
        search_text=search_text,
        urls=_extract_urls(raw),
        cashtags=extract_cashtags(raw),
        hashtags=_unique(HASHTAG_RE.findall(raw or "")),
        mentions=_unique(MENTION_RE.findall(raw or "")),
    )


def extract_cashtags(text: str | None) -> list[str]:
    return _unique(tag.upper() for tag in CASHTAG_RE.findall(text or ""))


def _clean_text(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    without_urls = URL_RE.sub(" ", text)
    without_emoji = "".join(ch for ch in without_urls if not _is_emoji_like(ch))
    normalized = re.sub(r"\s+", " ", without_emoji).strip()
    return normalized or None


def _extract_urls(text: str | None) -> list[str]:
    urls = []
    for match in URL_RE.findall(text or ""):
        urls.append(match.rstrip(".,!?;:)]}"))
    return _unique(urls)


def _is_emoji_like(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category in {"So", "Sk"} or ch in {"\ufe0f", "\u200d"}


def _unique(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        marker = item.lower()
        if item and marker not in seen:
            out.append(item)
            seen.add(marker)
    return out
