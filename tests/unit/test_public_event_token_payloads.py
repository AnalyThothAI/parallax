from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.surfaces.api.http import _payload_for_event as http_payload_for_event
from gmgn_twitter_intel.app.surfaces.api.ws import PublicWebSocketHub


def test_http_event_payload_uses_projected_event_tokens() -> None:
    repos = _Repos()

    payload = http_payload_for_event(repos, {"event_id": "event-1"})

    assert payload["token_resolutions"] == [{"target_id": "asset:voice", "symbol": "VOICE"}]
    assert repos.event_tokens.event_ids == ["event-1"]


def test_ws_event_payload_uses_projected_event_tokens() -> None:
    repos = _Repos()

    payload = PublicWebSocketHub._payload_for_event(repos, {"event_id": "event-1"})

    assert payload["token_resolutions"] == [{"target_id": "asset:voice", "symbol": "VOICE"}]
    assert repos.event_tokens.event_ids == ["event-1"]


class _Repos(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            entities=_StaticRepo("entities_for_event", []),
            signals=_StaticRepo("alerts_for_event", []),
            token_intents=_StaticRepo("intents_for_event", []),
            event_tokens=_EventTokens(),
            intent_resolutions=_ExplodingIntentResolutions(),
            harness=_StaticRepo("harness_for_event", None),
        )


class _EventTokens:
    def __init__(self) -> None:
        self.event_ids: list[str] = []

    def for_event(self, event_id: str) -> list[dict[str, Any]]:
        self.event_ids.append(event_id)
        return [{"target_id": "asset:voice", "symbol": "VOICE"}]


class _ExplodingIntentResolutions:
    def resolutions_for_event(self, event_id: str) -> list[dict[str, Any]]:
        raise AssertionError(f"public payload must not read raw intent resolutions for {event_id}")


class _StaticRepo:
    def __init__(self, method_name: str, value: Any) -> None:
        setattr(self, method_name, lambda _event_id: value)
