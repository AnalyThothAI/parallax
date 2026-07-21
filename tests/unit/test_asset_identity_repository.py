from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_TWEET_CONTRACT_MENTION,
)
from parallax.domains.asset_market.repositories.identity_evidence_repository import (
    IdentityEvidenceRepository,
)

ASSET_ID = "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108"
ADDRESS = "0x999b49c0d1612e619a4a4f6280733184da025108"
NOW_MS = 1_779_000_000_000
_ROWCOUNT_FROM_ROWS = object()


def test_recompute_current_identity_writes_policy_result_without_source_precedence():
    conn = FakeIdentityConnection(
        evidence_rows=[
            {
                "evidence_id": "tweet-sato",
                "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                "evidence_kind": EVIDENCE_TWEET_CONTRACT_MENTION,
                "provider": "twitter",
                "lookup_mode": "tweet_mention",
                "symbol": "SATO",
                "name": None,
                "decimals": None,
                "observed_at_ms": 100,
            },
            {
                "evidence_id": "okx-exact-slop",
                "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                "evidence_kind": EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                "provider": "okx",
                "lookup_mode": "exact_address",
                "symbol": "SLOP",
                "name": "SLOP",
                "decimals": None,
                "observed_at_ms": 200,
            },
        ]
    )
    repo = IdentityEvidenceRepository(conn)

    current = repo.recompute_current_identity(
        "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
        now_ms=1_000,
    )

    assert current["canonical_symbol"] == "SLOP"
    assert current["identity_confidence"] == "provider_exact"
    assert conn.current_rows == [
        {
            "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
            "canonical_symbol": "SLOP",
            "canonical_name": "SLOP",
            "identity_confidence": "provider_exact",
            "selected_evidence_id": "okx-exact-slop",
            "reason_codes": ["SELECTED_PROVIDER_EXACT", "CONFLICTING_IDENTITY_EVIDENCE", "MENTION_NOT_CANONICAL"],
            "conflict_count": 1,
        }
    ]
    assert conn.commits == 0


def test_recompute_current_identity_reports_zero_rows_written_when_projection_unchanged():
    conn = FakeIdentityConnection(
        evidence_rows=[
            {
                "evidence_id": "okx-exact-slop",
                "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                "evidence_kind": EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                "provider": "okx",
                "lookup_mode": "exact_address",
                "symbol": "SLOP",
                "name": "SLOP",
                "decimals": None,
                "observed_at_ms": 200,
            },
        ],
        insert_changed=False,
    )

    current = IdentityEvidenceRepository(conn).recompute_current_identity(
        "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
        now_ms=2_000,
    )

    assert current["rows_written"] == 0
    assert "RETURNING true AS changed" in conn.insert_sql
    assert "asset_identity_current.canonical_symbol IS DISTINCT FROM excluded.canonical_symbol" in conn.insert_sql
    assert "asset_identity_current.updated_at_ms IS DISTINCT FROM excluded.updated_at_ms" not in conn.insert_sql
    assert "asset_identity_current.verified_at_ms IS DISTINCT FROM excluded.verified_at_ms" not in conn.insert_sql


def test_recompute_current_identity_returning_changed_requires_cursor_rowcount() -> None:
    conn = FakeIdentityConnection(
        evidence_rows=_policy_evidence_rows(),
        omit_current_rowcount=True,
    )

    with pytest.raises(TypeError, match="identity_evidence_repository_rowcount_invalid"):
        IdentityEvidenceRepository(conn).recompute_current_identity(
            ASSET_ID,
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, False, -1])
def test_recompute_current_identity_returning_changed_rejects_invalid_cursor_rowcount(
    rowcount: object,
) -> None:
    conn = FakeIdentityConnection(
        evidence_rows=_policy_evidence_rows(),
        current_rowcount=rowcount,
    )

    with pytest.raises(TypeError, match="identity_evidence_repository_rowcount_invalid"):
        IdentityEvidenceRepository(conn).recompute_current_identity(
            ASSET_ID,
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize(
    ("insert_changed", "rowcount"),
    [
        (True, 0),
        (False, 1),
        (True, 2),
    ],
)
def test_recompute_current_identity_returning_changed_rejects_rowcount_returning_mismatch(
    insert_changed: bool,
    rowcount: int,
) -> None:
    conn = FakeIdentityConnection(
        evidence_rows=_policy_evidence_rows(),
        insert_changed=insert_changed,
        current_rowcount=rowcount,
    )

    with pytest.raises(TypeError, match="identity_evidence_repository_rowcount_invalid"):
        IdentityEvidenceRepository(conn).recompute_current_identity(
            ASSET_ID,
            now_ms=NOW_MS,
        )


class FakeCursor:
    def __init__(
        self,
        rows,
        *,
        rowcount: object = _ROWCOUNT_FROM_ROWS,
        omit_rowcount: bool = False,
    ):
        self.rows = rows
        if not omit_rowcount:
            self.rowcount = len(rows) if rowcount is _ROWCOUNT_FROM_ROWS else rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeIdentityConnection:
    def __init__(
        self,
        *,
        evidence_rows,
        insert_changed: bool = True,
        current_rowcount: object = _ROWCOUNT_FROM_ROWS,
        omit_current_rowcount: bool = False,
    ):
        self.evidence_rows = evidence_rows
        self.insert_changed = insert_changed
        self.current_rowcount = current_rowcount
        self.omit_current_rowcount = omit_current_rowcount
        self.insert_sql = ""
        self.current_rows = []
        self.sql = []
        self.params = []
        self.sql_depths = []
        self.commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        if "INSERT INTO registry_assets" in text:
            return FakeCursor(
                [
                    {
                        "asset_id": ASSET_ID,
                        "chain_id": "eip155:1",
                        "token_standard": "erc20",
                        "address": ADDRESS,
                        "status": "candidate",
                        "first_seen_at_ms": NOW_MS,
                        "updated_at_ms": NOW_MS,
                    }
                ]
            )
        if "INSERT INTO asset_identity_evidence" in text:
            return FakeCursor([])
        if "FROM asset_identity_evidence" in text and "WHERE evidence_id = %s" in text:
            return FakeCursor([])
        if "FROM asset_identity_evidence" in text:
            return FakeCursor(self.evidence_rows)
        if "INSERT INTO asset_identity_current" in text:
            self.insert_sql = text
            rows = [{"changed": True}] if self.insert_changed else []
            self.current_rows.append(
                {
                    "asset_id": params[0],
                    "canonical_symbol": params[1],
                    "canonical_name": params[2],
                    "identity_confidence": params[4],
                    "selected_evidence_id": params[5],
                    "reason_codes": list(params[6].obj),
                    "conflict_count": params[7],
                }
            )
            return FakeCursor(
                rows,
                rowcount=self.current_rowcount,
                omit_rowcount=self.omit_current_rowcount,
            )
        raise AssertionError(f"unexpected SQL: {text}")

    def commit(self):
        self.commits += 1

    def transaction(self):
        return IdentityTransaction(self)


class NoTransactionIdentityConnection(FakeIdentityConnection):
    transaction = None


class IdentityTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args):
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False


def _policy_evidence_rows() -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": "tweet-sato",
            "asset_id": ASSET_ID,
            "evidence_kind": EVIDENCE_TWEET_CONTRACT_MENTION,
            "provider": "twitter",
            "lookup_mode": "tweet_mention",
            "symbol": "SATO",
            "name": None,
            "decimals": None,
            "observed_at_ms": 100,
        },
        {
            "evidence_id": "okx-exact-slop",
            "asset_id": ASSET_ID,
            "evidence_kind": EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            "provider": "okx",
            "lookup_mode": "exact_address",
            "symbol": "SLOP",
            "name": "SLOP",
            "decimals": None,
            "observed_at_ms": 200,
        },
    ]
