from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery


def test_token_profile_source_query_has_no_broad_target_discovery_entrypoint():
    query = TokenProfileSourceQuery(_Conn(rows=[]))

    assert not hasattr(query, "recent" + "_profile_targets")


def test_gmgn_openapi_profiles_reads_ready_asset_profile_source_only():
    conn = _Conn(rows=[{"asset_id": "asset:abc", "status": "ready"}])

    rows = TokenProfileSourceQuery(conn).gmgn_openapi_profiles(["asset:abc"])

    assert rows == {"asset:abc": {"asset_id": "asset:abc", "status": "ready"}}
    sql = conn.sqls[-1]
    assert "FROM asset_profiles" in sql
    assert "provider = 'gmgn_dex_profile'" in sql
    assert "status = 'ready'" in sql


def test_binance_web3_profiles_reads_ready_asset_profile_source_only():
    conn = _Conn(rows=[{"asset_id": "asset:abc", "status": "ready", "provider": "binance_web3_profile"}])

    rows = TokenProfileSourceQuery(conn).binance_web3_profiles(["asset:abc"])

    assert rows == {"asset:abc": {"asset_id": "asset:abc", "status": "ready", "provider": "binance_web3_profile"}}
    sql = conn.sqls[-1]
    assert "FROM asset_profiles" in sql
    assert "provider = 'binance_web3_profile'" in sql
    assert "status = 'ready'" in sql


def test_gmgn_stream_profiles_reads_exact_payload_metadata_without_requiring_icons():
    conn = _Conn(
        rows=[
            {
                "asset_id": "asset:abc",
                "provider": "gmgn",
                "evidence_kind": "gmgn_payload_exact",
                "evidence_id": "gmgn-1",
                "raw_payload_json": {"s": "GMGN"},
            }
        ]
    )

    rows = TokenProfileSourceQuery(conn).gmgn_stream_profiles(["asset:abc"])

    assert rows["asset:abc"]["evidence_id"] == "gmgn-1"
    sql = conn.sqls[-1]
    params = conn.params[-1]
    assert "FROM asset_identity_evidence" in sql
    assert "provider = %s" in sql
    assert "evidence_kind = %s" in sql
    assert "raw_payload_json ? %s" not in sql
    assert params == ("gmgn", "gmgn_payload_exact", ["asset:abc"])


def test_okx_dex_profiles_reads_exact_address_metadata_without_requiring_logos():
    conn = _Conn(
        rows=[
            {
                "asset_id": "asset:abc",
                "provider": "okx",
                "evidence_kind": "okx_dex_exact_address",
                "evidence_id": "okx-1",
                "raw_payload_json": {"tokenSymbol": "OKX"},
            }
        ]
    )

    rows = TokenProfileSourceQuery(conn).okx_dex_profiles(["asset:abc"])

    assert rows["asset:abc"]["evidence_id"] == "okx-1"
    sql = conn.sqls[-1]
    params = conn.params[-1]
    assert "FROM asset_identity_evidence" in sql
    assert "provider = %s" in sql
    assert "evidence_kind = %s" in sql
    assert "raw_payload_json ? %s" not in sql
    assert params == ("okx", "okx_dex_exact_address", ["asset:abc"])
    assert "okx_dex_symbol_candidate" not in sql


def test_cex_token_profiles_reads_binance_source_cache_without_requiring_logo_columns():
    conn = _Conn(
        rows=[
            {
                "cex_token_id": "cex_token:BTC",
                "base_symbol": "BTC",
                "provider": "binance_cex_profile",
                "logo_url": "https://bin.bnbstatic.com/btc.png",
                "source_ref": "binance_marketing_symbol_list:BTC",
            }
        ]
    )

    rows = TokenProfileSourceQuery(conn).cex_token_profiles(["cex_token:BTC", "cex_token:BTC"])

    assert rows == {
        "cex_token:BTC": {
            "cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source_ref": "binance_marketing_symbol_list:BTC",
        }
    }
    sql = conn.sqls[-1]
    params = conn.params[-1]
    assert "FROM cex_token_profiles" in sql
    assert "JOIN cex_tokens" in sql
    assert "provider = 'binance_cex_profile'" in sql
    assert "logo_url IS NOT NULL" not in sql
    assert "cex_tokens.status IN ('candidate', 'canonical')" in sql
    assert "cex_tokens.logo_url" not in sql
    assert "logo_source" not in sql
    assert params == (["cex_token:BTC"],)


class _Conn:
    def __init__(self, *, rows: list[dict]) -> None:
        self.rows = rows
        self.sqls: list[str] = []
        self.params: list[tuple] = []

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        self.params.append(tuple(params or ()))
        return _Result(self.rows)


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows
