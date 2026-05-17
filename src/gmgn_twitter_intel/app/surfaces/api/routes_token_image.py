from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import ParseResult, urlparse
from uuid import uuid4

from curl_cffi import requests as curl_requests
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from gmgn_twitter_intel.app.surfaces.api.dependencies import _runtime
from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.responses import _json

TOKEN_IMAGE_PROXY_ALLOWED_PATH_PREFIXES = {
    "bin.bnbstatic.com": ("/",),
    "gmgn.ai": ("/external-res/",),
}
TOKEN_IMAGE_PROXY_CACHE_CONTROL = "public, max-age=86400"
TOKEN_IMAGE_PROXY_CURL_IMPERSONATE = "chrome142"
TOKEN_IMAGE_PROXY_MAX_BYTES = 3 * 1024 * 1024
TOKEN_IMAGE_PROXY_MEDIA_TYPES = frozenset({"image/gif", "image/jpeg", "image/png", "image/webp"})
TOKEN_IMAGE_PROXY_MEDIA_TYPES_BY_SUFFIX = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
TOKEN_IMAGE_PROXY_SUFFIX_BY_MEDIA_TYPE = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
TOKEN_IMAGE_PROXY_TIMEOUT_SECONDS = 8.0
TOKEN_IMAGE_PROXY_USER_AGENT = "Mozilla/5.0 AppleWebKit/537.36 Chrome/121 Safari/537.36"

router = APIRouter()


@router.get("/token-image", include_in_schema=False)
def token_image(request: Request, url: Annotated[str, Query(min_length=1)]) -> Response:
    return _token_image_response(url, cache_dir=_token_image_cache_dir(_runtime(request)))


def _token_image_response(raw_url: str, *, cache_dir: Path) -> Response:
    parsed = _validated_token_image_url(raw_url)
    cache_key = _token_image_cache_key(parsed)
    cached_path = _token_image_cache_hit(cache_dir, cache_key)
    if cached_path is not None:
        return _token_image_file_response(cached_path)

    headers = {
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "User-Agent": TOKEN_IMAGE_PROXY_USER_AGENT,
    }
    try:
        session = curl_requests.Session(impersonate=TOKEN_IMAGE_PROXY_CURL_IMPERSONATE)
        try:
            upstream = session.get(
                parsed.geturl(),
                allow_redirects=True,
                headers=headers,
                timeout=TOKEN_IMAGE_PROXY_TIMEOUT_SECONDS,
            )
        finally:
            session.close()
    except Exception:
        return _json({"ok": False, "error": "image_proxy_fetch_failed"}, status_code=502)

    upstream_url = urlparse(str(upstream.url or parsed.geturl()))
    if not _is_allowed_token_image_url(upstream_url.scheme, upstream_url.hostname, upstream_url.path):
        raise ApiBadRequest("unsupported_image_url", field="url")
    if int(upstream.status_code) < 200 or int(upstream.status_code) >= 300:
        return _json({"ok": False, "error": "image_proxy_fetch_failed"}, status_code=502)

    content_length = _int_header(upstream.headers.get("content-length"))
    if content_length is not None and content_length > TOKEN_IMAGE_PROXY_MAX_BYTES:
        return _json({"ok": False, "error": "image_proxy_too_large"}, status_code=413)

    content = upstream.content
    if len(content) > TOKEN_IMAGE_PROXY_MAX_BYTES:
        return _json({"ok": False, "error": "image_proxy_too_large"}, status_code=413)

    media_type = _token_image_media_type(
        url=str(upstream.url),
        content_type=upstream.headers.get("content-type"),
    )
    if media_type is None:
        return _json({"ok": False, "error": "unsupported_image_type"}, status_code=415)

    cached_path = _write_token_image_cache(cache_dir, cache_key=cache_key, media_type=media_type, content=content)
    return _token_image_file_response(cached_path)


def _token_image_cache_dir(runtime: Any) -> Path:
    return Path(runtime.settings.app_home) / "cache" / "token-images"


def _token_image_cache_key(parsed: ParseResult) -> str:
    return hashlib.sha256(parsed.geturl().encode("utf-8")).hexdigest()


def _token_image_cache_hit(cache_dir: Path, cache_key: str) -> Path | None:
    for suffix in TOKEN_IMAGE_PROXY_MEDIA_TYPES_BY_SUFFIX:
        path = cache_dir / f"{cache_key}{suffix}"
        if path.is_file():
            return path
    return None


def _write_token_image_cache(cache_dir: Path, *, cache_key: str, media_type: str, content: bytes) -> Path:
    suffix = TOKEN_IMAGE_PROXY_SUFFIX_BY_MEDIA_TYPE[media_type]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{cache_key}{suffix}"
    tmp_path = cache_dir / f".{cache_key}.{uuid4().hex}.tmp"
    tmp_path.write_bytes(content)
    tmp_path.replace(path)
    return path


def _token_image_file_response(path: Path) -> FileResponse:
    media_type = TOKEN_IMAGE_PROXY_MEDIA_TYPES_BY_SUFFIX.get(path.suffix.lower())
    if media_type is None:
        raise ApiBadRequest("unsupported_image_type", field="url")
    return FileResponse(
        path,
        headers={"Cache-Control": TOKEN_IMAGE_PROXY_CACHE_CONTROL},
        media_type=media_type,
    )


def _validated_token_image_url(raw_url: str) -> ParseResult:
    try:
        parsed = urlparse(raw_url.strip())
    except ValueError as exc:
        raise ApiBadRequest("invalid_image_url", field="url") from exc
    if not _is_allowed_token_image_url(parsed.scheme, parsed.hostname, parsed.path):
        raise ApiBadRequest("unsupported_image_url", field="url")
    if not parsed.path:
        raise ApiBadRequest("invalid_image_url", field="url")
    return parsed


def _is_allowed_token_image_url(scheme: str, host: str | None, path: str) -> bool:
    path_prefixes = TOKEN_IMAGE_PROXY_ALLOWED_PATH_PREFIXES.get((host or "").lower())
    return (
        scheme.lower() == "https"
        and path_prefixes is not None
        and any(path.startswith(prefix) for prefix in path_prefixes)
    )


def _token_image_media_type(*, url: str, content_type: str | None) -> str | None:
    normalized = (content_type or "").partition(";")[0].strip().lower()
    if normalized in TOKEN_IMAGE_PROXY_MEDIA_TYPES:
        return normalized
    path = urlparse(url).path.lower()
    suffix = "." + path.rsplit(".", maxsplit=1)[-1] if "." in path.rsplit("/", maxsplit=1)[-1] else ""
    return TOKEN_IMAGE_PROXY_MEDIA_TYPES_BY_SUFFIX.get(suffix)


def _int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
