# Signal Pulse Agent Cost Guard Verification

**Date:** 2026-05-21
**Worktree:** `.worktrees/signal-pulse-agent-cost-guard/`
**Branch:** `codex/signal-pulse-agent-cost-guard`

## Config Confirmation

`uv run gmgn-twitter-intel config` confirmed the live runtime files are the
operator-owned paths:

- `config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`

No secret values were printed. The live operator config still has Pulse lanes
set to `deepseek-v4-flash`; this change updates repository defaults and code
behavior, but does not mutate operator-owned config automatically.

## Automated Verification

Passed:

```bash
uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py tests/unit/domains/pulse_lab/test_agent_eval_v2.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_settings.py -q
```

Result: `125 passed`.

Passed:

```bash
uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repositories.py -q
```

Result: `123 passed`.

Passed:

```bash
uv run pytest tests/integration/test_pulse_repositories.py::test_pulse_runs_terminal_run_for_fingerprint_returns_latest_matching_terminal_run tests/integration/test_pulse_repositories.py::test_release_running_job_for_provider_cooldown_delays_without_burning_attempt -q
```

Result: `2 passed`.

Passed:

```bash
uv run ruff check src/gmgn_twitter_intel/domains/pulse_lab src/gmgn_twitter_intel/integrations/openai_agents src/gmgn_twitter_intel/platform/config/settings.py scripts/evaluate_signal_pulse_agent_cost_guard.py tests/unit/domains/pulse_lab tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_settings.py tests/integration/test_pulse_repositories.py
```

Result: `All checks passed`.

## Live Read-only Report

Command:

```bash
uv run python scripts/evaluate_signal_pulse_agent_cost_guard.py --lookback-hours 24 --dry-run
```

Generated:

`docs/generated/signal-pulse-agent-cost-guard-2026-05-21.md`

Live 24h summary from the generated report:

- runs_total: 1184
- backpressure_circuit_open_runs: 483
- hidden_invalid_output_runs: 354
- deepseek_total_tokens: 7,939,347
- hidden_invalid_output_tokens: 7,757,552
- predicted_deepseek_tokens_after: 163,120
- predicted_deepseek_reduction_ratio: 0.9795
- duplicate_success_fingerprint_groups: 0
- extra_success_runs_same_fingerprint: 0
- display_trade_candidate: 9
- display_token_watch: 13

Interpretation: the dry-run policy predicts a 97.95% DeepSeek token reduction
for the measured 24h window while preserving public trade/watch rows. The
largest savings still come from preventing hidden/invalid paths from reaching
the DeepSeek judge.

## Residual Risk

- Operator `~/.gmgn-twitter-intel/workers.yaml` still explicitly routes Pulse
  lanes to DeepSeek. Switching live traffic to the repository default model
  split requires an operator config edit.
- The read-only report estimates public preservation from current
  `display_status` and dry-run suppression policy. It does not replay every
  future model response, so the first live rollout should be watched for one
  full 1h and 4h cycle.
- Qwen research latency remains a throughput risk; the cost guard reduces
  DeepSeek spend but does not make Qwen faster.
