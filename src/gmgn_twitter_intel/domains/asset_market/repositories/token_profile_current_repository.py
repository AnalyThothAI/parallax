from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json, postgres_safe_text


class TokenProfileCurrentRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_current(self, row: dict[str, Any], *, commit: bool = True) -> None:
        computed_at_ms = int(row["computed_at_ms"])
        self.conn.execute(
            """
            INSERT INTO token_profile_current(
              target_type, target_id, status, profile_provider, source_kind, source_ref,
              symbol, name, logo_url, banner_url, website_url, twitter_username,
              twitter_url, telegram_url, gmgn_url, geckoterminal_url, description,
              quality_flags_json, source_payload_json, observed_at_ms, computed_at_ms,
              updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s
            )
            ON CONFLICT(target_type, target_id) DO UPDATE SET
              status = excluded.status,
              profile_provider = excluded.profile_provider,
              source_kind = excluded.source_kind,
              source_ref = excluded.source_ref,
              symbol = excluded.symbol,
              name = excluded.name,
              logo_url = excluded.logo_url,
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
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _required_text(row.get("target_type")),
                _required_text(row.get("target_id")),
                _required_text(row.get("status")),
                _optional_text(row.get("profile_provider")),
                _required_text(row.get("source_kind")),
                _optional_text(row.get("source_ref")),
                _optional_text(row.get("symbol")),
                _optional_text(row.get("name")),
                _optional_text(row.get("logo_url")),
                _optional_text(row.get("banner_url")),
                _optional_text(row.get("website_url")),
                _optional_text(row.get("twitter_username")),
                _optional_text(row.get("twitter_url")),
                _optional_text(row.get("telegram_url")),
                _optional_text(row.get("gmgn_url")),
                _optional_text(row.get("geckoterminal_url")),
                _optional_text(row.get("description")),
                Jsonb(_sanitize_json(row.get("quality_flags_json", row.get("quality_flags", [])) or [])),
                Jsonb(_sanitize_json(row.get("source_payload_json", row.get("source_payload", {})) or {})),
                _int_or_none(row.get("observed_at_ms")),
                computed_at_ms,
                int(row.get("updated_at_ms") or computed_at_ms),
            ),
        )
        if commit:
            self.conn.commit()

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
    return postgres_safe_json(value)


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None
