# Plan — Daily Macro SPY Judgment

**Status**: Verified
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/spec.md`
**Worktree**: `.worktrees/daily-macro-spy-judgment/`
**Branch**: `codex/daily-macro-spy-judgment`
**Approved by**: delegated user goal and GitHub Issue #6
**Approved at**: 2026-07-23

## Analyze Gate

| Check | Result |
|-------|--------|
| Issue authority | Pass: GitHub Issue #6 is open, labeled `ready-for-agent`, and explicitly authorizes full implementation. |
| Worktree isolation | Pass: implementation branch and worktree are isolated from clean `main`. |
| Existing product boundary | Pass: `macro_decision_v2` is the deterministic exactly-six current read model and remains unchanged. |
| Material-fact availability | Pass: `macro_observations` preserves `source_ts`, `ingested_at_ms`, and payload lineage; News preserves published/fetched timestamps and source trust, enabling a conservative versioned eligibility policy. |
| Agent runtime | Pass: current stable `deepagents==0.6.12` provides `create_deep_agent`, declarative subagents, native `task`, response formats, and harness profiles; `langchain-litellm` adapts the existing configured provider. |
| Transaction seam | Pass: current worker/repository sessions support short transactions around claim/finalize while model I/O remains outside transactions. |
| Public read seam | Pass: existing Macro routes and typed schemas can add one independent persisted-only read without changing six page identities. |
| Highest-risk gaps | Pass: point-in-time eligibility, immutable publication, bounded review, and real-provider receipt each have explicit failing-test and verification tasks. |

## Preflight

- [x] Worktree exists at `.worktrees/daily-macro-spy-judgment/` and `git branch --show-current` matches `codex/daily-macro-spy-judgment`.
- [x] `uv run parallax config` reports operator-owned paths without printing credentials.
- [x] Existing live PostgreSQL was inspected read-only for timestamp and source-health coverage.
- [x] The current DeepAgents public API was inspected from a clean dependency resolution.

## Implementation sequence

1. Add failing strict-contract, calendar, availability, migration, and PostgreSQL publication tests.
2. Add immutable job/publication/outcome storage and repositories.
3. Implement deterministic EvidencePack compilation, health policy, judgment gates, and Chinese renderer.
4. Pin and integrate the real two-role DeepAgents runtime behind a narrow domain protocol.
5. Add the one-writer daily worker, bounded retry/catch-up, and outcome maturation.
6. Add the persisted-only API and generated contract.
7. Narrow architecture guards, wire config/factory/manifest, and update canonical docs.
8. Run focused, full, Docker, and real-provider shadow verification; audit every acceptance criterion and move the SDD record only when verified.
9. Render the persisted judgment on `/macro`, then rerun frontend, browser, main-merge, image, and production verification.

## Key decisions

- Use a conservative versioned availability policy: exact source timestamps must be at or before cutoff; date-only facts are eligible only when their source semantics prove availability, otherwise they are excluded and degrade/block the pack.
- Freeze the first eligible pack per session before model I/O. Retries reuse the exact same persisted pack.
- Use session date as every product key. Do not add a mutable latest/current table.
- Keep the DeepAgents integration in the model-execution integration package; domain code depends on a narrow Analyst/Reviewer protocol.
- Configure Analyst and Reviewer model identities separately while keeping one provider credential/endpoint boundary and one bounded graph.
- Disable all default Agent capabilities except native `task`; custom tools can only read the frozen pack and submit a structured draft.
- Cap execution at one initial review and, only after `revise`, one Analyst revision plus one pass/block factual-closure review.
- Keep the UI to one compact section on the existing Overview. It reads the
  persisted contract, makes no new route, and adds no inference or trading
  controls.

## Acceptance test commands

- AC1: `uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- AC2: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_pack.py tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- AC3: `uv run pytest tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q`
- AC5: `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py -q`
- AC6: `uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- AC7: `uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py tests/integration/test_daily_macro_judgment_migration.py -q`
- AC8: `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment_worker.py tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- AC9: `uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- AC10: `uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q`
- AC11: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py tests/integration/test_daily_macro_judgment_migration.py -q`
- AC12: `make check`
- AC13: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroDecisionHardCut.test.ts && npm run test:e2e -- macro-evidence-pages.spec.ts`

## Runtime verification

- Build and start the actual application image after migration.
- Confirm readiness reports the new migration revision and all workers compose.
- Run one bounded shadow session against the configured real provider with no credentials in output.
- Persist or capture a redacted receipt containing session, pack hash, Analyst model/version, native Reviewer disposition, invocation counts, gate result, and no publication mutation when configured as shadow-only.
- Read the resulting persisted API contract and verify no request-time model call.
- Hard-reload `/macro` from the rebuilt main image and verify the Daily AI
  section, eight deterministic lanes, responsive containment, and zero failed
  API requests.

## Risks and repairs

- Historical material facts may lack trustworthy point-in-time availability. Exclude them; never infer availability from ingestion time.
- Existing providers can return invalid structured output or omit native delegation. Block publication and retry only within the job budget.
- A model may leak forbidden trading or probabilistic language. Strict fields plus recursive forbidden-key/text gates reject it.
- Operator config may be unavailable. Worker reports unavailable without affecting deterministic Macro; final real-provider gate remains unverified until a successful receipt exists.
- Full-suite regressions outside the lane are repaired only when caused by this change; no guard is deleted to make the feature pass.
