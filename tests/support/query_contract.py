from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any


def assert_query_contract(
    sql: str,
    *,
    params: Sequence[Any] | None = None,
    required_tables: Sequence[str] = (),
    forbidden_tables: Sequence[str] = (),
    required_predicates: Sequence[str] = (),
    forbidden_fragments: Sequence[str] = (),
    required_locks: Sequence[str] = (),
    expected_params: Sequence[Any] | None = None,
) -> None:
    normalized = normalize_sql(sql)

    for table in required_tables:
        if not _contains_identifier(normalized, table):
            raise AssertionError(f"missing required table: {table}")

    for table in forbidden_tables:
        if _contains_identifier(normalized, table):
            raise AssertionError(f"query used forbidden table: {table}")

    for predicate in required_predicates:
        if normalize_sql(predicate) not in normalized:
            raise AssertionError(f"missing required predicate: {predicate}")

    for fragment in forbidden_fragments:
        if normalize_sql(fragment) in normalized:
            raise AssertionError(f"query used forbidden fragment: {fragment}")

    for lock in required_locks:
        if normalize_sql(lock) not in normalized:
            raise AssertionError(f"missing required lock: {lock}")

    if expected_params is not None and tuple(params or ()) != tuple(expected_params):
        raise AssertionError(f"params mismatch: expected {tuple(expected_params)!r}, got {tuple(params or ())!r}")


def normalize_sql(sql: str) -> str:
    return " ".join(str(sql).strip().lower().split())


def _contains_identifier(normalized_sql: str, identifier: str) -> bool:
    normalized_identifier = normalize_sql(identifier)
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(normalized_identifier)}(?![a-z0-9_])")
    return bool(pattern.search(normalized_sql))
