from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.platform import current_read_model_payload_hash

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
        return current_read_model_payload_hash.stable_current_payload_hash(payload)

    def changed_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        existing_hashes: Mapping[tuple[Any, ...], str | None],
    ) -> list[dict[str, Any]]:
        _validate_row_batch(rows)
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
        invalid_hash_values = tuple(
            (identity, value)
            for identity, value in existing_hashes.items()
            if value is not None and type(value) is not str
        )
        if invalid_hash_values:
            raise ValueError(f"current read model existing hash values must be strings or None: {invalid_hash_values}")
        malformed_hash_values = tuple(
            (identity, value)
            for identity, value in existing_hashes.items()
            if value is not None and not _is_payload_hash(value)
        )
        if malformed_hash_values:
            raise ValueError(
                "current read model existing hash values must be sha256 payload hashes: "
                f"{malformed_hash_values}"
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


def _validate_row_batch(rows: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(rows, Sequence):
        raise ValueError(f"current read model rows must be sequence: {rows}")
    if isinstance(rows, Mapping | str | bytes):
        raise ValueError(f"current read model rows must be sequence: {rows}")


def _validate_row_columns(row: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping):
        raise ValueError(f"current read model row must be mapping: {row}")
    non_string_columns = tuple(column for column in row if type(column) is not str)
    if non_string_columns:
        raise ValueError(f"current read model row has non-string columns: {non_string_columns}")


def _is_payload_hash(value: str) -> bool:
    if not value.startswith(current_read_model_payload_hash.PAYLOAD_HASH_PREFIX):
        return False
    digest = value[len(current_read_model_payload_hash.PAYLOAD_HASH_PREFIX) :]
    return len(digest) == current_read_model_payload_hash.PAYLOAD_HASH_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in digest
    )
