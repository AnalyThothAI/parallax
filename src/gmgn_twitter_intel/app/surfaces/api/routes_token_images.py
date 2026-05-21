from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from gmgn_twitter_intel.app.surfaces.api.dependencies import _runtime

TOKEN_IMAGE_CACHE_CONTROL = "public, max-age=86400"
TOKEN_IMAGE_ID_HEX_CHARS = frozenset("0123456789abcdef")

router = APIRouter()


@router.get("/token-images/{image_id}", include_in_schema=False)
def token_image(request: Request, image_id: str) -> FileResponse:
    if not _valid_image_id(image_id):
        raise HTTPException(status_code=404)

    runtime = _runtime(request)
    with runtime.repositories() as repos:
        row = repos.token_image_assets.ready_by_image_id(image_id)
    if row is None:
        raise HTTPException(status_code=404)

    path = _resolved_token_image_path(
        _token_image_cache_dir(runtime.settings.app_home),
        storage_path=row.get("storage_path"),
    )
    if path is None or not path.is_file():
        raise HTTPException(status_code=404)

    return FileResponse(
        path,
        headers={"Cache-Control": TOKEN_IMAGE_CACHE_CONTROL},
        media_type=str(row["media_type"]),
    )


def _valid_image_id(image_id: str) -> bool:
    return len(image_id) == 64 and all(char in TOKEN_IMAGE_ID_HEX_CHARS for char in image_id)


def _token_image_cache_dir(app_home: Any) -> Path:
    return Path(app_home) / "cache" / "token-images"


def _resolved_token_image_path(cache_dir: Path, *, storage_path: Any) -> Path | None:
    if not isinstance(storage_path, str) or not storage_path.strip():
        return None

    relative_path = Path(storage_path)
    if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
        return None

    try:
        cache_root = cache_dir.resolve()
        path = (cache_root / relative_path).resolve()
        path.relative_to(cache_root)
    except (OSError, ValueError):
        return None
    return path
