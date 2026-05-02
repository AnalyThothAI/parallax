from __future__ import annotations


class TokenFlowService:
    def __init__(self, signals):
        self.signals = signals

    def token_flow(self, *, window: str, limit: int = 20) -> list[dict]:
        return self.signals.token_flow(window=window, limit=limit)
