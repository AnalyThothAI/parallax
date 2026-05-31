from __future__ import annotations

SOURCE_QUALITY_WINDOWS_MS: dict[str, int] = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
}


def window_ms_for_label(window: str) -> int:
    normalized = str(window or "").strip().lower()
    if normalized not in SOURCE_QUALITY_WINDOWS_MS:
        allowed = ", ".join(SOURCE_QUALITY_WINDOWS_MS)
        raise ValueError(f"unsupported news source quality window: {normalized or '<empty>'}; allowed: {allowed}")
    return SOURCE_QUALITY_WINDOWS_MS[normalized]


__all__ = ["SOURCE_QUALITY_WINDOWS_MS", "window_ms_for_label"]
