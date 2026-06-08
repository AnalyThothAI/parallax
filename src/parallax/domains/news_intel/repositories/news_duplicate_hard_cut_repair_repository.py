from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from parallax.domains.news_intel.repositories.news_intel_hard_cut_cleanup_repository import (
    news_intel_hard_cut_runtime_guard,
)
from parallax.domains.news_intel.types.news_material_identity import (
    material_title_fingerprint,
    material_title_is_eligible,
    provider_symbol_set,
    symbol_sets_compatible,
)
from parallax.domains.news_intel.types.news_url_identity import public_url_identity_policy

_MATERIAL_MATCH_WINDOW_MS = 600_000
_GENERIC_REWRITE_SCAN_BATCH_SIZE = 1_000
_OPENNEWS_FALLBACK_INVALID_RE = re.compile(r"[\s\x00-\x1f\x7f]")


class NewsDuplicateHardCutRepairAbort(RuntimeError):
    """Raised when execute mode detects active News runtime state."""


@dataclass(frozen=True, slots=True)
class _RewriteCandidate:
    provider_item_id: str
    news_item_id: str
    fallback_url: str


@dataclass(frozen=True, slots=True)
class _RepairGroup:
    group_key: str
    news_item_ids: tuple[str, ...]
    provider_item_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RepairCandidates:
    rewrite_candidates: tuple[_RewriteCandidate, ...]
    hard_groups: tuple[_RepairGroup, ...]
    material_groups: tuple[_RepairGroup, ...]


@dataclass
class _RepairTracker:
    news_item_ids: set[str] = field(default_factory=set)
    provider_item_ids: set[str] = field(default_factory=set)
    before_edge_items: dict[str, str] = field(default_factory=dict)
    before_page_rows: dict[str, int] = field(default_factory=dict)
    before_dirty_targets: dict[str, int] = field(default_factory=dict)
    before_agent_outputs: dict[str, int] = field(default_factory=dict)

    def capture(
        self,
        conn: Any,
        *,
        news_item_ids: Sequence[str],
        provider_item_ids: Sequence[str],
    ) -> None:
        item_ids = _distinct(news_item_ids)
        item_provider_ids = _provider_item_ids_for_news_items(conn, item_ids)
        provider_ids = _distinct([*provider_item_ids, *item_provider_ids])

        new_item_ids = [news_item_id for news_item_id in item_ids if news_item_id not in self.news_item_ids]
        if new_item_ids:
            self.before_page_rows.update(_count_by_news_item_id(conn, "news_page_rows", new_item_ids))
            self.before_dirty_targets.update(_dirty_target_counts(conn, new_item_ids))
            self.before_agent_outputs.update(_agent_output_counts(conn, new_item_ids))
            self.news_item_ids.update(new_item_ids)

        new_provider_ids = [
            provider_item_id for provider_item_id in provider_ids if provider_item_id not in self.provider_item_ids
        ]
        if new_provider_ids:
            self.before_edge_items.update(_edge_assignments(conn, new_provider_ids))
            self.provider_item_ids.update(new_provider_ids)

    def finish(self, conn: Any) -> dict[str, int]:
        item_ids = sorted(self.news_item_ids)
        provider_ids = sorted(self.provider_item_ids)
        after_edge_items = _edge_assignments(conn, provider_ids)
        after_page_rows = _count_by_news_item_id(conn, "news_page_rows", item_ids)
        after_dirty_targets = _dirty_target_counts(conn, item_ids)
        after_agent_outputs = _agent_output_counts(conn, item_ids)
        existing_item_ids = set(_existing_news_item_ids(conn, item_ids))
        return {
            "edges_remapped": sum(
                1
                for provider_item_id, before_news_item_id in self.before_edge_items.items()
                if after_edge_items.get(provider_item_id) not in {None, before_news_item_id}
            ),
            "zero_edge_items_deleted": len(set(item_ids) - existing_item_ids),
            "page_rows_deleted": sum(
                max(0, int(self.before_page_rows.get(news_item_id, 0)) - int(after_page_rows.get(news_item_id, 0)))
                for news_item_id in item_ids
            ),
            "stale_dirty_targets_deleted": sum(
                max(
                    0,
                    int(self.before_dirty_targets.get(news_item_id, 0)) - int(after_dirty_targets.get(news_item_id, 0)),
                )
                for news_item_id in item_ids
            ),
            "agent_audit_rows_remapped": sum(
                max(
                    0,
                    int(self.before_agent_outputs.get(news_item_id, 0)) - int(after_agent_outputs.get(news_item_id, 0)),
                )
                for news_item_id in item_ids
            ),
        }

    def surviving_news_item_ids(self, conn: Any) -> list[str]:
        assignments = _edge_assignments(conn, sorted(self.provider_item_ids))
        return sorted(set(assignments.values()))


def repair_news_duplicates_hard_cut(
    repos: Any,
    *,
    limit: int,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    conn = repos.conn
    bounded_limit = max(0, int(limit))
    now = int(now_ms)
    result: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "dry_run": not bool(execute),
        "execute": bool(execute),
        "limit": bounded_limit,
        "now_ms": now,
        "candidate_hard_url_groups": 0,
        "candidate_generic_urls": 0,
        "candidate_material_duplicate_groups": 0,
        "hard_url_groups_repaired": 0,
        "generic_urls_rewritten": 0,
        "material_duplicate_groups_repaired": 0,
        "edges_remapped": 0,
        "zero_edge_items_deleted": 0,
        "page_rows_deleted": 0,
        "stale_dirty_targets_deleted": 0,
        "agent_audit_rows_remapped": 0,
        "dirty_targets_enqueued": 0,
    }
    if not execute:
        result.update(_candidate_summary(_repair_candidates(conn, limit=bounded_limit)))
        return result
    if bounded_limit <= 0:
        return result

    with conn.transaction():
        guard_state = _raise_if_news_runtime_active(conn, now_ms=now)
        result["active_state"] = guard_state["active_state"]
        result["advisory_locks"] = guard_state["advisory_locks"]

    candidates = _repair_candidates(conn, limit=bounded_limit)
    rewrite_candidates = candidates.rewrite_candidates
    hard_groups = candidates.hard_groups
    material_groups = candidates.material_groups
    result.update(_candidate_summary(candidates))

    tracker = _RepairTracker()
    with conn.transaction():
        guard_state = _raise_if_news_runtime_active(conn, now_ms=now)
        result["active_state"] = guard_state["active_state"]
        result["advisory_locks"] = guard_state["advisory_locks"]

        for candidate in rewrite_candidates:
            tracker.capture(
                conn,
                news_item_ids=[candidate.news_item_id],
                provider_item_ids=[candidate.provider_item_id],
            )
        result["generic_urls_rewritten"] = _rewrite_generic_opennews_urls(
            conn,
            rewrite_candidates,
            now_ms=now,
        )
        _reprocess_observations(
            repos.news,
            [candidate.provider_item_id for candidate in rewrite_candidates],
            canonical_url_overrides={
                candidate.provider_item_id: candidate.fallback_url for candidate in rewrite_candidates
            },
            now_ms=now,
        )

        repaired_hard_url_groups = 0
        for group in hard_groups:
            tracker.capture(conn, news_item_ids=group.news_item_ids, provider_item_ids=group.provider_item_ids)
            _reprocess_observations(repos.news, group.provider_item_ids, canonical_url_overrides={}, now_ms=now)
            representative_id = _canonical_key_representative_news_item_id(conn, canonical_item_key=group.group_key)
            if representative_id:
                _cleanup_old_news_items(
                    repos.news,
                    old_news_item_ids=group.news_item_ids,
                    news_item_id=representative_id,
                    now_ms=now,
                )
                _refresh_news_item(conn, repos.news, representative_id, now_ms=now)
                if _provider_items_all_assigned_to(conn, group.provider_item_ids, news_item_id=representative_id):
                    repaired_hard_url_groups += 1
        result["hard_url_groups_repaired"] = repaired_hard_url_groups

        repaired_material_duplicate_groups = 0
        for group in material_groups:
            ordered_provider_ids = _ordered_material_provider_item_ids(conn, group.provider_item_ids)
            tracker.capture(conn, news_item_ids=group.news_item_ids, provider_item_ids=ordered_provider_ids)
            _reprocess_observations(repos.news, ordered_provider_ids, canonical_url_overrides={}, now_ms=now)
            representative_id = _best_representative_for_provider_items(conn, ordered_provider_ids)
            if representative_id:
                _cleanup_old_news_items(
                    repos.news,
                    old_news_item_ids=group.news_item_ids,
                    news_item_id=representative_id,
                    now_ms=now,
                )
                _refresh_news_item(conn, repos.news, representative_id, now_ms=now)
                if _provider_items_all_assigned_to(conn, ordered_provider_ids, news_item_id=representative_id):
                    repaired_material_duplicate_groups += 1
        result["material_duplicate_groups_repaired"] = repaired_material_duplicate_groups

        survivors = tracker.surviving_news_item_ids(conn)
        result["dirty_targets_enqueued"] = _enqueue_survivor_targets(
            repos,
            news_item_ids=survivors,
            now_ms=now,
        )
        result.update(tracker.finish(conn))

    return result


def _repair_candidates(conn: Any, *, limit: int) -> _RepairCandidates:
    if limit <= 0:
        return _RepairCandidates((), (), ())
    rewrite_candidates = tuple(_generic_blocked_opennews_rewrite_candidates(conn, limit=limit))
    hard_groups = tuple(_hard_public_url_groups(conn, limit=limit))
    material_groups = tuple(
        _opennews_material_duplicate_groups(
            conn,
            limit=limit,
            exclude_provider_item_ids={
                provider_item_id for group in hard_groups for provider_item_id in group.provider_item_ids
            },
        )
    )
    return _RepairCandidates(
        rewrite_candidates=rewrite_candidates,
        hard_groups=hard_groups,
        material_groups=material_groups,
    )


def _candidate_summary(candidates: _RepairCandidates) -> dict[str, int]:
    return {
        "candidate_hard_url_groups": len(candidates.hard_groups),
        "candidate_generic_urls": len(candidates.rewrite_candidates),
        "candidate_material_duplicate_groups": len(candidates.material_groups),
    }


def _raise_if_news_runtime_active(conn: Any, *, now_ms: int) -> dict[str, Any]:
    guard_state = news_intel_hard_cut_runtime_guard(conn, now_ms=int(now_ms))
    blockers = guard_state["blockers"]
    if blockers:
        raise NewsDuplicateHardCutRepairAbort(json.dumps({"blockers": blockers}, sort_keys=True))
    return guard_state


def _generic_blocked_opennews_rewrite_candidates(conn: Any, *, limit: int) -> list[_RewriteCandidate]:
    if limit <= 0:
        return []
    candidates: list[_RewriteCandidate] = []
    offset = 0
    while len(candidates) < limit:
        rows = conn.execute(
            """
            SELECT provider_items.provider_item_id,
                   provider_items.provider_article_id,
                   provider_items.provider_article_key,
                   provider_items.canonical_url,
                   COALESCE(edges.news_item_id, '') AS news_item_id
              FROM news_provider_items AS provider_items
              JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
              LEFT JOIN news_item_observation_edges AS edges
                ON edges.provider_item_id = provider_items.provider_item_id
             WHERE lower(trim(sources.provider_type)) = 'opennews'
               AND provider_items.canonical_url ~* '^https?://'
               AND (
                 provider_items.provider_article_id <> ''
                 OR provider_items.provider_article_key <> ''
               )
             ORDER BY provider_items.provider_observed_at_ms DESC,
                      provider_items.provider_item_id ASC
             LIMIT %s OFFSET %s
            """,
            (_GENERIC_REWRITE_SCAN_BATCH_SIZE, offset),
        ).fetchall()
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            policy = public_url_identity_policy(row["canonical_url"])
            if policy.allowed or not policy.normalized_url:
                continue
            article_id = _opennews_article_id(row["provider_article_id"], row["provider_article_key"])
            if not article_id:
                continue
            fallback_url = f"opennews://item/{article_id}"
            if str(row["canonical_url"] or "") == fallback_url:
                continue
            candidates.append(
                _RewriteCandidate(
                    provider_item_id=str(row["provider_item_id"]),
                    news_item_id=str(row["news_item_id"] or ""),
                    fallback_url=fallback_url,
                )
            )
            if len(candidates) >= limit:
                break
    return candidates


def _rewrite_generic_opennews_urls(
    conn: Any,
    candidates: Sequence[_RewriteCandidate],
    *,
    now_ms: int,
) -> int:
    rewritten = 0
    for candidate in candidates:
        cursor = conn.execute(
            """
            UPDATE news_provider_items
               SET canonical_url = %s
             WHERE provider_item_id = %s
               AND canonical_url IS DISTINCT FROM %s
            """,
            (candidate.fallback_url, candidate.provider_item_id, candidate.fallback_url),
        )
        rewritten += int(cursor.rowcount or 0)
        conn.execute(
            """
            UPDATE news_item_observation_edges
               SET evidence_json = jsonb_set(
                     evidence_json,
                     '{item_payload,canonical_url}',
                     to_jsonb(%s::text),
                     true
                   ),
                   last_seen_at_ms = GREATEST(last_seen_at_ms, %s)
             WHERE provider_item_id = %s
            """,
            (candidate.fallback_url, int(now_ms), candidate.provider_item_id),
        )
    return rewritten


def _hard_public_url_groups(conn: Any, *, limit: int) -> list[_RepairGroup]:
    if limit <= 0:
        return []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    offset = 0
    while True:
        rows = conn.execute(
            """
            SELECT items.news_item_id,
                   items.canonical_url,
                   items.canonical_item_key,
                   items.dedup_key_kind,
                   COALESCE(edge_summary.provider_item_ids, ARRAY[]::text[]) AS provider_item_ids
              FROM news_items AS items
              LEFT JOIN LATERAL (
                SELECT array_agg(edges.provider_item_id ORDER BY edges.provider_item_id) AS provider_item_ids
                  FROM news_item_observation_edges AS edges
                 WHERE edges.news_item_id = items.news_item_id
              ) AS edge_summary ON true
             WHERE items.canonical_url ~* '^https?://'
             ORDER BY items.canonical_url ASC, items.updated_at_ms DESC, items.news_item_id ASC
             LIMIT %s OFFSET %s
            """,
            (_GENERIC_REWRITE_SCAN_BATCH_SIZE, offset),
        ).fetchall()
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            policy = public_url_identity_policy(row["canonical_url"])
            if not policy.allowed:
                continue
            grouped[policy.identity_key].append(row)

    groups: list[_RepairGroup] = []
    for identity_key, group_rows in sorted(grouped.items()):
        needs_repair = len(group_rows) > 1 or any(
            str(row["canonical_item_key"] or "") != identity_key or str(row["dedup_key_kind"] or "") != "canonical_url"
            for row in group_rows
        )
        if not needs_repair:
            continue
        news_item_ids = _distinct(str(row["news_item_id"]) for row in group_rows)
        provider_item_ids = _distinct(
            provider_item_id for row in group_rows for provider_item_id in list(row["provider_item_ids"] or [])
        )
        groups.append(
            _RepairGroup(
                group_key=identity_key,
                news_item_ids=tuple(news_item_ids),
                provider_item_ids=tuple(provider_item_ids),
            )
        )
        if len(groups) >= limit:
            break
    return groups


def _opennews_material_duplicate_groups(
    conn: Any,
    *,
    limit: int,
    exclude_provider_item_ids: set[str] | None = None,
) -> list[_RepairGroup]:
    if limit <= 0:
        return []
    excluded_provider_ids = set(exclude_provider_item_ids or set())
    keyed_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    offset = 0
    while True:
        rows = conn.execute(
            """
            SELECT items.news_item_id,
                   items.source_id,
                   items.canonical_url,
                   items.canonical_item_key,
                   items.dedup_key_kind,
                   items.title,
                   items.published_at_ms,
                   items.provider_token_impacts_json,
                   COALESCE(edge_summary.provider_item_ids, ARRAY[]::text[]) AS provider_item_ids
              FROM news_items AS items
              JOIN news_sources AS sources ON sources.source_id = items.source_id
              LEFT JOIN LATERAL (
                SELECT array_agg(edges.provider_item_id ORDER BY edges.provider_item_id) AS provider_item_ids
                  FROM news_item_observation_edges AS edges
                 WHERE edges.news_item_id = items.news_item_id
              ) AS edge_summary ON true
             WHERE lower(trim(sources.provider_type)) = 'opennews'
             ORDER BY items.source_id ASC, items.published_at_ms ASC, items.news_item_id ASC
             LIMIT %s OFFSET %s
            """,
            (_GENERIC_REWRITE_SCAN_BATCH_SIZE, offset),
        ).fetchall()
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            fingerprint = material_title_fingerprint(row["title"])
            if not material_title_is_eligible(fingerprint):
                continue
            payload = dict(row)
            payload["material_fingerprint"] = fingerprint
            payload["material_symbols"] = provider_symbol_set(row["provider_token_impacts_json"])
            keyed_rows[(str(row["source_id"]), fingerprint)].append(payload)

    groups: list[_RepairGroup] = []
    for (source_id, fingerprint), source_rows in sorted(keyed_rows.items()):
        clusters: list[list[dict[str, Any]]] = []
        for row in source_rows:
            cluster = _matching_material_cluster(clusters, row)
            if cluster is None:
                clusters.append([row])
            else:
                cluster.append(row)
        for cluster in clusters:
            news_item_ids = _distinct(str(row["news_item_id"]) for row in cluster)
            if len(news_item_ids) <= 1:
                continue
            provider_item_ids = _distinct(
                provider_item_id for row in cluster for provider_item_id in list(row["provider_item_ids"] or [])
            )
            if any(provider_item_id in excluded_provider_ids for provider_item_id in provider_item_ids):
                continue
            groups.append(
                _RepairGroup(
                    group_key=f"{source_id}:{fingerprint}:{len(groups)}",
                    news_item_ids=tuple(news_item_ids),
                    provider_item_ids=tuple(provider_item_ids),
                )
            )
            if len(groups) >= limit:
                return groups
    return groups


def _matching_material_cluster(
    clusters: Sequence[list[dict[str, Any]]],
    row: dict[str, Any],
) -> list[dict[str, Any]] | None:
    row_published_at = int(row["published_at_ms"])
    row_symbols = set(row["material_symbols"])
    for cluster in clusters:
        if any(
            abs(row_published_at - int(candidate["published_at_ms"])) <= _MATERIAL_MATCH_WINDOW_MS
            and symbol_sets_compatible(row_symbols, set(candidate["material_symbols"]))
            for candidate in cluster
        ):
            return cluster
    return None


def _reprocess_observations(
    repo: Any,
    provider_item_ids: Sequence[str],
    *,
    canonical_url_overrides: Mapping[str, str],
    now_ms: int,
) -> None:
    ids = _distinct(provider_item_ids)
    if not ids:
        return
    rows = repo.conn.execute(
        """
        SELECT edges.provider_item_id,
               edges.evidence_json #> '{item_payload}' AS item_payload,
               provider_items.canonical_url AS provider_canonical_url,
               provider_items.provider_payload_status,
               items.canonical_url AS item_canonical_url,
               items.title,
               items.summary,
               items.body_text,
               items.language,
               items.published_at_ms,
               items.fetched_at_ms,
               items.content_hash,
               items.title_fingerprint,
               items.provider_signal_json,
               items.provider_token_impacts_json
          FROM news_item_observation_edges AS edges
          JOIN news_provider_items AS provider_items
            ON provider_items.provider_item_id = edges.provider_item_id
          JOIN news_items AS items ON items.news_item_id = edges.news_item_id
         WHERE edges.provider_item_id = ANY(%s::text[])
         ORDER BY array_position(%s::text[], edges.provider_item_id)
        """,
        (ids, ids),
    ).fetchall()
    for row in rows:
        provider_item_id = str(row["provider_item_id"])
        item_payload = _json_dict(row["item_payload"])
        repo.upsert_canonical_news_item(
            provider_item_id=provider_item_id,
            canonical_url=str(
                canonical_url_overrides.get(provider_item_id)
                or item_payload.get("canonical_url")
                or row["provider_canonical_url"]
                or row["item_canonical_url"]
                or ""
            ),
            title=str(item_payload.get("title") or row["title"] or ""),
            summary=str(item_payload.get("summary") or row["summary"] or ""),
            body_text=str(item_payload.get("body_text") or row["body_text"] or ""),
            language=str(item_payload.get("language") or row["language"] or "en"),
            published_at_ms=int(item_payload.get("published_at_ms") or row["published_at_ms"] or 0),
            fetched_at_ms=int(item_payload.get("fetched_at_ms") or row["fetched_at_ms"] or 0),
            content_hash=str(item_payload.get("content_hash") or row["content_hash"] or ""),
            title_fingerprint=str(item_payload.get("title_fingerprint") or row["title_fingerprint"] or ""),
            provider_signal=_json_dict(item_payload.get("provider_signal_json") or row["provider_signal_json"]),
            provider_token_impacts=_json_list(
                item_payload.get("provider_token_impacts_json") or row["provider_token_impacts_json"]
            ),
            provider_payload_status=str(row["provider_payload_status"] or ""),
            now_ms=int(now_ms),
            commit=False,
        )


def _cleanup_old_news_items(
    repo: Any,
    *,
    old_news_item_ids: Sequence[str],
    news_item_id: str,
    now_ms: int,
) -> None:
    for old_news_item_id in _distinct(old_news_item_ids):
        if old_news_item_id == str(news_item_id):
            continue
        if not repo._lock_news_item_for_edge_remap_cleanup(news_item_id=old_news_item_id):
            continue
        repo._refresh_news_item_observation_summary(news_item_id=old_news_item_id, now_ms=now_ms)
        if repo._news_item_has_observation_edges(news_item_id=old_news_item_id):
            repo._reselect_news_item_representative_from_edges(news_item_id=old_news_item_id, now_ms=now_ms)
            repo._clear_item_scoped_derived_facts(news_item_id=old_news_item_id)
            continue
        repo._remap_item_scoped_agent_outputs_to_news_item(
            old_news_item_ids=[old_news_item_id],
            news_item_id=str(news_item_id),
            now_ms=now_ms,
        )
        repo._remap_projection_dirty_targets_to_news_item(
            old_news_item_ids=[old_news_item_id],
            news_item_id=str(news_item_id),
            now_ms=now_ms,
        )
        repo._delete_zero_edge_news_item(news_item_id=old_news_item_id)


def _refresh_news_item(conn: Any, repo: Any, news_item_id: str, *, now_ms: int) -> None:
    if _news_item_exists(conn, news_item_id):
        repo._refresh_news_item_observation_summary(news_item_id=news_item_id, now_ms=now_ms)


def _enqueue_survivor_targets(repos: Any, *, news_item_ids: Sequence[str], now_ms: int) -> int:
    targets = [
        {
            "projection_name": projection_name,
            "target_kind": "news_item",
            "target_id": news_item_id,
            "source_watermark_ms": int(now_ms),
            "priority": 5,
            "due_at_ms": int(now_ms),
        }
        for news_item_id in _distinct(news_item_ids)
        for projection_name in ("page", "brief_input")
    ]
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason="ops_news_duplicate_hard_cut_repair",
            now_ms=int(now_ms),
            commit=False,
        )
    )


def _ordered_material_provider_item_ids(conn: Any, provider_item_ids: Sequence[str]) -> list[str]:
    ids = _distinct(provider_item_ids)
    if not ids:
        return []
    rows = conn.execute(
        """
        SELECT edges.provider_item_id,
               items.dedup_key_kind,
               items.canonical_url,
               provider_items.provider_payload_status,
               items.published_at_ms
          FROM news_item_observation_edges AS edges
          JOIN news_items AS items ON items.news_item_id = edges.news_item_id
          JOIN news_provider_items AS provider_items
            ON provider_items.provider_item_id = edges.provider_item_id
         WHERE edges.provider_item_id = ANY(%s::text[])
         ORDER BY
           CASE
             WHEN items.dedup_key_kind = 'canonical_url'
              AND items.canonical_url ~* '^https?://'
               THEN 0
             ELSE 1
           END,
           CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
           items.published_at_ms DESC,
           edges.provider_item_id ASC
        """,
        (ids,),
    ).fetchall()
    return [str(row["provider_item_id"]) for row in rows]


def _best_representative_for_provider_items(conn: Any, provider_item_ids: Sequence[str]) -> str:
    ids = _distinct(provider_item_ids)
    if not ids:
        return ""
    row = conn.execute(
        """
        SELECT items.news_item_id
          FROM news_item_observation_edges AS edges
          JOIN news_items AS items ON items.news_item_id = edges.news_item_id
          JOIN news_provider_items AS provider_items
            ON provider_items.provider_item_id = edges.provider_item_id
         WHERE edges.provider_item_id = ANY(%s::text[])
         ORDER BY
           CASE
             WHEN items.dedup_key_kind = 'canonical_url'
              AND items.canonical_url ~* '^https?://'
               THEN 0
             ELSE 1
           END,
           CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
           items.published_at_ms DESC,
           items.news_item_id ASC
         LIMIT 1
        """,
        (ids,),
    ).fetchone()
    return str(row["news_item_id"]) if row is not None else ""


def _canonical_key_representative_news_item_id(conn: Any, *, canonical_item_key: str) -> str:
    row = conn.execute(
        "SELECT news_item_id FROM news_items WHERE canonical_item_key = %s",
        (str(canonical_item_key),),
    ).fetchone()
    return str(row["news_item_id"]) if row is not None else ""


def _provider_item_ids_for_news_items(conn: Any, news_item_ids: Sequence[str]) -> list[str]:
    ids = _distinct(news_item_ids)
    if not ids:
        return []
    rows = conn.execute(
        """
        SELECT provider_item_id
          FROM news_item_observation_edges
         WHERE news_item_id = ANY(%s::text[])
         ORDER BY provider_item_id ASC
        """,
        (ids,),
    ).fetchall()
    return [str(row["provider_item_id"]) for row in rows]


def _edge_assignments(conn: Any, provider_item_ids: Sequence[str]) -> dict[str, str]:
    ids = _distinct(provider_item_ids)
    if not ids:
        return {}
    rows = conn.execute(
        """
        SELECT provider_item_id, news_item_id
          FROM news_item_observation_edges
         WHERE provider_item_id = ANY(%s::text[])
        """,
        (ids,),
    ).fetchall()
    return {str(row["provider_item_id"]): str(row["news_item_id"]) for row in rows}


def _provider_items_all_assigned_to(conn: Any, provider_item_ids: Sequence[str], *, news_item_id: str) -> bool:
    ids = _distinct(provider_item_ids)
    if not ids:
        return False
    assignments = _edge_assignments(conn, ids)
    return set(assignments) == set(ids) and set(assignments.values()) == {str(news_item_id)}


def _count_by_news_item_id(conn: Any, table_name: str, news_item_ids: Sequence[str]) -> dict[str, int]:
    ids = _distinct(news_item_ids)
    if not ids:
        return {}
    rows = conn.execute(
        f"""
        SELECT news_item_id, COUNT(*)::int AS count
          FROM {table_name}
         WHERE news_item_id = ANY(%s::text[])
         GROUP BY news_item_id
        """,
        (ids,),
    ).fetchall()
    return {str(row["news_item_id"]): int(row["count"] or 0) for row in rows}


def _dirty_target_counts(conn: Any, news_item_ids: Sequence[str]) -> dict[str, int]:
    ids = _distinct(news_item_ids)
    if not ids:
        return {}
    rows = conn.execute(
        """
        SELECT target_id AS news_item_id, COUNT(*)::int AS count
          FROM news_projection_dirty_targets
         WHERE target_kind = 'news_item'
           AND target_id = ANY(%s::text[])
         GROUP BY target_id
        """,
        (ids,),
    ).fetchall()
    return {str(row["news_item_id"]): int(row["count"] or 0) for row in rows}


def _agent_output_counts(conn: Any, news_item_ids: Sequence[str]) -> dict[str, int]:
    ids = _distinct(news_item_ids)
    if not ids:
        return {}
    run_counts = _count_by_news_item_id(conn, "news_item_agent_runs", ids)
    brief_counts = _count_by_news_item_id(conn, "news_item_agent_briefs", ids)
    return {
        news_item_id: int(run_counts.get(news_item_id, 0)) + int(brief_counts.get(news_item_id, 0))
        for news_item_id in ids
    }


def _existing_news_item_ids(conn: Any, news_item_ids: Sequence[str]) -> list[str]:
    ids = _distinct(news_item_ids)
    if not ids:
        return []
    rows = conn.execute(
        """
        SELECT news_item_id
          FROM news_items
         WHERE news_item_id = ANY(%s::text[])
        """,
        (ids,),
    ).fetchall()
    return [str(row["news_item_id"]) for row in rows]


def _news_item_exists(conn: Any, news_item_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 AS exists FROM news_items WHERE news_item_id = %s",
        (str(news_item_id),),
    ).fetchone()
    return row is not None


def _opennews_article_id(provider_article_id: Any, provider_article_key: Any) -> str:
    article_id = str(provider_article_id or "").strip()
    if not article_id:
        key = str(provider_article_key or "").strip()
        prefix = "opennews:"
        if key.lower().startswith(prefix):
            article_id = key[len(prefix) :].strip()
    if not article_id or _OPENNEWS_FALLBACK_INVALID_RE.search(article_id):
        return ""
    return article_id


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _distinct(values: Any) -> list[str]:
    return [value for value in dict.fromkeys(str(item) for item in values if str(item or "").strip()) if value]


__all__ = [
    "NewsDuplicateHardCutRepairAbort",
    "repair_news_duplicates_hard_cut",
]
