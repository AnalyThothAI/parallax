from __future__ import annotations

import hashlib
import html
import re

from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EvidenceArtifactKind,
    EvidenceExtractionStatus,
    NormalizedEquityEvidenceArtifact,
)

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_EXCERPT_MAX_CHARS = 800


def extract_sec_html_text(html_text: str) -> str:
    if not str(html_text or "").strip():
        return ""
    without_blocked_tags = _SCRIPT_STYLE_RE.sub(" ", str(html_text))
    without_tags = _TAG_RE.sub(" ", without_blocked_tags)
    decoded = html.unescape(without_tags)
    return _WHITESPACE_RE.sub(" ", decoded).strip()


def build_ready_html_text_artifact(
    *,
    event_document_id: str,
    source_url: str,
    content_text: str,
    fetched_at_ms: int,
    parsed_at_ms: int,
    now_ms: int,
    provider_document_id: str | None = None,
    source_id: str | None = None,
) -> NormalizedEquityEvidenceArtifact:
    content_hash = _content_hash(content_text)
    return NormalizedEquityEvidenceArtifact(
        evidence_artifact_id=_artifact_id(
            event_document_id=event_document_id,
            artifact_kind="html_text",
            content_hash=content_hash,
        ),
        event_document_id=event_document_id,
        provider_document_id=provider_document_id,
        source_id=source_id,
        artifact_kind="html_text",
        extraction_status="ready",
        source_url=source_url,
        content_hash=content_hash,
        content_text=content_text,
        content_json={},
        excerpt_text=_excerpt(content_text),
        fetched_at_ms=int(fetched_at_ms),
        parsed_at_ms=int(parsed_at_ms),
        created_at_ms=int(now_ms),
        updated_at_ms=int(now_ms),
        failure_reason=None,
    )


def build_unavailable_evidence_artifact(
    *,
    event_document_id: str,
    artifact_kind: EvidenceArtifactKind,
    source_url: str,
    reason: str,
    fetched_at_ms: int,
    parsed_at_ms: int,
    now_ms: int,
    provider_document_id: str | None = None,
    source_id: str | None = None,
) -> NormalizedEquityEvidenceArtifact:
    return _empty_artifact(
        event_document_id=event_document_id,
        artifact_kind=artifact_kind,
        extraction_status="unavailable",
        source_url=source_url,
        reason=reason,
        fetched_at_ms=fetched_at_ms,
        parsed_at_ms=parsed_at_ms,
        now_ms=now_ms,
        provider_document_id=provider_document_id,
        source_id=source_id,
    )


def build_failed_evidence_artifact(
    *,
    event_document_id: str,
    artifact_kind: EvidenceArtifactKind,
    source_url: str,
    reason: str,
    fetched_at_ms: int,
    parsed_at_ms: int,
    now_ms: int,
    provider_document_id: str | None = None,
    source_id: str | None = None,
) -> NormalizedEquityEvidenceArtifact:
    return _empty_artifact(
        event_document_id=event_document_id,
        artifact_kind=artifact_kind,
        extraction_status="failed",
        source_url=source_url,
        reason=reason,
        fetched_at_ms=fetched_at_ms,
        parsed_at_ms=parsed_at_ms,
        now_ms=now_ms,
        provider_document_id=provider_document_id,
        source_id=source_id,
    )


def _empty_artifact(
    *,
    event_document_id: str,
    artifact_kind: EvidenceArtifactKind,
    extraction_status: EvidenceExtractionStatus,
    source_url: str,
    reason: str,
    fetched_at_ms: int,
    parsed_at_ms: int,
    now_ms: int,
    provider_document_id: str | None,
    source_id: str | None,
) -> NormalizedEquityEvidenceArtifact:
    content_hash = _content_hash("")
    return NormalizedEquityEvidenceArtifact(
        evidence_artifact_id=_artifact_id(
            event_document_id=event_document_id,
            artifact_kind=artifact_kind,
            content_hash=reason,
        ),
        event_document_id=event_document_id,
        provider_document_id=provider_document_id,
        source_id=source_id,
        artifact_kind=artifact_kind,
        extraction_status=extraction_status,
        source_url=source_url,
        content_hash=content_hash,
        content_text="",
        content_json={},
        excerpt_text="",
        fetched_at_ms=int(fetched_at_ms),
        parsed_at_ms=int(parsed_at_ms),
        created_at_ms=int(now_ms),
        updated_at_ms=int(now_ms),
        failure_reason=reason,
    )


def _content_hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _artifact_id(*, event_document_id: str, artifact_kind: EvidenceArtifactKind, content_hash: str) -> str:
    suffix = content_hash.split(":", 1)[-1][:16]
    return f"sec-evidence:{event_document_id}:{artifact_kind}:{suffix}"


def _excerpt(text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    if len(normalized) <= _EXCERPT_MAX_CHARS:
        return normalized
    return normalized[:_EXCERPT_MAX_CHARS].rstrip()


__all__ = [
    "build_failed_evidence_artifact",
    "build_ready_html_text_artifact",
    "build_unavailable_evidence_artifact",
    "extract_sec_html_text",
]
