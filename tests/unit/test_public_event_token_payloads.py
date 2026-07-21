from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from parallax.app.surfaces.api.routes_events import _recent_data
from parallax.app.surfaces.api.ws import MAX_SUBSCRIPTION_FILTER_VALUES, ClientSubscription, PublicWebSocketHub


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


def test_ws_subscription_rejects_filter_sets_over_budget_without_mutating_client() -> None:
    socket = _RecordingWebSocket()
    hub = PublicWebSocketHub(token="secret", repository_session=_exploding_repository_session)
    client = ClientSubscription(websocket=socket, symbols={"KEEP"})

    asyncio.run(
        hub._handle_client_message(
            client,
            json.dumps(
                {
                    "type": "subscribe",
                    "symbols": [f"SYM{i}" for i in range(MAX_SUBSCRIPTION_FILTER_VALUES + 1)],
                    "replay": 5,
                }
            ),
        )
    )

    assert json.loads(socket.messages) == {
        "type": "error",
        "code": "too_many_filters",
        "limit": MAX_SUBSCRIPTION_FILTER_VALUES,
    }
    assert client.symbols == {"KEEP"}


def test_ws_token_replay_batches_token_filters_into_one_repository_read() -> None:
    repos = _ReplayRepos()
    hub = PublicWebSocketHub(token="secret", repository_session=lambda: _RepoContext(repos))
    client = ClientSubscription(websocket=_RecordingWebSocket(), symbols={"ONE", "TWO", "THREE", "FOUR"})

    payloads = hub._replay_events(client, 10)

    assert repos.evidence.calls == []
    assert repos.evidence.token_filter_calls == [
        {
            "limit": 10,
            "per_filter_limit": 3,
            "cas": set(),
            "symbols": {"ONE", "TWO", "THREE", "FOUR"},
        }
    ]
    assert len(payloads) == 10


def test_ws_replay_batches_projected_event_payloads_for_page() -> None:
    repos = _RecentRepos(
        [
            {"event_id": "event-1", "text": "$ONE", "received_at_ms": 2},
            {"event_id": "event-2", "text": "$TWO", "received_at_ms": 1},
        ]
    )
    hub = PublicWebSocketHub(token="secret", repository_session=lambda: _RepoContext(repos))
    client = ClientSubscription(websocket=_RecordingWebSocket(), handles={"alice"})

    payloads = hub._replay_events(client, 2)

    assert [payload["event"]["event_id"] for payload in payloads] == ["event-1", "event-2"]
    assert repos.event_tokens.batch_event_ids == [("event-1", "event-2")]
    assert repos.event_tokens.event_ids == []
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


class _ReplayEvidence:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.token_filter_calls: list[dict[str, Any]] = []

    def recent_events(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(kwargs))
        label = str(kwargs.get("symbol") or kwargs.get("ca") or "all").lower()
        limit = int(kwargs["limit"])
        return [
            {
                "event_id": f"event-{label}-{index}",
                "received_at_ms": 10_000 - index,
            }
            for index in range(limit)
        ]

    def recent_events_for_token_filters(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.token_filter_calls.append(dict(kwargs))
        limit = int(kwargs["limit"])
        return [
            {
                "event_id": f"event-batch-{index}",
                "received_at_ms": 10_000 - index,
            }
            for index in range(limit)
        ]


class _ReplayRepos(_Repos):
    def __init__(self) -> None:
        super().__init__()
        self.evidence = _ReplayEvidence()
        self.entities = _BatchRepo("entities_for_event", "entities_for_events", {})
        self.signals = _BatchRepo("alerts_for_event", "alerts_for_events", {})
        self.token_intents = _BatchRepo("intents_for_event", "intents_for_events", {})


class _RepoContext:
    def __init__(self, repos: _ReplayRepos) -> None:
        self._repos = repos

    def __enter__(self) -> _ReplayRepos:
        return self._repos

    def __exit__(self, *_args: Any) -> None:
        return None


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.messages = ""

    async def send_text(self, message: str) -> None:
        self.messages = message


def _exploding_repository_session() -> Any:
    raise AssertionError("oversized websocket subscriptions must not open a repository session")


class _Runtime:
    def __init__(self, repos: _RecentRepos) -> None:
        self._repos = repos

    def repositories(self) -> _Runtime:
        return self

    def __enter__(self) -> _RecentRepos:
        return self._repos

    def __exit__(self, *_args: Any) -> None:
        return None
