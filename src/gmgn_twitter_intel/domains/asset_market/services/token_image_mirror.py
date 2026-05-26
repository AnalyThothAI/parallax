from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, urlparse
from uuid import uuid4

from curl_cffi import requests as curl_requests

TOKEN_IMAGE_MIRROR_ALLOWED_PATH_PREFIXES = {
    "bin.bnbstatic.com": ("/",),
    "gmgn.ai": ("/external-res/",),
    "static.okx.com": ("/",),
}
TOKEN_IMAGE_MIRROR_CURL_IMPERSONATE = "chrome142"
TOKEN_IMAGE_MIRROR_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/121 Safari/537.36",
}
TOKEN_IMAGE_MIRROR_MAX_BYTES = 3 * 1024 * 1024
TOKEN_IMAGE_MIRROR_RETRY_MS = 15 * 60 * 1000
TOKEN_IMAGE_MIRROR_TIMEOUT_SECONDS = 8.0

_MEDIA_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class TokenImageMirrorService:
    def __init__(
        self,
        *,
        repository: Any,
        app_home: str | Path,
        http_client: Any | None = None,
        retry_ms: int = TOKEN_IMAGE_MIRROR_RETRY_MS,
    ) -> None:
        self.repository = repository
        self.app_home = Path(app_home)
        self.http_client = http_client or _CurlCffiTokenImageClient()
        self.retry_ms = int(retry_ms)

    def mirror_source(self, row: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        source_url = str(row.get("source_url") or "").strip()
        try:
            source_url = _required_claimed_source_url(source_url)
            result = self._mirror_source(source_url=source_url, now_ms=now_ms)
        except ValueError as exc:
            error = _error_text(exc)
            self.repository.mark_unsupported(
                source_url,
                error=error,
                now_ms=int(now_ms),
            )
            return {"status": "unsupported", "source_url": source_url, "error": error}
        except _TokenImageMirrorError as exc:
            error = str(exc)
            if _is_terminal_unsupported_error(error):
                self.repository.mark_unsupported(
                    source_url,
                    error=error,
                    now_ms=int(now_ms),
                )
                return {"status": "unsupported", "source_url": source_url, "error": error}
            self.repository.mark_error(source_url, error=error, now_ms=int(now_ms), retry_ms=self.retry_ms)
            return {"status": "error", "source_url": source_url, "error": str(exc)}
        except Exception as exc:
            error = f"image_fetch_failed: {_error_text(exc)}"
            self.repository.mark_error(
                source_url,
                error=error,
                now_ms=int(now_ms),
                retry_ms=self.retry_ms,
            )
            return {"status": "error", "source_url": source_url, "error": error}
        return {"status": "ready", "source_url": source_url, "asset": result}

    def _mirror_source(self, *, source_url: str, now_ms: int) -> dict[str, Any]:
        parsed = validated_token_image_source_url(source_url)
        response = self._fetch(parsed.geturl())
        final_url = str(getattr(response, "url", "") or parsed.geturl())
        validated_token_image_source_url(final_url)

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 200 or status_code >= 300:
            raise _TokenImageMirrorError(f"image_fetch_failed: upstream_status_{status_code}")

        headers = _response_headers(response)
        content_length = _int_header(headers.get("content-length"))
        if content_length is not None and content_length > TOKEN_IMAGE_MIRROR_MAX_BYTES:
            raise _TokenImageMirrorError("image_too_large: content_length_exceeded")

        content = bytes(getattr(response, "content", b"") or b"")
        if len(content) > TOKEN_IMAGE_MIRROR_MAX_BYTES:
            raise _TokenImageMirrorError("image_too_large: byte_limit_exceeded")

        media = _verified_media(content=content, content_type=headers.get("content-type"))
        content_hash = sha256(content).hexdigest()
        filename = f"{content_hash}{media.file_extension}"
        self._write_cache_file(filename=filename, content=content)

        return cast(
            dict[str, Any],
            self.repository.mark_ready(
                source_url,
                media_type=media.media_type,
                file_extension=media.file_extension,
                content_sha256=content_hash,
                byte_size=len(content),
                storage_path=filename,
                now_ms=int(now_ms),
            ),
        )

    def _fetch(self, url: str) -> Any:
        try:
            return self.http_client.get(
                url,
                allow_redirects=True,
                headers=dict(TOKEN_IMAGE_MIRROR_HEADERS),
                timeout=TOKEN_IMAGE_MIRROR_TIMEOUT_SECONDS,
            )
        except _TokenImageMirrorError:
            raise
        except Exception as exc:
            raise _TokenImageMirrorError(f"image_fetch_failed: {_error_text(exc)}") from exc

    def _write_cache_file(self, *, filename: str, content: bytes) -> None:
        cache_dir = self.app_home / "cache" / "token-images"
        cache_dir.mkdir(parents=True, exist_ok=True)
        final_path = cache_dir / filename
        tmp_path = cache_dir / f".{filename}.{uuid4().hex}.tmp"
        try:
            tmp_path.write_bytes(content)
            tmp_path.replace(final_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


def is_allowed_token_image_source_url(raw_url: str) -> bool:
    try:
        validated_token_image_source_url(raw_url)
    except ValueError:
        return False
    return True


def validated_token_image_source_url(raw_url: str) -> ParseResult:
    try:
        parsed = urlparse(str(raw_url or "").strip())
    except ValueError as exc:
        raise ValueError("invalid_image_url") from exc
    path_prefixes = TOKEN_IMAGE_MIRROR_ALLOWED_PATH_PREFIXES.get((parsed.hostname or "").lower())
    if (
        parsed.scheme.lower() != "https"
        or path_prefixes is None
        or not parsed.path
        or not any(parsed.path.startswith(prefix) for prefix in path_prefixes)
    ):
        raise ValueError("unsupported_image_url")
    return parsed


@dataclass(frozen=True)
class _VerifiedMedia:
    media_type: str
    file_extension: str


class _TokenImageMirrorError(Exception):
    pass


class _CurlCffiTokenImageClient:
    def get(self, url: str, **kwargs: Any) -> Any:
        session = curl_requests.Session(impersonate=cast(Any, TOKEN_IMAGE_MIRROR_CURL_IMPERSONATE))
        try:
            return session.get(url, **kwargs)
        finally:
            session.close()


def _required_claimed_source_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("source_url is required")
    if not text.startswith(("http://", "https://")):
        raise ValueError("source_url must be an absolute URL")
    return text


def _verified_media(*, content: bytes, content_type: str | None) -> _VerifiedMedia:
    header_media_type = _header_media_type(content_type)
    magic_media_type = _magic_media_type(content)
    if magic_media_type is None:
        raise _TokenImageMirrorError("unsupported_image_bytes: unknown_magic")

    if header_media_type is None:
        return _VerifiedMedia(
            media_type=magic_media_type,
            file_extension=_MEDIA_EXTENSIONS[magic_media_type],
        )

    if header_media_type != magic_media_type:
        raise _TokenImageMirrorError("unsupported_image_bytes: media_type_mismatch")

    return _VerifiedMedia(
        media_type=magic_media_type,
        file_extension=_MEDIA_EXTENSIONS[magic_media_type],
    )


def _magic_media_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _header_media_type(value: str | None) -> str | None:
    media_type = str(value or "").partition(";")[0].strip().lower()
    if not media_type:
        return None
    return media_type if media_type in _MEDIA_EXTENSIONS else None


def _response_headers(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", None) or {}
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


def _int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _error_text(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:200] if text else exc.__class__.__name__


def _is_terminal_unsupported_error(error: str) -> bool:
    return error.startswith("unsupported_") or error.startswith("image_too_large:")
