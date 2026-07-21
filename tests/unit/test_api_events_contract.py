from __future__ import annotations

from types import SimpleNamespace

import pytest

from parallax.app.surfaces.api import routes_events


def test_watched_handle_decoration_propagates_read_model_failure_instead_of_returning_all_false(monkeypatch) -> None:
    class FailingAccountQualityService:
        @staticmethod
        def from_conn(conn: object) -> FailingAccountQualityService:
            del conn
            return FailingAccountQualityService()

        def watched_handles(self, handles: list[str]) -> set[str]:
            del handles
            raise RuntimeError("account quality unavailable")

    monkeypatch.setattr(routes_events, "AccountQualityService", FailingAccountQualityService)

    with pytest.raises(RuntimeError, match="account quality unavailable"):
        routes_events._watched_handle_set(SimpleNamespace(conn=object()), ["alice"])


def test_watched_handle_decoration_skips_repository_read_for_empty_input(monkeypatch) -> None:
    class UnexpectedAccountQualityService:
        @staticmethod
        def from_conn(conn: object) -> UnexpectedAccountQualityService:
            del conn
            raise AssertionError("empty handles must not open the read model")

    monkeypatch.setattr(routes_events, "AccountQualityService", UnexpectedAccountQualityService)

    assert routes_events._watched_handle_set(SimpleNamespace(conn=object()), []) == set()
