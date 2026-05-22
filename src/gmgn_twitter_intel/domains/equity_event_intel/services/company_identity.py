from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


@dataclass(frozen=True, slots=True)
class CompanyIdentityValidation:
    company_id: str
    ticker: str
    validation_status: str


def validate_company_identity(document: Mapping[str, Any]) -> CompanyIdentityValidation:
    company_id = _required_text(document, "company_id")
    ticker = _required_text(document, "ticker").upper()
    expected_company_id = f"market_instrument:us_equity:{ticker}"
    return CompanyIdentityValidation(
        company_id=company_id,
        ticker=ticker,
        validation_status="accepted" if company_id == expected_company_id and _TICKER_RE.match(ticker) else "attention",
    )


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = str(document.get(key) or "").strip()
    if not value:
        raise ValueError(f"equity event document missing {key}")
    return value
