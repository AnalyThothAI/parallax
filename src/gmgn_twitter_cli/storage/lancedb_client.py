from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any

import lancedb
import pyarrow as pa
from filelock import FileLock
from lancedb.rerankers import RRFReranker

from .lancedb_schema import ensure_required_tables, table_schema

Row = dict[str, Any]


class LanceDbClient:
    def __init__(self, path: str | Path, *, embedding_dim: int | None = 1024):
        self.root = Path(path).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.root))
        self._embedding_dim = int(embedding_dim or _existing_embedding_dim(self._db) or 1024)
        self._known_tables: set[str] = set()
        self._catalog_mutex = RLock()
        self._table_mutexes: dict[str, RLock] = {}
        self._table_lock_creation_mutex = RLock()
        self._catalog_file_lock = FileLock(str(self.root / ".catalog.lock"), timeout=10)
        ensure_required_tables(self, embedding_dim=self._embedding_dim)

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def create_if_missing(self, table_name: str, *, embedding_dim: int | None = None) -> None:
        if embedding_dim is not None and int(embedding_dim) != self._embedding_dim:
            raise ValueError(
                "client embedding_dim "
                f"{self._embedding_dim} does not match requested embedding_dim {int(embedding_dim)}"
            )
        with self._catalog_lock():
            if table_name in self._known_tables:
                if table_name == "twitter_events":
                    self._validate_embedding_schema(table_name)
                return
            names = set(self.table_names())
            if table_name not in names:
                self._db.create_table(table_name, schema=table_schema(table_name, embedding_dim=self._embedding_dim))
            elif table_name == "twitter_events":
                self._validate_embedding_schema(table_name)
            self._known_tables.add(table_name)

    def table_schema(self, table_name: str) -> pa.Schema:
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            return table.schema

    def table_names(self) -> list[str]:
        listed = self._db.list_tables()
        names = sorted(str(name) for name in getattr(listed, "tables", listed))
        self._known_tables.update(names)
        return names

    def insert(self, table_name: str, row: Row) -> None:
        schema = self.table_schema(table_name)
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            table.add(_rows_to_arrow_payload([_normalize_row(row, schema=schema)], schema=schema))

    def insert_if_missing(self, table_name: str, *, row: Row, key_fields: tuple[str, ...]) -> bool:
        if not key_fields:
            raise ValueError("key_fields is required")
        schema = self.table_schema(table_name)
        normalized = _normalize_row(row, schema=schema)
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            filters = {key: normalized.get(key) for key in key_fields}
            if table.search().where(_filters_to_where(filters)).limit(1).to_list():
                return False
            table.add(_rows_to_arrow_payload([normalized], schema=schema))
            return True

    def upsert(self, table_name: str, *, key_fields: tuple[str, ...], row: Row) -> None:
        if not key_fields:
            raise ValueError("key_fields is required")
        schema = self.table_schema(table_name)
        normalized = _normalize_row(row, schema=schema)
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            key = key_fields[0] if len(key_fields) == 1 else list(key_fields)
            (
                table.merge_insert(key)
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(_rows_to_arrow_payload([normalized], schema=schema))
            )

    def get_one(self, table_name: str, **filters: Any) -> Row | None:
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            query = table.search()
            where = _filters_to_where(filters)
            if where:
                query = query.where(where)
            rows = query.limit(1).to_list()
        return _decode_row(rows[0]) if rows else None

    def query_where(
        self,
        table_name: str,
        *,
        where: str | None = None,
        limit: int | None = None,
        order_by: str | None = None,
        descending: bool = False,
    ) -> list[Row]:
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            query = table.search()
            if where and where.strip():
                query = query.where(where.strip())
            if limit is not None and order_by is None:
                query = query.limit(max(0, int(limit)))
            rows = [_decode_row(row) for row in query.to_list()]
        if order_by is not None:
            rows.sort(key=lambda item: item.get(order_by) or 0, reverse=descending)
            if limit is not None:
                rows = rows[: max(0, int(limit))]
        return [dict(row) for row in rows]

    def query_in(self, table_name: str, *, column: str, values: list[Any]) -> list[Row]:
        normalized: list[Any] = []
        seen: set[str] = set()
        for value in values:
            marker = repr(value)
            if value is None or marker in seen:
                continue
            seen.add(marker)
            normalized.append(value)
        if not normalized:
            return []

        rows: list[Row] = []
        for chunk in _chunked(normalized, size=200):
            rows.extend(self.query_where(table_name, where=_in_clause(column=column, values=chunk)))
        return rows

    def count_where(self, table_name: str, *, where: str | None = None) -> int:
        return len(self.query_where(table_name, where=where))

    def create_scalar_index(
        self,
        *,
        table_name: str,
        column: str,
        replace: bool = False,
        index_type: str = "BTREE",
    ) -> None:
        with self._catalog_lock():
            table = self._open_table(table_name)
            table.create_scalar_index(column, replace=replace, index_type=index_type)

    def create_fts_index(
        self,
        *,
        table_name: str,
        field_names: str | list[str],
        replace: bool = False,
        **kwargs: Any,
    ) -> None:
        with self._catalog_lock():
            table = self._open_table(table_name)
            table.create_fts_index(field_names, replace=replace, **kwargs)

    def create_vector_index(
        self,
        *,
        table_name: str,
        vector_column: str,
        metric: str = "cosine",
        replace: bool = False,
    ) -> None:
        with self._catalog_lock():
            table = self._open_table(table_name)
            table.create_index(metric=metric, vector_column_name=vector_column, replace=replace)

    def hybrid_search(
        self,
        *,
        table_name: str,
        vector: list[float],
        text: str,
        vector_column: str,
        text_columns: tuple[str, ...],
        where: str | None = None,
        limit: int = 20,
    ) -> list[Row]:
        if not vector or not text.strip():
            return []
        with self._table_lock(table_name):
            table = self._open_table(table_name)
            query = (
                table.search(
                    query_type="hybrid",
                    vector_column_name=vector_column,
                    fts_columns=list(text_columns),
                )
                .vector([float(value) for value in vector])
                .text(text.strip())
            )
            if where and where.strip():
                query = query.where(where.strip(), prefilter=True)
            rows = query.rerank(RRFReranker()).limit(max(1, int(limit))).to_list()
        return [_decode_row(row) for row in rows]

    def close(self) -> None:
        return None

    def _open_table(self, table_name: str):
        if table_name not in self._known_tables:
            self.create_if_missing(table_name)
        return self._db.open_table(table_name)

    def _validate_embedding_schema(self, table_name: str) -> None:
        table = self._db.open_table(table_name)
        if "embedding" not in table.schema.names:
            return
        list_size = table.schema.field("embedding").type.list_size
        if int(list_size) != self._embedding_dim:
            raise ValueError(
                f"LanceDB embedding dimension mismatch: table={list_size} settings={self._embedding_dim}"
            )

    @contextmanager
    def _catalog_lock(self):
        already_owned = getattr(self._catalog_mutex, "_is_owned", lambda: False)()
        with self._catalog_mutex:
            if already_owned:
                yield
                return
            with self._catalog_file_lock:
                yield

    def _get_table_mutex(self, table_name: str) -> RLock:
        with self._table_lock_creation_mutex:
            mutex = self._table_mutexes.get(table_name)
            if mutex is None:
                mutex = RLock()
                self._table_mutexes[table_name] = mutex
            return mutex

    @contextmanager
    def _table_lock(self, table_name: str):
        mutex = self._get_table_mutex(table_name)
        file_lock = FileLock(str(self.root / f".{table_name}.lock"), timeout=10)
        already_owned = getattr(mutex, "_is_owned", lambda: False)()
        with mutex:
            if already_owned:
                yield
                return
            with file_lock:
                yield


def build_lancedb_client(path: str | Path | None = None, *, embedding_dim: int | None = None) -> LanceDbClient:
    root = path or tempfile.mkdtemp(prefix="gmgn-twitter-lancedb-")
    return LanceDbClient(root, embedding_dim=embedding_dim)


def _normalize_row(row: Row, *, schema: pa.Schema) -> Row:
    normalized: Row = {}
    for field in schema:
        value = row.get(field.name)
        normalized[field.name] = _coerce_value(field.type, value)
    return normalized


def _existing_embedding_dim(db: Any) -> int | None:
    try:
        listed = db.list_tables()
        names = set(str(name) for name in getattr(listed, "tables", listed))
        if "twitter_events" not in names:
            return None
        schema = db.open_table("twitter_events").schema
        if "embedding" not in schema.names:
            return None
        return int(schema.field("embedding").type.list_size)
    except Exception:  # noqa: BLE001
        return None


def _coerce_value(arrow_type: pa.DataType, value: Any) -> Any:
    if value is None:
        return None
    if pa.types.is_fixed_size_list(arrow_type):
        if isinstance(value, str):
            value = json.loads(value)
        return [float(item) for item in value]
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)
    if pa.types.is_integer(arrow_type):
        return int(value)
    if pa.types.is_floating(arrow_type):
        return float(value)
    if pa.types.is_boolean(arrow_type):
        return bool(value)
    return value


def _rows_to_arrow_payload(rows: list[Row], *, schema: pa.Schema) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=schema)


def _decode_row(row: Row) -> Row:
    out: Row = {}
    for key, value in row.items():
        if isinstance(value, dict) and "values" in value:
            out[key] = list(value["values"])
        else:
            out[key] = value
    return out


def _filters_to_where(filters: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in filters.items():
        if value is None:
            parts.append(f"{key} IS NULL")
        elif isinstance(value, bool):
            parts.append(f"{key} = {'TRUE' if value else 'FALSE'}")
        elif isinstance(value, (int, float)):
            parts.append(f"{key} = {value}")
        else:
            parts.append(f"{key} = '{_escape_sql_literal(str(value))}'")
    return " AND ".join(parts)


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _in_clause(*, column: str, values: list[Any]) -> str:
    if not values:
        raise ValueError("values is required")
    parts: list[str] = []
    for value in values:
        if isinstance(value, bool):
            parts.append("TRUE" if value else "FALSE")
        elif isinstance(value, (int, float)):
            parts.append(str(value))
        else:
            parts.append(f"'{_escape_sql_literal(str(value))}'")
    return f"{column} IN ({', '.join(parts)})"


def _chunked(values: list[Any], *, size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
