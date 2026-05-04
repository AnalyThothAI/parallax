import asyncio
import json
from types import SimpleNamespace

from gmgn_twitter_intel.pipeline.llm_client import OpenAIChatEnrichmentClient


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "summary": "TROLL social flow is accelerating.",
                                "narratives": [
                                    {
                                        "label": "TROLL Social Acceleration",
                                        "description": "TROLL social attention is accelerating.",
                                        "seed_family": "token_social_flow",
                                        "trigger_terms": ["TROLL", "social flow"],
                                        "market_interpretation": "Market may look for TROLL token flow.",
                                        "evidence": "$TROLL social flow",
                                        "confidence": 0.9,
                                    }
                                ],
                                "stance": "informational",
                                "intent": "technical_commentary",
                                "confidence": 0.9,
                            }
                        )
                    )
                )
            ]
        )


class FakeSdkClient:
    def __init__(self):
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def test_openai_chat_client_uses_sdk_chat_completions_json_mode():
    sdk_client = FakeSdkClient()
    client = OpenAIChatEnrichmentClient(
        api_key="sk-test",
        model="gpt-test",
        base_url="https://example.test/v1",
        sdk_client=sdk_client,
    )

    result = asyncio.run(
        client.enrich_event(
            event={
                "event_id": "event-1",
                "author_handle": "smoke",
                "text_clean": "$TROLL social flow is accelerating.",
                "search_text": "$TROLL social flow is accelerating.",
            },
            entities=[],
        )
    )

    assert sdk_client.completions.kwargs["model"] == "gpt-test"
    assert sdk_client.completions.kwargs["temperature"] == 0
    assert sdk_client.completions.kwargs["response_format"] == {"type": "json_object"}
    assert sdk_client.completions.kwargs["messages"][0]["role"] == "system"
    assert result.summary == "TROLL social flow is accelerating."
