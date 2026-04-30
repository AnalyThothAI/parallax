import json

from gmgn_twitter_cli.pipeline.llm_enrichment import LlmEnrichmentService
from gmgn_twitter_cli.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_cli.storage.llm_repository import LlmRepository


class FakeLlmClient:
    def __init__(self, payload):
        self.payload = payload

    def extract(self, events):
        return self.payload


def test_llm_enrichment_persists_evidence_bound_claims(tmp_path):
    client = build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8)
    repo = LlmRepository(client)
    event = {"event_id": "event-1", "content": {"text": "PEPE listed on exchange"}}
    service = LlmEnrichmentService(
        repo,
        FakeLlmClient(
            {
                "claims": [{"event_id": "event-1", "claim": "PEPE listed", "quote": "PEPE listed", "confidence": 0.9}],
                "entities": [],
                "relations": [],
            }
        ),
    )

    run = service.enrich_events([event], scope="test", model="fake")

    assert run["status"] == "succeeded"
    assert repo.count_claims(run["llm_run_id"]) == 1
    client.close()


def test_llm_enrichment_rejects_missing_quotes_without_corrupting_rows(tmp_path):
    client = build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8)
    repo = LlmRepository(client)
    event = {"event_id": "event-1", "content": {"text": "PEPE listed on exchange"}}
    service = LlmEnrichmentService(
        repo,
        FakeLlmClient(
            {
                "claims": [{"event_id": "event-1", "claim": "bad", "quote": "not in tweet", "confidence": 0.9}],
                "entities": [],
                "relations": [],
            }
        ),
    )

    run = service.enrich_events([event], scope="test", model="fake")

    assert run["status"] == "failed"
    assert "quote_not_found" in run["error"]
    assert repo.count_claims(run["llm_run_id"]) == 0
    client.close()


def test_llm_enrichment_rejects_invalid_json_response(tmp_path):
    client = build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8)
    repo = LlmRepository(client)
    event = {"event_id": "event-1", "content": {"text": "PEPE listed on exchange"}}
    service = LlmEnrichmentService(repo, FakeLlmClient(json.dumps({"claims": "wrong"})))

    run = service.enrich_events([event], scope="test", model="fake")

    assert run["status"] == "failed"
    assert repo.count_claims(run["llm_run_id"]) == 0
    client.close()
