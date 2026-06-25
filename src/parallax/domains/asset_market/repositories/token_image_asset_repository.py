from __future__ import annotations

from contextlib import AbstractContextManager
from hashlib import sha256
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.platform.db.json_safety import postgres_safe_json, postgres_safe_text

READY_MEDIA_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
READY_FILE_EXTENSIONS = {".gif", ".jpg", ".png", ".webp"}


class TokenImageAssetRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_pending_sources(self, rows: list[dict[str, Any]], now_ms: int, commit: bool = True) -> int:
        unique_rows = _unique_source_rows(rows)
        if not unique_rows:
            return 0
        if commit:
            with _transaction(self.conn):
                return self.upsert_pending_sources(unique_rows, now_ms=now_ms, commit=False)

        affected = 0
        for source in unique_rows:
            source_url = _required_source_url(source.get("source_url"))
            source_url_hash = _source_url_hash(source_url)
            cursor = self.conn.execute(
                """
                INSERT INTO token_image_assets(
                  image_id, source_url, source_url_hash, source_provider, source_kind, status,
                  raw_ref_json, observed_at_ms, next_refresh_at_ms, created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s)
                ON CONFLICT(image_id) DO UPDATE SET
                  source_url = excluded.source_url,
                  source_url_hash = excluded.source_url_hash,
                  source_provider = excluded.source_provider,
                  source_kind = excluded.source_kind,
                  raw_ref_json = excluded.raw_ref_json,
                  observed_at_ms = excluded.observed_at_ms,
                  updated_at_ms = excluded.updated_at_ms
                WHERE token_image_assets.status NOT IN ('ready', 'unsupported')
                RETURNING image_id
                """,
                (
                    source_url_hash,
                    source_url,
                    source_url_hash,
                    _required_text(source.get("source_provider"), field_name="source_provider"),
                    _required_text(source.get("source_kind"), field_name="source_kind"),
                    Jsonb(_sanitize_json(source.get("raw_ref_json") or {})),
                    int(now_ms),
                    int(now_ms),
                    int(now_ms),
                    int(now_ms),
                ),
            )
            row = cursor.fetchone()
            affected += _single_returning_rowcount(cursor, row)

        return affected

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
    ) -> dict[str, Any]:
        normalized_source_url = _required_source_url(source_url)
        if commit:
            with _transaction(self.conn):
                return self.mark_ready(
                    source_url=normalized_source_url,
                    media_type=media_type,
                    file_extension=file_extension,
                    content_sha256=content_sha256,
                    byte_size=byte_size,
                    storage_path=storage_path,
                    now_ms=now_ms,
                    commit=False,
                )
        source_url_hash = _source_url_hash(normalized_source_url)
        public_url = f"/api/token-images/{source_url_hash}"
        cursor = self.conn.execute(
            """
            UPDATE token_image_assets
            SET status = 'ready',
                media_type = %s,
                file_extension = %s,
                content_sha256 = %s,
                byte_size = %s,
                storage_path = %s,
                public_url = %s,
                failure_count = 0,
                last_error = NULL,
                next_refresh_at_ms = %s,
                updated_at_ms = %s
            WHERE source_url_hash = %s
            RETURNING *
            """,
            (
                _ready_media_type(media_type),
                _ready_file_extension(file_extension),
                _sha256_hex(content_sha256, field_name="content_sha256"),
                _positive_int(byte_size, field_name="byte_size"),
                _relative_cache_filename(storage_path),
                public_url,
                int(now_ms),
                int(now_ms),
                source_url_hash,
            ),
        )
        row = cursor.fetchone()
        _single_returning_rowcount(cursor, row)
        if row is None:
            raise ValueError("token image source has not been upserted")
        return dict(row)

    def mark_error(
        self,
        source_url: str,
        error: str,
        now_ms: int,
        retry_ms: int,
        commit: bool = True,
    ) -> None:
        normalized_source_url = _required_source_url(source_url)
        parsed_retry_ms = _required_positive_int(
            retry_ms,
            "token_image_asset_retry_ms_required",
        )
        if commit:
            with _transaction(self.conn):
                self.mark_error(
                    source_url=normalized_source_url,
                    error=error,
                    now_ms=now_ms,
                    retry_ms=parsed_retry_ms,
                    commit=False,
                )
                return
        retry_at_ms = int(now_ms) + parsed_retry_ms
        cursor = self.conn.execute(
            """
            UPDATE token_image_assets
            SET status = 'error',
                failure_count = failure_count + 1,
                last_error = %s,
                next_refresh_at_ms = %s,
                updated_at_ms = %s
            WHERE source_url_hash = %s
              AND status NOT IN ('ready', 'unsupported')
            """,
            (
                _optional_text(error),
                retry_at_ms,
                int(now_ms),
                _source_url_hash(normalized_source_url),
            ),
        )
        _single_rowcount(cursor)

    def mark_unsupported(
        self,
        source_url: str,
        error: str,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        normalized_source_url = _required_source_url(source_url)
        if commit:
            with _transaction(self.conn):
                self.mark_unsupported(
                    source_url=normalized_source_url,
                    error=error,
                    now_ms=now_ms,
                    commit=False,
                )
                return
        cursor = self.conn.execute(
            """
            UPDATE token_image_assets
            SET status = 'unsupported',
                failure_count = failure_count + 1,
                last_error = %s,
                next_refresh_at_ms = %s,
                updated_at_ms = %s
            WHERE source_url_hash = %s
              AND status <> 'ready'
            """,
            (
                _optional_text(error),
                int(now_ms),
                int(now_ms),
                _source_url_hash(normalized_source_url),
            ),
        )
        _single_rowcount(cursor)

    def ready_by_source_urls(self, source_urls: list[str]) -> dict[str, dict[str, Any]]:
        source_url_hashes = [_source_url_hash(source_url) for source_url in _unique_source_urls(source_urls)]
        if not source_url_hashes:
            return {}

        rows = self.conn.execute(
            """
            SELECT *
            FROM token_image_assets
            WHERE status = 'ready'
              AND source_url_hash = ANY(%s)
            """,
            (source_url_hashes,),
        ).fetchall()
        return {str(row["source_url"]): dict(row) for row in rows}

    def by_source_urls(self, source_urls: list[str]) -> dict[str, dict[str, Any]]:
        source_url_hashes = [_source_url_hash(source_url) for source_url in _unique_source_urls(source_urls)]
        if not source_url_hashes:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_image_assets
            WHERE source_url_hash = ANY(%s)
            """,
            (source_url_hashes,),
        ).fetchall()
        return {str(row["source_url"]): dict(row) for row in rows}

    def terminal_by_source_urls(self, source_urls: list[str]) -> dict[str, dict[str, Any]]:
        source_url_hashes = [_source_url_hash(source_url) for source_url in _unique_source_urls(source_urls)]
        if not source_url_hashes:
            return {}

        rows = self.conn.execute(
            """
            SELECT *
            FROM token_image_assets
            WHERE status IN ('ready', 'unsupported')
              AND source_url_hash = ANY(%s)
            """,
            (source_url_hashes,),
        ).fetchall()
        return {str(row["source_url"]): dict(row) for row in rows}

    def ready_by_image_id(self, image_id: str) -> dict[str, Any] | None:
        normalized_image_id = _optional_text(image_id)
        if not normalized_image_id:
            return None
        row = self.conn.execute(
            """
            SELECT *
            FROM token_image_assets
            WHERE status = 'ready'
              AND image_id = %s
            """,
            (normalized_image_id,),
        ).fetchone()
        return dict(row) if row else None


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_image_asset_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("token_image_asset_repository_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("token_image_asset_repository_rowcount_invalid")
    return rowcount


def _single_rowcount(cursor: Any) -> int:
    count = _cursor_rowcount(cursor)
    if count not in (0, 1):
        raise TypeError("token_image_asset_repository_rowcount_invalid")
    return count


def _single_returning_rowcount(cursor: Any, row: Any | None) -> int:
    count = _single_rowcount(cursor)
    if count != (1 if row is not None else 0):
        raise TypeError("token_image_asset_repository_rowcount_invalid")
    return count


def _unique_source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_url = _required_source_url(row.get("source_url"))
        unique[_source_url_hash(source_url)] = {**row, "source_url": source_url}
    return list(unique.values())


def _unique_source_urls(source_urls: list[str]) -> list[str]:
    unique: dict[str, str] = {}
    for source_url in source_urls:
        normalized = _required_source_url(source_url)
        unique.setdefault(_source_url_hash(normalized), normalized)
    return list(unique.values())


def _source_url_hash(source_url: str) -> str:
    return sha256(source_url.encode("utf-8")).hexdigest()


def _required_source_url(value: Any) -> str:
    text = _required_text(value, field_name="source_url")
    if not text.startswith(("http://", "https://")):
        raise ValueError("token image source_url must be an absolute URL")
    return text


def _ready_media_type(value: Any) -> str:
    text = _required_text(value, field_name="media_type").lower()
    if text not in READY_MEDIA_TYPES:
        raise ValueError("token image media_type is unsupported")
    return text


def _ready_file_extension(value: Any) -> str:
    text = _required_text(value, field_name="file_extension").lower()
    if text not in READY_FILE_EXTENSIONS:
        raise ValueError("token image file_extension is unsupported")
    return text


def _sha256_hex(value: Any, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field_name} must be a lowercase sha256 hex digest")
    return text


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_image_asset_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_image_asset_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _relative_cache_filename(value: Any) -> str:
    text = _required_text(value, field_name="storage_path")
    if text.startswith(("/", "\\")) or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError("token image storage_path must be a relative cache filename")
    return text


def _positive_int(value: Any, *, field_name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


def _optional_text(value: Any) -> str | None:
    text = _clean_text(value).strip()
    return text or None


def _required_text(value: Any, *, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _clean_text(value: Any) -> str:
    return postgres_safe_text(value)


def _sanitize_json(value: Any) -> Any:
    return postgres_safe_json(value)
