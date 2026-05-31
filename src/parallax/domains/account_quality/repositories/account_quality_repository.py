from __future__ import annotations

import hashlib
import time
from typing import Any


class AccountQualityRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_profile(
        self,
        *,
        handle: str,
        first_seen_ms: int,
        latest_seen_ms: int,
        follower_max: int | None,
        watched_status: str,
        commit: bool = True,
    ) -> None:
        normalized = _handle(handle)
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO account_profiles(
              handle, first_seen_ms, latest_seen_ms, follower_max, watched_status, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(handle) DO UPDATE SET
              first_seen_ms = LEAST(account_profiles.first_seen_ms, excluded.first_seen_ms),
              latest_seen_ms = GREATEST(account_profiles.latest_seen_ms, excluded.latest_seen_ms),
              follower_max = CASE
                WHEN account_profiles.follower_max IS NULL THEN excluded.follower_max
                WHEN excluded.follower_max IS NULL THEN account_profiles.follower_max
                ELSE GREATEST(account_profiles.follower_max, excluded.follower_max)
              END,
              watched_status = CASE
                WHEN account_profiles.watched_status = 'watched' OR excluded.watched_status = 'watched'
                  THEN 'watched'
                ELSE excluded.watched_status
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            (normalized, int(first_seen_ms), int(latest_seen_ms), follower_max, watched_status, now_ms, now_ms),
        )
        if commit:
            self.conn.commit()

    def upsert_directory_entry(
        self,
        *,
        handle: str,
        gmgn_user_id: str | None,
        user_tags: tuple[str, ...],
        platform_followers: int | None,
        observed_at_ms: int,
        commit: bool = True,
    ) -> None:
        normalized = _handle(handle)
        now_ms = _now_ms()
        tags_list = list(user_tags)
        self.conn.execute(
            """
            INSERT INTO account_profiles(
              handle, first_seen_ms, latest_seen_ms, follower_max, watched_status,
              gmgn_user_id, gmgn_user_tags, gmgn_platform_followers, gmgn_directory_observed_at_ms,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(handle) DO UPDATE SET
              gmgn_user_id = excluded.gmgn_user_id,
              gmgn_user_tags = excluded.gmgn_user_tags,
              gmgn_platform_followers = excluded.gmgn_platform_followers,
              gmgn_directory_observed_at_ms = excluded.gmgn_directory_observed_at_ms,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                normalized,
                int(observed_at_ms),
                int(observed_at_ms),
                None,
                "public",  # weakest status; upsert_profile promotes to 'watched' on event arrival
                gmgn_user_id,
                tags_list,
                int(platform_followers) if platform_followers is not None else None,
                int(observed_at_ms),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def upsert_token_call_stat(
        self,
        *,
        handle: str,
        token_id: str,
        first_mention_ms: int,
        mention_count: int,
        was_early_author: bool,
        outcome_status: str,
        price_change_5m_pct: float | None = None,
        price_change_1h_pct: float | None = None,
        price_change_24h_pct: float | None = None,
        max_drawdown_1h_pct: float | None = None,
        commit: bool = True,
    ) -> None:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO account_token_call_stats(
              handle, token_id, first_mention_ms, mention_count, was_early_author,
              price_change_5m_pct, price_change_1h_pct, price_change_24h_pct, max_drawdown_1h_pct,
              outcome_status, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(handle, token_id) DO UPDATE SET
              first_mention_ms = LEAST(account_token_call_stats.first_mention_ms, excluded.first_mention_ms),
              mention_count = excluded.mention_count,
              was_early_author = account_token_call_stats.was_early_author OR excluded.was_early_author,
              price_change_5m_pct = excluded.price_change_5m_pct,
              price_change_1h_pct = excluded.price_change_1h_pct,
              price_change_24h_pct = excluded.price_change_24h_pct,
              max_drawdown_1h_pct = excluded.max_drawdown_1h_pct,
              outcome_status = excluded.outcome_status,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _handle(handle),
                token_id,
                int(first_mention_ms),
                int(mention_count),
                was_early_author,
                price_change_5m_pct,
                price_change_1h_pct,
                price_change_24h_pct,
                max_drawdown_1h_pct,
                outcome_status,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def insert_quality_snapshot(
        self,
        *,
        handle: str,
        window: str,
        precision_score: float | None,
        early_call_score: float | None,
        spam_risk_score: float | None,
        avg_realized_return: float | None,
        sample_size: int,
        commit: bool = True,
    ) -> str:
        normalized = _handle(handle)
        now_ms = _now_ms()
        snapshot_id = _id("account_quality_snapshot", normalized, window, str(now_ms))
        self.conn.execute(
            """
            INSERT INTO account_quality_snapshots(
              snapshot_id, handle, "window", precision_score, early_call_score, spam_risk_score,
              avg_realized_return, sample_size, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot_id,
                normalized,
                window,
                precision_score,
                early_call_score,
                spam_risk_score,
                avg_realized_return,
                int(sample_size),
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return snapshot_id

    def account_quality(self, handle: str) -> dict[str, Any]:
        normalized = _handle(handle)
        profile = self.conn.execute(
            """
            SELECT *
            FROM account_profiles
            WHERE handle = %s
            """,
            (normalized,),
        ).fetchone()
        stats = self.conn.execute(
            """
            SELECT *
            FROM account_token_call_stats
            WHERE handle = %s
            ORDER BY first_mention_ms DESC, token_id
            LIMIT 50
            """,
            (normalized,),
        ).fetchall()
        snapshots = self.conn.execute(
            """
            SELECT *
            FROM account_quality_snapshots
            WHERE handle = %s
            ORDER BY updated_at_ms DESC, "window"
            LIMIT 20
            """,
            (normalized,),
        ).fetchall()
        return {
            "profile": dict(profile) if profile else None,
            "token_call_stats": [dict(row) for row in stats],
            "quality_snapshots": [dict(row) for row in snapshots],
        }

    def accounts_quality(self, handles: list[str]) -> list[dict[str, Any]]:
        return [self.account_quality(handle) for handle in handles]

    def profiles_by_handles(self, handles: list[str]) -> dict[str, dict[str, Any]]:
        normalized = sorted({_handle(handle) for handle in handles if handle.strip()})
        if not normalized:
            return {}
        placeholders = ",".join("%s" for _ in normalized)
        rows = self.conn.execute(
            f"""
            SELECT handle, watched_status
            FROM account_profiles
            WHERE handle IN ({placeholders})
            """,
            normalized,
        ).fetchall()
        return {str(row["handle"]): dict(row) for row in rows}

    def account_token_rows(self, *, resolver_policy_version: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH filtered AS (
              SELECT
                tir.target_type,
                tir.target_id,
                CASE
                  WHEN tir.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN 'chain_token'
                  WHEN tir.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN 'cex_symbol'
                  ELSE NULL
                END AS market_target_type,
                CASE
                  WHEN tir.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN registry_assets.chain_id || ':' || registry_assets.address
                  WHEN tir.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN price_feeds.provider || ':' || price_feeds.native_market_id
                  ELSE NULL
                END AS market_target_id,
                lower(events.author_handle) AS handle,
                tir.event_id,
                events.received_at_ms,
                events.author_followers,
                events.is_watched
              FROM token_intent_resolutions tir
              JOIN events ON events.event_id = tir.event_id
              LEFT JOIN registry_assets
                ON tir.target_type = 'Asset'
               AND registry_assets.asset_id = tir.target_id
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_feeds
                WHERE tir.target_type = 'CexToken'
                  AND price_feeds.subject_type = 'CexToken'
                  AND price_feeds.subject_id = tir.target_id
                  AND price_feeds.provider = 'binance'
                  AND price_feeds.feed_type = 'cex_swap'
                  AND price_feeds.quote_symbol = 'USDT'
                  AND price_feeds.status = 'canonical'
                ORDER BY
                  price_feeds.updated_at_ms DESC,
                  price_feeds.native_market_id ASC
                LIMIT 1
              ) price_feeds ON true
              WHERE tir.target_type IN ('Asset', 'CexToken')
                AND tir.target_id IS NOT NULL
                AND tir.is_current = true
                AND tir.resolver_policy_version = %s
                AND events.author_handle IS NOT NULL
                AND events.author_handle != ''
                AND tir.resolution_status IN ('EXACT', 'UNIQUE_BY_CONTEXT')
            ),
            token_first AS (
              SELECT target_type, target_id, MIN(received_at_ms) AS global_first_mention_ms
              FROM filtered
              GROUP BY target_type, target_id
            )
            SELECT
              f.handle,
              f.target_type,
              f.target_id,
              f.market_target_type,
              f.market_target_id,
              MIN(f.received_at_ms) AS first_mention_ms,
              MAX(f.received_at_ms) AS latest_mention_ms,
              COUNT(DISTINCT f.event_id) AS mention_count,
              MAX(f.author_followers) AS follower_max,
              SUM(CASE WHEN f.is_watched = true THEN 1 ELSE 0 END) AS watched_count,
              MIN(tf.global_first_mention_ms) AS global_first_mention_ms
            FROM filtered f
            JOIN token_first tf
              ON tf.target_type = f.target_type
             AND tf.target_id = f.target_id
            GROUP BY f.handle, f.target_type, f.target_id, f.market_target_type, f.market_target_id
            ORDER BY first_mention_ms DESC, f.handle, f.target_type, f.target_id
            LIMIT %s
            """,
            (resolver_policy_version, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def market_ticks_for_token(
        self,
        *,
        target_type: str,
        target_id: str,
        first_mention_ms: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              price_usd AS price,
              observed_at_ms AS received_at_ms
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
              AND observed_at_ms >= %(start_ms)s
              AND observed_at_ms <= %(end_ms)s
              AND price_usd IS NOT NULL
            ORDER BY observed_at_ms ASC
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "start_ms": first_mention_ms,
                "end_ms": first_mention_ms + 24 * 60 * 60_000,
            },
        ).fetchall()
        return [dict(row) for row in rows]


def _handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
