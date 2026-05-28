from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.types import NormalizedEquityDocument

_MATERIAL_FORMS = {
    "8-K",
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "DEF 14A",
    "DEFA14A",
    "S-1",
    "S-1/A",
}


def normalize_sec_submission_documents(
    *,
    source: Mapping[str, Any],
    payload: Mapping[str, Any],
    fetched_at_ms: int,
) -> list[NormalizedEquityDocument]:
    recent = _recent_filings(payload)
    if not recent:
        return []

    docs: list[NormalizedEquityDocument] = []
    cik = _optional_string(payload.get("cik") or source.get("cik"))
    for index, accession_number in enumerate(_column(recent, "accessionNumber")):
        accession = _optional_string(accession_number)
        form_type = _optional_string(_value_at(recent, "form", index))
        if accession is None or form_type is None:
            continue
        normalized_form = form_type.upper()
        if normalized_form not in _MATERIAL_FORMS:
            continue

        filing_date = _optional_string(_value_at(recent, "filingDate", index))
        acceptance_datetime = _optional_string(_value_at(recent, "acceptanceDateTime", index))
        report_date = _optional_string(_value_at(recent, "reportDate", index))
        primary_document = _optional_string(_value_at(recent, "primaryDocument", index))
        primary_doc_description = _optional_string(_value_at(recent, "primaryDocDescription", index))
        filing_items = _optional_string(_value_at(recent, "items", index))
        document_url = _sec_document_url(cik=cik, accession_number=accession, primary_document=primary_document)
        if not document_url:
            continue
        raw_payload = {
            "company_cik": cik,
            "company_name": _optional_string(payload.get("name")),
            "accession_number": accession,
            "form_type": normalized_form,
            "acceptance_datetime": acceptance_datetime,
            "filing_date": filing_date,
            "report_date": report_date,
            "primary_document": primary_document,
        }
        payload_hash = _hash_payload(raw_payload)
        docs.append(
            NormalizedEquityDocument(
                provider_document_key=f"{accession}:{normalized_form}",
                company_id=str(source["company_id"]),
                ticker=str(source["ticker"]).upper(),
                cik=cik,
                document_url=document_url,
                payload_hash=payload_hash,
                raw_payload_json=raw_payload,
                fetched_at_ms=int(fetched_at_ms),
                provider_title=primary_doc_description or f"{str(source['ticker']).upper()} {normalized_form}",
                provider_summary=filing_items,
                primary_document_url=document_url,
                document_type="sec_filing",
                form_type=normalized_form,
                accession_number=accession,
                fiscal_period=_fiscal_period(report_date),
                event_time_ms=_datetime_to_ms(acceptance_datetime) or _date_to_ms(filing_date) or int(fetched_at_ms),
                content_hash=payload_hash,
            )
        )
    return docs


def _recent_filings(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    filings = payload.get("filings")
    if not isinstance(filings, Mapping):
        return None
    recent = filings.get("recent")
    return recent if isinstance(recent, Mapping) else None


def _column(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _value_at(payload: Mapping[str, Any], key: str, index: int) -> Any:
    values = _column(payload, key)
    if index >= len(values):
        return None
    return values[index]


def _sec_document_url(*, cik: str | None, accession_number: str, primary_document: str | None) -> str:
    if cik is None or primary_document is None:
        return ""
    cik_digits = _digits(cik)
    if not cik_digits:
        return ""
    cik_path = str(int(cik_digits))
    accession_path = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{accession_path}/{primary_document}"


def _fiscal_period(report_date: str | None) -> str | None:
    parsed = _parse_date(report_date)
    if parsed is None:
        return None
    quarter = (parsed.month - 1) // 3 + 1
    return f"{parsed.year}Q{quarter}"


def _date_to_ms(value: str | None) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return int(datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC).timestamp() * 1000)


def _datetime_to_ms(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _digits(value: str) -> str:
    return "".join(char for char in value if char.isdigit())
