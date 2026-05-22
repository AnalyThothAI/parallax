from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceReconcilePayloads:
    sources: list[dict[str, Any]]
    universe_members: list[dict[str, Any]]
    expected_events: list[dict[str, Any]]
    expected_event_source_ids: list[str]


def build_source_reconcile_payloads(
    *,
    settings: Any,
    registry_lookup: Callable[[str], Mapping[str, Any] | None],
    now_ms: int,
) -> SourceReconcilePayloads:
    companies_by_symbol = {_symbol(company): company for company in _field(settings, "companies", ()) or ()}
    sources: list[dict[str, Any]] = []
    universe_members: list[dict[str, Any]] = []
    for symbol, company in companies_by_symbol.items():
        company_id = _company_id(symbol)
        registry_row = registry_lookup(symbol)
        identity_status = "confirmed" if registry_row is not None else "configured_only"
        company_name = _string(_registry_value(registry_row, "security_name")) or _string(
            _field(company, "company_name")
        )
        exchange = _string(_registry_value(registry_row, "exchange")) or _string(_field(company, "exchange"))
        cik = _string(_field(company, "cik"))
        enabled = bool(_field(company, "enabled", True))
        universe = _string(_field(company, "universe")) or _string(_field(settings, "default_universe"))

        if cik is not None:
            sources.append(
                {
                    "source_id": f"sec:{symbol}",
                    "provider_type": "sec_submissions",
                    "company_id": company_id,
                    "ticker": symbol,
                    "cik": cik,
                    "source_role": "official_regulator",
                    "trust_tier": "official",
                    "refresh_interval_seconds": 300,
                    "enabled": enabled,
                    "extra_json": {
                        "identity_status": identity_status,
                        "universe": universe,
                        "company_name": company_name,
                        "reconciled_at_ms": int(now_ms),
                    },
                }
            )
        if enabled:
            universe_members.append(
                {
                    "company_id": company_id,
                    "ticker": symbol,
                    "company_name": company_name or "",
                    "cik": cik,
                    "exchange": exchange,
                    "active": True,
                    "priority": "P3",
                    "config_json": {
                        "identity_status": identity_status,
                        "universe": universe,
                        "configured_company_name": _string(_field(company, "company_name")),
                        "configured_exchange": _string(_field(company, "exchange")),
                    },
                }
            )

    expected_events: list[dict[str, Any]] = []
    expected_event_source_ids = sorted(
        {
            str(_field(event, "source_id"))
            for event in _field(settings, "expected_events", ()) or ()
            if _field(event, "source_id") is not None
        }
    )
    for event in _field(settings, "expected_events", ()) or ():
        if not bool(_field(event, "enabled", True)):
            continue
        symbol = _symbol(event)
        if symbol not in companies_by_symbol:
            continue
        expected_events.append(
            {
                "expected_event_id": str(_field(event, "expected_event_id")),
                "company_id": _company_id(symbol),
                "ticker": symbol,
                "event_type": str(_field(event, "event_type")),
                "fiscal_period": _string(_field(event, "fiscal_period")),
                "expected_at_ms": int(_field(event, "expected_at_ms")),
                "source_id": str(_field(event, "source_id")),
                "source_role": "calendar",
            }
        )
    return SourceReconcilePayloads(
        sources=sources,
        universe_members=universe_members,
        expected_events=expected_events,
        expected_event_source_ids=expected_event_source_ids,
    )


def _company_id(symbol: str) -> str:
    return f"market_instrument:us_equity:{symbol.upper()}"


def _symbol(value: Any) -> str:
    return str(_field(value, "symbol")).strip().upper()


def _field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _registry_value(row: Mapping[str, Any] | None, key: str) -> Any:
    if row is None:
        return None
    return row.get(key)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
