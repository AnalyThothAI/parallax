from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION


class NarrativeReadModel:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        targets = _extract_targets(data)
        digests = self.repository.current_digests_for_targets(
            targets,
            window=window,
            scope=_normalize_scope(scope),
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
        hydrated = dict(data)
        for key in ("targets", "attention", "items"):
            if isinstance(hydrated.get(key), list):
                hydrated[key] = [self._hydrate_row(row, digests) for row in hydrated[key]]
        return hydrated

    def hydrate_token_case(self, dossier: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        target = dossier.get("target") or {}
        digests = self.repository.current_digests_for_targets(
            [{"target_type": target.get("target_type"), "target_id": target.get("target_id")}],
            window=window,
            scope=_normalize_scope(scope),
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
        hydrated = dict(dossier)
        hydrated["discussion_digest"] = digests.get(
            (str(target.get("target_type")), str(target.get("target_id"))),
            _missing_digest("digest_not_ready"),
        )
        hydrated.setdefault("narrative_clusters", hydrated["discussion_digest"].get("dominant_narratives_json", []))
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

    def _hydrate_row(self, row: dict[str, Any], digests: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
        target_type = str(row.get("target_type") or row.get("type") or "")
        target_id = str(row.get("target_id") or row.get("id") or "")
        return {
            **row,
            "discussion_digest": digests.get((target_type, target_id), _missing_digest("digest_not_ready")),
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
        "data_gaps": [{"reason": reason}],
        "semantic_coverage": 0,
        "evidence_refs": [],
    }


def _missing_semantic() -> dict[str, Any]:
    return {
        "status": "pending",
        "trade_stance": "unknown",
        "attention_valence": "unknown",
        "data_gaps": [{"reason": "semantic_not_ready"}],
    }
