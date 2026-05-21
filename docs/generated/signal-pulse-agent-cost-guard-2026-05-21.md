# Signal Pulse Agent Cost Guard Read-only Report

- generated_date: 2026-05-21
- lookback_hours: 24
- dry_run: true
- since_ms: 1779236179547
- now_ms: 1779322579547

## Runtime Config Confirmation

- config_path: /Users/qinghuan/.gmgn-twitter-intel/config.yaml
- workers_config_path: /Users/qinghuan/.gmgn-twitter-intel/workers.yaml
- config_path_under_operator_home: true
- workers_config_path_under_operator_home: true

## Summary

- runs_total: 1156
- backpressure_circuit_open_runs: 463
- hidden_invalid_output_runs: 353
- deepseek_total_tokens: 8047265
- hidden_invalid_output_tokens: 7833907
- predicted_deepseek_tokens_after: 194683
- predicted_deepseek_reduction_ratio: 0.9758
- duplicate_success_fingerprint_groups: 0
- extra_success_runs_same_fingerprint: 0
- display_trade_candidate: 9
- display_token_watch: 14

## Steps By Stage Model Status

| stage | model | status | steps | tokens |
| --- | --- | --- | --- | --- |
| bear_case | deepseek-v4-flash | failed | 25 | 0 |
| bear_case | deepseek-v4-flash | ok | 232 | 2775650 |
| bear_case | qwen3.6 | failed | 9 | 128470 |
| bear_case | qwen3.6 | ok | 43 | 501296 |
| bear_case | qwen3.6 | timeout | 2 | 0 |
| claim_verifier | deepseek-v4-flash | ok | 363 | 0 |
| claim_verifier | qwen3.6 | ok | 201 | 0 |
| decision_maker | qwen3.6 | failed | 12 | 26957 |
| decision_maker | qwen3.6 | ok | 77 | 796227 |
| decision_maker | qwen3.6 | timeout | 1 | 0 |
| deterministic_eval | deepseek-v4-flash | ok | 363 | 0 |
| deterministic_eval | qwen3.6 | ok | 201 | 0 |
| evidence_completeness_gate | deepseek-v4-flash | ok | 916 | 0 |
| evidence_completeness_gate | qwen3.6 | ok | 240 | 0 |
| evidence_debate | qwen3.6 | failed | 22 | 33344 |
| evidence_debate | qwen3.6 | ok | 90 | 606484 |
| evidence_debate | qwen3.6 | timeout | 5 | 0 |
| evidence_pack | deepseek-v4-flash | ok | 916 | 0 |
| evidence_pack | qwen3.6 | ok | 240 | 0 |
| recommendation_clipper | deepseek-v4-flash | ok | 363 | 0 |
| recommendation_clipper | qwen3.6 | ok | 201 | 0 |
| risk_portfolio_judge | deepseek-v4-flash | failed | 79 | 117115 |
| risk_portfolio_judge | deepseek-v4-flash | ok | 153 | 2107719 |
| risk_portfolio_judge | qwen3.6 | failed | 14 | 64288 |
| risk_portfolio_judge | qwen3.6 | ok | 27 | 416567 |
| risk_portfolio_judge | qwen3.6 | timeout | 2 | 0 |
| signal_analyst | deepseek-v4-flash | failed | 98 | 155664 |
| signal_analyst | deepseek-v4-flash | ok | 257 | 2891117 |
| signal_analyst | qwen3.6 | failed | 9 | 133908 |
| signal_analyst | qwen3.6 | ok | 54 | 623509 |
| signal_analyst | qwen3.6 | timeout | 1 | 0 |
| write_gate | deepseek-v4-flash | ok | 363 | 0 |
| write_gate | qwen3.6 | ok | 201 | 0 |

## Tokens By Display Status

| display_status | steps | tokens |
| --- | --- | --- |
| display_risk_rejected_high_info | 440 | 919550 |
| display_token_watch | 121 | 402103 |
| display_trade_candidate | 72 | 184583 |
| hidden_abstain | 40 | 64007 |
| hidden_insufficient_evidence | 552 | 0 |
| hidden_invalid_output | 3048 | 9762581 |
| hidden_source_quality | 213 | 18675 |
| unknown | 1294 | 26816 |
