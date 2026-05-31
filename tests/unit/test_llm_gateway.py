from __future__ import annotations

import asyncio

from parallax.app.runtime.llm_gateway import LLMGateway


def test_llm_gateway_is_litellm_config_holder() -> None:
    gateway = LLMGateway(
        api_key="sk-llm",
        base_url="https://provider.example/v1/",
        trace_enabled=True,
        trace_api_key="sk-trace",
    )

    assert gateway.api_key == "sk-llm"
    assert gateway.base_url == "https://provider.example/v1"
    assert gateway.trace_enabled is True
    assert gateway.trace_api_key_configured is True
    assert gateway.trace_export_enabled is False


def test_llm_gateway_has_no_provider_client_factory() -> None:
    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)

    assert not hasattr(gateway, "openai_client")
    assert not hasattr(gateway, "run_with_limits")


def test_llm_gateway_close_is_noop() -> None:
    gateway = LLMGateway(api_key="sk-test", trace_enabled=False)

    asyncio.run(gateway.aclose())
