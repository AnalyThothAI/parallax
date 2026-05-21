from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from os import environ
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from urllib.parse import parse_qs, urlparse

from cryptopanic_cli.browser_transport import CryptopanicBrowserTransport
from cryptopanic_cli.parser import normalize_posts_page

from gmgn_twitter_intel.integrations.news_feeds.feed_client import FeedFetchResult

DEFAULT_CRYPTOPANIC_PROFILE_DIR = Path(gettempdir()) / "gmgn-twitter-intel" / "cryptopanic-profile"


class CryptopanicFeedClient:
    def __init__(
        self,
        *,
        transport_factory: Any = CryptopanicBrowserTransport,
        default_profile_dir: str | Path = DEFAULT_CRYPTOPANIC_PROFILE_DIR,
        default_timeout_seconds: float = 35.0,
        default_headless: bool = True,
    ) -> None:
        self._transport_factory = transport_factory
        self._default_profile_dir = Path(default_profile_dir)
        self._default_timeout_seconds = float(default_timeout_seconds)
        self._default_headless = bool(default_headless)

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        provider_type: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> FeedFetchResult:
        del provider_type, source, last_modified
        options = _parse_options(
            url,
            default_profile_dir=self._default_profile_dir,
            default_timeout_seconds=self._default_timeout_seconds,
            default_headless=self._default_headless,
        )
        with self._transport_factory(
            profile_dir=options["profile_dir"],
            headless=options["headless"],
            timeout=options["timeout"],
            proxy=options["proxy"],
            evidence_dir=options["evidence_dir"],
        ) as transport:
            raw_page = transport.fetch_posts_page(**options["query"])

        page = normalize_posts_page(raw_page)
        next_etag = page.next
        if etag and next_etag == etag and not page.results:
            return FeedFetchResult(status_code=304, etag=next_etag, not_modified=True, entries=[])

        entries: list[dict[str, Any]] = []
        max_items = options["max_items"]
        for post in page.results:
            if str(getattr(post, "kind", "") or "").lower() == "sponsored":
                continue
            entries.append(_post_to_feed_entry(post))
            if len(entries) >= max_items:
                break
        return FeedFetchResult(
            status_code=200,
            entries=entries,
            etag=next_etag,
            not_modified=False,
            feed={"provider": "cryptopanic", "next": page.next, "previous": page.previous},
        )

    def close(self) -> None:
        return None


def _parse_options(
    url: str,
    *,
    default_profile_dir: Path,
    default_timeout_seconds: float,
    default_headless: bool,
) -> dict[str, Any]:
    parsed = urlparse(str(url))
    if parsed.scheme != "cryptopanic":
        raise ValueError(f"unsupported CryptoPanic feed URL scheme: {parsed.scheme}")
    params = parse_qs(parsed.query, keep_blank_values=False)
    currencies = _csv_values(params.get("currencies"), transform=str.upper)
    regions = _csv_values(params.get("regions"), transform=str.lower)
    query: dict[str, Any] = {}
    if currencies:
        query["currencies"] = currencies
    if _first(params, "filter"):
        query["filter"] = _first(params, "filter")
    if _first(params, "kind"):
        query["kind"] = _first(params, "kind")
    if regions:
        query["regions"] = regions
    if _first(params, "search"):
        query["search"] = _first(params, "search")
    if _first(params, "page_url"):
        query["page_url"] = _first(params, "page_url")

    profile_dir = Path(_first(params, "profile_dir") or environ.get("CRYPTOPANIC_PROFILE_DIR") or default_profile_dir)
    timeout = float(_first(params, "timeout") or default_timeout_seconds)
    evidence_dir_raw = _first(params, "evidence_dir") or environ.get("CRYPTOPANIC_EVIDENCE_DIR")
    headful = _first(params, "headful")
    return {
        "profile_dir": profile_dir,
        "headless": not _truthy(headful) if headful is not None else default_headless,
        "timeout": timeout,
        "proxy": _first(params, "proxy") or environ.get("CRYPTOPANIC_PROXY") or None,
        "evidence_dir": Path(evidence_dir_raw) if evidence_dir_raw else None,
        "max_items": max(1, int(_first(params, "max_items") or 50)),
        "query": query,
    }


def _post_to_feed_entry(post: Any) -> dict[str, Any]:
    source = getattr(post, "source", None)
    instruments = list(getattr(post, "instruments", []) or [])
    content = getattr(post, "content", None)
    content_text = _optional_str(getattr(content, "clean", None)) or _optional_str(getattr(content, "original", None))
    summary = _optional_str(getattr(post, "description", None)) or content_text or ""
    link = _optional_str(getattr(post, "original_url", None)) or _optional_str(getattr(post, "url", None)) or ""
    entry = {
        "id": f"cryptopanic:{post.id}",
        "link": link,
        "title": str(getattr(post, "title", "") or "").strip() or "Untitled CryptoPanic post",
        "summary": summary,
        "description": summary,
        "content": [{"value": content_text or summary}],
        "published_parsed": _datetime_to_struct_time(getattr(post, "published_at", None)),
        "updated_parsed": _datetime_to_struct_time(getattr(post, "created_at", None)),
        "language": _optional_str(getattr(source, "region", None)) or "en",
        "source": _dataclass_dict(source),
        "source_domain": _optional_str(getattr(source, "domain", None)),
        "cryptopanic_url": _optional_str(getattr(post, "url", None)),
        "original_url": _optional_str(getattr(post, "original_url", None)),
        "kind": _optional_str(getattr(post, "kind", None)),
        "author": _optional_str(getattr(post, "author", None)),
        "image": _optional_str(getattr(post, "image", None)),
        "currencies": [_dataclass_dict(instrument) for instrument in instruments],
        "currencies_codes": [_optional_str(getattr(instrument, "code", None)) for instrument in instruments],
        "votes": _dataclass_dict(getattr(post, "votes", None)),
        "panic_score": getattr(post, "panic_score", None),
        "panic_score_1h": getattr(post, "panic_score_1h", None),
        "raw": getattr(post, "raw", {}),
    }
    entry["currencies_codes"] = [code for code in entry["currencies_codes"] if code]
    return entry


def _datetime_to_struct_time(value: Any) -> time.struct_time | None:
    if not isinstance(value, datetime):
        return None
    return value.utctimetuple()


def _dataclass_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key) or []
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def _csv_values(values: list[str] | None, *, transform: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        for part in str(value or "").split(","):
            item = transform(part.strip())
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
    return normalized


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}
