from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery


def test_recent_profile_targets_uses_current_radar_and_bounded_recent_resolutions():
    conn = _Conn(rows=[{"target_type": "Asset", "target_id": "asset:abc", "best_radar_rank": 1}])
    query = TokenProfileSourceQuery(conn)

    rows = query.recent_profile_targets(now_ms=1_700_000_100_000, limit=25)

    assert rows == [{"target_type": "Asset", "target_id": "asset:abc", "best_radar_rank": 1}]
    sql = conn.sqls[-1]
    params = conn.params[-1]
    assert "token_radar_projection_coverage" in sql
    assert "token_radar_rows" in sql
    assert "token_intent_resolutions" in sql
    assert "recent_resolution_rows AS MATERIALIZED" in sql
    assert "events.received_at_ms >= %s" in sql
    assert "ORDER BY events.received_at_ms DESC" in sql
    assert "target_type IN ('Asset', 'CexToken')" in sql
    assert "LIMIT %s" in sql
    assert params[-2] == 100
    assert params[-1] == 25


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


def test_gmgn_stream_profiles_reads_exact_payload_icons():
    conn = _Conn(
        rows=[
            {
                "asset_id": "asset:abc",
                "provider": "gmgn",
                "evidence_kind": "gmgn_payload_exact",
                "evidence_id": "gmgn-1",
                "raw_payload_json": {"i": "https://gmgn.example/icon.png"},
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
    assert "raw_payload_json ? %s" in sql
    assert params[:3] == ("gmgn", "gmgn_payload_exact", "i")


def test_okx_dex_profiles_reads_exact_address_logos_and_not_symbol_candidates():
    conn = _Conn(
        rows=[
            {
                "asset_id": "asset:abc",
                "provider": "okx",
                "evidence_kind": "okx_dex_exact_address",
                "evidence_id": "okx-1",
                "raw_payload_json": {"tokenLogoUrl": "https://okx.example/icon.png"},
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
    assert "raw_payload_json ? %s" in sql
    assert params[:3] == ("okx", "okx_dex_exact_address", "tokenLogoUrl")
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
