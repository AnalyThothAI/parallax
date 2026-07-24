from __future__ import annotations


def cancellation_reason(exc: BaseException) -> str | None:
    reason = getattr(exc, "cancellation_reason", None)
    if isinstance(reason, str) and reason:
        return reason
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, str) and arg:
            return arg
    return None
