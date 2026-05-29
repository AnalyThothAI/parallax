from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    stable_generation_id,
)
from gmgn_twitter_intel.domains.token_intel.services import token_radar_projection


def test_token_radar_venue_for_rank_input_prefers_cex_target_type() -> None:
    assert token_radar_projection.token_radar_venue_for_rank_input(
        {"target_type": "CexToken", "asset_chain_id": "eip155:56"}
    ) == "cex"


def test_token_radar_venue_for_rank_input_normalizes_bsc_chain_ids() -> None:
    assert token_radar_projection.token_radar_venue_for_rank_input(
        {"target_type": "Asset", "asset_chain_id": "eip155:56"}
    ) == "bsc"
    assert token_radar_projection.token_radar_venue_for_rank_input(
        {"target_type": "Asset", "factor_snapshot_json": {"subject": {"chain": "bnb"}}}
    ) == "bsc"


def test_stable_generation_id_is_scoped_by_venue_product_key() -> None:
    row = {
        "lane": "resolved",
        "rank": 1,
        "target_type_key": "Asset",
        "identity_id": "asset-bsc-1",
        "payload_hash": "hash-1",
        "quality_status": "ready",
        "degraded_reasons_json": [],
    }

    all_generation = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="4h",
        scope="all",
        venue="all",
        rows=[row],
    )
    bsc_generation = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="4h",
        scope="all",
        venue="bsc",
        rows=[row],
    )

    assert bsc_generation != all_generation


def test_latest_current_rows_requires_venue_and_filters_server_side() -> None:
    conn = _FakeConn()

    TokenRadarRepository(conn).latest_current_rows(
        window="4h",
        scope="all",
        venue="bsc",
        limit=20,
        projection_version="token-radar-v13-social-attention",
    )

    assert "current_rows.venue = %s" in conn.sql
    assert "state.venue = current_rows.venue" in conn.sql
    assert "bsc" in conn.params


class _FakeConn:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> _FakeConn:
        self.sql = str(sql)
        self.params = params or ()
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []
