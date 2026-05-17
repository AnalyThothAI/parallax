from __future__ import annotations

from typing import Any


def sync_cex_token_icons(*, registry: Any, icon_source: Any, observed_at_ms: int) -> dict[str, Any]:
    icons_seen = 0
    icons_updated = 0
    missing_cex_tokens = 0
    affected_lookup_keys: set[str] = set()
    source_name = None

    for icon in icon_source.token_icons():
        base_symbol = _field(icon, "base_symbol")
        logo_url = _field(icon, "logo_url")
        source = _field(icon, "source") or "cex_token_icon_static"
        if not base_symbol or not logo_url:
            continue
        icons_seen += 1
        source_name = source_name or source
        row = registry.update_cex_token_icon(
            base_symbol=base_symbol,
            logo_url=logo_url,
            source=source,
            observed_at_ms=int(observed_at_ms),
            commit=False,
        )
        if row is None:
            missing_cex_tokens += 1
            continue
        icons_updated += 1
        affected_lookup_keys.update(_symbol_lookup_keys(base_symbol))

    registry.conn.commit()
    return {
        "icons_seen": icons_seen,
        "icons_updated": icons_updated,
        "missing_cex_tokens": missing_cex_tokens,
        "affected_lookup_keys": sorted(affected_lookup_keys),
        "source": source_name or "cex_token_icon_static",
    }


def _field(icon: Any, key: str) -> str | None:
    value = icon.get(key) if isinstance(icon, dict) else getattr(icon, key, None)
    text = str(value or "").strip()
    return text or None


def _symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}", f"cex_token:{normalized}"}
