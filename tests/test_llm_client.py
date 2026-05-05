import asyncio
import json
from types import SimpleNamespace

from gmgn_twitter_intel.pipeline.llm_client import OpenAIChatEnrichmentClient
from gmgn_twitter_intel.pipeline.social_event_extraction import social_event_response_format


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
                                "is_signal_event": True,
                                "event_type": "meme_phrase_seed",
                                "source_action": "posted",
                                "subject": "TROLL social flow",
                                "direction_hint": "attention_positive",
                                "attention_mechanism": "meme_phrase",
                                "impact_hint": 0.74,
                                "semantic_novelty_hint": 0.63,
                                "confidence": 0.9,
                                "anchor_terms": [
                                    {
                                        "term": "$TROLL social flow",
                                        "role": "meme_phrase",
                                        "evidence": "$TROLL social flow",
                                    }
                                ],
                                "token_candidates": [
                                    {
                                        "symbol": "TROLL",
                                        "project_name": None,
                                        "chain": None,
                                        "address": None,
                                        "evidence": "$TROLL",
                                        "confidence": 0.86,
                                    }
                                ],
                                "semantic_risks": ["public_stream_coverage"],
                                "summary_zh": "TROLL 社交流正在加速。",
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


def test_openai_chat_client_uses_strict_social_event_schema():
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
    assert sdk_client.completions.kwargs["response_format"] == social_event_response_format()
    assert sdk_client.completions.kwargs["messages"][0]["role"] == "system"
    assert result.event_type == "meme_phrase_seed"
    assert result.subject == "TROLL social flow"
    assert result.token_candidates[0].symbol == "TROLL"
