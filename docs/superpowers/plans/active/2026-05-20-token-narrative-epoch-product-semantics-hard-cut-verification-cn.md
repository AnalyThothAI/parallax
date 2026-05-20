# Token Narrative Epoch Hard Cut Verification

Date: 2026-05-20
Branch: `codex/token-narrative-epoch-product-semantics-hard-cut`

## Passed

- `uv run ruff check .`
  - Result: passed.
- Focused backend gate:
  - Command: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_currentness.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/integration/test_narrative_repository.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/test_api_narrative_contract.py tests/unit/test_pulse_evidence_packet_builder.py tests/integration/test_pulse_evidence_repository.py tests/architecture/test_worker_runtime_contracts.py tests/contract/test_openapi_drift.py -q`
  - Result: `161 passed in 108.43s`.
- Earlier focused backend merge gate:
  - Command: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_currentness.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/integration/test_narrative_repository.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/test_api_narrative_contract.py tests/unit/test_pulse_evidence_packet_builder.py tests/integration/test_pulse_evidence_repository.py -q`
  - Result: `96 passed in 96.83s`.
- API contract generation:
  - Command: `make regen-contract`
  - Result: passed; regenerated `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts`.
- API/OpenAPI focused contract:
  - Command: `uv run pytest tests/unit/test_api_narrative_contract.py tests/contract/test_openapi_drift.py -q`
  - Result: `13 passed in 3.68s`.
- Frontend focused currentness gate:
  - Command: `cd web && npm run test -- --run tests/unit/shared/model/narrativeDataGaps.test.ts tests/unit/shared/model/tokenRadarCompactCase.test.ts tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts tests/component/features/live/ui/TokenRadarTable.test.tsx tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`
  - Result: `5 passed`, `37 tests passed`.
- Frontend typecheck:
  - Command: `cd web && npm run typecheck`
  - Result: passed.
- Frontend build:
  - Command: `cd web && npm run build`
  - Result: passed. Vite reported the existing chunk-size warning for a >500 kB bundle.

## Not Fully Passed

- Full frontend test suite:
  - Command: `cd web && npm run test -- --run`
  - Result: failed in `tests/routes/watchlist.route.test.tsx`.
  - Failure: `AppRoutes` read `stocksRadarQuery.data.items.length` when the test mock did not provide `items`, so `$ALOY` was not rendered.
  - This is outside the narrative currentness path; focused Token Radar/Token Case currentness tests passed.
- Full backend pytest:
  - Command: `uv run pytest -q`
  - Result: stopped after several minutes because it had already emitted failures and was still below 20 percent completion.
  - Residual risk: full-suite failures need separate triage before landing if this branch requires a fully clean repository-wide gate.

## Verified Product Behavior

- `5m` Token Radar narrative returns `currentness.display_status="unsupported_window"` and does not write discussion digest rows.
- `1h`/`4h`/`24h` public snapshots compose last-ready digest plus current admission delta.
- Fingerprint mismatch no longer hides ready digest rows; public display becomes `updating` or `stale` with delta counts.
- Digest worker does not overwrite an existing ready digest with pending/insufficient status when current semantics are still catching up.
- Pulse receives stale/updating digest as context only; current evidence refs remain required for non-abstain support.
- OpenAPI now exposes `NarrativeCurrentnessData`, `TokenDiscussionDigestData`, `NarrativeDeltaData`, and `TokenRadarRowData`.

## Generated Artifacts

- `docs/generated/openapi.json`
- `web/src/lib/types/openapi.ts`
- `docs/generated/cli-help.md`
- `docs/generated/db-schema.md`

`cli-help.md` and `db-schema.md` changed during verification because the generated artifacts were stale relative to current CLI/schema state.
