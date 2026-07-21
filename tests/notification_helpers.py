from __future__ import annotations

from typing import Any


def insert_notification_row(repository: Any, **kwargs: Any) -> dict[str, Any]:
    outcome = repository.insert_notification_with_outcome(**kwargs)
    if not outcome.created or outcome.row is None:
        raise AssertionError("notification_fixture_expected_new_row")
    return outcome.row
