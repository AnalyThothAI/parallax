from __future__ import annotations

WORKER_HARD_TIMEOUT_CANCEL_REASON = "worker_hard_timeout"


def cancellation_reason(exc: BaseException) -> str | None:
    reason = getattr(exc, "cancellation_reason", None)
    if isinstance(reason, str) and reason:
        return reason
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, str) and arg:
            return arg
    return None


def is_worker_hard_timeout_cancelled(exc: BaseException) -> bool:
    return cancellation_reason(exc) == WORKER_HARD_TIMEOUT_CANCEL_REASON
