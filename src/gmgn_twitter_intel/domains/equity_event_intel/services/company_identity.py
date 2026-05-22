from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CompanyIdentityValidation:
    company_id: str
    ticker: str
    validation_status: str


def validate_company_identity(document: Mapping[str, Any]) -> CompanyIdentityValidation:
    company_id = _required_text(document, "company_id")
    ticker = _required_text(document, "ticker").upper()
    return CompanyIdentityValidation(
        company_id=company_id,
        ticker=ticker,
        validation_status="accepted" if company_id.endswith(f":{ticker}") else "attention",
    )


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = str(document.get(key) or "").strip()
    if not value:
        raise ValueError(f"equity event document missing {key}")
    return value
