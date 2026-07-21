from __future__ import annotations

from types import SimpleNamespace

import pytest

from parallax.platform.db.write_contract import expect_mutation_count, mutation_count, returning_mutation_count


def test_mutation_count_requires_nonnegative_integer_evidence() -> None:
    assert mutation_count(SimpleNamespace(rowcount=2), error_code="write_count_invalid") == 2
    with pytest.raises(TypeError, match="write_count_invalid"):
        mutation_count(SimpleNamespace(rowcount=-1), error_code="write_count_invalid")


def test_expect_mutation_count_enforces_cas_cardinality() -> None:
    assert expect_mutation_count(SimpleNamespace(rowcount=1), expected=1, error_code="cas_invalid") == 1
    with pytest.raises(TypeError, match="cas_invalid"):
        expect_mutation_count(SimpleNamespace(rowcount=0), expected=1, error_code="cas_invalid")


def test_returning_mutation_count_matches_payload_presence() -> None:
    assert returning_mutation_count(SimpleNamespace(rowcount=0), None, error_code="returning_invalid") == 0
    with pytest.raises(TypeError, match="returning_invalid"):
        returning_mutation_count(SimpleNamespace(rowcount=1), None, error_code="returning_invalid")
