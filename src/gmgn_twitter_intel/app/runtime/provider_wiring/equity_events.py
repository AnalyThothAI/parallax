from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from gmgn_twitter_intel.app.runtime.provider_wiring.types import EquityEventIntelProviders
from gmgn_twitter_intel.domains.equity_event_intel.services.sec_evidence import (
    build_failed_evidence_artifact,
    build_ready_html_text_artifact,
    build_unavailable_evidence_artifact,
    extract_sec_html_text,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EquityEvidenceHydrationResult,
    EvidenceArtifactKind,
    NormalizedEquityDocument,
    NormalizedEquityEvidenceArtifact,
)
from gmgn_twitter_intel.integrations.equity_events.sec_edgar_client import (
    SecEdgarClient,
    SecEdgarInvalidCikError,
    SecEdgarInvalidJsonError,
)
from gmgn_twitter_intel.platform.config.settings import Settings


@dataclass(frozen=True, slots=True)
class EquityDocumentProviderFetchResult:
    status_code: int
    documents: list[dict[str, Any]] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class CompositeEquityEventDocumentProvider:
    def __init__(self, *, sec_client: SecEdgarClient | None) -> None:
        self._sec_client = sec_client

    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentProviderFetchResult:
        provider_type = str(source.get("provider_type") or "sec_submissions")
        if provider_type != "sec_submissions":
            return _failed_fetch(source=source, reason="unsupported_provider_type")
        if self._sec_client is None:
            return _failed_fetch(source=source, reason="missing_sec_user_agent")

        cik = source.get("cik") or source.get("company_cik")
        if not cik:
            return _failed_fetch(source=source, reason="missing_cik")

        try:
            result = self._sec_client.fetch_company_submissions(
                str(cik),
                etag=_optional_string(source.get("etag")),
                last_modified=_optional_string(source.get("last_modified")),
            )
        except SecEdgarInvalidCikError:
            return _failed_fetch(source=source, reason="invalid_cik")
        except SecEdgarInvalidJsonError:
            return _failed_fetch(source=source, reason="sec_invalid_json")
        except httpx.TimeoutException:
            return _failed_fetch(source=source, reason="sec_timeout")
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            return _failed_fetch(
                source=source,
                reason=f"sec_http_{status_code}",
                status_code=status_code,
            )
        except httpx.TransportError:
            return _failed_fetch(source=source, reason="sec_transport_error")
        if result.not_modified:
            return EquityDocumentProviderFetchResult(
                status_code=result.status_code,
                etag=result.etag,
                last_modified=result.last_modified,
                not_modified=True,
            )
        return EquityDocumentProviderFetchResult(
            status_code=result.status_code,
            documents=[
                {
                    "provider_type": "sec_submissions",
                    "source_id": source.get("source_id"),
                    "cik": str(cik),
                    "payload": result.payload,
                }
            ],
            etag=result.etag,
            last_modified=result.last_modified,
            not_modified=False,
        )

    def hydrate_document_evidence(
        self,
        *,
        source: dict[str, Any],
        document: NormalizedEquityDocument,
    ) -> EquityEvidenceHydrationResult:
        event_document_id = _event_document_id(document)
        provider_document_id = document.provider_document_id
        source_id = _optional_string(source.get("source_id"))
        now_ms = int(document.fetched_at_ms)

        if document.document_type != "sec_filing":
            return EquityEvidenceHydrationResult(
                status_code=0,
                error_code="unsupported_document_type",
                artifacts=[
                    build_unavailable_evidence_artifact(
                        event_document_id=event_document_id,
                        provider_document_id=provider_document_id,
                        source_id=source_id,
                        artifact_kind="html_text",
                        source_url=document.document_url,
                        reason="unsupported_document_type",
                        fetched_at_ms=document.fetched_at_ms,
                        parsed_at_ms=now_ms,
                        now_ms=now_ms,
                    )
                ],
            )
        if self._sec_client is None:
            return _failed_hydration(
                document=document,
                source_id=source_id,
                event_document_id=event_document_id,
                provider_document_id=provider_document_id,
                reason="missing_sec_user_agent",
                status_code=0,
                artifact_kind="html_text",
                source_url=document.document_url,
            )

        artifacts: list[NormalizedEquityEvidenceArtifact] = []
        status_code = 0
        error_code: str | None = None
        try:
            result = self._sec_client.fetch_filing_document(document.document_url)
            status_code = result.status_code
            extracted_text = extract_sec_html_text(result.text)
            if extracted_text:
                artifacts.append(
                    build_ready_html_text_artifact(
                        event_document_id=event_document_id,
                        provider_document_id=provider_document_id,
                        source_id=source_id,
                        source_url=document.document_url,
                        content_text=extracted_text,
                        fetched_at_ms=document.fetched_at_ms,
                        parsed_at_ms=now_ms,
                        now_ms=now_ms,
                    )
                )
            else:
                artifacts.append(
                    build_unavailable_evidence_artifact(
                        event_document_id=event_document_id,
                        provider_document_id=provider_document_id,
                        source_id=source_id,
                        artifact_kind="html_text",
                        source_url=document.document_url,
                        reason="empty_sec_document_text",
                        fetched_at_ms=document.fetched_at_ms,
                        parsed_at_ms=now_ms,
                        now_ms=now_ms,
                    )
                )
        except ValueError:
            reason = "sec_invalid_url"
            return _failed_hydration(
                document=document,
                source_id=source_id,
                event_document_id=event_document_id,
                provider_document_id=provider_document_id,
                reason=reason,
                status_code=0,
                artifact_kind="html_text",
                source_url=document.document_url,
            )
        except httpx.TimeoutException:
            reason = "sec_timeout"
            status_code = 0
            error_code = reason
            artifacts.append(
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="html_text",
                    source_url=document.document_url,
                    reason=reason,
                )
            )
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            reason = f"sec_http_{status_code}"
            error_code = reason
            artifacts.append(
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="html_text",
                    source_url=document.document_url,
                    reason=reason,
                )
            )
        except httpx.TransportError:
            reason = "sec_transport_error"
            status_code = 0
            error_code = reason
            artifacts.append(
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="html_text",
                    source_url=document.document_url,
                    reason=reason,
                )
            )

        if document.cik:
            companyfacts_artifact, companyfacts_status, companyfacts_error = self._hydrate_companyfacts(
                document=document,
                source_id=source_id,
                event_document_id=event_document_id,
                provider_document_id=provider_document_id,
            )
            artifacts.append(companyfacts_artifact)
            if error_code is None and companyfacts_error is not None:
                error_code = companyfacts_error
                status_code = companyfacts_status

        return EquityEvidenceHydrationResult(status_code=status_code, artifacts=artifacts, error_code=error_code)

    def _hydrate_companyfacts(
        self,
        *,
        document: NormalizedEquityDocument,
        source_id: str | None,
        event_document_id: str,
        provider_document_id: str | None,
    ) -> tuple[NormalizedEquityEvidenceArtifact, int, str | None]:
        sec_client = self._sec_client
        if sec_client is None:
            raise RuntimeError("SEC client is required for companyfacts hydration")
        source_url = _companyfacts_url(str(document.cik))
        now_ms = int(document.fetched_at_ms)
        try:
            result = sec_client.fetch_companyfacts(str(document.cik))
        except SecEdgarInvalidCikError:
            reason = "sec_invalid_cik"
            return (
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="companyfacts",
                    source_url=source_url,
                    reason=reason,
                ),
                0,
                reason,
            )
        except SecEdgarInvalidJsonError:
            reason = "sec_invalid_json"
            return (
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="companyfacts",
                    source_url=source_url,
                    reason=reason,
                ),
                0,
                reason,
            )
        except httpx.TimeoutException:
            reason = "sec_timeout"
            return (
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="companyfacts",
                    source_url=source_url,
                    reason=reason,
                ),
                0,
                reason,
            )
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            if status_code == 404:
                return (
                    build_unavailable_evidence_artifact(
                        event_document_id=event_document_id,
                        provider_document_id=provider_document_id,
                        source_id=source_id,
                        artifact_kind="companyfacts",
                        source_url=source_url,
                        reason="companyfacts_unavailable",
                        fetched_at_ms=document.fetched_at_ms,
                        parsed_at_ms=now_ms,
                        now_ms=now_ms,
                    ),
                    status_code,
                    None,
                )
            reason = f"sec_http_{status_code}"
            return (
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="companyfacts",
                    source_url=source_url,
                    reason=reason,
                ),
                status_code,
                reason,
            )
        except httpx.TransportError:
            reason = "sec_transport_error"
            return (
                _failed_artifact_for_document(
                    document=document,
                    source_id=source_id,
                    event_document_id=event_document_id,
                    provider_document_id=provider_document_id,
                    artifact_kind="companyfacts",
                    source_url=source_url,
                    reason=reason,
                ),
                0,
                reason,
            )

        content_hash = _json_content_hash(result.payload)
        artifact_suffix = content_hash.split(":", 1)[-1][:16]
        return (
            NormalizedEquityEvidenceArtifact(
                evidence_artifact_id=f"sec-evidence:{event_document_id}:companyfacts:{artifact_suffix}",
                event_document_id=event_document_id,
                provider_document_id=provider_document_id,
                source_id=source_id,
                artifact_kind="companyfacts",
                extraction_status="ready",
                source_url=source_url,
                content_hash=content_hash,
                content_text="",
                content_json=result.payload,
                excerpt_text="",
                fetched_at_ms=document.fetched_at_ms,
                parsed_at_ms=now_ms,
                created_at_ms=now_ms,
                updated_at_ms=now_ms,
                failure_reason=None,
            ),
            result.status_code,
            None,
        )

    def close(self) -> None:
        if self._sec_client is not None:
            self._sec_client.close()


def wire_equity_event_intel(
    settings: Settings,
    *,
    brief_provider: object | None = None,
) -> EquityEventIntelProviders:
    if not settings.equity_event_intel.enabled:
        return EquityEventIntelProviders()
    return EquityEventIntelProviders(
        document_provider=CompositeEquityEventDocumentProvider(
            sec_client=_sec_client(settings),
        ),
        brief_provider=brief_provider,
    )


def _sec_client(settings: Settings) -> SecEdgarClient | None:
    user_agent = _optional_string(settings.equity_event_intel.sec_user_agent)
    if user_agent is None:
        return None
    return SecEdgarClient(user_agent=user_agent)


def _failed_fetch(*, source: dict[str, Any], reason: str, status_code: int = 0) -> EquityDocumentProviderFetchResult:
    return EquityDocumentProviderFetchResult(
        status_code=max(0, int(status_code)),
        documents=[
            {
                "status": "failed",
                "error_code": reason,
                "provider_type": source.get("provider_type") or "sec_submissions",
                "source_id": source.get("source_id"),
            }
        ],
    )


def _failed_hydration(
    *,
    document: NormalizedEquityDocument,
    source_id: str | None,
    event_document_id: str,
    provider_document_id: str | None,
    reason: str,
    status_code: int,
    artifact_kind: EvidenceArtifactKind,
    source_url: str,
) -> EquityEvidenceHydrationResult:
    return EquityEvidenceHydrationResult(
        status_code=max(0, int(status_code)),
        error_code=reason,
        artifacts=[
            _failed_artifact_for_document(
                document=document,
                source_id=source_id,
                event_document_id=event_document_id,
                provider_document_id=provider_document_id,
                artifact_kind=artifact_kind,
                source_url=source_url,
                reason=reason,
            )
        ],
    )


def _failed_artifact_for_document(
    *,
    document: NormalizedEquityDocument,
    source_id: str | None,
    event_document_id: str,
    provider_document_id: str | None,
    artifact_kind: EvidenceArtifactKind,
    source_url: str,
    reason: str,
) -> NormalizedEquityEvidenceArtifact:
    now_ms = int(document.fetched_at_ms)
    return build_failed_evidence_artifact(
        event_document_id=event_document_id,
        provider_document_id=provider_document_id,
        source_id=source_id,
        artifact_kind=artifact_kind,
        source_url=source_url,
        reason=reason,
        fetched_at_ms=document.fetched_at_ms,
        parsed_at_ms=now_ms,
        now_ms=now_ms,
    )


def _event_document_id(document: NormalizedEquityDocument) -> str:
    value = document.event_document_id
    return str(value or document.provider_document_key)


def _companyfacts_url(cik: str) -> str:
    digits = "".join(ch for ch in str(cik or "") if ch.isdigit())
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{digits.zfill(10)}.json"


def _json_content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "CompositeEquityEventDocumentProvider",
    "EquityDocumentProviderFetchResult",
    "wire_equity_event_intel",
]
