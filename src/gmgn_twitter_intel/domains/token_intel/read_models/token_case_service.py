from __future__ import annotations

from typing import Any

from .search_agent_brief import build_token_agent_brief
from .token_target_posts_service import TokenTargetPostsService
from .token_target_social_timeline_service import TokenTargetSocialTimelineService


class TokenCaseTargetNotFound(Exception):
    pass


class TokenCaseInvalidScope(Exception):
    pass


def normalize_token_case_scope(scope: str) -> tuple[str, str]:
    if scope == "all":
        return ("all", "all")
    if scope in {"matched", "watched"}:
        return ("matched", "watched")
    raise TokenCaseInvalidScope(scope)


class TokenCaseService:
    def __init__(self, *, targets: Any, profiles: Any, live_price_gateway: Any | None) -> None:
        self.targets = targets
        self.profiles = profiles
        self.live_price_gateway = live_price_gateway

    def dossier(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        posts_limit: int,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        target = self.targets.target_identity(target_type=target_type, target_id=target_id)
        if target is None:
            raise TokenCaseTargetNotFound(target_id)
        service_scope, response_scope = normalize_token_case_scope(scope)
        timeline = TokenTargetSocialTimelineService(targets=self.targets).timeline(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=service_scope,
            limit=max(posts_limit, 24),
            now_ms=now_ms,
        )
        posts = TokenTargetPostsService(targets=self.targets).target_posts(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=service_scope,
            post_range="current_window",
            sort="recent",
            limit=posts_limit,
            now_ms=now_ms,
        )
        timeline["query"]["scope"] = response_scope
        posts["query"]["scope"] = response_scope
        profile = self.profiles.profile_for_target(target_type=target_type, target_id=target_id)
        return {
            "target": target,
            "profile": profile,
            "timeline": timeline,
            "posts": posts,
            "agent_brief": build_token_agent_brief(target=target, timeline=timeline, posts=posts, radar_item=None),
            "market_live": self._market_live(target_type=target_type, target_id=target_id, now_ms=now_ms),
        }

    def _market_live(self, *, target_type: str, target_id: str, now_ms: int | None) -> dict[str, Any]:
        if self.live_price_gateway is None:
            return _market_snapshot(target_type=target_type, target_id=target_id, status="unsupported")
        snapshot = self.live_price_gateway.snapshot(target_type=target_type, target_id=target_id, now_ms=now_ms)
        if snapshot is None:
            return _market_snapshot(target_type=target_type, target_id=target_id, status="missing")
        return snapshot


def _market_snapshot(*, target_type: str, target_id: str, status: str) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "status": status,
        "price_usd": None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "holders": None,
        "observed_at_ms": None,
        "provider": None,
    }
