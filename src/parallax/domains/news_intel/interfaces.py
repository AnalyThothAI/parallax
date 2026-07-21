from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsNotificationCandidate:
    row_id: str
    news_item_id: str
    representative_news_item_id: str
    story_key: str
    latest_at_ms: int
    headline: str | None
    source_domain: str
    canonical_url: str | None
    direction: str
    decision_class: str
    title_zh: str | None
    projected_title_zh: str | None
    summary_zh: str | None
    affected_symbols: tuple[str, ...]
    token_symbols: tuple[str, ...]
    external_push_ready: bool | None
    external_push_basis: str | None
    external_push_block_reason: str | None

    @classmethod
    def from_repository_row(cls, row: Mapping[str, Any]) -> NewsNotificationCandidate:
        return cls(
            row_id=_required_text(row, "row_id"),
            news_item_id=_required_text(row, "news_item_id"),
            representative_news_item_id=_required_text(row, "representative_news_item_id"),
            story_key=_required_text(row, "story_key"),
            latest_at_ms=_required_positive_int(row, "latest_at_ms"),
            headline=_optional_text(row, "headline"),
            source_domain=_required_text(row, "source_domain"),
            canonical_url=_optional_text(row, "canonical_url"),
            direction=_required_text(row, "direction"),
            decision_class=_required_text(row, "decision_class"),
            title_zh=_optional_text(row, "title_zh"),
            projected_title_zh=_optional_text(row, "projected_title_zh"),
            summary_zh=_optional_text(row, "summary_zh"),
            affected_symbols=_symbols(row, "affected_entities"),
            token_symbols=_symbols(row, "token_impacts"),
            external_push_ready=_optional_bool(row, "external_push_ready"),
            external_push_basis=_optional_text(row, "external_push_basis"),
            external_push_block_reason=_optional_text(row, "external_push_block_reason"),
        )


def _required_text(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_notification_candidate_{field_name}_required")
    return value.strip()


def _optional_text(row: Mapping[str, Any], field_name: str) -> str | None:
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"news_notification_candidate_{field_name}_invalid")
    return value.strip() or None


def _required_positive_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"news_notification_candidate_{field_name}_required")
    return value


def _required_bool(row: Mapping[str, Any], field_name: str) -> bool:
    value = row.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_notification_candidate_{field_name}_required")
    return value


def _optional_bool(row: Mapping[str, Any], field_name: str) -> bool | None:
    if row.get(field_name) is None:
        return None
    return _required_bool(row, field_name)


def _symbols(row: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    values = row.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"news_notification_candidate_{field_name}_required")
    symbols: list[str] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError(f"news_notification_candidate_{field_name}_invalid")
        raw_symbol = value.get("symbol") or value.get("target_symbol")
        if raw_symbol is None:
            continue
        if not isinstance(raw_symbol, str):
            raise ValueError(f"news_notification_candidate_{field_name}_symbol_invalid")
        symbol = raw_symbol.strip().lstrip("$").upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return tuple(symbols)


__all__ = ["NewsNotificationCandidate"]
