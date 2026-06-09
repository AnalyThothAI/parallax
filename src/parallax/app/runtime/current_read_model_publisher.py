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
        if type(self.identity_columns) is not tuple:
            raise ValueError(f"non-tuple stable identity columns: {self.identity_columns}")
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
        if not self.payload_hash_column.strip():
            raise ValueError(f"blank current payload hash column: {self.payload_hash_column!r}")
        if self.payload_hash_column in FORBIDDEN_SERVING_IDENTITY_COLUMNS:
            raise ValueError(f"payload hash column cannot be lifecycle column: {self.payload_hash_column}")
        if self.payload_hash_column in self.identity_columns:
            raise ValueError(f"payload hash column cannot be identity column: {self.payload_hash_column}")
        if self.payload_columns is not None and type(self.payload_columns) is not tuple:
            raise ValueError(f"non-tuple current payload columns: {self.payload_columns}")
        if self.payload_columns is not None:
            non_string_payload_columns = tuple(column for column in self.payload_columns if type(column) is not str)
            if non_string_payload_columns:
                raise ValueError(f"non-string current payload columns: {non_string_payload_columns}")
            blank_payload_columns = tuple(column for column in self.payload_columns if not column.strip())
            if blank_payload_columns:
                raise ValueError(f"blank current payload columns: {blank_payload_columns}")
            duplicate_payload_columns = sorted(
                {column for column in self.payload_columns if self.payload_columns.count(column) > 1}
            )
            if duplicate_payload_columns:
                raise ValueError(f"duplicate current payload columns: {duplicate_payload_columns}")
            if self.payload_hash_column in self.payload_columns:
                raise ValueError(f"payload columns cannot include payload hash column: {self.payload_hash_column}")
            forbidden_payload_columns = sorted(set(self.payload_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS)
            if forbidden_payload_columns:
                raise ValueError(f"payload columns cannot include lifecycle columns: {forbidden_payload_columns}")

    def row_identity(self, row: Mapping[str, Any]) -> tuple[Any, ...]:
        _validate_row_columns(row)
        missing_identity_columns = tuple(column for column in self.identity_columns if column not in row)
        if missing_identity_columns:
            raise ValueError(f"current read model row missing identity columns: {missing_identity_columns}")
        null_identity_columns = tuple(column for column in self.identity_columns if row[column] is None)
        if null_identity_columns:
            raise ValueError(f"current read model row has null identity values: {null_identity_columns}")
        blank_identity_columns = tuple(
            column for column in self.identity_columns if isinstance(row[column], str) and not row[column].strip()
        )
        if blank_identity_columns:
            raise ValueError(f"current read model row has blank identity values: {blank_identity_columns}")
        return tuple(row[column] for column in self.identity_columns)

    def row_payload_hash(self, row: Mapping[str, Any]) -> str:
        _validate_row_columns(row)
        if self.payload_columns is None:
            payload = {
                key: value
                for key, value in row.items()
                if key != self.payload_hash_column and key not in FORBIDDEN_SERVING_IDENTITY_COLUMNS
            }
        else:
            missing_payload_columns = tuple(column for column in self.payload_columns if column not in row)
            if missing_payload_columns:
                raise ValueError(f"current read model row missing payload columns: {missing_payload_columns}")
            payload = {key: row[key] for key in self.payload_columns}
        return stable_current_payload_hash(payload)

    def changed_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        existing_hashes: Mapping[tuple[Any, ...], str | None],
    ) -> list[dict[str, Any]]:
        if not isinstance(existing_hashes, Mapping):
            raise ValueError(f"current read model existing hashes must be mapping: {existing_hashes}")
        non_tuple_hash_identities = tuple(identity for identity in existing_hashes if type(identity) is not tuple)
        if non_tuple_hash_identities:
            raise ValueError(f"current read model existing hash identities must be tuples: {non_tuple_hash_identities}")
        wrong_arity_hash_identities = tuple(
            identity for identity in existing_hashes if len(identity) != len(self.identity_columns)
        )
        if wrong_arity_hash_identities:
            raise ValueError(
                "current read model existing hash identity arity must match identity columns: "
                f"{wrong_arity_hash_identities}"
            )
        changed: list[dict[str, Any]] = []
        seen_identities: set[tuple[Any, ...]] = set()
        for row in rows:
            identity = self.row_identity(row)
            if identity in seen_identities:
                raise ValueError(f"current read model batch has duplicate row identities: {identity}")
            seen_identities.add(identity)
            row_hash = self.row_payload_hash(row)
            if existing_hashes.get(identity) == row_hash:
                continue
            next_row = dict(row)
            next_row[self.payload_hash_column] = row_hash
            changed.append(next_row)
        return changed


def _validate_row_columns(row: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping):
        raise ValueError(f"current read model row must be mapping: {row}")
    non_string_columns = tuple(column for column in row if type(column) is not str)
    if non_string_columns:
        raise ValueError(f"current read model row has non-string columns: {non_string_columns}")


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
