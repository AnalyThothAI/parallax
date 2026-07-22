# Ingest, resolution, Radar, and News projection hard cut

Mode: write-allowed

## Findings

- Collector publication now reuses the resolutions returned by the committed ingest result instead of opening a second repository session.
- Deleted response placeholders and an unused rebuild argument that did not drive any projection.
- Removed the duplicate Radar missing-work pass; the current hot/background schedulers remain authoritative.
- News reprojection now calls the required repository capability directly and preserves real query errors.

## Scope Adherence

Owned scope: pass

Conflict set: pass

## Changed Files

- `src/parallax/app/runtime/bootstrap.py`
- `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- `src/parallax/domains/ingestion/providers.py`
- `src/parallax/domains/ingestion/runtime/collector_service.py`
- `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- `src/parallax/domains/token_intel/interfaces.py`
- `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`
- `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/parallax/domains/token_intel/services/token_resolution_refresh.py`
- `tests/contract/test_provider_protocol_fixtures.py`
- `tests/integration/test_token_intent_rebuild.py`
- `tests/unit/domains/news_intel/test_news_projection_work.py`
- `tests/unit/test_collector_service.py`
- `tests/unit/test_token_intent_rebuild_runtime.py`
- `tests/unit/test_token_radar_projection_worker.py`

## Required Reading Evidence

Task classification: fact-to-projection data-flow implementation.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, the domain audit report, and the relevant ingestion, Asset Market, Token Intel, and News architecture maps.

## Verification Evidence

```text
$ uv run pytest -q tests/unit/test_collector_service.py tests/contract/test_provider_protocol_fixtures.py tests/unit/test_token_intent_rebuild_runtime.py tests/integration/test_token_intent_rebuild.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py
...........................................                              [100%]
43 passed in 15.27s
exit code: 0
```

## Remaining Risks

- The full integration suite remains the authority for transaction and publication behavior across real repository sessions.
