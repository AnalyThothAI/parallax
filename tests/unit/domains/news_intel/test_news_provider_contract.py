from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from parallax.app.runtime.app import _news_provider_contract_payload
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from parallax.domains.news_intel.services.news_provider_contract import (
    NewsProviderContractError,
    validate_news_provider_contract,
)
from parallax.platform.config.news_provider_types import RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES
from parallax.platform.config.settings import NewsFetchWorkerSettings

NOW_MS = 1_779_000_000_000


def test_opennews_registry_schema_and_config_contract_passes() -> None:
    evidence = validate_news_provider_contract(
        configured_sources=[_source(provider_type="opennews")],
        supported_provider_types=("rss", "opennews"),
        schema_provider_types=("rss", "opennews", "manual_api"),
    )

    assert evidence == {
        "ok": True,
        "configured_provider_types": ["opennews"],
        "supported_provider_types": ["opennews", "rss"],
        "schema_provider_types": ["manual_api", "opennews", "rss"],
    }


def test_schema_constraint_missing_opennews_fails_before_db_write() -> None:
    with pytest.raises(NewsProviderContractError) as exc_info:
        validate_news_provider_contract(
            configured_sources=[_source(provider_type="opennews")],
            supported_provider_types=("rss", "opennews"),
            schema_provider_types=("rss",),
        )

    error = exc_info.value
    assert error.reason == "news_provider_type_missing_from_db_constraint"
    assert error.provider_types == ("opennews",)
    assert error.to_payload()["configured_provider_types"] == ["opennews"]


def test_registry_missing_configured_provider_fails() -> None:
    with pytest.raises(NewsProviderContractError) as exc_info:
        validate_news_provider_contract(
            configured_sources=[_source(provider_type="opennews")],
            supported_provider_types=("rss",),
            schema_provider_types=("rss", "opennews"),
        )

    error = exc_info.value
    assert error.reason == "news_provider_type_missing_from_registry"
    assert error.provider_types == ("opennews",)


def test_repository_constraint_parser_reads_0105_provider_values_from_news_sources_constraint() -> None:
    constraint_def = (
        "CHECK ((provider_type)::text = ANY "
        "(ARRAY['rss'::text, 'atom'::text, 'json_feed'::text, 'cryptopanic'::text, "
        "'openbb'::text, 'telegram_public'::text, 'twitter_profile'::text, "
        "'twitter_thread_context'::text, 'reddit'::text, 'hackernews'::text, "
        "'github'::text, 'ossinsight'::text, 'manual_api'::text, 'opennews'::text]))"
    )
    repo = NewsRepository(FakeConstraintConn(constraint_def))

    values = repo.news_source_provider_constraint_values()

    assert values == (
        "rss",
        "atom",
        "json_feed",
        "cryptopanic",
        "openbb",
        "telegram_public",
        "twitter_profile",
        "twitter_thread_context",
        "reddit",
        "hackernews",
        "github",
        "ossinsight",
        "manual_api",
        "opennews",
    )


def test_news_fetch_worker_returns_contract_error_without_provider_capability_probe() -> None:
    source = _source(provider_type="opennews")
    repo = FakeNewsRepository(schema_provider_types=("rss",))
    db = FakeDB(repo)
    worker = NewsFetchWorker(
        name="news_fetch",
        settings=NewsFetchWorkerSettings(batch_size=10, lease_ms=60_000, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        feed_client=FakeCapabilityProbeProvider(),
        news_settings=SimpleNamespace(sources=(source,)),
        wake_emitter=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["reason"] == "news_provider_type_missing_from_db_constraint"
    assert result.notes["provider_types"] == ["opennews"]
    assert repo.reconcile_calls == 0
    assert repo.claim_due_calls == 0


def test_runtime_status_news_provider_contract_uses_static_provider_types_without_provider_probe() -> None:
    source = _source(provider_type="opennews")
    runtime = SimpleNamespace(
        settings=SimpleNamespace(news_intel=SimpleNamespace(sources=(source,))),
        providers=SimpleNamespace(news_intel=SimpleNamespace(feed_client=FakeCapabilityProbeProvider())),
        repositories=lambda: FakeRuntimeRepositoryContext(FakeNewsRepository(schema_provider_types=PROVIDER_SCHEMA)),
    )

    payload = _news_provider_contract_payload(runtime)

    assert payload["ok"] is True
    assert payload["configured_provider_types"] == ["opennews"]
    assert payload["supported_provider_types"] == list(RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES)


def test_runtime_status_news_provider_contract_requires_news_intel_settings_contract() -> None:
    runtime = SimpleNamespace(
        settings=SimpleNamespace(),
        repositories=lambda: FakeRuntimeRepositoryContext(FakeNewsRepository(schema_provider_types=PROVIDER_SCHEMA)),
    )

    with pytest.raises(AttributeError, match="news_intel"):
        _news_provider_contract_payload(runtime)


def test_news_fetch_worker_fails_fast_when_schema_introspection_missing() -> None:
    source = _source(provider_type="opennews")
    repo = FakeNewsRepositoryWithoutSchemaIntrospection()
    db = FakeDB(repo)
    worker = NewsFetchWorker(
        name="news_fetch",
        settings=NewsFetchWorkerSettings(batch_size=10, lease_ms=60_000, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        feed_client=FakeCapabilityProbeProvider(),
        news_settings=SimpleNamespace(sources=(source,)),
        wake_emitter=None,
    )

    with pytest.raises(AttributeError, match="news_source_provider_constraint_values"):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repo.reconcile_calls == 0
    assert repo.claim_due_calls == 0


def _source(*, provider_type: str) -> dict[str, object]:
    return {
        "source_id": f"{provider_type}-source",
        "provider_type": provider_type,
        "feed_url": f"{provider_type}://feed",
        "source_domain": "example.test",
        "source_name": "Example",
    }


PROVIDER_SCHEMA = (
    "rss",
    "atom",
    "json_feed",
    "cryptopanic",
    "opennews",
)


class FakeConstraintConn:
    def __init__(self, constraint_def: str) -> None:
        self.constraint_def = constraint_def

    def execute(self, sql: str, params: tuple[object, ...] = ()):
        assert "pg_constraint" in sql
        assert "conrelid = 'news_sources'::regclass" in " ".join(sql.split())
        assert params == ("news_sources_provider_type_check",)
        return SimpleNamespace(fetchone=lambda: {"constraint_def": self.constraint_def})


class FakeRegistryProvider:
    provider_type = "registry"

    def __init__(self, *, supported_provider_types: tuple[str, ...]) -> None:
        self._supported_provider_types = supported_provider_types

    def supported_provider_types(self) -> tuple[str, ...]:
        return self._supported_provider_types


class FakeCapabilityProbeProvider:
    provider_type = "fake"

    def fetch(self, *args, **kwargs):  # pragma: no cover - contract failure exits before fetch
        raise AssertionError("provider fetch should not run when contract validation fails")

    def close(self) -> None:
        return None

    def supported_provider_types(self) -> tuple[str, ...]:
        raise AssertionError("NewsFetchWorker must use the static provider-type contract")


class FakeNewsRepository:
    def __init__(self, *, schema_provider_types: tuple[str, ...]) -> None:
        self.schema_provider_types = schema_provider_types
        self.reconcile_calls = 0
        self.claim_due_calls = 0

    def news_source_provider_constraint_values(self) -> tuple[str, ...]:
        return self.schema_provider_types

    def reconcile_configured_sources(self, sources, *, now_ms: int, commit: bool = True):
        self.reconcile_calls += 1
        return []

    def claim_due_sources(self, *, now_ms: int, limit: int, claim_lease_ms: int, commit: bool = True):
        del claim_lease_ms
        self.claim_due_calls += 1
        return []


class FakeNewsRepositoryWithoutSchemaIntrospection:
    def __init__(self) -> None:
        self.reconcile_calls = 0
        self.claim_due_calls = 0

    def reconcile_configured_sources(self, sources, *, now_ms: int, commit: bool = True):
        self.reconcile_calls += 1
        return []

    def claim_due_sources(self, *, now_ms: int, limit: int, claim_lease_ms: int, commit: bool = True):
        del claim_lease_ms
        self.claim_due_calls += 1
        return []


class FakeDB:
    def __init__(self, repo: FakeNewsRepository) -> None:
        self.repo = repo
        self.conn = FakeConn()

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert name == "news_fetch"
        assert statement_timeout_seconds == 30
        yield SimpleNamespace(news=self.repo, conn=self.conn, transaction=self.conn.transaction)


class FakeRuntimeRepositoryContext:
    def __init__(self, repo: FakeNewsRepository) -> None:
        self.repo = repo

    def __enter__(self):
        return SimpleNamespace(news=self.repo)

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    @contextmanager
    def transaction(self):
        yield
