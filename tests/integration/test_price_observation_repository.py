from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import (
    PriceObservationRepository,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_latest_for_target_accepts_unbounded_age_on_postgres(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)

        observation = PriceObservationRepository(conn).latest_for_target(
            target_type="CexToken",
            target_id="cex_token:BTC",
            now_ms=1_778_000_000_000,
            max_age_ms=None,
        )
    finally:
        conn.close()

    assert observation is None
