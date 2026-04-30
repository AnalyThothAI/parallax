from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..pipeline.token_registry import TokenResolver

LoopFactory = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class BackgroundLoopRunner:
    factories: list[LoopFactory] = field(default_factory=list)
    tasks: list[asyncio.Task] = field(default_factory=list)

    def start(self) -> None:
        if self.tasks:
            return
        self.tasks = [asyncio.create_task(factory()) for factory in self.factories]

    async def stop(self) -> None:
        tasks = list(self.tasks)
        self.tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def warm_token_resolution_loop(repo, resolver: TokenResolver, *, interval_seconds: float = 60.0, limit: int = 50):
    while True:
        rows = repo.client.query_where(
            "tweet_entities",
            where="entity_type = 'symbol' AND token_resolution_status = 'unresolved'",
            limit=limit,
        )
        for row in rows:
            resolver.resolve_symbol(str(row.get("normalized_value") or ""))
        await asyncio.sleep(interval_seconds)
