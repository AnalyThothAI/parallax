from __future__ import annotations

from typing import Any


def narrative_bulk_analysis_enabled(settings: Any) -> bool:
    workers = getattr(settings, "workers", None)
    return bool(
        getattr(settings, "narrative_intel_configured", False)
        and _worker_enabled(workers, "narrative_admission")
        and _worker_enabled(workers, "mention_semantics")
        and _worker_enabled(workers, "token_discussion_digest")
    )


def _worker_enabled(workers: Any, key: str) -> bool:
    worker_settings = getattr(workers, key, None)
    if worker_settings is None:
        return False
    return bool(getattr(worker_settings, "enabled", True))


__all__ = ["narrative_bulk_analysis_enabled"]
