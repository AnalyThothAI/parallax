from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash
from parallax.platform.db.json_safety import postgres_safe_json, postgres_safe_text

_PUBLICATION_METADATA_FIELDS = {"computed_at_ms", "updated_at_ms", "projected_at_ms", "payload_hash"}


class TokenProfileCurrentRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_current(self, row: dict[str, Any], *, commit: bool = True) -> bool:
        if commit:
            with _transaction(self.conn):
                return self.upsert_current(row, commit=False)
        computed_at_ms = int(row["computed_at_ms"])
        payload = {
            "target_type": _required_text(row.get("target_type")),
            "target_id": _required_text(row.get("target_id")),
            "status": _required_text(row.get("status")),
            "profile_provider": _optional_text(row.get("profile_provider")),
            "source_kind": _required_text(row.get("source_kind")),
            "source_ref": _optional_text(row.get("source_ref")),
            "symbol": _optional_text(row.get("symbol")),
            "name": _optional_text(row.get("name")),
            "logo_url": _optional_text(row.get("logo_url")),
            "logo_image_id": _optional_text(row.get("logo_image_id")),
            "logo_source_provider": _optional_text(row.get("logo_source_provider")),
            "logo_source_url_hash": _optional_text(row.get("logo_source_url_hash")),
            "banner_url": _optional_text(row.get("banner_url")),
            "website_url": _optional_text(row.get("website_url")),
            "twitter_username": _optional_text(row.get("twitter_username")),
            "twitter_url": _optional_text(row.get("twitter_url")),
            "telegram_url": _optional_text(row.get("telegram_url")),
            "gmgn_url": _optional_text(row.get("gmgn_url")),
            "geckoterminal_url": _optional_text(row.get("geckoterminal_url")),
            "description": _optional_text(row.get("description")),
            "quality_flags_json": _required_json_list(row, "quality_flags_json"),
            "source_payload_json": _required_json_mapping(row, "source_payload_json"),
            "observed_at_ms": _int_or_none(row.get("observed_at_ms")),
            "computed_at_ms": computed_at_ms,
            "updated_at_ms": int(row.get("updated_at_ms") or computed_at_ms),
        }
        payload_hash = stable_current_payload_hash(
            {key: value for key, value in payload.items() if key not in _PUBLICATION_METADATA_FIELDS}
        )
        cursor = self.conn.execute(
            """
            INSERT INTO token_profile_current(
              target_type, target_id, status, profile_provider, source_kind, source_ref,
              symbol, name, logo_url, logo_image_id, logo_source_provider,
              logo_source_url_hash, banner_url, website_url, twitter_username,
              twitter_url, telegram_url, gmgn_url, geckoterminal_url,
              description, quality_flags_json, source_payload_json,
              observed_at_ms, computed_at_ms, updated_at_ms, payload_hash
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(target_type, target_id) DO UPDATE SET
              status = excluded.status,
              profile_provider = excluded.profile_provider,
              source_kind = excluded.source_kind,
              source_ref = excluded.source_ref,
              symbol = excluded.symbol,
              name = excluded.name,
              logo_url = excluded.logo_url,
              logo_image_id = excluded.logo_image_id,
              logo_source_provider = excluded.logo_source_provider,
              logo_source_url_hash = excluded.logo_source_url_hash,
              banner_url = excluded.banner_url,
              website_url = excluded.website_url,
              twitter_username = excluded.twitter_username,
              twitter_url = excluded.twitter_url,
              telegram_url = excluded.telegram_url,
              gmgn_url = excluded.gmgn_url,
              geckoterminal_url = excluded.geckoterminal_url,
              description = excluded.description,
              quality_flags_json = excluded.quality_flags_json,
              source_payload_json = excluded.source_payload_json,
              observed_at_ms = excluded.observed_at_ms,
              computed_at_ms = excluded.computed_at_ms,
              updated_at_ms = excluded.updated_at_ms,
              payload_hash = excluded.payload_hash
            WHERE token_profile_current.payload_hash IS DISTINCT FROM excluded.payload_hash
            RETURNING true AS changed
            """,
            (
                payload["target_type"],
                payload["target_id"],
                payload["status"],
                payload["profile_provider"],
                payload["source_kind"],
                payload["source_ref"],
                payload["symbol"],
                payload["name"],
                payload["logo_url"],
                payload["logo_image_id"],
                payload["logo_source_provider"],
                payload["logo_source_url_hash"],
                payload["banner_url"],
                payload["website_url"],
                payload["twitter_username"],
                payload["twitter_url"],
                payload["telegram_url"],
                payload["gmgn_url"],
                payload["geckoterminal_url"],
                payload["description"],
                Jsonb(payload["quality_flags_json"]),
                Jsonb(payload["source_payload_json"]),
                payload["observed_at_ms"],
                payload["computed_at_ms"],
                payload["updated_at_ms"],
                payload_hash,
            ),
        )
        row = cursor.fetchone()
        return _single_returning_changed(cursor, row)

    def current_for_targets(self, targets: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
        requested = _dedupe_targets(targets)
        if not requested:
            return {}
        target_types = [target_type for target_type, _ in requested]
        target_ids = [target_id for _, target_id in requested]
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_profile_current
            WHERE (target_type, target_id) IN (
              SELECT *
              FROM unnest(%s::text[], %s::text[])
            )
            """,
            (target_types, target_ids),
        ).fetchall()
        return {(str(row["target_type"]), str(row["target_id"])): dict(row) for row in rows}


def _dedupe_targets(targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
    normalized = [(_optional_text(target_type), _optional_text(target_id)) for target_type, target_id in targets]
    return [
        (str(target_type), str(target_id))
        for target_type, target_id in dict.fromkeys(normalized)
        if target_type and target_id
    ]


def _optional_text(value: Any) -> str | None:
    text = _clean_text(value).strip()
    return text or None


def _required_text(value: Any) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError("required token profile text field is empty")
    return text


def _clean_text(value: Any) -> str:
    return postgres_safe_text(value)


def _sanitize_json(value: Any) -> Any:
    stable_current_payload_hash({"json": value})
    return postgres_safe_json(value)


def _required_json_list(row: dict[str, Any], field: str) -> Any:
    if field not in row or row[field] is None:
        raise ValueError(f"token_profile_current_repository_required:{field}")
    value = row[field]
    if not isinstance(value, list):
        raise ValueError(f"token_profile_current_repository_invalid:{field}")
    return _sanitize_json(list(value))


def _required_json_mapping(row: dict[str, Any], field: str) -> Any:
    if field not in row or row[field] is None:
        raise ValueError(f"token_profile_current_repository_required:{field}")
    value = row[field]
    if not isinstance(value, Mapping):
        raise ValueError(f"token_profile_current_repository_invalid:{field}")
    return _sanitize_json(dict(value))


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_profile_current_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("token_profile_current_repository_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("token_profile_current_repository_rowcount_invalid")
    return rowcount


def _single_returning_changed(cursor: Any, row: Any | None) -> bool:
    count = _cursor_rowcount(cursor)
    if count not in (0, 1):
        raise TypeError("token_profile_current_repository_rowcount_invalid")
    if count != (1 if row is not None else 0):
        raise TypeError("token_profile_current_repository_rowcount_invalid")
    return row is not None and bool(row.get("changed", True))


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_profile_current_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_profile_current_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())
