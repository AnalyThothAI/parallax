from __future__ import annotations

from hashlib import sha256

from parallax.domains.asset_market.services.token_image_mirror import (
    TOKEN_IMAGE_MIRROR_MAX_BYTES,
    TOKEN_IMAGE_MIRROR_RETRY_MS,
    TokenImageMirrorService,
    is_allowed_token_image_source_url,
)

NOW_MS = 1_779_000_000_000
GMGN_URL = "https://gmgn.ai/external-res/token-alpha.png"
PNG_BYTES = b"\x89PNG\r\n\x1a\nunit-test"


def test_allowed_token_image_source_urls_are_provider_scoped() -> None:
    assert is_allowed_token_image_source_url("https://gmgn.ai/external-res/token-alpha.png")
    assert is_allowed_token_image_source_url("https://bin.bnbstatic.com/static/images/token.webp")
    assert is_allowed_token_image_source_url(
        "https://static.oklink.com/cdn/web3/currency/token/large/56-token/type=default_90_0?v=1"
    )


def test_rejected_token_image_source_urls_require_https_known_host_and_path() -> None:
    assert not is_allowed_token_image_source_url("http://gmgn.ai/external-res/token-alpha.png")
    assert not is_allowed_token_image_source_url("https://gmgn.ai/not-external/token-alpha.png")
    assert not is_allowed_token_image_source_url("https://static.okx.com/cdn/assets/token.gif")
    assert not is_allowed_token_image_source_url("https://example.com/external-res/token-alpha.png")


def test_mirror_marks_unsupported_when_magic_bytes_mismatch_media_type(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(_FakeImageResponse(content=b"not an image", content_type="image/png")),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "unsupported"
    assert repo.ready_rows == []
    assert repo.error_rows == []
    assert repo.unsupported_rows == [
        {
            "source_url": GMGN_URL,
            "now_ms": NOW_MS,
            "error_prefix": "unsupported_image_bytes",
        }
    ]
    assert not (tmp_path / "cache" / "token-images").exists()


def test_mirror_marks_unsupported_source_url_without_fetching(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    client = _FakeImageClient(_FakeImageResponse(content=PNG_BYTES, content_type="image/png"))
    service = TokenImageMirrorService(repository=repo, app_home=tmp_path, http_client=client)

    result = service.mirror_source({"source_url": "https://example.com/token.png"}, now_ms=NOW_MS)

    assert result["status"] == "unsupported"
    assert repo.ready_rows == []
    assert repo.error_rows == []
    assert repo.unsupported_rows == [
        {
            "source_url": "https://example.com/token.png",
            "now_ms": NOW_MS,
            "error_prefix": "unsupported_image_url",
        }
    ]
    assert client.requests == []


def test_mirror_accepts_valid_image_bytes_when_content_type_is_missing(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(_FakeImageResponse(content=PNG_BYTES, content_type=None)),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    content_hash = sha256(PNG_BYTES).hexdigest()
    assert result["status"] == "ready"
    assert repo.ready_rows == [
        {
            "source_url": GMGN_URL,
            "media_type": "image/png",
            "file_extension": ".png",
            "content_sha256": content_hash,
            "byte_size": len(PNG_BYTES),
            "storage_path": f"{content_hash}.png",
            "now_ms": NOW_MS,
        }
    ]
    assert repo.error_rows == []


def test_mirror_uses_magic_bytes_when_provider_content_type_disagrees(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(_FakeImageResponse(content=PNG_BYTES, content_type="image/webp")),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    content_hash = sha256(PNG_BYTES).hexdigest()
    assert result["status"] == "ready"
    assert repo.ready_rows == [
        {
            "source_url": GMGN_URL,
            "media_type": "image/png",
            "file_extension": ".png",
            "content_sha256": content_hash,
            "byte_size": len(PNG_BYTES),
            "storage_path": f"{content_hash}.png",
            "now_ms": NOW_MS,
        }
    ]
    assert repo.unsupported_rows == []


def test_mirror_rejects_malformed_png_with_only_four_byte_prefix(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(_FakeImageResponse(content=b"\x89PNGbad", content_type="image/png")),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "unsupported"
    assert repo.ready_rows == []
    assert repo.error_rows == []
    assert repo.unsupported_rows[0]["error_prefix"] == "unsupported_image_bytes"


def test_mirror_marks_unsupported_when_response_is_oversized(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(
            _FakeImageResponse(
                content=PNG_BYTES,
                content_type="image/png",
                headers={"content-length": str(TOKEN_IMAGE_MIRROR_MAX_BYTES + 1)},
            )
        ),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "unsupported"
    assert repo.ready_rows == []
    assert repo.error_rows == []
    assert repo.unsupported_rows[0]["error_prefix"] == "image_too_large"


def test_mirror_marks_unsupported_when_actual_body_is_oversized(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(
            _FakeImageResponse(
                content=b"\x89PNG\r\n\x1a\n" + (b"x" * TOKEN_IMAGE_MIRROR_MAX_BYTES),
                content_type="image/png",
            )
        ),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "unsupported"
    assert repo.ready_rows == []
    assert repo.error_rows == []
    assert repo.unsupported_rows[0]["error_prefix"] == "image_too_large"


def test_mirror_marks_upstream_404_as_error_with_retry_backoff(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FakeImageClient(
            _FakeImageResponse(content=b"not found", content_type="text/plain", status_code=404)
        ),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "error"
    assert repo.ready_rows == []
    assert repo.error_rows == [
        {
            "source_url": GMGN_URL,
            "now_ms": NOW_MS,
            "retry_ms": TOKEN_IMAGE_MIRROR_RETRY_MS,
            "error_prefix": "image_fetch_failed",
        }
    ]


def test_mirror_writes_verified_image_atomically_and_marks_ready(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    client = _FakeImageClient(_FakeImageResponse(content=PNG_BYTES, content_type="image/png"))
    service = TokenImageMirrorService(repository=repo, app_home=tmp_path, http_client=client)

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    content_hash = sha256(PNG_BYTES).hexdigest()
    expected_filename = f"{content_hash}.png"
    image_dir = tmp_path / "cache" / "token-images"
    assert result["status"] == "ready"
    assert (image_dir / expected_filename).read_bytes() == PNG_BYTES
    assert list(image_dir.glob("*.tmp")) == []
    assert repo.ready_rows == [
        {
            "source_url": GMGN_URL,
            "media_type": "image/png",
            "file_extension": ".png",
            "content_sha256": content_hash,
            "byte_size": len(PNG_BYTES),
            "storage_path": expected_filename,
            "now_ms": NOW_MS,
        }
    ]
    assert repo.error_rows == []
    assert client.requests[0]["headers"]["User-Agent"].startswith("Mozilla/5.0")


def test_mirror_marks_provider_fetch_failures_for_retry(tmp_path) -> None:
    repo = _FakeTokenImageAssetRepository()
    service = TokenImageMirrorService(
        repository=repo,
        app_home=tmp_path,
        http_client=_FailingImageClient(RuntimeError("tls handshake failed")),
    )

    result = service.mirror_source({"source_url": GMGN_URL}, now_ms=NOW_MS)

    assert result["status"] == "error"
    assert repo.ready_rows == []
    assert repo.error_rows == [
        {
            "source_url": GMGN_URL,
            "now_ms": NOW_MS,
            "retry_ms": TOKEN_IMAGE_MIRROR_RETRY_MS,
            "error_prefix": "image_fetch_failed",
        }
    ]


class _FakeTokenImageAssetRepository:
    def __init__(self) -> None:
        self.ready_rows: list[dict[str, object]] = []
        self.error_rows: list[dict[str, object]] = []
        self.unsupported_rows: list[dict[str, object]] = []

    def mark_ready(
        self,
        source_url: str,
        media_type: str,
        file_extension: str,
        content_sha256: str,
        byte_size: int,
        storage_path: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, object]:
        row = {
            "source_url": source_url,
            "media_type": media_type,
            "file_extension": file_extension,
            "content_sha256": content_sha256,
            "byte_size": byte_size,
            "storage_path": storage_path,
            "now_ms": now_ms,
        }
        self.ready_rows.append(row)
        return {"status": "ready", **row}

    def mark_error(self, source_url: str, error: str, now_ms: int, retry_ms: int, commit: bool = True) -> None:
        self.error_rows.append(
            {
                "source_url": source_url,
                "now_ms": now_ms,
                "retry_ms": retry_ms,
                "error_prefix": error.split(":", maxsplit=1)[0],
            }
        )

    def mark_unsupported(self, source_url: str, error: str, now_ms: int, commit: bool = True) -> None:
        self.unsupported_rows.append(
            {
                "source_url": source_url,
                "now_ms": now_ms,
                "error_prefix": error.split(":", maxsplit=1)[0],
            }
        )


class _FakeImageClient:
    def __init__(self, response: _FakeImageResponse) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> _FakeImageResponse:
        self.requests.append({"url": url, **kwargs})
        return self.response


class _FailingImageClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get(self, url: str, **kwargs: object) -> _FakeImageResponse:
        raise self.error


class _FakeImageResponse:
    def __init__(
        self,
        *,
        content: bytes,
        content_type: str | None,
        status_code: int = 200,
        url: str = GMGN_URL,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.url = url
        self.headers = dict(headers or {})
        if content_type is not None:
            self.headers["content-type"] = content_type
