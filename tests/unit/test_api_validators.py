from __future__ import annotations

import pytest

from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.validators import _limit, _positive_limit


def test_api_limit_allows_zero_and_caps_upper_bound() -> None:
    assert _limit(0, maximum=50) == 0
    assert _limit(75, maximum=50) == 50


@pytest.mark.parametrize("value", [-1, True, object()])
def test_api_limit_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ApiBadRequest) as exc:
        _limit(value)  # type: ignore[arg-type]

    assert exc.value.error == "invalid_limit"
    assert exc.value.field == "limit"


def test_api_positive_limit_rejects_zero_with_field_specific_error() -> None:
    with pytest.raises(ApiBadRequest) as exc:
        _positive_limit(0, field="posts_limit")

    assert exc.value.error == "invalid_limit"
    assert exc.value.field == "posts_limit"
