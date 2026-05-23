from __future__ import annotations

from hashlib import sha256
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json, postgres_safe_text

READY_MEDIA_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
READY_FILE_EXTENSIONS = {".gif", ".jpg", ".png", ".webp"}
CLAIM_LEASE_MS = 10 * 60 * 1000


class TokenImageAssetRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_pending_sources(self, rows: list[dict[str, Any]], now_ms: int, commit: bool = True) -> int:
        unique_rows = _unique_source_rows(rows)
        if not unique_rows:
            return 0

        affected = 0
        for source in unique_rows:
            source_url = _required_source_url(source.get("source_url"))
            source_url_hash = _source_url_hash(source_url)
            row = self.conn.execute(
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
            ).fetchone()
            if row is not None:
                affected += 1

        if commit:
            self.conn.commit()
        return affected

    def claim_due_sources(self, now_ms: int, limit: int) -> list[dict[str, Any]]:
        claim_limit = int(limit)
        if claim_limit <= 0:
            return []

        lease_until_ms = int(now_ms) + CLAIM_LEASE_MS
        rows = self.conn.execute(
            """
            WITH picked AS (
              SELECT image_id
              FROM token_image_assets
              WHERE status IN ('pending', 'error')
                AND next_refresh_at_ms <= %s
              ORDER BY next_refresh_at_ms ASC, updated_at_ms ASC, image_id ASC
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE token_image_assets AS asset
            SET status = 'pending',
                next_refresh_at_ms = %s,
                updated_at_ms = %s
            FROM picked
            WHERE asset.image_id = picked.image_id
              AND asset.status IN ('pending', 'error')
              AND asset.next_refresh_at_ms <= %s
            RETURNING asset.*
            """,
            (int(now_ms), claim_limit, lease_until_ms, int(now_ms), int(now_ms)),
        ).fetchall()
        return [dict(row) for row in rows]

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
        source_url_hash = _source_url_hash(normalized_source_url)
        public_url = f"/api/token-images/{source_url_hash}"
        row = self.conn.execute(
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
        ).fetchone()
        if row is None:
            raise ValueError("token image source has not been upserted")
        if commit:
            self.conn.commit()
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
        retry_at_ms = int(now_ms) + max(0, int(retry_ms))
        self.conn.execute(
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
        if commit:
            self.conn.commit()

    def mark_unsupported(
        self,
        source_url: str,
        error: str,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        normalized_source_url = _required_source_url(source_url)
        self.conn.execute(
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
        if commit:
            self.conn.commit()

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
