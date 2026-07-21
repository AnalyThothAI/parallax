from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from parallax.domains.asset_market.repositories.token_profile_current_repository import (
    TokenProfileCurrentRepository,
)

_ROWCOUNT_FROM_RESULT = object()


def test_current_for_targets_empty_input_returns_empty_dict_without_db_call():
    conn = _Conn(rows=[])

    assert TokenProfileCurrentRepository(conn).current_for_targets([]) == {}
    assert conn.sqls == []


def test_current_for_targets_queries_pairs_and_keys_rows_by_target():
    conn = _Conn(
        rows=[
            {
                "target_type": "Asset",
                "target_id": "asset:abc",
                "status": "ready",
            }
        ]
    )

    rows = TokenProfileCurrentRepository(conn).current_for_targets(
        [("Asset", "asset:abc"), ("Asset", "asset:abc"), ("CexToken", "cex_token:BTC")]
    )

    assert rows == {("Asset", "asset:abc"): {"target_type": "Asset", "target_id": "asset:abc", "status": "ready"}}
    assert "unnest(%s::text[], %s::text[])" in conn.sqls[-1]
    assert conn.params[-1] == (["Asset", "CexToken"], ["asset:abc", "cex_token:BTC"])


def test_upsert_current_sanitizes_text_and_json_payloads():
    conn = _Conn(rows=[{"changed": True}])

    TokenProfileCurrentRepository(conn).upsert_current(
        {
            "target_type": "Asset",
            "target_id": "asset:abc",
            "status": "ready",
            "profile_provider": "okx_dex_evidence",
            "source_kind": "asset_identity_evidence",
            "source_ref": "okx\x00-1",
            "symbol": "ABC\x00",
            "name": "",
            "logo_url": "/api/token-images/image-okx",
            "logo_image_id": "image-okx",
            "logo_source_provider": "okx_dex_evidence",
            "logo_source_url_hash": "hash-okx",
            "quality_flags_json": ["invalid\x00_logo"],
            "source_payload_json": {"tokenLogoUrl\x00": "https://okx.example/logo.png"},
            "observed_at_ms": 1_000,
            "computed_at_ms": 2_000,
        }
    )

    params = conn.params[-1]
    assert params[5] == "okx-1"
    assert params[6] == "ABC"
    assert params[7] is None
    assert params[8] == "/api/token-images/image-okx"
    assert params[9] == "image-okx"
    assert params[10] == "okx_dex_evidence"
    assert params[11] == "hash-okx"
    assert isinstance(params[20], Jsonb)
    assert isinstance(params[21], Jsonb)
    assert "logo_image_id" in conn.sqls[-1]
    assert "logo_source_provider" in conn.sqls[-1]
    assert "logo_source_url_hash" in conn.sqls[-1]
    assert conn.transaction_commits == 0
    assert conn.manual_commits == 0
    assert conn.sql_depths == [0]


@pytest.mark.parametrize(
    ("patch", "error"),
    [
        (
            {"quality_flags_json": None},
            "token_profile_current_repository_required:quality_flags_json",
        ),
        (
            {"source_payload_json": None},
            "token_profile_current_repository_required:source_payload_json",
        ),
        (
            {"quality_flags_json": {"flag": "legacy"}},
            "token_profile_current_repository_invalid:quality_flags_json",
        ),
        (
            {"source_payload_json": ["legacy"]},
            "token_profile_current_repository_invalid:source_payload_json",
        ),
        (
            {
                "quality_flags_json": None,
                "source_payload_json": None,
                "quality_flags": [],
                "source_payload": {},
            },
            "token_profile_current_repository_required:quality_flags_json",
        ),
    ],
)
def test_upsert_current_requires_formal_json_payload_fields_before_sql(patch, error):
    conn = _Conn(rows=[{"changed": True}])
    row = {**_current_row(), **patch}

    with pytest.raises(ValueError, match=error):
        TokenProfileCurrentRepository(conn).upsert_current(row)

    assert conn.sqls == []


def test_upsert_current_rejects_legacy_quality_and_source_payload_aliases_before_sql():
    conn = _Conn(rows=[{"changed": True}])
    row = _current_row()
    row.pop("quality_flags_json")
    row.pop("source_payload_json")
    row["quality_flags"] = []
    row["source_payload"] = {}

    with pytest.raises(ValueError, match="token_profile_current_repository_required:quality_flags_json"):
        TokenProfileCurrentRepository(conn).upsert_current(row)

    assert conn.sqls == []


def test_upsert_current_does_not_require_or_own_a_transaction():
    conn = _NoTransactionConn(rows=[])

    assert TokenProfileCurrentRepository(conn).upsert_current(_current_row()) is False
    assert len(conn.sqls) == 1
    assert conn.manual_commits == 0
    assert conn.sql_depths == [0]


def test_upsert_current_returning_changed_requires_cursor_rowcount():
    conn = _Conn(rows=[{"changed": True}], omit_rowcount=True)

    with pytest.raises(TypeError, match="token_profile_current_repository_rowcount_invalid"):
        TokenProfileCurrentRepository(conn).upsert_current(_current_row())


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 2])
def test_upsert_current_returning_changed_rejects_invalid_cursor_rowcount(rowcount):
    conn = _Conn(rows=[{"changed": True}], rowcount=rowcount)

    with pytest.raises(TypeError, match="token_profile_current_repository_rowcount_invalid"):
        TokenProfileCurrentRepository(conn).upsert_current(_current_row())


@pytest.mark.parametrize(
    ("rowcount", "rows"),
    [
        (0, [{"changed": True}]),
        (1, []),
    ],
)
def test_upsert_current_returning_changed_rejects_rowcount_returning_mismatch(rowcount, rows):
    conn = _Conn(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match="token_profile_current_repository_rowcount_invalid"):
        TokenProfileCurrentRepository(conn).upsert_current(_current_row())


def _current_row() -> dict:
    return {
        "target_type": "Asset",
        "target_id": "asset:abc",
        "status": "ready",
        "profile_provider": "okx_dex_evidence",
        "source_kind": "asset_identity_evidence",
        "source_ref": "okx-1",
        "symbol": "ABC",
        "quality_flags_json": [],
        "source_payload_json": {},
        "computed_at_ms": 2_000,
    }


class _Conn:
    def __init__(
        self,
        *,
        rows: list[dict],
        rowcount: object = _ROWCOUNT_FROM_RESULT,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.sqls: list[str] = []
        self.params: list[tuple] = []
        self.sql_depths: list[int] = []
        self.manual_commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        self.params.append(tuple(params or ()))
        self.sql_depths.append(self.transaction_depth)
        return _Result(self.rows, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)

    def commit(self) -> None:
        self.manual_commits += 1

    def transaction(self):
        return _Transaction(self)


class _NoTransactionConn(_Conn):
    transaction = None


class _Result:
    def __init__(
        self,
        rows: list[dict],
        *,
        rowcount: object = _ROWCOUNT_FROM_RESULT,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        if not omit_rowcount:
            self.rowcount = len(rows) if rowcount is _ROWCOUNT_FROM_RESULT else rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Transaction:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args) -> bool:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False
