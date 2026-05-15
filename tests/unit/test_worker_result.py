from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult


def test_worker_result_defaults_to_zero_counts_and_empty_notes() -> None:
    result = WorkerResult()

    assert is_dataclass(result)
    assert result.processed == 0
    assert result.failed == 0
    assert result.dead == 0
    assert result.skipped == 0
    assert result.notes == {}


def test_worker_result_is_frozen_and_slots_backed() -> None:
    notes: dict[str, Any] = {"reason": "caught_up"}
    result = WorkerResult(processed=2, failed=1, dead=0, skipped=3, notes=notes)

    with pytest.raises(FrozenInstanceError):
        result.processed = 3
    assert not hasattr(result, "__dict__")
    assert result.notes == {"reason": "caught_up"}
