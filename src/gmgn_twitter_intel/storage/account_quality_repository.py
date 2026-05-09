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
                "public",
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


def _handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
