from __future__ import annotations

import pytest

from tests.support.query_contract import assert_query_contract


def test_query_contract_asserts_semantic_sql_without_alias_coupling() -> None:
    sql = """
        WITH requested AS (SELECT unnest(%s::text[]) AS concept_key)
        SELECT requested.concept_key, COUNT(rows.observed_at) AS points
          FROM requested
          LEFT JOIN macro_observation_series_rows AS rows
            ON rows.concept_key = requested.concept_key
           AND rows.projection_version = %s
           AND rows.series_rank = 1
         GROUP BY requested.concept_key
    """

    assert_query_contract(
        sql,
        params=(["asset:spx"], "macro_regime_v4"),
        required_tables=("macro_observation_series_rows",),
        forbidden_tables=("macro_observations",),
        required_predicates=("projection_version = %s", "series_rank = 1"),
        forbidden_fragments=("row_number() over",),
        expected_params=(["asset:spx"], "macro_regime_v4"),
    )


def test_query_contract_reports_forbidden_tables_with_word_boundaries() -> None:
    sql = """
        SELECT *
          FROM macro_observation_series_rows
          JOIN macro_observations ON true
    """

    with pytest.raises(AssertionError, match="forbidden table"):
        assert_query_contract(
            sql,
            required_tables=("macro_observation_series_rows",),
            forbidden_tables=("macro_observations",),
        )
