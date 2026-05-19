from __future__ import annotations

import asyncio

from gmgn_twitter_intel.app.runtime.llm_gateway import LLMGateway


def test_llm_gateway_sets_configured_trace_export_key(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.set_tracing_export_api_key",
        exported_keys.append,
    )

    gateway = LLMGateway(
        api_key="sk-llm",
        base_url="https://api.openai.com/v1",
        trace_enabled=True,
        trace_api_key="sk-trace",
    )

    assert exported_keys == ["sk-trace"]
    assert gateway.trace_export_enabled is True


def test_llm_gateway_uses_openai_api_key_for_openai_trace_export(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.set_tracing_export_api_key",
        exported_keys.append,
    )

    gateway = LLMGateway(
        api_key="sk-openai",
        base_url="https://api.openai.com/v1",
        trace_enabled=True,
    )

    assert exported_keys == ["sk-openai"]
    assert gateway.trace_export_enabled is True


def test_llm_gateway_does_not_export_custom_provider_key(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.set_tracing_export_api_key",
        exported_keys.append,
    )

    gateway = LLMGateway(
        api_key="custom-provider-key",
        base_url="https://big9er.example/v1",
        trace_enabled=True,
    )

    assert exported_keys == []
    assert gateway.trace_export_enabled is False


def test_llm_gateway_exports_explicit_trace_key_for_custom_provider(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.set_tracing_export_api_key",
        exported_keys.append,
    )

    gateway = LLMGateway(
        api_key="custom-provider-key",
        base_url="https://big9er.example/v1",
        trace_enabled=True,
        trace_api_key="sk-trace",
    )

    assert exported_keys == ["sk-trace"]
    assert gateway.trace_export_enabled is True


def test_llm_gateway_no_longer_exposes_execution_limit_api() -> None:
    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)

    assert not hasattr(gateway, "run_with_limits")
    assert not hasattr(gateway, "last_worker_name")
    assert not hasattr(gateway, "last_stage")


def test_openai_client_uses_shared_headers_and_owned_http_clients(monkeypatch) -> None:
    http_clients: list[FakeHttpClient] = []
    openai_clients: list[FakeAsyncOpenAI] = []

    def fake_http_client(*, trust_env: bool) -> FakeHttpClient:
        client = FakeHttpClient(trust_env=trust_env)
        http_clients.append(client)
        return client

    def fake_openai_client(**kwargs) -> FakeAsyncOpenAI:
        client = FakeAsyncOpenAI(**kwargs)
        openai_clients.append(client)
        return client

    monkeypatch.setattr("gmgn_twitter_intel.app.runtime.llm_gateway.httpx.AsyncClient", fake_http_client)
    monkeypatch.setattr("gmgn_twitter_intel.app.runtime.llm_gateway.AsyncOpenAI", fake_openai_client)

    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)
    client = gateway.openai_client(model="gpt-test", base_url="https://api.openai.com/v1", timeout_s=7)

    assert client is openai_clients[0]
    assert openai_clients[0].kwargs["api_key"] == "sk-test"
    assert openai_clients[0].kwargs["base_url"] == "https://api.openai.com/v1"
    assert openai_clients[0].kwargs["timeout"] == 7
    assert openai_clients[0].kwargs["max_retries"] == 0
    assert openai_clients[0].kwargs["default_headers"] == {"User-Agent": "gmgn-twitter-intel/0.1"}
    assert openai_clients[0].kwargs["http_client"] is http_clients[0]
    assert http_clients[0].trust_env is False

    asyncio.run(gateway.aclose())

    assert openai_clients[0].closed is True


def test_openai_client_normalizes_root_base_url_to_v1(monkeypatch) -> None:
    openai_clients: list[FakeAsyncOpenAI] = []

    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.httpx.AsyncClient",
        lambda *, trust_env: FakeHttpClient(trust_env=trust_env),
    )
    monkeypatch.setattr(
        "gmgn_twitter_intel.app.runtime.llm_gateway.AsyncOpenAI",
        lambda **kwargs: openai_clients.append(FakeAsyncOpenAI(**kwargs)) or openai_clients[-1],
    )

    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)
    gateway.openai_client(model="gpt-test", base_url="https://api.openai.com", timeout_s=7)
    gateway.openai_client(model="qwen-test", base_url="https://big9er.example", timeout_s=7)

    assert [client.kwargs["base_url"] for client in openai_clients] == [
        "https://api.openai.com/v1",
        "https://big9er.example/v1",
    ]


class FakeHttpClient:
    def __init__(self, *, trust_env: bool) -> None:
        self.trust_env = trust_env


class FakeAsyncOpenAI:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False

    async def close(self) -> None:
        self.closed = True
