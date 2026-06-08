from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
)

CURRENT_NEWS_ITEM_BRIEF_PROMPT_VERSION = NEWS_ITEM_BRIEF_PROMPT_VERSION
CURRENT_NEWS_ITEM_BRIEF_SCHEMA_VERSION = NEWS_ITEM_BRIEF_SCHEMA_VERSION
CURRENT_NEWS_ITEM_BRIEF_VALIDATOR_VERSION = NEWS_ITEM_BRIEF_VALIDATOR_VERSION
CURRENT_NEWS_ITEM_BRIEF_CONTRACT = {
    "prompt_version": CURRENT_NEWS_ITEM_BRIEF_PROMPT_VERSION,
    "schema_version": CURRENT_NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    "validator_version": CURRENT_NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
}

_SQL_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_current_news_item_brief_contract(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    return (
        str(row.get("prompt_version") or "") == CURRENT_NEWS_ITEM_BRIEF_PROMPT_VERSION
        and str(row.get("schema_version") or "") == CURRENT_NEWS_ITEM_BRIEF_SCHEMA_VERSION
        and str(row.get("validator_version") or "") == CURRENT_NEWS_ITEM_BRIEF_VALIDATOR_VERSION
    )


def current_news_item_brief_sql_predicate(alias: str = "current_brief") -> str:
    if not _SQL_ALIAS_RE.fullmatch(alias):
        raise ValueError(f"invalid SQL alias for news item brief contract: {alias!r}")
    return (
        f"{alias}.prompt_version = {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_PROMPT_VERSION)}"
        f" AND {alias}.schema_version = {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_SCHEMA_VERSION)}"
        f" AND {alias}.validator_version = {_sql_literal(CURRENT_NEWS_ITEM_BRIEF_VALIDATOR_VERSION)}"
    )


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"
