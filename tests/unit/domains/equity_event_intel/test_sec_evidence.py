from __future__ import annotations

from gmgn_twitter_intel.domains.equity_event_intel.services.sec_evidence import (
    build_failed_evidence_artifact,
    build_ready_html_text_artifact,
    build_unavailable_evidence_artifact,
    extract_sec_html_text,
)


def test_extract_sec_html_text_removes_script_style_and_normalizes_whitespace() -> None:
    html = """
    <html>
      <head>
        <style>.hidden { display: none; }</style>
        <script>window.SECRET = true;</script>
      </head>
      <body>
        Revenue&nbsp;rose
        <noscript>tracking fallback</noscript>
        <div>  10% &amp; margins expanded. </div>
      </body>
    </html>
    """

    assert extract_sec_html_text(html) == "Revenue rose 10% & margins expanded."
    assert extract_sec_html_text("   ") == ""


def test_build_ready_html_text_artifact_hashes_content_and_sets_excerpt() -> None:
    artifact = build_ready_html_text_artifact(
        event_document_id="doc-1",
        provider_document_id="provider-doc-1",
        source_id="sec:AAPL",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl.htm",
        content_text="Revenue rose 10% and margins expanded.",
        fetched_at_ms=10,
        parsed_at_ms=20,
        now_ms=30,
    )

    assert artifact.evidence_artifact_id.startswith("sec-evidence:doc-1:html_text:")
    assert artifact.artifact_kind == "html_text"
    assert artifact.extraction_status == "ready"
    assert artifact.content_hash == "sha256:fa57a520416b2e94859462a436f2fb2f0e0470d52ccd991de9300033b2410329"
    assert artifact.content_text == "Revenue rose 10% and margins expanded."
    assert artifact.content_json == {}
    assert artifact.excerpt_text == "Revenue rose 10% and margins expanded."
    assert artifact.failure_reason is None


def test_build_unavailable_evidence_artifact_stores_reason() -> None:
    artifact = build_unavailable_evidence_artifact(
        event_document_id="doc-1",
        artifact_kind="html_text",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
        reason="empty_sec_document_text",
        fetched_at_ms=10,
        parsed_at_ms=20,
        now_ms=30,
    )

    assert artifact.extraction_status == "unavailable"
    assert artifact.content_text == ""
    assert artifact.failure_reason == "empty_sec_document_text"


def test_build_failed_evidence_artifact_stores_reason() -> None:
    artifact = build_failed_evidence_artifact(
        event_document_id="doc-1",
        artifact_kind="companyfacts",
        source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        reason="sec_timeout",
        fetched_at_ms=10,
        parsed_at_ms=20,
        now_ms=30,
    )

    assert artifact.extraction_status == "failed"
    assert artifact.content_text == ""
    assert artifact.failure_reason == "sec_timeout"
