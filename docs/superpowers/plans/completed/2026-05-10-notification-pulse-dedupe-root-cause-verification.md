# Notification and Pulse Dedupe Root Cause Verification

**Date:** 2026-05-10
**Branch:** codex/dedupe-investigation

## Commands

- `uv run ruff check .` — PASS, output: `All checks passed!`
- `uv run pytest` — PASS, output: `383 passed, 136 skipped in 4.16s`
- `uv run python -m compileall src tests` — PASS, command exited 0 after compiling changed test/source modules.

## Focused Regression Evidence

- Notification conflict aggregation:
  - Command:
    `GMGN_TEST_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:55433/gmgn_twitter_intel_test uv run pytest tests/test_notification_repository.py tests/test_notification_rules.py tests/test_settings.py tests/test_pulse_candidate_worker.py tests/test_pulse_repository.py -q`
  - Result before final cleanup: `61 passed in 9.34s`
- Signal Pulse stable dedup:
  - `tests/test_notification_rules.py::test_signal_pulse_dedup_key_uses_candidate_status_bucket_not_signature` verifies changing `notification_signature` no longer changes the dedup key.
- No compatibility fallback:
  - `tests/test_notification_rules.py::test_watched_account_activity_does_not_fall_back_to_event_key_when_cooldown_zero` passed.
  - `tests/test_notification_rules.py::test_watched_account_token_alert_does_not_fall_back_to_alert_key_when_cooldown_zero` passed.
- Pulse active-job guard:
  - `tests/test_pulse_candidate_worker.py::test_existing_pending_job_blocks_signature_churn_reenqueue` passed.
- Pulse material-rerun gate:
  - `tests/test_pulse_candidate_worker.py::test_cooldown_bypass_matrix` passed after removing social-phase, heat-bucket, and market-fresh-only bypasses.
- Pulse storage active-state preservation:
  - `tests/test_pulse_repository.py::test_enqueue_job_preserves_active_retry_state_on_signature_churn` passed.

## Live Smoke Evidence

- Docker rebuild/recreate:
  - Command: `docker compose up -d --build`
  - Result: `gmgn-twitter-intel-migrate` and `gmgn-twitter-intel-app` images built; `migrate` exited; `app` recreated and started.
- Container health:
  - Command: `docker compose ps`
  - Result: `gmgn-twitter-intel-app-1` is `Up ... (healthy)` and PostgreSQL is `Up ... (healthy)`.
- `/healthz`:
  - Command: `curl -sS http://127.0.0.1:8765/healthz`
  - Result: `ok`
- `/readyz`:
  - Command: `curl -sS http://127.0.0.1:8765/readyz`
  - Result: `ok=true`, `db.ok=true`, `notifications.worker_running=true`, `pulse_agent.worker_running=true`.
- Collector reconnect:
  - App logs show `GMGN 直连 WS 已连接` and subscriptions for `twitter_monitor_basic` / `twitter_monitor_token`.
- Notification duplicate SQL probe: not run for a post-deploy window because the new app had just started; use the probe in the plan after at least one full notification/Pulse cycle.
- Pulse run churn SQL probe: not run for a post-deploy window because the new app had just started; use the probe in the plan after at least one full Pulse cycle.

## Additional Notes

- An exploratory full run with `GMGN_TEST_POSTGRES_DSN` pointed at an empty isolated test Postgres produced unrelated integration failures because some tests treat that variable as a live data DSN and others still use old fixture SQL. The default required command `uv run pytest` passed.
- The temporary Docker test database `gmgn-twitter-intel-test-postgres-dedupe` was removed after verification.

## Risks

- Watched-account activity now aggregates by account/action/bucket, so individual posts inside a bucket update `occurrence_count` rather than creating separate notification rows.
- Watched-account token alerts now aggregate by asset/author/bucket, so repeated mentions inside a bucket update one row and do not trigger duplicate PushDeer delivery.
- Signal Pulse same-candidate same-status thesis updates inside a cooldown bucket update payload and `occurrence_count` without a new external delivery.
- Agent retries for model errors still run up to `max_attempts`; this is expected retry behavior, not duplicate analysis.
