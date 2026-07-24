from __future__ import annotations

from typing import Any


def required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(error_code)
    return int(value)


def required_nonnegative_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(error_code)
    return int(value)


__all__ = ["required_nonnegative_int", "required_positive_int"]
