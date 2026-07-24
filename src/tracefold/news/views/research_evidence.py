from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsResearchCatalog:
    item_count: int
    source_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NewsResearchEvidence:
    news_item_id: str
    source_id: str
    source_domain: str
    canonical_url: str | None
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    fetched_at_ms: int
    lifecycle_status: str


class NewsResearchEvidenceReader:
    """News-owned read interface for bounded downstream research evidence."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def catalog(
        self,
        *,
        published_before_ms: int,
        fetched_before_ms: int,
    ) -> NewsResearchCatalog:
        row = self._conn.execute(
            """
            SELECT
              COUNT(*)::int AS news_count,
              COALESCE(
                array_agg(DISTINCT source_domain ORDER BY source_domain),
                ARRAY[]::text[]
              ) AS source_labels
            FROM news_items
            WHERE published_at_ms <= %s
              AND fetched_at_ms <= %s
            """,
            (int(published_before_ms), int(fetched_before_ms)),
        ).fetchone()
        return NewsResearchCatalog(
            item_count=int(row["news_count"] or 0),
            source_labels=tuple(str(value) for value in (row["source_labels"] or ())),
        )

    def search(
        self,
        *,
        published_before_ms: int,
        fetched_before_ms: int,
        source_labels: tuple[str, ...],
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[NewsResearchEvidence, ...]:
        rows = self._conn.execute(
            """
            SELECT
              news_item_id,
              source_id,
              source_domain,
              canonical_url,
              title,
              summary,
              body_text,
              language,
              published_at_ms,
              fetched_at_ms,
              lifecycle_status
            FROM news_items
            WHERE published_at_ms <= %s
              AND fetched_at_ms <= %s
              AND (
                cardinality(%s::text[]) = 0
                OR source_id = ANY(%s::text[])
                OR source_domain = ANY(%s::text[])
              )
              AND (
                %s = ''
                OR title ILIKE %s
                OR summary ILIKE %s
                OR body_text ILIKE %s
              )
            ORDER BY published_at_ms DESC, news_item_id ASC
            LIMIT %s
            OFFSET %s
            """,
            (
                int(published_before_ms),
                int(fetched_before_ms),
                list(source_labels),
                list(source_labels),
                list(source_labels),
                query,
                _like(query),
                _like(query),
                _like(query),
                int(limit),
                int(offset),
            ),
        ).fetchall()
        return tuple(_evidence_from_row(row) for row in rows)

    def read(
        self,
        *,
        news_item_ids: tuple[str, ...],
        published_before_ms: int,
        fetched_before_ms: int,
    ) -> tuple[NewsResearchEvidence, ...]:
        if not news_item_ids:
            return ()
        rows = self._conn.execute(
            """
            SELECT
              news_item_id,
              source_id,
              source_domain,
              canonical_url,
              title,
              summary,
              body_text,
              language,
              published_at_ms,
              fetched_at_ms,
              lifecycle_status
            FROM news_items
            WHERE news_item_id = ANY(%s::text[])
              AND published_at_ms <= %s
              AND fetched_at_ms <= %s
            """,
            (
                list(news_item_ids),
                int(published_before_ms),
                int(fetched_before_ms),
            ),
        ).fetchall()
        return tuple(_evidence_from_row(row) for row in rows)


def _evidence_from_row(row: Any) -> NewsResearchEvidence:
    return NewsResearchEvidence(
        news_item_id=str(row["news_item_id"]),
        source_id=str(row["source_id"]),
        source_domain=str(row["source_domain"]),
        canonical_url=str(row["canonical_url"]) if row["canonical_url"] else None,
        title=str(row["title"] or ""),
        summary=str(row["summary"] or ""),
        body_text=str(row["body_text"] or ""),
        language=str(row["language"] or ""),
        published_at_ms=int(row["published_at_ms"]),
        fetched_at_ms=int(row["fetched_at_ms"]),
        lifecycle_status=str(row["lifecycle_status"] or ""),
    )


def _like(value: str) -> str:
    return f"%{value}%"


__all__ = [
    "NewsResearchCatalog",
    "NewsResearchEvidence",
    "NewsResearchEvidenceReader",
]
