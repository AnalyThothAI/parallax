from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_EVENT_PAYLOAD_PATHS = (
    ROOT / "src/gmgn_twitter_intel/app/surfaces/api/http.py",
    ROOT / "src/gmgn_twitter_intel/app/surfaces/api/ws.py",
    ROOT / "src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py",
)


def test_public_event_payloads_do_not_return_raw_intent_resolution_facts() -> None:
    violations: list[str] = []
    for path in PUBLIC_EVENT_PAYLOAD_PATHS:
        text = path.read_text()
        if "intent_resolutions.resolutions_for_event" in text:
            violations.append(f"{path.relative_to(ROOT)} reads raw intent resolution facts")
        if path.name == "collector_service.py" and "ingested.token_resolutions" in text:
            violations.append(f"{path.relative_to(ROOT)} publishes internal ingest token_resolutions")

    assert violations == []
