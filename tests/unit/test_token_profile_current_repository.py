from __future__ import annotations

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.repositories.token_profile_current_repository import (
    TokenProfileCurrentRepository,
)


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
    conn = _Conn(rows=[])

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
            "logo_url": "https://okx.example/logo.png",
            "quality_flags": ["invalid\x00_logo"],
            "source_payload": {"tokenLogoUrl\x00": "https://okx.example/logo.png"},
            "observed_at_ms": 1_000,
            "computed_at_ms": 2_000,
        }
    )

    params = conn.params[-1]
    assert params[5] == "okx-1"
    assert params[6] == "ABC"
    assert params[7] is None
    assert isinstance(params[17], Jsonb)
    assert isinstance(params[18], Jsonb)
    assert conn.commits == 1


class _Conn:
    def __init__(self, *, rows: list[dict]) -> None:
        self.rows = rows
        self.sqls: list[str] = []
        self.params: list[tuple] = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        self.params.append(tuple(params or ()))
        return _Result(self.rows)

    def commit(self) -> None:
        self.commits += 1


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows
