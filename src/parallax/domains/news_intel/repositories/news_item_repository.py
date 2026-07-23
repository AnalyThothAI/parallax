from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.repositories.news_repository_support import (
    _MATERIAL_MATCH_WINDOW_MS,
    _canonical_identity_with_evidence,
    _compact_error,
    _distinct_old_news_item_ids,
    _entity_payload,
    _fact_payload,
    _json,
    _json_dict,
    _market_scope_payload,
    _material_symbol_key_for_impacts,
    _material_window_bucket_ms_for_published_at,
    _material_window_bucket_ms_values_for_match_window,
    _mention_payload,
    _news_item_aggregate_changed,
    _news_item_content_changed,
    _news_item_edge_changed,
    _optional_returning_row,
    _representative_payload_should_replace,
    _required_returning_row,
    _story_identity_payload,
)
from parallax.domains.news_intel.types.news_canonical_identity import (
    CANONICAL_POLICY_VERSION,
    CanonicalIdentity,
    canonical_identity_for_observation,
    provider_global_article_key,
)
from parallax.domains.news_intel.types.news_extraction import (
    NewsEntity,
    NewsFactCandidate,
    NewsTokenMention,
)
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_material_identity import (
    material_title_fingerprint,
    material_title_is_eligible,
    provider_symbol_set,
    symbol_sets_compatible,
)
from parallax.domains.news_intel.types.news_story_identity import NewsStoryIdentity
from parallax.platform.db.write_contract import expect_mutation_count, mutation_count
from parallax.platform.validation import require_nonnegative_int, require_positive_int


class NewsItemRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def upsert_canonical_news_item(
        self,
        *,
        provider_item_id: str,
        canonical_url: str,
        title: str,
        summary: str = "",
        body_text: str = "",
        language: str = "en",
        published_at_ms: int | None = None,
        fetched_at_ms: int,
        content_hash: str,
        title_fingerprint: str,
        now_ms: int,
        provider_signal: Mapping[str, Any] | None = None,
        provider_token_impacts: Sequence[Mapping[str, Any]] | None = None,
        provider_payload_status: str | None = None,
    ) -> dict[str, Any]:
        item_published_at_ms = int(published_at_ms if published_at_ms is not None else fetched_at_ms)
        provider_signal_payload = dict(provider_signal or {})
        provider_token_impacts_payload = [dict(item) for item in provider_token_impacts or []]
        observation = self.conn.execute(
            """
            SELECT provider_items.*, sources.provider_type, sources.source_domain
              FROM news_provider_items AS provider_items
              JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
             WHERE provider_items.provider_item_id = %s
            """,
            (provider_item_id,),
        ).fetchone()
        if observation is None:
            raise ValueError(f"news provider item does not exist: {provider_item_id}")
        observation_source_id = str(observation["source_id"])
        observation_source_domain = str(observation["source_domain"])
        identity = canonical_identity_for_observation(
            provider_type=str(observation["provider_type"]),
            source_id=observation_source_id,
            provider_article_id=str(observation["provider_article_id"] or ""),
            canonical_url=canonical_url,
            content_hash=content_hash,
            title_fingerprint=title_fingerprint,
            title=title,
            summary=summary,
            body_text=body_text,
            published_at_ms=item_published_at_ms,
        )
        provider_article_key = provider_global_article_key(
            provider_type=str(observation["provider_type"] or ""),
            provider_article_id=str(observation["provider_article_id"] or ""),
        )
        identity = self._material_duplicate_identity_for_observation(
            identity=identity,
            provider_type=str(observation["provider_type"] or ""),
            source_id=observation_source_id,
            title=str(title),
            published_at_ms=item_published_at_ms,
            provider_token_impacts=provider_token_impacts_payload,
        )
        observation_payload_status = str(observation["provider_payload_status"] or "").strip().lower()
        incoming_payload_status = str(provider_payload_status or "").strip().lower()
        effective_payload_status = (
            incoming_payload_status if incoming_payload_status in {"partial", "ready"} else observation_payload_status
        )
        ready_content_identity = identity.dedup_key_kind == "content_hash" and effective_payload_status == "ready"
        hard_url_identity = identity.dedup_key_kind == "canonical_url"
        promotes_provider_article_identity = hard_url_identity or ready_content_identity
        if provider_article_key:
            existing_provider_article_item = self.conn.execute(
                """
                SELECT items.news_item_id,
                       items.provider_item_id,
                       items.source_id,
                       items.canonical_item_key,
                       items.dedup_key_kind,
                       items.dedup_key_confidence,
                       items.url_identity_kind,
                       provider_items.provider_payload_status
                  FROM news_item_observation_edges AS edges
                  JOIN news_items AS items ON items.news_item_id = edges.news_item_id
                  JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = items.provider_item_id
                 WHERE edges.provider_article_key = %s
                 ORDER BY
                   CASE
                     WHEN items.dedup_key_kind = 'content_hash'
                      AND items.url_identity_kind = 'article'
                      AND provider_items.provider_payload_status = 'ready'
                       THEN 0
                     ELSE 1
                   END,
                   edges.provider_article_key ASC,
                   items.source_id ASC,
                   items.provider_item_id ASC
                 LIMIT 1
                """,
                (provider_article_key,),
            ).fetchone()
            reuse_provider_article_item = (
                existing_provider_article_item is not None
                and str(existing_provider_article_item["canonical_item_key"] or "")
                and str(existing_provider_article_item["canonical_item_key"]) != identity.canonical_item_key
            )
            if reuse_provider_article_item and promotes_provider_article_identity:
                if hard_url_identity:
                    reuse_provider_article_item = False
                else:
                    existing_ready_content_identity = (
                        str(existing_provider_article_item["dedup_key_kind"] or "") == "content_hash"
                        and str(existing_provider_article_item["url_identity_kind"] or "") == "article"
                        and str(existing_provider_article_item["provider_payload_status"] or "") == "ready"
                    )
                    same_provider_item = str(existing_provider_article_item["provider_item_id"] or "") == str(
                        provider_item_id
                    )
                    if same_provider_item:
                        reuse_provider_article_item = False
                    elif existing_ready_content_identity:
                        existing_tie_breaker = (
                            provider_article_key,
                            str(existing_provider_article_item["source_id"] or ""),
                            str(existing_provider_article_item["provider_item_id"] or ""),
                        )
                        incoming_tie_breaker = (provider_article_key, observation_source_id, str(provider_item_id))
                        reuse_provider_article_item = existing_tie_breaker <= incoming_tie_breaker
                    else:
                        reuse_provider_article_item = False
            if reuse_provider_article_item and existing_provider_article_item is not None:
                identity = CanonicalIdentity(
                    canonical_item_key=str(existing_provider_article_item["canonical_item_key"]),
                    news_item_id=str(existing_provider_article_item["news_item_id"]),
                    dedup_key_kind=str(existing_provider_article_item["dedup_key_kind"] or identity.dedup_key_kind),
                    dedup_key_confidence=str(
                        existing_provider_article_item["dedup_key_confidence"] or identity.dedup_key_confidence
                    ),
                    url_identity_kind=str(
                        existing_provider_article_item["url_identity_kind"] or identity.url_identity_kind
                    ),
                    match_type="same_provider_article_id",
                    match_confidence="strong",
                    evidence={
                        **dict(identity.evidence),
                        "provider_article_key": provider_article_key,
                        "provider_article_id": str(observation["provider_article_id"] or ""),
                        "provider_article_existing_news_item_id": str(existing_provider_article_item["news_item_id"]),
                    },
                )
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(
              ('x' || substr(md5(%s), 1, 16))::bit(64)::bigint
            )
            """,
            (identity.canonical_item_key,),
        )
        item_payload = {
            "provider_item_id": str(provider_item_id),
            "source_id": observation_source_id,
            "source_domain": observation_source_domain,
            "canonical_url": str(canonical_url),
            "title": str(title),
            "summary": str(summary),
            "body_text": str(body_text),
            "language": str(language),
            "published_at_ms": item_published_at_ms,
            "fetched_at_ms": int(fetched_at_ms),
            "content_hash": str(content_hash),
            "title_fingerprint": str(title_fingerprint),
            "provider_signal_json": provider_signal_payload,
            "provider_token_impacts_json": provider_token_impacts_payload,
        }
        existing = self.conn.execute(
            "SELECT * FROM news_items WHERE canonical_item_key = %s",
            (identity.canonical_item_key,),
        ).fetchone()
        existing_representative_provider = None
        if existing is not None:
            existing_representative_provider = self.conn.execute(
                """
                SELECT provider_items.provider_article_id,
                       provider_items.provider_payload_status,
                       sources.provider_type
                  FROM news_provider_items AS provider_items
                  JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
                 WHERE provider_items.provider_item_id = %s
                """,
                (str(existing["provider_item_id"]),),
            ).fetchone()
        existing_representative_provider_article_key = (
            provider_global_article_key(
                provider_type=str(existing_representative_provider["provider_type"] or ""),
                provider_article_id=str(existing_representative_provider["provider_article_id"] or ""),
            )
            if existing_representative_provider is not None
            else ""
        )
        existing_representative = (
            {
                **dict(existing),
                "provider_payload_status": (
                    str(existing_representative_provider["provider_payload_status"] or "")
                    if existing_representative_provider is not None
                    else ""
                ),
                "provider_article_key": existing_representative_provider_article_key,
            }
            if existing is not None
            else None
        )
        incoming_representative = {
            **item_payload,
            "provider_payload_status": str(observation["provider_payload_status"] or ""),
            "provider_article_key": provider_article_key,
        }
        replace_representative = existing is None or _representative_payload_should_replace(
            existing_representative or {},
            incoming_representative,
        )
        content_changed = (
            existing is not None and replace_representative and _news_item_content_changed(existing, item_payload)
        )
        item_id = str(existing["news_item_id"]) if existing is not None else identity.news_item_id
        existing_edge = self.conn.execute(
            "SELECT * FROM news_item_observation_edges WHERE provider_item_id = %s",
            (provider_item_id,),
        ).fetchone()
        previous_edge_news_item_id = (
            str(existing_edge["news_item_id"])
            if existing_edge is not None and str(existing_edge["news_item_id"]) != item_id
            else None
        )
        cursor = self.conn.execute(
            """
            INSERT INTO news_items (
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, summary, body_text, language, published_at_ms, fetched_at_ms,
              content_hash, title_fingerprint, provider_signal_json, provider_token_impacts_json,
              canonical_item_key, dedup_key_kind, dedup_key_confidence, url_identity_kind,
              canonical_policy_version, created_at_ms, updated_at_ms
            )
            VALUES (
              %(item_id)s, %(provider_item_id)s, %(source_id)s, %(source_domain)s,
              %(canonical_url)s, %(title)s, %(summary)s, %(body_text)s, %(language)s,
              %(published_at_ms)s, %(fetched_at_ms)s, %(content_hash)s,
              %(title_fingerprint)s, %(provider_signal_json)s, %(provider_token_impacts_json)s,
              %(canonical_item_key)s, %(dedup_key_kind)s, %(dedup_key_confidence)s,
              %(url_identity_kind)s, %(canonical_policy_version)s, %(created_at_ms)s,
              %(updated_at_ms)s
            )
            ON CONFLICT (canonical_item_key) WHERE canonical_item_key <> '' DO UPDATE SET
              provider_item_id = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_item_id
                ELSE news_items.provider_item_id
              END,
              source_id = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.source_id
                ELSE news_items.source_id
              END,
              source_domain = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.source_domain
                ELSE news_items.source_domain
              END,
              canonical_url = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.canonical_url
                ELSE news_items.canonical_url
              END,
              title = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.title
                ELSE news_items.title
              END,
              summary = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.summary
                ELSE news_items.summary
              END,
              body_text = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.body_text
                ELSE news_items.body_text
              END,
              language = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.language
                ELSE news_items.language
              END,
              published_at_ms = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.published_at_ms
                ELSE news_items.published_at_ms
              END,
              fetched_at_ms = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.fetched_at_ms
                ELSE news_items.fetched_at_ms
              END,
              content_hash = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.content_hash
                ELSE news_items.content_hash
              END,
              title_fingerprint = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.title_fingerprint
                ELSE news_items.title_fingerprint
              END,
              provider_signal_json = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_signal_json
                ELSE news_items.provider_signal_json
              END,
              provider_token_impacts_json = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_token_impacts_json
                ELSE news_items.provider_token_impacts_json
              END,
              dedup_key_kind = EXCLUDED.dedup_key_kind,
              dedup_key_confidence = EXCLUDED.dedup_key_confidence,
              url_identity_kind = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.url_identity_kind
                ELSE news_items.url_identity_kind
              END,
              canonical_policy_version = EXCLUDED.canonical_policy_version,
              lifecycle_status = CASE
                WHEN NOT %(replace_representative)s THEN news_items.lifecycle_status
                WHEN news_items.content_hash = EXCLUDED.content_hash THEN news_items.lifecycle_status
                ELSE 'raw'
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            {
                "item_id": item_id,
                "provider_item_id": item_payload["provider_item_id"],
                "source_id": item_payload["source_id"],
                "source_domain": item_payload["source_domain"],
                "canonical_url": item_payload["canonical_url"],
                "title": item_payload["title"],
                "summary": item_payload["summary"],
                "body_text": item_payload["body_text"],
                "language": item_payload["language"],
                "published_at_ms": item_published_at_ms,
                "fetched_at_ms": int(fetched_at_ms),
                "content_hash": item_payload["content_hash"],
                "title_fingerprint": item_payload["title_fingerprint"],
                "provider_signal_json": _json(provider_signal_payload),
                "provider_token_impacts_json": _json(provider_token_impacts_payload),
                "canonical_item_key": identity.canonical_item_key,
                "dedup_key_kind": identity.dedup_key_kind,
                "dedup_key_confidence": identity.dedup_key_confidence,
                "url_identity_kind": identity.url_identity_kind,
                "canonical_policy_version": CANONICAL_POLICY_VERSION,
                "created_at_ms": int(now_ms),
                "updated_at_ms": int(now_ms),
                "replace_representative": replace_representative,
            },
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        edge_evidence = {
            **dict(identity.evidence),
            "provider_article_key": provider_article_key or None,
            "item_payload": {
                "canonical_url": item_payload["canonical_url"],
                "title": item_payload["title"],
                "summary": item_payload["summary"],
                "body_text": item_payload["body_text"],
                "language": item_payload["language"],
                "published_at_ms": item_payload["published_at_ms"],
                "fetched_at_ms": item_payload["fetched_at_ms"],
                "content_hash": item_payload["content_hash"],
                "title_fingerprint": item_payload["title_fingerprint"],
                "provider_signal_json": provider_signal_payload,
                "provider_token_impacts_json": provider_token_impacts_payload,
                "url_identity_kind": identity.url_identity_kind,
            },
        }
        edge_payload = {
            "news_item_id": str(returned_row["news_item_id"]),
            "source_id": observation_source_id,
            "provider_article_key": provider_article_key,
            "match_type": identity.match_type,
            "match_confidence": identity.match_confidence,
            "policy_version": CANONICAL_POLICY_VERSION,
            "evidence_json": edge_evidence,
        }
        cursor = self.conn.execute(
            """
            INSERT INTO news_item_observation_edges (
              provider_item_id, news_item_id, source_id, provider_article_key, match_type,
              match_confidence, policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_item_id) DO UPDATE SET
              news_item_id = EXCLUDED.news_item_id,
              source_id = EXCLUDED.source_id,
              provider_article_key = EXCLUDED.provider_article_key,
              match_type = EXCLUDED.match_type,
              match_confidence = EXCLUDED.match_confidence,
              policy_version = EXCLUDED.policy_version,
              evidence_json = EXCLUDED.evidence_json,
              last_seen_at_ms = EXCLUDED.last_seen_at_ms
            """,
            (
                provider_item_id,
                edge_payload["news_item_id"],
                edge_payload["source_id"],
                edge_payload["provider_article_key"],
                edge_payload["match_type"],
                edge_payload["match_confidence"],
                edge_payload["policy_version"],
                _json(edge_payload["evidence_json"]),
                int(now_ms),
                int(now_ms),
            ),
        )
        expect_mutation_count(cursor, expected=1, error_code="news_repository_rowcount_invalid")
        provider_article_remapped_old_item_ids: list[str] = []
        if provider_article_key and promotes_provider_article_identity:
            provider_article_remapped_old_item_ids = self._remap_provider_article_edges_to_news_item(
                provider_article_key=provider_article_key,
                news_item_id=str(returned_row["news_item_id"]),
                now_ms=now_ms,
                remap_reason="hard_canonical_url" if hard_url_identity else "ready_content_hash",
            )
        material_remapped_old_item_ids: list[str] = []
        if hard_url_identity:
            material_remapped_old_item_ids = self._remap_material_duplicate_edges_to_news_item(
                source_id=observation_source_id,
                news_item_id=str(returned_row["news_item_id"]),
                canonical_item_key=identity.canonical_item_key,
                title=str(title),
                published_at_ms=item_published_at_ms,
                provider_token_impacts=provider_token_impacts_payload,
                now_ms=now_ms,
            )
        row = self._refresh_news_item_observation_summary(
            news_item_id=str(returned_row["news_item_id"]),
            now_ms=now_ms,
        )
        aggregate_changed = existing is not None and _news_item_aggregate_changed(existing, row)
        edge_changed = (
            existing_edge is None
            or _news_item_edge_changed(
                existing_edge,
                edge_payload,
            )
            or bool(provider_article_remapped_old_item_ids)
            or bool(material_remapped_old_item_ids)
        )
        remapped_edge = previous_edge_news_item_id is not None
        affected_news_item_ids = [str(row["news_item_id"])]
        old_news_item_ids = list(
            dict.fromkeys(
                [
                    item_id
                    for item_id in [
                        previous_edge_news_item_id,
                        *provider_article_remapped_old_item_ids,
                        *material_remapped_old_item_ids,
                    ]
                    if item_id
                ]
            )
        )
        if old_news_item_ids:
            remapped_edge = True
        for old_news_item_id in old_news_item_ids:
            affected_news_item_ids.append(old_news_item_id)
            if not self._lock_news_item_for_edge_remap_cleanup(news_item_id=old_news_item_id):
                continue
            self._refresh_news_item_observation_summary(
                news_item_id=old_news_item_id,
                now_ms=now_ms,
                required=False,
            )
            if self._news_item_has_observation_edges(news_item_id=old_news_item_id):
                self._reselect_news_item_representative_from_edges(
                    news_item_id=old_news_item_id,
                    now_ms=now_ms,
                )
                self._clear_item_scoped_derived_facts(news_item_id=old_news_item_id)
                continue
            self._remap_projection_dirty_targets_to_news_item(
                old_news_item_ids=[old_news_item_id],
                news_item_id=str(row["news_item_id"]),
                now_ms=now_ms,
            )
            deleted_old_item = self._delete_zero_edge_news_item(news_item_id=old_news_item_id)
            if not deleted_old_item:
                self._reselect_news_item_representative_from_edges(
                    news_item_id=old_news_item_id,
                    now_ms=now_ms,
                )
                self._clear_item_scoped_derived_facts(news_item_id=old_news_item_id)
        if existing is None and not remapped_edge:
            status = "inserted"
        elif content_changed or aggregate_changed or edge_changed or remapped_edge:
            status = "updated"
        else:
            status = "duplicate"
        if content_changed:
            self._clear_item_scoped_derived_facts(news_item_id=item_id)
            self.mark_news_items_for_reprocessing(news_item_ids=[item_id], now_ms=now_ms)
        return {
            **dict(row),
            "status": status,
            "affected_news_item_ids": list(dict.fromkeys(affected_news_item_ids)),
        }

    def _material_duplicate_identity_for_observation(
        self,
        *,
        identity: CanonicalIdentity,
        provider_type: str,
        source_id: str,
        title: str,
        published_at_ms: int,
        provider_token_impacts: Sequence[Mapping[str, Any]],
    ) -> CanonicalIdentity:
        if str(provider_type or "").strip().lower() != "opennews":
            return identity
        material_fingerprint = material_title_fingerprint(title)
        if not material_title_is_eligible(material_fingerprint):
            return identity

        material_window_bucket_ms = _material_window_bucket_ms_for_published_at(published_at_ms)
        material_symbol_key = _material_symbol_key_for_impacts(provider_token_impacts)
        material_evidence = {
            "material_title_fingerprint": material_fingerprint,
            "material_window_bucket_ms": material_window_bucket_ms,
            "material_symbol_key": material_symbol_key,
            "material_match_window_ms": _MATERIAL_MATCH_WINDOW_MS,
        }
        self._lock_material_duplicate_candidate_window(
            source_id=source_id,
            material_fingerprint=material_fingerprint,
            published_at_ms=published_at_ms,
        )
        candidates = self._material_duplicate_candidate_rows(
            source_id=source_id,
            published_at_ms=published_at_ms,
            canonical_item_key=identity.canonical_item_key,
        )
        enriched_identity = _canonical_identity_with_evidence(identity, material_evidence)
        if identity.dedup_key_kind == "canonical_url":
            return enriched_identity

        incoming_symbols = provider_symbol_set(provider_token_impacts)
        for candidate in candidates:
            if material_title_fingerprint(candidate["title"]) != material_fingerprint:
                continue
            existing_symbols = provider_symbol_set(candidate["provider_token_impacts_json"])
            if not symbol_sets_compatible(incoming_symbols, existing_symbols):
                continue
            return CanonicalIdentity(
                canonical_item_key=str(candidate["canonical_item_key"]),
                news_item_id=str(candidate["news_item_id"]),
                dedup_key_kind=str(candidate["dedup_key_kind"] or enriched_identity.dedup_key_kind),
                dedup_key_confidence=str(candidate["dedup_key_confidence"] or enriched_identity.dedup_key_confidence),
                url_identity_kind=str(candidate["url_identity_kind"] or enriched_identity.url_identity_kind),
                match_type="same_material_title",
                match_confidence="strong",
                evidence={
                    **dict(enriched_identity.evidence),
                    "material_existing_news_item_id": str(candidate["news_item_id"]),
                    "material_existing_canonical_item_key": str(candidate["canonical_item_key"]),
                },
            )
        return enriched_identity

    def _lock_material_duplicate_candidate_window(
        self,
        *,
        source_id: str,
        material_fingerprint: str,
        published_at_ms: int,
    ) -> None:
        for material_window_bucket_ms in _material_window_bucket_ms_values_for_match_window(published_at_ms):
            lock_key = json.dumps(
                [
                    "news-material-duplicate-v2",
                    str(source_id),
                    str(material_fingerprint),
                    int(material_window_bucket_ms),
                ],
                separators=(",", ":"),
            )
            self.conn.execute(
                """
                SELECT pg_advisory_xact_lock(
                  ('x' || substr(md5(%s), 1, 16))::bit(64)::bigint
                )
                """,
                (lock_key,),
            )

    def _material_duplicate_candidate_rows(
        self,
        *,
        source_id: str,
        published_at_ms: int,
        canonical_item_key: str,
    ) -> list[Any]:
        return list(
            self.conn.execute(
                """
                WITH ranked_edges AS (
                  SELECT items.news_item_id,
                         items.canonical_item_key,
                         items.dedup_key_kind,
                         items.dedup_key_confidence,
                         items.url_identity_kind,
                         items.title,
                         items.provider_token_impacts_json,
                         items.published_at_ms,
                         provider_items.provider_payload_status,
                         ROW_NUMBER() OVER (
                           PARTITION BY items.news_item_id
                           ORDER BY
                             CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
                             edges.provider_article_key ASC,
                             provider_items.payload_hash ASC,
                             edges.provider_item_id ASC
                         ) AS edge_rank
                    FROM news_items AS items
                    JOIN news_item_observation_edges AS edges
                      ON edges.news_item_id = items.news_item_id
                    JOIN news_provider_items AS provider_items
                      ON provider_items.provider_item_id = edges.provider_item_id
                   WHERE items.source_id = %s
                     AND items.published_at_ms BETWEEN %s AND %s
                     AND items.canonical_item_key <> %s
                )
                SELECT news_item_id,
                       canonical_item_key,
                       dedup_key_kind,
                       dedup_key_confidence,
                       url_identity_kind,
                       title,
                       provider_token_impacts_json,
                       published_at_ms,
                       provider_payload_status
                  FROM ranked_edges
                 WHERE edge_rank = 1
                 ORDER BY
                   CASE WHEN dedup_key_kind = 'canonical_url' THEN 0 ELSE 1 END,
                   CASE WHEN provider_payload_status = 'ready' THEN 0 ELSE 1 END,
                   published_at_ms DESC,
                   news_item_id ASC
                """,
                (
                    str(source_id),
                    int(published_at_ms) - _MATERIAL_MATCH_WINDOW_MS,
                    int(published_at_ms) + _MATERIAL_MATCH_WINDOW_MS,
                    str(canonical_item_key),
                ),
            ).fetchall()
        )

    def _remap_material_duplicate_edges_to_news_item(
        self,
        *,
        source_id: str,
        news_item_id: str,
        canonical_item_key: str,
        title: str,
        published_at_ms: int,
        provider_token_impacts: Sequence[Mapping[str, Any]],
        now_ms: int,
    ) -> list[str]:
        material_fingerprint = material_title_fingerprint(title)
        if not material_title_is_eligible(material_fingerprint):
            return []
        material_window_bucket_ms = _material_window_bucket_ms_for_published_at(published_at_ms)
        material_symbol_key = _material_symbol_key_for_impacts(provider_token_impacts)
        self._lock_material_duplicate_candidate_window(
            source_id=source_id,
            material_fingerprint=material_fingerprint,
            published_at_ms=published_at_ms,
        )

        incoming_symbols = provider_symbol_set(provider_token_impacts)
        old_news_item_ids: list[str] = []
        for candidate in self._material_duplicate_candidate_rows(
            source_id=source_id,
            published_at_ms=published_at_ms,
            canonical_item_key=canonical_item_key,
        ):
            candidate_news_item_id = str(candidate["news_item_id"])
            if candidate_news_item_id == str(news_item_id):
                continue
            if material_title_fingerprint(candidate["title"]) != material_fingerprint:
                continue
            existing_symbols = provider_symbol_set(candidate["provider_token_impacts_json"])
            if not symbol_sets_compatible(incoming_symbols, existing_symbols):
                continue
            old_news_item_ids.append(candidate_news_item_id)

        old_news_item_ids = list(dict.fromkeys(old_news_item_ids))
        if not old_news_item_ids:
            return []

        placeholders = ", ".join(["%s"] * len(old_news_item_ids))
        cursor = self.conn.execute(
            f"""
            WITH remapped AS (
              SELECT provider_item_id, news_item_id AS old_news_item_id
                FROM news_item_observation_edges
               WHERE news_item_id IN ({placeholders})
                 AND news_item_id <> %s
            ),
            updated AS (
              UPDATE news_item_observation_edges AS edges
                 SET news_item_id = %s,
                     match_type = 'same_material_title',
                     match_confidence = 'strong',
                     policy_version = %s,
                     evidence_json = edges.evidence_json || jsonb_build_object(
                       'material_remap_reason', 'hard_canonical_url',
                       'material_title_fingerprint', %s::text,
                       'material_window_bucket_ms', %s::bigint,
                       'material_symbol_key', %s::text,
                       'material_remapped_to_news_item_id', %s::text,
                       'material_remapped_at_ms', %s::bigint
                     ),
                     last_seen_at_ms = %s
                FROM remapped
               WHERE edges.provider_item_id = remapped.provider_item_id
               RETURNING remapped.old_news_item_id
            )
            SELECT DISTINCT old_news_item_id
              FROM updated
            """,
            (
                *old_news_item_ids,
                str(news_item_id),
                str(news_item_id),
                CANONICAL_POLICY_VERSION,
                material_fingerprint,
                int(material_window_bucket_ms),
                material_symbol_key,
                str(news_item_id),
                int(now_ms),
                int(now_ms),
            ),
        )
        rows = cursor.fetchall()
        expect_mutation_count(cursor, expected=len(rows), error_code="news_repository_rowcount_invalid")
        old_item_ids = [str(row["old_news_item_id"]) for row in rows]
        return old_item_ids

    def _remap_provider_article_edges_to_news_item(
        self,
        *,
        provider_article_key: str,
        news_item_id: str,
        now_ms: int,
        remap_reason: str = "ready_content_hash",
    ) -> list[str]:
        cursor = self.conn.execute(
            """
            WITH remapped AS (
              SELECT provider_item_id, news_item_id AS old_news_item_id
                FROM news_item_observation_edges
               WHERE provider_article_key = %s
                 AND news_item_id <> %s
            ),
            updated AS (
              UPDATE news_item_observation_edges AS edges
                 SET news_item_id = %s,
                     match_type = 'same_provider_article_id',
                     match_confidence = 'strong',
                     policy_version = %s,
                     evidence_json = edges.evidence_json || jsonb_build_object(
                       'provider_article_remap_reason', %s::text,
                       'provider_article_remapped_to_news_item_id', %s::text,
                       'provider_article_remapped_at_ms', %s::bigint
                     ),
                     last_seen_at_ms = %s
                FROM remapped
               WHERE edges.provider_item_id = remapped.provider_item_id
               RETURNING remapped.old_news_item_id
            )
            SELECT DISTINCT old_news_item_id
              FROM updated
            """,
            (
                str(provider_article_key),
                str(news_item_id),
                str(news_item_id),
                CANONICAL_POLICY_VERSION,
                str(remap_reason),
                str(news_item_id),
                int(now_ms),
                int(now_ms),
            ),
        )
        rows = cursor.fetchall()
        expect_mutation_count(cursor, expected=len(rows), error_code="news_repository_rowcount_invalid")
        old_item_ids = [str(row["old_news_item_id"]) for row in rows]
        return old_item_ids

    def _refresh_news_item_observation_summary(
        self,
        *,
        news_item_id: str,
        now_ms: int,
        required: bool = True,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """
            WITH edge_summary AS (
              SELECT
                edges.news_item_id,
                COUNT(*)::int AS duplicate_observation_count,
                COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb) AS source_ids_json,
                COALESCE(
                  jsonb_agg(DISTINCT sources.source_domain ORDER BY sources.source_domain),
                  '[]'::jsonb
                ) AS source_domains_json,
                COALESCE(
                  jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                    FILTER (WHERE edges.provider_article_key <> ''),
                  '[]'::jsonb
                ) AS provider_article_keys_json
              FROM news_item_observation_edges AS edges
              JOIN news_sources AS sources ON sources.source_id = edges.source_id
             WHERE edges.news_item_id = %s
             GROUP BY edges.news_item_id
            )
            UPDATE news_items AS items
               SET duplicate_observation_count = edge_summary.duplicate_observation_count,
                   source_ids_json = edge_summary.source_ids_json,
                   source_domains_json = edge_summary.source_domains_json,
                   provider_article_keys_json = edge_summary.provider_article_keys_json,
                   updated_at_ms = %s
              FROM edge_summary
             WHERE items.news_item_id = edge_summary.news_item_id
            RETURNING items.*
            """,
            (news_item_id, int(now_ms)),
        )
        row = cursor.fetchone()
        if required:
            return _required_returning_row(cursor, row)
        return _optional_returning_row(cursor, row) or {}

    def _delete_zero_edge_news_item(self, *, news_item_id: str) -> bool:
        cursor = self.conn.execute(
            """
            DELETE FROM news_items AS items
             WHERE items.news_item_id = %s
               AND NOT EXISTS (
                 SELECT 1
                   FROM news_item_observation_edges AS edges
                  WHERE edges.news_item_id = items.news_item_id
               )
            RETURNING items.news_item_id
            """,
            (news_item_id,),
        )
        row = cursor.fetchone()
        rows = [row] if row is not None else []
        deleted_count = expect_mutation_count(cursor, expected=len(rows), error_code="news_repository_rowcount_invalid")
        return deleted_count > 0

    def _lock_news_item_for_edge_remap_cleanup(self, *, news_item_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT news_item_id
              FROM news_items
             WHERE news_item_id = %s
             FOR UPDATE
            """,
            (news_item_id,),
        ).fetchone()
        return row is not None

    def _news_item_has_observation_edges(self, *, news_item_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT EXISTS (
              SELECT 1
                FROM news_item_observation_edges AS edges
               WHERE edges.news_item_id = %s
            ) AS has_edges
            """,
            (news_item_id,),
        ).fetchone()
        return bool(row and row["has_edges"])

    def _remap_projection_dirty_targets_to_news_item(
        self,
        *,
        old_news_item_ids: Sequence[str],
        news_item_id: str,
        now_ms: int,
    ) -> None:
        old_ids = _distinct_old_news_item_ids(old_news_item_ids, news_item_id=news_item_id)
        if not old_ids:
            return
        placeholders = ", ".join(["%s"] * len(old_ids))
        self.conn.execute(
            f"""
            WITH moved AS (
              SELECT
                targets.projection_name,
                targets.target_kind,
                targets."window",
                md5(
                  'canonical_news_item_merge:' || %s::text || ':' ||
                  targets.projection_name || ':' ||
                  targets.target_kind || ':' ||
                  targets."window" || ':' ||
                  string_agg(targets.payload_hash, '|' ORDER BY targets.payload_hash)
                ) AS payload_hash,
                MAX(targets.source_watermark_ms)::bigint AS source_watermark_ms,
                MIN(targets.priority)::integer AS priority,
                MIN(targets.due_at_ms)::bigint AS due_at_ms,
                MIN(targets.first_dirty_at_ms)::bigint AS first_dirty_at_ms
              FROM news_projection_dirty_targets AS targets
              WHERE targets.target_kind = 'news_item'
                AND targets.target_id IN ({placeholders})
              GROUP BY targets.projection_name, targets.target_kind, targets."window"
            ),
            upserted AS (
              INSERT INTO news_projection_dirty_targets(
                projection_name,
                target_kind,
                target_id,
                "window",
                dirty_reason,
                payload_hash,
                source_watermark_ms,
                priority,
                due_at_ms,
                leased_until_ms,
                lease_owner,
                attempt_count,
                last_error,
                first_dirty_at_ms,
                updated_at_ms
              )
              SELECT
                moved.projection_name,
                moved.target_kind,
                %s,
                moved."window",
                'canonical_news_item_merge',
                moved.payload_hash,
                moved.source_watermark_ms,
                moved.priority,
                moved.due_at_ms,
                NULL,
                NULL,
                0,
                NULL,
                LEAST(moved.first_dirty_at_ms, %s::bigint),
                %s
              FROM moved
              ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
                dirty_reason = EXCLUDED.dirty_reason,
                payload_hash = EXCLUDED.payload_hash,
                source_watermark_ms = GREATEST(
                  news_projection_dirty_targets.source_watermark_ms,
                  EXCLUDED.source_watermark_ms
                ),
                priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
                due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
                leased_until_ms = NULL,
                lease_owner = NULL,
                attempt_count = 0,
                last_error = NULL,
                first_dirty_at_ms = LEAST(
                  news_projection_dirty_targets.first_dirty_at_ms,
                  EXCLUDED.first_dirty_at_ms
                ),
                updated_at_ms = EXCLUDED.updated_at_ms
              RETURNING projection_name, target_kind, target_id, "window"
            )
            DELETE FROM news_projection_dirty_targets AS targets
             WHERE targets.target_kind = 'news_item'
               AND targets.target_id IN ({placeholders})
            """,
            (
                str(news_item_id),
                *old_ids,
                str(news_item_id),
                int(now_ms),
                int(now_ms),
                *old_ids,
            ),
        )

    def _clear_item_scoped_derived_facts(self, *, news_item_id: str) -> None:
        self.conn.execute("DELETE FROM news_fact_candidates WHERE news_item_id = %s", (news_item_id,))
        self.conn.execute("DELETE FROM news_token_mentions WHERE news_item_id = %s", (news_item_id,))
        self.conn.execute("DELETE FROM news_item_entities WHERE news_item_id = %s", (news_item_id,))

    def _enqueue_item_scoped_page_cleanup_target(self, *, news_item_id: str, reason: str, now_ms: int) -> None:
        payload_hash = hashlib.sha256(f"{reason}:{news_item_id}".encode()).hexdigest()
        self.conn.execute(
            """
            INSERT INTO news_projection_dirty_targets(
              projection_name,
              target_kind,
              target_id,
              "window",
              dirty_reason,
              payload_hash,
              source_watermark_ms,
              priority,
              due_at_ms,
              leased_until_ms,
              lease_owner,
              attempt_count,
              last_error,
              first_dirty_at_ms,
              updated_at_ms
            )
            VALUES (
              'page',
              'news_item',
              %s,
              '',
              %s,
              %s,
              %s,
              1,
              %s,
              NULL,
              NULL,
              0,
              NULL,
              %s,
              %s
            )
            ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
              dirty_reason = EXCLUDED.dirty_reason,
              payload_hash = EXCLUDED.payload_hash,
              source_watermark_ms = GREATEST(
                news_projection_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = NULL,
              lease_owner = NULL,
              attempt_count = 0,
              last_error = NULL,
              first_dirty_at_ms = LEAST(
                news_projection_dirty_targets.first_dirty_at_ms,
                EXCLUDED.first_dirty_at_ms
              ),
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            (
                str(news_item_id),
                str(reason),
                payload_hash,
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
            ),
        )

    def _reselect_news_item_representative_from_edges(self, *, news_item_id: str, now_ms: int) -> dict[str, Any]:
        cursor = self.conn.execute(
            """
            WITH representative_edge AS (
              SELECT
                edges.provider_item_id,
                edges.source_id,
                sources.source_domain,
                provider_items.canonical_url AS provider_canonical_url,
                edges.evidence_json #> '{item_payload}' AS item_payload
              FROM news_item_observation_edges AS edges
              JOIN news_provider_items AS provider_items
                ON provider_items.provider_item_id = edges.provider_item_id
              JOIN news_sources AS sources ON sources.source_id = edges.source_id
             WHERE edges.news_item_id = %s
             ORDER BY
               CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
               CASE
                 WHEN edges.evidence_json #>> '{item_payload,url_identity_kind}' = 'article' THEN 0
                 WHEN provider_items.canonical_url ~* '^https?://' THEN 1
                 ELSE 2
               END,
               edges.provider_article_key ASC,
               edges.source_id ASC,
               provider_items.payload_hash ASC,
               edges.provider_item_id ASC
             LIMIT 1
            )
            UPDATE news_items AS items
               SET provider_item_id = representative_edge.provider_item_id,
                   source_id = representative_edge.source_id,
                   source_domain = representative_edge.source_domain,
                   canonical_url = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'canonical_url', ''),
                     representative_edge.provider_canonical_url
                   ),
                   title = COALESCE(NULLIF(representative_edge.item_payload ->> 'title', ''), items.title),
                   summary = COALESCE(representative_edge.item_payload ->> 'summary', items.summary),
                   body_text = COALESCE(representative_edge.item_payload ->> 'body_text', items.body_text),
                   language = COALESCE(NULLIF(representative_edge.item_payload ->> 'language', ''), items.language),
                   published_at_ms = COALESCE(
                     CASE
                       WHEN representative_edge.item_payload ->> 'published_at_ms' ~ '^[0-9]+$'
                         THEN (representative_edge.item_payload ->> 'published_at_ms')::bigint
                       ELSE NULL
                     END,
                     items.published_at_ms
                   ),
                   fetched_at_ms = COALESCE(
                     CASE
                       WHEN representative_edge.item_payload ->> 'fetched_at_ms' ~ '^[0-9]+$'
                         THEN (representative_edge.item_payload ->> 'fetched_at_ms')::bigint
                       ELSE NULL
                     END,
                     items.fetched_at_ms
                   ),
                   content_hash = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'content_hash', ''),
                     items.content_hash
                   ),
                   title_fingerprint = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'title_fingerprint', ''),
                     items.title_fingerprint
                   ),
                   provider_signal_json = COALESCE(
                     representative_edge.item_payload -> 'provider_signal_json',
                     '{}'::jsonb
                   ),
                   provider_token_impacts_json = COALESCE(
                     representative_edge.item_payload -> 'provider_token_impacts_json',
                     '[]'::jsonb
                   ),
                   url_identity_kind = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'url_identity_kind', ''),
                     items.url_identity_kind
                   ),
                   lifecycle_status = 'raw',
                   updated_at_ms = %s
              FROM representative_edge
             WHERE items.news_item_id = %s
            RETURNING items.*
            """,
            (news_item_id, int(now_ms), news_item_id),
        )
        row = cursor.fetchone()
        returned_row = _optional_returning_row(cursor, row)
        return returned_row or {}

    def claim_unprocessed_items(
        self,
        *,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="news_item_claim_limit_required",
        )
        lease_deadline = int(now_ms) + require_positive_int(
            lease_ms,
            error_code="news_item_claim_lease_ms_required",
        )
        cursor = self.conn.execute(
            """
            WITH picked AS (
              SELECT news_item_id,
                     CASE
                       WHEN lifecycle_status = 'process_retryable' THEN 0
                       ELSE 1
                     END AS claim_priority
                FROM news_items
               WHERE lifecycle_status = 'raw'
                  OR (
                    lifecycle_status = 'process_retryable'
                    AND processing_next_due_at_ms <= %s
                  )
               ORDER BY claim_priority ASC,
                        processing_next_due_at_ms ASC,
                        published_at_ms ASC,
                        news_item_id ASC
               LIMIT %s
               FOR UPDATE SKIP LOCKED
            ),
            claimed AS (
              UPDATE news_items AS items
                 SET lifecycle_status = 'processing',
                     processing_lease_owner = %s,
                     processing_leased_until_ms = %s,
                     processing_attempts = processing_attempts + 1,
                     processing_error = NULL,
                     processing_terminal_error = NULL,
                     updated_at_ms = %s
                FROM picked
               WHERE items.news_item_id = picked.news_item_id
              RETURNING items.*
            )
            SELECT claimed.news_item_id,
                   claimed.provider_item_id,
                   claimed.source_id,
                   sources.source_domain AS source_domain,
                   claimed.canonical_url,
                   claimed.title,
                   claimed.summary,
                   claimed.body_text,
                   claimed.language,
                   claimed.published_at_ms,
                   claimed.fetched_at_ms,
                   claimed.content_hash,
                   claimed.title_fingerprint,
                   claimed.lifecycle_status,
                   claimed.processing_attempts,
                   claimed.processing_lease_owner,
                   claimed.processing_leased_until_ms,
                   claimed.processing_next_due_at_ms,
                   claimed.processing_error,
                   claimed.processing_terminal_error,
                   claimed.processed_at_ms,
                   claimed.content_class,
                   claimed.content_tags_json,
                   claimed.content_classification_json,
                   claimed.provider_signal_json,
                   claimed.provider_token_impacts_json,
                   claimed.provider_article_keys_json,
                   claimed.created_at_ms,
                   claimed.updated_at_ms,
                   sources.provider_type,
                   sources.source_role,
                   sources.trust_tier,
                   sources.source_name,
                   sources.coverage_tags_json,
                   sources.authority_scope_json,
                   provider_items.canonical_url AS provider_canonical_url
              FROM claimed
              JOIN picked ON picked.news_item_id = claimed.news_item_id
              JOIN news_sources AS sources ON sources.source_id = claimed.source_id
              JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = claimed.provider_item_id
             ORDER BY picked.claim_priority ASC,
                      claimed.processing_next_due_at_ms ASC,
                      claimed.published_at_ms ASC,
                      claimed.news_item_id ASC
            """,
            (
                int(now_ms),
                parsed_limit,
                str(lease_owner),
                lease_deadline,
                int(now_ms),
            ),
        )
        rows = cursor.fetchall()
        expect_mutation_count(cursor, expected=len(rows), error_code="news_repository_rowcount_invalid")
        claimed_rows = [dict(row) for row in rows]
        return claimed_rows

    def replace_item_entities(
        self,
        *,
        news_item_id: str,
        entities: Sequence[NewsEntity],
    ) -> None:
        self.conn.execute("DELETE FROM news_item_entities WHERE news_item_id = %s", (news_item_id,))
        for entity in entities:
            self.conn.execute(
                """
                INSERT INTO news_item_entities (
                  entity_id, news_item_id, entity_type, raw_value, normalized_value, chain,
                  span_start, span_end, text_surface, confidence, extraction_policy_version, created_at_ms
                )
                VALUES (
                  %(entity_id)s, %(news_item_id)s, %(entity_type)s, %(raw_value)s, %(normalized_value)s,
                  %(chain)s, %(span_start)s, %(span_end)s, %(text_surface)s, %(confidence)s,
                  %(extraction_policy_version)s, %(created_at_ms)s
                )
                ON CONFLICT (entity_id) DO UPDATE SET
                  raw_value = EXCLUDED.raw_value,
                  normalized_value = EXCLUDED.normalized_value,
                  chain = EXCLUDED.chain,
                  span_start = EXCLUDED.span_start,
                  span_end = EXCLUDED.span_end,
                  text_surface = EXCLUDED.text_surface,
                  confidence = EXCLUDED.confidence,
                  extraction_policy_version = EXCLUDED.extraction_policy_version
                """,
                _entity_payload(entity),
            )

    def replace_token_mentions(
        self,
        *,
        news_item_id: str,
        mentions: Sequence[NewsTokenMention],
    ) -> None:
        self.conn.execute("DELETE FROM news_token_mentions WHERE news_item_id = %s", (news_item_id,))
        for mention in mentions:
            self.conn.execute(
                """
                INSERT INTO news_token_mentions (
                  mention_id, news_item_id, entity_id, observed_symbol, chain_id, address,
                  resolution_status, target_type, target_id, display_symbol, display_name,
                  reason_codes_json, candidate_targets_json, evidence_strength, confidence, created_at_ms
                )
                VALUES (
                  %(mention_id)s, %(news_item_id)s, %(entity_id)s, %(observed_symbol)s, %(chain_id)s,
                  %(address)s, %(resolution_status)s, %(target_type)s, %(target_id)s, %(display_symbol)s,
                  %(display_name)s, %(reason_codes_json)s, %(candidate_targets_json)s,
                  %(evidence_strength)s, %(confidence)s, %(created_at_ms)s
                )
                ON CONFLICT (mention_id) DO UPDATE SET
                  observed_symbol = EXCLUDED.observed_symbol,
                  chain_id = EXCLUDED.chain_id,
                  address = EXCLUDED.address,
                  resolution_status = EXCLUDED.resolution_status,
                  target_type = EXCLUDED.target_type,
                  target_id = EXCLUDED.target_id,
                  display_symbol = EXCLUDED.display_symbol,
                  display_name = EXCLUDED.display_name,
                  reason_codes_json = EXCLUDED.reason_codes_json,
                  candidate_targets_json = EXCLUDED.candidate_targets_json,
                  evidence_strength = EXCLUDED.evidence_strength,
                  confidence = EXCLUDED.confidence
                """,
                _mention_payload(mention),
            )

    def replace_fact_candidates(
        self,
        *,
        news_item_id: str,
        candidates: Sequence[NewsFactCandidate],
    ) -> None:
        self.conn.execute("DELETE FROM news_fact_candidates WHERE news_item_id = %s", (news_item_id,))
        for candidate in candidates:
            self.conn.execute(
                """
                INSERT INTO news_fact_candidates (
                  fact_candidate_id, news_item_id, event_type, claim, realis, evidence_quote,
                  evidence_span_start, evidence_span_end, source_role, required_slots_json,
                  affected_targets_json, validation_status, rejection_reasons_json,
                  extraction_method, policy_version, created_at_ms, updated_at_ms
                )
                VALUES (
                  %(fact_candidate_id)s, %(news_item_id)s, %(event_type)s, %(claim)s, %(realis)s,
                  %(evidence_quote)s, %(evidence_span_start)s, %(evidence_span_end)s, %(source_role)s,
                  %(required_slots_json)s, %(affected_targets_json)s, %(validation_status)s,
                  %(rejection_reasons_json)s, %(extraction_method)s, %(policy_version)s,
                  %(created_at_ms)s, %(updated_at_ms)s
                )
                ON CONFLICT (fact_candidate_id) DO UPDATE SET
                  claim = EXCLUDED.claim,
                  realis = EXCLUDED.realis,
                  evidence_quote = EXCLUDED.evidence_quote,
                  evidence_span_start = EXCLUDED.evidence_span_start,
                  evidence_span_end = EXCLUDED.evidence_span_end,
                  required_slots_json = EXCLUDED.required_slots_json,
                  affected_targets_json = EXCLUDED.affected_targets_json,
                  validation_status = EXCLUDED.validation_status,
                  rejection_reasons_json = EXCLUDED.rejection_reasons_json,
                  extraction_method = EXCLUDED.extraction_method,
                  policy_version = EXCLUDED.policy_version,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                _fact_payload(candidate),
            )

    def mark_item_processed(
        self,
        *,
        news_item_id: str,
        processed_at_ms: int,
        lease_owner: str | None = None,
        processing_attempts: int | None = None,
    ) -> int:
        if (lease_owner is None) != (processing_attempts is None):
            raise ValueError("lease_owner and processing_attempts must be provided together")
        if lease_owner is None:
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'processed',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = 0,
                       processing_error = NULL,
                       processing_terminal_error = NULL,
                       processed_at_ms = %s,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                """,
                (int(processed_at_ms), int(processed_at_ms), news_item_id),
            )
        else:
            if processing_attempts is None:
                raise ValueError("lease_owner and processing_attempts must be provided together")
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'processed',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = 0,
                       processing_error = NULL,
                       processing_terminal_error = NULL,
                       processed_at_ms = %s,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                   AND lifecycle_status = 'processing'
                   AND processing_lease_owner = %s
                   AND processing_attempts = %s
                """,
                (
                    int(processed_at_ms),
                    int(processed_at_ms),
                    news_item_id,
                    str(lease_owner),
                    int(processing_attempts),
                ),
            )
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")

    def mark_news_items_for_reprocessing(
        self,
        *,
        news_item_ids: Sequence[str],
        now_ms: int,
    ) -> int:
        scoped_ids = [str(item) for item in news_item_ids if str(item or "")]
        if not scoped_ids:
            return 0
        cursor = self.conn.execute(
            """
            UPDATE news_items
               SET lifecycle_status = 'raw',
                   processing_lease_owner = NULL,
                   processing_leased_until_ms = NULL,
                   processing_next_due_at_ms = 0,
                   processing_error = NULL,
                   processing_terminal_error = NULL,
                   updated_at_ms = GREATEST(updated_at_ms, %s)
             WHERE news_item_id = ANY(%s::text[])
               AND lifecycle_status IN ('processed', 'processing', 'process_retryable', 'process_terminal_failed')
            """,
            (int(now_ms), scoped_ids),
        )
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")

    def update_item_content_classification(
        self,
        *,
        news_item_id: str,
        content_class: str,
        content_tags: Sequence[str],
        classification_payload: Mapping[str, Any],
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_items
               SET content_class = %s,
                   content_tags_json = %s,
                   content_classification_json = %s,
                   updated_at_ms = %s
             WHERE news_item_id = %s
            """,
            (
                str(content_class),
                _json([str(tag) for tag in content_tags]),
                _json(_json_dict(classification_payload)),
                int(now_ms),
                str(news_item_id),
            ),
        )

    def update_item_market_scope_and_story_identity(
        self,
        *,
        news_item_id: str,
        market_scope: NewsMarketScope,
        story_identity: NewsStoryIdentity,
        now_ms: int,
    ) -> None:
        market_scope_payload = _market_scope_payload(market_scope)
        story_identity_payload = _story_identity_payload(story_identity)
        self.conn.execute(
            """
            UPDATE news_items
               SET market_scope_json = %s,
                   story_key = %s,
                   story_identity_json = %s,
                   story_identity_version = %s,
                   updated_at_ms = %s
             WHERE news_item_id = %s
            """,
            (
                _json(market_scope_payload),
                str(story_identity_payload["story_key"]),
                _json(story_identity_payload),
                str(story_identity_payload["version"]),
                int(now_ms),
                str(news_item_id),
            ),
        )

    def mark_item_process_retryable(
        self,
        *,
        news_item_id: str,
        error: str,
        next_due_at_ms: int,
        now_ms: int,
        lease_owner: str | None = None,
        processing_attempts: int | None = None,
    ) -> int:
        if (lease_owner is None) != (processing_attempts is None):
            raise ValueError("lease_owner and processing_attempts must be provided together")
        if lease_owner is None:
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'process_retryable',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = %s,
                       processing_error = %s,
                       processing_terminal_error = NULL,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                """,
                (int(next_due_at_ms), _compact_error(error), int(now_ms), news_item_id),
            )
        else:
            if processing_attempts is None:
                raise ValueError("lease_owner and processing_attempts must be provided together")
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'process_retryable',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = %s,
                       processing_error = %s,
                       processing_terminal_error = NULL,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                   AND lifecycle_status = 'processing'
                   AND processing_lease_owner = %s
                   AND processing_attempts = %s
                """,
                (
                    int(next_due_at_ms),
                    _compact_error(error),
                    int(now_ms),
                    news_item_id,
                    str(lease_owner),
                    int(processing_attempts),
                ),
            )
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")

    def mark_item_process_terminal_failed(
        self,
        *,
        news_item_id: str,
        error: str,
        now_ms: int,
        lease_owner: str | None = None,
        processing_attempts: int | None = None,
    ) -> int:
        if (lease_owner is None) != (processing_attempts is None):
            raise ValueError("lease_owner and processing_attempts must be provided together")
        if lease_owner is None:
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'process_terminal_failed',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = 0,
                       processing_error = NULL,
                       processing_terminal_error = %s,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                """,
                (_compact_error(error), int(now_ms), news_item_id),
            )
        else:
            if processing_attempts is None:
                raise ValueError("lease_owner and processing_attempts must be provided together")
            cursor = self.conn.execute(
                """
                UPDATE news_items
                   SET lifecycle_status = 'process_terminal_failed',
                       processing_lease_owner = NULL,
                       processing_leased_until_ms = NULL,
                       processing_next_due_at_ms = 0,
                       processing_error = NULL,
                       processing_terminal_error = %s,
                       updated_at_ms = %s
                 WHERE news_item_id = %s
                   AND lifecycle_status = 'processing'
                   AND processing_lease_owner = %s
                   AND processing_attempts = %s
                """,
                (
                    _compact_error(error),
                    int(now_ms),
                    news_item_id,
                    str(lease_owner),
                    int(processing_attempts),
                ),
            )
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")

    def release_expired_processing_items(self, *, now_ms: int) -> int:
        cursor = self.conn.execute(
            """
            UPDATE news_items
               SET lifecycle_status = 'process_retryable',
                   processing_lease_owner = NULL,
                   processing_leased_until_ms = NULL,
                   processing_next_due_at_ms = %s,
                   updated_at_ms = %s
             WHERE lifecycle_status = 'processing'
               AND processing_leased_until_ms <= %s
            """,
            (int(now_ms), int(now_ms), int(now_ms)),
        )
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")

    def servable_news_item_ids(self, news_item_ids: Sequence[str]) -> list[str]:
        target_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not target_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT items.news_item_id
              FROM unnest(%s::text[]) WITH ORDINALITY AS target_ids(news_item_id, ordinal)
              JOIN news_items AS items ON items.news_item_id = target_ids.news_item_id
             WHERE EXISTS (
                     SELECT 1
                       FROM news_item_observation_edges AS edges
                       JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                      WHERE edges.news_item_id = items.news_item_id
                        AND edge_sources.enabled = true
                   )
             ORDER BY target_ids.ordinal ASC
            """,
            (target_ids,),
        ).fetchall()
        return [str(row["news_item_id"]) for row in rows]
