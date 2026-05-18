from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.providers import ToolBudgetExceeded
from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import (
    fetch_official_token_profile,
    fetch_target_price_action,
    fetch_target_recent_tweets,
)

_MAX_RESULT_BYTES = 4 * 1024
_DEFAULT_TWEET_LIMIT = 15
_MIN_TWEET_LIMIT = 1
_MAX_TWEET_LIMIT = 30
_DEFAULT_PRICE_HOURS = 24
_MIN_PRICE_HOURS = 1
_MAX_PRICE_HOURS = 168


@dataclass
class AgentToolRuntime:
    db_pool: Any
    tool_calls_count: int = 0
    investigator_max_tool_calls: int = 5
    contributed_event_ids: set[str] = field(default_factory=set)

    def get_target_recent_tweets(
        self,
        *,
        target_id: str,
        limit: int = _DEFAULT_TWEET_LIMIT,
    ) -> dict[str, Any]:
        self._check_and_increment_budget()
        target = str(target_id or "").strip()
        bounded_limit = max(_MIN_TWEET_LIMIT, min(int(limit), _MAX_TWEET_LIMIT))
        if not target:
            return {
                "data": {"target_id": "", "tweets": []},
                "contributed_event_ids": [],
            }

        payload = fetch_target_recent_tweets(self.db_pool, target_id=target, limit=bounded_limit)
        if "error" in payload:
            return {"data": {"error": payload["error"]}, "contributed_event_ids": []}

        tweets = list(payload.get("tweets") or [])
        event_ids = [
            str(tweet.get("event_id")) for tweet in tweets if isinstance(tweet, dict) and tweet.get("event_id")
        ]
        data: dict[str, Any] = {**payload, "tweets": tweets}
        truncated = False
        while len(json.dumps(data).encode("utf-8")) > _MAX_RESULT_BYTES and tweets:
            tweets.pop()
            if event_ids:
                event_ids.pop()
            data["tweets"] = tweets
            truncated = True
        if truncated:
            data["truncated"] = True

        for event_id in event_ids:
            self.contributed_event_ids.add(event_id)

        return {"data": data, "contributed_event_ids": event_ids}

    def get_target_price_action(
        self,
        *,
        target_id: str,
        hours: int = _DEFAULT_PRICE_HOURS,
    ) -> dict[str, Any]:
        self._check_and_increment_budget()
        target = str(target_id or "").strip()
        bounded_hours = max(_MIN_PRICE_HOURS, min(int(hours), _MAX_PRICE_HOURS))
        if not target:
            return {
                "data": {"target_id": "", "hours": bounded_hours, "candles_count": 0},
                "contributed_event_ids": [],
            }

        payload = fetch_target_price_action(self.db_pool, target_id=target, hours=bounded_hours)
        if len(json.dumps(payload).encode("utf-8")) > _MAX_RESULT_BYTES:
            for key in (
                "holders_peak",
                "volume_24h_peak_usd",
                "liquidity_peak_usd",
                "price_min_usd",
                "price_max_usd",
            ):
                payload.pop(key, None)
                if len(json.dumps(payload).encode("utf-8")) <= _MAX_RESULT_BYTES:
                    break
            payload["truncated"] = True

        return {"data": payload, "contributed_event_ids": []}

    def get_official_token_profile(self, *, target_id: str) -> dict[str, Any]:
        self._check_and_increment_budget()
        target = str(target_id or "").strip()
        if not target:
            return {"data": {}, "contributed_event_ids": []}

        data = fetch_official_token_profile(self.db_pool, target_id=target)
        if len(json.dumps(data).encode("utf-8")) > _MAX_RESULT_BYTES:
            if isinstance(data.get("description"), str):
                data["description"] = data["description"][:1500]
            data["truncated"] = True

        return {"data": data, "contributed_event_ids": []}

    def _check_and_increment_budget(self) -> None:
        self.tool_calls_count += 1
        if self.tool_calls_count > self.investigator_max_tool_calls:
            raise ToolBudgetExceeded(
                f"investigator tool call budget exceeded: {self.tool_calls_count} > {self.investigator_max_tool_calls}"
            )


__all__ = ["AgentToolRuntime"]
