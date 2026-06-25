from __future__ import annotations

from typing import Any


def positive_worker_setting_int(settings: Any, field_name: str, *, worker_name: str) -> int:
    try:
        value = getattr(settings, field_name)
    except AttributeError as exc:
        raise RuntimeError(f"{worker_name}_{field_name}_required") from exc
    return required_positive_int(value, error_code=f"{worker_name}_{field_name}_required")


def required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(error_code)
    return int(value)


def required_nonnegative_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(error_code)
    return int(value)


__all__ = ["positive_worker_setting_int", "required_nonnegative_int", "required_positive_int"]
