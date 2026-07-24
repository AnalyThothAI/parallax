from __future__ import annotations

import pytest

from tests.support.query_contract import assert_query_contract


def test_query_contract_asserts_semantic_sql_without_alias_coupling() -> None:
    sql = """
        WITH requested AS (SELECT unnest(%s::date[]) AS session_date)
        SELECT requested.session_date, publications.artifact_hash
          FROM requested
          LEFT JOIN macro_research_publications AS publications
            ON publications.session_date = requested.session_date
           AND publications.workflow_version = %s
         WHERE publications.artifact_hash IS NOT NULL
    """

    assert_query_contract(
        sql,
        params=(["2026-07-23"], "deepagents_macro_research_v2"),
        required_tables=("macro_research_publications",),
        forbidden_tables=("macro_observations",),
        required_predicates=("workflow_version = %s", "artifact_hash is not null"),
        forbidden_fragments=("row_number() over",),
        expected_params=(["2026-07-23"], "deepagents_macro_research_v2"),
    )


def test_query_contract_reports_forbidden_tables_with_word_boundaries() -> None:
    sql = """
        SELECT *
          FROM macro_research_publications
          JOIN macro_observations ON true
    """

    with pytest.raises(AssertionError, match="forbidden table"):
        assert_query_contract(
            sql,
            required_tables=("macro_research_publications",),
            forbidden_tables=("macro_observations",),
        )
