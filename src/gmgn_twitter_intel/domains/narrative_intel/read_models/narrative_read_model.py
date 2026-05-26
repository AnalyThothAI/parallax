from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.narrative_intel.types.narrative_currentness import (
    narrative_delta_from_currentness,
    public_currentness,
)

TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW = "1h"
TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS = frozenset({"5m", "4h", "24h"})
OVERLAY_READY_STATUSES = frozenset({"current", "updating", "stale"})


class NarrativeReadModel:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        targets = _extract_targets(data)
        normalized_scope = _normalize_scope(scope)
        repository_window = (
            TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW if window in TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS else window
        )
        digests = self.repository.current_narrative_snapshots_for_targets(
            targets,
            window=repository_window,
            scope=normalized_scope,
            schema_version=NARRATIVE_SCHEMA_VERSION,
            now_ms=now_ms,
        )
        hydrated = dict(data)
        for key in ("targets", "attention", "items"):
            if isinstance(hydrated.get(key), list):
                hydrated[key] = [
                    self._hydrate_row(
                        row,
                        digests,
                        now_ms=now_ms,
                        surface_window=window,
                        scope=normalized_scope,
                    )
                    for row in hydrated[key]
                ]
        return hydrated

    def hydrate_token_case(self, dossier: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        target = dossier.get("target") or {}
        digests = self.repository.current_narrative_snapshots_for_targets(
            [{"target_type": target.get("target_type"), "target_id": target.get("target_id")}],
            window=window,
            scope=_normalize_scope(scope),
            schema_version=NARRATIVE_SCHEMA_VERSION,
            now_ms=now_ms,
        )
        hydrated = dict(dossier)
        hydrated["discussion_digest"] = _public_digest(
            digests.get(
                (str(target.get("target_type")), str(target.get("target_id"))),
                _missing_digest("digest_not_ready"),
            ),
            now_ms=now_ms,
            surface="token_case",
        )
        hydrated["narrative_delta"] = narrative_delta_from_currentness(hydrated["discussion_digest"]["currentness"])
        hydrated.setdefault("narrative_clusters", hydrated["discussion_digest"].get("dominant_narratives", []))
        if isinstance(hydrated.get("posts"), dict):
            hydrated["posts"] = self.hydrate_target_posts(
                hydrated["posts"],
                window=window,
                scope=scope,
                now_ms=now_ms,
            )
        return hydrated

    def hydrate_target_posts(
        self,
        posts_data: dict[str, Any],
        *,
        window: str,
        scope: str,
        now_ms: int,
    ) -> dict[str, Any]:
        posts = list(posts_data.get("items") or posts_data.get("posts") or [])
        semantics = self.repository.semantics_for_posts(posts, schema_version=NARRATIVE_SCHEMA_VERSION)
        hydrated_posts = []
        for post in posts:
            key = (str(post.get("event_id")), str(post.get("target_type")), str(post.get("target_id")))
            hydrated_posts.append({**post, "semantic": semantics.get(key, _missing_semantic())})
        hydrated = dict(posts_data)
        if "items" in hydrated:
            hydrated["items"] = hydrated_posts
        else:
            hydrated["posts"] = hydrated_posts
        return hydrated

    def _hydrate_row(
        self,
        row: dict[str, Any],
        digests: dict[tuple[str, str], dict[str, Any]],
        *,
        now_ms: int,
        surface_window: str,
        scope: str,
    ) -> dict[str, Any]:
        target_type = str(row.get("target_type") or row.get("type") or "")
        target_id = str(row.get("target_id") or row.get("id") or "")
        digest = digests.get((target_type, target_id), _missing_digest("digest_not_ready"))
        if surface_window in TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS:
            digest = _token_radar_overlay_digest(
                digest,
                target_type=target_type,
                target_id=target_id,
                surface_window=surface_window,
                scope=scope,
                now_ms=now_ms,
            )
        return {
            **row,
            "discussion_digest": _public_digest(
                digest,
                now_ms=now_ms,
                surface="token_radar",
            ),
            "pulse_overlay": row.get("pulse_overlay") or {"status": "absent"},
        }


def _extract_targets(data: dict[str, Any]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for key in ("targets", "attention", "items"):
        for row in data.get(key) or []:
            target_type = row.get("target_type") or row.get("type")
            target_id = row.get("target_id") or row.get("id")
            if target_type and target_id:
                targets.append({"target_type": str(target_type), "target_id": str(target_id)})
    return targets


def _normalize_scope(scope: str) -> str:
    return "matched" if scope == "watched" else scope


def _missing_digest(reason: str) -> dict[str, Any]:
    return {
        "status": "pending",
        "data_gaps_json": [{"reason": reason}],
        "semantic_coverage": 0,
        "evidence_refs_json": [],
    }


def _token_radar_overlay_digest(
    digest: dict[str, Any],
    *,
    target_type: str,
    target_id: str,
    surface_window: str,
    scope: str,
    now_ms: int,
) -> dict[str, Any]:
    if _is_reusable_token_radar_overlay_digest(digest, now_ms=now_ms):
        return {
            **digest,
            "analysis_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
            "source_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
            "surface_window": surface_window,
            "reuse_reason": "target_current_1h_narrative",
        }
    return _missing_token_radar_overlay_digest(
        target_type=target_type,
        target_id=target_id,
        surface_window=surface_window,
        scope=scope,
        now_ms=now_ms,
    )


def _is_reusable_token_radar_overlay_digest(digest: dict[str, Any], *, now_ms: int) -> bool:
    if digest.get("status") != "ready":
        return False
    currentness = _public_currentness_for_row(digest, now_ms=now_ms)
    return currentness.get("display_status") in OVERLAY_READY_STATUSES


def _missing_token_radar_overlay_digest(
    *,
    target_type: str,
    target_id: str,
    surface_window: str,
    scope: str,
    now_ms: int,
) -> dict[str, Any]:
    reason = "no_reusable_1h_digest"
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
        "scope": scope,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "status": "pending",
        "is_current": False,
        "analysis_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
        "source_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
        "surface_window": surface_window,
        "reuse_reason": reason,
        "data_gaps_json": [{"reason": reason}],
        "semantic_coverage": 0,
        "source_event_count": 0,
        "labeled_event_count": 0,
        "independent_author_count": 0,
        "evidence_refs_json": [],
        "currentness": public_currentness(
            digest=None,
            admission=None,
            window=TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
            now_ms=now_ms,
            reason=reason,
        ),
    }


def _public_digest(
    digest: dict[str, Any],
    *,
    now_ms: int | None = None,
    surface: str = "token_radar",
) -> dict[str, Any]:
    row = dict(digest)
    narratives = _list(row.get("dominant_narratives_json"))
    dominant = _dict(narratives[0]) if narratives else {}
    bull = _dict(row.get("bull_view_json"))
    bear = _dict(row.get("bear_view_json"))
    propagation = _dict(row.get("propagation_read_json"))
    data_gaps = [_public_gap(gap) for gap in _list(row.get("data_gaps_json"))]
    semantic_coverage = _float(row.get("semantic_coverage"))
    currentness = _public_currentness_for_row(row, now_ms=now_ms)
    if (
        surface == "token_case"
        and row.get("status") == "ready"
        and currentness.get("display_status") == "out_of_frontier"
    ):
        currentness = {**currentness, "display_status": "stale"}
    payload = {
        **row,
        "currentness": currentness,
        "dominant_narratives": narratives,
        "dominant_narrative": _dominant_narrative(row, dominant),
        "coverage": {
            "semantic_coverage": semantic_coverage,
            "source_mentions": _int(row.get("source_event_count")),
            "labeled_mentions": _int(row.get("labeled_event_count")),
            "independent_authors": _int(row.get("independent_author_count")),
        },
        "stance_mix": _dict(row.get("stance_mix_json")),
        "attention_valence_mix": _dict(row.get("attention_valence_mix_json")),
        "propagation": _propagation(propagation),
        "bull_bear": {
            "stance": _bull_bear_stance(row.get("status"), semantic_coverage),
            "bull": _argument(bull),
            "bear": _argument(bear),
        },
        "timeline_pills": _timeline_pills(narratives),
        "data_gaps": data_gaps,
        "evidence_refs": _list(row.get("evidence_refs_json")),
    }
    processing = _processing(row, now_ms=now_ms)
    if processing:
        payload["processing"] = processing
    return payload


def _public_currentness_for_row(row: dict[str, Any], *, now_ms: int | None) -> dict[str, Any]:
    currentness = row.get("currentness")
    if isinstance(currentness, dict):
        return dict(currentness)
    return public_currentness(
        digest=row,
        admission=row.get("_current_admission") if isinstance(row.get("_current_admission"), dict) else None,
        window=str(row.get("window") or ""),
        now_ms=0 if now_ms is None else int(now_ms),
        reason=_first_data_gap_reason(row),
    )


def _first_data_gap_reason(row: dict[str, Any]) -> str | None:
    for gap in _list(row.get("data_gaps_json")):
        if isinstance(gap, dict) and gap.get("reason"):
            return str(gap["reason"])
    return None


def _processing(row: dict[str, Any], *, now_ms: int | None) -> dict[str, Any] | None:
    semantic = _int(row.get("semantic_backlog_pending"))
    retryable = _int(row.get("semantic_backlog_retryable"))
    unavailable = _int(row.get("semantic_backlog_unavailable"))
    oldest_due_age_ms = _oldest_due_age(row.get("semantic_backlog_oldest_due_at_ms"), now_ms=now_ms)
    if semantic <= 0 and retryable <= 0 and unavailable <= 0 and oldest_due_age_ms is None:
        return None
    backlog: dict[str, Any] = {
        "semantic": semantic,
        "retryable": retryable,
        "unavailable": unavailable,
    }
    if oldest_due_age_ms is not None:
        backlog["oldest_due_age_ms"] = oldest_due_age_ms
    return {"backlog": backlog}


def _dominant_narrative(row: dict[str, Any], dominant: dict[str, Any]) -> dict[str, Any] | None:
    title = dominant.get("label_zh") or dominant.get("title") or row.get("headline_zh") or dominant.get("cluster_key")
    summary = dominant.get("summary_zh") or row.get("headline_zh")
    if not title and not summary:
        return None
    return {
        "title": title or "narrative",
        "summary_zh": summary or "",
        "propagation_state": dominant.get("propagation_state") or dominant.get("cluster_key"),
        "trade_stance": _top_key(_dict(dominant.get("stance_mix"))),
        "attention_valence": _top_key(_dict(dominant.get("attention_valence_mix"))),
        "evidence_refs": _list(dominant.get("evidence_refs")),
    }


def _argument(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary_zh": value.get("summary_zh") or "",
        "strength": value.get("strength") or "unknown",
        "evidence_refs": _list(value.get("evidence_refs")),
    }


def _propagation(value: dict[str, Any]) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "state": value.get("state") or value.get("phase") or value.get("primary_channel") or "unknown",
        "summary_zh": value.get("summary_zh") or value.get("summary") or "",
        "evidence_refs": _list(value.get("evidence_refs")),
    }


def _public_gap(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    reason = value.get("reason") or value.get("message") or value.get("concrete_reason")
    if not reason:
        reason = value.get("gap_type") or value.get("code")
    return {**value, "reason": reason} if reason else value


def _timeline_pills(narratives: list[Any]) -> list[dict[str, Any]]:
    pills = []
    for narrative in narratives[:3]:
        item = _dict(narrative)
        label = item.get("label_zh") or item.get("cluster_key")
        if label:
            pills.append({"label": label, "tone": "info", "evidence_refs": _list(item.get("evidence_refs"))})
    return pills


def _bull_bear_stance(status: Any, semantic_coverage: float) -> str:
    if status == "ready" and semantic_coverage >= 0.35:
        return "research"
    if status == "insufficient":
        return "unknown"
    return "watch"


def _top_key(values: dict[str, Any]) -> str | None:
    if not values:
        return None
    return max(values.items(), key=lambda item: float(item[1] or 0))[0]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _oldest_due_age(value: Any, *, now_ms: int | None) -> int | None:
    if value is None or now_ms is None:
        return None
    try:
        return max(0, int(now_ms) - int(value))
    except (TypeError, ValueError):
        return None


def _missing_semantic() -> dict[str, Any]:
    return {
        "status": "pending",
        "trade_stance": "unknown",
        "attention_valence": "unknown",
        "data_gaps": [{"reason": "semantic_not_ready"}],
    }
