from __future__ import annotations

import pytest

from gmgn_twitter_intel.app.runtime import provider_wiring
from gmgn_twitter_intel.platform.config.settings import Settings


def test_equity_event_provider_wiring_is_disabled_by_default() -> None:
    providers = provider_wiring.wire_providers(Settings(ws_token="secret"), start_collector=False)

    assert providers.equity_event_intel.document_provider is None
    assert providers.equity_event_intel.brief_provider is None


def test_equity_event_brief_provider_requires_agent_gateway() -> None:
    settings = Settings(
        ws_token="secret",
        llm={"api_key": "test-key"},
        equity_event_intel={"enabled": True, "agent": {"enabled": True}},
        workers={"agent_runtime": {"defaults": {"model": "gpt-equity"}}, "equity_event_brief": {"enabled": True}},
    )

    with pytest.raises(RuntimeError, match="AgentExecutionGateway is required"):
        provider_wiring.wire_providers(settings, start_collector=False)
