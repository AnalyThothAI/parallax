from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from parallax.app.surfaces.api.routes_events import _payload_for_event as http_payload_for_event
from parallax.app.surfaces.api.routes_events import _recent_data
from parallax.app.surfaces.api.ws import PublicWebSocketHub


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


def test_recent_data_batches_projected_event_tokens_for_page() -> None:
    repos = _RecentRepos(
        [
            {"event_id": "event-1", "text": "$ONE"},
            {"event_id": "event-2", "text": "$TWO"},
        ]
    )
    runtime = _Runtime(repos)

    data = _recent_data(
        runtime,
        limit=2,
        handles=set(),
        ca=None,
        chain=None,
        symbol=None,
        scope="all",
    )

    assert repos.event_tokens.batch_event_ids == [("event-1", "event-2")]
    assert repos.event_tokens.event_ids == []
    assert [item["token_resolutions"] for item in data["items"]] == [
        [{"target_id": "asset:one", "symbol": "ONE"}],
        [{"target_id": "asset:two", "symbol": "TWO"}],
    ]
    assert repos.entities.batch_event_ids == [("event-1", "event-2")]
    assert repos.entities.event_ids == []
    assert repos.signals.batch_event_ids == [("event-1", "event-2")]
    assert repos.signals.event_ids == []
    assert repos.token_intents.batch_event_ids == [("event-1", "event-2")]
    assert repos.token_intents.event_ids == []


class _Repos(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            entities=_StaticRepo("entities_for_event", []),
            signals=_StaticRepo("alerts_for_event", []),
            token_intents=_StaticRepo("intents_for_event", []),
            event_tokens=_EventTokens(),
            intent_resolutions=_ExplodingIntentResolutions(),
        )


class _EventTokens:
    def __init__(self) -> None:
        self.event_ids: list[str] = []
        self.batch_event_ids: list[tuple[str, ...]] = []

    def for_event(self, event_id: str) -> list[dict[str, Any]]:
        self.event_ids.append(event_id)
        return [{"target_id": "asset:voice", "symbol": "VOICE"}]

    def for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        self.batch_event_ids.append(event_ids)
        return {
            "event-1": [{"target_id": "asset:one", "symbol": "ONE"}],
            "event-2": [{"target_id": "asset:two", "symbol": "TWO"}],
        }


class _ExplodingIntentResolutions:
    def resolutions_for_event(self, event_id: str) -> list[dict[str, Any]]:
        raise AssertionError(f"public payload must not read raw intent resolutions for {event_id}")


class _StaticRepo:
    def __init__(self, method_name: str, value: Any) -> None:
        setattr(self, method_name, lambda _event_id: value)


class _BatchRepo:
    def __init__(self, single_name: str, batch_name: str, values: dict[str, Any]) -> None:
        self.event_ids: list[str] = []
        self.batch_event_ids: list[tuple[str, ...]] = []
        self.values = values
        setattr(self, single_name, self._single)
        setattr(self, batch_name, self._batch)

    def _single(self, event_id: str) -> Any:
        self.event_ids.append(event_id)
        return self.values.get(event_id, [])

    def _batch(self, event_ids: tuple[str, ...]) -> dict[str, Any]:
        self.batch_event_ids.append(event_ids)
        return {event_id: self.values.get(event_id, []) for event_id in event_ids}


class _RecentRepos(_Repos):
    def __init__(self, events: list[dict[str, Any]]) -> None:
        super().__init__()
        self.evidence = _Evidence(events)
        self.entities = _BatchRepo(
            "entities_for_event",
            "entities_for_events",
            {
                "event-1": [{"entity_id": "entity-1"}],
                "event-2": [{"entity_id": "entity-2"}],
            },
        )
        self.signals = _BatchRepo(
            "alerts_for_event",
            "alerts_for_events",
            {
                "event-1": [{"alert_id": "alert-1"}],
                "event-2": [{"alert_id": "alert-2"}],
            },
        )
        self.token_intents = _BatchRepo(
            "intents_for_event",
            "intents_for_events",
            {
                "event-1": [{"intent_id": "intent-1"}],
                "event-2": [{"intent_id": "intent-2"}],
            },
        )


class _Evidence:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    def recent_events(self, **_: Any) -> list[dict[str, Any]]:
        return self.events


class _Runtime:
    def __init__(self, repos: _RecentRepos) -> None:
        self._repos = repos

    def repositories(self) -> _Runtime:
        return self

    def __enter__(self) -> _RecentRepos:
        return self._repos

    def __exit__(self, *_args: Any) -> None:
        return None
