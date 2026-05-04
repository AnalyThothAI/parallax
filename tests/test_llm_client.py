import json
import urllib.request

from gmgn_twitter_intel.pipeline.llm_client import OpenAIChatEnrichmentClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
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
                        }
                    }
                ]
            }
        ).encode("utf-8")


def test_openai_chat_client_sends_application_headers(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAIChatEnrichmentClient(api_key="sk-test", model="gpt-test", base_url="https://example.test/v1")

    result = client._enrich_event_sync(
        event={
            "event_id": "event-1",
            "author_handle": "smoke",
            "text_clean": "$TROLL social flow is accelerating.",
            "search_text": "$TROLL social flow is accelerating.",
        },
        entities=[],
    )

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["timeout"] == 20.0
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["User-agent"] == "gmgn-twitter-intel/0.1"
    assert result.summary == "TROLL social flow is accelerating."
