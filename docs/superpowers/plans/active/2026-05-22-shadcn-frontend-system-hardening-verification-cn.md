# Shadcn Frontend System Hardening Verification

Date: 2026-05-22
Branch: `codex/shadcn-frontend-system-hardening`
Worktree: `.worktrees/shadcn-frontend-system-hardening`

## Summary

- Status: frontend implementation verified after merging current `main`; repository/Docker readiness has unrelated backend blockers recorded below.
- Scope: frontend shell/sidebar, shadcn primitives, unified page state, lazy route architecture, CSS/fixture cleanup, Docker smoke.
- Deviations: `make check-all` and `/readyz` are not green because of pre-existing backend/harness blockers outside the frontend scope. Both are tracked in `docs/TECH_DEBT.md`.

## Frontend Gates

- `cd web && npm run lint`: PASS. ESLint clean; architecture tests included.
- `cd web && npm run test:architecture`: PASS. 10 files, 55 tests.
- `cd web && npm run typecheck`: PASS.
- `cd web && npm test -- --run`: PASS. 84 files, 325 tests.
- `cd web && npm run build`: PASS. Largest JS chunk: `index-BcYh8N0-.js` 374.67 kB gzip 116.12 kB. No Vite `> 500 kB` chunk warning.
- `cd web && npm run test:e2e`: PASS. 58 passed, 52 skipped.

## Coverage

- Repository coverage gate was not reached because `make check-all` stopped in the `make check` stage.
- Frontend unit/route/component coverage was exercised through the full Vitest suite above.

## Skipped Tests

- Playwright golden paths: 52 skipped. These are viewport-gated specs skipped by project, not failures.
- Vitest: 0 skipped in the reported full run.

## E2E Golden Path

- `npm run test:e2e`: PASS. 58 passed, 52 skipped.
- Covered desktop/sidebar, tablet shell, mobile shell, mobile route cold loads, search submit, notifications, token case, and signal lab filter flows through existing golden-path specs.

## Make Check-All Full Output

Command:

```bash
make check-all
```

Exit code: 2.

Full final-worktree output:

```text
All checks passed!
Would reformat: scripts/regen_pulse_agent_desk_decisions.py
Would reformat: src/gmgn_twitter_intel/app/runtime/ops_diagnostics.py
Would reformat: src/gmgn_twitter_intel/app/runtime/provider_wiring/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py
Would reformat: src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py
Would reformat: src/gmgn_twitter_intel/domains/macro_intel/services/macro_asset_correlation.py
Would reformat: src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/_constants.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/prompts/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/read_models/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/repositories/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/services/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/services/evidence_ref_validator.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/services/fingerprints.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/types/__init__.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/types/evidence_refs.py
Would reformat: src/gmgn_twitter_intel/domains/narrative_intel/types/mention_semantics.py
Would reformat: src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py
Would reformat: src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_brief_worker.py
Would reformat: src/gmgn_twitter_intel/domains/news_intel/services/news_fact_candidates.py
Would reformat: src/gmgn_twitter_intel/domains/news_intel/services/text_normalization.py
Would reformat: src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_packet_builder.py
Would reformat: src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_agent_cost_report.py
Would reformat: src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py
Would reformat: src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py
Would reformat: src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py
Would reformat: src/gmgn_twitter_intel/integrations/binance/usdm_futures_client.py
Would reformat: src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py
Would reformat: src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py
Would reformat: src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py
Would reformat: src/gmgn_twitter_intel/platform/db/alembic/versions/20260520_0067_pulse_research_committee_checks.py
Would reformat: src/gmgn_twitter_intel/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py
Would reformat: tests/integration/test_api_http.py
Would reformat: tests/integration/test_narrative_repository.py
Would reformat: tests/integration/test_registry_repository.py
Would reformat: tests/unit/domains/narrative_intel/test_discussion_digest_service.py
Would reformat: tests/unit/domains/narrative_intel/test_narrative_workers.py
Would reformat: tests/unit/domains/news_intel/test_news_item_brief_validation.py
Would reformat: tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py
Would reformat: tests/unit/domains/pulse_lab/test_agent_output_normalization.py
Would reformat: tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py
Would reformat: tests/unit/integrations/openai_agents/test_structured_output_strategy.py
Would reformat: tests/unit/test_api_macro_contract.py
Would reformat: tests/unit/test_api_ops_contract.py
Would reformat: tests/unit/test_cex_binance_hard_cut_cleanup.py
Would reformat: tests/unit/test_cli_ops_contract.py
Would reformat: tests/unit/test_ops_backfill_commands.py
Would reformat: tests/unit/test_ops_diagnostics.py
Would reformat: tests/unit/test_postgres_schema.py
Would reformat: tests/unit/test_provider_capabilities.py
Would reformat: tests/unit/test_pulse_display_status.py
Would reformat: tests/unit/test_token_case_service.py
Would reformat: tests/unit/test_token_image_mirror_worker.py
57 files would be reformatted, 767 files already formatted
make[1]: *** [check] Error 1
make: *** [check-all] Error 2
```

Additional isolation note: applying `uv run ruff format` temporarily reformatted 57 files and allowed the gate to pass formatting, then `uv run mypy src` reported 101 errors in 34 unchanged backend/worker files. The mechanical format was reverted to avoid unrelated churn in this frontend branch.

## Docker Smoke

- `make docker-up`: PASS. Images `gmgn-twitter-intel-app:latest` and `gmgn-twitter-intel-migrate:latest` rebuilt; app container started.
- `docker compose ps`: app `Up ... (healthy)`; postgres `Up ... (healthy)`.
- `curl -sS http://127.0.0.1:8765/healthz`: `ok`.
- `curl -sS http://127.0.0.1:8765/readyz`: HTTP command succeeded, payload `ok: false`.
- `/readyz` reason:

```text
worker:market_tick_stream:errored:WorkerRunSoftTimeout: worker:market_tick_stream:run_once soft timeout after 120s
```

- `/readyz` DB summary: `db.ok=true`, `migration_status=ready`.
- Provider summary: `gmgn_direct_ws=streaming`, `okx_dex_ws=failed`.
- App log evidence includes OKX DEX WS `state=failed` and repeated `market tick poll quote skipped` warnings. This is recorded as backend runtime debt in `docs/TECH_DEBT.md`.

## Browser Verification

- Browser target: Docker app at `http://127.0.0.1:8765/`.
- `1366x768`: desktop sidebar expanded screenshot captured; topbar/content boxes do not overlap.
- `1366x768 collapsed`: desktop collapsed rail screenshot captured.
- `834x1194`: tablet screenshot captured; topbar/content boxes do not overlap, sidebar trigger remains reachable.
- `390x844`: mobile screenshot captured; topbar is 48px high and content begins below it.
- `390x844 drawer`: mobile drawer screenshot captured; route navigation is visible and touch sized.
- Screenshots:
  - `docs/generated/frontend-verification/shadcn-hardening-desktop-1366.png`
  - `docs/generated/frontend-verification/shadcn-hardening-desktop-1366-collapsed.png`
  - `docs/generated/frontend-verification/shadcn-hardening-tablet-834.png`
  - `docs/generated/frontend-verification/shadcn-hardening-mobile-390.png`
  - `docs/generated/frontend-verification/shadcn-hardening-mobile-390-drawer.png`
- Console/network note: browser saw repeated `503 /api/status` errors because `/readyz` is false from the backend worker blocker. No layout break was observed in screenshots or Playwright shell specs.

## Other Commands Run

- `git diff --check`: PASS before Task 6 amend.
- `git diff --check HEAD~1..HEAD`: PASS for Task 6 commit.
- `git diff --check`: PASS before post-main e2e alignment commit.
- `find web/src -path '*/test/*' -o -path '*/tests/*' -o -path '*/fixtures/*' -o -path '*/__fixtures__/*'`: no production test/fixture folders.
- `rg -n "desktop-side-rail|mobile-route-nav|side-rail|route-nav" web/src web/tests/architecture`: retired fragments appear only in architecture tests.

## Risks And Follow-Ups

- `make check-all` is blocked by existing backend/harness formatting and mypy debt; not introduced by this frontend branch.
- Docker `/readyz` is blocked by `market_tick_stream` / OKX runtime state; not introduced by this frontend branch.
- Frontend-specific gates, route code splitting, shadcn primitive usage, PageState migration, CSS diet, and Playwright golden paths are green.
