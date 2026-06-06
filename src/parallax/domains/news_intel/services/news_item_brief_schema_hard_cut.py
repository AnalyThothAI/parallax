from __future__ import annotations

from typing import Any

from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
)


def cleanup_news_item_brief_schema_hard_cut(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    conn = repos.conn
    params = (
        NEWS_ITEM_BRIEF_PROMPT_VERSION,
        NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    )
    stale_count = int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM news_item_agent_briefs
             WHERE COALESCE(prompt_version, '') <> %s
                OR COALESCE(schema_version, '') <> %s
                OR COALESCE(validator_version, '') <> %s
            """,
            params,
        ).fetchone()["count"]
        or 0
    )
    deleted = 0
    if execute and stale_count:
        deleted = int(
            conn.execute(
                """
                DELETE FROM news_item_agent_briefs
                 WHERE COALESCE(prompt_version, '') <> %s
                    OR COALESCE(schema_version, '') <> %s
                    OR COALESCE(validator_version, '') <> %s
                """,
                params,
            ).rowcount
            or 0
        )
    return {
        "mode": "execute" if execute else "dry_run",
        "now_ms": int(now_ms),
        "current_contract": {
            "prompt_version": NEWS_ITEM_BRIEF_PROMPT_VERSION,
            "schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            "validator_version": NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        },
        "stale_current_briefs": stale_count,
        "deleted": deleted,
    }


__all__ = ["cleanup_news_item_brief_schema_hard_cut"]
