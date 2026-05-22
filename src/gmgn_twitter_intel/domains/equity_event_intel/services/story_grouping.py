from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_STORY_POLICY_VERSION

_TITLE_THRESHOLD = 0.72
_TITLE_TIME_WINDOW_MS = 6 * 60 * 60 * 1000
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EVENT_FAMILIES = {
    "earnings_release": "earnings",
    "quarterly_report": "earnings",
    "annual_report": "earnings",
}


@dataclass(frozen=True, slots=True)
class StoryAssignment:
    story_id: str | None
    relation: str
    match_reason: str
    match_score: float


def choose_story_assignment(*, event: dict[str, Any], candidates: list[dict[str, Any]]) -> StoryAssignment:
    for candidate in candidates:
        if _same_document_lineage(event, candidate):
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_document_lineage", 1.0)
        if _same_period_family(event, candidate):
            return StoryAssignment(
                str(candidate["story_id"]),
                "same_story",
                "same_company_period_event_family",
                0.95,
            )

    best: StoryAssignment | None = None
    for candidate in candidates:
        if _text(event.get("company_id")) != _text(candidate.get("company_id")):
            continue
        if _periods_conflict(event, candidate):
            continue
        if not _is_time_close(event, candidate):
            continue
        score = _lexical_score(_headline(event), _headline(candidate))
        if score < _TITLE_THRESHOLD:
            continue
        assignment = StoryAssignment(
            str(candidate["story_id"]),
            "same_story",
            "title_time_company_overlap",
            score,
        )
        if best is None or assignment.match_score > best.match_score:
            best = assignment

    if best is not None:
        return best
    return StoryAssignment(None, "representative", "new_story", 0.0)


def new_story_id(*, company_event_id: str) -> str:
    seed = f"equity-story|{EQUITY_EVENT_STORY_POLICY_VERSION}|{company_event_id}"
    return "equity-story-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def event_family(event_type: str) -> str:
    return _EVENT_FAMILIES.get(event_type, event_type)


def _same_period_family(event: dict[str, Any], candidate: dict[str, Any]) -> bool:
    fiscal_period = _text(event.get("fiscal_period"))
    return (
        bool(fiscal_period)
        and _text(event.get("company_id")) == _text(candidate.get("company_id"))
        and fiscal_period == _text(candidate.get("fiscal_period"))
        and event_family(_text(event.get("event_type"))) == event_family(_text(candidate.get("event_type")))
    )


def _same_document_lineage(event: dict[str, Any], candidate: dict[str, Any]) -> bool:
    for key in ("primary_document_id", "accession_number"):
        left = _text(event.get(key))
        if left and left == _text(candidate.get(key)):
            return _text(event.get("company_id")) == _text(candidate.get("company_id"))
    return False


def _periods_conflict(event: dict[str, Any], candidate: dict[str, Any]) -> bool:
    event_period = _text(event.get("fiscal_period"))
    candidate_period = _text(candidate.get("fiscal_period"))
    return bool(event_period and candidate_period and event_period != candidate_period)


def _headline(row: dict[str, Any]) -> str:
    return _text(row.get("summary") or row.get("representative_headline") or row.get("title"))


def _lexical_score(left: str, right: str) -> float:
    left_tokens = set(_TOKEN_RE.findall(left.casefold()))
    right_tokens = set(_TOKEN_RE.findall(right.casefold()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(min(len(left_tokens), len(right_tokens)))


def _is_time_close(event: dict[str, Any], candidate: dict[str, Any]) -> bool:
    event_time = _int_or_none(event.get("event_time_ms"))
    candidate_time = _int_or_none(candidate.get("latest_seen_at_ms") or candidate.get("event_time_ms"))
    if event_time is None or candidate_time is None:
        return False
    return abs(event_time - candidate_time) <= _TITLE_TIME_WINDOW_MS


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
