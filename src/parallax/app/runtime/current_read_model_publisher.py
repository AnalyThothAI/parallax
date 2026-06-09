from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

FORBIDDEN_SERVING_IDENTITY_COLUMNS = frozenset(
    {
        "run_id",
        "generation_id",
        "generation",
        "snapshot_id",
        "attempt_id",
        "computed_at_ms",
        "published_at_ms",
    }
)


def stable_current_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_ready(dict(payload)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CurrentReadModelPublisher:
    identity_columns: tuple[str, ...]
    payload_hash_column: str = "payload_hash"
    payload_columns: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.identity_columns:
            raise ValueError("current read model publisher requires stable identity columns")
        non_string_identity = tuple(column for column in self.identity_columns if type(column) is not str)
        if non_string_identity:
            raise ValueError(f"non-string stable identity columns: {non_string_identity}")
        blank_identity = sorted({column for column in self.identity_columns if not column.strip()})
        if blank_identity:
            raise ValueError(f"blank stable identity columns: {blank_identity}")
        duplicate_identity = sorted(
            {column for column in self.identity_columns if self.identity_columns.count(column) > 1}
        )
        if duplicate_identity:
            raise ValueError(f"duplicate stable identity columns: {duplicate_identity}")
        forbidden_identity = sorted(set(self.identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS)
        if forbidden_identity:
            raise ValueError(
                f"current read model identity cannot include serving lifecycle columns: {forbidden_identity}"
            )
        if type(self.payload_hash_column) is not str:
            raise ValueError(f"non-string current payload hash column: {self.payload_hash_column}")
        if self.payload_columns is not None and type(self.payload_columns) is not tuple:
            raise ValueError(f"non-tuple current payload columns: {self.payload_columns}")
        if self.payload_columns is not None:
            non_string_payload_columns = tuple(column for column in self.payload_columns if type(column) is not str)
            if non_string_payload_columns:
                raise ValueError(f"non-string current payload columns: {non_string_payload_columns}")

    def row_identity(self, row: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(row[column] for column in self.identity_columns)

    def row_payload_hash(self, row: Mapping[str, Any]) -> str:
        if self.payload_columns is None:
            payload = {
                key: value
                for key, value in row.items()
                if key != self.payload_hash_column and key not in FORBIDDEN_SERVING_IDENTITY_COLUMNS
            }
        else:
            payload = {key: row.get(key) for key in self.payload_columns}
        return stable_current_payload_hash(payload)

    def changed_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        existing_hashes: Mapping[tuple[Any, ...], str | None],
    ) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for row in rows:
            row_hash = self.row_payload_hash(row)
            identity = self.row_identity(row)
            if existing_hashes.get(identity) == row_hash:
                continue
            next_row = dict(row)
            next_row[self.payload_hash_column] = row_hash
            changed.append(next_row)
        return changed


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, set | frozenset):
        return sorted(_json_ready(inner) for inner in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
